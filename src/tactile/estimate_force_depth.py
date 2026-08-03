"""
estimate_force_depth.py
=======================
Given a reference image, a deformed image, and a binary ROI mask (white
circle on black), estimates:

  * the mean stripe-width ratio inside the ROI
  * the contact force  [N]
  * the mean indentation depth  [mm]

How it works: each image's 2-D FFT gives its stripe period inside the ROI
(with sub-pixel refinement). ratio = period_deformed / period_reference.
That ratio is converted to force via a linear fit to
force_vs_mean_width_ratio.csv, and force is converted to depth via PCHIP
interpolation through force_vs_mean_depth.csv (extrapolated linearly past
the table's range).
"""

# ═══ CONFIG — edit these paths, then run ═══
REF_IMAGE = "data/raw/force_pictures/reference/img_01.jpg"
DEF_IMAGE = "data/raw/force_pictures/30N/img_01.jpg"
MASK_IMAGE   = "data/masks/roi_mask_width_stripe.png"
RATIO_CSV    = "data/processed/csv_files/force_vs_mean_width_ratio.csv"
DEPTH_CSV    = "data/processed/csv_files/force_vs_mean_depth.csv"
SHOW_PREVIEW = True   # pop up a quick visual of the FFT + ROI overlay

# ═══════════════════════════════════════════════════════════

import argparse
import os
import sys

import cv2
import numpy as np
from scipy.interpolate import PchipInterpolator


# --- 1. ROI — same logic as plot_width_change.py ---------------------

def load_roi_from_mask(mask_path):
    """Load the binary mask (white circle on black) and return its circle
    parameters for FFT measurement: (cx, cy, radius, binary_mask_array)."""
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(
            f"Cannot read mask image: {mask_path}\n"
            f"Set MASK_IMAGE in the CONFIG block, or pass --mask on the CLI."
        )
    _, binary = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("No white region found in the mask image.")
    largest = max(contours, key=cv2.contourArea)
    (cx_f, cy_f), radius_f = cv2.minEnclosingCircle(largest)
    return int(cx_f), int(cy_f), int(radius_f), binary


# --- 2. Frequency-based stripe period (true perpendicular px) ----------

def _parabolic(lm, iy, ix):
    """Sub-pixel peak refinement (parabolic fit to log magnitude)."""
    def _p(fm1, f0, fp1):
        d = fm1 - 2 * f0 + fp1
        return 0.0 if abs(d) < 1e-12 else float(
            np.clip(0.5 * (fm1 - fp1) / d, -0.5, 0.5))
    dy = _p(lm[iy - 1, ix], lm[iy, ix], lm[iy + 1, ix])
    dx = _p(lm[iy, ix - 1], lm[iy, ix], lm[iy, ix + 1])
    return dy, dx


