import logging

import ctk
import qt
import slicer
import vtk
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic,
)
from slicer.util import VTKObservationMixin


class SlicerHemorrhageTools(ScriptedLoadableModule):
    """One-click helpers for HU-constrained hemorrhage segmentation cleanup."""

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Hemorrhage Tools"
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = ["SegmentEditor"]
        self.parent.contributors = ["Anjan Ballekere"]
        self.parent.helpText = (
            "One-click tools for HU-constrained hemorrhage and edema cleanup "
            "in 3D Slicer's Segment Editor."
        )
        self.parent.acknowledgementText = "Developed for rapid manual CT segmentation cleanup workflows."


class SlicerHemorrhageToolsWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    DEFAULT_SHORTCUTS = {
        "Brush Smaller": "[",
        "Brush Larger": "]",
        "Paint Range 1 (High)": "1",
        "Erase Range 2 (Low)": "2",
        "Paint Range 2 (Low)": "3",
        "Erase Range 1 (High)": "4",
        "Toggle Segmentation Visibility": "v",
        "Toggle Editable Intensity Mask": "m",
        "Dilate Active Segment": "d",
        "Erode Active Segment": "e",
        "Switch to Segment Editor": "Alt+1",
        "Switch to Hemorrhage Tools": "Alt+2",
        "Switch to Hemorrhage Morphology": "Alt+3",
        "Save & Load Next": "Alt+n",
        "Refresh Segment Volumes": "r",
        "Deactivate Active Effect": "Escape",
    }

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        VTKObservationMixin.__init__(self)
        self.logic = SlicerHemorrhageToolsLogic()
        self.shortcuts = {}
        self.observedSegmentEditorNode = None
        self.observedSegmentationNode = None
        self.updatingOverwriteMode = False
        self.updatingStatus = False

        self.customShortcuts = {}
        self.shortcutInputs = {}
        self.displayedSegmentIds = []
        self.segmentCheckboxes = {}

        # Batch Case Manager state
        self.loadedVolumeNode = None
        self.loadedSegmentationNode = None
        self.matchedCases = []
        self.currentLoadedCaseIndex = None

        # Debounced volume refresh timer
        self.volumeRefreshTimer = qt.QTimer(self.parent)
        self.volumeRefreshTimer.setSingleShot(True)
        self.volumeRefreshTimer.setInterval(5000)
        self.volumeRefreshTimer.timeout.connect(self.onRefreshSegmentVolumes)

        self.loadShortcuts()
        self._buildUi()
        self.setupShortcuts()
        self.setupStatusTimer()

        # Connect to focus change to dynamically enable/disable shortcuts
        try:
            qt.QApplication.instance().focusChanged.connect(self.updateShortcutsState)
        except Exception as e:
            logging.warning(f"Could not connect to focusChanged: {e}")

        # Connect to segment editor widget signals for instant node selection updates
        try:
            editorWidget = self.logic.segmentEditorWidget()
            editorWidget.segmentationNodeChanged.connect(self.onSegmentationNodeChanged)
        except Exception as e:
            logging.warning(f"Could not connect to segment editor widget signals: {e}")

        # Observe the scene for file loading/drop events
        self.addObserver(slicer.mrmlScene, slicer.vtkMRMLScene.NodeAddedEvent, self.onNodeAdded)
        self.addObserver(slicer.mrmlScene, slicer.vtkMRMLScene.NodeRemovedEvent, self.onNodeRemoved)
        self.addObserver(slicer.mrmlScene, slicer.vtkMRMLScene.EndImportEvent, self.onSceneImported)

        self.observeSegmentEditorNode()
        self.observeSegmentationNode()
        self.updateStatus()

    def _buildUi(self):
        # --- Module Navigation ---
        switcherGroupBox = qt.QGroupBox("Module Navigation")
        switcherLayout = qt.QHBoxLayout(switcherGroupBox)
        
        self.btnEditor = qt.QPushButton("Segment Editor")
        self.btnTools = qt.QPushButton("Hemorrhage Tools")
        self.btnMorphology = qt.QPushButton("Hemorrhage Morphology")
        
        self.btnEditor.toolTip = "Switch to Segment Editor module."
        self.btnTools.toolTip = "Currently in Hemorrhage Tools module."
        self.btnMorphology.toolTip = "Switch to Hemorrhage Morphology module."
        
        self.btnTools.enabled = False  # We are currently in this module
        
        self.btnEditor.clicked.connect(self.onSwitchToSegmentEditor)
        self.btnMorphology.clicked.connect(lambda: slicer.util.selectModule("SlicerMorphology"))
        
        switcherLayout.addWidget(self.btnEditor)
        switcherLayout.addWidget(self.btnTools)
        switcherLayout.addWidget(self.btnMorphology)
        self.layout.addWidget(switcherGroupBox)

        mainCollapsibleButton = ctk.ctkCollapsibleButton()
        mainCollapsibleButton.text = "Hemorrhage cleanup"
        self.layout.addWidget(mainCollapsibleButton)

        formLayout = qt.QFormLayout(mainCollapsibleButton)

        brainWindowButton = qt.QPushButton("Set Brain Window")
        brainWindowButton.toolTip = "Set the current background CT volume to W/L 80/40."
        brainWindowButton.clicked.connect(self.onSetBrainWindow)
        formLayout.addRow(brainWindowButton)

        openSegmentEditorButton = qt.QPushButton("Open Segment Editor")
        openSegmentEditorButton.toolTip = "Switch to Segment Editor to choose source volume, segmentation, and segment."
        openSegmentEditorButton.clicked.connect(self.onOpenSegmentEditor)
        formLayout.addRow(openSegmentEditorButton)

        settings = qt.QSettings()
        range1Min = float(settings.value("SlicerHemorrhageTools/Range1Min", 40))
        range1Max = float(settings.value("SlicerHemorrhageTools/Range1Max", 80))
        range2Min = float(settings.value("SlicerHemorrhageTools/Range2Min", 5))
        range2Max = float(settings.value("SlicerHemorrhageTools/Range2Max", 33))

        self.highMinimumSpinBox = self.createHuSpinBox(range1Min)
        self.highMaximumSpinBox = self.createHuSpinBox(range1Max)
        self.lowMinimumSpinBox = self.createHuSpinBox(range2Min)
        self.lowMaximumSpinBox = self.createHuSpinBox(range2Max)

        # Connect value change signals to update settings
        self.highMinimumSpinBox.valueChanged.connect(
            lambda val: qt.QSettings().setValue("SlicerHemorrhageTools/Range1Min", val)
        )
        self.highMaximumSpinBox.valueChanged.connect(
            lambda val: qt.QSettings().setValue("SlicerHemorrhageTools/Range1Max", val)
        )
        self.lowMinimumSpinBox.valueChanged.connect(
            lambda val: qt.QSettings().setValue("SlicerHemorrhageTools/Range2Min", val)
        )
        self.lowMaximumSpinBox.valueChanged.connect(
            lambda val: qt.QSettings().setValue("SlicerHemorrhageTools/Range2Max", val)
        )

        highRangeLayout = self.createRangeLayout(self.highMinimumSpinBox, self.highMaximumSpinBox)
        lowRangeLayout = self.createRangeLayout(self.lowMinimumSpinBox, self.lowMaximumSpinBox)
        formLayout.addRow("Range 1 HU:", highRangeLayout)
        formLayout.addRow("Range 2 HU:", lowRangeLayout)

        modeLayout = qt.QGridLayout()
        self.paintHighButton = qt.QPushButton()
        self.eraseLowButton = qt.QPushButton()
        self.paintLowButton = qt.QPushButton()
        self.eraseHighButton = qt.QPushButton()

        self.paintHighButton.clicked.connect(lambda: self.onSetMode("Paint", "high"))
        self.eraseLowButton.clicked.connect(lambda: self.onSetMode("Erase", "low"))
        self.paintLowButton.clicked.connect(lambda: self.onSetMode("Paint", "low"))
        self.eraseHighButton.clicked.connect(lambda: self.onSetMode("Erase", "high"))

        modeLayout.addWidget(self.paintHighButton, 0, 0)
        modeLayout.addWidget(self.eraseLowButton, 0, 1)
        modeLayout.addWidget(self.paintLowButton, 1, 0)
        modeLayout.addWidget(self.eraseHighButton, 1, 1)
        formLayout.addRow(modeLayout)

        self.workflowButtons = [
            self.paintHighButton,
            self.eraseLowButton,
            self.paintLowButton,
            self.eraseHighButton,
        ]

        self.overwriteModeComboBox = qt.QComboBox()
        self.overwriteModeComboBox.addItem("Do not overwrite segments", "none")
        self.overwriteModeComboBox.addItem("Overwrite visible segments", "visible")
        self.overwriteModeComboBox.toolTip = "Controls how Paint handles overlap with other visible segments."
        self.overwriteModeComboBox.currentIndexChanged.connect(lambda unusedIndex: self.onOverwriteModeChanged())
        formLayout.addRow("Overwrite:", self.overwriteModeComboBox)

        brushLayout = qt.QHBoxLayout()
        self.brushSmallerButton = qt.QPushButton("Brush Smaller")
        self.brushLargerButton = qt.QPushButton("Brush Larger")
        self.brushSmallerButton.toolTip = "Decrease Paint/Erase brush diameter."
        self.brushLargerButton.toolTip = "Increase Paint/Erase brush diameter."
        self.brushSmallerButton.clicked.connect(lambda: self.onAdjustBrush(-1.0))
        self.brushLargerButton.clicked.connect(lambda: self.onAdjustBrush(1.0))
        brushLayout.addWidget(self.brushSmallerButton)
        brushLayout.addWidget(self.brushLargerButton)
        formLayout.addRow(brushLayout)

        # Margin operations
        marginInputLayout = qt.QHBoxLayout()
        self.marginSizeSpinBox = qt.QDoubleSpinBox()
        self.marginSizeSpinBox.minimum = 0.1
        self.marginSizeSpinBox.maximum = 20.0
        marginSize = float(settings.value("SlicerHemorrhageTools/MarginSize", 1.0))
        self.marginSizeSpinBox.value = marginSize
        self.marginSizeSpinBox.singleStep = 0.5
        self.marginSizeSpinBox.suffix = " mm"
        marginInputLayout.addWidget(self.marginSizeSpinBox)
        self.marginSizeSpinBox.valueChanged.connect(
            lambda val: qt.QSettings().setValue("SlicerHemorrhageTools/MarginSize", val)
        )

        self.marginMaskingComboBox = qt.QComboBox()
        self.marginMaskingComboBox.addItem("Default (Dilate R1 / Erode R2)", "default")
        self.marginMaskingComboBox.addItem("No masking", "none")
        self.marginMaskingComboBox.addItem("Range 1 HU", "range1")
        self.marginMaskingComboBox.addItem("Range 2 HU", "range2")
        self.marginMaskingComboBox.addItem("Current editor mask", "current")
        self.marginMaskingComboBox.toolTip = "Constrain grow/shrink to only voxels within these HU thresholds."
        marginInputLayout.addWidget(self.marginMaskingComboBox)
        formLayout.addRow("Margin:", marginInputLayout)

        marginButtonsLayout = qt.QHBoxLayout()
        self.dilateButton = qt.QPushButton("Dilate Active Segment")
        self.erodeButton = qt.QPushButton("Erode Active Segment")
        self.dilateButton.toolTip = "Grow active segment boundary by the margin size (default: constrained to Range 1 HU)."
        self.erodeButton.toolTip = "Shrink active segment boundary by the margin size (default: constrained to Range 2 HU)."
        self.dilateButton.clicked.connect(self.onPerformDilate)
        self.erodeButton.clicked.connect(self.onPerformErode)
        marginButtonsLayout.addWidget(self.dilateButton)
        marginButtonsLayout.addWidget(self.erodeButton)
        formLayout.addRow(marginButtonsLayout)

        self.workflowButtons.extend([self.dilateButton, self.erodeButton])

        self.maskToggleButton = qt.QPushButton("Editable Intensity On/Off")
        self.maskToggleButton.toolTip = "Toggle source volume editable intensity masking."
        self.maskToggleButton.clicked.connect(self.onToggleMask)
        formLayout.addRow(self.maskToggleButton)

        self.toggleSegmentationVisibilityButton = qt.QPushButton("Toggle Segmentation Visibility")
        self.toggleSegmentationVisibilityButton.toolTip = "Toggle the visibility of the active segmentation node."
        self.toggleSegmentationVisibilityButton.clicked.connect(self.onToggleSegmentationVisibility)
        formLayout.addRow(self.toggleSegmentationVisibilityButton)

        # Rename Segmentation
        self.renameSegmentationLineEdit = qt.QLineEdit()
        self.renameSegmentationLineEdit.toolTip = "Rename the current active segmentation node."
        self.renameSegmentationLineEdit.editingFinished.connect(self.onRenameSegmentation)
        formLayout.addRow("Rename Segmentation:", self.renameSegmentationLineEdit)

        self.segmentsGroupBox = qt.QGroupBox("Segments Visibility")
        self.segmentsLayout = qt.QVBoxLayout(self.segmentsGroupBox)
        formLayout.addRow(self.segmentsGroupBox)

        self.refreshVolumesButton = qt.QPushButton("Refresh Segment Volumes")
        self.refreshVolumesButton.toolTip = "List current segments and labelmap volumes for the active segmentation."
        self.refreshVolumesButton.clicked.connect(self.onRefreshSegmentVolumes)
        formLayout.addRow(self.refreshVolumesButton)

        self.segmentVolumesTextEdit = qt.QPlainTextEdit()
        self.segmentVolumesTextEdit.setReadOnly(True)
        self.segmentVolumesTextEdit.maximumHeight = 120
        self.segmentVolumesTextEdit.setPlainText("Segment volumes: not calculated")
        formLayout.addRow("Volumes:", self.segmentVolumesTextEdit)

        self.ratioLabel = qt.QLabel("N/A")
        self.ratioLabel.setStyleSheet("font-weight: bold; font-size: 11pt;")
        formLayout.addRow("PHE/Hematoma Ratio:", self.ratioLabel)

        # Islands / Satellites UI
        self.traceSatellitesCheckBox = qt.QCheckBox("Trace Satellite Connections")
        self.traceSatellitesCheckBox.setChecked(qt.QSettings().value("SlicerHemorrhageTools/TraceSatellites", "false") == "true")
        self.traceSatellitesCheckBox.toolTip = "Identify disconnected components of the active segment and show virtual connection lines and distances on 2D slices."
        self.traceSatellitesCheckBox.stateChanged.connect(self.onTraceSatellitesToggle)
        formLayout.addRow(self.traceSatellitesCheckBox)

        self.satellitesLabel = qt.QLabel("N/A")
        self.satellitesLabel.setStyleSheet("font-weight: bold; font-size: 11pt;")
        formLayout.addRow("Islands / Satellites:", self.satellitesLabel)

        # Satellite Cleanup Tools UI
        self.cleanupCollapsibleButton = ctk.ctkCollapsibleButton()
        self.cleanupCollapsibleButton.text = "Satellite Cleanup Tools"
        self.cleanupCollapsibleButton.collapsed = True
        formLayout.addRow(self.cleanupCollapsibleButton)

        cleanupFormLayout = qt.QFormLayout(self.cleanupCollapsibleButton)

        # Size threshold check and spinbox
        self.cleanupSizeCheckBox = qt.QCheckBox("Remove satellites size <=")
        self.cleanupSizeCheckBox.toolTip = "Delete all satellite components that are smaller than or equal to this volume (in mL). The main body is always kept."
        self.cleanupSizeCheckBox.setChecked(qt.QSettings().value("SlicerHemorrhageTools/CleanupSizeEnabled", "false") == "true")
        self.cleanupSizeCheckBox.stateChanged.connect(self.onCleanupSettingsChanged)

        self.cleanupSizeSpinBox = qt.QDoubleSpinBox()
        self.cleanupSizeSpinBox.minimum = 0.01
        self.cleanupSizeSpinBox.maximum = 50.0
        self.cleanupSizeSpinBox.value = float(qt.QSettings().value("SlicerHemorrhageTools/CleanupSizeLimit", 0.10))
        self.cleanupSizeSpinBox.singleStep = 0.05
        self.cleanupSizeSpinBox.suffix = " mL"
        self.cleanupSizeSpinBox.valueChanged.connect(self.onCleanupSettingsChanged)

        sizeLayout = qt.QHBoxLayout()
        sizeLayout.addWidget(self.cleanupSizeCheckBox)
        sizeLayout.addWidget(self.cleanupSizeSpinBox)
        cleanupFormLayout.addRow(sizeLayout)

        # Distance threshold check and spinbox
        self.cleanupDistanceCheckBox = qt.QCheckBox("Remove satellites distance >=")
        self.cleanupDistanceCheckBox.toolTip = "Delete all satellite components that are further than or equal to this boundary distance (in mm) from the main body. The main body is always kept."
        self.cleanupDistanceCheckBox.setChecked(qt.QSettings().value("SlicerHemorrhageTools/CleanupDistanceEnabled", "false") == "true")
        self.cleanupDistanceCheckBox.stateChanged.connect(self.onCleanupSettingsChanged)

        self.cleanupDistanceSpinBox = qt.QDoubleSpinBox()
        self.cleanupDistanceSpinBox.minimum = 1.0
        self.cleanupDistanceSpinBox.maximum = 200.0
        self.cleanupDistanceSpinBox.value = float(qt.QSettings().value("SlicerHemorrhageTools/CleanupDistanceLimit", 20.0))
        self.cleanupDistanceSpinBox.singleStep = 1.0
        self.cleanupDistanceSpinBox.suffix = " mm"
        self.cleanupDistanceSpinBox.valueChanged.connect(self.onCleanupSettingsChanged)

        distLayout = qt.QHBoxLayout()
        distLayout.addWidget(self.cleanupDistanceCheckBox)
        distLayout.addWidget(self.cleanupDistanceSpinBox)
        cleanupFormLayout.addRow(distLayout)

        # Auto-apply toggle
        self.cleanupAutoApplyCheckBox = qt.QCheckBox("Auto-apply cleanup on refresh")
        self.cleanupAutoApplyCheckBox.toolTip = "Automatically run the enabled cleanup filters every time segment volumes are refreshed (manual button or auto-refresh)."
        self.cleanupAutoApplyCheckBox.setChecked(qt.QSettings().value("SlicerHemorrhageTools/CleanupAutoApply", "false") == "true")
        self.cleanupAutoApplyCheckBox.stateChanged.connect(self.onCleanupSettingsChanged)
        cleanupFormLayout.addRow(self.cleanupAutoApplyCheckBox)

        # Cleanup action button
        self.cleanupApplyButton = qt.QPushButton("Apply Cleanup Now")
        self.cleanupApplyButton.toolTip = "Run cleanup filtering on the active segment immediately."
        self.cleanupApplyButton.clicked.connect(self.onApplyCleanup)
        cleanupFormLayout.addRow(self.cleanupApplyButton)

        self.statusLabel = qt.QLabel()
        self.statusLabel.wordWrap = True
        formLayout.addRow("Status:", self.statusLabel)

        # --- Batch Case Manager UI ---
        batchCollapsibleButton = ctk.ctkCollapsibleButton()
        batchCollapsibleButton.text = "Batch Case Manager"
        batchCollapsibleButton.collapsed = True
        self.layout.addWidget(batchCollapsibleButton)

        batchFormLayout = qt.QFormLayout(batchCollapsibleButton)

        self.ctDirButton = ctk.ctkDirectoryButton()
        self.ctDirButton.toolTip = "Directory containing source CT volumes."
        batchFormLayout.addRow("CT Folder:", self.ctDirButton)

        self.segDirButton = ctk.ctkDirectoryButton()
        self.segDirButton.toolTip = "Directory containing input segmentations."
        batchFormLayout.addRow("Segmentation Folder:", self.segDirButton)

        self.outDirButton = ctk.ctkDirectoryButton()
        self.outDirButton.toolTip = "Directory where cleaned segmentations will be saved."
        batchFormLayout.addRow("Output Folder:", self.outDirButton)

        # Annotator Suffix
        self.annotatorSuffixLineEdit = qt.QLineEdit()
        self.annotatorSuffixLineEdit.toolTip = "Suffix added to saved files (e.g. _anjan)."
        self.annotatorSuffixLineEdit.placeholderText = "e.g. _anjan"
        self.annotatorSuffixLineEdit.text = settings.value("SlicerHemorrhageTools/AnnotatorSuffix", "")
        self.annotatorSuffixLineEdit.textChanged.connect(
            lambda val: qt.QSettings().setValue("SlicerHemorrhageTools/AnnotatorSuffix", val)
        )
        batchFormLayout.addRow("Annotator Suffix:", self.annotatorSuffixLineEdit)

        # Flag Case
        self.caseFlagComboBox = qt.QComboBox()
        self.caseFlagComboBox.addItems(["None", "Needs Review", "Uncertain", "Skip"])
        self.caseFlagComboBox.toolTip = "Flag case status."
        batchFormLayout.addRow("Flag Case:", self.caseFlagComboBox)

        # Case Notes
        self.caseNotesLineEdit = qt.QLineEdit()
        self.caseNotesLineEdit.toolTip = "Enter any notes or observations about this case."
        self.caseNotesLineEdit.placeholderText = "Enter notes here..."
        batchFormLayout.addRow("Case Notes:", self.caseNotesLineEdit)

        self.caseComboBox = qt.QComboBox()
        self.caseComboBox.toolTip = "Scanned and matched cases from directories."
        batchFormLayout.addRow("Select Case:", self.caseComboBox)

        # Progress bar
        self.batchProgressBar = qt.QProgressBar()
        self.batchProgressBar.minimum = 0
        self.batchProgressBar.maximum = 0
        self.batchProgressBar.value = 0
        self.batchProgressBar.textVisible = True
        batchFormLayout.addRow("Progress:", self.batchProgressBar)

        batchNavLayout = qt.QHBoxLayout()
        self.loadCaseButton = qt.QPushButton("Load Selected Case")
        self.loadCaseButton.toolTip = "Load the selected case into Slicer."
        self.saveCaseButton = qt.QPushButton("Save Current Case")
        self.saveCaseButton.toolTip = "Save active segmentation and notes to Output Folder."
        self.saveLoadNextButton = qt.QPushButton("Save & Load Next")
        self.saveLoadNextButton.toolTip = "Save active segmentation to Output Folder and advance to the next case."
        
        batchNavLayout.addWidget(self.loadCaseButton)
        batchNavLayout.addWidget(self.saveCaseButton)
        batchNavLayout.addWidget(self.saveLoadNextButton)
        batchFormLayout.addRow(batchNavLayout)

        self.batchStatusLabel = qt.QLabel("Specify folders to scan cases.")
        self.batchStatusLabel.wordWrap = True
        batchFormLayout.addRow("Batch Status:", self.batchStatusLabel)

        # Load Batch settings
        ctPath = settings.value("SlicerHemorrhageTools/BatchCTPath", "")
        segPath = settings.value("SlicerHemorrhageTools/BatchSegPath", "")
        outPath = settings.value("SlicerHemorrhageTools/BatchOutPath", "")
        if ctPath:
            self.ctDirButton.directory = ctPath
        if segPath:
            self.segDirButton.directory = segPath
        if outPath:
            self.outDirButton.directory = outPath

        # Connect signals
        self.ctDirButton.directoryChanged.connect(self.scanBatchDirectories)
        self.segDirButton.directoryChanged.connect(self.scanBatchDirectories)
        self.outDirButton.directoryChanged.connect(self.scanBatchDirectories)
        self.loadCaseButton.clicked.connect(self.onLoadCase)
        self.saveCaseButton.clicked.connect(self.saveCurrentSegmentation)
        self.saveLoadNextButton.clicked.connect(self.onSaveAndLoadNext)

        # Initial scan
        self.scanBatchDirectories()

        # Keyboard Shortcuts configuration UI
        shortcutsCollapsibleButton = ctk.ctkCollapsibleButton()
        shortcutsCollapsibleButton.text = "Keyboard Shortcuts"
        shortcutsCollapsibleButton.collapsed = True
        self.layout.addWidget(shortcutsCollapsibleButton)

        shortcutsFormLayout = qt.QFormLayout(shortcutsCollapsibleButton)
        self.shortcutInputs = {}
        for action in self.DEFAULT_SHORTCUTS.keys():
            lineEdit = qt.QLineEdit()
            lineEdit.text = self.customShortcuts.get(action, "")
            lineEdit.toolTip = f"Shortcut key sequence for '{action}'"
            self.shortcutInputs[action] = lineEdit
            shortcutsFormLayout.addRow(f"{action}:", lineEdit)

        saveShortcutsButton = qt.QPushButton("Apply and Save Shortcuts")
        saveShortcutsButton.clicked.connect(self.onSaveShortcuts)
        shortcutsFormLayout.addRow(saveShortcutsButton)

        self.layout.addStretch(1)
        self.updateModeButtonLabels()

    def cleanup(self):
        self.removeObservers()
        if hasattr(self, "statusTimer") and self.statusTimer:
            self.statusTimer.stop()
        try:
            qt.QApplication.instance().focusChanged.disconnect(self.updateShortcutsState)
        except Exception:
            pass
        for shortcut in self.shortcuts.values():
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts = {}

        try:
            editorWidget = self.logic.segmentEditorWidget()
            editorWidget.segmentationNodeChanged.disconnect(self.onSegmentationNodeChanged)
        except Exception:
            pass

    def enter(self):
        layoutManager = slicer.app.layoutManager()
        if layoutManager:
            currentLayout = layoutManager.layout
            # If stuck in a single slice view (Red=6, Yellow=7, Green=8), restore the saved layout
            if currentLayout in [6, 7, 8]:
                savedLayout = qt.QSettings().value("SlicerHemorrhageTools/SavedLayout")
                if savedLayout is not None:
                    try:
                        layoutId = int(savedLayout)
                        layoutManager.setLayout(layoutId)
                        return
                    except Exception:
                        pass
                # Fallback to FourUpView
                layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)

    def onSwitchToSegmentEditor(self):
        layoutManager = slicer.app.layoutManager()
        if layoutManager:
            currentLayout = layoutManager.layout
            # If it's not a single slice view, save it
            if currentLayout not in [6, 7, 8]:
                qt.QSettings().setValue("SlicerHemorrhageTools/SavedLayout", currentLayout)
        slicer.util.selectModule("SegmentEditor")

    def setupStatusTimer(self):
        self.statusTimer = qt.QTimer(self.parent)
        self.statusTimer.setInterval(1000)
        self.statusTimer.timeout.connect(self.updateStatus)
        self.statusTimer.start()

    def loadShortcuts(self):
        settings = qt.QSettings()
        self.customShortcuts = {}
        for action, defaultKey in self.DEFAULT_SHORTCUTS.items():
            val = settings.value(f"SlicerHemorrhageTools/Shortcut_{action.replace(' ', '_')}")
            if val is None or val == "":
                val = defaultKey
            self.customShortcuts[action] = val

    def onSaveShortcuts(self):
        settings = qt.QSettings()
        for action, lineEdit in self.shortcutInputs.items():
            key = lineEdit.text.strip()
            settings.setValue(f"SlicerHemorrhageTools/Shortcut_{action.replace(' ', '_')}", key)
        self.setupShortcuts()
        self.updateStatus("Shortcuts updated and saved.")

    def scanBatchDirectories(self):
        import os
        import glob
        
        ctDir = self.ctDirButton.directory
        segDir = self.segDirButton.directory
        outDir = self.outDirButton.directory
        
        # Save to QSettings
        settings = qt.QSettings()
        settings.setValue("SlicerHemorrhageTools/BatchCTPath", ctDir)
        settings.setValue("SlicerHemorrhageTools/BatchSegPath", segDir)
        settings.setValue("SlicerHemorrhageTools/BatchOutPath", outDir)
        
        # Disconnect select changes to avoid triggering load case during clear
        self.caseComboBox.blockSignals(True)
        self.caseComboBox.clear()
        self.matchedCases = []
        
        if not ctDir or not os.path.exists(ctDir) or not segDir or not os.path.exists(segDir):
            self.batchStatusLabel.text = "Please select valid CT and Segmentation folders."
            self.loadCaseButton.enabled = False
            self.saveCaseButton.enabled = False
            self.saveLoadNextButton.enabled = False
            self.batchProgressBar.maximum = 0
            self.batchProgressBar.value = 0
            self.caseComboBox.blockSignals(False)
            return
            
        # List CT files
        ctExtensions = ["*.nii.gz", "*.nii", "*.nrrd", "*.mha", "*.mhd"]
        ctFiles = []
        for ext in ctExtensions:
            ctFiles.extend(glob.glob(os.path.join(ctDir, ext)))
            ctFiles.extend(glob.glob(os.path.join(ctDir, ext.upper())))
        
        # List Segmentation files
        segExtensions = ["*.seg.nrrd", "*.nrrd", "*.nii.gz", "*.nii", "*.mha", "*.mhd"]
        segFiles = []
        for ext in segExtensions:
            segFiles.extend(glob.glob(os.path.join(segDir, ext)))
            segFiles.extend(glob.glob(os.path.join(segDir, ext.upper())))
            
        # De-duplicate file paths
        ctFiles = sorted(list(set(os.path.abspath(f) for f in ctFiles)))
        segFiles = sorted(list(set(os.path.abspath(f) for f in segFiles)))
        
        # Suffixes to strip for clean root name comparison
        suffixes_to_strip = [
            ".seg.nrrd", ".seg", ".nrrd", ".nii.gz", ".nii", ".mha", ".mhd",
            "_anjan_ich", "_seg", "-seg", "_segmentation", "_cleaned"
        ]
        
        def get_clean_root(filename):
            name = os.path.basename(filename).lower()
            # Loop multiple times to strip nested extensions or suffixes (e.g. .seg.nrrd)
            changed = True
            while changed:
                changed = False
                for suffix in suffixes_to_strip:
                    if name.endswith(suffix):
                        name = name[:-len(suffix)]
                        changed = True
            # Strip non-alphanumeric chars at start/end
            name = name.strip("_- ")
            return name
            
        # Pair files
        matched = []
        for ctFile in ctFiles:
            ct_root = get_clean_root(ctFile)
            if not ct_root:
                continue
            
            # Find a matching segmentation file
            best_match = None
            for segFile in segFiles:
                seg_root = get_clean_root(segFile)
                if not seg_root:
                    continue
                # If either contains the other, we consider it a match
                if ct_root == seg_root or ct_root in seg_root or seg_root in ct_root:
                    best_match = segFile
                    break
                    
            if best_match:
                case_name = os.path.basename(ctFile)
                # Strip standard extensions for a cleaner label in combo box
                for ext in [".nii.gz", ".nii", ".nrrd", ".mha", ".mhd"]:
                    if case_name.lower().endswith(ext):
                        case_name = case_name[:-len(ext)]
                        break
                matched.append({
                    "caseName": case_name,
                    "ctPath": ctFile,
                    "segPath": best_match
                })
                
        # Sort matched cases alphabetically/numerically by case name
        matched.sort(key=lambda x: x["caseName"].lower())
        self.matchedCases = matched
        
        # Populate combobox
        for case in self.matchedCases:
            self.caseComboBox.addItem(
                f"{case['caseName']} (CT: {os.path.basename(case['ctPath'])}, Seg: {os.path.basename(case['segPath'])})",
                case
            )
            
        self.caseComboBox.blockSignals(False)
            
        if self.matchedCases:
            self.batchStatusLabel.text = f"Scanned: {len(self.matchedCases)} matching cases found."
            self.loadCaseButton.enabled = True
            self.saveCaseButton.enabled = True
            self.saveLoadNextButton.enabled = True
            self.batchProgressBar.maximum = len(self.matchedCases)
            
            # Restore position from settings
            lastCaseIndex = settings.value("SlicerHemorrhageTools/BatchLastCaseIndex")
            if lastCaseIndex is not None:
                try:
                    index = int(lastCaseIndex)
                    if 0 <= index < len(self.matchedCases):
                        self.caseComboBox.setCurrentIndex(index)
                        self.batchProgressBar.value = index
                except (ValueError, TypeError):
                    pass
        else:
            self.batchStatusLabel.text = "No matching CT/segmentation cases found."
            self.loadCaseButton.enabled = False
            self.saveCaseButton.enabled = False
            self.saveLoadNextButton.enabled = False
            self.batchProgressBar.maximum = 0
            self.batchProgressBar.value = 0

    def confirmUnsavedChanges(self):
        if not self.loadedSegmentationNode:
            return True
            
        segModified = self.loadedSegmentationNode.GetModifiedSinceRead()
        notesModified = (self.caseNotesLineEdit.text.strip() != getattr(self, "loadedNotesText", "") or 
                         self.caseFlagComboBox.currentText != getattr(self, "loadedFlagText", "None"))
                         
        if not segModified and not notesModified:
            return True
            
        msgBox = qt.QMessageBox(slicer.util.mainWindow())
        msgBox.setWindowTitle("Unsaved Changes")
        msgBox.setText("The current segmentation or notes have unsaved changes. Do you want to save them before proceeding?")
        
        saveButton = msgBox.addButton("Save & Continue", qt.QMessageBox.AcceptRole)
        discardButton = msgBox.addButton("Discard Changes", qt.QMessageBox.DestructiveRole)
        cancelButton = msgBox.addButton(qt.QMessageBox.Cancel)
        
        msgBox.exec_()
        clickedButton = msgBox.clickedButton()
        
        if clickedButton == saveButton:
            if not self.saveCurrentSegmentation():
                return False  # Save failed or cancelled, do not proceed
            return True
        elif clickedButton == discardButton:
            return True  # Proceed without saving
        else:
            return False  # Cancel

    def saveCurrentSegmentation(self):
        import os
        if not self.matchedCases:
            return False
            
        caseIndex = self.caseComboBox.currentIndex
        if caseIndex < 0 or caseIndex >= len(self.matchedCases):
            return False
            
        case = self.matchedCases[caseIndex]
        outDir = self.outDirButton.directory
        
        if not outDir:
            self.reportError("Output directory is not specified.")
            return False
            
        try:
            os.makedirs(outDir, exist_ok=True)
        except Exception as e:
            self.reportError(f"Failed to create output directory {outDir}: {e}")
            return False
            
        # Get active segmentation node
        segmentationNode = None
        try:
            editorWidget = self.logic.segmentEditorWidget()
            segmentationNode = editorWidget.segmentationNode()
        except Exception:
            pass
            
        if not segmentationNode:
            segmentationNode = self.loadedSegmentationNode
            
        if not segmentationNode:
            self.reportError("No active segmentation node to save.")
            return False
            
        # Construct output path using the original filename and suffix
        origFilename = os.path.basename(case["segPath"])
        suffix = self.annotatorSuffixLineEdit.text.strip()
        if suffix:
            base, ext = os.path.splitext(origFilename)
            if base.endswith(".seg"):
                base = base[:-4]
                outputPath = os.path.join(outDir, f"{base}{suffix}.seg{ext}")
            else:
                outputPath = os.path.join(outDir, f"{base}{suffix}{ext}")
        else:
            outputPath = os.path.join(outDir, origFilename)
            
        # Save node
        try:
            success = slicer.util.saveNode(segmentationNode, outputPath)
            if not success:
                raise RuntimeError("Slicer saveNode returned False.")
        except Exception as e:
            self.reportError(f"Failed to save cleaned segmentation: {e}")
            return False
            
        self.updateStatus(f"Saved {os.path.basename(outputPath)} to {outDir}")
        
        # Save notes sidecar
        self.saveNotesSidecar(outputPath)
        
        return True

    def saveNotesSidecar(self, segmentationOutputPath):
        import os
        flag = self.caseFlagComboBox.currentText
        notes = self.caseNotesLineEdit.text.strip()
        
        notesPath = os.path.splitext(segmentationOutputPath)[0] + "_notes.txt"
        
        if flag != "None" or notes or os.path.exists(notesPath):
            try:
                with open(notesPath, "w") as f:
                    f.write(f"Flag: {flag}\n")
                    f.write(f"Notes: {notes}\n")
                # Update cache of loaded notes to reflect saved state
                self.loadedFlagText = flag
                self.loadedNotesText = notes
                logging.debug(f"Saved sidecar notes to {notesPath}")
            except Exception as e:
                logging.warning(f"Could not save sidecar notes to {notesPath}: {e}")

    def loadNotesSidecar(self, case):
        import os
        outDir = self.outDirButton.directory
        origFilename = os.path.basename(case["segPath"])
        suffix = self.annotatorSuffixLineEdit.text.strip()
        
        if suffix:
            base, ext = os.path.splitext(origFilename)
            if base.endswith(".seg"):
                base = base[:-4]
                outputPath = os.path.join(outDir, f"{base}{suffix}.seg{ext}")
            else:
                outputPath = os.path.join(outDir, f"{base}{suffix}{ext}")
        else:
            outputPath = os.path.join(outDir, origFilename)
            
        notesPath = os.path.splitext(outputPath)[0] + "_notes.txt"
        
        flag = "None"
        notes = ""
        
        if os.path.exists(notesPath):
            try:
                with open(notesPath, "r") as f:
                    for line in f:
                        if line.startswith("Flag:"):
                            flag = line.split(":", 1)[1].strip()
                        elif line.startswith("Notes:"):
                            notes = line.split(":", 1)[1].strip()
            except Exception as e:
                logging.warning(f"Could not read sidecar notes from {notesPath}: {e}")
                
        self.loadedFlagText = flag
        self.loadedNotesText = notes
        
        index = self.caseFlagComboBox.findText(flag)
        if index >= 0:
            self.caseFlagComboBox.setCurrentIndex(index)
        else:
            self.caseFlagComboBox.setCurrentIndex(0)
            
        self.caseNotesLineEdit.text = notes

    def onLoadCase(self):
        import os
        if not self.matchedCases:
            return
            
        caseIndex = self.caseComboBox.currentIndex
        if caseIndex < 0 or caseIndex >= len(self.matchedCases):
            return
            
        if not self.confirmUnsavedChanges():
            # Restore combo box to currently loaded index
            if hasattr(self, "currentLoadedCaseIndex") and self.currentLoadedCaseIndex is not None:
                self.caseComboBox.blockSignals(True)
                self.caseComboBox.setCurrentIndex(self.currentLoadedCaseIndex)
                self.caseComboBox.blockSignals(False)
            return
            
        case = self.matchedCases[caseIndex]
        ctPath = case["ctPath"]
        segPath = case["segPath"]
        
        # 1. Clean up previous nodes loaded by our batch manager
        if self.loadedVolumeNode:
            try:
                slicer.mrmlScene.RemoveNode(self.loadedVolumeNode)
            except Exception as e:
                logging.debug(f"Failed to remove previous volume node: {e}")
            self.loadedVolumeNode = None
            
        if self.loadedSegmentationNode:
            try:
                slicer.mrmlScene.RemoveNode(self.loadedSegmentationNode)
            except Exception as e:
                logging.debug(f"Failed to remove previous segmentation node: {e}")
            self.loadedSegmentationNode = None
            
        # 2. Load CT volume
        try:
            volumeNode = slicer.util.loadVolume(ctPath)
            self.loadedVolumeNode = volumeNode
        except Exception as e:
            self.reportError(f"Failed to load CT volume {ctPath}: {e}")
            return
            
        # 3. Load Segmentation
        try:
            segmentationNode = slicer.util.loadSegmentation(segPath)
            self.loadedSegmentationNode = segmentationNode
        except Exception as e:
            self.reportError(f"Failed to load segmentation {segPath}: {e}")
            return
            
        # 4. Connect to Segment Editor
        try:
            editorWidget = self.logic.segmentEditorWidget()
            if editorWidget:
                if not editorWidget.mrmlScene():
                    editorWidget.setMRMLScene(slicer.mrmlScene)
                
                parameterNode = editorWidget.mrmlSegmentEditorNode()
                if not parameterNode:
                    parameterNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode")
                    editorWidget.setMRMLSegmentEditorNode(parameterNode)
                
                if parameterNode:
                    parameterNode.SetNodeReferenceID("masterVolumeRef", self.loadedVolumeNode.GetID() if self.loadedVolumeNode else "")
                    parameterNode.SetNodeReferenceID("segmentationRef", self.loadedSegmentationNode.GetID() if self.loadedSegmentationNode else "")
                
                editorWidget.setSourceVolumeNode(self.loadedVolumeNode)
                editorWidget.setSegmentationNode(self.loadedSegmentationNode)
                
            # Autoselect the first segment if available to prevent validation crash
            segmentation = self.loadedSegmentationNode.GetSegmentation()
            if segmentation.GetNumberOfSegments() > 0:
                firstSegId = segmentation.GetNthSegmentID(0)
                editorWidget.setCurrentSegmentID(firstSegId)
        except Exception as e:
            logging.warning(f"Could not fully set up Segment Editor: {e}")
            
        # 5. Fit views to loaded data (Re-centering) & Propagate volume selection
        if self.loadedVolumeNode:
            try:
                # Set background volume globally in Slicer
                slicer.util.setSliceViewerLayers(background=self.loadedVolumeNode)
                appLogic = slicer.app.applicationLogic()
                selectionNode = appLogic.GetSelectionNode()
                if selectionNode:
                    selectionNode.SetReferenceActiveVolumeID(self.loadedVolumeNode.GetID())
                    if self.loadedSegmentationNode:
                        selectionNode.SetReferenceActiveSegmentationID(self.loadedSegmentationNode.GetID())
                    appLogic.PropagateVolumeSelection(0)
            except Exception as selection_err:
                logging.warning(f"Could not propagate volume selection: {selection_err}")

        if slicer.app.layoutManager() is not None:
            try:
                slicer.app.layoutManager().setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)
            except Exception as layout_err:
                logging.warning(f"Could not set layout to FourUpView: {layout_err}")
            slicer.util.resetSliceViews()
        
        # 6. Apply Brain Window
        try:
            self.logic.setBrainWindow()
        except Exception as e:
            logging.debug(f"Could not auto-set brain window: {e}")
            
        # 7. Load notes/flag if sidecar exists
        self.loadNotesSidecar(case)
        
        # 8. Refresh Segment Volumes immediately on load
        self.onRefreshSegmentVolumes()
            
        self.currentLoadedCaseIndex = caseIndex
        self.batchProgressBar.value = caseIndex + 1
        
        # Save to QSettings
        settings = qt.QSettings()
        settings.setValue("SlicerHemorrhageTools/BatchLastCaseIndex", caseIndex)
        
        self.updateStatus(f"Loaded case {caseIndex + 1}/{len(self.matchedCases)}: {case['caseName']}")
        self.batchStatusLabel.text = f"Active case: {caseIndex + 1}/{len(self.matchedCases)} - {case['caseName']}"

        # 9. Switch to Segment Editor to pull up the editor and slice viewers
        slicer.util.selectModule("SegmentEditor")

    def onSaveAndLoadNext(self):
        # Toggle trace satellites checkbox OFF when Alt+n is pressed
        if hasattr(self, "traceSatellitesCheckBox") and self.traceSatellitesCheckBox.isChecked():
            self.traceSatellitesCheckBox.setChecked(False)

        if not self.matchedCases:
            return

        caseIndex = self.caseComboBox.currentIndex
        if caseIndex < 0 or caseIndex >= len(self.matchedCases):
            return
            
        if not self.saveCurrentSegmentation():
            return
            
        # Load next case if available
        nextIndex = caseIndex + 1
        if nextIndex < len(self.matchedCases):
            self.caseComboBox.setCurrentIndex(nextIndex)
            self.onLoadCase()
        else:
            self.batchStatusLabel.text = f"Batch finished! Saved {len(self.matchedCases)} cases."
            self.batchProgressBar.value = len(self.matchedCases)
            slicer.util.infoDisplay("Batch processing complete! All cases saved.")

    def setupShortcuts(self):
        for shortcut in self.shortcuts.values():
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts = {}

        self.loadShortcuts()

        self.addShortcutForAction("Brush Smaller", lambda: self.onAdjustBrush(-1.0))
        self.addShortcutForAction("Brush Larger", lambda: self.onAdjustBrush(1.0))
        self.addShortcutForAction("Paint Range 1 (High)", lambda: self.onSetMode("Paint", "high"))
        self.addShortcutForAction("Erase Range 2 (Low)", lambda: self.onSetMode("Erase", "low"))
        self.addShortcutForAction("Paint Range 2 (Low)", lambda: self.onSetMode("Paint", "low"))
        self.addShortcutForAction("Erase Range 1 (High)", lambda: self.onSetMode("Erase", "high"))
        self.addShortcutForAction("Toggle Segmentation Visibility", self.onToggleSegmentationVisibility)
        self.addShortcutForAction("Toggle Editable Intensity Mask", self.onToggleMask)
        self.addShortcutForAction("Dilate Active Segment", self.onPerformDilate)
        self.addShortcutForAction("Erode Active Segment", self.onPerformErode)
        self.addShortcutForAction("Save & Load Next", self.onSaveAndLoadNext)
        self.addShortcutForAction("Refresh Segment Volumes", self.onRefreshSegmentVolumes)
        self.addShortcutForAction("Deactivate Active Effect", self.onDeactivateActiveEffect)

        # Register global switcher shortcuts
        self.registerGlobalShortcut(
            "Switch to Segment Editor",
            self.customShortcuts.get("Switch to Segment Editor", ""),
            self.onSwitchToSegmentEditor
        )
        self.registerGlobalShortcut(
            "Switch to Hemorrhage Tools",
            self.customShortcuts.get("Switch to Hemorrhage Tools", ""),
            lambda: slicer.util.selectModule("SlicerHemorrhageTools")
        )
        self.registerGlobalShortcut(
            "Switch to Hemorrhage Morphology",
            self.customShortcuts.get("Switch to Hemorrhage Morphology", ""),
            lambda: slicer.util.selectModule("SlicerMorphology")
        )

        # Update button labels to show custom shortcuts
        self.updateButtonShortcutLabels()

        # Update shortcut enabled/disabled states immediately
        self.updateShortcutsState()

        # Log registered shortcuts with their keys
        try:
            registered = {}
            for action, shortcut in self.shortcuts.items():
                try:
                    registered[action] = shortcut.key.toString()
                except Exception:
                    registered[action] = "Unknown"
            print(f"HTools: Registered shortcuts: {registered}")
        except Exception as e:
            print(f"HTools debug print failed: {e}")

        # Scan for potential conflicts on the main window
        try:
            mainWindow = slicer.util.mainWindow()
            if mainWindow:
                shortcuts = mainWindow.findChildren(qt.QShortcut)
                for sc in shortcuts:
                    # Ignore our own shortcuts
                    if sc in self.shortcuts.values():
                        continue
                    seq = sc.key.toString()
                    if seq in ["1", "2", "3", "4", "Escape", "v", "m", "d", "e", "r"]:
                        print(f"HTools WARNING: Conflicting shortcut '{seq}' found on main window! Parent: {sc.parent().className() if sc.parent() else 'None'}, Enabled: {sc.isEnabled()}")
        except Exception as e:
            print(f"HTools conflict check failed: {e}")

    def registerGlobalShortcut(self, actionName, keySequence, callback):
        if not hasattr(slicer, "hemorrhageModuleShortcuts"):
            slicer.hemorrhageModuleShortcuts = {}
        if actionName in slicer.hemorrhageModuleShortcuts:
            oldShortcut = slicer.hemorrhageModuleShortcuts[actionName]
            try:
                oldShortcut.setEnabled(False)
                oldShortcut.deleteLater()
            except Exception:
                pass
            del slicer.hemorrhageModuleShortcuts[actionName]
        if keySequence:
            shortcut = qt.QShortcut(qt.QKeySequence(keySequence), slicer.util.mainWindow())
            shortcut.setContext(qt.Qt.ApplicationShortcut)
            shortcut.activated.connect(callback)
            slicer.hemorrhageModuleShortcuts[actionName] = shortcut

    def addShortcutForAction(self, actionName, callback):
        keySequence = self.customShortcuts.get(actionName, "")
        if not keySequence:
            return
        shortcut = self.addShortcut(keySequence, callback)
        if shortcut:
            self.shortcuts[actionName] = shortcut

    def addShortcut(self, keySequence, callback):
        shortcut = qt.QShortcut(qt.QKeySequence(keySequence), slicer.util.mainWindow())
        shortcut.setContext(qt.Qt.ApplicationShortcut)
        shortcut.activated.connect(callback)
        return shortcut

    def updateShortcutsState(self, oldWidget=None, newWidget=None):
        try:
            if not hasattr(self, "shortcuts") or not self.shortcuts:
                return

            activeModule = slicer.util.selectedModule()
            isInAllowedModule = activeModule in ["SegmentEditor", "SlicerHemorrhageTools"]

            focusWidget = qt.QApplication.focusWidget()
            isTextInputFocused = False
            if focusWidget:
                try:
                    className = focusWidget.metaObject().className()
                    # Exclude spinboxes and comboboxes to prevent focus-stickiness from disabling shortcuts
                    textClasses = ["QLineEdit", "QTextEdit", "QPlainTextEdit", "ctkSearchBox"]
                    isTextInputFocused = (
                        isinstance(focusWidget, (qt.QLineEdit, qt.QTextEdit, qt.QPlainTextEdit)) or
                        any(cls in className for cls in textClasses) or
                        any(term in className for term in ["LineEdit", "TextEdit", "SearchBox", "Console", "Terminal"])
                    )
                except Exception:
                    pass

            shouldEnableActions = isInAllowedModule and not isTextInputFocused

            # Check if there is an active effect in Segment Editor
            hasActiveEffect = False
            try:
                editorWidget = self.logic.segmentEditorWidget()
                if editorWidget:
                    effect = editorWidget.activeEffect()
                    if effect and getattr(effect, "name", lambda: "")() != "":
                        hasActiveEffect = True
            except Exception as e:
                # Log active effect check errors if any
                logging.debug(f"HTools activeEffect error: {e}")

            for actionName, shortcut in self.shortcuts.items():
                try:
                    if actionName == "Deactivate Active Effect":
                        shortcut.setEnabled(shouldEnableActions and hasActiveEffect)
                    else:
                        shortcut.setEnabled(shouldEnableActions)
                except Exception:
                    pass

            # Print state changes to Slicer's Python Console to assist with debugging
            if not hasattr(self, "lastShortcutsState"):
                self.lastShortcutsState = None
            currentState = (isInAllowedModule, isTextInputFocused, hasActiveEffect)
            if currentState != self.lastShortcutsState:
                self.lastShortcutsState = currentState
                print(f"HTools: Shortcut state: allowed_module={isInAllowedModule}, text_focused={isTextInputFocused}, active_effect={hasActiveEffect} -> shortcuts_enabled={shouldEnableActions}")
        except Exception:
            pass

    def onToggleSegmentationVisibility(self):
        try:
            self.logic.toggleSegmentationVisibility()
            self.updateStatus()
        except Exception as exc:
            self.reportError(exc)

    def cleanNodeName(self, name):
        name = name.strip()
        if not name:
            return ""
        # Replace characters that are invalid in Slicer MRML node names or file paths
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '&', '%', '$', '#', '@']
        for char in invalid_chars:
            name = name.replace(char, "_")
        return name

    def onRenameSegmentation(self):
        try:
            editorWidget = self.logic.segmentEditorWidget()
            segmentationNode = editorWidget.segmentationNode()
        except Exception:
            segmentationNode = None

        if not segmentationNode:
            segmentationNodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
            if segmentationNodes:
                segmentationNode = segmentationNodes[0]

        if segmentationNode:
            rawName = self.renameSegmentationLineEdit.text.strip()
            if not rawName:
                # Revert to current name
                self.renameSegmentationLineEdit.text = segmentationNode.GetName()
                self.updateStatus("Rename aborted: Name cannot be empty.")
                return
                
            newName = self.cleanNodeName(rawName)
            if not newName:
                self.renameSegmentationLineEdit.text = segmentationNode.GetName()
                self.updateStatus("Rename aborted: Name contained only invalid characters.")
                return
                
            if newName != rawName:
                self.renameSegmentationLineEdit.text = newName
                
            if newName != segmentationNode.GetName():
                segmentationNode.SetName(newName)
                self.updateStatus(f"Renamed segmentation to: {newName}")

    def onPerformDilate(self):
        try:
            marginSize = self.marginSizeSpinBox.value
            maskMode = self.marginMaskingComboBox.itemData(self.marginMaskingComboBox.currentIndex)
            if maskMode == "default":
                maskMode = "range1"
            range1 = self.huRange("high", validate=False)
            range2 = self.huRange("low", validate=False)
            self.logic.performMarginOperation(marginSize, maskMode, range1, range2)
            self.updateStatus(f"Dilated active segment by {marginSize} mm.")
        except Exception as exc:
            self.reportError(exc)

    def onPerformErode(self):
        try:
            marginSize = self.marginSizeSpinBox.value
            maskMode = self.marginMaskingComboBox.itemData(self.marginMaskingComboBox.currentIndex)
            if maskMode == "default":
                maskMode = "range2"
            range1 = self.huRange("high", validate=False)
            range2 = self.huRange("low", validate=False)
            self.logic.performMarginOperation(-marginSize, maskMode, range1, range2)
            self.updateStatus(f"Eroded active segment by {marginSize} mm.")
        except Exception as exc:
            self.reportError(exc)

    def updateSegmentVisibilityList(self):
        segmentationNode = None
        displayNode = None
        try:
            editorWidget = self.logic.segmentEditorWidget()
            segmentationNode = editorWidget.segmentationNode()
        except Exception:
            pass

        if not segmentationNode:
            segmentationNodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
            if segmentationNodes:
                segmentationNode = segmentationNodes[0]

        if segmentationNode:
            displayNode = segmentationNode.GetDisplayNode()
            if not displayNode:
                segmentationNode.CreateDefaultDisplayNodes()
                displayNode = segmentationNode.GetDisplayNode()

        currentSegments = []
        if segmentationNode:
            segmentation = segmentationNode.GetSegmentation()
            for i in range(segmentation.GetNumberOfSegments()):
                segmentId = segmentation.GetNthSegmentID(i)
                segment = segmentation.GetSegment(segmentId)
                currentSegments.append((segmentId, segment.GetName()))

        currentSegmentIds = [s[0] for s in currentSegments]
        if currentSegmentIds != self.displayedSegmentIds:
            self.rebuildSegmentsUi(currentSegments)
            self.displayedSegmentIds = currentSegmentIds

        if displayNode:
            for segmentId, checkbox in self.segmentCheckboxes.items():
                if segmentId == "_empty":
                    continue
                visible = displayNode.GetSegmentVisibility(segmentId)
                checkbox.blockSignals(True)
                checkbox.setChecked(visible)
                checkbox.blockSignals(False)

    def rebuildSegmentsUi(self, currentSegments):
        for widget in list(self.segmentCheckboxes.values()):
            self.segmentsLayout.removeWidget(widget)
            widget.deleteLater()
        self.segmentCheckboxes = {}

        if not currentSegments:
            noSegmentsLabel = qt.QLabel("No segments in active segmentation.")
            self.segmentsLayout.addWidget(noSegmentsLabel)
            self.segmentCheckboxes["_empty"] = noSegmentsLabel
            return

        for segmentId, segmentName in currentSegments:
            checkbox = qt.QCheckBox(segmentName)
            checkbox.stateChanged.connect(lambda state, sId=segmentId: self.onSegmentVisibilityChanged(sId, state))
            self.segmentsLayout.addWidget(checkbox)
            self.segmentCheckboxes[segmentId] = checkbox

    def onSegmentVisibilityChanged(self, segmentId, state):
        try:
            segmentationNode = None
            try:
                editorWidget = self.logic.segmentEditorWidget()
                segmentationNode = editorWidget.segmentationNode()
            except Exception:
                pass

            if not segmentationNode:
                segmentationNodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
                if segmentationNodes:
                    segmentationNode = segmentationNodes[0]

            if not segmentationNode:
                return

            displayNode = segmentationNode.GetDisplayNode()
            if not displayNode:
                segmentationNode.CreateDefaultDisplayNodes()
                displayNode = segmentationNode.GetDisplayNode()
            if displayNode:
                displayNode.SetSegmentVisibility(segmentId, state == qt.Qt.Checked)
        except Exception as exc:
            self.reportError(exc)

    def createHuSpinBox(self, value):
        spinBox = qt.QSpinBox()
        spinBox.minimum = -1024
        spinBox.maximum = 3071
        spinBox.value = value
        spinBox.suffix = " HU"
        spinBox.valueChanged.connect(lambda unusedValue: self.updateButtonShortcutLabels())
        return spinBox

    def createRangeLayout(self, minimumSpinBox, maximumSpinBox):
        layout = qt.QHBoxLayout()
        layout.addWidget(minimumSpinBox)
        layout.addWidget(qt.QLabel("to"))
        layout.addWidget(maximumSpinBox)
        return layout

    def updateButtonShortcutLabels(self):
        # Update Brush buttons
        brushSmallerKey = self.customShortcuts.get("Brush Smaller", "")
        brushLargerKey = self.customShortcuts.get("Brush Larger", "")
        self.brushSmallerButton.text = f"Brush Smaller ({brushSmallerKey})" if brushSmallerKey else "Brush Smaller"
        self.brushLargerButton.text = f"Brush Larger ({brushLargerKey})" if brushLargerKey else "Brush Larger"

        # Update Mask and Segmentation Visibility buttons
        maskKey = self.customShortcuts.get("Toggle Editable Intensity Mask", "")
        self.maskToggleButton.text = f"Editable Intensity On/Off ({maskKey})" if maskKey else "Editable Intensity On/Off"
        
        segVisKey = self.customShortcuts.get("Toggle Segmentation Visibility", "")
        self.toggleSegmentationVisibilityButton.text = f"Toggle Segmentation Visibility ({segVisKey})" if segVisKey else "Toggle Segmentation Visibility"

        # Update Save & Load Next button
        saveNextKey = self.customShortcuts.get("Save & Load Next", "")
        self.saveLoadNextButton.text = f"Save & Load Next ({saveNextKey})" if saveNextKey else "Save & Load Next"

        # Update Dilate and Erode buttons
        dilateKey = self.customShortcuts.get("Dilate Active Segment", "")
        erodeKey = self.customShortcuts.get("Erode Active Segment", "")
        self.dilateButton.text = f"Dilate Active Segment ({dilateKey})" if dilateKey else "Dilate Active Segment"
        self.erodeButton.text = f"Erode Active Segment ({erodeKey})" if erodeKey else "Erode Active Segment"

        # Update Refresh Volumes button
        refreshKey = self.customShortcuts.get("Refresh Segment Volumes", "")
        if hasattr(self, "refreshVolumesButton"):
            self.refreshVolumesButton.text = f"Refresh Segment Volumes ({refreshKey})" if refreshKey else "Refresh Segment Volumes"

        # Update switcher buttons if they exist
        if hasattr(self, "btnEditor") and hasattr(self, "btnTools") and hasattr(self, "btnMorphology"):
            keyEditor = self.customShortcuts.get("Switch to Segment Editor", "")
            keyTools = self.customShortcuts.get("Switch to Hemorrhage Tools", "")
            keyMorph = self.customShortcuts.get("Switch to Hemorrhage Morphology", "")
            self.btnEditor.text = f"Segment Editor ({keyEditor})" if keyEditor else "Segment Editor"
            self.btnTools.text = f"Hemorrhage Tools ({keyTools})" if keyTools else "Hemorrhage Tools"
            self.btnMorphology.text = f"Hemorrhage Morphology ({keyMorph})" if keyMorph else "Hemorrhage Morphology"

        # Update HU range mode buttons
        self.updateModeButtonLabels()

    def updateModeButtonLabels(self):
        highMinimum, highMaximum = self.huRange("high", validate=False)
        lowMinimum, lowMaximum = self.huRange("low", validate=False)
        
        paintHighKey = self.customShortcuts.get("Paint Range 1 (High)", "")
        eraseLowKey = self.customShortcuts.get("Erase Range 2 (Low)", "")
        paintLowKey = self.customShortcuts.get("Paint Range 2 (Low)", "")
        eraseHighKey = self.customShortcuts.get("Erase Range 1 (High)", "")

        self.paintHighButton.text = f"Paint {highMinimum}-{highMaximum} HU ({paintHighKey})" if paintHighKey else f"Paint {highMinimum}-{highMaximum} HU"
        self.eraseLowButton.text = f"Erase {lowMinimum}-{lowMaximum} HU ({eraseLowKey})" if eraseLowKey else f"Erase {lowMinimum}-{lowMaximum} HU"
        self.paintLowButton.text = f"Paint {lowMinimum}-{lowMaximum} HU ({paintLowKey})" if paintLowKey else f"Paint {lowMinimum}-{lowMaximum} HU"
        self.eraseHighButton.text = f"Erase {highMinimum}-{highMaximum} HU ({eraseHighKey})" if eraseHighKey else f"Erase {highMinimum}-{highMaximum} HU"

    def onSetBrainWindow(self):
        try:
            self.logic.setBrainWindow()
            self.updateStatus("Brain window set to W/L 80/40.")
        except Exception as exc:
            self.reportError(exc)

    def onOpenSegmentEditor(self):
        slicer.util.selectModule("SegmentEditor")
        self.observeSegmentEditorNode()
        self.updateStatus()

    def onSetMode(self, effectName, rangeName):
        try:
            minimumHu, maximumHu = self.huRange(rangeName)
            overwriteMode = self.overwriteModeComboBox.itemData(self.overwriteModeComboBox.currentIndex)
            self.logic.setSegmentEditorMode(effectName, minimumHu, maximumHu, overwriteMode)
            self.syncOverwriteModeFromNode()
            self.updateStatus()
        except Exception as exc:
            self.reportError(exc)

    def huRange(self, rangeName, validate=True):
        if rangeName == "high":
            minimumHu = self.highMinimumSpinBox.value
            maximumHu = self.highMaximumSpinBox.value
        else:
            minimumHu = self.lowMinimumSpinBox.value
            maximumHu = self.lowMaximumSpinBox.value

        if validate and minimumHu > maximumHu:
            raise RuntimeError("HU range minimum must be less than or equal to maximum.")
        return minimumHu, maximumHu

    def onAdjustBrush(self, deltaMm):
        try:
            self.logic.adjustBrushSize(deltaMm)
            self.updateStatus()
        except Exception as exc:
            self.reportError(exc)

    def onToggleMask(self):
        try:
            self.logic.toggleIntensityMask()
            self.updateStatus()
        except Exception as exc:
            self.reportError(exc)

    def onDeactivateActiveEffect(self):
        try:
            editorWidget = self.logic.segmentEditorWidget()
            editorWidget.setActiveEffectByName("")
            self.updateStatus()
        except Exception as exc:
            self.reportError(exc)

    def onRefreshSegmentVolumes(self):
        try:
            # Apply automatic cleanup if enabled
            if hasattr(self, "cleanupAutoApplyCheckBox") and self.cleanupAutoApplyCheckBox.isChecked():
                self.applySatelliteCleanupInternal()

            self.segmentVolumesTextEdit.setPlainText(self.logic.segmentVolumesText())
            # Parse volumes and extract PHE/Hematoma Ratio
            text = self.segmentVolumesTextEdit.toPlainText()
            ratio = "N/A"
            for line in text.split("\n"):
                if "PHE/Hematoma ratio:" in line:
                    ratio = line.split(":", 1)[1].strip()
                    break
            self.ratioLabel.text = ratio

            # Update satellite connection markups
            self.updateSatelliteMarkups()

            self.updateStatus()
        except Exception as exc:
            self.reportError(exc)

    def onCleanupSettingsChanged(self):
        try:
            qt.QSettings().setValue("SlicerHemorrhageTools/CleanupSizeEnabled", "true" if self.cleanupSizeCheckBox.isChecked() else "false")
            qt.QSettings().setValue("SlicerHemorrhageTools/CleanupSizeLimit", self.cleanupSizeSpinBox.value)
            qt.QSettings().setValue("SlicerHemorrhageTools/CleanupDistanceEnabled", "true" if self.cleanupDistanceCheckBox.isChecked() else "false")
            qt.QSettings().setValue("SlicerHemorrhageTools/CleanupDistanceLimit", self.cleanupDistanceSpinBox.value)
            qt.QSettings().setValue("SlicerHemorrhageTools/CleanupAutoApply", "true" if self.cleanupAutoApplyCheckBox.isChecked() else "false")
        except Exception as exc:
            self.reportError(exc)

    def onApplyCleanup(self):
        try:
            success = self.applySatelliteCleanupInternal()
            if success:
                self.onRefreshSegmentVolumes()
                self.updateStatus("Satellite cleanup applied successfully.")
            else:
                self.updateStatus("No cleanup filters were enabled or segment is empty.")
        except Exception as exc:
            self.reportError(exc)

    def applySatelliteCleanupInternal(self):
        cleanSizeEnabled = self.cleanupSizeCheckBox.isChecked()
        sizeLimitMl = self.cleanupSizeSpinBox.value
        cleanDistEnabled = self.cleanupDistanceCheckBox.isChecked()
        distLimitMm = self.cleanupDistanceSpinBox.value

        if not cleanSizeEnabled and not cleanDistEnabled:
            return False

        success = self.logic.applySatelliteCleanup(
            cleanSizeEnabled=cleanSizeEnabled,
            sizeLimitMl=sizeLimitMl,
            cleanDistEnabled=cleanDistEnabled,
            distLimitMm=distLimitMm
        )
        return success

    def onTraceSatellitesToggle(self, state):
        try:
            qt.QSettings().setValue("SlicerHemorrhageTools/TraceSatellites", "true" if self.traceSatellitesCheckBox.isChecked() else "false")
            self.onRefreshSegmentVolumes()
        except Exception as exc:
            self.reportError(exc)

    def clearSatelliteMarkups(self):
        nodes = slicer.util.getNodesByClass("vtkMRMLMarkupsLineNode")
        for node in nodes:
            name = node.GetName()
            if name.startswith("HTools_Satellite_Line_") or name.startswith("HTools_Satellite_Line_2D_"):
                slicer.mrmlScene.RemoveNode(node)

    def updateSatelliteMarkups(self):
        self.clearSatelliteMarkups()

        if not hasattr(self, "traceSatellitesCheckBox") or not self.traceSatellitesCheckBox.isChecked():
            self.satellitesLabel.text = "Disabled"
            return

        result = self.logic.computeSatelliteConnections()
        if result is None:
            self.satellitesLabel.text = "N/A (No active segment or volume)"
            return

        mode, num_satellites, min_dist, satellites_info = result
        if num_satellites == 0:
            self.satellitesLabel.text = "0 satellites (1 component)"
            return

        for idx, sat in enumerate(satellites_info):
            lineNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsLineNode")
            prefix = "HTools_Satellite_Line_2D_" if mode == "2d" else "HTools_Satellite_Line_"
            lineNode.SetName(f"{prefix}{idx+1}")

            p1 = sat["main_closest_point_ras"]
            p2 = sat["sat_closest_point_ras"]

            lineNode.AddControlPoint(p1[0], p1[1], p1[2], "Main Body")
            lineNode.AddControlPoint(p2[0], p2[1], p2[2], f"Satellite {idx+1}")

            lineNode.CreateDefaultDisplayNodes()
            displayNode = lineNode.GetDisplayNode()
            if displayNode:
                if mode == "2d":
                    # Cyan color for 2D slice gaps
                    displayNode.SetSelectedColor(0.0, 0.8, 1.0)
                    displayNode.SetColor(0.0, 0.8, 1.0)
                else:
                    # Orange color for 3D satellites
                    displayNode.SetSelectedColor(1.0, 0.5, 0.0)
                    displayNode.SetColor(1.0, 0.5, 0.0)
                try:
                    displayNode.SetSliceProjection(True)
                    if hasattr(displayNode, "SetProjectedOpacity"):
                        displayNode.SetProjectedOpacity(0.7)
                    displayNode.SetGlyphScale(1.5)
                    displayNode.SetTextScale(1.5)
                except Exception as style_err:
                    logging.debug(f"Could not apply all display styles: {style_err}")

        distances = [sat["min_bound_dist"] for sat in satellites_info]
        if distances:
            min_dist = min(distances)
            max_dist = max(distances)

            if mode == "2d":
                if num_satellites == 1:
                    self.satellitesLabel.text = f"0 satellites (2D Slice Gap: {min_dist:.1f} mm)"
                else:
                    self.satellitesLabel.text = f"0 satellites (2D Gaps: Closest {min_dist:.1f} mm, Furthest {max_dist:.1f} mm)"
            else:
                if num_satellites == 1:
                    self.satellitesLabel.text = f"1 satellite (Distance: {min_dist:.1f} mm)"
                else:
                    self.satellitesLabel.text = f"{num_satellites} satellites (Closest: {min_dist:.1f} mm, Furthest: {max_dist:.1f} mm)"
        else:
            self.satellitesLabel.text = "0 satellites (1 component)"

    def onOverwriteModeChanged(self):
        if self.updatingOverwriteMode:
            return

        try:
            overwriteMode = self.overwriteModeComboBox.itemData(self.overwriteModeComboBox.currentIndex)
            self.logic.setOverwriteMode(overwriteMode)
            self.updateStatus()
        except Exception as exc:
            self.reportError(exc)

    def updateStatus(self, message=None):
        if self.updatingStatus:
            return

        self.updatingStatus = True
        try:
            self.updateShortcutsState()
            self.observeSegmentEditorNode()
            self.observeSegmentationNode()
            self.updateValidationState()
            self.syncOverwriteModeFromNode()
            self.updateSegmentVisibilityList()

            # Update rename text box
            try:
                editorWidget = self.logic.segmentEditorWidget()
                segmentationNode = editorWidget.segmentationNode()
            except Exception:
                segmentationNode = None

            if not segmentationNode:
                segmentationNodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
                if segmentationNodes:
                    segmentationNode = segmentationNodes[0]

            if segmentationNode:
                if not self.renameSegmentationLineEdit.hasFocus():
                    self.renameSegmentationLineEdit.text = segmentationNode.GetName()
                self.renameSegmentationLineEdit.enabled = True
            else:
                if not self.renameSegmentationLineEdit.hasFocus():
                    self.renameSegmentationLineEdit.text = ""
                self.renameSegmentationLineEdit.enabled = False

            status = self.logic.status()
            if message:
                status = f"{message}\n{status}"
            self.statusLabel.text = status
        finally:
            self.updatingStatus = False

    def updateValidationState(self):
        isReady, _message = self.logic.validationState()
        for button in self.workflowButtons:
            button.enabled = isReady

    def observeSegmentEditorNode(self):
        segmentEditorNode = self.logic.segmentEditorNodeOrNone()
        if segmentEditorNode == self.observedSegmentEditorNode:
            return

        if self.observedSegmentEditorNode and self.hasObserver(
            self.observedSegmentEditorNode, vtk.vtkCommand.ModifiedEvent, self.onSegmentEditorNodeModified
        ):
            self.removeObserver(
                self.observedSegmentEditorNode,
                vtk.vtkCommand.ModifiedEvent,
                self.onSegmentEditorNodeModified,
            )

        self.observedSegmentEditorNode = segmentEditorNode
        if not segmentEditorNode:
            return

        self.addObserver(
            segmentEditorNode, vtk.vtkCommand.ModifiedEvent, self.onSegmentEditorNodeModified
        )

    def observeSegmentationNode(self):
        try:
            editorWidget = self.logic.segmentEditorWidget()
            segmentationNode = editorWidget.segmentationNode()
        except Exception:
            segmentationNode = None

        if not segmentationNode:
            segmentationNodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
            if segmentationNodes:
                segmentationNode = segmentationNodes[0]

        if segmentationNode == self.observedSegmentationNode:
            return

        if self.observedSegmentationNode and self.hasObserver(
            self.observedSegmentationNode, vtk.vtkCommand.ModifiedEvent, self.onSegmentationNodeModified
        ):
            self.removeObserver(
                self.observedSegmentationNode,
                vtk.vtkCommand.ModifiedEvent,
                self.onSegmentationNodeModified,
            )

        self.observedSegmentationNode = segmentationNode
        if not segmentationNode:
            return

        self.addObserver(
            segmentationNode, vtk.vtkCommand.ModifiedEvent, self.onSegmentationNodeModified
        )

    def onSegmentEditorNodeModified(self, caller, event):
        self.updateStatus()

    def onSegmentationNodeModified(self, caller, event):
        self.updateStatus()
        if hasattr(self, "volumeRefreshTimer"):
            self.volumeRefreshTimer.start()

    def onSegmentationNodeChanged(self, node):
        self.updateStatus()

    def onNodeAdded(self, caller, event, node=None):
        self.updateStatus()

    def onNodeRemoved(self, caller, event, node=None):
        self.updateStatus()

    def onSceneImported(self, caller, event):
        self.updateStatus()

    def syncOverwriteModeFromNode(self):
        overwriteMode = self.logic.currentOverwriteModeKey()
        index = self.overwriteModeComboBox.findData(overwriteMode)
        if index < 0:
            return

        self.updatingOverwriteMode = True
        self.overwriteModeComboBox.setCurrentIndex(index)
        self.updatingOverwriteMode = False

    def reportError(self, exc):
        logging.exception(exc)
        # Only show dialog if main window exists to avoid headless blocking
        try:
            if slicer.util.mainWindow() is not None:
                slicer.util.errorDisplay(str(exc))
        except Exception:
            pass
        self.updateStatus(f"Error: {exc}")


