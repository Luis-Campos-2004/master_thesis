"""
Batch Temperature Validation — Predicted vs Actual

Each sub-folder of DATA_ROOT is named after its actual temperature (25, 26, 27, ...).
For every image in a folder, predicts a temperature, trims the highest/lowest
outliers, and averages the rest. Then plots predicted vs actual temperature
with error bars and a y = x reference line.

Set PREDICTOR to "color" or "black" in the CONFIG block to pick the model.
CSV columns expected (case-insensitive): Temperature, R, G, B, H, S, V, L, a, b
"""

import os
import re
import sys
import glob

import cv2
import numpy as np
import matplotlib.pyplot as plt

# Make sure the predictor modules can be imported regardless of cwd
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
from color_prediction import ColorPredictor
from black_prediction import BlackPredictor

# CONFIG — edit these paths

# Choose the model: "color" or "black"
PREDICTOR   = "black"

# Root folder containing the temperature sub-folders (25/, 26/, …)
DATA_ROOT   = "data/raw/black_and_color_experiment/Heating Run"

# Repo root (where data/masks and data/processed/csv_files live)
REPO_ROOT   = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))

MASK_PATH   = os.path.join(REPO_ROOT, "data", "masks", "black_color_mask.jpg")

# Reference CSV used for each predictor
CSV_COLOR   = os.path.join(REPO_ROOT, "data", "processed", "csv_files", "average_temps.csv")
CSV_BLACK   = os.path.join(REPO_ROOT, "data", "processed", "csv_files", "average_temps_black.csv")

TARGET_COL  = "Temperature"
COLOR_SPACE = "auto"          # "rgb" | "hsv" | "lab" | "auto"
N_NEIGHBORS = 3

N_DISCARD   = 0              # drop this many highest AND this many lowest

IMAGE_EXTS  = (".jpg", ".jpeg", ".png", ".bmp")

# ── derived from PREDICTOR (no need to edit) ──────────────────────────────────
_PREDICTORS = {"color": (ColorPredictor, CSV_COLOR),
               "black": (BlackPredictor, CSV_BLACK)}
if PREDICTOR.lower() not in _PREDICTORS:
    raise ValueError(f"PREDICTOR must be one of {list(_PREDICTORS)}, got '{PREDICTOR}'")
PREDICTOR_CLASS, CSV_PATH = _PREDICTORS[PREDICTOR.lower()]
OUT_PLOT    = os.path.join(REPO_ROOT,
                           f"{PREDICTOR}_predicted_vs_actual_temperature_{PREDICTOR.lower()}.png")

# HELPERS

def load_mask(mask_path):
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Could not load mask: {mask_path}")
    print(f"Mask loaded: {mask_path}  ({int(mask.sum() // 255):,} px, shape {mask.shape})")
    return mask


def mean_rgb_in_mask(bgr, mask):
    """Mean (R, G, B) over every pixel inside the mask. None if mask is empty."""
    if bgr.shape[:2] != mask.shape[:2]:
        mask = cv2.resize(mask, (bgr.shape[1], bgr.shape[0]),
                          interpolation=cv2.INTER_NEAREST)
    sel = mask > 0
    if not np.any(sel):
        return None
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(float)
    return rgb[sel].mean(axis=0)


# Column order for the per-folder colour summary
COLOR_CHANNELS = ("R", "G", "B", "H", "S", "V", "L", "a", "b")


def rgb_to_all_channels(avg_rgb):
    """Convert a mean (R, G, B) to the 9-vector (R,G,B,H,S,V,L,a,b), using the
    same OpenCV HSV/LAB conventions as the predictor."""
    rgb_feat, hsv_feat, lab_feat = ColorPredictor._pixel_to_all_spaces(*avg_rgb)
    return np.concatenate([rgb_feat, hsv_feat, lab_feat])


def trimmed_stats(values, n_discard):
    """Sort, drop n_discard from each end, return (mean, std_dev, kept_array)."""
    arr = np.sort(np.asarray(values, dtype=float))
    if len(arr) > 2 * n_discard:
        kept = arr[n_discard:len(arr) - n_discard]
    else:                                  # too few to trim — keep them all
        kept = arr
    mean = float(kept.mean())
    std  = float(kept.std(ddof=1))
    return mean, std, kept


# MAIN

