# Metahuman API
# Collection of classes and functions to extract data from Metahuman face rig for
# retargeting the FBX animation from the root joint back onto the face rig controls

from functools import wraps
import logging
import re
import time

import maya.cmds as cmds
import maya.mel as mel

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Excluded from zeroing out
ZERO_OUT_EXCLUDED_CONTROLS = ['CTRL_eyesAimFollowHead',
                              'CTRL_faceGUIfollowHead'
                              'CTRL_lookAtSwitch',
                              'CTRL_rigLogicSwitch',
                              'CTRL_neckCorrectivesMultiplyerU',
                              'CTRL_neckCorrectivesMultiplyerM',
                              'CTRL_neckCorrectivesMultiplyerD',
                              'CTRL_faceGUI',
                              'CTRL_GUIswitch',
                              'CTRL_L_mouth_lipsPressD',
                              'CTRL_R_mouth_lipsPressD',
                              'CTRL_expressions',
                              'CTRL_rigLogic'
                              ]

EXCLUDED_RETARGET_CONTROLS = ['CTRL_C_eye',
                              'CTRL_C_eyesAim',
                              'CTRL_L_eyeAim',
                              'CTRL_R_eyeAim',
							  'CTRL_lookAtSwitch',
                              'CTRL_convergenceSwitch',
                              'CTRL_faceTweakersGUI']

EXCLUDED_RETARGET_CONTROLS.extend(ZERO_OUT_EXCLUDED_CONTROLS)
DEFAULT_NAMESPACE = ':'

MINIMUM_LEVEL_SEQUENCE_API = 20220400
VERIFIED_LEVEL_SEQUENCE_VERSIONS = [20200400, 20220400, 20220500, 20230300]

NAMED_FPS = {
	'game': 15.0, 'film': 24.0, 'pal': 25.0, 'ntsc': 30.0,
	'show': 48.0, 'palf': 50.0, 'ntscf': 60.0,
}


class ControllerError(Exception):
	pass

class SelectionError(Exception):
	pass

class MetahumanError(Exception):
	pass

def strip_namespace(name):
	'''
	Strip namespace from a node name.
	Args:
		name (str): node name, may include a DAG path and/or a namespace
	Returns:
		str: short node name with no path or namespace
	'''
	return name.split('|')[-1].split(':')[-1]

def get_namespace(name):
	'''
	Get the namespace of a node.
	Args:
		name (str): node name, may include a DAG path
	Returns:
		str: namespace with trailing colon, or ''
	'''
	short_name = name.split('|')[-1]
	if ':' not in short_name:
		return ''
	return short_name.rsplit(':', 1)[0] + ':'

def plug(node, attr):
	'''
	Build a 'node.attr' plug string.
	Args:
		node (str): node name
		attr (str): attribute name
	Returns:
		str: plug string
	'''
	return '{}.{}'.format(node, attr)

def set_current_namespace(namespace):
	'''
	Set the current namespace.
	Args:
		namespace (str): namespace to set as current, '' for root
	'''
	cmds.namespace(setNamespace=namespace if namespace else ':')

def _fbx_flag(command, value):
	'''
	Evaluate a single FBX plugin MEL command with correctly formatted value.
	Args:
		command (str): FBX MEL command name, e.g. 'FBXExportShapes'
		value (bool or str): value to pass with -v
	'''
	if isinstance(value, bool):
		value = 'true' if value else 'false'
	elif isinstance(value, str):
		value = '"{}"'.format(value)
	mel.eval('{} -v {}'.format(command, value))

def _mel_path(path):
	'''
	Args:
		path (str): file path
	Returns:
		str: absolute path with forward slashes, safe to embed in a MEL command
	'''
	return path.replace('\\', '/')

def scene_fps():
	'''
	Returns:
		float: frames-per-second of the current scene's time unit
	'''
	unit = cmds.currentUnit(query=True, time=True)
	if unit in NAMED_FPS:
		return NAMED_FPS[unit]
	match = re.match(r'^([\d.]+)(fps|df)$', unit)
	return float(match.group(1)) if match else 24.0

def _has_attr(node, attr):
	'''
	Args:
		node (str): node name
		attr (str): attribute name
	Returns:
		bool: True if node has attr
	'''
	return cmds.attributeQuery(attr, node=node, exists=True)

def _anim_curves_on(node_plug):
	'''
	Args:
		node_plug (str): 'node.attr' plug string
	Returns:
		list of str: incoming animCurve nodes connected to node_plug
	'''
	return cmds.listConnections(node_plug, source=True, destination=False, type='animCurve') or []

def _safe_delete(nodes):
	'''
	Delete nodes, skipping any that no longer exist (e.g. already removed as a
	side effect of deleting another node in the same list).
	Args:
		nodes (iterable of str): node names to delete
	'''
	existing = [node for node in nodes if cmds.objExists(node)]
	if existing:
		cmds.delete(existing)

