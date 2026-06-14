# SlicerHemorrhageTools

A small scripted 3D Slicer module for faster manual cleanup of hemorrhage
segmentations.

The first version focuses on one-click Segment Editor setup for common
HU-constrained Paint and Erase workflows:

- Set CT brain window to W/L 80/40
- Editable HU ranges with defaults of 40-80 and 5-33
- Paint or erase with either HU range
- Increase or decrease brush size
- Toggle editable intensity masking
- Toggle overwrite behavior between **do not overwrite segments** and
  **overwrite visible segments**
- Show current tool, HU mask, and brush status
- Validate source volume, segmentation, and active segment before enabling
  workflow buttons
- Keyboard shortcuts for brush size and workflow modes
- Open Segment Editor from the module panel when setup is needed

![Hemorrhage and perihematomal edema cleanup example](docs/images/hemorrhage-edema-cleanup.png)

## Target

This module is intended for 3D Slicer 5.10.

## Install

1. Open 3D Slicer.
2. Go to **Edit > Application Settings > Modules**.
3. Add this folder as an additional module path:

   ```text
   <path-to-this-repo>/SlicerHemorrhageTools
   ```

   For example, if the repo is in your Documents folder on macOS:

   ```text
   ~/Documents/Slicerhemorrhagetools/SlicerHemorrhageTools
   ```

   On Windows, it may look like:

   ```text
   C:\Users\<YourName>\Documents\Slicerhemorrhagetools\SlicerHemorrhageTools
   ```

4. Restart Slicer.
5. Open **Modules > Segmentation > Hemorrhage Tools**.

## Use

1. Load the CT volume and segmentation.
2. Open Hemorrhage Tools.
3. Click **Open Segment Editor** if you need to choose the source volume,
   segmentation, or active segment.
4. Return to Hemorrhage Tools.
5. Adjust either HU range if needed.
6. Choose the overwrite behavior.
7. Click the desired workflow button.

The module uses the current Segment Editor context. It does not create a new
segmentation or force re-selection of volumes. If Segment Editor does not
already have a source volume selected, the module uses the current background
volume from the Red slice viewer.

## Shortcuts

When Slicer is focused:

- `[` decreases brush size by 1 mm.
- `]` increases brush size by 1 mm.
- `1` activates Paint with Range 1.
- `2` activates Erase with Range 2.
- `3` activates Paint with Range 2.
- `4` activates Erase with Range 1.

## Tested Workflow

This workflow was tested in 3D Slicer:

1. Load a CT scan.
2. Click **Set Brain Window**.
3. Click **Open Segment Editor**.
4. Add a segment and rename it `Hemorrhage`.
5. Switch back to Hemorrhage Tools from the module history.
6. Paint the hemorrhage using the HU-constrained Paint button.
7. Switch back to Segment Editor and add an `Edema` segment.
8. Switch back to Hemorrhage Tools and paint edema.
9. Use the Erase buttons for quick cleanup when painting extends outside the target region.

## Notes

- Brain window currently uses window 80 and level 40.
- Brush size changes by 1 mm per click, with a minimum diameter of 0.5 mm.
- The Paint/Erase buttons use the HU values currently shown in the range fields.
- The workflow buttons are disabled until Segment Editor has a source volume,
  segmentation, and selected segment. If Segment Editor has no source volume,
  the module uses the Red slice background volume when available.
- The status display reflects Segment Editor state directly, including active
  tool, selected segment, editable intensity range, overwrite mode, and brush
  size.
- Editable intensity masking limits painting/erasing by source CT HU, but it
  does not make segments mutually exclusive. If two visible segments overlap,
  Slicer may show blended overlay colors. Use the Erase buttons to remove
  spillover from the active segment, and confirm the correct active segment in
  Segment Editor before painting.
- Keyboard shortcuts are intentionally minimal and mirror the visible workflow
  buttons.