def stripe_period_fft(img_bgr, cx, cy, cr):
    """Mean stripe period (px) inside the ROI circle, via 2-D FFT with
    sub-pixel refinement. Returns (period_px, carrier_fy, carrier_fx).
    Uses the largest square that fits inside the ROI circle, so every
    pixel used is fully inside the mask."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)

    # largest square that fits inside the ROI circle
    half = int(cr / np.sqrt(2)) - 2
    if half < 32:
        raise ValueError(f"ROI radius {cr} px is too small for FFT analysis.")
    sub = gray[cy - half:cy + half, cx - half:cx + half]
    n = min(sub.shape)
    sub = sub[:n, :n]

    win = np.outer(np.hanning(n), np.hanning(n))
    F = np.fft.fftshift(np.fft.fft2((sub - sub.mean()) * win))
    mag = np.abs(F)
    c = n // 2

    # Zero the DC region before peak search
    search = mag.copy()
    dc_r = max(6, n // 40)
    search[c - dc_r:c + dc_r + 1, c - dc_r:c + dc_r + 1] = 0.0

    iy, ix = np.unravel_index(np.argmax(search), search.shape)
    lm = np.log(mag + 1e-9)
    dy, dx = _parabolic(lm, iy, ix)
    fy = (iy - c) + dy
    fx = (ix - c) + dx

    # Enforce consistent half-plane (negative fy, or fy==0 negative fx)
    if fy > 0 or (abs(fy) < 0.5 and fx > 0):
        fy, fx = -fy, -fx

    fr = float(np.hypot(fy, fx))
    if fr < 0.5:
        raise ValueError("Could not detect a carrier peak — check the ROI.")

    period = n / fr    # true perpendicular period in px (no sin needed for FFT)
    return period, fy, fx, F, n, c


# --- 3. Calibration chain: ratio -> force -> depth ----------------------

class Calibration:
    def __init__(self, ratio_csv, depth_csv):
        import csv as _csv

        def read(path):
            with open(path, newline="", encoding="utf-8") as f:
                rows = list(_csv.reader(f))
            data = np.array([[float(v) for v in r] for r in rows[1:] if r],
                            dtype=np.float64)
            return data

        rd = read(ratio_csv)
        F_r, R = rd[:, 0], rd[:, 1]
        # Linear fit:  ratio = a + b * F   (free intercept best fits data)
        self.b_ratio, self.a_ratio = np.polyfit(F_r, R, 1)
        self.F_ratio_max = float(F_r.max())
        self.R_at_max    = float(R.max())

        dd = read(depth_csv)
        Fd, D = dd[:, 0], dd[:, 1]
        # Anchor at (0 N, 0 mm) then PCHIP
        Fd = np.concatenate([[0.0], Fd])
        D  = np.concatenate([[0.0], D])
        self._pchip      = PchipInterpolator(Fd, D, extrapolate=False)
        self.F_depth_max = float(Fd.max())
        self._D_max      = float(D.max())
        # Linear slope beyond table end (PCHIP can bend non-physically there)
        self._end_slope  = float((D[-1] - D[-4]) / (Fd[-1] - Fd[-4]))

    def force_from_ratio(self, ratio):
        """Linear calibration inverted: F = (ratio - a) / b. Clipped >= 0."""
        return max(0.0, (ratio - self.a_ratio) / self.b_ratio)

    def depth_from_force(self, force_N):
        """PCHIP interpolation; linear extrapolation beyond the table."""
        if force_N <= self.F_depth_max:
            d = float(self._pchip(min(force_N, self.F_depth_max)))
        else:
            d = self._D_max + self._end_slope * (force_N - self.F_depth_max)
        return max(0.0, d)

    def depth_from_ratio(self, ratio):
        return self.depth_from_force(self.force_from_ratio(ratio))

    def beyond_calibration(self, ratio):
        return ratio > self.R_at_max


# --- 4. Preview figure ---------------------------------------------------

def show_preview(img_ref, img_def, cx, cy, cr,
                 F_ref, F_def, period_ref, period_def,
                 ratio, force_N, depth_mm, beyond):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(17, 5))

    # Panel 1: reference image with ROI circle
    ax = axes[0]
    ax.imshow(cv2.cvtColor(img_ref, cv2.COLOR_BGR2RGB))
    th = np.linspace(0, 2 * np.pi, 300)
    ax.plot(cx + cr * np.cos(th), cy + cr * np.sin(th),
            "lime", lw=2, label="ROI")
    ax.set_title("Reference image + ROI")
    ax.axis("off"); ax.legend(loc="lower right", fontsize=8)

    # Panel 2: deformed image
    ax = axes[1]
    ax.imshow(cv2.cvtColor(img_def, cv2.COLOR_BGR2RGB))
    ax.plot(cx + cr * np.cos(th), cy + cr * np.sin(th),
            "lime", lw=2)
    ax.set_title("Deformed image + ROI")
    ax.axis("off")

    # Panel 3: measurement summary
    ax = axes[2]
    ax.axis("off")
    warn = "\n⚠ ratio beyond calibration range\n   (extrapolated)" if beyond else ""
    lines = [
        f"Stripe period — reference : {period_ref:.2f} px",
        f"Stripe period — deformed  : {period_def:.2f} px",
        "",
        f"Width ratio               : {ratio:.5f}",
        "",
        f"Estimated force           : {force_N:.1f} N",
        f"Estimated mean depth      : {depth_mm:.3f} mm",
        warn,
    ]
    ax.text(0.05, 0.95, "\n".join(lines),
            transform=ax.transAxes, va="top", ha="left",
            fontsize=13, family="monospace",
            bbox=dict(boxstyle="round,pad=0.6", fc="lightyellow",
                      ec="goldenrod", lw=1.5))
    ax.set_title("Result")
    fig.tight_layout()
    plt.show()
    plt.close(fig)


# --- 5. Main --------------------------------------------------------------

def estimate(ref_path, def_path, mask_path, ratio_csv, depth_csv,
             preview=SHOW_PREVIEW):

    cx, cy, cr, _ = load_roi_from_mask(mask_path)
    print(f"  ROI : centre ({cx}, {cy}), radius {cr} px")

    img_ref = cv2.imread(ref_path)
    img_def = cv2.imread(def_path)
    if img_ref is None:
        raise FileNotFoundError(f"Cannot read reference: {ref_path}")
    if img_def is None:
        raise FileNotFoundError(f"Cannot read deformed:  {def_path}")

    period_ref, *_ = stripe_period_fft(img_ref, cx, cy, cr)
    period_def, *_ = stripe_period_fft(img_def, cx, cy, cr)
    ratio = period_def / period_ref

    cal   = Calibration(ratio_csv, depth_csv)
    force = cal.force_from_ratio(ratio)
    depth = cal.depth_from_force(force)
    beyond = cal.beyond_calibration(ratio)

    print()
    print("=" * 48)
    print(f"  Stripe period  (reference) : {period_ref:8.3f} px")
    print(f"  Stripe period  (deformed)  : {period_def:8.3f} px")
    print(f"  Width ratio                : {ratio:8.5f}")
    print("-" * 48)
    print(f"  Estimated force            : {force:8.1f} N")
    print(f"  Estimated mean depth       : {depth:8.3f} mm")
    if beyond:
        print()
        print("  ⚠  Ratio is beyond calibration range —")
        print("     force and depth are extrapolated.")
    print("=" * 48)
    print()

    if preview:
        try:
            show_preview(img_ref, img_def, cx, cy, cr,
                         None, None, period_ref, period_def,
                         ratio, force, depth, beyond)
        except Exception as e:
            print(f"  (preview skipped: {e})")

    return {"ratio": ratio, "force_N": force, "depth_mm": depth,
            "period_ref_px": period_ref, "period_def_px": period_def,
            "beyond_calibration": beyond}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reference", default= REF_IMAGE,
                    help="reference (unloaded) image")
    ap.add_argument("--deformed", default= DEF_IMAGE,
                    help="deformed (loaded) image")
    ap.add_argument("--mask",      default=MASK_IMAGE,
                    help=f"binary ROI mask image (default: {MASK_IMAGE})")
    ap.add_argument("--ratio-csv", default=RATIO_CSV,
                    help=f"width-ratio calibration CSV (default: {RATIO_CSV})")
    ap.add_argument("--depth-csv", default=DEPTH_CSV,
                    help=f"force-vs-depth calibration CSV (default: {DEPTH_CSV})")
    ap.add_argument("--no-preview", action="store_true",
                    help="skip the matplotlib preview window")
    args = ap.parse_args()

    estimate(args.reference, args.deformed,
             args.mask, args.ratio_csv, args.depth_csv,
             preview=not args.no_preview)


if __name__ == "__main__":
    main()
