import os

try:
	import pymel.core as pm
except:
	raise ImportError("Must have PyMEL installed. Update your Maya installation to include this.")
import maya.mel as mm
import shutil
import sys

sys.dont_write_bytecode = True


def onMayaDroppedPythonFile(*args):
	"""
	Drag and drop install tool
	"""
	cur_path = os.path.dirname(__file__)
	api_file = os.path.join(cur_path, 'metahuman_api.py')
	mh_file = os.path.join(cur_path, 'metahuman_facial_transfer.py')
	mel_file = os.path.join(cur_path, 'shelf_Metahuman.mel')
	
	scripts_folder = pm.internalVar(userScriptDir=True)
	shelf_dir = pm.internalVar(userShelfDir=True)
	shelf_file = os.path.join(shelf_dir, 'shelf_Metahuman.mel').replace('\\', '/')
	result = pm.confirmDialog(title='Install Metahuman Transfer Tool',
	                          message='Installing Tool to:\n{}\n\nContinue?'.format(scripts_folder),
	                          button=['Continue', 'Cancel'],
	                          defaultButton='Continue',
	                          cancelButton='Cancel',
	                          dismissString='Cancel')
	if result == 'Continue':
		# Copy files and load shelf
		updated = False
		if os.path.exists(os.path.join(scripts_folder, 'metahuman_api.py')) or \
			os.path.exists(os.path.join(scripts_folder, 'metahuman_facial_transfer.py')) or \
			os.path.exists(os.path.join(shelf_dir, 'shelf_Metahuman.mel')):
			updated = True
		
		shutil.copy(api_file, scripts_folder)
		shutil.copy(mh_file, scripts_folder)
		shutil.copy(mel_file, shelf_dir)
		# Load shelf if doesn't exist
		if not pm.shelfLayout('Metahuman', query=True, exists=True):
			mm.eval('loadNewShelf("{}")'.format(shelf_file))
		if not updated:
			pm.confirmDialog(title='Installed', message='Installed!\nClick on new shelf button to launch tool.',
			                 button=['Okay'], defaultButton='Okay')
		else:
			pm.confirmDialog(title='Install Updated', message='Files Update!\t\t\t\nRestart Maya!',
			                 button=['Okay'], defaultButton='Okay')