class Controller:

	def __init__(self, control, ctrl_expressions_node):
		'''
		Class to hold and train facial expressions to control channel attributes
		Args:
			control (str): control transform node name
			ctrl_expressions_node (str): transform node name that holds facial expressions
		'''
		if not cmds.objExists(control) or not cmds.objectType(control, isAType='transform'):
			raise ControllerError('{} is not a control transform'.format(control))
		if not cmds.objExists(ctrl_expressions_node) or not cmds.objectType(ctrl_expressions_node, isAType='transform'):
			raise ControllerError('{} is not the CTRL_expressions node!'.format(ctrl_expressions_node))

		if strip_namespace(ctrl_expressions_node) != 'CTRL_expressions':
			raise ControllerError('{} is not the CTRL_expressions node!'.format(ctrl_expressions_node))

		expression_list = cmds.listAttr(ctrl_expressions_node, userDefined=True, scalar=True, shortNames=True) or []

		if not expression_list:
			raise ControllerError('Missing expressions on the {}! Unable to process!'.format(ctrl_expressions_node))

		self.control = control
		self._ctrl_expressions_node = ctrl_expressions_node
		self._expression_list = expression_list
		self._control_mapping = {}
		self.train_control_expressions()

	def train_control_expressions(self):
		''' Trains controls to expression by determining the control limits and what's keyable
			and creates a mapping between the controls attribute and driven expression

			While the controls are driven with a similar animCurve name that the incoming FBX data will have,
			there's a few animCurves that don't follow this convention so will train the data. Takes longer
			to build but more reliable.
		'''
		control_limits = {}
		self._control_mapping = {}
		mapping = {}
		tx_plug = plug(self.control, 'tx')
		ty_plug = plug(self.control, 'ty')
		if cmds.getAttr(tx_plug, settable=True) and cmds.getAttr(tx_plug, keyable=True):
			control_limits[tx_plug] = [cmds.transformLimits(self.control, translationX=True, query=True), 'tx']
		if cmds.getAttr(ty_plug, settable=True) and cmds.getAttr(ty_plug, keyable=True):
			control_limits[ty_plug] = [cmds.transformLimits(self.control, translationY=True, query=True), 'ty']
		if control_limits:
			for control_plug, (ctrl_limits, channel_name) in control_limits.items():
				for value in ctrl_limits:
					# Set the control value which will drive the expression
					cmds.setAttr(control_plug, value)

					# Loop through expressions to determine what is active
					for exp in self._expression_list:
						cur_value = cmds.getAttr(plug(self._ctrl_expressions_node, exp))
						if cur_value > 0 or cur_value < 0:
							# The expression name matches the keyframed attribute name from incoming FBX file
							# This will make it easier to connect the keyframe data to a control
							driven_anim_name = 'CTRL_expressions_{}'.format(exp)
							mapping[driven_anim_name] = [plug(self.control, channel_name), value]
				# Reset the control
				cmds.setAttr(control_plug, 0.0)

		for key, (attr_plug, value) in mapping.items():
			if attr_plug not in self._control_mapping:
				self._control_mapping[attr_plug] = []
			self._control_mapping[attr_plug].append([key, value])

	@property
	def control_mapping(self):
		return self._control_mapping

	def is_valid(self):
		if self.control_mapping:
			return True
		else:
			return False

def show_wait_cursor(func):
	''' Decorator for waitCursor'''
	@wraps(func)
	def wrapper(*args, **kwargs):
		cmds.waitCursor(state=True)
		try:
			result = func(*args, **kwargs)
		finally:
			cmds.waitCursor(state=False)
		return result
	return wrapper

def load_plugin(plugin_name='fbxmaya'):
	'''
	Load the plugin if not already loaded
	Args:
		plugin_name (str): name of plugin
	'''
	loaded_plugins = cmds.pluginInfo(query=True, listPlugins=True) or []
	if plugin_name not in loaded_plugins:
		cmds.loadPlugin(plugin_name, quiet=True)

def get_scene_namespaces(exclude=('UI', 'shared')):
	'''
	List all namespaces present in the scene, root not included.
	Args:
		exclude (tuple of str): namespace names to always omit (Maya's
			own built-in 'UI'/'shared' namespaces by default)
	Returns:
		list of str: namespace names with trailing colon (e.g. 'char1:'),
			sorted
	'''
	found = cmds.namespaceInfo(':', listOnlyNamespaces=True, recurse=True) or []
	return sorted('{}:'.format(ns) for ns in found if ns not in exclude)

def get_face_controls(namespace=DEFAULT_NAMESPACE):
	'''
	Get a list of metahuman face controls
	Args:
		namespace (str): namespace
	Returns:
		(list of str): list of face control long DAG paths
	'''
	control_set = 'FacialControls'
	face_control_set = '{}{}'.format(namespace, control_set)
	if cmds.objExists(face_control_set):
		cmds.select(face_control_set, replace=True)
		controls = cmds.ls(selection=True, long=True) or []
	else:
		# If we're missing the FacialControls set, will look by CTRL_ convention naming
		controls = cmds.ls('{}{}'.format(namespace, 'CTRL_*'), type='transform', long=True) or []

	face_controls = []
	# Some controls are shapes so make sure the list is just transforms
	for control in controls:
		if cmds.objectType(control, isAType='transform'):
			face_controls.append(control)
		if cmds.objectType(control, isAType='mesh'):
			parent = cmds.listRelatives(control, parent=True, fullPath=True)
			if parent:
				face_controls.append(parent[0])
	cmds.select(clear=True)
	return face_controls

