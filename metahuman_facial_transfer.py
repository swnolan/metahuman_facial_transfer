# Metahuman Facial Animation Transfer
#
# Purpose: Import and transfer FBX facial animation from Unreal Metahuman face rig to Maya Metahuman face rig
#
# Unreal Instructions:
#	* Open Metahuman Sample Level Sequence or existing Level Seq with a Metahuman Face Track
#	* Right-Click on Face Track and 'Bake Animation Sequence' in Level Sequence
#	* Save your Baked Animation Seq to a folder
# 	* Right-Click on your New Animation Sequence
#	* Choose Asset Actions -> Export
# 	* Export Settings:
#		- FBX Export Compatibility: 2020
#		- Export Morph Targets: True
#		- Export Preview Mesh: True
# 		- Map Skeleton Motion to Root: True
#		- Export Local Time: True
#	* Leaving other options on will only increase file size
#
# Installation/Usage:
#   * Use drag_and_drop_install.py and drop file into Maya viewport
#   * Import, Reference or Open your Metahuman Maya file that has the face control board in the scene
#   * Open up the Maya script editor (Python) 	
# 	* Select anything on your Metahuman and click 'Set Current Metahuman'
#   * Import FBX Animation Sequence (coming from Animation Sequence file)
#       * This import type is most compatible
#       * The Level Sequence version works as well but only certain years/cuts of Maya support it
#   * Export Facial FBX
#       * Save out FBX File
#       * Open up Unreal and right+click on 'Face_ControlBoard_CtrlRig' track and import FBX in your level sequence


import os
import logging
from functools import partial
try:
	# Maya <= 2025
	from PySide6 import QtWidgets
	from PySide6 import QtCore
	from PySide6 import QtGui
except ImportError:
	# Maya >= 2025
	from PySide2 import QtWidgets
	from PySide2 import QtCore
	from PySide2 import QtGui

from maya.app.general.mayaMixin import MayaQWidgetBaseMixin

try:
	import pymel.core as pm
except:
	raise ImportError("Must have PyMEL installed. Update your Maya installation to include this.")

