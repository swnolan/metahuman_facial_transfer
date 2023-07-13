# Metahuman API
# Collection of classes and functions to extract data from Metahuman face rig for
# retargeting the FBX animation from the root joint back onto the face rig controls

from functools import wraps
import logging
import time

try:
	import pymel.core as pm
except:
	raise ImportError("Must have PyMEL installed. Update your Maya installation to include this.")
import maya.cmds as cmds
import pymel.versions

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
                              'CTRL_faceGUI'
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


class ControllerError(Exception):
	pass

class SelectionError(Exception):
	pass

class MetahumanError(Exception):
	pass

class Controller:
	
	def __init__(self, control, ctrl_expressions_node):
		'''
		Class to hold and train facial expressions to control channel attributes
		Args:
			control (pm.nt.Transform): control node
			ctrl_expressions_node (pm.nt.Transform): transform node that holds facial expressions
		'''
		if not isinstance(control, pm.nt.Transform):
			raise ControllerError('{} is not a control transform'.format(control))
		if not isinstance(ctrl_expressions_node, pm.nt.Transform):
			raise ControllerError('{} is not the CTRL_expressions node!'.format(ctrl_expressions_node))
		
		if ctrl_expressions_node.stripNamespace() != 'CTRL_expressions':
			raise ControllerError('{} is not the CTRL_expressions node!'.format(ctrl_expressions_node))
		
		expression_list = ctrl_expressions_node.listAttr(userDefined=True, scalar=True)
		expression_list = [exp.attrName() for exp in expression_list]
		
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
		free_to_change = pm.Attribute.FreeToChangeState.freeToChange
		if self.control.attr('tx').isFreeToChange() == free_to_change and self.control.attr('tx').isKeyable():
			control_limits[self.control.attr('tx')] = [pm.transformLimits(self.control, translationX=True, query=True),
			                                           'tx']
		if self.control.attr('ty').isFreeToChange() == free_to_change and self.control.attr('ty').isKeyable():
			control_limits[self.control.attr('ty')] = [pm.transformLimits(self.control, translationY=True, query=True),
			                                           'ty']
		if control_limits:
			for control_attr, (ctrl_limits, channel_name) in control_limits.items():
				for value in ctrl_limits:
					# Set the control value which will drive the expression
					control_attr.set(value)
					
					# Loop through expressions to determine what is active
					for exp in self._expression_list:
						cur_value = self._ctrl_expressions_node.attr(exp).get()
						if cur_value > 0 or cur_value < 0:
							# The expression name matches the keyframed attribute name from incoming FBX file
							# This will make it easier to connect the keyframe data to a control
							driven_anim_name = 'CTRL_expressions_{}'.format(exp)
							mapping[driven_anim_name] = [self.control.attr(channel_name), value]
				# Reset the control
				control_attr.set(0.0)
				
		for key, (attr, value) in mapping.items():
			if attr not in self._control_mapping:
				self._control_mapping[attr] = []
			self._control_mapping[attr].append([key, value])
			
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
		pm.waitCursor(state=True)
		try:
			result = func(*args, **kwargs)
		finally:
			pm.waitCursor(state=False)
		return result
	return wrapper 

def load_plugin(plugin_name='fbxmaya'):
	'''
	Load the plugin if not already loaded
	Args:
		plugin_name (str): name of plugin
	'''
	loaded_plugins = pm.pluginInfo(listPlugins=True, query=True)
	if plugin_name not in loaded_plugins:
		pm.loadPlugin(plugin_name, quiet=True)