def select_face_controls(namespace=DEFAULT_NAMESPACE):
	'''
	Select face controls
	Args:
		namespace (str): namespace
	Returns:
		bool: True if controls present, otherwise False
	'''
	result = False
	controls = get_face_controls(namespace)
	if controls:
		cmds.select(controls, replace=True)
		result = True
	return result

def zero_out_face_controls(namespace=DEFAULT_NAMESPACE):
	'''
	Zeroes out all controls
	Args:
		namespace (str): namespace
	Returns:
		bool: True if controls present, otherwise False
	'''
	result = False
	selection = cmds.ls(selection=True, long=True) or []
	controls = get_face_controls(namespace)
	if controls:
		result = True
	for control in controls:
		if strip_namespace(control) not in ZERO_OUT_EXCLUDED_CONTROLS:
			cmds.setAttr(plug(control, 'translateY'), 0.0)
			if not cmds.getAttr(plug(control, 'translateX'), lock=True):
				cmds.setAttr(plug(control, 'translateX'), 0.0)
	if selection:
		cmds.select(selection, replace=True)
	return result

def get_controllers(namespace=DEFAULT_NAMESPACE):
	'''
	Get all controller objects
	Args:
		namespace (str): rig namespace, so we can gather all the controls

	Returns:
		tuple(list of Controller, error message): list of Controller objects, error message
	'''
	error_msg = ''
	face_controls = get_face_controls(namespace)
	if not face_controls:
		error_msg = 'Unable to find face controls! Either not a Metahuman or controls are missing!'
		return [], error_msg

	expression_node = '{}{}'.format(namespace, 'CTRL_expressions')
	if not cmds.objExists(expression_node):
		error_msg = 'Unable to find CTRL_expressions! Unable to process!'
		return [], error_msg
	# Zero out controls so we get the proper control mapping
	zero_out_face_controls(namespace)
	controllers = []
	for face_control in face_controls:
		if strip_namespace(face_control) not in EXCLUDED_RETARGET_CONTROLS:
			controller = Controller(face_control, expression_node)
			if controller.is_valid():
				controllers.append(controller)
	return controllers, error_msg

def import_fbx_animation(fbx_path, take=1):
	'''
	Import fbx animation data
	Args:
		fbx_path (str): absolute path to fbx animation
		take (int): FBX take index to import
	Returns:
		(set of str): long names of imported nodes
	'''
	# Import animation
	_fbx_flag('FBXImportShapes', False)
	_fbx_flag('FBXImportSkins', False)
	_fbx_flag('FBXImportMode', 'add')
	_fbx_flag('FBXImportMergeAnimationLayers', False)
	_fbx_flag('FBXImportProtectDrivenKeys', True)
	_fbx_flag('FBXImportSetMayaFrameRate', False)
	_fbx_flag('FBXImportFillTimeline', False)

	cur_nodes = set(cmds.ls(long=True))
	mel.eval('FBXImport -f "{}" -t {}'.format(_mel_path(fbx_path), int(take)))
	return set(cmds.ls(long=True)) - cur_nodes

def probe_fbx_takes(fbx_path, fps=None):
	'''
	Read take time ranges from an FBX file without importing it into the scene.
	Args:
		fbx_path (str): absolute path to fbx animation
		fps (float): frames-per-second to convert seconds to frames; scene fps if omitted
	Returns:
		list of dict: {'index', 'name', 'start', 'end', 'frame_count'} per take
	'''
	load_plugin()
	fps = float(fps) if fps else scene_fps()
	mel.eval('FBXRead -f "{}"'.format(_mel_path(fbx_path)))
	try:
		count = int(mel.eval('FBXGetTakeCount'))
		takes = []
		for i in range(1, count + 1):
			span = mel.eval('FBXGetTakeLocalTimeSpan {}'.format(i))
			start, end = span[0] * fps, span[1] * fps
			takes.append({'index': i,
			              'name': mel.eval('FBXGetTakeName {}'.format(i)),
			              'start': start,
			              'end': end,
			              'frame_count': int(round(end - start)) + 1})
		return takes
	finally:
		mel.eval('FBXClose')

def _probe_take_name(fbx_path, take):
	'''
	Lookup of a take's display name.
	Args:
		fbx_path (str): absolute path to fbx animation
		take (int): FBX take index
	Returns:
		str: take name, or '' if unavailable
	'''
	try:
		takes = probe_fbx_takes(fbx_path)
	except Exception as exc:
		logger.warning('Could not read take names from {}: {}'.format(fbx_path, exc))
		return ''
	chosen = None
	for entry in takes:
		if entry['index'] == take:
			chosen = entry
			break
	if chosen is None and takes:
		chosen = takes[0]
	return chosen['name'] if chosen else ''