class SlicerHemorrhageToolsLogic(ScriptedLoadableModuleLogic):
    BRAIN_WINDOW = 80
    BRAIN_LEVEL = 40
    DEFAULT_BRUSH_DIAMETER_MM = 5.0
    MIN_BRUSH_DIAMETER_MM = 0.5

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)
        self.currentMaskRange = None

    def setBrainWindow(self):
        volumeNode = self.backgroundVolumeNode()
        if not volumeNode:
            raise RuntimeError("No background CT volume is selected in the slice viewers.")

        displayNode = volumeNode.GetDisplayNode()
        if not displayNode:
            volumeNode.CreateDefaultDisplayNodes()
            displayNode = volumeNode.GetDisplayNode()

        displayNode.AutoWindowLevelOff()
        displayNode.SetWindow(self.BRAIN_WINDOW)
        displayNode.SetLevel(self.BRAIN_LEVEL)
        slicer.util.setSliceViewerLayers(background=volumeNode, fit=False)

    def setSegmentEditorMode(self, effectName, minimumHu, maximumHu, overwriteMode="none"):
        editorWidget = self.segmentEditorWidget()
        segmentEditorNode = self.segmentEditorNode(editorWidget)

        self.ensureSourceVolume(editorWidget)
        self.requireSegmentEditorContext(editorWidget, segmentEditorNode)
        editorWidget.setActiveEffectByName(effectName)
        if not editorWidget.activeEffect():
            raise RuntimeError(f"Could not activate Segment Editor effect: {effectName}")

        self.setIntensityMask(segmentEditorNode, minimumHu, maximumHu, True)
        self.setOverwriteMode(overwriteMode)
        self.ensureBrushDiameter(editorWidget)

        self.currentMaskRange = (minimumHu, maximumHu)

    def adjustBrushSize(self, deltaMm):
        editorWidget = self.segmentEditorWidget()
        activeEffect = editorWidget.activeEffect()
        if not activeEffect:
            raise RuntimeError("No active Paint or Erase effect. Choose one of the mode buttons first.")

        currentDiameter = self.brushDiameter(activeEffect)
        newDiameter = max(self.MIN_BRUSH_DIAMETER_MM, currentDiameter + deltaMm)
        activeEffect.setParameter("BrushAbsoluteDiameter", str(newDiameter))

    def toggleIntensityMask(self):
        editorWidget = self.segmentEditorWidget()
        segmentEditorNode = self.segmentEditorNode(editorWidget)
        enabled = bool(segmentEditorNode.GetSourceVolumeIntensityMask())

        if not enabled and self.currentMaskRange:
            minimumHu, maximumHu = self.currentMaskRange
            self.setIntensityMask(segmentEditorNode, minimumHu, maximumHu, True)
        else:
            segmentEditorNode.SetSourceVolumeIntensityMask(not enabled)

    def ensureSourceVolume(self, editorWidget):
        if editorWidget.sourceVolumeNode():
            return

        volumeNode = self.backgroundVolumeNode()
        if volumeNode:
            editorWidget.setSourceVolumeNode(volumeNode)

    def validationState(self):
        try:
            editorWidget = self.segmentEditorWidget()
        except Exception:
            return False, "Open Segment Editor once so Slicer can initialize the editor."

        if not editorWidget.segmentationNode():
            return False, "Select a segmentation in Segment Editor first."
        if not editorWidget.sourceVolumeNode() and not self.backgroundVolumeNode():
            return False, "No source volume detected. Please load a CT volume."

        try:
            segmentEditorNode = self.segmentEditorNode(editorWidget)
        except Exception:
            return False, "Segment Editor is not ready yet."

        if not segmentEditorNode.GetSelectedSegmentID():
            return False, "Select or add a segment in Segment Editor first."

        return True, "Ready."

    def segmentVolumesText(self):
        editorWidget = self.segmentEditorWidget()
        segmentationNode = editorWidget.segmentationNode()
        if not segmentationNode:
            segmentationNodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
            if segmentationNodes:
                segmentationNode = segmentationNodes[0]

        if not segmentationNode:
            raise RuntimeError("No segmentation node found. Please load or select a segmentation first.")

        import SegmentStatistics

        statisticsLogic = SegmentStatistics.SegmentStatisticsLogic()
        parameterNode = statisticsLogic.getParameterNode()
        parameterNode.SetParameter("Segmentation", segmentationNode.GetID())

        sourceVolumeNode = editorWidget.sourceVolumeNode() or self.backgroundVolumeNode()
        if sourceVolumeNode:
            parameterNode.SetParameter("ScalarVolume", sourceVolumeNode.GetID())

        statisticsLogic.computeStatistics()
        statistics = statisticsLogic.getStatistics()
        segmentation = segmentationNode.GetSegmentation()
        segmentIds = statistics["SegmentIDs"] if "SegmentIDs" in statistics else [
            segmentation.GetNthSegmentID(index)
            for index in range(segmentation.GetNumberOfSegments())
        ]

        if not segmentIds:
            return "No segments in current segmentation."

        lines = []
        namedVolumesMl = []
        totalMl = 0.0
        for segmentId in segmentIds:
            segment = segmentation.GetSegment(segmentId)
            segmentName = segment.GetName() if segment else segmentId
            volumeMl = self.segmentVolumeMl(statistics, segmentId)

            if volumeMl is None:
                lines.append(f"{segmentName}: volume unavailable")
                continue

            totalMl += volumeMl
            namedVolumesMl.append((segmentName, volumeMl))
            lines.append(f"{segmentName}: {volumeMl:.2f} mL")

        if len(lines) > 1:
            lines.append(f"Total: {totalMl:.2f} mL")
            ratioText = self.pheToHematomaRatioText(namedVolumesMl)
            if ratioText:
                lines.append(ratioText)
        return "\n".join(lines)

    def pheToHematomaRatioText(self, namedVolumesMl):
        hematomaVolumeMl = self.firstMatchingVolume(
            namedVolumesMl,
            ["hematoma", "haematoma", "hemorrhage", "haemorrhage", "ich"],
        )
        pheVolumeMl = self.firstMatchingVolume(
            namedVolumesMl,
            ["phe", "edema", "oedema", "perihematomal", "perihaematomal"],
        )

        if hematomaVolumeMl is None or pheVolumeMl is None:
            return ""
        if hematomaVolumeMl <= 0:
            return "PHE/Hematoma ratio: unavailable (hematoma volume is 0 mL)"

        return f"PHE/Hematoma ratio: {pheVolumeMl / hematomaVolumeMl:.2f}"

    def firstMatchingVolume(self, namedVolumesMl, keywords):
        for segmentName, volumeMl in namedVolumesMl:
            normalizedName = segmentName.lower()
            if any(keyword in normalizedName for keyword in keywords):
                return volumeMl
        return None

    def segmentVolumeMl(self, statistics, segmentId):
        volumeCm3 = self.statisticValue(
            statistics,
            segmentId,
            [
                "LabelmapSegmentStatisticsPlugin.volume_cm3",
                "ClosedSurfaceSegmentStatisticsPlugin.volume_cm3",
            ],
        )
        if volumeCm3 is not None:
            return float(volumeCm3)

        volumeMm3 = self.statisticValue(
            statistics,
            segmentId,
            [
                "LabelmapSegmentStatisticsPlugin.volume_mm3",
                "ClosedSurfaceSegmentStatisticsPlugin.volume_mm3",
            ],
        )
        if volumeMm3 is not None:
            return float(volumeMm3) / 1000.0

        return None

    def statisticValue(self, statistics, segmentId, keys):
        for key in keys:
            if (segmentId, key) in statistics:
                return statistics[segmentId, key]
        return None

    def status(self):
        try:
            editorWidget = self.segmentEditorWidget()
            segmentEditorNode = self.segmentEditorNode(editorWidget)
            activeEffect = editorWidget.activeEffect()
            toolName = self.effectName(activeEffect) if activeEffect else "None"
            maskEnabled = bool(segmentEditorNode.GetSourceVolumeIntensityMask())
            minimumHu, maximumHu = segmentEditorNode.GetSourceVolumeIntensityMaskRange()
            maskText = f"{minimumHu:g}-{maximumHu:g} HU" if maskEnabled else "Off"
            brushText = self.brushStatus(activeEffect)
            overwriteText = self.overwriteStatus(segmentEditorNode)
            segmentText = self.selectedSegmentName(editorWidget, segmentEditorNode)
            isReady, validationMessage = self.validationState()
            return (
                f"Ready: {'Yes' if isReady else 'No'} - {validationMessage}\n"
                f"Tool: {toolName or 'None'}\n"
                f"Segment: {segmentText}\n"
                f"Editable intensity: {maskText}\n"
                f"Overwrite: {overwriteText}\n"
                f"Brush: {brushText}"
            )
        except Exception:
            return "Open Segment Editor and select a source volume, segmentation, and segment."

    def setIntensityMask(self, segmentEditorNode, minimumHu, maximumHu, enabled=True):
        segmentEditorNode.SetSourceVolumeIntensityMask(enabled)
        segmentEditorNode.SetSourceVolumeIntensityMaskRange(float(minimumHu), float(maximumHu))

    def setOverwriteMode(self, overwriteMode):
        editorWidget = self.segmentEditorWidget()
        segmentEditorNode = self.segmentEditorNode(editorWidget)
        segmentEditorNode.SetOverwriteMode(self.overwriteModeValue(overwriteMode))

    def overwriteModeValue(self, overwriteMode):
        if overwriteMode == "visible":
            return getattr(slicer.vtkMRMLSegmentEditorNode, "OverwriteVisibleSegments", 1)
        return getattr(slicer.vtkMRMLSegmentEditorNode, "OverwriteNone", 2)

    def currentOverwriteModeKey(self):
        segmentEditorNode = self.segmentEditorNodeOrNone()
        if not segmentEditorNode:
            return "none"

        overwriteMode = segmentEditorNode.GetOverwriteMode()
        overwriteVisible = getattr(slicer.vtkMRMLSegmentEditorNode, "OverwriteVisibleSegments", 1)
        return "visible" if overwriteMode == overwriteVisible else "none"

    def backgroundVolumeNode(self):
        layoutManager = slicer.app.layoutManager()
        if layoutManager:
            sliceWidget = layoutManager.sliceWidget("Red")
            if sliceWidget:
                volumeNode = sliceWidget.sliceLogic().GetBackgroundLayer().GetVolumeNode()
                if volumeNode:
                    return volumeNode

        return None

    def segmentEditorWidget(self):
        segmentEditorModuleWidget = slicer.util.getModuleWidget("SegmentEditor")
        if hasattr(segmentEditorModuleWidget, "editor"):
            return segmentEditorModuleWidget.editor

        editorWidgets = slicer.util.findChildren(
            segmentEditorModuleWidget, className="qMRMLSegmentEditorWidget"
        )
        if editorWidgets:
            return editorWidgets[0]

        raise RuntimeError("Could not find the Segment Editor widget.")

    def segmentEditorNode(self, editorWidget):
        segmentEditorNode = editorWidget.mrmlSegmentEditorNode()
        if not segmentEditorNode:
            raise RuntimeError("Segment Editor does not have an active parameter node.")
        return segmentEditorNode

    def segmentEditorNodeOrNone(self):
        try:
            return self.segmentEditorNode(self.segmentEditorWidget())
        except Exception:
            return None

    def requireSegmentEditorContext(self, editorWidget, segmentEditorNode):
        if not editorWidget.segmentationNode():
            raise RuntimeError("Select a segmentation in Segment Editor first.")
        if not editorWidget.sourceVolumeNode():
            raise RuntimeError("Select the CT source volume in Segment Editor first.")
        if not segmentEditorNode.GetSelectedSegmentID():
            raise RuntimeError("Select a segment in Segment Editor first.")

    def ensureBrushDiameter(self, editorWidget):
        activeEffect = editorWidget.activeEffect()
        if not activeEffect:
            return
        if self.brushDiameter(activeEffect) <= 0:
            activeEffect.setParameter("BrushAbsoluteDiameter", str(self.DEFAULT_BRUSH_DIAMETER_MM))

    def brushDiameter(self, activeEffect):
        value = activeEffect.parameter("BrushAbsoluteDiameter")
        try:
            return float(value)
        except (TypeError, ValueError):
            return self.DEFAULT_BRUSH_DIAMETER_MM

    def brushStatus(self, activeEffect):
        if not activeEffect:
            return "No active brush"
        return f"{self.brushDiameter(activeEffect):g} mm"

    def effectName(self, activeEffect):
        name = getattr(activeEffect, "name", None)
        return name() if callable(name) else name

    def overwriteStatus(self, segmentEditorNode):
        overwriteMode = segmentEditorNode.GetOverwriteMode()
        overwriteNone = getattr(slicer.vtkMRMLSegmentEditorNode, "OverwriteNone", 2)
        overwriteVisible = getattr(slicer.vtkMRMLSegmentEditorNode, "OverwriteVisibleSegments", 1)
        overwriteAll = getattr(slicer.vtkMRMLSegmentEditorNode, "OverwriteAllSegments", 0)

        if overwriteMode == overwriteNone:
            return "Do not overwrite segments"
        if overwriteMode == overwriteVisible:
            return "Overwrite visible segments"
        if overwriteMode == overwriteAll:
            return "Overwrite all segments"
        return f"Mode {overwriteMode}"

    def selectedSegmentName(self, editorWidget, segmentEditorNode):
        segmentId = segmentEditorNode.GetSelectedSegmentID()
        if not segmentId:
            return "None"

        segmentationNode = editorWidget.segmentationNode()
        if not segmentationNode:
            return segmentId

        segment = segmentationNode.GetSegmentation().GetSegment(segmentId)
        return segment.GetName() if segment else segmentId

    def toggleSegmentationVisibility(self):
        segmentationNode = None
        try:
            editorWidget = self.segmentEditorWidget()
            segmentationNode = editorWidget.segmentationNode()
        except Exception:
            pass

        if not segmentationNode:
            segmentationNodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
            if segmentationNodes:
                segmentationNode = segmentationNodes[0]

        if not segmentationNode:
            raise RuntimeError("No segmentation node found. Please load or select a segmentation first.")

        displayNode = segmentationNode.GetDisplayNode()
        if not displayNode:
            segmentationNode.CreateDefaultDisplayNodes()
            displayNode = segmentationNode.GetDisplayNode()
        if not displayNode:
            raise RuntimeError("Segmentation node does not have a display node.")
        displayNode.SetVisibility(not displayNode.GetVisibility())

    def performMarginOperation(self, marginSizeMm, maskMode="none", range1=None, range2=None):
        editorWidget = self.segmentEditorWidget()
        segmentEditorNode = self.segmentEditorNode(editorWidget)
        self.requireSegmentEditorContext(editorWidget, segmentEditorNode)

        # Save previous active effect name and mask settings
        previousEffect = editorWidget.activeEffect()
        previousEffectName = self.effectName(previousEffect) if previousEffect else None

        prevMaskEnabled = bool(segmentEditorNode.GetSourceVolumeIntensityMask())
        prevMin, prevMax = segmentEditorNode.GetSourceVolumeIntensityMaskRange()

        # Configure masking based on maskMode
        if maskMode == "range1" and range1:
            self.setIntensityMask(segmentEditorNode, range1[0], range1[1], True)
        elif maskMode == "range2" and range2:
            self.setIntensityMask(segmentEditorNode, range2[0], range2[1], True)
        elif maskMode == "none":
            segmentEditorNode.SetSourceVolumeIntensityMask(False)
        # if maskMode == "current", we keep the current settings as is

        # Activate the Margin effect
        editorWidget.setActiveEffectByName("Margin")
        marginEffect = editorWidget.activeEffect()
        if not marginEffect:
            raise RuntimeError("Could not find the 'Margin' effect in Segment Editor.")

        try:
            # Set parameters
            marginEffect.setParameter("MarginSizeMm", str(marginSizeMm))
            marginEffect.setParameter("ApplyToAllVisibleSegments", "0") # 0 for selected only, 1 for all

            # Apply
            marginEffect.self().onApply()
        finally:
            # Restore masking state
            segmentEditorNode.SetSourceVolumeIntensityMask(prevMaskEnabled)
            segmentEditorNode.SetSourceVolumeIntensityMaskRange(prevMin, prevMax)

            # Restore active effect
            if previousEffectName:
                editorWidget.setActiveEffectByName(previousEffectName)
            else:
                editorWidget.setActiveEffectByName(None)

    def computeSatelliteConnections(self):
        """
        Computes connected components for the active segment.
        Returns:
            (mode, num_satellites, min_dist, satellites_info) or None
            where mode is "3d" or "2d".
        """
        try:
            editorWidget = self.segmentEditorWidget()
            segmentationNode = editorWidget.segmentationNode()
            if not segmentationNode:
                return None

            activeSegmentId = editorWidget.currentSegmentID()
            if not activeSegmentId:
                return None

            segment = segmentationNode.GetSegmentation().GetSegment(activeSegmentId)
            if not segment:
                return None

            # Export active segment to a temporary labelmap
            labelmapNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLLabelMapVolumeNode", f"_tmp_labelmap_{activeSegmentId}"
            )
            segmentIdArray = vtk.vtkStringArray()
            segmentIdArray.InsertNextValue(activeSegmentId)

            sourceVolumeNode = editorWidget.sourceVolumeNode() or self.backgroundVolumeNode()
            if not sourceVolumeNode:
                slicer.mrmlScene.RemoveNode(labelmapNode)
                return None

            slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(
                segmentationNode,
                segmentIdArray,
                labelmapNode,
                sourceVolumeNode,
            )

            import SimpleITK as sitk
            import sitkUtils
            import numpy as np
            import scipy.ndimage as ndimage

            sitkMask = sitkUtils.PullVolumeFromSlicer(labelmapNode)
            mask_arr = sitk.GetArrayFromImage(sitkMask)

            ijkToRas = vtk.vtkMatrix4x4()
            labelmapNode.GetIJKToRASMatrix(ijkToRas)

            slicer.mrmlScene.RemoveNode(labelmapNode)

            if np.sum(mask_arr > 0) == 0:
                return ("3d", 0, 0.0, [])

            spacing = sitkMask.GetSpacing()
            spacing_zyx = (spacing[2], spacing[1], spacing[0])
            voxel_volume_mm3 = spacing[0] * spacing[1] * spacing[2]

            labeled_mask, num_features = ndimage.label(mask_arr > 0)

            def getRasCoords(voxel_zyx, ijkToRasMatrix):
                z, y, x = voxel_zyx
                pos_ijk = [x, y, z, 1.0]
                pos_ras = ijkToRasMatrix.MultiplyPoint(pos_ijk)
                return [pos_ras[0], pos_ras[1], pos_ras[2]]

            if num_features <= 1:
                # 3D is contiguous. Check 2D slice of the active Red viewer.
                layoutManager = slicer.app.layoutManager()
                redWidget = layoutManager.sliceWidget("Red") if layoutManager else None
                if redWidget:
                    sliceLogic = redWidget.sliceLogic()
                    sliceNode = sliceLogic.GetSliceNode()
                    
                    # Convert slice center to RAS
                    sliceToRas = sliceNode.GetSliceToRAS()
                    center_slice = [0.0, 0.0, 0.0, 1.0]
                    center_ras = sliceToRas.MultiplyPoint(center_slice)
                    
                    # Convert RAS to IJK
                    rasToIjk = vtk.vtkMatrix4x4()
                    if sourceVolumeNode:
                        sourceVolumeNode.GetRASToIJKMatrix(rasToIjk)
                    else:
                        return ("3d", 0, 0.0, [])
                    center_ijk = rasToIjk.MultiplyPoint(center_ras)
                    
                    z = int(round(center_ijk[2]))
                    if 0 <= z < mask_arr.shape[0]:
                        slice_2d = mask_arr[z, :, :]
                        if np.sum(slice_2d > 0) > 0:
                            labeled_slice, num_2d_features = ndimage.label(slice_2d > 0)
                            if num_2d_features > 1:
                                # We have disconnected components on this slice
                                component_sizes_2d = []
                                for i in range(1, num_2d_features + 1):
                                    voxels_2d = np.sum(labeled_slice == i)
                                    component_sizes_2d.append((i, voxels_2d))
                                component_sizes_2d.sort(key=lambda x: x[1], reverse=True)
                                
                                main_2d_id = component_sizes_2d[0][0]
                                main_2d_mask = (labeled_slice == main_2d_id)
                                
                                spacing_yx = (spacing[1], spacing[0])
                                edt_2d = ndimage.distance_transform_edt(~main_2d_mask, sampling=spacing_yx)
                                
                                # Surface of main 2D body
                                boundary_mask_2d = main_2d_mask ^ ndimage.binary_erosion(main_2d_mask)
                                main_2d_coords = np.argwhere(boundary_mask_2d)
                                if len(main_2d_coords) == 0:
                                    main_2d_coords = np.argwhere(main_2d_mask)
                                    
                                satellites_info_2d = []
                                min_dist_val_2d = None
                                
                                for comp_id, voxels_2d in component_sizes_2d[1:]:
                                    comp_mask_2d = (labeled_slice == comp_id)
                                    min_bound_dist_2d = float(np.min(edt_2d[comp_mask_2d]))
                                    
                                    if min_dist_val_2d is None or min_bound_dist_2d < min_dist_val_2d:
                                        min_dist_val_2d = min_bound_dist_2d
                                        
                                    sat_edt_2d = np.where(comp_mask_2d, edt_2d, np.inf)
                                    closest_voxel_idx_flat_2d = np.argmin(sat_edt_2d)
                                    closest_voxel_yx = np.unravel_index(closest_voxel_idx_flat_2d, edt_2d.shape)
                                    
                                    diffs_2d = (main_2d_coords - closest_voxel_yx) * spacing_yx
                                    dists_sq_2d = np.sum(diffs_2d**2, axis=1)
                                    closest_main_idx_2d = np.argmin(dists_sq_2d)
                                    main_closest_yx = main_2d_coords[closest_main_idx_2d]
                                    
                                    sat_closest_zyx = [z, closest_voxel_yx[0], closest_voxel_yx[1]]
                                    main_closest_zyx = [z, main_closest_yx[0], main_closest_yx[1]]
                                    
                                    satellites_info_2d.append({
                                        "id": comp_id,
                                        "min_bound_dist": min_bound_dist_2d,
                                        "sat_closest_point_ras": getRasCoords(sat_closest_zyx, ijkToRas),
                                        "main_closest_point_ras": getRasCoords(main_closest_zyx, ijkToRas)
                                    })
                                    
                                num_satellites_2d = num_2d_features - 1
                                return ("2d", num_satellites_2d, min_dist_val_2d, satellites_info_2d)
                
                return ("3d", 0, 0.0, [])

            component_sizes = []
            for i in range(1, num_features + 1):
                voxels = np.sum(labeled_mask == i)
                vol_ml = (voxels * voxel_volume_mm3) / 1000.0
                component_sizes.append((i, voxels, vol_ml))

            component_sizes.sort(key=lambda x: x[1], reverse=True)

            main_body_id = component_sizes[0][0]
            main_body_mask = (labeled_mask == main_body_id)

            # Boundary-to-boundary distance transform
            edt = ndimage.distance_transform_edt(~main_body_mask, sampling=spacing_zyx)

            # Surface coordinates of main body for closest point calculation
            boundary_mask = main_body_mask ^ ndimage.binary_erosion(main_body_mask)
            main_body_coords = np.argwhere(boundary_mask)
            if len(main_body_coords) == 0:
                main_body_coords = np.argwhere(main_body_mask)

            satellites_info = []
            min_dist_val = None

            for comp_id, voxels, vol_ml in component_sizes[1:]:
                comp_mask = (labeled_mask == comp_id)
                min_bound_dist = float(np.min(edt[comp_mask]))

                if min_dist_val is None or min_bound_dist < min_dist_val:
                    min_dist_val = min_bound_dist

                # Closest voxel in the satellite
                satellite_edt = np.where(comp_mask, edt, np.inf)
                closest_voxel_idx_flat = np.argmin(satellite_edt)
                closest_voxel_zyx = np.unravel_index(closest_voxel_idx_flat, edt.shape)
                sat_closest_point_ras = getRasCoords(closest_voxel_zyx, ijkToRas)

                # Closest voxel on the main body surface
                diffs = (main_body_coords - closest_voxel_zyx) * spacing_zyx
                dists_sq = np.sum(diffs**2, axis=1)
                closest_main_body_idx = np.argmin(dists_sq)
                main_closest_point_zyx = main_body_coords[closest_main_body_idx]
                main_closest_point_ras = getRasCoords(main_closest_point_zyx, ijkToRas)

                satellites_info.append({
                    "id": comp_id,
                    "vol_ml": vol_ml,
                    "min_bound_dist": min_bound_dist,
                    "sat_closest_point_ras": sat_closest_point_ras,
                    "main_closest_point_ras": main_closest_point_ras
                })

            num_satellites = num_features - 1
            return ("3d", num_satellites, min_dist_val, satellites_info)

        except Exception as e:
            logging.error(f"Error computing satellite connections: {e}")
            return None

    def applySatelliteCleanup(self, cleanSizeEnabled, sizeLimitMl, cleanDistEnabled, distLimitMm):
        """
        Filters and removes disconnected components from the active segment based on size and/or distance.
        Returns:
            bool: True if cleanup was successfully applied and modified the mask, False otherwise.
        """
        try:
            editorWidget = self.segmentEditorWidget()
            segmentationNode = editorWidget.segmentationNode()
            if not segmentationNode:
                return False

            activeSegmentId = editorWidget.currentSegmentID()
            if not activeSegmentId:
                return False

            segment = segmentationNode.GetSegmentation().GetSegment(activeSegmentId)
            if not segment:
                return False

            # Export active segment to a temporary labelmap
            labelmapNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLLabelMapVolumeNode", f"_tmp_labelmap_{activeSegmentId}"
            )
            segmentIdArray = vtk.vtkStringArray()
            segmentIdArray.InsertNextValue(activeSegmentId)

            sourceVolumeNode = editorWidget.sourceVolumeNode() or self.backgroundVolumeNode()
            if not sourceVolumeNode:
                slicer.mrmlScene.RemoveNode(labelmapNode)
                return False

            slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(
                segmentationNode,
                segmentIdArray,
                labelmapNode,
                sourceVolumeNode,
            )

            import SimpleITK as sitk
            import sitkUtils
            import numpy as np
            import scipy.ndimage as ndimage

            sitkMask = sitkUtils.PullVolumeFromSlicer(labelmapNode)
            mask_arr = sitk.GetArrayFromImage(sitkMask)

            if np.sum(mask_arr > 0) == 0:
                slicer.mrmlScene.RemoveNode(labelmapNode)
                return False

            spacing = sitkMask.GetSpacing()
            spacing_zyx = (spacing[2], spacing[1], spacing[0])
            voxel_volume_mm3 = spacing[0] * spacing[1] * spacing[2]

            labeled_mask, num_features = ndimage.label(mask_arr > 0)
            if num_features <= 1:
                # Only 1 component (main body) exists, nothing to clean
                slicer.mrmlScene.RemoveNode(labelmapNode)
                return False

            component_sizes = []
            for i in range(1, num_features + 1):
                voxels = np.sum(labeled_mask == i)
                vol_ml = (voxels * voxel_volume_mm3) / 1000.0
                component_sizes.append((i, voxels, vol_ml))

            component_sizes.sort(key=lambda x: x[1], reverse=True)

            main_body_id = component_sizes[0][0]
            main_body_mask = (labeled_mask == main_body_id)

            # Calculate distance transform from main body if distance threshold is enabled
            if cleanDistEnabled:
                edt = ndimage.distance_transform_edt(~main_body_mask, sampling=spacing_zyx)

            # Track if we actually delete any components
            anyDeleted = False
            modified_mask = mask_arr.copy()

            for comp_id, voxels, vol_ml in component_sizes[1:]:
                shouldDelete = False
                comp_mask = (labeled_mask == comp_id)

                if cleanSizeEnabled and vol_ml <= sizeLimitMl:
                    shouldDelete = True

                if cleanDistEnabled:
                    min_bound_dist = float(np.min(edt[comp_mask]))
                    if min_bound_dist >= distLimitMm:
                        shouldDelete = True

                if shouldDelete:
                    modified_mask[comp_mask] = 0
                    anyDeleted = True

            if not anyDeleted:
                slicer.mrmlScene.RemoveNode(labelmapNode)
                return False

            # Push the modified numpy mask back to SimpleITK and Slicer
            filtered_mask = sitk.GetImageFromArray(modified_mask)
            filtered_mask.SetSpacing(sitkMask.GetSpacing())
            filtered_mask.SetOrigin(sitkMask.GetOrigin())
            filtered_mask.SetDirection(sitkMask.GetDirection())
            
            # Update labelmapNode from SimpleITK image
            sitkUtils.PushVolumeToSlicer(filtered_mask, labelmapNode)

            # Import the labelmap back to overwrite the active segment!
            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
                labelmapNode,
                segmentationNode,
                segmentIdArray
            )

            slicer.mrmlScene.RemoveNode(labelmapNode)
            return True

        except Exception as e:
            logging.error(f"Error applying satellite cleanup: {e}")
            if 'labelmapNode' in locals():
                slicer.mrmlScene.RemoveNode(labelmapNode)
            return False
