# SlicerHemorrhageTools

**A pair of scripted 3D Slicer modules for manual hemorrhage segmentation cleanup and quantitative morphological characterisation of intracerebral hemorrhage (ICH) on CT.**

The toolkit consists of two independent modules that work together:

| Module | Location | Purpose |
|---|---|---|
| **Hemorrhage Tools** | `SlicerHemorrhageTools/` | One-click HU-constrained segmentation cleanup, batch case management |
| **Hemorrhage Morphology** | `SlicerMorphology/` | Radiomics feature extraction, satellite tracking, longitudinal analysis |

Both modules share a **Module Navigation** bar and global keyboard shortcuts (`Alt+1/2/3`) for instant switching between Segment Editor, Hemorrhage Tools, and Hemorrhage Morphology without using the Slicer module menu.

![Hemorrhage and perihematomal edema cleanup example](docs/images/hemorrhage-edema-cleanup.png)

---

## Table of Contents

1. [Target Platform](#target-platform)
2. [Hemorrhage Tools — Module 1](#hemorrhage-tools--module-1)
   - [Features](#features)
   - [Install](#install)
   - [Use](#use)
   - [Keyboard Shortcuts](#keyboard-shortcuts)
   - [Batch Case Manager](#batch-case-manager)
   - [Notes](#notes)
3. [Hemorrhage Morphology — Module 2](#hemorrhage-morphology--module-2)
   - [Requirements](#requirements)
   - [Install](#install-1)
   - [Use](#use-1)
   - [Feature Categories](#feature-categories)
   - [Clinical Risk Thresholds](#clinical-risk-thresholds)
   - [Spatial Graph Tracking (Method 3)](#spatial-graph-tracking-method-3)
   - [Radial Distance Complexity (Method 2)](#radial-distance-complexity-method-2)
   - [Perihematomal Edema (PHE) Metrics](#perihematomal-edema-phe-metrics)
   - [Longitudinal Analysis](#longitudinal-analysis)
   - [CSV Export](#csv-export)
4. [Repository Structure](#repository-structure)
5. [References](#references)
6. [Troubleshooting](#troubleshooting)
7. [License](#license)

---

## Target Platform

Both modules target **3D Slicer 5.10**. They are scripted Python modules and require no compilation.

---

## Hemorrhage Tools — Module 1

### Module Navigation

A **Module Navigation** bar sits at the top of both Hemorrhage Tools and Hemorrhage Morphology. It contains three buttons:

- **Segment Editor** — switches to Slicer's built-in Segment Editor
- **Hemorrhage Tools** — switches to this module
- **Hemorrhage Morphology** — switches to the morphology analysis module

The button for the currently active module is automatically disabled. All three buttons display their assigned shortcut key in parentheses.

Three global Slicer-wide shortcuts are registered via `slicer.hemorrhageModuleShortcuts` so they remain active regardless of which module is visible:

| Key | Action |
|---|---|
| `Alt+1` | Switch to Segment Editor |
| `Alt+2` | Switch to Hemorrhage Tools |
| `Alt+3` | Switch to Hemorrhage Morphology |

### Features

A streamlined panel for threshold-constrained Paint and Erase workflows:

- **Module Navigation bar** — one-click switching to Segment Editor, Hemorrhage Tools, or Hemorrhage Morphology (see above)
- **Set Brain Window** — sets the current background volume to W/L 80/40 with one click
- **Persistent intensity range gating** — two independently configurable threshold ranges persisted to Slicer `QSettings` across sessions:
  - *Range 1* (default 40–80 HU, for acute hemorrhage or high-intensity structures)
  - *Range 2* (default 5–33 HU, for perihematomal edema or low-intensity structures)
- **Brush size control** — Brush Smaller / Brush Larger buttons (1 mm steps, minimum 0.5 mm diameter)
- **Dilate / Erode active segment** — margin grow/shrink using the Segment Editor Margin effect, with five masking options:
  - *Default* — Dilate constrains to Range 1 HU; Erode constrains to Range 2 HU
  - No masking
  - Constrained to Range 1 HU
  - Constrained to Range 2 HU
  - Use current editor mask
- **Toggle editable intensity masking** — quickly turn range paint gating on/off
- **Toggle segmentation visibility** — show/hide the entire segmentation with one click
- **Segment-by-segment visibility checklist** — individual checkbox per segment for precise visibility control
- **Overwrite mode selection** — *Do not overwrite segments* or *Overwrite visible segments*
- **Segment volume reporting** — prints all segment names and volumes in mL; computes PHE/Hematoma ratio when matching segment names are found
- **Persistent ratio readout** — a dedicated, prominent PHE/Hematoma ratio display field is visible at all times
- **Debounced live auto-refresh** — segment volumes and the PHE/Hematoma ratio are automatically computed immediately on case load and auto-refresh 5 seconds after any segment edits to avoid lagging Slicer during continuous paint strokes
- **Trace Satellite Connections** — identifies disconnected components in 3D (satellites) or 2D (current slice gaps when 3D is contiguous), displays statistics (including closest and furthest distances) in the panel, and overlays interactive, color-coded 3D/2D markup lines (Orange for 3D, Cyan for 2D) showing boundary-to-boundary distances in Slicer's slice views. Persists user preference via Slicer `QSettings`
- **Satellite Cleanup Tools** — provides size-based (mL) and distance-based (mm) filters to clean up disconnected satellite islands from the active segment. Includes manual "Apply Cleanup Now" and "Auto-apply cleanup on refresh" modes. Settings are persisted to Slicer `QSettings`
- **Rename Segmentation text box** — rename the active segmentation node directly on the panel with scene sync, name emptiness validation, and invalid character cleaning
- **Real-time status display** — shows active tool, selected segment, current HU mask range, overwrite mode, and brush size
- **Batch Case Manager** — automated dataset review/annotation with file pairing, annotator suffixing, case flagging, case-level text notes, a visual progress bar, data-loss protection, and progress recovery
- **Customisable keyboard shortcuts** — all 15 actions are individually configurable and saved to Slicer QSettings; shortcut keys are displayed directly on each button
- **Dynamic button labels** — buttons update in real time to reflect the current ranges and assigned shortcuts
- **Validation guard** — workflow buttons are disabled until Segment Editor has a source volume, a segmentation node, and an active segment selected

### Install

1. Open 3D Slicer.
2. Go to **Edit → Application Settings → Modules**.
3. Add the `SlicerHemorrhageTools` subfolder as an additional module path:

   ```
   <path-to-this-repo>/SlicerHemorrhageTools
   ```

   **macOS example:**
   ```
   ~/Documents/SlicerHemorrhageTools/SlicerHemorrhageTools
   ```

   **Windows example:**
   ```
   C:\Users\<YourName>\Documents\SlicerHemorrhageTools\SlicerHemorrhageTools
   ```

4. Restart Slicer.
5. Open **Modules → Segmentation → Hemorrhage Tools**.

### Use

1. Load the CT volume and segmentation (or create a new segmentation in Segment Editor).
2. Open **Hemorrhage Tools**.
3. Click **Set Brain Window** to apply the standard CT brain windowing.
4. Click **Open Segment Editor** to select the source volume, segmentation node, and active segment, then return to Hemorrhage Tools.
5. Adjust the HU ranges if needed (Range 1 for hemorrhage, Range 2 for edema).
6. Select the overwrite behaviour.
7. Click the desired Paint or Erase workflow button (or use keyboard shortcuts).
8. Use **Dilate Active Segment** / **Erode Active Segment** to refine segment boundaries with optional HU masking.
9. (Optional) Type a new name in the **Rename Segmentation** field and press Enter to rename the active segmentation node — the change propagates immediately to the MRML scene.
10. Click **Refresh Segment Volumes** to list volumes for all segments.
11. Check **Trace Satellite Connections** to automatically run component analysis on the active segment. This displays the satellite count, closest, and furthest distances (3D or 2D slice gap) on the panel, and renders dynamic, color-coded 3D/2D markup lines (Orange for 3D satellites, Cyan for 2D slice gaps) showing the shortest boundary-to-boundary distance between the main body and each disconnected piece.
12. Expand the **Satellite Cleanup Tools** panel to filter out noise satellites. Enable size-based cleanup (e.g. <= 0.10 mL) and/or distance-based cleanup (e.g. >= 20.0 mm) and click **Apply Cleanup Now**. Toggle **Auto-apply cleanup on refresh** to automatically run this cleanup every time the segment is modified (with a 5-second debounce after editing).

> **Tip:** The module reads the current Segment Editor context. It does not create a new segmentation or force re-selection of volumes. If Segment Editor has no source volume set, the module automatically falls back to the CT volume currently displayed in the Red slice viewer.

### Keyboard Shortcuts

Shortcuts are fully configurable through the **Keyboard Shortcuts** collapsible panel. After entering new key sequences, click **Apply and Save Shortcuts** — settings are persisted to Slicer QSettings and survive Slicer restarts. Button labels update immediately to show the newly assigned keys.

Default shortcuts:

| Key | Action | Scope |
|---|---|---|
| `[` | Brush Smaller (−1 mm) | Slicer window |
| `]` | Brush Larger (+1 mm) | Slicer window |
| `1` | Paint with Range 1 (40–80 HU) | Slicer window |
| `2` | Erase with Range 2 (5–33 HU) | Slicer window |
| `3` | Paint with Range 2 (5–33 HU) | Slicer window |
| `4` | Erase with Range 1 (40–80 HU) | Slicer window |
| `v` | Toggle segmentation visibility | Slicer window |
| `m` | Toggle editable intensity mask | Slicer window |
| `d` | Dilate active segment | Slicer window |
| `e` | Erode active segment | Slicer window |
| `Alt+1` | Switch to Segment Editor | **Global** (all modules) |
| `Alt+2` | Switch to Hemorrhage Tools | **Global** (all modules) |
| `Alt+3` | Switch to Hemorrhage Morphology | **Global** (all modules) |
| `Alt+n` | Save & Load Next | Slicer window |
| `r` | Refresh Segment Volumes | Slicer window |
| `Escape` | Deactivate active effect (go back to click/navigation) | Slicer window |

> **Note:** The three `Alt+` module-switching shortcuts are registered globally via `slicer.hemorrhageModuleShortcuts` and remain active regardless of which module panel is currently displayed. They are also available from Hemorrhage Morphology (both modules share the same shortcut registration system).

### Batch Case Manager

The **Batch Case Manager** is a collapsible panel in Hemorrhage Tools that automates sequential annotation of large CT datasets.

#### Setup

1. Set the **CT Folder** — directory containing raw CT volumes (`.nii.gz`, `.nii`, `.nrrd`, `.mha`, `.mhd`).
2. Set the **Segmentation Folder** — directory containing input segmentations (`.seg.nrrd`, `.nrrd`, `.nii.gz`, etc.).
3. Set the **Output Folder** — where cleaned segmentations will be saved.

Folder paths are persisted to Slicer QSettings and restored on next launch.

#### Matching Algorithm

The scanner uses a generalised suffix-stripping substring algorithm — it does not require fixed naming prefixes:

1. Lists all CT and segmentation files in their respective directories.
2. Strips file extensions and common workflow suffixes (`_anjan_ich`, `_seg`, `-seg`, `_segmentation`, `_cleaned`, etc.) from each filename to produce a clean root name.
3. Pairs a CT and a segmentation if either clean root is a substring of the other (case-insensitive).
4. Sorts all matched pairs alphabetically/numerically by case name.
5. Displays matched pairs in the **Select Case** dropdown.

Example matches:

| CT file | Segmentation file | Match? |
|---|---|---|
| `case01.nii.gz` | `case01_anjan_ich.seg.nrrd` | ✓ |
| `Patient02_CT.nii` | `Patient02_CT_seg.nrrd` | ✓ |
| `003.nii` | `003-segmentation.nrrd` | ✓ |
| `case_456_CT.mha` | `case_456_segmentation.seg.nrrd` | ✓ |

#### Case Loading

Click **Load Selected Case** to:

1. Check if the current case has unsaved modifications (to either the segmentation or notes/flags). If unsaved changes are present, display a confirmation dialog offering to save, discard, or cancel.
2. Remove any previously loaded batch CT and segmentation nodes from the scene.
3. Load the new CT volume and segmentation synchronously.
4. Auto-assign both nodes to the Segment Editor (source volume + segmentation) and select the first available segment.
5. Apply the standard Brain Window (W/L 80/40) to the CT.
6. Reset and re-center all 2D slice views and the 3D viewer on the new data.
7. Automatically load and populate the case flag and notes from the sidecar file if it exists.
8. Automatically calculate segment volumes and the PHE/Hematoma ratio immediately upon load.

#### Save Current Case

Click **Save Current Case** to manually save the current segmentation and notes sidecar to the Output Folder without advancing the active case index.

#### Save & Load Next

Click **Save & Load Next** (or press its default shortcut **`Alt+n`**) to:

1. Save the active segmentation to the Output Folder under its **original filename** (or with a custom **Annotator Suffix** if configured, preserving the file format).
2. Save/update the case flag and case notes to a sidecar file (`<segmentation_filename>_notes.txt`) in the Output Folder.
3. Automatically uncheck (toggle OFF) the **Trace Satellite Connections** checkbox to clear connection markups and overlays for a clean start on the next case.
4. Automatically advance the dropdown to the next case and load it.
5. Display a completion dialog when all cases in the list have been processed.

---

### Notes

- Brain window uses W=80, L=40.
- The Paint/Erase buttons use the HU values currently shown in the range fields at the time of the click.
- Editable intensity masking limits where painting or erasing can occur (by CT HU), but it does not prevent segment overlap. Use the Erase buttons to remove spillover.
- The **Default** dilate/erode masking mode applies Range 1 HU (40–80) for dilation and Range 2 HU (5–33) for erosion automatically — matching standard hemorrhage/edema cleanup logic. After the margin operation completes, the previous active effect and intensity mask state are automatically restored.
- The **Rename Segmentation** text box always shows the current segmentation node name and updates automatically when the active node changes. It is disabled when no segmentation is loaded. The rename only fires when you press Enter or leave the field.
- The status bar always reflects the Segment Editor state directly: active tool, selected segment, editable intensity range, overwrite mode, and brush size.
- **Segment Volumes** uses Slicer's `SegmentStatistics` plugin. Volumes are reported in mL. If segment names contain keywords like *hematoma*, *hemorrhage*, or *ICH* alongside *PHE*, *edema*, or *perihematomal*, the PHE/Hematoma volume ratio is automatically computed and appended.

---

## Hemorrhage Morphology — Module 2

A companion module that extracts an extensive set of volumetric, morphological, density, texture, and spatial complexity features from hemorrhage segmentations using PyRadiomics. Results are displayed in a sortable, filterable table and can be exported to CSV.

### Module Navigation

Identical to the Hemorrhage Tools navigation bar: Segment Editor, Hemorrhage Tools, and Hemorrhage Morphology buttons appear at the top of the panel. The **Hemorrhage Morphology** button is disabled when this module is active. The same global `Alt+1/2/3` shortcuts apply.

### Requirements

- **3D Slicer 5.10**
- **SlicerRadiomics** extension — install via the Extension Manager, then restart Slicer.
- **SlicerElastix** extension — required only for the **Deformable Image Registration (DIR) & Jacobian** workflow. Install via Extension Manager if longitudinal registration is needed.

Python packages used at runtime (bundled with the above extensions):
- `pyradiomics`
- `SimpleITK` / `sitkUtils`
- `numpy`
- `scipy`

### Install

Add the `SlicerMorphology` directory as an additional module path (alongside or separately from Hemorrhage Tools):

```
<path-to-this-repo>/SlicerMorphology
```

Restart Slicer. The module appears under **Modules → Segmentation → Hemorrhage Morphology**.

### Use

1. Load a CT volume and segmentation (or create one with Hemorrhage Tools).
2. Open **Hemorrhage Morphology**.
3. Click **Refresh Segment List** to populate the segment selector with the current segmentation's segments.
4. Select the target segments from the dropdown (*All segments* or a specific segment).
5. Expand **Feature classes** to enable or disable individual PyRadiomics feature class groups.
6. Adjust **Bin width** (default 25 HU) for texture feature discretisation.
7. Adjust **Hyperdense threshold** (default 50 HU) for the custom Hyperdense/Hypodense ratio.
8. (Optional) Expand **Spatial Graph Settings (Method 3)** to configure satellite tracking:
   - Toggle **Enable Spatial Graph Tracking** on/off.
   - Set the **Distance threshold** (default 10.0 mm, range 0.5–50 mm).
9. Click **Compute Features**.
10. Review results in the sortable table. Risk flags (⚠) appear when published clinical thresholds are crossed.
11. Click **Export CSV** to save.

For longitudinal analysis (follow-up CT scan available):

1. Expand **Longitudinal Analysis (Deltas & Registration)**.
2. Select the **Follow-up Volume** and **Follow-up Segmentation** nodes from the scene.
3. Click **Compute Longitudinal Deltas** to compute feature changes between baseline and follow-up.
4. (Optional, requires SlicerElastix) Click **Compute DIR & Jacobian** to run deformable registration and visualise local tissue expansion/compression.

### Feature Categories

#### 1. Volumetric Parameters

| Feature | Unit | Description |
|---|---|---|
| Hematoma Volume (mesh) | mL | Total volume from mesh surface reconstruction |
| Hematoma Volume (voxel) | mL | Total volume from raw voxel count |

#### 2. Morphological and Geometric Indices

| Feature | Unit | Description |
|---|---|---|
| Surface Area | mm² | Total boundary surface area |
| Maximum 3D Diameter | mm | Widest Feret diameter span |
| Sphericity | — | Boundary regularity; 1.0 = perfect sphere (⚠ ≤ 0.56) |
| Elongation | — | Ratio of 2nd to 1st principal axis lengths |
| Flatness | — | Ratio of 3rd to 1st principal axis lengths |
| Surface-to-Volume Ratio | 1/mm | Surface area per unit volume |
| Major Axis Length | mm | Length of the longest principal axis |
| Minor Axis Length | mm | Length of the 2nd principal axis |
| Least Axis Length | mm | Length of the shortest principal axis |

#### 3. Density and Heterogeneity Markers

| Feature | Unit | Description |
|---|---|---|
| Mean Attenuation | HU | Average CT density within the segment |
| Density Variance (SD) | HU | Standard deviation of HU values (blend/swirl sign proxy) |
| Variance | HU² | Variance of HU distribution |
| Skewness | — | Asymmetry of the intensity distribution |
| Kurtosis | — | Tail weight of the intensity distribution |
| Entropy | — | Intensity disorder / information content |
| Energy | — | Sum of squared normalised intensities |
| HU Range | HU | Max minus min HU within the segment |
| Minimum / Maximum HU | HU | Minimum and maximum voxel intensities |
| 10th / 90th Percentile | HU | Intensity percentile values |
| Median HU | HU | Median intensity |
| Interquartile Range | HU | IQR of intensity distribution |
| Robust Mean Abs Deviation | HU | Robust measure of dispersion |
| Mean Abs Deviation | HU | Mean absolute deviation from the mean |
| Root Mean Squared | HU | RMS of intensities |
| Total Energy | — | Total energy of the volume |
| Uniformity | — | Uniformity of the intensity distribution |
| **Hyperdense / Hypodense Ratio** | — | Custom metric: voxels ≥ hyperdense threshold / voxels < threshold; proxy for clotted vs. liquid blood |

#### 4. Texture Matrices

Five PyRadiomics texture classes are computed, each producing multiple features describing the spatial arrangement and clustering of voxel intensities:

| Class | Full Name |
|---|---|
| GLCM | Gray-Level Co-occurrence Matrix |
| GLRLM | Gray-Level Run Length Matrix |
| GLSZM | Gray-Level Size Zone Matrix |
| GLDM | Gray-Level Dependence Matrix |
| NGTDM | Neighbouring Gray Tone Difference Matrix |

> **Bin width** controls the HU discretisation step before texture computation (default 25 HU). A smaller bin width produces finer texture resolution at the cost of computation time.

#### 5. Radial Distance Complexity (Method 2)

Computed from the boundary voxels of each segment in physical space:

| Feature | Description |
|---|---|
| **Radial Spikiness (CV)** | Coefficient of variation of centroid-to-boundary distances. A higher value indicates more irregular, spiked boundaries. |
| **Radial Peakness (Kurtosis)** | Excess kurtosis of the centroid-to-boundary distance distribution. High kurtosis indicates sharp, isolated projections. |

Formulation:

$$\text{CV} = \frac{\sigma(D)}{\mu(D)}, \qquad \text{Kurtosis} = \frac{\frac{1}{N}\sum_{i=1}^{N}(d_i - \mu)^4}{\sigma^4} - 3$$

where $D = \{d_1, \ldots, d_N\}$ is the set of Euclidean distances from the segment centroid to each boundary voxel in physical (mm) coordinates.

#### 6. Spatial Graph Metrics (Method 3 — Satellite/Island Sign Tracking)

When **Enable Spatial Graph Tracking** is active:

| Feature | Unit | Description |
|---|---|---|
| Total Satellites | count | Number of disconnected components excluding the main body |
| Connected Satellites | count | Satellites with boundary-to-boundary distance ≤ threshold |
| Closest Satellite Distance | mm | Minimum boundary-to-boundary distance to the nearest satellite |
| Largest Satellite Volume | mL | Physical volume of the largest disconnected satellite |

See the [Spatial Graph Tracking](#spatial-graph-tracking-method-3) section below for algorithmic details.

#### 7. Perihematomal Edema (PHE) Metrics

Automatically computed when both a hemorrhage and an edema segment are present (matched by name keywords):

| Feature | Description |
|---|---|
| PHE / Hematoma Volume Ratio | Edema volume relative to the primary hemorrhage volume |
| PHE Sphericity | Sphericity of the edema segment boundary (⚠ ≤ 0.56) |

---

### Clinical Risk Thresholds

The module checks published clinical thresholds and flags at-risk features with a ⚠ symbol in the results table:

| Feature | Threshold | Interpretation | Reference |
|---|---|---|---|
| Sphericity | ≤ 0.56 | Irregular boundary — associated with hematoma expansion risk | Yang et al. (2025) [6] |
| Surface Area | > 55 cm² (5500 mm²) | Large surface boundary — associated with expansion risk | Yang et al. (2025) [6] |
| PHE Sphericity | ≤ 0.56 | Irregular edema boundary — secondary injury risk | [5] |

Expansion classification (applied automatically to hematoma volume deltas in longitudinal analysis):

| Condition | Classification |
|---|---|
| Volume increase ≥ 12.5 mL | ⚠ Major expansion [8] |
| Volume increase ≥ 6.0 mL **or** ≥ 33% relative | ⚠ Significant expansion [8] |
| Otherwise | No significant expansion |

---

### Spatial Graph Tracking (Method 3)

**Background:** Standard segmentation pipelines apply connected component analysis (CCA) to remove small isolated components, treating them as noise. However, these isolated "satellite" or "island" components may represent clinically important secondary bleeding points (the Satellite Sign and Island Sign), whose presence is an independent predictor of early hematoma expansion (AUC = 0.881 per Ma et al. 2020).

**Algorithm:**

1. The binary segmentation mask is labeled using `scipy.ndimage.label` to identify all disconnected components.
2. The main hematoma body is defined as the largest component by voxel count.
3. For each satellite component $S$, the minimum boundary-to-boundary Euclidean distance to the main body $M$ is computed using the Euclidean Distance Transform of the inverse main-body mask:
   $$d_{\min}(M, S) = \min_{p \in \partial M, q \in \partial S} \|p - q\|$$
4. Satellites where $d_{\min} \leq \theta$ (the configurable threshold, default 10 mm) are "virtually connected" to the main body — their voxels are included in the mask passed to PyRadiomics for shape feature calculation.
5. This preserves the true lower sphericity and larger surface area of the irregular combined shape, **without** morphological dilation that would inflate volume measurements.

**Key finding on Scan 1:** The satellite (1 voxel, 0.0013 mL) lies only 1.61 mm from the main body boundary. Standard CCA removes it and inflates sphericity from 0.6382 to 0.6388. Method 3 retains it, preserving the clinically accurate shape profile.

---

### Radial Distance Complexity (Method 2)

Provides a continuous index of boundary spikiness independent of connected component counting:

- **Radial Spikiness (CV):** Detects how widely boundary distances vary around the centroid. A perfect sphere produces CV = 0. Multi-lobed or projecting hematomas produce higher values.
- **Radial Peakness (Kurtosis):** Detects sharp, focal projections. Highly irregular hematomas with a few isolated tentacles produce high positive kurtosis. Smooth, roughly uniform boundaries produce kurtosis near 0 or negative.

Both metrics are computed in physical space (mm), accounting for anisotropic voxel spacing.

---

### Perihematomal Edema (PHE) Metrics

PHE metrics are computed automatically when both a hemorrhage-named segment and an edema-named segment are found. Name matching is case-insensitive and keyword-based:

- Hemorrhage keywords: `hematoma`, `haematoma`, `hemorrhage`, `haemorrhage`, `ich`
- Edema keywords: `phe`, `edema`, `oedema`, `perihematomal`, `perihaematomal`

---

### Longitudinal Analysis

Requires both a **baseline** CT scan+segmentation (loaded in Segment Editor) and a **follow-up** CT scan+segmentation (selected in the Longitudinal Analysis panel).

#### Feature Deltas

Computed for all matched segments across both time points:

| Feature | Unit | Formula |
|---|---|---|
| Δ Volume (absolute) | mL | $V_\text{fu} - V_\text{bl}$ |
| Δ Volume (relative) | % | $(V_\text{fu} - V_\text{bl}) / V_\text{bl} \times 100$ |
| Δ Surface Area | mm² | $A_\text{fu} - A_\text{bl}$ |
| Δ Sphericity | — | $S_\text{fu} - S_\text{bl}$ |
| Δ Mean Attenuation | HU | $\overline{HU}_\text{fu} - \overline{HU}_\text{bl}$ |
| Δ Density Variance | HU | $\sigma_\text{fu} - \sigma_\text{bl}$ |
| Expansion Classification | — | See [Clinical Risk Thresholds](#clinical-risk-thresholds) |

Results are labelled `Baseline - <SegmentName>`, `Follow-up - <SegmentName>`, and `<SegmentName>` (for deltas) in the exported CSV.

#### Deformable Image Registration & Jacobian Determinant

Requires **SlicerElastix**. The follow-up scan is registered to the baseline (rigid skull alignment → B-spline non-rigid deformation) using custom Elastix parameter files bundled in `SlicerMorphology/Resources/`:

- `Parameters_Rigid.txt` — 4-resolution rigid registration (EulerTransform, Mattes Mutual Information)
- `Parameters_BSpline.txt` — B-spline non-rigid registration

The **Jacobian Determinant** ($J$) field is computed from the resulting displacement field:

- $J > 1$: Local tissue expansion / dilation
- $J < 1$: Local tissue compression / contraction
- $J \leq 0$: Non-physical deformation (folding)

The Jacobian volume is pushed into the Slicer scene and coloured with the **DivergingBlueRed** preset (blue = compression, red = expansion) for interactive 3D visualisation.

Per-segment Jacobian statistics reported:

| Metric | Unit | Description |
|---|---|---|
| Mean Jacobian | — | Average local deformation within the mask |
| Max Local Expansion (max J) | — | Peak local tissue expansion |
| Max Local Compression (min J) | — | Peak local tissue compression |
| Expansion Fraction (J > 1.05) | % | Proportion of segment undergoing expansion |
| Compression Fraction (J < 0.95) | % | Proportion of segment undergoing compression |
| Conserved Fraction (0.95 ≤ J ≤ 1.05) | % | Proportion of stable, undeformed tissue |
| Expansion Deformation Volume | mL | Volume-weighted integral of local expansion |
| Compression Deformation Volume | mL | Volume-weighted integral of local compression |
| Folding Voxels (J ≤ 0) | count | Count of voxels with non-physical deformation |

---

### CSV Export

Click **Export CSV** after computing features. The file uses the following schema:

| Column | Description |
|---|---|
| `segment` | Segment name (prefixed with `Baseline -` / `Follow-up -` for longitudinal) |
| `category` | Feature category group (e.g., `Volumetric`, `Morphological / Geometric`, `Texture — GLCM`, `Spatial Graph (Method 3)`, `Longitudinal Delta`, `DIR / Jacobian`) |
| `feature` | Human-readable feature name |
| `value` | Computed value (numeric string) |
| `unit` | Unit of measurement (e.g., `mL`, `mm²`, `HU`, `%`, `mm`, `count`) |
| `risk_flag` | Empty or a ⚠ string with the clinical threshold description |

---

## Repository Structure

```
SlicerHemorrhageTools/                  ← root
│
├── SlicerHemorrhageTools/              ← Module 1: Hemorrhage cleanup panel
│   └── SlicerHemorrhageTools.py        ← Single-file scripted module (~1,460 lines)
│       ├── SlicerHemorrhageTools       ← Module metadata (title, category, contributors)
│       ├── SlicerHemorrhageToolsWidget ← Full Qt UI: nav bar, cleanup, batch manager,
│       │                                  shortcuts (14 configurable), segment checklist
│       └── SlicerHemorrhageToolsLogic  ← Segment Editor API, brush, margin, statistics
│
├── SlicerMorphology/                   ← Module 2: Morphological feature extraction
│   ├── SlicerMorphology.py             ← Single-file scripted module (~1,730 lines)
│   │   ├── SlicerMorphology            ← Module metadata
│   │   ├── SlicerMorphologyWidget      ← Qt UI: nav bar, feature classes, spatial graph,
│   │   │                                  longitudinal analysis, results table
│   │   └── SlicerMorphologyLogic       ← PyRadiomics extraction, Method 2, Method 3, DIR
│   └── Resources/
│       ├── Parameters_Rigid.txt        ← Elastix rigid registration preset (EulerTransform)
│       └── Parameters_BSpline.txt      ← Elastix B-spline deformable registration preset
│
├── docs/
│   └── images/
│       └── hemorrhage-edema-cleanup.png ← Screenshot used in this README
│
├── test_features.py                    ← Integration test script (runs inside Slicer Python console)
│                                         Covers: nav shortcuts, batch matching, load/save lifecycle
│
├── literature_review.md               ← Clinical background: Island Sign, Satellite Sign,
│                                         Sphericity, Method 2 & Method 3 formulations
├── method_comparison_results.md       ← Quantitative comparison of Methods 1–3 on Scan 1
├── walkthrough.md                     ← Developer walkthrough: QOL features, batch manager,
│                                         module navigation, shortcut system
├── Finger like projections.txt        ← Reference document: shape complexity extraction methods
├── worklog.md                         ← Development log for spatial graph morphometry features
│
├── LICENSE                            ← MIT License
├── .gitignore
└── README.md                          ← This file
```

---

## References

For a detailed review of clinical shape complexity markers (Island Sign, Satellite Sign) and their mathematical formulations (Methods 2 & 3), see [literature_review.md](literature_review.md).

1. *Density and Shape as CT Predictors of Intracerebral Hemorrhage Growth* (Stroke)
2. *Radiomics for intracerebral hemorrhage: are all small hematomas benign?* (PMC)
3. *Radiomics for prediction of intracerebral hemorrhage outcomes: A retrospective multicenter study* (PMC)
4. *Radiomics Outperforms Clinical and Radiologic Signs in Predicting Spontaneous Basal Ganglia Hematoma Expansion: A Pilot Study* (PMC)
5. *Quantitative Perihematomal Imaging Analysis for the Prediction of Intracerebral Hematoma Expansion* (American Journal of Neuroradiology)
6. Yang et al. (2025). *The Prediction of Hematoma Growth in Acute Intracerebral Hemorrhage: From 2-Dimensional Shape to 3-Dimensional Morphology.* Journal of Stroke and Cerebrovascular Diseases.
7. *Predictive modeling of hematoma expansion from non-contrast computed tomography in spontaneous intracerebral hemorrhage patients* (eLife)
8. *Hematoma Expansion in Intracerebral Hemorrhage: Definition and Predictors* (Journal of Stroke)
9. Ma et al. (2020). *A Nomogram Model of Radiomics and Satellite Sign Number as Imaging Predictor for Intracranial Hematoma Expansion.* Frontiers in Neurology, 11, 580.
10. Li et al. (2017). *Island Sign on Noncontrast Computed Tomography Predicts Hematoma Expansion and Poor Outcome in Patients With Intracerebral Hemorrhage.* Stroke, 48(11), 3024–3030.

---

## Troubleshooting

### 1. PyRadiomics / NumPy Version Conflict
If Slicer has NumPy 2.x installed, you may see an `ImportError` or warning regarding `_unique_hash` from `numpy._core._multiarray_umath` when reloading the Hemorrhage Morphology module. This happens because the pre-compiled `SlicerRadiomics` binary wheels are built for NumPy 1.x.

**Solution**:
1. Close 3D Slicer.
2. Open PowerShell or Command Prompt.
3. Force-reinstall a compatible version of NumPy by running Slicer's offline Python interpreter:
   ```powershell
   & "C:\Users\anjan\AppData\Local\slicer.org\3D Slicer 5.10.0\bin\PythonSlicer.exe" -m pip install --upgrade --force-reinstall "numpy<2"
   ```
4. Reopen 3D Slicer and reload the module.

### 2. VTK Warning: `Input data type must be VTK_TRIANGLE not 9`
For certain patient cases, Slicer's automatic closed surface mesh generation may produce quadrilateral cells (VTK cell type 9) instead of purely triangles. When Slicer's internal logic computes segment statistics on these meshes, it outputs this warning.

**Solution**:
* This warning is harmless and can be ignored. It does not affect the PyRadiomics feature calculation.
* To prevent this warning window from popping up, you can run this command in Slicer's Python Console:
  ```python
  import vtk
  vtk.vtkObject.GlobalWarningDisplayOff()
  ```

---

## License

MIT — see [LICENSE](LICENSE).
