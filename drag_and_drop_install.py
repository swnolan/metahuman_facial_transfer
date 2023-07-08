import os
import pymel.core as pm
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
			   button=['Continue','Cancel'], 
			   defaultButton='Continue', 
			   cancelButton='Cancel', 
			   dismissString='Cancel')
	if result == 'Continue':
		# Copy files and load shelf
		shutil.copy(api_file,scripts_folder)
		shutil.copy(mh_file,scripts_folder)
		shutil.copy(mel_file,shelf_dir)
		mm.eval('loadNewShelf("{}")'.format(shelf_file))
		pm.confirmDialog(title='Installed', message='Installed!\nClick on new shelf button to launch tool.', button=['Okay'], defaultButton='Okay')
	