def main():
    print(f"Predictor: {PREDICTOR.lower()}  ({PREDICTOR_CLASS.__name__})")
    predictor = PREDICTOR_CLASS(CSV_PATH, TARGET_COL,
                                color_space=COLOR_SPACE, n_neighbors=N_NEIGHBORS)
    predictor.load_reference()

    mask = load_mask(MASK_PATH)

    # Numeric sub-folders only, sorted by their numeric value
    subfolders = []
    for name in os.listdir(DATA_ROOT):
        full = os.path.join(DATA_ROOT, name)
        if os.path.isdir(full) and re.fullmatch(r"\d+(\.\d+)?", name):
            subfolders.append((float(name), name, full))
    subfolders.sort(key=lambda t: t[0])

    if not subfolders:
        sys.exit(f"No numeric temperature sub-folders found in:\n  {DATA_ROOT}")

    actuals, pred_means, pred_stds = [], [], []
    color_summaries = []          # (name, mean_9vec) per folder

    print("\n" + "=" * 64)
    print(f"{'Folder':>8} {'Actual':>8} {'Pred(mean)':>11} {'SD':>7} {'#imgs':>6}")
    print("=" * 64)

    for nominal, name, folder in subfolders:
        images = [p for p in glob.glob(os.path.join(folder, "*"))
                  if p.lower().endswith(IMAGE_EXTS)]
        images.sort()
        if not images:
            print(f"{name:>8}  (no images — skipped)")
            continue

        preds = []
        color_vecs = []
        for img_path in images:
            bgr = cv2.imread(img_path)
            if bgr is None:
                print(f"    ! could not read {os.path.basename(img_path)}")
                continue
            avg_rgb = mean_rgb_in_mask(bgr, mask)
            if avg_rgb is None:
                print(f"    ! empty mask for {os.path.basename(img_path)}")
                continue
            color_vecs.append(rgb_to_all_channels(avg_rgb))
            temp, *_ = predictor.predict(avg_rgb)
            preds.append(temp)

        if color_vecs:
            color_summaries.append((name, np.mean(color_vecs, axis=0)))

        if not preds:
            print(f"{name:>8}  (no valid predictions — skipped)")
            continue

        actual = nominal          # folder name is the actual temperature
        mean, std, kept = trimmed_stats(preds, N_DISCARD)

        actuals.append(actual)
        pred_means.append(mean)
        pred_stds.append(std)

        print(f"{name:>8} {actual:>8.1f} {mean:>11.2f} {std:>7.2f} "
              f"{len(kept):>3}/{len(preds):<2}")

    # ── per-folder average colour values (R,G,B,H,S,V,L,a,b) ──────────────────
    if color_summaries:
        print("\n" + "=" * 86)
        print("Average colour values per folder (mask-mean, averaged over all images)")
        print("=" * 86)
        header = f"{'Folder':>8} " + " ".join(f"{ch:>8}" for ch in COLOR_CHANNELS)
        print(header)
        print("-" * 86)
        for name, vec in color_summaries:
            row = f"{name:>8} " + " ".join(f"{v:>8.2f}" for v in vec)
            print(row)

    if not actuals:
        sys.exit("No data to plot.")

    actuals    = np.asarray(actuals)
    pred_means = np.asarray(pred_means)
    pred_stds  = np.asarray(pred_stds)

    # ── R² and RMSE of predicted vs actual, relative to the ideal y = x line ──
    # Color model: only fit actual temps 24-31°C. Black model: use full range.
    if PREDICTOR.lower() == "color":
        r2_mask = (actuals >= 24.0) & (actuals <= 31.0)
        r2_range = "24–31 °C"
    else:
        r2_mask = np.ones_like(actuals, dtype=bool)
        r2_range = "full range"
    a_fit = actuals[r2_mask]
    p_fit = pred_means[r2_mask]
    ss_res = float(np.sum((p_fit - a_fit) ** 2))
    ss_tot = float(np.sum((a_fit - a_fit.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    rmse = float(np.sqrt(ss_res / len(a_fit))) if len(a_fit) > 0 else float("nan")
    print(f"\nR² (predicted vs actual, about y = x, {r2_range}, "
          f"n={len(a_fit)}): {r2:.4f}")
    print(f"RMSE (predicted vs actual, {r2_range}, "
          f"n={len(a_fit)}): {rmse:.4f} °C")

    # ── plot ────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 4))

    # Ideal, perfectly-linear reference line  y = x
    lo = min(actuals.min(), pred_means.min())
    hi = max(actuals.max(), pred_means.max())
    pad = 0.05 * (hi - lo if hi > lo else 1.0)
    line = np.array([lo - pad, hi + pad])
    # Draw the y = x line across the full plotted range (fixed 23–32 for color)
    ref = np.array([23.0, 32.0]) if PREDICTOR.lower() == "color" else line
    ax.plot(ref, ref, "--", color="#888", linewidth=1.5,
            label="Ideal (y = x)", zorder=1)

    ax.errorbar(actuals, pred_means, yerr=pred_stds,
                fmt="o", color="#1f6fb2", ecolor="#1f6fb2",
                elinewidth=1.4, capsize=4, markersize=8,
                label="Predicted (mean ± SD)", zorder=3)

    ax.set_xlabel("Measured temperature (°C)", fontsize=12)
    ax.set_ylabel("Predicted temperature (°C)", fontsize=12)
    ax.set_title(f"Predicted vs Measured Temperature  (Black Model)",
                 fontsize=13)
    # Fix axes to 23-32°C for the color model so the 31°C point isn't cut off.
    if PREDICTOR.lower() == "color":
        ax.set_xlim(23.0, 32.0)
        ax.set_ylim(23.0, 32.0)
    else:
        ax.set_xlim(line)
        ax.set_ylim(line)
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.legend(fontsize=10, loc="upper left")
    fig.tight_layout()

    fig.savefig(OUT_PLOT, dpi=150)
    print("\nPlot saved →", OUT_PLOT)
    plt.show()


if __name__ == "__main__":
    main()
