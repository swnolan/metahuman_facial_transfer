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


import logging
import os

from maya.app.general.mayaMixin import MayaQWidgetBaseMixin
import maya.cmds as cmds

try:
	from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
	from PySide2 import QtCore, QtGui, QtWidgets

import metahuman_api as mh_api

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

_ROOT_LABEL = 'Root'

COL_FILE, COL_TAKE, COL_START, COL_END, COL_FRAMES, COL_STATUS = range(6)
TABLE_HEADERS = ['File', 'Take', 'Start', 'End', 'Frames', 'Status']
FILE_PATH_ROLE = QtCore.Qt.UserRole


STYLE = """
QWidget, QDialog {
    background-color: #26272c;
    color: #c9cdd3;
    font-family: "Segoe UI", "Roboto", "Arial";
    font-size: 8pt;
}

QPushButton {
    background-color: #2e2f36;
    color: #c9cdd3;
    border: 1px solid #3a3b42;
    border-radius: 4px;
    padding: 6px 15px;
    min-height: 20px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #4be8ef;
    border: 1px solid #4be8ef;
    color: #000000;
}
QPushButton:pressed {
    background-color: #00a4ab;
    border: 1px solid #00a4ab;
    color: #000000;
}
QPushButton:disabled {
    background-color: #333333;
    color: #777777;
    border-color: #404040;
}

QGroupBox {
    border: 1px solid #00d8e0;
    border-radius: 8px;
    margin-top: 1.8em;
    padding: 12px 8px 8px 8px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: #00d8e0;
    font-weight: bold;
}

QComboBox {
    background-color: #2e2f36;
    color: #c9cdd3;
    border: 1px solid #3a3b42;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 20px;
}
QComboBox:hover {
    border: 1px solid #4be8ef;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #3a3b42;
}
QComboBox::down-arrow {
    image: url(__ARROW_DOWN__);
    width: 10px;
    height: 10px;
}
QComboBox QAbstractItemView {
    background-color: #2e2f36;
    color: #c9cdd3;
    selection-background-color: #00d8e0;
    selection-color: #000000;
    border: 1px solid #3a3b42;
}

QRadioButton {
    spacing: 6px;
    font-weight: bold;
}
QRadioButton::indicator {
    width: 14px;
    height: 14px;
}

QSpinBox {
    background-color: #2e2f36;
    color: #c9cdd3;
    border: 1px solid #3a3b42;
    border-radius: 4px;
    padding: 2px 4px;
    min-height: 26px;
}
QSpinBox:hover {
    border: 1px solid #4be8ef;
}
QSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #3a3b42;
    border-top-right-radius: 4px;
    background-color: #2e2f36;
}
QSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    border-left: 1px solid #3a3b42;
    border-bottom-right-radius: 4px;
    background-color: #2e2f36;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background-color: #4be8ef;
}
QSpinBox::up-arrow {
    image: url(__ARROW_UP__);
    width: 10px;
    height: 10px;
}
QSpinBox::down-arrow {
    image: url(__ARROW_DOWN__);
    width: 10px;
    height: 10px;
}

QTableWidget {
    background-color: #2e2f36;
    color: #c9cdd3;
    gridline-color: #3a3b42;
    border: 1px solid #3a3b42;
    border-radius: 4px;
    selection-background-color: #00a4ab;
    selection-color: #000000;
}
QTableWidget::item {
    padding: 3px;
}
QHeaderView::section {
    background-color: #2e2f36;
    color: #00d8e0;
    border: 1px solid #3a3b42;
    padding: 4px;
    font-weight: bold;
}
"""

_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons').replace('\\', '/')


def _resolved_stylesheet():
	return (STYLE.replace('__ARROW_UP__', '{}/arrow_up.png'.format(_ICON_DIR))
	             .replace('__ARROW_DOWN__', '{}/arrow_down.png'.format(_ICON_DIR)))


def _namespace_to_label(namespace):
	if not namespace or namespace == mh_api.DEFAULT_NAMESPACE:
		return _ROOT_LABEL
	return namespace


