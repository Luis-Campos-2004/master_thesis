# Physical Decoupled Multimodal Vision-Based Programmable Skin

<p align="center">
  <img src="results/images_report/figures/sensor_setup_compact.png" alt="Assembled sensor housing" height="260">
  <img src="results/images_report/figures/sensor_setup_annot.png" alt="Exploded view: grating, PDMS, LED strip, and camera" height="260">
</p>

Touch is one of the senses that lets humans understand and manipulate their
environment, and giving robots something comparable — shape, pressure,
force, and temperature sensing in one package — would meaningfully improve
their dexterity. Vision-based tactile sensors achieve this in a simple but elegant manner: a soft contact surface is
imaged by a camera and deformation is recovered through image processing.

This project is a **physically decoupled, multimodal** vision-based skin: a
single printed stripe pattern, imaged with a USB camera,
is enough to recover **temperature, force, depth, and shape** —
with no embedded electronics and no specialized imaging hardware. Two
independent physical effects are layered into the same pattern and read out
separately:

- **Temperature** — thermochromic liquid-crystal pigments mixed into the
  stripe grating shift *color* with temperature, at either a sensitive
  range close to body temperature (25–31°C) or a wider range (10–70°C),
  depending on the pigment mix used.
- **Touch** — the stripe *geometry* (spacing and phase) distorts under
  mechanical contact, decoded via Fourier Transform Profilometry (FTP) into
  contact shape, force, and indentation depth, with a 3-D reconstruction
  built from the resulting force–depth relationship.

What makes both readable from the same photo is that they're **physically
decoupled**: a press doesn't impact *color*  and a temperature change doesn't shift stripe *spacing*, so each
effect can be measured almost independently and then reconciled — this
project's central contribution — so a temperature-only event isn't mistaken
for a press, and vice versa. This repository is the full image-processing
pipeline behind that idea: it turns a before/after photo pair of the
membrane into contact shape, force, indentation depth, and surface
temperature, and includes the raw calibration photo sets and CSVs the
pipeline was built and validated against.

Concretely, each image pair — one *reference* (undeformed /
unheated) and one *deformed* (pressed and/or heated) — is analyzed with two
independent, image-only pipelines:

- **`src/tactile/`** — Fourier Transform Profilometry (FTP): a press distorts
  the printed stripe pattern, and that distortion is decoded into contact
  shape, force, and depth.
- **`src/temperature/`** — color/LAB analysis: a temperature change shifts
  the stripe color, which is decoded into a predicted temperature via k-NN
  regression against a calibration CSV, and detected as a segmented
  color-change region.

`src/integrated_pipeline.py` runs both stages on one image pair and
reconciles them, so temperature-only artifacts don't get reported as
presses and vice versa.

## How it works

The sensor surface is printed with a regular stripe/fringe pattern. Two
independent physical effects perturb that pattern in distinguishable ways:

1. **Mechanical contact** locally compresses/stretches the stripes —
   measurable as a **phase shift** of the fringe pattern (FTP) — but leaves
   stripe *color* essentially unchanged (chroma shift ~2.5 LAB units).
2. **Temperature change** shifts the stripe *color* (LAB chroma shifts of
   ~8–12 units) but leaves the stripe *spacing/period* unchanged.

Each pipeline exploits one of these effects and (approximately) ignores the
other, so they can run on the same image pair and be combined without one
contaminating the other's result.