def plan_sequence(fbx_paths, start_frame=1.0, gap=0.0, take=1, timeunit=None):
	'''
	Compute where each clip in fbx_paths will land if retargeted back to back.

	FBX take metadata (FBXGetTakeLocalTimeSpan) reflects the take's overall
	stored time span, which can be far longer than the actual keyed range of
	the CTRL_expressions_* curves that end up on the imported root joint --
	so this imports each file, measures the real keyframe extent, and deletes
	it again, mirroring exactly what build_merged_clip does on the real run.
	Args:
		fbx_paths (list of str): absolute paths to fbx animation, in playback order
		start_frame (float): frame the first clip starts on
		gap (float): extra frames of silence inserted between clips
		take (int): FBX take index to import from every file
		timeunit (str): time unit to measure under, e.g. 'ntsc'; current scene unit if omitted
	Returns:
		list of dict: {'path', 'take', 'start', 'end', 'frame_count', 'error'} per file
	'''
	load_plugin()
	original_unit = cmds.currentUnit(query=True, time=True)
	switch_unit = bool(timeunit) and timeunit != original_unit
	if switch_unit:
		cmds.currentUnit(time=timeunit)
	try:
		rows = []
		cursor = float(start_frame)
		for path in fbx_paths:
			take_name = _probe_take_name(path, take)
			new_nodes = import_fbx_animation(path, take=take)
			curves = cmds.ls(list(new_nodes), type='animCurve') or []
			if not curves:
				_safe_delete(new_nodes)
				rows.append({'path': path, 'take': take_name, 'start': None, 'end': None,
				             'frame_count': None, 'error': 'No animation curves in file'})
				continue

			first = min(float(cmds.findKeyframe(c, which='first')) for c in curves)
			last = max(float(cmds.findKeyframe(c, which='last')) for c in curves)
			_safe_delete(new_nodes)

			duration = last - first
			rows.append({'path': path,
			             'take': take_name,
			             'start': cursor,
			             'end': cursor + duration,
			             'frame_count': int(round(duration)) + 1,
			             'error': ''})
			cursor = cursor + duration + 1.0 + gap
		return rows
	finally:
		if switch_unit:
			cmds.currentUnit(time=original_unit)

def export_fbx_animation(fbx_path, namespace=DEFAULT_NAMESPACE):
	'''
	Export fbx animation
	Args:
		fbx_path (str): absolute path to fbx animation
		namespace (str): rig namespace
	Returns:
		(list of str): list of exported control long DAG paths
	'''
	face_controls = get_face_controls(namespace)
	if not face_controls:
		return []

	start_frame, end_frame = get_key_frame_ranges(face_controls)
	cmds.bakeResults(face_controls,
				time=(int(start_frame), int(end_frame)),
				preserveOutsideKeys=True,
				minimizeRotation=False,
				sparseAnimCurveBake=False,
				sampleBy=1,
				oversamplingRate=1,
				bakeOnOverrideLayer=False,
				removeBakedAttributeFromLayer=False,
				removeBakedAnimFromLayer=False,
				shape=False,
				controlPoints=False,
				disableImplicitControl=True)

	cmds.select(face_controls, replace=True)
	current_namespace = get_namespace(face_controls[0])
	controls = []
	# Handle exporting control animation if in namespace
	if current_namespace:
		# Set to root namespace
		set_current_namespace(':')
		for control in face_controls:
			control_name = strip_namespace(control)
			dup_control = cmds.duplicate(control, returnRootsOnly=True, inputConnections=True)[0]
			new_control = cmds.rename(dup_control, control_name)
			controls.append(new_control)
		cmds.select(controls, replace=True)
	# Set it back to current namespace
	set_current_namespace(current_namespace)
	mel.eval('FBXResetExport')
	_fbx_flag('FBXExportAnimationOnly', True)
	_fbx_flag('FBXExportBakeComplexAnimation', False)
	_fbx_flag('FBXExportLights', False)
	_fbx_flag('FBXExportCameras', False)
	_fbx_flag('FBXExportConstraints', False)
	_fbx_flag('FBXExportSkins', False)
	_fbx_flag('FBXExportApplyConstantKeyReducer', False)
	_fbx_flag('FBXExportSmoothMesh', False)
	_fbx_flag('FBXExportShapes', False)
	_fbx_flag('FBXExportEmbeddedTextures', False)
	_fbx_flag('FBXExportInputConnections', False)
	try:
		_fbx_flag('FBXExportFileVersion', 'FBX202000')
	except RuntimeError:
		logger.warning('FBX export file version FBX202000 is not recognized by this Maya/FBX '
		                'plugin combination; using the plugin default instead.')
	safe_path = fbx_path.replace('\\', '/')
	mel.eval('FBXExport -f "{}" -s'.format(safe_path))
	mel.eval('FBXExport -f "{}" -s'.format(safe_path))
	if controls:
		cmds.delete(controls)
	return face_controls

