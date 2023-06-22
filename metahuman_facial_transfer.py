# Metahuman Facial Animation Transfer
# Import and transfer FBX facial animation from Metahuman face control board exported from Unreal
#
# Installation/Usage:
#   * Place script anywhere in your MAYA_PYTHON_PATH or in Documents/maya/2020+/scripts folder
#   * Import, Reference or Open your Metahuman Maya file that has the face control board in the scene
#   * Open up the Maya script editor (Python)
#   * Select a control on the face rig and run code:
#
#   import metahuman_facial_transfer
#   metahuman_facial_transfer.import_metahuman_animation()
#


import pymel.core as pm
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def import_metahuman_animation():
	'''	Opens up a file dialog to bring in metahuman fbx data

	Notes:
		Select a face control on the Metahuman Face control board
		Navigate to the export FBX animation from Unreal
	'''
	selection = pm.selected()
	if not selection:
		pm.confirmDialog(title='Selection Error',
		                 message='Nothing selected! Select a control of the face control board!',
		                 icon='critical',
		                 button=['Ok'])
		return
	file_path = pm.fileDialog2(fileFilter='(FBX (*.fbx)',
	                           fileMode=1,
	                           caption='(FBX) Exported Metahuman facial data')
	if file_path:
		transfer_metahuman_animation_data(file_path[0], selection[0].namespace())
	
		pm.confirmDialog(title='Transfer Complete',
		                 message='Animation Transferred!',
		                 icon='information',
		                 button=['Ok'])
	
		
def transfer_metahuman_animation_data(fbx_path, current_namespace=None):
	'''
	References in FBX file and copies the keys from the attributes over to the face controls
	Args:
		fbx_path (str): path to exported FBX file from Unreal
		current_namespace (str): current namespace
	'''
	nodes = pm.createReference(fbx_path, namespace=':', returnNewNodes=True)
	if not nodes:
		raise RuntimeError('{} is an empty file!'.format(fbx_path))
	
	control_board = None
	for node in pm.ls(nodes):
		if node.nodeName() == 'Face_ControlBoard_CtrlRig':
			control_board = node
			break
	if not control_board:
		raise ValueError("Missing Face_ControlBoard_CtrlRig node. Unable to import animation!")
	
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
				if current_namespace:
					control_name = '{}{}'.format(current_namespace, control_name)
				result = (control_name, driven_channel)
			else:
				if current_namespace:
					control_name = '{}{}'.format(current_namespace,attr_name)
				else:
					control_name = attr_name
				result = (control_name, 'translateY')
			keyed_attributes[keyed_attr] = result
	
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
	
	# Cleanup
	for node in pm.ls(nodes, type=pm.nt.Reference):
		reference_file = node.referenceFile()
		if reference_file:
			reference_file.remove()
			break
