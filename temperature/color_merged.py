import cv2
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('TkAgg')  # Use TkAgg for interactive popups; change to 'Qt5Agg' if needed
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from scipy.signal import find_peaks, savgol_filter
from scipy.ndimage import median_filter, gaussian_filter

from color_prediction import ColorPredictor
from black_prediction import BlackPredictor


# ====================================================================
# Config — color_segment.py settings
# ====================================================================

REF_IMAGE_PATH  = "C:/Users/liamg/OneDrive/Pictures/Camera Roll/WIN_20260520_20_50_17_Pro.jpg"
IMG_IMAGE_PATH  = "C:/Users/liamg/OneDrive/Pictures/Camera Roll/WIN_20260522_04_31_51_Pro.jpg"

CROP_RATIO    = 0.31   # fraction of min(h,w) used as crop radius
GRATING_ANGLE = 0      # degrees — set to your actual grating angle if needed
SIGMA         = 30     # Gaussian blur sigma to suppress grating stripes
THRESHOLD     = 0.7    # z-score threshold for bright/dark segmentation
MORPH_SIZE    = 40     # morphological kernel size (pixels)

# ====================================================================
# Config — color_segmentation_model.py settings
# ====================================================================
COLOR_CSV_PATH  = "C:/Users/liamg/OneDrive/Documents/EPFL Master/Thesis/Code/csv_files/average_temps.csv"
BLACK_CSV_PATH  = "C:/Users/liamg/OneDrive/Documents/EPFL Master/Thesis/Code/csv_files/average_temps_black.csv"

SMOOTH_WIN    = 21
SMOOTH_POLY   = 3
MIN_PEAK_DIST = 12
MIN_PEAK_PROM = 6
VERT_SMOOTH   = 5
MORPH_OPEN_K  = (3, 5)
MORPH_CLOSE_K = (3, 9)

SAMPLE_RADIUS = 5
N_NEIGHBORS   = 3
TARGET_COL    = "Temperature"
COLOR_SPACE   = "auto"   # 'auto' picks the best of RGB/HSV/LAB per click
BLACK_COLOR_SPACE = "auto"


# ====================================================================
# Shared helpers
# ====================================================================

def rotate_image(img, angle):
    """Rotate image around its centre; angle in degrees."""
    if angle == 0.0:
        return img
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REFLECT)


# ====================================================================
# Part 1 — Flatfield segmentation (from color_segment.py)
# ====================================================================

def crop_roi(bgr, crop_ratio=CROP_RATIO):
    """Crop a square centred on the image and return float32 grayscale."""
    h, w = bgr.shape[:2]
    cx, cy = w // 2, h // 2
    r = int(min(h, w) * crop_ratio)
    crop = bgr[cy - r:cy + r, cx - r:cx + r]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gray = rotate_image(gray, GRATING_ANGLE)
    return gray, r, gray.shape[0]


def run_flatfield_segmentation(ref_bgr, img_bgr):
    """
    Run flatfield correction + z-score segmentation on the cropped ROI.
    Returns the cleaned bright mask, the cropped colour images, and the radius r.
    """
    ref_g, r, side = crop_roi(ref_bgr)
    img_g, _,    _ = crop_roi(img_bgr)

    h, w   = ref_g.shape
    cx, cy = w // 2, h // 2
    r_outer = int(min(h, w) * 0.48)
    r_inner = int(min(h, w) * 0.02)

    Y, X = np.ogrid[:h, :w]
    dist        = np.sqrt((X - cx)**2 + (Y - cy)**2)
    circle_mask = (dist < r_outer) & (dist > r_inner)

    # Flatfield correction
    ratio    = img_g / (ref_g + 1e-3)
    ratio_lp = gaussian_filter(ratio, sigma=SIGMA)

    # Z-score within circular ROI
    roi_vals = ratio_lp[circle_mask]
    mean_val = float(np.mean(roi_vals))
    std_val  = float(np.std(roi_vals))

    zscore = np.zeros_like(ratio_lp)
    zscore[circle_mask] = (ratio_lp[circle_mask] - mean_val) / (std_val + 1e-6)

    bright_mask = (zscore > THRESHOLD) & circle_mask

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MORPH_SIZE, MORPH_SIZE))

    def clean(mask):
        m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
        m = cv2.morphologyEx(m,                     cv2.MORPH_OPEN,  kernel)
        return m

    bright_clean = clean(bright_mask)

    def crop_bgr(bgr, r):
        h, w = bgr.shape[:2]
        cx, cy = w // 2, h // 2
        return bgr[cy - r:cy + r, cx - r:cx + r]

    ref_crop_rgb = cv2.cvtColor(crop_bgr(ref_bgr, r), cv2.COLOR_BGR2RGB)
    img_crop_rgb = cv2.cvtColor(crop_bgr(img_bgr, r), cv2.COLOR_BGR2RGB)

    return bright_clean, ref_crop_rgb, img_crop_rgb, r