def get_face_controls(namespace=DEFAULT_NAMESPACE):
	'''
	Get a list of metahuman face controls
	Args:
		namespace (str): namespace
	Returns:
		(list of pm.nt.Transforms): list of face controls
	'''
	control_set = 'FacialControls'
	face_control_set = '{}{}'.format(namespace, control_set)
	if pm.objExists(face_control_set):
		pm.select(face_control_set, replace=True)
		controls = pm.selected()
	else:
		# If we're missing the FacialControls set, will look by CTRL_ convention naming
		controls = pm.ls('{}{}'.format(namespace, 'CTRL_*'), type=pm.nt.Transform)
		
	face_controls = []
	# Some controls are shapes so make sure the list is just transforms
	for control in controls:
		if isinstance(control, pm.nt.Transform):
			face_controls.append(control)
		if isinstance(control, pm.nt.Mesh):
			face_controls.append(control.getTransform())
	pm.select(clear=True)
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
		pm.select(controls, replace=True)
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
	selection = pm.selected()
	controls = get_face_controls(namespace)
	if controls:
		result = True
	for control in controls:
		if control.stripNamespace() not in ZERO_OUT_EXCLUDED_CONTROLS:
			control.translateY.set(0.0)
			if not control.translateX.isLocked():
				control.translateX.set(0.0)
	if selection:
		pm.select(selection, replace=True)
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
	if not pm.objExists(expression_node):
		error_msg = 'Unable to find CTRL_expressions! Unable to process!'
		return [], error_msg
	# Zero out controls so we get the proper control mapping
	zero_out_face_controls(namespace)
	controllers = []
	for face_control in face_controls:
		if face_control.stripNamespace() not in EXCLUDED_RETARGET_CONTROLS:
			controller = Controller(face_control, pm.PyNode(expression_node))
			if controller.is_valid():
				controllers.append(controller)
	return controllers, error_msg

def import_fbx_animation(fbx_path):
	'''
	Import fbx animation data
	Args:
		fbx_path (str): absolute path to fbx animation
	Returns:
		(list of pm.nt.DagNode): list of imported nodes
	'''
	# Import animation
	pm.mel.FBXImportShapes(v=False)
	pm.mel.FBXImportSkins(v=False)
	pm.mel.FBXImportMode(v='add')
	pm.mel.FBXImportMergeAnimationLayers(v=False)
	pm.mel.FBXImportProtectDrivenKeys(v=True)
	pm.mel.FBXImportSetMayaFrameRate(v=False)
	
	cur_nodes = pm.ls()
	pm.mel.FBXImport(file=fbx_path, take=1)
	return set(pm.ls()) - set(cur_nodes)