def get_root_joint(joint_list):
	'''
	Get the root joint from joint list: the first joint with no joint parent.
	Args:
		joint_list (list of str): list of joint node names

	Returns:
		str or None: root joint long name, or None
	'''
	for joint in joint_list:
		if not cmds.listRelatives(joint, parent=True, type='joint'):
			return joint
	return None

def get_key_frame_range(node):
	'''
	Get the min, max range of keyframes for this node
	Args:
		node (str): node with keys

	Returns:
		tuple(float, float): start, end of keyframes
	'''
	return float(cmds.findKeyframe(node, which='first')), float(cmds.findKeyframe(node, which='last'))

def get_key_frame_ranges(nodes):
	'''
	Get the min, max of start and end frames
	Args:
        nodes (list of str): list of nodes with keys
    Returns:
    	tuple(float, float): start, end of keyframes
	'''
	start_frames = [get_key_frame_range(node)[0] for node in nodes]
	end_frames = [get_key_frame_range(node)[1] for node in nodes]
	return min(start_frames), max(end_frames)

def combine_control_mappings(controllers):
	'''
	Flatten a list of Controllers into one control_mapping dict, suitable
	for map_and_bake.
	Args:
		controllers (list of Controller): trained controllers
	Returns:
		dict: {control_plug: [[expression_attr, driver_value], ...]}
	'''
	combined = {}
	for controller in controllers:
		combined.update(controller.control_mapping)
	return combined

def map_and_bake(control_mapping, root_joint, start_frame, end_frame):
	'''
	Drive face controls from root_joint's CTRL_expressions_* curves, then bake
	the result onto the controls once and clean up.
	Args:
		control_mapping (dict): {control_plug: [[expression_attr, driver_value], ...]},
			as produced by combine_control_mappings
		root_joint (str): node carrying the CTRL_expressions_* animated attrs
		start_frame (float): first frame to bake
		end_frame (float): last frame to bake
	Returns:
		list of str: control plugs that were baked
	'''
	blend_weighted_nodes = []
	controls_attrs_to_bake = []

	for control_attr, expression_data in control_mapping.items():
		if not cmds.objExists(control_attr):
			logger.warning('{} does not exist -- skipped'.format(control_attr))
			continue

		# Connect control channel that has more than one anim curve driving it
		if len(expression_data) > 1:
			anim_curves = []
			for expression, driver_value in expression_data:
				if not _has_attr(root_joint, expression):
					logger.warning('{} does not have {} in the name. This will be skipped!'.format(root_joint, expression))
					continue
				anim_curve = _anim_curves_on(plug(root_joint, expression))
				if not anim_curve:
					logger.error('No animation curve for {}'.format(plug(root_joint, expression)))
					continue
				# Control moves in the negative
				if driver_value == -1.0:
					cmds.scaleKey(anim_curve[0], valueScale=-1.0)
				anim_curves.append(anim_curve[0])

			if not anim_curves:
				continue

			# Connect anim curves
			bw_node = cmds.createNode('blendWeighted')
			for i, anim_curve in enumerate(anim_curves):
				cmds.connectAttr(anim_curve + '.output', '{}.input[{}]'.format(bw_node, i), force=True)
			cmds.connectAttr(bw_node + '.output', control_attr, force=True)
			blend_weighted_nodes.append(bw_node)
			controls_attrs_to_bake.append(control_attr)
		else:
			expression, driver_value = expression_data[0]
			if not _has_attr(root_joint, expression):
				logger.warning('{} does not have {} in the name. This will be skipped!'.format(root_joint, expression))
				continue
			if not _anim_curves_on(plug(root_joint, expression)):
				continue
			copied = cmds.copyKey(root_joint, attribute=expression)
			if copied:
				try:
					dest_node, dest_attr = control_attr.rsplit('.', 1)
					# Explicit time + merge: the source curve already sits at
					# final frames, so anchor the paste there rather than at
					# whatever currentTime happens to be.
					cmds.pasteKey(dest_node, attribute=dest_attr, time=(start_frame,), option='merge')
				except RuntimeError:
					logger.error('Failed to paste keys to {}'.format(control_attr))

	if controls_attrs_to_bake:
		cmds.bakeResults(controls_attrs_to_bake,
						time=(int(start_frame), int(end_frame)),
						preserveOutsideKeys=True,
						sparseAnimCurveBake=False,
						sampleBy=1,
						oversamplingRate=1,
						removeBakedAttributeFromLayer=False,
						removeBakedAnimFromLayer=False,
						shape=False,
						controlPoints=False,
						disableImplicitControl=True)

	_safe_delete(blend_weighted_nodes)
	return controls_attrs_to_bake