def save_segmentation_output(bright_clean, ref_crop_rgb, img_crop_rgb):
    """Render the 3-panel segmentation figure and save to disk."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.patch.set_facecolor('#1a1a2e')

    def show(ax, data, title, cmap='gray', vmin=None, vmax=None):
        ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax)
        ax.set_title(title, color='white', fontsize=12, fontweight='bold')
        ax.axis('off')

    show(axes[0], ref_crop_rgb, 'Reference Image')
    show(axes[1], img_crop_rgb, 'Colored Image')

    contours_b, _ = cv2.findContours(bright_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    img_contour = img_crop_rgb.copy()
    cv2.drawContours(img_contour, contours_b, -1, (255, 120, 0), 6)
    show(axes[2], img_contour, 'Segmentation')

    plt.suptitle('Color-based Segmentation',
                 color='white', fontsize=14, fontweight='bold', y=1.01)
    plt.tight_layout()
    plt.savefig('output/color_segmentation_result.png', dpi=150,
                bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    print("Segmentation image saved → output/color_segmentation_result.png")


# ====================================================================
# Part 2 — Stripe detection (from color_segmentation_model.py)
# ====================================================================

def load_image(path):
    """Load image and return BGR, RGB, HSV versions plus the V-channel float array."""
    img_bgr = cv2.imread(path)
    if img_bgr is None:
        raise FileNotFoundError(f"Could not load image: {path}")
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    val     = img_hsv[:, :, 2].astype(float)
    H, W    = img_bgr.shape[:2]
    print(f"Loaded: {path}  ({W}×{H} px)")
    return img_bgr, img_rgb, img_hsv, val, H, W


def get_center_radius(H, W):
    cx, cy = W // 2, H // 2
    radius = int(min(H, W) * 0.35)
    return cx, cy, radius


def build_wafer_mask(H, W, cx, cy, r_eff):
    mask = np.zeros((H, W), dtype=np.uint8)
    cv2.circle(mask, (cx, cy), r_eff, 255, -1)
    return mask


def get_stripes(val, H, W, cx, cy, radius,
                smooth_win, smooth_poly, min_peak_dist, min_peak_prom,
                vert_smooth, row_step=1):
    label_map = np.full((H, W), -1, dtype=np.int8)

    y_top = max(cy - radius, 0)
    y_bot = min(cy + radius, H - 1)

    for y in range(y_top, y_bot + 1, row_step):
        dy   = y - cy
        disc = radius**2 - dy**2
        if disc <= 0:
            continue
        half      = int(np.sqrt(disc))
        x0        = max(cx - half, 0)
        x1        = min(cx + half, W)
        chord_len = x1 - x0
        if chord_len < 30:
            continue

        row_v = val[y, x0:x1]

        win = min(smooth_win, chord_len - (1 if chord_len % 2 == 0 else 0))
        if win % 2 == 0:
            win -= 1
        win = max(win, 5)
        smoothed = savgol_filter(row_v, win, smooth_poly)

        peaks,   _ = find_peaks( smoothed, distance=min_peak_dist, prominence=min_peak_prom)
        troughs, _ = find_peaks(-smoothed, distance=min_peak_dist, prominence=min_peak_prom)

        if len(peaks) == 0 and len(troughs) == 0:
            med = np.median(smoothed)
            label_map[y, x0:x1] = (row_v >= med).astype(np.int8)
            continue

        extrema = sorted(
            [(int(p), "peak")   for p in peaks  ] +
            [(int(t), "trough") for t in troughs],
            key=lambda e: e[0]
        )

        boundaries = []
        for i in range(len(extrema) - 1):
            mid   = (extrema[i][0] + extrema[i+1][0]) // 2
            label = 1 if extrema[i][1] == "peak" else 0
            boundaries.append((mid, label))

        local_labels = np.zeros(chord_len, dtype=np.uint8)
        first_label  = 1 if extrema[0][1] == "peak" else 0
        if boundaries:
            local_labels[:boundaries[0][0]] = first_label
            for i, (bx, lbl) in enumerate(boundaries):
                nxt = boundaries[i+1][0] if i + 1 < len(boundaries) else chord_len
                local_labels[bx:nxt] = 1 - lbl
            local_labels[boundaries[-1][0]:] = 1 - boundaries[-1][1]
        else:
            local_labels[:] = first_label

        label_map[y, x0:x1] = local_labels

    inside = label_map >= 0
    lf     = label_map.astype(np.float32)
    lf_sm  = median_filter(lf, size=(vert_smooth, 1))
    label_map = np.where(inside, np.round(lf_sm).astype(np.int8), np.int8(-1))

    return label_map


def build_masks(label_map, wafer_mask, morph_open_k, morph_close_k):
    purple_raw = np.where((label_map == 1) & (wafer_mask == 255), 255, 0).astype(np.uint8)
    black_raw  = np.where((label_map == 0) & (wafer_mask == 255), 255, 0).astype(np.uint8)

    k_open  = cv2.getStructuringElement(cv2.MORPH_RECT, morph_open_k)
    k_close = cv2.getStructuringElement(cv2.MORPH_RECT, morph_close_k)

    def clean(m):
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN,  k_open)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k_close)
        return cv2.bitwise_and(m, wafer_mask)

    return clean(purple_raw), clean(black_raw)


# ====================================================================
# Interactive viewer (from color_segmentation_model.py)
# ====================================================================

def classify_pixel(x, y, purple_mask, black_mask, wafer_mask):
    H, W = purple_mask.shape
    if not (0 <= y < H and 0 <= x < W):
        return "outside image"
    if wafer_mask[y, x] == 0:
        return "outside ROI"
    if purple_mask[y, x] == 255:
        return "purple stripe"
    if black_mask[y, x] == 255:
        return "black stripe"
    return "unclassified"


LABEL_STYLE = {
    "purple stripe": dict(color="#c020c0", bg="#fce8fc"),
    "black stripe":  dict(color="#1a7a8a", bg="#e0f7fa"),
    "outside ROI":   dict(color="#888888", bg="#f0f0f0"),
    "outside image": dict(color="#cc4444", bg="#fff0f0"),
    "unclassified":  dict(color="#aaaaaa", bg="#f8f8f8"),
}


def launch_interactive(img_rgb, img_bgr, purple_mask, black_mask, wafer_mask,
                       predictor=None, black_predictor=None):
    fig, ax = plt.subplots(figsize=(10, 8))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    ax.imshow(img_rgb)
    ax.set_title(
        "Click anywhere on the image to identify the stripe\n"
        "(close this window to generate the segmentation output image)",
        color="white", fontsize=13, pad=12, fontfamily="monospace"
    )
    ax.axis("off")

    legend_handles = [
        mpatches.Patch(facecolor="#c020c0", edgecolor="white", label="Purple stripe"),
        mpatches.Patch(facecolor="#1a7a8a", edgecolor="white", label="Black stripe"),
        mpatches.Patch(facecolor="#555555", edgecolor="white", label="Outside ROI"),
    ]
    ax.legend(handles=legend_handles, loc="lower right", framealpha=0.7,
              facecolor="#1a1a2e", labelcolor="white", fontsize=10)

    marker, = ax.plot([], [], "o", ms=14, mec="white", mew=2,
                      color="#ffdd00", zorder=5, alpha=0.9)
    crossh, = ax.plot([], [], "+", ms=20, mew=2, color="white", zorder=6)
    ann = ax.annotate(
        "", xy=(0, 0), xytext=(20, -30), textcoords="offset points",
        fontsize=12, fontfamily="monospace", color="white",
        bbox=dict(boxstyle="round,pad=0.5", fc="#1a1a2e", ec="white", lw=1.5),
        arrowprops=dict(arrowstyle="->", color="white", lw=1.5),
        visible=False, zorder=10,
    )

    status = fig.text(
        0.5, 0.02, "Click on the wafer to classify a pixel",
        ha="center", va="bottom",
        color="#aaaaaa", fontsize=10, fontfamily="monospace",
        transform=fig.transFigure
    )

    def on_click(event):
        if event.inaxes is not ax or event.xdata is None:
            return

        x, y  = int(round(event.xdata)), int(round(event.ydata))
        label = classify_pixel(x, y, purple_mask, black_mask, wafer_mask)
        style = LABEL_STYLE.get(label, LABEL_STYLE["unclassified"])

        marker.set_data([x], [y])
        crossh.set_data([x], [y])
        marker.set_color(style["color"])

        ann_lines = []

        if label == "purple stripe" and predictor is not None:
            avg_color, n_px = predictor.sample_neighborhood(
                img_rgb, purple_mask, cx=x, cy=y, radius=SAMPLE_RADIUS
            )
            if avg_color is not None:
                temp, _, _, cs_used, _ = predictor.predict(avg_color)
                ann_lines.append(" Color Model ")
                ann_lines.append(f" Prediction: {temp:.0f}°C ")
            else:
                ann_lines.append(" (no pixels in sample) ")

        elif label == "black stripe" and black_predictor is not None:
            avg_rgb, n_px = black_predictor.sample_neighborhood(
                img_bgr, black_mask, cx=x, cy=y, radius=SAMPLE_RADIUS
            )
            if avg_rgb is not None:
                temp, _, _, _, _ = black_predictor.predict(avg_rgb)
                ann_lines.append(" Black Model ")
                ann_lines.append(f" Prediction: {temp:.0f}°C ")
            else:
                ann_lines.append(" (no pixels in sample) ")

        else:
            ann_lines.append(f" {label} ")

        ann.set_text("\n".join(ann_lines))
        ann.xy = (x, y)
        ann.get_bbox_patch().set_facecolor(style["bg"])
        ann.get_bbox_patch().set_edgecolor(style["color"])
        ann.set_color(style["color"])
        ann.set_visible(True)

        status.set_text(f"Last click → ({x}, {y})  ·  {label}")
        status.set_color(style["color"])

        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("button_press_event", on_click)

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    plt.show()   # blocks until the window is closed


# ====================================================================
# Main — runs both parts in sequence
# ====================================================================

if __name__ == "__main__":

    # ── Part 1: Load images for stripe detection & interactive viewer ─────────
    img_bgr, img_rgb, img_hsv, val, H, W = load_image(IMG_IMAGE_PATH)

    cx, cy, radius = get_center_radius(H, W)
    wafer_mask     = build_wafer_mask(H, W, cx, cy, radius)

    print("Running row-adaptive stripe detection...")
    label_map = get_stripes(
        val, H, W, cx, cy, radius,
        smooth_win    = SMOOTH_WIN,
        smooth_poly   = SMOOTH_POLY,
        min_peak_dist = MIN_PEAK_DIST,
        min_peak_prom = MIN_PEAK_PROM,
        vert_smooth   = VERT_SMOOTH,
    )

    purple_mask, black_mask = build_masks(label_map, wafer_mask, MORPH_OPEN_K, MORPH_CLOSE_K)

    # ── Load predictors ───────────────────────────────────────────────────────
    predictor = ColorPredictor(
        csv_file    = COLOR_CSV_PATH,
        target_col  = TARGET_COL,
        color_space = COLOR_SPACE,
        n_neighbors = N_NEIGHBORS,
    )
    try:
        predictor.load_reference()
    except Exception as e:
        print(f"Warning: could not load reference CSV ({e}). "
              "Temperature prediction will be disabled.")
        predictor = None

    black_predictor = BlackPredictor(
        csv_file    = BLACK_CSV_PATH,
        target_col  = TARGET_COL,
        color_space = BLACK_COLOR_SPACE,
        n_neighbors = N_NEIGHBORS,
    )
    try:
        black_predictor.load_reference()
    except Exception as e:
        print(f"Warning: could not load black reference CSV ({e}). "
              "Black temperature prediction will be disabled.")
        black_predictor = None

    # ── Part 2: Launch interactive viewer (blocks until window is closed) ─────
    print("Launching interactive viewer — close the window to continue.")
    launch_interactive(img_rgb, img_bgr, purple_mask, black_mask, wafer_mask,
                       predictor=predictor, black_predictor=black_predictor)

    # ── Part 3: Run flatfield segmentation and save output image ─────────────
    print("Generating segmentation output image...")
    ref_bgr = cv2.imread(REF_IMAGE_PATH)
    seg_bgr = cv2.imread(IMG_IMAGE_PATH)

    bright_clean, ref_crop_rgb, img_crop_rgb, _ = run_flatfield_segmentation(ref_bgr, seg_bgr)
    save_segmentation_output(bright_clean, ref_crop_rgb, img_crop_rgb)

    print("All done.")