<table align="center">
  <tr>
    <td align="center">
      <img src="results/images_report/figures_final/ref_image.jpg" alt="Reference (undeformed, unheated) image" height="220"><br>
      <sub>Reference frame — undeformed, unheated stripe pattern</sub>
    </td>
    <td align="center">
      <img src="results/images_report/figures_final/def_image.jpg" alt="Deformed (pressed and heated) image" height="220"><br>
      <sub>Deformed frame — same region, pressed and/or heated</sub>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="results/images_report/figures_final/def_img_red_circ.png" alt="Deformed stripe pattern with the detected contact region circled" height="220"><br>
      <sub>Detected contact region outlined on the deformed frame</sub>
    </td>
    <td align="center">
      <img src="results/images_report/figures_final/combo_tip.jpg" alt="Sensor tip components: contact nut and 3-D printed housing" height="220"><br>
      <sub>Sensor tip components — contact nut and 3-D printed housing</sub>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="results/images_report/figures_final/depth_3d.png" alt="3-D depth reconstruction of the contact" height="220"><br>
      <sub>3-D depth reconstruction from the force–depth relationship</sub>
    </td>
    <td align="center">
      <img src="results/images_report/figures_final/temp_seg.png" alt="Color-based temperature-change segmentation: detected regions outlined" height="220"><br>
      <sub>Color-based temperature-change segmentation</sub>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="results/images_report/figures_final/temp_pred.png" alt="Interactive stripe-color temperature prediction" height="220"><br>
      <sub>Interactive stripe-color temperature prediction (k-NN)</sub>
    </td>
    <td align="center">
      <img src="results/images_report/figures_final/shape.png" alt="Reconstructed contact shape mask" height="220"><br>
      <sub>Reconstructed contact shape mask (FTP)</sub>
    </td>
  </tr>
</table>

## Repository layout

```
src/
  integrated_pipeline.py          combined pipeline: color stage + tactile stage
  tactile/
    detect_shape.py                shape detection from stripe phase distortion (FTP)
    estimate_force_depth.py        global stripe-period ratio -> force -> depth (single ROI)
    uniform_reconstruct.py         per-contact reconstruction: shape + force + depth + 3-D plot
  temperature/
    color_merged.py                stripe/flatfield segmentation + interactive temperature viewer
    color_prediction.py            ColorPredictor: k-NN temperature regression (purple stripes)
    black_prediction.py            BlackPredictor: k-NN temperature regression (black stripes)
    color_segment.py               standalone flatfield/z-score segmentation script (debug/dev)
    batch_temperature_validation.py batch predicted-vs-actual validation over labeled image folders
data/
  raw/
    shape_pictures/                 reference + deformed image sets for the tactile pipeline, by shape
    force_pictures/                 reference + known-force image sets for tactile force/depth calibration
    full_color_experiment/          purple-stripe temperature data (calibration + heating/cooling runs)
    black_and_color_experiment/     black-stripe temperature data (calibration + heating/cooling runs)
    final_images/                   one example reference/deformed pair used for the report figures below
  masks/                           ROI/segmentation mask images used by the tactile and temperature scripts
  processed/
    csv_files/                     calibration CSVs (force<->ratio, force<->depth, color<->temperature)
results/
  images_report/                  output figures generated by the pipelines, used in the thesis write-up
```

## Pipeline 1 — Tactile: shape, force, and depth (`src/tactile/`)

Given a **reference** (unloaded) and **deformed** (loaded) image of the
striped membrane:

1. **`detect_shape.py`** — demodulates the stripe carrier via FFT, computes
   the phase difference between reference and deformed images (unwrapped),
   turns it into a robust z-score map, and thresholds/cleans it (hysteresis
   threshold, morphological close/open, hole-filling, component filtering)
   into a binary mask of the contact shape. Each connected component is a
   separate contact. Optional auxiliary channels (`--use-orient`,
   `--use-amp`) can help on weak contacts.