@show_wait_cursor
def retarget_metahuman_animation_sequence(fbx_path, namespace=DEFAULT_NAMESPACE, timeunit='ntsc'):
	'''
	Imports the fbx animation into the scene and connects the curve data to the control rig.
	Then will bake the animation on the controls and clean up the scene

	To keep the file size small and still bring in the animation, here are suggested settings
	Unreal FBX Export Options:
		* FBX Export Compatibility: 2020
		* Set ONLY these check-box's to True
			* Export Morph Targets: True
			* Export Preview Mesh: True
			* Map Skeletal Motion to Root: True
			* Export Local Time: True

	Args:
		fbx_path (str): absolute path to fbx animation
		namespace (str): rig namespace, so we can gather all the controls
  		timeunit (str): time unit to set the scene to. Default is 'ntsc' for 30fps

	Returns:
		tuple(str, str): elapsed time to complete, error message
	'''
	start_time = time.time()
	load_plugin()

	error_msg = ''
	elapsed_time = ''

	# Build control mapping
	controllers, error = get_controllers(namespace)
	if error:
		return elapsed_time, error
	control_mapping = combine_control_mappings(controllers)

	new_nodes = import_fbx_animation(fbx_path)

	cmds.currentUnit(time=timeunit)

	# Check if animCurves came in
	anim_curves = cmds.ls(list(new_nodes), type='animCurve') or []
	if not anim_curves:
		error_msg = "No animation curves present!\n\n" \
		            "Ensure the exported animation is from an animation sequence!"
		cmds.delete(list(new_nodes))
		return elapsed_time, error_msg

	new_joints = cmds.ls(list(new_nodes), type='joint', long=True) or []
	root_joint = get_root_joint(new_joints)
	if not root_joint:
		cmds.delete(list(new_nodes))
		error_msg = 'Did not find the root joint from: {}.\n' \
		            'Ensure the exported animation is from an animation sequence!'.format(fbx_path)
		return elapsed_time, error_msg

	# Get the range of keys
	start_frame, end_frame = get_key_frame_range(root_joint)

	map_and_bake(control_mapping, root_joint, start_frame, end_frame)

	cmds.delete(list(new_nodes))
	cmds.playbackOptions(animationStartTime=int(start_frame), animationEndTime=int(end_frame))

	delta_time = time.gmtime(time.time() - start_time)
	elapsed_time = str(time.strftime("%H:%M:%S", delta_time))
	logger.info("Transfer completed in: {}".format(elapsed_time))
	return elapsed_time, error_msg

def _shift_clip(new_nodes, target_start):
	'''
	Slide every animCurve in new_nodes so its earliest key lands on target_start.
	Args:
		new_nodes (iterable of str): nodes from a single FBX import
		target_start (float): frame the clip's first key should land on
	Returns:
		tuple(float, float) or None: (clip_start, clip_end) after the shift, or
			None if new_nodes carries no animCurves
	'''
	curves = cmds.ls(list(new_nodes), type='animCurve') or []
	if not curves:
		return None
	first = min(float(cmds.findKeyframe(c, which='first')) for c in curves)
	last = max(float(cmds.findKeyframe(c, which='last')) for c in curves)
	offset = float(target_start) - first
	if abs(offset) > 1e-6:
		cmds.keyframe(curves, edit=True, relative=True, timeChange=offset, option='over')
	return first + offset, last + offset

def _merge_expression_attrs(source_root, master_root, start, end, pin_previous=True):
	'''
	Copy every keyed CTRL_expressions_* attr from source_root onto master_root.
	Args:
		source_root (str): root joint of the clip just imported
		master_root (str): root joint all clips get merged onto
		start (float): clip's start frame, after shifting
		end (float): clip's end frame, after shifting
		pin_previous (bool): insert a key just before this clip on channels
			master_root already has animation on, so the previous clip's last
			value holds flat instead of ramping across the gap into this clip
	Returns:
		int: number of attrs merged
	'''
	merged = 0
	skipped = []
	for attr in cmds.listAttr(source_root, userDefined=True) or []:
		source_plug = plug(source_root, attr)
		if not _anim_curves_on(source_plug):
			continue
		if not _has_attr(master_root, attr):
			skipped.append(attr)
			continue

		target_plug = plug(master_root, attr)
		if pin_previous and _anim_curves_on(target_plug):
			try:
				cmds.setKeyframe(target_plug, time=(start - 1.0,), insert=True)
			except RuntimeError:
				pass

		if cmds.copyKey(source_root, attribute=attr, time=(start, end)):
			try:
				cmds.pasteKey(master_root, attribute=attr, time=(start,), option='merge')
				merged += 1
			except RuntimeError:
				logger.error('Failed to merge keys onto {}'.format(target_plug))

	if skipped:
		logger.warning('{} expression attrs missing on master root joint (first few: {})'.format(
			len(skipped), skipped[:5]))
	return merged

