import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter

# ── Config ──────────────────────────────────────────────────────────────────
CROP_RATIO    = 0.31   # fraction of min(h,w) used as crop radius
GRATING_ANGLE = 0    # degrees — set to your actual grating angle if needed
SIGMA         = 30     # Gaussian blur sigma to suppress grating stripes
THRESHOLD     = 0.7    # z-score threshold for bright/dark segmentation
MORPH_SIZE    = 40     # morphological kernel size (pixels)
# ────────────────────────────────────────────────────────────────────────────

def rotate_image(img, angle):
    """Rotate image around its centre; angle in degrees."""
    if angle == 0.0:
        return img
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REFLECT)

def crop_roi(bgr, crop_ratio=CROP_RATIO):
    """
    Crop a square centred on the image, convert to float32 grayscale,
    and optionally rotate to align the grating.
    Returns: (gray_float32, half-side radius r, cropped side length)
    """
    h, w = bgr.shape[:2]
    cx, cy = w // 2, h // 2
    r = int(min(h, w) * crop_ratio)
    crop = bgr[cy - r:cy + r, cx - r:cx + r]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gray = rotate_image(gray, GRATING_ANGLE)
    return gray, r, gray.shape[0]

# ── Load & crop to ROI ───────────────────────────────────────────────────────
ref_bgr = cv2.imread('C:/Users/liamg/OneDrive/Pictures/Camera Roll/WIN_20260520_20_50_16_Pro.jpg')
img_bgr = cv2.imread('C:/Users/liamg/OneDrive/Pictures/Camera Roll/WIN_20260522_04_31_56_Pro.jpg')

ref_g, r, side = crop_roi(ref_bgr)
img_g, _,    _  = crop_roi(img_bgr)

# ── Circular mask inside the cropped ROI ────────────────────────────────────
# The crop is a square of side `2r × 2r`; the disk fills it almost exactly.
h, w   = ref_g.shape
cx, cy = w // 2, h // 2
r_outer = int(min(h, w) * 0.48)   # slightly inside the square edge
r_inner = int(min(h, w) * 0.02)   # exclude centre bolt

Y, X = np.ogrid[:h, :w]
dist         = np.sqrt((X - cx)**2 + (Y - cy)**2)
circle_mask  = (dist < r_outer) & (dist > r_inner)

# ── Step 1: Flatfield correction ─────────────────────────────────────────────
ratio = img_g / (ref_g + 1e-3)

# ── Step 2: Low-pass filter (suppresses grating stripes) ────────────────────
ratio_lp = gaussian_filter(ratio, sigma=SIGMA)

# ── Debug plot: result after step 2 (Gaussian filter) ────────────────────────
fig_lp, axes_lp = plt.subplots(1, 2, figsize=(12, 6))
fig_lp.patch.set_facecolor('#1a1a2e')

def _show_lp(ax, data, title):
    # Clamp the display range to the signal inside the ROI so a few
    # divide-by-near-zero outliers don't hijack the colorbar.
    vmin, vmax = np.percentile(data[circle_mask], [1, 99])
    im = ax.imshow(data, cmap='viridis', vmin=vmin, vmax=vmax)
    ax.set_title(title, color='white', fontsize=12, fontweight='bold')
    ax.axis('off')
    cbar = fig_lp.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.yaxis.set_tick_params(color='white')
    plt.setp(plt.getp(cbar.ax.axes, 'yticklabels'), color='white')

_show_lp(axes_lp[0], ratio,    'Step 1: Flatfield ratio (pre-filter)')
_show_lp(axes_lp[1], ratio_lp, f'Step 2: Gaussian filter (sigma={SIGMA})')

plt.suptitle('After Gaussian Filter', color='white',
             fontsize=14, fontweight='bold', y=1.01)
plt.tight_layout()
fig_lp.savefig('output/gaussian_filter_result.png', dpi=150,
               bbox_inches='tight', facecolor=fig_lp.get_facecolor())

# ── Step 3: Z-score within the circular ROI ──────────────────────────────────
roi_vals = ratio_lp[circle_mask]
mean_val = float(np.mean(roi_vals))
std_val  = float(np.std(roi_vals))

zscore = np.zeros_like(ratio_lp)
zscore[circle_mask] = (ratio_lp[circle_mask] - mean_val) / (std_val + 1e-6)

# ── Step 4: Threshold ────────────────────────────────────────────────────────
bright_mask = (zscore >  THRESHOLD) & circle_mask

# ── Step 5: Morphological cleanup ────────────────────────────────────────────
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MORPH_SIZE, MORPH_SIZE))

def clean(mask):
    m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
    m = cv2.morphologyEx(m,                     cv2.MORPH_OPEN,  kernel)
    return m

bright_clean = clean(bright_mask)

# ── Visualisation ────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 6))
fig.patch.set_facecolor('#1a1a2e')

def show(ax, data, title, cmap='gray', vmin=None, vmax=None):
    ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_title(title, color='white', fontsize=12, fontweight='bold')
    ax.axis('off')

def crop_bgr(bgr, r):
    h, w = bgr.shape[:2]
    cx, cy = w // 2, h // 2
    return bgr[cy - r:cy + r, cx - r:cx + r]

ref_crop_rgb = cv2.cvtColor(crop_bgr(ref_bgr, r), cv2.COLOR_BGR2RGB)
img_crop_rgb = cv2.cvtColor(crop_bgr(img_bgr, r), cv2.COLOR_BGR2RGB)

show(axes[0], ref_crop_rgb, 'Reference Image')
show(axes[1], img_crop_rgb, 'Colored Image')

# Contours drawn on the cropped colour image
contours_b, _ = cv2.findContours(bright_clean, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
img_contour = img_crop_rgb.copy()
cv2.drawContours(img_contour, contours_b, -1, (255, 120, 0), 6)
show(axes[2], img_contour, 'Segmentation')

plt.suptitle('Color-based Segmentation',
             color='white', fontsize=14, fontweight='bold', y=1.01)
plt.tight_layout()
plt.savefig('output/color_segmentation_result.png', dpi=150,
            bbox_inches='tight', facecolor=fig.get_facecolor())
print("Done")