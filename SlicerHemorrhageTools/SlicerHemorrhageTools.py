import logging

import ctk
import qt
import slicer
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic,
)


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


class SlicerHemorrhageToolsWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        self.logic = SlicerHemorrhageToolsLogic()

        self._buildUi()
        self.updateStatus()

    def _buildUi(self):
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

        self.highMinimumSpinBox = self.createHuSpinBox(40)
        self.highMaximumSpinBox = self.createHuSpinBox(80)
        self.lowMinimumSpinBox = self.createHuSpinBox(5)
        self.lowMaximumSpinBox = self.createHuSpinBox(33)

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

        brushLayout = qt.QHBoxLayout()
        brushSmallerButton = qt.QPushButton("Brush Smaller")
        brushLargerButton = qt.QPushButton("Brush Larger")
        brushSmallerButton.toolTip = "Decrease Paint/Erase brush diameter."
        brushLargerButton.toolTip = "Increase Paint/Erase brush diameter."
        brushSmallerButton.clicked.connect(lambda: self.onAdjustBrush(-1.0))
        brushLargerButton.clicked.connect(lambda: self.onAdjustBrush(1.0))
        brushLayout.addWidget(brushSmallerButton)
        brushLayout.addWidget(brushLargerButton)
        formLayout.addRow(brushLayout)

        self.maskToggleButton = qt.QPushButton("Editable Intensity On/Off")
        self.maskToggleButton.toolTip = "Toggle source volume editable intensity masking."
        self.maskToggleButton.clicked.connect(self.onToggleMask)
        formLayout.addRow(self.maskToggleButton)

        self.statusLabel = qt.QLabel()
        self.statusLabel.wordWrap = True
        formLayout.addRow("Status:", self.statusLabel)

        self.layout.addStretch(1)
        self.updateModeButtonLabels()

    def createHuSpinBox(self, value):
        spinBox = qt.QSpinBox()
        spinBox.minimum = -1024
        spinBox.maximum = 3071
        spinBox.value = value
        spinBox.suffix = " HU"
        spinBox.valueChanged.connect(lambda unusedValue: self.updateModeButtonLabels())
        return spinBox

    def createRangeLayout(self, minimumSpinBox, maximumSpinBox):
        layout = qt.QHBoxLayout()
        layout.addWidget(minimumSpinBox)
        layout.addWidget(qt.QLabel("to"))
        layout.addWidget(maximumSpinBox)
        return layout

    def updateModeButtonLabels(self):
        highMinimum, highMaximum = self.huRange("high", validate=False)
        lowMinimum, lowMaximum = self.huRange("low", validate=False)
        self.paintHighButton.text = f"Paint {highMinimum}-{highMaximum} HU"
        self.eraseLowButton.text = f"Erase {lowMinimum}-{lowMaximum} HU"
        self.paintLowButton.text = f"Paint {lowMinimum}-{lowMaximum} HU"
        self.eraseHighButton.text = f"Erase {highMinimum}-{highMaximum} HU"

    def onSetBrainWindow(self):
        try:
            self.logic.setBrainWindow()
            self.updateStatus("Brain window set to W/L 80/40.")
        except Exception as exc:
            self.reportError(exc)

    def onOpenSegmentEditor(self):
        slicer.util.selectModule("SegmentEditor")

    def onSetMode(self, effectName, rangeName):
        try:
            minimumHu, maximumHu = self.huRange(rangeName)
            self.logic.setSegmentEditorMode(effectName, minimumHu, maximumHu)
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

    def updateStatus(self, message=None):
        status = self.logic.status()
        if message:
            status = f"{message}\n{status}"
        self.statusLabel.text = status

    def reportError(self, exc):
        logging.exception(exc)
        slicer.util.errorDisplay(str(exc))
        self.updateStatus(f"Error: {exc}")


class SlicerHemorrhageToolsLogic(ScriptedLoadableModuleLogic):
    BRAIN_WINDOW = 80
    BRAIN_LEVEL = 40
    DEFAULT_BRUSH_DIAMETER_MM = 5.0
    MIN_BRUSH_DIAMETER_MM = 0.5

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)
        self.currentTool = "None"
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

    def setSegmentEditorMode(self, effectName, minimumHu, maximumHu):
        editorWidget = self.segmentEditorWidget()
        segmentEditorNode = self.segmentEditorNode(editorWidget)

        self.ensureSourceVolume(editorWidget)
        self.requireSegmentEditorContext(editorWidget, segmentEditorNode)
        editorWidget.setActiveEffectByName(effectName)
        if not editorWidget.activeEffect():
            raise RuntimeError(f"Could not activate Segment Editor effect: {effectName}")

        self.setIntensityMask(segmentEditorNode, minimumHu, maximumHu, True)
        self.setDoNotOverwriteSegments(segmentEditorNode)
        self.ensureBrushDiameter(editorWidget)

        self.currentTool = effectName
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

    def status(self):
        try:
            editorWidget = self.segmentEditorWidget()
            segmentEditorNode = self.segmentEditorNode(editorWidget)
            activeEffect = editorWidget.activeEffect()
            toolName = self.effectName(activeEffect) if activeEffect else self.currentTool
            maskEnabled = bool(segmentEditorNode.GetSourceVolumeIntensityMask())
            minimumHu, maximumHu = segmentEditorNode.GetSourceVolumeIntensityMaskRange()
            maskText = f"{minimumHu:g}-{maximumHu:g} HU" if maskEnabled else "Off"
            brushText = self.brushStatus(activeEffect)
            overwriteText = self.overwriteStatus(segmentEditorNode)
            segmentText = self.selectedSegmentName(editorWidget, segmentEditorNode)
            return (
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

    def setDoNotOverwriteSegments(self, segmentEditorNode):
        overwriteNone = getattr(slicer.vtkMRMLSegmentEditorNode, "OverwriteNone", 2)
        segmentEditorNode.SetOverwriteMode(overwriteNone)

    def backgroundVolumeNode(self):
        layoutManager = slicer.app.layoutManager()
        if layoutManager:
            for sliceViewName in layoutManager.sliceViewNames():
                sliceWidget = layoutManager.sliceWidget(sliceViewName)
                compositeNode = sliceWidget.mrmlSliceCompositeNode()
                volumeId = compositeNode.GetBackgroundVolumeID()
                if volumeId:
                    return slicer.mrmlScene.GetNodeByID(volumeId)

        volumeNodes = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")
        return volumeNodes[0] if volumeNodes else None

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