def build_merged_clip(fbx_paths, start_frame=1.0, gap=0.0, take=1, pin_previous=True):
	'''
	Import each FBX, slide it into place, and merge its CTRL_expressions_*
	curves onto one root joint so a single map_and_bake call can drive the
	whole sequence. Each clip starts where the previous one ended, +1, plus gap.
	Args:
		fbx_paths (list of str): absolute paths to fbx animation, in playback order
		start_frame (float): frame the first clip starts on
		gap (float): extra frames of silence inserted between clips
		take (int): FBX take index to import from every file
		pin_previous (bool): see _merge_expression_attrs
	Returns:
		tuple(str or None, list of str, float, float, list of dict):
			master_root (None if no usable clip found), master_nodes (caller
			owns deleting these), seq_start, seq_end, placements
			({'path', 'start', 'end'} per clip actually merged)
	'''
	master_root = None
	master_nodes = []
	seq_start = seq_end = None
	placements = []
	cursor = float(start_frame)

	for path in fbx_paths:
		new_nodes = import_fbx_animation(path, take=take)

		if not cmds.ls(list(new_nodes), type='animCurve'):
			logger.warning('No animation curves in {} -- skipping'.format(path))
			_safe_delete(new_nodes)
			continue

		root = get_root_joint(cmds.ls(list(new_nodes), type='joint') or [])
		if root is None:
			logger.warning('No root joint in {} -- skipping'.format(path))
			_safe_delete(new_nodes)
			continue

		span = _shift_clip(new_nodes, cursor)
		if span is None:
			_safe_delete(new_nodes)
			continue
		clip_start, clip_end = span

		if master_root is None:
			master_root = root
			master_nodes = list(new_nodes)
		else:
			_merge_expression_attrs(root, master_root, clip_start, clip_end, pin_previous=pin_previous)
			_safe_delete(new_nodes)

		seq_start = clip_start if seq_start is None else min(seq_start, clip_start)
		seq_end = clip_end if seq_end is None else max(seq_end, clip_end)
		placements.append({'path': path, 'start': clip_start, 'end': clip_end})
		cursor = clip_end + 1.0 + gap

	if master_root is None:
		return None, [], 0.0, 0.0, placements
	return master_root, master_nodes, seq_start, seq_end, placements

@show_wait_cursor
def retarget_metahuman_animation_sequences(fbx_paths, namespace=DEFAULT_NAMESPACE, timeunit='ntsc',
                                           start_frame=1.0, gap=0.0, take=1, pin_previous=True):
	'''
	Retarget several Animation Sequence FBX clips onto one face board, laid
	end to end starting at start_frame.
	Args:
		fbx_paths (list of str): absolute paths to fbx animation, in playback order
		namespace (str): rig namespace, so we can gather all the controls
		timeunit (str): time unit to set the scene to before importing anything
		start_frame (float): frame the first clip starts on
		gap (float): extra frames of silence inserted between clips
		take (int): FBX take index to import from every file
		pin_previous (bool): see _merge_expression_attrs
	Returns:
		tuple(str, str, list of dict): elapsed time to complete, error message,
			placements ({'path', 'start', 'end'} per clip actually merged)
	'''
	start_time = time.time()
	load_plugin()

	error_msg = ''
	elapsed_time = ''

	controllers, error = get_controllers(namespace)
	if error:
		return elapsed_time, error, []
	control_mapping = combine_control_mappings(controllers)

	# Set the time unit BEFORE any import: currentUnit defaults to
	# updateAnimation=True and will rescale curves already in the scene.
	if timeunit:
		cmds.currentUnit(time=timeunit)

	master_root, master_nodes, seq_start, seq_end, placements = build_merged_clip(
		fbx_paths, start_frame=start_frame, gap=gap, take=take, pin_previous=pin_previous)

	if master_root is None:
		error_msg = ('No usable animation found in the supplied FBX files.\n\n'
		             'Ensure each export came from an animation sequence.')
		return elapsed_time, error_msg, []

	map_and_bake(control_mapping, master_root, seq_start, seq_end)

	_safe_delete(master_nodes)
	cmds.playbackOptions(animationStartTime=int(seq_start), animationEndTime=int(seq_end),
	                     minTime=int(seq_start), maxTime=int(seq_end))

	delta_time = time.gmtime(time.time() - start_time)
	elapsed_time = str(time.strftime("%H:%M:%S", delta_time))
	logger.info("Sequence transfer completed in: {}".format(elapsed_time))
	return elapsed_time, error_msg, placements