import metahuman_api as mh_api

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class UI(MayaQWidgetBaseMixin, QtWidgets.QWidget):
	"""	UI Class """
	
	WIN_NAME = "mhFacialTool"
	TITLE = 'Metahuman Facial Tool'
	
	def __init__(self, *args, **kwargs):
		super(UI, self).__init__(*args, **kwargs)
		
		if pm.window(UI.WIN_NAME, query=True, exists=True):
			pm.deleteUI(UI.WIN_NAME, window=True)
		
		self._current_namespace = ''
		self._current_mh_name = None
		
		self.setObjectName(UI.WIN_NAME)
		self.setWindowTitle(UI.TITLE)
		self.setWindowFlags(QtCore.Qt.Window)
		
		btn_styles = ("QPushButton{background-color: "
		             "rgb(50, 50, 50); color: orange; solid black 1px:}"
		             "QPushButton:hover{background-color: "
		             "rgb(25, 25, 25); color: orange; solid black 1px:}")
		
		line_styles = ("QLineEdit{background-color: "
		               "rgb(50, 50, 50); color: orange; solid black 1px:}")
		
		qbox_style = QtWidgets.QStyleFactory.create('Windows')
		
		main_layout = QtWidgets.QVBoxLayout()
		bold_font = QtGui.QFont()
		bold_font.setBold(True)
		bold_font.setPointSize(9)
		
		combo_layout = QtWidgets.QHBoxLayout()
		help_button = QtWidgets.QPushButton('?')
		help_button.setToolTip('Help')
		help_button.setToolTip('Help documentation')
		help_button.setFixedSize(QtCore.QSize(34, 34))
		help_button.setStyleSheet(btn_styles)
		help_button.setFont(bold_font)
		help_button.clicked.connect(self._help_dialog)
		
		set_mh_button = QtWidgets.QPushButton('Set Current Metahuman -->')
		set_mh_button.setToolTip('Select any part of your Metahuman and hit the button to set current Metahuman')
		set_mh_button.setMinimumWidth(300)
		set_mh_button.setStyleSheet(btn_styles)
		set_mh_button.setFont(bold_font)
		set_mh_button.clicked.connect(self._set_metahuman_name)
		
		self.mh_name = QtWidgets.QLineEdit()
		self.mh_name.setReadOnly(True)
		self.mh_name.setFocusPolicy(QtCore.Qt.NoFocus)
		self.mh_name.setPlaceholderText('<No Metahuman Set>')
		self.mh_name.setToolTip('Select any part of your Metahuman and hit the button to set current Metahuman')
		self.mh_name.setMinimumWidth(250)
		self.mh_name.setFont(bold_font)
		self.mh_name.setAlignment(QtCore.Qt.AlignCenter)
		self.mh_name.setStyleSheet(line_styles)
		
		combo_layout.addWidget(help_button)
		combo_layout.addWidget(set_mh_button)
		combo_layout.addWidget(self.mh_name)
		
		import_box = QtWidgets.QGroupBox('Import Facial Animaton')
		import_box.setStyle(qbox_style)
		import_layout = QtWidgets.QVBoxLayout()
		
		import_anim_button = QtWidgets.QPushButton('Import FBX Animation Sequence File...')
		import_anim_button.setToolTip('Navigate to FBX exported from Animation Sequence.\n'
		                              'Slower to complete but more compatible between Maya versions')
		import_anim_button.setStyleSheet(btn_styles)
		import_anim_button.setFont(bold_font)
		import_anim_button.clicked.connect(partial(self.import_metahuman_animation, 'anim'))

		import_level_button = QtWidgets.QPushButton('Import FBX Level Sequence File...')
		import_level_button.setToolTip('Navigate to FBX exported from Level Sequence.\n'
		                               'Faster to complete')
		import_level_button.setStyleSheet(btn_styles)
		import_level_button.setFont(bold_font)
		import_level_button.clicked.connect(partial(self.import_metahuman_animation, 'level'))
		
		import_layout.addWidget(import_anim_button)
		import_layout.addWidget(import_level_button)

		export_box = QtWidgets.QGroupBox('Export Facial Animation')
		export_box.setStyle(qbox_style)
		export_layout = QtWidgets.QVBoxLayout()
		export_button = QtWidgets.QPushButton('Export Facial FBX')
		export_button.setToolTip('Export face control animation')
		export_button.setStyleSheet(btn_styles)
		export_button.setFont(bold_font)
		export_button.clicked.connect(self.export_fbx)
		export_box.setLayout(export_layout)
		export_layout.addWidget(export_button)

		control_box = QtWidgets.QGroupBox('Controls')
		control_box.setStyle(qbox_style)
		controls_layout = QtWidgets.QVBoxLayout()
		reset_button = QtWidgets.QPushButton('Reset Facial Controls')
		reset_button.setToolTip('Restores face controls to default position')
		reset_button.setFont(bold_font)
		reset_button.setStyleSheet(btn_styles)
		reset_button.clicked.connect(self.zero_out_face_controls)
		
		select_button = QtWidgets.QPushButton('Select Facial Controls')
		select_button.setToolTip('Selects face controls for keying')
		select_button.setStyleSheet(btn_styles)
		select_button.setFont(bold_font)
		select_button.clicked.connect(self.select_face_controls)
		controls_layout.addWidget(reset_button)
		controls_layout.addWidget(select_button)
		control_box.setLayout(controls_layout)

		close_button = QtWidgets.QPushButton('Close')
		close_button.setStyleSheet(btn_styles)
		close_button.setFont(bold_font)
		close_button.clicked.connect(self.close)
		
		import_box.setLayout(import_layout)
		main_layout.addLayout(combo_layout)
		main_layout.addWidget(import_box)
		main_layout.addWidget(export_box)
		main_layout.addWidget(control_box)
		main_layout.addWidget(close_button)
		main_layout.addStretch()
		self.setLayout(main_layout)
		
		self.show()
	
	def _help_dialog(self):
		''' Help Dialog '''
		dialog = HelpDialog(self)
		dialog.show()
		
	def closeEvent(self, event):
		event.accept()
	
	def export_fbx(self):
		''' Export FBX Animation '''
		if self._current_mh_name is None:
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle("Metahuman: Selection Error")
			msg_box.setText("Missing selection!\nSelect any thing on your Metahuman\nClick 'Set Current Metahuman'")
			msg_box.setIcon(QtWidgets.QMessageBox.Critical)
			msg_box.exec_()
			return
				
		file_path = pm.fileDialog2(fileFilter='(*.fbx)', dialogStyle=1, caption='Export FBX Animation')
		if file_path:
			# Strip namespace before export and then restore

			results = mh_api.export_fbx_animation(file_path[0], self._current_namespace)
			if results:
				msg_box = QtWidgets.QMessageBox()
				msg_box.setWindowTitle("Export Completed")
				msg_box.setText('Export Completed!')
				msg_box.setIcon(QtWidgets.QMessageBox.Information)
				msg_box.exec_()

	def _set_metahuman_name(self):
		''' Set the Metahuman name and current namespace '''
		selected = pm.selected()
		if not selected:
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle("Metahuman: Selection Error")
			msg_box.setText("Missing selection!\nSelect any thing on your Metahuman\nClick 'Set Current Metahuman'")
			msg_box.setIcon(QtWidgets.QMessageBox.Critical)
			msg_box.exec_()
			return
		current_namespace = pm.Namespace(selected[0].namespace())
		nodes = current_namespace.ls()
		embedded_node = pm.ls(nodes, type=pm.nt.EmbeddedNodeRL4)
		if not embedded_node:
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle("Metahuman: Missing node")
			msg_box.setText("Missing critical node, embeddedNodeRL4, used for rig logic!")
			msg_box.setIcon(QtWidgets.QMessageBox.Critical)
			msg_box.exec_()
			return
		embedded_node = embedded_node[0]
		file_path = embedded_node.dnaFilePath.get()
		file_name = os.path.basename(file_path).split('_rl.dna')
		self._current_mh_name = file_name[0]
		self.mh_name.setText(self._current_mh_name)
		self._current_namespace = embedded_node.namespace()
		pm.Namespace(embedded_node.namespace()).setCurrent()
	
	def import_metahuman_animation(self, transfer_type):
		'''
		Opens up a file dialog to bring in metahuman fbx data
		Args:
			transfer_type (str): 'anim' or 'level' for animation data
		'''
		if self._current_mh_name is None:
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle("Metahuman: Selection Error")
			msg_box.setText("Missing selection!\nSelect any thing on your Metahuman\nClick 'Set Current Metahuman'")
			msg_box.setIcon(QtWidgets.QMessageBox.Critical)
			msg_box.exec_()
			return
		controls = mh_api.get_face_controls(self._current_namespace)
		bold_font = QtGui.QFont()
		bold_font.setBold(True)
		if not controls:
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle("Metahuman: Missing Controls")
			msg_box.setText("Missing Metahuman facial controls!\nUnable to import animation!")
			msg_box.setIcon(QtWidgets.QMessageBox.Critical)
			msg_box.setFont(bold_font)
			msg_box.exec_()
			return
		
		file_path = pm.fileDialog2(fileFilter='(FBX (*.fbx)',
		                           fileMode=1,
		                           caption='(FBX) Exported Metahuman facial data')
		if file_path:
			if transfer_type == 'anim':
				elapsed_time, errors = mh_api.retarget_metahuman_animation_sequence(file_path[0],
				                                                                    self._current_namespace)
			else:
				elapsed_time, errors = mh_api.retarget_metahuman_level_sequence(file_path[0],
				                                                                self._current_namespace)
			
			if errors:
				title = "Transfer Failed!"
				message = errors
				icon = QtWidgets.QMessageBox.Critical
			else:
				title = "Transfer Complete!"
				message = "Animation Transferred in: {}".format(elapsed_time)
				icon = QtWidgets.QMessageBox.Information
			
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle(title)
			msg_box.setText(message)
			msg_box.setIcon(icon)
			msg_box.setFont(bold_font)
			msg_box.exec_()
			
	def select_face_controls(self):
		'''	Select face controls '''
		if self._current_mh_name is None:
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle("Metahuman: Selection Error")
			msg_box.setText("Missing selection!\nSelect any thing on your Metahuman\nClick 'Set Current Metahuman'")
			msg_box.setIcon(QtWidgets.QMessageBox.Critical)
			msg_box.exec_()
			return
		result = mh_api.select_face_controls(self._current_namespace)
		if not result:
			bold_font = QtGui.QFont()
			bold_font.setBold(True)
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle("Operation Failed")
			msg_box.setText('Missing Face Controls or Metahuman not Set!\nMake sure your Metahuman is set!')
			msg_box.setIcon(QtWidgets.QMessageBox.Critical)
			msg_box.setFont(bold_font)
			msg_box.exec_()
			
	def zero_out_face_controls(self):
		'''	Zero out face controls '''
		if self._current_mh_name is None:
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle("Metahuman: Selection Error")
			msg_box.setText("Missing selection!\nSelect any thing on your Metahuman\nClick 'Set Current Metahuman'")
			msg_box.setIcon(QtWidgets.QMessageBox.Critical)
			msg_box.exec_()
			return
		result = mh_api.zero_out_face_controls(self._current_namespace)
		if not result:
			bold_font = QtGui.QFont()
			bold_font.setBold(True)
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle("Operation Failed")
			msg_box.setText('Missing Face Controls or Metahuman not Set!\nMake sure your Metahuman is set!')
			msg_box.setIcon(QtWidgets.QMessageBox.Critical)
			msg_box.setFont(bold_font)
			msg_box.exec_()