2. **`estimate_force_depth.py`** — given a single ROI mask, measures the mean
   stripe period (via 2-D FFT with sub-pixel refinement) in the reference and
   deformed images. The ratio `period_deformed / period_reference` is mapped
   to a force via a linear fit to a `force_vs_mean_width_ratio.csv`
   calibration table, and force is mapped to depth via PCHIP interpolation
   through a `force_vs_mean_depth.csv` table (linearly extrapolated beyond
   the table's range). This is the simplest, single-region version of the
   measurement.
3. **`uniform_reconstruct.py`** — the full per-contact version: for each
   shape detected by `detect_shape.py`, erodes away the rim (a kinematic
   artifact, not a pressure signal), takes **one global masked FFT** of the
   interior at full camera resolution to get its stripe period, and applies
   the same ratio → force → depth calibration chain per contact. Supports an
   area correction (the membrane responds to *pressure*, i.e. force/area, so
   the measured ratio is rescaled to what the calibration circle would show
   at the same force) and renders an interior/overlay figure plus a
   mouse-rotatable 3-D surface plot (flat plateau per contact, feathered at
   the rim).

**Calibration data**: the width-ratio/depth CSVs and calibration ROI mask
generated for this rig are included in
[`data/processed/csv_files/`](#dataprocessedcsv_files--calibration-tables)
and [`data/masks/`](#datamasks--roi-and-segmentation-masks) — see those
sections below. To recalibrate against your own rig, regenerate
`force_vs_mean_width_ratio.csv`, `force_vs_mean_depth.csv`, and an ROI mask
image (white circle on black) for the calibration circle's area from a
controlled loading experiment.

Run standalone, e.g.:
```bash
python src/tactile/uniform_reconstruct.py 
```

## Pipeline 2 — Temperature: color-based prediction (`src/temperature/`)

1. **`color_merged.py`** — the main entry point. Detects stripes via
   row-adaptive peak finding on the value channel, separates "purple" and
   "black" stripe pixels into masks, and launches an **interactive
   matplotlib pop-up**: click any stripe pixel to see its predicted
   temperature (see `ColorPredictor` / `BlackPredictor` below). It also
   contains a gated color-change segmentation (used by the integrated
   pipeline) that flags a "temperature change" region only when the local
   LAB chroma shift and area exceed configurable thresholds — set high
   enough that a mechanical press (which barely shifts chroma) doesn't
   falsely trigger it.
2. **`color_prediction.py`** (`ColorPredictor`) / **`black_prediction.py`**
   (`BlackPredictor`) — inverse-distance-weighted k-NN regression from pixel
   color to temperature, calibrated from a CSV of (temperature, color)
   samples. Each supports RGB, HSV, and/or LAB color spaces (features are
   min-max normalized per channel); with `color_space="auto"`, whichever
   space gives the closest nearest-neighbour match is used per query pixel.
   Two separate predictors/CSVs exist because the purple and black stripes
   have different color-temperature responses.
3. **`color_segment.py`** — a standalone, non-interactive dev/debug script
   for the flatfield + z-score segmentation step in isolation (produces
   diagnostic plots only; not needed for the main pipeline).
4. **`batch_temperature_validation.py`** — validation harness: point it at a
   folder of sub-folders named by their true temperature (e.g. `25/`, `26/`,
   ...), and for every image it predicts a temperature (via `ColorPredictor`
   or `BlackPredictor`, chosen with `PREDICTOR = "color" | "black"`), trims
   outliers, and plots predicted vs. actual temperature with error bars
   against a `y = x` reference line.

**Calibration data**: `data/processed/csv_files/average_temps.csv` (purple
stripes) and `data/processed/csv_files/average_temps_black.csv` (black
stripes) are included, each with a `Temperature` column plus R/G/B, H/S/V,
and L/a/b columns — see
[`data/processed/csv_files/`](#dataprocessedcsv_files--calibration-tables)
below. To recalibrate, regenerate these from your own temperature-controlled
reference shots.

## Combined pipeline (`src/integrated_pipeline.py`)

Runs both stages on one reference + one deformed image:

1. **Color stage** — pops up the interactive temperature viewer on the
   deformed image, then checks reference vs. deformed for a genuine
   temperature change (gated on LAB chroma shift and area, since a press
   alone shouldn't trigger it) and saves a 3-panel segmentation figure only
   if one is found.
2. **Tactile stage** — reconstructs shape/force/depth per contact. Contacts
   with force at or below `MIN_FORCE_N` (default 0.5 N) are discarded as
   temperature-only artifacts, since a temperature change alone leaves the
   stripe period — and hence the computed ratio/force — essentially
   unchanged.

```bash
python src/integrated_pipeline.py 
```

Useful flags: `--area` (contact area in mm², for the force area-correction),
`--seg-chroma` / `--seg-min-area` / `--seg-min-blob` (temperature-change
segmentation gates), `--min-force` (tactile force-artifact gate),
`--z-exaggeration` (3-D plot z-scaling), `--no-show` (save files only, skip
all pop-up windows).

## Image folders

The repository includes the raw photo sets that were used to calibrate the tactile and 
temperature pipelines. Within each leaf folder, photos are named sequentially in
chronological order as `img_01.jpg`, `img_02.jpg`, ... — the folder path itself
(shape, force level, or temperature) already gives the photo its context, so the
filename only needs to disambiguate multiple shots of the same condition.
Ground-truth shape photos keep their descriptive names (e.g. `ring_gt.jpg`).

### `data/raw/shape_pictures/` — tactile shape reconstruction

One subfolder per contact shape (`F shape`, `P shape`, `Ring`, `Square`,
`Square Circle`, `Star`, `Three Circles`). Each contains a few photos of the membrane under that contact, and most also
include a `*_gt.jpg` ground-truth image (a photo/drawing of the pressed
object itself, for visually checking the reconstructed shape against it).
There's no separate "reference" (undeformed) image per shape folder — pick
any two same-shape images as reference/deformed, or use one of the
unloaded shots from `data/raw/force_pictures/reference/` as the shared
reference.

```bash
# detect_shape.py has no --reference/--deformed flags; edit REF_IMAGE /
# DEF_IMAGE in its CONFIG block, e.g.
#   REF_IMAGE = "data/raw/force_pictures/reference/img_01.jpg"
#   DEF_IMAGE = "data/raw/shape_pictures/Star/img_01.jpg"
# then run:
python src/tactile/detect_shape.py
```

### `data/raw/force_pictures/` — tactile force/depth calibration

`reference/` holds unloaded membrane photos; the other subfolders (`3N`,
`6N`, `9N`, ... `48N`) each hold 5 photos taken under that known applied
force. This is the raw data used to build the
`force_vs_mean_width_ratio.csv` calibration table that
`estimate_force_depth.py` / `uniform_reconstruct.py` expect (measure the
stripe-period ratio for each `reference` vs `<N>N` pair and fit force vs.
ratio), and is also useful as a standalone accuracy check by running the
tactile pipeline on a pair and comparing the reported force to the folder's
label.

```bash
python src/tactile/estimate_force_depth.py
```

### `data/raw/full_color_experiment/` and `data/raw/black_and_color_experiment/` — temperature calibration

Same layout, one per stripe color (purple stripes vs. black stripes, used
by `ColorPredictor` and `BlackPredictor` respectively):

- **`Calibration images/`** (purple set only) — reference shots used to
  build the color→temperature calibration CSV (`average_temps.csv`).
- **`Room Temperature/`, `Room Temperature 2/`** — baseline unheated shots.
- **`Heating Run/`, `Heating Run 2/`** and
  **`Cooling Run/`, `Cooling Run 2/`** — one subfolder per target
  temperature (e.g. `24/`, `25/`, ... up to `75/`), each with ~10 photos.
  The subfolder name is the actual measured temperature for that batch —
  this is exactly the layout `batch_temperature_validation.py` expects for
  `DATA_ROOT`.

```bash
# Predicted-vs-actual validation over a whole run (edit DATA_ROOT / PREDICTOR
# in the CONFIG block at the top of the script, or pass the folder directly
# if you've parameterised it):
#   DATA_ROOT = "data/raw/full_color_experiment/Cooling Run"   PREDICTOR = "color"
#   DATA_ROOT = "data/raw/black_and_color_experiment/Heating Run"  PREDICTOR = "black"
python src/temperature/batch_temperature_validation.py

# Single-image interactive viewer: edit REF_IMAGE_PATH / IMG_IMAGE_PATH in the
# CONFIG block at the top of color_merged.py, e.g.
#   IMG_IMAGE_PATH = "data/raw/full_color_experiment/Heating Run/40/img_01.jpg"
# then run:
python src/temperature/color_merged.py
```

## Supporting data and output folders

### `data/processed/csv_files/` — calibration tables

The tables consumed by both pipelines at run time, plus the raw load-cell
logs and derived color-calibration variants they were built from:

- `force_vs_mean_depth.csv` — force → indentation depth (used by
  `estimate_force_depth.py` / `uniform_reconstruct.py`).
- `force_vs_mean_width_ratio_frequency.csv` — stripe-period ratio → force fit
  data. (`estimate_force_depth.py`'s default `RATIO_CSV` points at
  `force_vs_mean_width_ratio.csv`; pass `--ratio-csv
  data/processed/csv_files/force_vs_mean_width_ratio_frequency.csv`
  explicitly, or rename the file, until the default is updated to match.)
- `liamtestforce-Run-*.csv` — raw load-cell run logs used to derive the
  force/ratio and force/depth calibration curves above.
- `average_temps.csv` / `average_temps_black.csv` — the color→temperature
  calibration tables used by `ColorPredictor` / `BlackPredictor`
  respectively (each with a `Temperature` column plus R/G/B, H/S/V, and
  L/a/b columns).
- `average_temps_color_*` / `average_temps_black_*` / `average_temps_l_*` —
  per-run and per-color-space variants (heating/cooling, "l" = L value in LAB)
  used during calibration development and validation; not required by the
  main scripts but kept for reproducing the calibration analysis.

### `data/masks/` — ROI and segmentation masks

- `roi_mask_width_stripe.png` — the calibration-circle ROI mask used by
  `uniform_reconstruct.py` (`CALIB_MASK_PATH`) for the tactile area
  correction.
- `black_color_mask.jpg` — the stripe-color mask used by
  `batch_temperature_validation.py` (`MASK_PATH`) to isolate the pixels
  in the raw data from the Black and Color experiments. Used in order to 
  avoid any flawed pixels
- `color_mask.png` — companion mask for the Full Color experiments.

### `data/raw/final_images/` and `results/images_report/` — example run and report figures

- `data/raw/final_images/` — one example `reference`/`deformed` image pair
  (`ref_image.jpg`, `def_image.jpg`) used to generate the walkthrough
  figures aboce; a convenient pair to try the pipeline on without digging
  through the experiment folders.
- `results/images_report/` — figures produced by the pipelines
  (shape/force/depth reconstructions, 3-D plots, color-prediction and
  segmentation plots) and used directly in the thesis write-up: `figures/`
  (per-pipeline result figures), `figures_final/` (the final selected
  figures, generated from the `data/raw/final_images/` pair), and
  `3d_recon/` (rendered 3-D reconstructions per contact shape). These are
  outputs, not inputs — regenerate them by running the scripts above with
  `-o` pointed at this folder.

## Requirements

Python 3 with: `numpy`, `opencv-python`, `scipy`, `scikit-image`,
`matplotlib`, `pandas`.

## Notes

All default paths in the `CONFIG` block at the top of each script are
**relative to the repository root**, so run every command from the top of
this repository (as in the examples above) and the bundled calibration CSVs
([`data/processed/csv_files/`](#dataprocessedcsv_files--calibration-tables)),
masks ([`data/masks/`](#datamasks--roi-and-segmentation-masks)), and sample
images resolve automatically — no path edits needed to reproduce the
included results.

A few `REF_IMAGE` / `DEF_IMAGE` (or `REF_IMAGE_PATH` / `IMG_IMAGE_PATH`)
defaults in `tactile/uniform_reconstruct.py`, `temperature/color_merged.py`,
and `temperature/color_segment.py` are left **blank** — they originally
pointed at development photos outside this repository that aren't bundled here. 
Point these at any reference/deformed
pair under [`data/raw/`](#image-folders) before running those scripts
standalone, or use the corresponding CLI flags (`--reference`, `--deformed`)
where available.  