def _label_to_namespace(label):
	if label == _ROOT_LABEL:
		return mh_api.DEFAULT_NAMESPACE
	return label


class UI(MayaQWidgetBaseMixin, QtWidgets.QWidget):
	"""	UI Class """
	
	WIN_NAME = "mhFacialTool"
	TITLE = 'Metahuman Facial Tool v2'
	
	def __init__(self, *args, **kwargs):
		super(UI, self).__init__(*args, **kwargs)
		
		if cmds.window(UI.WIN_NAME, query=True, exists=True):
			cmds.deleteUI(UI.WIN_NAME, window=True)
		
		self.setObjectName(UI.WIN_NAME)
		self.setWindowTitle(UI.TITLE)
		self.setWindowFlags(QtCore.Qt.Window)
		self.setMinimumWidth(800)
		fusion_style = QtWidgets.QStyleFactory.create('Fusion')
		if fusion_style:
			self.setStyle(fusion_style)
		self.setStyleSheet(_resolved_stylesheet())

		main_layout = QtWidgets.QVBoxLayout()
		bold_font = QtGui.QFont()
		bold_font.setBold(True)
		bold_font.setPointSize(9)
		
		combo_layout = QtWidgets.QHBoxLayout()
		help_button = QtWidgets.QPushButton('?')
		help_button.setToolTip('Help')
		help_button.setToolTip('Help documentation')
		help_button.setFixedSize(QtCore.QSize(44, 34))
		help_button.setFont(bold_font)
		help_button.clicked.connect(self._help_dialog)

		set_mh_button = QtWidgets.QPushButton('Set Current Metahuman -->')
		set_mh_button.setToolTip('Select any part of your Metahuman and hit the button to set the namespace')
		set_mh_button.setMinimumWidth(300)
		set_mh_button.setFont(bold_font)
		set_mh_button.clicked.connect(self._set_namespace_from_selection)

		self.namespace_combo = QtWidgets.QComboBox()
		self.namespace_combo.setEditable(False)
		self.namespace_combo.setToolTip('Namespace of the Metahuman rig to operate on')
		self.namespace_combo.setMinimumWidth(250)
		self.namespace_combo.setFont(bold_font)
		self.namespace_combo.addItems(self._scan_namespace_labels())

		combo_layout.addWidget(help_button)
		combo_layout.addWidget(set_mh_button)
		combo_layout.addWidget(self.namespace_combo)
		
		import_box = QtWidgets.QGroupBox('Import Facial Animaton')
		import_layout = QtWidgets.QVBoxLayout()

		mode_layout = QtWidgets.QHBoxLayout()
		self.anim_radio = QtWidgets.QRadioButton('Animation Sequence')
		self.anim_radio.setToolTip('FBX exported from Animation Sequence.\n'
		                           'Slower to complete but more compatible between Maya versions.\n'
		                           'Multiple files are merged and laid end to end.')
		self.anim_radio.setChecked(True)
		self.level_radio = QtWidgets.QRadioButton('Level Sequence')
		self.level_radio.setToolTip('FBX exported from Level Sequence.\n'
		                            'Faster to complete but less compatible.\n'
		                            'Multiple files are each imported independently.')
		self.import_mode_group = QtWidgets.QButtonGroup(self)
		self.import_mode_group.addButton(self.anim_radio)
		self.import_mode_group.addButton(self.level_radio)
		self.anim_radio.toggled.connect(self._on_import_mode_changed)
		mode_layout.addWidget(self.anim_radio)
		mode_layout.addWidget(self.level_radio)
		mode_layout.addStretch()

		placement_layout = QtWidgets.QHBoxLayout()
		start_frame_label = QtWidgets.QLabel('Start Frame:')
		self.start_frame_spin = QtWidgets.QSpinBox()
		self.start_frame_spin.setRange(0, 999999)
		self.start_frame_spin.setValue(1)
		self.start_frame_spin.setToolTip('Frame the first clip starts on (Animation Sequence only)')
		self.start_frame_spin.valueChanged.connect(self._reflow_preview)

		gap_label = QtWidgets.QLabel('Gap:')
		self.gap_spin = QtWidgets.QSpinBox()
		self.gap_spin.setRange(0, 999999)
		self.gap_spin.setValue(0)
		self.gap_spin.setToolTip('Extra frames of silence inserted between clips (Animation Sequence only)')
		self.gap_spin.valueChanged.connect(self._reflow_preview)

		take_label = QtWidgets.QLabel('Take:')
		self.take_spin = QtWidgets.QSpinBox()
		self.take_spin.setRange(1, 999)
		self.take_spin.setValue(1)
		self.take_spin.setToolTip('FBX take index to import from every file (Animation Sequence only)')
		self.take_spin.valueChanged.connect(self._refresh_preview)

		fps_label = QtWidgets.QLabel('FPS:')
		self.fps_combo = QtWidgets.QComboBox()
		self.fps_combo.setToolTip('Scene time unit to import/bake under.\n'
		                          'Frame numbers of imported FBX keys depend on this,\n'
		                          'so it must match between preview and the actual import.')
		for unit_name, fps_value in sorted(mh_api.NAMED_FPS.items(), key=lambda pair: pair[1]):
			self.fps_combo.addItem('{} ({:g} fps)'.format(unit_name, fps_value), unit_name)
		default_fps_index = self.fps_combo.findData('ntsc')
		if default_fps_index != -1:
			self.fps_combo.setCurrentIndex(default_fps_index)
		self.fps_combo.currentIndexChanged.connect(self._refresh_preview)

		placement_layout.addWidget(start_frame_label)
		placement_layout.addWidget(self.start_frame_spin)
		placement_layout.addWidget(gap_label)
		placement_layout.addWidget(self.gap_spin)
		placement_layout.addWidget(take_label)
		placement_layout.addWidget(self.take_spin)
		placement_layout.addWidget(fps_label)
		placement_layout.addWidget(self.fps_combo)
		placement_layout.addStretch()

		self.file_table = QtWidgets.QTableWidget(0, len(TABLE_HEADERS))
		self.file_table.setHorizontalHeaderLabels(TABLE_HEADERS)
		self.file_table.setToolTip('FBX files queued for import, in playback order')
		self.file_table.horizontalHeader().setStretchLastSection(True)
		self.file_table.horizontalHeader().setSectionResizeMode(COL_FILE, QtWidgets.QHeaderView.Interactive)
		self.file_table.setColumnWidth(COL_FILE, 320)
		for col in (COL_TAKE, COL_START, COL_END, COL_FRAMES):
			self.file_table.horizontalHeader().setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeToContents)
		self.file_table.verticalHeader().setVisible(False)
		self.file_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
		self.file_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
		self.file_table.setMinimumHeight(160)

		table_button_layout = QtWidgets.QHBoxLayout()
		add_button = QtWidgets.QPushButton('Add...')
		add_button.setToolTip('Add FBX file(s) to the queue')
		add_button.setFont(bold_font)
		add_button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
		add_button.clicked.connect(self._add_files)

		remove_button = QtWidgets.QPushButton('Remove')
		remove_button.setToolTip('Remove the selected row(s) from the queue')
		remove_button.setFont(bold_font)
		remove_button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
		remove_button.clicked.connect(self._remove_selected_rows)

		clear_button = QtWidgets.QPushButton('Clear')
		clear_button.setToolTip('Remove all rows from the queue')
		clear_button.setFont(bold_font)
		clear_button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
		clear_button.clicked.connect(self._clear_table)

		table_button_layout.addWidget(add_button, 1)
		table_button_layout.addWidget(remove_button, 1)
		table_button_layout.addWidget(clear_button, 1)

		import_run_button = QtWidgets.QPushButton('Import Queued FBX Files')
		import_run_button.setToolTip('Runs the transfer for every file in the queue,\n'
		                             'using whichever import type is selected above')
		import_run_button.setFont(bold_font)
		import_run_button.clicked.connect(self._run_import)

		import_layout.addLayout(mode_layout)
		import_layout.addLayout(placement_layout)
		import_layout.addWidget(self.file_table)
		import_layout.addLayout(table_button_layout)
		import_layout.addWidget(import_run_button)

		self._on_import_mode_changed()

		export_box = QtWidgets.QGroupBox('Export Facial Animation')
		export_layout = QtWidgets.QVBoxLayout()
		export_button = QtWidgets.QPushButton('Export Facial FBX')
		export_button.setToolTip('Export face control animation')
		export_button.setFont(bold_font)
		export_button.clicked.connect(self.export_fbx)
		export_box.setLayout(export_layout)
		export_layout.addWidget(export_button)

		control_box = QtWidgets.QGroupBox('Controls')
		controls_layout = QtWidgets.QVBoxLayout()
		reset_button = QtWidgets.QPushButton('Reset Facial Controls')
		reset_button.setToolTip('Restores face controls to default position')
		reset_button.setFont(bold_font)
		reset_button.clicked.connect(self.zero_out_face_controls)

		select_button = QtWidgets.QPushButton('Select Facial Controls')
		select_button.setToolTip('Selects face controls for keying')
		select_button.setFont(bold_font)
		select_button.clicked.connect(self.select_face_controls)
		controls_layout.addWidget(reset_button)
		controls_layout.addWidget(select_button)
		control_box.setLayout(controls_layout)

		close_button = QtWidgets.QPushButton('Close')
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
		file_path = cmds.fileDialog2(fileFilter='(*.fbx)', dialogStyle=1, caption='Export FBX Animation')
		if file_path:
			results = mh_api.export_fbx_animation(file_path[0], self._get_current_namespace())
			if results:
				msg_box = QtWidgets.QMessageBox()
				msg_box.setWindowTitle("Export Completed")
				msg_box.setText('Export Completed!')
				msg_box.setIcon(QtWidgets.QMessageBox.Information)
				msg_box.exec()

	def _scan_namespace_labels(self):
		return [_ROOT_LABEL] + mh_api.get_scene_namespaces()

	def _get_current_namespace(self):
		return _label_to_namespace(self.namespace_combo.currentText())

	def _set_namespace_from_selection(self):
		selected = cmds.ls(selection=True, long=True) or []
		if not selected:
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle("Metahuman: Selection Error")
			msg_box.setText("Missing selection!\nSelect any thing on your Metahuman\nClick 'Set Current Metahuman'")
			msg_box.setIcon(QtWidgets.QMessageBox.Critical)
			msg_box.exec()
			return
		namespace = mh_api.get_namespace(selected[0])
		label = _namespace_to_label(namespace)
		index = self.namespace_combo.findText(label)
		if index == -1:
			self.namespace_combo.addItem(label)
			index = self.namespace_combo.findText(label)
		self.namespace_combo.setCurrentIndex(index)
		mh_api.set_current_namespace(namespace)

	def _on_import_mode_changed(self):
		anim_mode = self.anim_radio.isChecked()
		self.start_frame_spin.setEnabled(anim_mode)
		self.gap_spin.setEnabled(anim_mode)
		self.take_spin.setEnabled(anim_mode)
		self._refresh_preview()

	def _current_timeunit(self):
		return self.fps_combo.currentData()

	def _table_paths(self):
		paths = []
		for row in range(self.file_table.rowCount()):
			item = self.file_table.item(row, COL_FILE)
			if item:
				paths.append(item.data(FILE_PATH_ROLE))
		return paths

	def _set_row_cell(self, row, col, text):
		item = QtWidgets.QTableWidgetItem(text)
		item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
		self.file_table.setItem(row, col, item)

	def _add_files(self):
		file_paths = cmds.fileDialog2(fileFilter='FBX (*.fbx)', fileMode=4,
		                              caption='Add FBX File(s)')
		if not file_paths:
			return
		for file_path in file_paths:
			row = self.file_table.rowCount()
			self.file_table.insertRow(row)
			file_item = QtWidgets.QTableWidgetItem(os.path.basename(file_path))
			file_item.setFlags(file_item.flags() & ~QtCore.Qt.ItemIsEditable)
			file_item.setToolTip(file_path)
			file_item.setData(FILE_PATH_ROLE, file_path)
			self.file_table.setItem(row, COL_FILE, file_item)
			for col in (COL_TAKE, COL_START, COL_END, COL_FRAMES, COL_STATUS):
				self._set_row_cell(row, col, '')
		self._refresh_preview()

	def _remove_selected_rows(self):
		rows = sorted({index.row() for index in self.file_table.selectedIndexes()}, reverse=True)
		for row in rows:
			self.file_table.removeRow(row)
		self._reflow_preview()

	def _clear_table(self):
		self.file_table.setRowCount(0)

	def _reflow_preview(self):
		if not hasattr(self, 'file_table') or not self.anim_radio.isChecked():
			return
		cursor = float(self.start_frame_spin.value())
		gap = float(self.gap_spin.value())
		for row in range(self.file_table.rowCount()):
			frames_item = self.file_table.item(row, COL_FRAMES)
			frame_count_text = frames_item.text() if frames_item else ''
			if not frame_count_text.isdigit():
				self._set_row_cell(row, COL_START, '')
				self._set_row_cell(row, COL_END, '')
				continue
			frame_count = int(frame_count_text)
			start = cursor
			end = cursor + frame_count - 1
			self._set_row_cell(row, COL_START, str(int(start)))
			self._set_row_cell(row, COL_END, str(int(end)))
			cursor = end + 1.0 + gap

	def _refresh_preview(self):
		if not hasattr(self, 'file_table'):
			return
		row_count = self.file_table.rowCount()
		if row_count == 0:
			return

		if not self.anim_radio.isChecked():
			# Level Sequence rows batch-run independently -- no placement preview
			for row in range(row_count):
				for col in (COL_TAKE, COL_START, COL_END, COL_FRAMES):
					self._set_row_cell(row, col, '—')
				self._set_row_cell(row, COL_STATUS, '')
			return

		try:
			plan_rows = mh_api.plan_sequence(self._table_paths(),
			                                 start_frame=self.start_frame_spin.value(),
			                                 gap=self.gap_spin.value(),
			                                 take=self.take_spin.value(),
			                                 timeunit=self._current_timeunit())
		except Exception as exc:
			logger.error('Failed to preview sequence: %s', exc)
			return

		for row, plan_row in enumerate(plan_rows):
			if plan_row['error']:
				self._set_row_cell(row, COL_TAKE, '')
				self._set_row_cell(row, COL_START, '')
				self._set_row_cell(row, COL_END, '')
				self._set_row_cell(row, COL_FRAMES, '')
				self._set_row_cell(row, COL_STATUS, plan_row['error'])
			else:
				self._set_row_cell(row, COL_TAKE, str(plan_row['take']))
				self._set_row_cell(row, COL_START, str(int(plan_row['start'])))
				self._set_row_cell(row, COL_END, str(int(plan_row['end'])))
				self._set_row_cell(row, COL_FRAMES, str(plan_row['frame_count']))
				self._set_row_cell(row, COL_STATUS, '')

	def _run_import(self):
		''' Run the transfer for every FBX file in the queue, using the selected import mode '''
		namespace = self._get_current_namespace()
		controls = mh_api.get_face_controls(namespace)
		bold_font = QtGui.QFont()
		bold_font.setBold(True)
		if not controls:
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle("Metahuman: Missing Controls")
			msg_box.setText("Missing Metahuman facial controls!\nUnable to import animation!")
			msg_box.setIcon(QtWidgets.QMessageBox.Critical)
			msg_box.setFont(bold_font)
			msg_box.exec()
			return

		paths = self._table_paths()
		if not paths:
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle("Metahuman: Empty Queue")
			msg_box.setText("Add at least one FBX file to the queue!")
			msg_box.setIcon(QtWidgets.QMessageBox.Warning)
			msg_box.setFont(bold_font)
			msg_box.exec()
			return

		if self.anim_radio.isChecked():
			elapsed_time, errors, placements = mh_api.retarget_metahuman_animation_sequences(
				paths, namespace, timeunit=self._current_timeunit(),
				start_frame=self.start_frame_spin.value(),
				gap=self.gap_spin.value(), take=self.take_spin.value())
			merged_paths = {placement['path'] for placement in placements}
			for row, path in enumerate(paths):
				self._set_row_cell(row, COL_STATUS, 'Merged' if path in merged_paths else 'Skipped')
			if errors:
				title, message, icon = "Transfer Failed!", errors, QtWidgets.QMessageBox.Critical
			else:
				title = "Transfer Complete!"
				message = "Animation Transferred in: {}".format(elapsed_time)
				icon = QtWidgets.QMessageBox.Information
		else:
			results = mh_api.retarget_metahuman_level_sequences(paths, namespace,
			                                                    timeunit=self._current_timeunit())
			for row, result in enumerate(results):
				self._set_row_cell(row, COL_STATUS, result['error'] if result['error'] else 'Imported')
			failures = [result for result in results if result['error']]
			if len(failures) == len(results):
				title = "Transfer Failed!"
				message = failures[0]['error']
				icon = QtWidgets.QMessageBox.Critical
			elif failures:
				title = "Transfer Completed with Errors"
				message = "{} of {} file(s) failed. See Status column.".format(len(failures), len(results))
				icon = QtWidgets.QMessageBox.Warning
			else:
				title = "Transfer Complete!"
				message = "{} file(s) imported.".format(len(results))
				icon = QtWidgets.QMessageBox.Information

		msg_box = QtWidgets.QMessageBox()
		msg_box.setWindowTitle(title)
		msg_box.setText(message)
		msg_box.setIcon(icon)
		msg_box.setFont(bold_font)
		msg_box.exec()


	def select_face_controls(self):
		'''	Select face controls '''
		result = mh_api.select_face_controls(self._get_current_namespace())
		if not result:
			bold_font = QtGui.QFont()
			bold_font.setBold(True)
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle("Operation Failed")
			msg_box.setText('Missing Face Controls for this namespace!')
			msg_box.setIcon(QtWidgets.QMessageBox.Critical)
			msg_box.setFont(bold_font)
			msg_box.exec()
			
	def zero_out_face_controls(self):
		'''	Zero out face controls '''
		result = mh_api.zero_out_face_controls(self._get_current_namespace())
		if not result:
			bold_font = QtGui.QFont()
			bold_font.setBold(True)
			msg_box = QtWidgets.QMessageBox()
			msg_box.setWindowTitle("Operation Failed")
			msg_box.setText('Missing Face Controls for this namespace!')
			msg_box.setIcon(QtWidgets.QMessageBox.Critical)
			msg_box.setFont(bold_font)
			msg_box.exec()


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
    * Click the 'Set Current Metahuman' and the namespace field
      will update to match
    * Choose Animation Sequence or Level Sequence with the radio buttons
    * Animation Sequence:
       + Most compatible but slower to process
       + 'Add...' queues one or more FBX files into the table
       + Set 'Start Frame', 'Gap' and 'Take' -- the table's Start/End/
         Frames columns preview where each clip will land before you
         run anything
       + All queued files are merged and laid end to end in one pass
    * Level Sequence:
      + Least compatible but faster to apply
      + Each queued file is imported independently at its own frame
        range -- there is no end-to-end placement for this mode
    * 'Remove' drops the selected row(s); 'Clear' empties the table
    * 'Import Queued FBX Files' runs the transfer for every row using
      whichever mode is selected; per-file results appear in the
      table's Status column

Exporting FBX data:
    * Select anything on your Metahuman character
    * Click the 'Set Current Metahuman' and the namespace field
      will update to match
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