class HelpDialog(QtWidgets.QDialog):
	def __init__(self, parent=None):
		super(HelpDialog, self).__init__(parent)
		self.setWindowTitle("Metahuman Facial Help")
		info = '''
Metahuman Facial Tool provides a few functions to aid in bring animation
onto your Metahuman face rigs coming from either an exported Animation
Sequence (more reliable but slower) or from a Level Sequence (faster but
less reliable). Both have the same results. The one from the Level Seq
can sometimes not work depending on Maya year and cut due to FBX
incompatibility.

Unreal Exporting Instructions:
    * Open Metahuman Sample Project or your project with an
      animated Metahuman face
    * Open the Level Sequence
    * Find your 'Face' Track
    * For 'Import FBX Animation Sequence File'
      + Right-Click on Face Track and 'Bake Animation Sequence'
      + Pick a folder and save the file
      + Right-Click on your new Animation Sequence
      + Choose 'Asset Actions -> Export'
      * Export Settings:
        - FBX Export Compatibility: 2020
        - Export Morph Targets: True
        - Export Preview Mesh: True
        - Map Skeleton Motion to Root: True
        - Export Local Time: True

    * For 'Import FBX Level Sequence File'
      + Right-Click on Face Track and 'Bake To Control Rig'
      + Choose 'Face_ControlBoard_CtrlRig'
      + Use Default settings -> Create
      + Right-Click on Face Track -> 'Export'
      + Export Settings:
        - FBX Export Compatibility: 2020
        - Export Morph Targets: True
        - Export Preview Mesh: True
        - Map Skeleton Motion to Root: True
        - Export Local Time: True

Importing FBX data:
    * First, select anything on your Metahuman character
    * Click the 'Set Current Metahuman' and your character name
      will appear in the field
    * Choose which Import type to bring in
    * Animation Sequence: 
       + This is the most compatible but will take longer to process
    * Level Sequence:
      + Least compatible but is faster to apply

Exporting FBX data:
    * Select anything on your Metahuman character
    * Click the 'Set Current Metahuman' and your character name
      will appear in the field
    * Navigate to a folder and name export file
    * In Unreal:
      + Open Level Sequence
      + Right-Click 'Face_ControlBoard_CtrlRig' track
      + 'Import Control Rig FBX'
      + Set Control Mapping to 'Metahuman Control Mapping'

Controls:
    * Reset Facial Controls
      + Will reset all the controls to a default position
    * Select Facial Controls
      + Will select all the controls
		'''
		bold_font = QtGui.QFont()
		bold_font.setBold(True)
		layout = QtWidgets.QVBoxLayout()
		self.setLayout(layout)
		
		scroll_area = QtWidgets.QScrollArea()
		scroll_area.setWidgetResizable(True)
		layout.addWidget(scroll_area)
		
		container = QtWidgets.QWidget()
		container_layout = QtWidgets.QVBoxLayout()
		container.setLayout(container_layout)
		scroll_area.setWidget(container)
		
		text_edit = QtWidgets.QPlainTextEdit(info)
		text_edit.setReadOnly(True)
		text_edit.setFont(bold_font)
		container_layout.addWidget(text_edit)
		
		button = QtWidgets.QPushButton("Close")
		button.clicked.connect(self.close)
		container_layout.addWidget(button)
		self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
		self.setMinimumSize(675, 800)