def retarget_metahuman_level_sequence(fbx_path, namespace=DEFAULT_NAMESPACE, timeunit='film'):
	'''
	Requires a minimum Maya API version of MINIMUM_LEVEL_SEQUENCE_API; a
	warning is logged (but import still proceeds) for any API version not
	in VERIFIED_LEVEL_SEQUENCE_VERSIONS.

	This only supports FBX data exported from a Level Sequence exported from
	the face track in Unreal. The data is hit or miss due to FBX incompatibility issues with Maya.
	It's recommended to use	'retarget_metahuman_animation_sequence' instead for broader compatibility

	References in FBX file and copies the keys from the attributes over to the face controls
	Args:
		fbx_path (str): path to exported FBX file from Unreal
		namespace (str): current namespace
  		timeunit (str): time unit to set the scene to. Default is 'film' for 24fps
	Returns:
		tuple(str, str): elapsed time to complete, error message
	'''
	start_time = time.time()
	load_plugin()

	error_msg = ''
	elapsed_time = ''

	api_version = cmds.about(api=True)
	if api_version < MINIMUM_LEVEL_SEQUENCE_API:
		error_msg = 'This version (year.cut) of Maya is not supported for level sequence import: {}'.format(api_version)
		return elapsed_time, error_msg
	if api_version not in VERIFIED_LEVEL_SEQUENCE_VERSIONS:
		logger.warning('Level sequence import is unverified on Maya API {}. '
		               'Prefer the animation sequence workflow if you hit issues.'.format(api_version))

	cmds.currentUnit(time=timeunit)

	nodes = cmds.file(fbx_path, reference=True, namespace=':', returnNewNodes=True) or []
	reference_file = None
	for node in cmds.ls(nodes, type='reference') or []:
		try:
			reference_file = cmds.referenceQuery(node, filename=True)
		except RuntimeError:
			reference_file = None
		if reference_file:
			break

	if not nodes:
		error_msg = '{} is an empty file!'.format(fbx_path)
		if reference_file:
			cmds.file(reference_file, removeReference=True)
		return elapsed_time, error_msg

	# Check if animCurves came in
	anim_curves = cmds.ls(nodes, type='animCurve') or []
	if not anim_curves:
		error_msg = "No animation curves present!\n\n" \
		            "Export Facial animation from Animation Sequence \n" \
		            "Then use 'Import FBX Animation Sequence File'"
		if reference_file:
			cmds.file(reference_file, removeReference=True)
		return elapsed_time, error_msg

	control_board = None
	for node in cmds.ls(nodes) or []:
		if strip_namespace(node) == 'Face_ControlBoard_CtrlRig':
			control_board = node
			break
	if control_board is None:
		error_msg = "Missing Face_ControlBoard_CtrlRig node!\nUnable to import animation!"
		if reference_file:
			cmds.file(reference_file, removeReference=True)
		return elapsed_time, error_msg

	keyed_attributes = {}
	for attr_name in cmds.listAttr(control_board, keyable=True, shortNames=True) or []:
		if 'CTRL_' in attr_name:
			index = attr_name.find("FBX")
			if index != -1:
				channel_name = attr_name[-1]
				if channel_name == 'X':
					driven_channel = 'translateX'
				elif channel_name == 'Y':
					driven_channel = 'translateY'
				elif channel_name == 'Z':
					driven_channel = 'translateZ'
				else:
					driven_channel = 'translateY'
				control_name = attr_name[:index]
				if control_name not in EXCLUDED_RETARGET_CONTROLS:
					control_name = '{}{}'.format(namespace, control_name)
					result = (control_name, driven_channel)
					keyed_attributes[attr_name] = result
			else:
				if attr_name not in EXCLUDED_RETARGET_CONTROLS:
					control_name = '{}{}'.format(namespace, attr_name)
					result = (control_name, 'translateY')
					keyed_attributes[attr_name] = result

	copied_keys = []
	for driver_attr_name, (control_name, channel) in keyed_attributes.items():
		if cmds.objExists(control_name):
			driven_plug = plug(control_name, channel)
			if cmds.getAttr(driven_plug, settable=True) and not cmds.getAttr(driven_plug, lock=True):
				copied = cmds.copyKey(control_board, attribute=driver_attr_name)
				if copied:
					try:
						dest_node, dest_attr = driven_plug.rsplit('.', 1)
						cmds.pasteKey(dest_node, attribute=dest_attr)
					except RuntimeError:
						logger.error('Failed to paste keys to {}'.format(driven_plug))
					copied_keys.append(driven_plug)

	if len(copied_keys) == 0:
		error_msg = "Missing animation data. Possible incompatible FBX data."
		if reference_file:
			cmds.file(reference_file, removeReference=True)
		return elapsed_time, error_msg

	# Cleanup
	for node in cmds.ls(nodes, type='reference') or []:
		try:
			reference_file = cmds.referenceQuery(node, filename=True)
		except RuntimeError:
			reference_file = None
		if reference_file:
			cmds.file(reference_file, removeReference=True)
			break

	delta_time = time.gmtime(time.time() - start_time)
	elapsed_time = str(time.strftime("%H:%M:%S", delta_time))
	logger.info("Transfer completed in: {}".format(elapsed_time))
	return elapsed_time, error_msg

def retarget_metahuman_level_sequences(fbx_paths, namespace=DEFAULT_NAMESPACE, timeunit='film'):
	'''
	Batch-run retarget_metahuman_level_sequence over several FBX files. Each
	file is imported and keyed independently, at its own native frame range --
	there is no end-to-end placement/offset like the animation-sequence
	workflow gets, since referenced Level Sequence FBX has no root joint to
	merge clips onto.
	Args:
		fbx_paths (list of str): absolute paths to fbx animation
		namespace (str): rig namespace, so we can gather all the controls
		timeunit (str): time unit to set the scene to. Default is 'film' for 24fps
	Returns:
		list of dict: {'path', 'elapsed', 'error'} per file, in fbx_paths order
	'''
	results = []
	for fbx_path in fbx_paths:
		elapsed_time, error_msg = retarget_metahuman_level_sequence(fbx_path, namespace=namespace, timeunit=timeunit)
		results.append({'path': fbx_path, 'elapsed': elapsed_time, 'error': error_msg})
	return results