def export_fbx_animation(fbx_path, namespace=DEFAULT_NAMESPACE):
	'''
	Export fbx animation
	Args:
		fbx_path (str): absolute path to fbx animation
		namespace (str): rig namespace
	Returns:
		(list of pm.nt.Transforms): list of exported controls
	'''	
	face_controls = get_face_controls(namespace)
	if not face_controls:
		return []

	start_frame, end_frame = get_key_frame_ranges(face_controls)
	pm.bakeResults(face_controls,
				time=[int(start_frame), int(end_frame)],
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

	pm.select(face_controls, replace=True)
	current_namespace = face_controls[0].namespace()
	controls = []
	# Handle exporting control animation if in namespace
	if current_namespace:
		# Set to root namespace
		pm.Namespace(':').setCurrent()
		for control in face_controls:
			control_name = str(control.stripNamespace())
			dup_control = pm.duplicate(control, returnRootsOnly=True, inputConnections=True)[0]
			new_control = pm.rename(dup_control, control_name)
			controls.append(new_control)
		pm.select(controls, replace=True)
	# Set it back to current namespace
	pm.Namespace(current_namespace).setCurrent()
	pm.mel.FBXResetExport()
	pm.mel.FBXExportAnimationOnly(v=True)
	pm.mel.FBXExportBakeComplexAnimation(v=False)
	pm.mel.FBXExportLights(v=False)
	pm.mel.FBXExportCameras(v=False)
	pm.mel.FBXExportConstraints(v=False)
	pm.mel.FBXExportSkins(v=False)
	pm.mel.FBXExportApplyConstantKeyReducer(v=False)
	pm.mel.FBXExportSmoothMesh(v=False)
	pm.mel.FBXExportShapes(v=False)
	pm.mel.FBXExportEmbeddedTextures(v=False)
	pm.mel.FBXExportInputConnections(v=False)
	pm.mel.FBXExportFileVersion(v='FBX202000')
	pm.mel.FBXExport(file=fbx_path, s=True)
	pm.mel.eval('FBXExport -f "{}" -s'.format(fbx_path))
	if controls:
		pm.delete(controls)
	return face_controls

def get_root_joint(joint_list):
	'''
	Get the root joint from joint list
	Args:
		joint_list (list of pm.nt.Joint): list of joint nodes

	Returns:
		pm.nt.Joint: root joint or None
	'''
	root_joints = [joint for joint in joint_list if joint.getParent() is None]
	if len(root_joints) == 0:
		return None
	return root_joints[0]

def get_key_frame_range(node):
	'''
	Get the min, max range of keyframes for this node
	Args:
		node (pm.nt.DagNode): node with keys

	Returns:
		tuple(float, float): start, end of keyframes
	'''
	return float(pm.findKeyframe(node, which='first')), float(pm.findKeyframe(node, which='last'))

def get_key_frame_ranges(nodes):
	'''
	Get the min, max of start and end frames
	'''	
	start_frames = []
	end_frames = []
	for node in nodes:
		start_frame, end_frame = get_key_frame_range(node)
		start_frames.append(start_frame)
		end_frames.append(end_frame)
	return min(start_frames), max(end_frames)

@show_wait_cursor
def retarget_metahuman_animation_sequence(fbx_path, namespace=DEFAULT_NAMESPACE):
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
	
	new_nodes = import_fbx_animation(fbx_path)

	# 30fps
	pm.currentUnit(time='ntsc')

	# Check if animCurves came in
	anim_curves = pm.ls(new_nodes, type=pm.nt.AnimCurve)
	if not anim_curves:
		error_msg = "No animation curves present!\n\n" \
		            "Ensure the exported animation is from an animation sequence!"
		pm.delete(new_nodes)
		return elapsed_time, error_msg
	
	new_joints = pm.ls(new_nodes, type=pm.nt.Joint)
	root_joint = get_root_joint(new_joints)
	if not root_joint:
		pm.delete(new_nodes)
		error_msg = 'Did not find the root joint from: {}.\n' \
		            'Ensure the exported animation is from an animation sequence!'.format(fbx_path)
		pm.delete(new_nodes)
		return elapsed_time, error_msg
		
	# Get the range of keys
	start_frame, end_frame = get_key_frame_range(root_joint)
	
	# Take the mapping data and copy animation keys over to the proper control.channel
	for controller in controllers:
		for control_attr, expression_data in controller.control_mapping.items():
			for index, (expression, driver_value) in enumerate(expression_data):
				# Incoming anim data is 0-1 but is driven by controls that can
				# move -1 to +1, so we're remapping the data as we go
				if root_joint.hasAttr(expression):
					# Control moves in the negative
					if driver_value == -1.0:
						# Get the anim curve and scale it by -1 
						anim_curve = root_joint.attr(expression).inputs(type=pm.nt.AnimCurve)
						if anim_curve:
							pm.scaleKey(anim_curve[0], valueScale=-1.0)
							copied = pm.copyKey(root_joint.attr(expression))
							if copied:
								try:
									pm.pasteKey(control_attr)
								except RuntimeError:
									logger.error('Failed to paste keys to {}'.format(control_attr))
						else:
							logger.error('No animation curve for {}'.format(root_joint.attr(expression)))
					# Control moves in the positive 
					else:
						copied = pm.copyKey(root_joint.attr(expression))
						if copied:
							try:
								pm.pasteKey(control_attr)
							except RuntimeError:
								logger.error('Failed to paste keys to {}'.format(control_attr))
				else:
					logger.warning('{} does not have {} in the name. This will be skipped!'.format(root_joint, expression))

	# Clean up 	
	pm.delete(new_nodes)

	pm.playbackOptions(animationStartTime=int(start_frame), animationEndTime=int(end_frame))

	delta_time = time.gmtime(time.time() - start_time)
	elapsed_time = str(time.strftime("%H:%M:%S", delta_time))
	logger.info("Transfer completed in: {}".format(elapsed_time))
	return elapsed_time, error_msg


def retarget_metahuman_level_sequence(fbx_path, namespace=DEFAULT_NAMESPACE):
	'''
	This currently is only supported in Maya 2022.4, 2022.5 and 2023.3

	This only supports FBX data exported from a Level Sequence exported from
	the face track in Unreal. The data is hit or miss due to FBX incompatibility issues with Maya.
	It's recommended to use	'retarget_metahuman_animation_sequence' instead for broader compatibility

	References in FBX file and copies the keys from the attributes over to the face controls
	Args:
		fbx_path (str): path to exported FBX file from Unreal
		namespace (str): current namespace
	Returns:
		tuple(str, str): elapsed time to complete, error message
	'''
	start_time = time.time()
	load_plugin()
	
	error_msg = ''
	elapsed_time = ''
	
	supported_versions = [20200400, 20220400, 20220500, 20230300]
	if pymel.versions.current() not in supported_versions:
		error_msg = 'This version (year.cut) of Maya is not currently supported: {}'.format(pymel.versions.current())
		return elapsed_time, error_msg

	# Set to 24 fps
	# Change to 'ntsc' if your Level Sequence is 30fps
	pm.currentUnit(time='film')
	
	nodes = pm.createReference(fbx_path, namespace=':', returnNewNodes=True)
	reference_file = None
	for node in pm.ls(nodes, type=pm.nt.Reference):
		reference_file = node.referenceFile()
		if reference_file:
			break
			
	if not nodes:
		error_msg = '{} is an empty file!'.format(fbx_path)
		if reference_file:
			reference_file.remove()
		return elapsed_time, error_msg
	
	# Check if animCurves came in
	anim_curves = pm.ls(nodes, type=pm.nt.AnimCurve)
	if not anim_curves:
		error_msg = "No animation curves present!\n\n" \
		            "Export Facial animation from Animation Sequence \n" \
		            "Then use 'Import FBX Animation Sequence File'"
		if reference_file:
			reference_file.remove()
		return elapsed_time, error_msg
	
	control_board = None
	for node in pm.ls(nodes):
		if node.stripNamespace() == 'Face_ControlBoard_CtrlRig':
			control_board = node
			break
	if control_board is None:
		error_msg = "Missing Face_ControlBoard_CtrlRig node!\nUnable to import animation!"
		if reference_file:
			reference_file.remove()
		return elapsed_time, error_msg
	
	keyed_attributes = {}
	for keyed_attr in control_board.listAttr(keyable=True):
		attr_name = keyed_attr.attrName()
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
					keyed_attributes[keyed_attr] = result
			else:
				if attr_name not in EXCLUDED_RETARGET_CONTROLS:
					control_name = '{}{}'.format(namespace, attr_name)
					result = (control_name, 'translateY')
					keyed_attributes[keyed_attr] = result
	
	copied_keys = []
	for driver_attr, (control_name, channel) in keyed_attributes.items():
		if pm.objExists(control_name):
			driven_attr = pm.Attribute('{}.{}'.format(control_name, channel))
			if driven_attr.isFreeToChange() == pm.Attribute.FreeToChangeState.freeToChange:
				copied = pm.copyKey(driver_attr)
				if copied:
					try:
						pm.pasteKey(driven_attr)
					except RuntimeError:
						logger.error('Failed to paste keys to {}'.format(driven_attr))
					copied_keys.append(driven_attr)

	if len(copied_keys) == 0:
		error_msg = "Missing animation data. Possible incompatible FBX data."
		if reference_file:
			reference_file.remove()
		return elapsed_time, error_msg
	
	# Cleanup
	for node in pm.ls(nodes, type=pm.nt.Reference):
		reference_file = node.referenceFile()
		if reference_file:
			reference_file.remove()
			break
	
	delta_time = time.gmtime(time.time() - start_time)
	elapsed_time = str(time.strftime("%H:%M:%S", delta_time))
	logger.info("Transfer completed in: {}".format(elapsed_time))
	return elapsed_time, error_msg
