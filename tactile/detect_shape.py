#!/usr/bin/env python3
"""
detect_shape.py — Detect the shape of an object pressed into an elastomer
with a striped grating, from a (reference, deformed) image pair.

Method (Fourier Transform Profilometry, FTP):
  1. Crop a centred square ROI from both images and downsample.
  2. Complex-demodulate the fringe carrier of each image:
       - FFT, isolate the +1 carrier lobe with a Gaussian band-pass,
       - inverse FFT  -> analytic field  z = A * exp(i*phi),
       - multiply by exp(-i*2*pi*f0.r) to remove the carrier ramp.
  3. Phase difference  dphi = unwrap( angle( z_def * conj(z_ref) ) ).
     dphi is proportional to the out-of-plane deformation of the membrane.
  4. High-pass dphi (subtract a large-sigma Gaussian) to remove the global
     bulge/tilt; what remains is the local indentation footprint.
  5. Robust z-score using a background-only MAD estimate, automatic sign
     selection, hysteresis thresholding, morphological clean-up and
     contour smoothing -> binary mask of the pressed shape.

Optional auxiliary channels (off by default; the phase channel alone is
the cleanest on the test data, but these can help on weak contacts):
  --use-orient : structure-tensor fringe-orientation anomaly vs reference
  --use-amp    : fringe-modulation (amplitude) drop vs reference

Usage:
  python detect_shape.py reference.jpg deformed.jpg -o out_dir
  python detect_shape.py ref.jpg def.jpg --size 1024 --debug
"""

import argparse
import os

import cv2
import numpy as np
from scipy.ndimage import binary_fill_holes
from skimage.filters import apply_hysteresis_threshold
from skimage.restoration import unwrap_phase

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
REF_IMAGE = "C:/Users/liamg/OneDrive/Documents/EPFL Master/Thesis/Good Pictures/Ring/WIN_20260610_16_26_11_Pro.jpg"
DEF_IMAGE = "C:/Users/liamg/OneDrive/Documents/EPFL Master/Thesis/Good Pictures/Ring/WIN_20260610_16_26_31_Pro.jpg"
OUTPUT_PATH = "output/recon"
STEM = "star"


# ----------------------------------------------------------------------
# Parameters
# ----------------------------------------------------------------------
CROP_RATIO = 0.31     # centred square crop, fraction of min(h, w)
PROC_SIZE = 768       # working resolution (px); fringes stay well sampled
HP_SIGMA_FRAC = 0.117  # high-pass sigma as fraction of PROC_SIZE (~90 px @768)
SMOOTH_SIGMA_FRAC = 0.008  # post-smoothing of the score (~6 px @768)
ROI_RADIUS_FRAC = 0.45     # circular analysis mask radius (fraction of size)
HYST_LO, HYST_HI = 2.2, 4.0   # hysteresis thresholds in robust-sigma units
MIN_PEAK_Z = 3.5      # below this peak z-score, declare "no contact"
HI_PEAK_FRAC = 0.45   # adaptive seed threshold = HI_PEAK_FRAC * peak (capped)
TIGHT_LO_FRAC = 0.35  # tight mode: hysteresis floods only down to this
                      # fraction of the peak (instead of a fixed 2.2 sigma)
STRAIN_SIGMA = 8      # smoothing of the strain (|grad dphi|) channel
STRAIN_WEIGHT = 1.0   # contribution of the strain channel to the score
DIPOLE_LO, DIPOLE_HI = 0.4, 0.7   # lobe-peak ratio gating for straight presses
RING_BRIDGE_FRAC = 0.09   # extra closing (dipole mode) to bridge edge arcs
SEAM_RING_FRAC = 0.025    # dilation used to sample a hole's boundary evidence
SEAM_Z = 1.0              # |z| level that counts as signed evidence
SEAM_MIN_FRAC = 0.15      # both signs must exceed this fraction -> seam
CLOSE_FRAC = 0.027    # morphological closing kernel (fraction of size)
OPEN_FRAC = 0.012     # morphological opening kernel
MIN_COMP_FRAC = 0.04  # keep components >= this fraction of the largest one
MIN_COMP_ABS = 4e-4   # ... and >= this fraction of the full frame (absolute floor)
HOLE_FILL_FRAC = 0.15  # fill holes smaller than this fraction of the mask
FINAL_SMOOTH_FRAC = 0.008  # mask boundary smoothing sigma


# ----------------------------------------------------------------------
# ROI crop (user-supplied)
# ----------------------------------------------------------------------
def crop_roi(bgr, crop_ratio=CROP_RATIO):
    """Centred square crop -> float32 grayscale."""
    h, w = bgr.shape[:2]
    cx, cy = w // 2, h // 2
    r = int(min(h, w) * crop_ratio)
    crop = bgr[cy - r:cy + r, cx - r:cx + r]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return gray, r, gray.shape[0]


def load_roi(path, size=PROC_SIZE, crop_ratio=CROP_RATIO):
    bgr = cv2.imread(path)
    if bgr is None:
        raise FileNotFoundError(path)
    gray, _, _ = crop_roi(bgr, crop_ratio)
    return cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)


# ----------------------------------------------------------------------
# FTP demodulation
# ----------------------------------------------------------------------
def find_carrier(gray):
    """Locate the fringe-carrier peak in the FFT magnitude (half-plane)."""
    n = gray.shape[0]
    win = np.outer(np.hanning(n), np.hanning(n))
    F = np.fft.fftshift(np.fft.fft2((gray - gray.mean()) * win))
    mag = np.abs(F).copy()
    c = n // 2
    mag[c - 5:c + 6, c - 5:c + 6] = 0.0          # suppress DC
    iy, ix = np.unravel_index(np.argmax(mag), mag.shape)
    fy, fx = iy - c, ix - c
    if fy > 0 or (fy == 0 and fx < 0):           # consistent half-plane
        fy, fx = -fy, -fx
    return F, (fy, fx)


def demodulate(gray, carrier=None, bw_frac=0.55):
    """Return complex fringe field with the carrier ramp removed.

    carrier : (fy, fx) in FFT bins, or None to auto-detect.
    bw_frac : Gaussian band-pass sigma as a fraction of |carrier|.
    """
    n = gray.shape[0]
    F, auto = find_carrier(gray)
    fy, fx = carrier if carrier is not None else auto
    c = n // 2
    fr = np.hypot(fy, fx)
    sig = max(fr * bw_frac, 2.0)
    Y, X = np.ogrid[:n, :n]
    H = np.exp(-(((Y - (c + fy)) ** 2 + (X - (c + fx)) ** 2)) / (2 * sig ** 2))
    z = np.fft.ifft2(np.fft.ifftshift(F * H))
    yy, xx = np.mgrid[:n, :n]
    z *= np.exp(-2j * np.pi * (fy * yy + fx * xx) / n)
    return z, (fy, fx)


# ----------------------------------------------------------------------
# Robust statistics
# ----------------------------------------------------------------------
def robust_z(x, roi, n_iter=4):
    """Z-score with an iteratively refined background-only MAD scale.

    Without the iteration the contact region inflates the scale estimate
    and large indentations get under-scored.
    """
    x = x - np.median(x[roi])
    a = np.abs(x[roi])
    # initialise from the quietest 60% of pixels so that a large/deep contact
    # cannot inflate the scale estimate (which would deflate all z-scores)
    s = np.median(a[a < np.percentile(a, 60)]) * 1.4826 + 1e-9
    for _ in range(n_iter):
        bg = roi & (np.abs(x) < 3 * s)
        if bg.sum() < 100:
            break
        s = np.median(np.abs(x[bg])) * 1.4826 + 1e-9
    return x / s


# ----------------------------------------------------------------------
# Optional auxiliary channels
# ----------------------------------------------------------------------
def orientation_anomaly(gray_def, gray_ref, sigma_i=12):
    """Structure-tensor fringe-orientation difference (double-angle)."""
    def tensor(g):
        gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=5)
        gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=5)
        jxx = cv2.GaussianBlur(gx * gx, (0, 0), sigma_i)
        jyy = cv2.GaussianBlur(gy * gy, (0, 0), sigma_i)
        jxy = cv2.GaussianBlur(gx * gy, (0, 0), sigma_i)
        return np.arctan2(2 * jxy, jxx - jyy)        # double-angle orientation
    a_r, a_d = tensor(gray_ref), tensor(gray_def)
    dor = np.abs(np.angle(np.exp(1j * (a_d - a_r))))
    return cv2.GaussianBlur(dor.astype(np.float32), (0, 0), 6)


def amplitude_drop(z_def, z_ref):
    """Log ratio of fringe modulation amplitude (contact blurs fringes)."""
    a = np.log(np.abs(z_def) + 1e-6) - np.log(np.abs(z_ref) + 1e-6)
    return -cv2.GaussianBlur(a.astype(np.float32), (0, 0), 6)


# ----------------------------------------------------------------------
# Main detection
# ----------------------------------------------------------------------
def detect(ref_path, def_path, size=PROC_SIZE, crop_ratio=CROP_RATIO,
           use_orient=False, use_amp=False, tight=False):
    """tight=False (default): segment the full deformation FOOTPRINT (the
    membrane halo extends well beyond the indenter, and the force pipeline's
    CALIB_FOOTPRINT_SCALE is calibrated against exactly this behaviour).

    tight=True: segment the INDENTER CONTACT instead. The footprint mask is
    found exactly as in default mode (so no contact is missed), then each
    connected contact is cut back to score > TIGHT_LO_FRAC of ITS OWN peak —
    a deep press cannot balloon into its halo, and a shallow contact is not
    judged against a deeper one's peak. Use for shape recognition; do NOT
    feed into the area-corrected force chain without re-measuring
    CALIB_FOOTPRINT_SCALE (that constant was calibrated on footprints)."""
    g_ref = load_roi(ref_path, size, crop_ratio)
    g_def = load_roi(def_path, size, crop_ratio)

    # demodulate both with the *same* carrier (taken from the reference)
    z_ref, carrier = demodulate(g_ref)
    z_def, _ = demodulate(g_def, carrier=carrier)

    n = size
    yy, xx = np.mgrid[:n, :n]
    roi = np.hypot(yy - n / 2, xx - n / 2) < n * ROI_RADIUS_FRAC

    # --- phase-difference channel -------------------------------------
    dphi = unwrap_phase(np.angle(z_def * np.conj(z_ref))).astype(np.float32)
    hp = dphi - cv2.GaussianBlur(dphi, (0, 0), HP_SIGMA_FRAC * n)
    hp = cv2.GaussianBlur(hp, (0, 0), max(SMOOTH_SIGMA_FRAC * n, 1.5))
    zp = robust_z(hp, roi)

    # The FTP phase measures the in-plane displacement of the grating along
    # the carrier normal. A tilted/dragging press shifts the whole contact one
    # way (a single-signed lobe surrounded by a weak opposite-sign rebound
    # halo), but a straight-down press makes material flow outward from the
    # contact: the phase is antisymmetric (+ and - lobes of comparable
    # strength with a zero-crossing seam through the middle).
    #
    # Strategy: always use the dominant-sign lobe; include the opposite-sign
    # lobe only to the extent its peak is comparable to the dominant one
    # (lobe-peak ratio gating). Measured ratios: dragged presses 0.13-0.31,
    # straight press 0.87, so the gate ramps over DIPOLE_LO..DIPOLE_HI.
    s_pos = np.maximum(zp, 0.0)
    s_neg = np.maximum(-zp, 0.0)
    p_pos = float(np.percentile(s_pos[roi], 99.9))
    p_neg = float(np.percentile(s_neg[roi], 99.9))
    if p_pos >= p_neg:
        s_dom, s_opp, sign = s_pos, s_neg, 1.0
        ratio = p_neg / max(p_pos, 1e-9)
    else:
        s_dom, s_opp, sign = s_neg, s_pos, -1.0
        ratio = p_pos / max(p_neg, 1e-9)
    w_opp = float(np.clip((ratio - DIPOLE_LO) / (DIPOLE_HI - DIPOLE_LO), 0, 1))
    score = np.maximum(s_dom, w_opp * s_opp)

    # Strain channel: |grad(dphi_highpass)|. Strain is large throughout the
    # contact area regardless of the displacement sign, so it fills in the
    # zero-crossing seam of straight-down presses. It also smears slightly
    # outside contact edges, so it is gated by the same dipole weight: only
    # straight presses need it, dragged presses are cleaner without it.
    if w_opp > 0:
        gx = cv2.Sobel(hp, cv2.CV_32F, 1, 0, ksize=5)
        gy = cv2.Sobel(hp, cv2.CV_32F, 0, 1, ksize=5)
        strain = cv2.GaussianBlur(np.hypot(gx, gy), (0, 0), STRAIN_SIGMA)
        z_strain = robust_z(strain, roi)
        score = np.maximum(score,
                           w_opp * STRAIN_WEIGHT * np.maximum(z_strain, 0.0))

    # --- optional channels ---------------------------------------------
    if use_orient:
        zo = robust_z(orientation_anomaly(g_def, g_ref), roi)
        score = score + 0.5 * np.maximum(zo, 0.0)
    if use_amp:
        za = robust_z(amplitude_drop(z_def, z_ref), roi)
        score = score + 0.4 * np.maximum(za, 0.0)

    score[~roi] = 0.0

    # --- threshold + clean-up ------------------------------------------
    # Adaptive hysteresis: the absolute z-scores depend on how much of the
    # field is disturbed, so anchor the seed threshold to the score peak.
    # A fixed seed (e.g. 4.0) creates a cliff: a slightly weaker or deeper
    # press drops the peak below it and the mask collapses to empty even
    # though the (display-normalised) score map looks fine.
    peak = float(np.percentile(score[roi], 99.9))
    if peak < MIN_PEAK_Z:
        print(f"WARNING: peak score {peak:.2f} < {MIN_PEAK_Z} - no reliable "
              f"contact detected; returning empty mask")
        empty = np.zeros_like(score, np.uint8)
        return {"mask": empty, "score": score, "dphi": dphi, "ref": g_ref,
                "def": g_def, "roi": roi, "carrier": carrier, "sign": sign,
                "peak": peak, "thresholds": (None, None)}
    hi = float(np.clip(HI_PEAK_FRAC * peak, 2.5, HYST_HI))
    lo = min(HYST_LO, 0.5 * hi)
    mask = apply_hysteresis_threshold(score, lo, hi).astype(np.uint8)
    mask &= roi.astype(np.uint8)

    k_close = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (int(CLOSE_FRAC * n) | 1,) * 2)
    k_open = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (int(OPEN_FRAC * n) | 1,) * 2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k_close)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k_open)

    # keep all significant components: hysteresis already guarantees every
    # surviving component contains a >= hi seed, so size filtering only has
    # to reject tiny fragments. Works for any number of contact points.
    n_cc, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    keep = np.zeros_like(mask)
    n_kept = 0
    if n_cc > 1:
        order = np.argsort(-stats[1:, cv2.CC_STAT_AREA]) + 1
        a0 = stats[order[0], cv2.CC_STAT_AREA]
        floor = max(MIN_COMP_FRAC * a0, MIN_COMP_ABS * mask.size)
        for o in order:
            if stats[o, cv2.CC_STAT_AREA] >= floor:
                keep[lab == o] = 1
                n_kept += 1
    mask = keep

    # Flat indenters pressed straight down pin the material inside the
    # contact: nearly all signal sits in two opposite-sign crescents at the
    # contact edge, separated by a zero-crossing seam. Bridge the arcs with
    # a generous closing (dipole mode only, so dragged shapes keep their
    # concavities), then decide each enclosed hole by its boundary evidence.
    if w_opp > 0:
        k_bridge = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (int(RING_BRIDGE_FRAC * n) | 1,) * 2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k_bridge)

    # Conditional hole filling. A hole is a *seam artifact* (fill it) if its
    # boundary touches strong evidence of BOTH signs - the + crescent on one
    # side and the - crescent on the other. A *genuine* indenter hole (e.g.
    # the annulus) is bordered by single-signed contact evidence (keep it).
    # Small holes are always filled.
    zp_signed = sign * zp
    filled = binary_fill_holes(mask).astype(np.uint8)
    holes = filled & ~mask
    n_h, h_lab, h_stats, _ = cv2.connectedComponentsWithStats(holes)
    k_ring = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (int(SEAM_RING_FRAC * n) | 1,) * 2)
    for i in range(1, n_h):
        small = h_stats[i, cv2.CC_STAT_AREA] < HOLE_FILL_FRAC * max(mask.sum(), 1)
        if not small:
            ring = (cv2.dilate((h_lab == i).astype(np.uint8), k_ring) > 0) & (mask > 0)
            if ring.sum() == 0:
                continue
            pos_frac = float((zp_signed[ring] > SEAM_Z).mean())
            neg_frac = float((zp_signed[ring] < -SEAM_Z).mean())
            seam = min(pos_frac, neg_frac) > SEAM_MIN_FRAC
        if small or seam:
            mask[h_lab == i] = 1

    # --- tight mode: per-contact peak-relative cut ----------------------
    # The footprint above includes the membrane halo (the surface drapes far
    # beyond the indenter edge, and on a strong press the halo rises well
    # above the fixed lo threshold). Cut each contact back to the pixels
    # scoring > TIGHT_LO_FRAC of that contact's own peak; using the LOCAL
    # peak keeps shallow contacts that a global-peak cut would erase.
    if tight:
        n_cc2, lab2 = cv2.connectedComponents(mask)
        refined = np.zeros(mask.shape, bool)
        for i in range(1, n_cc2):
            comp = lab2 == i
            local_peak = float(np.percentile(score[comp], 99.5))
            keep_c = comp & (score > TIGHT_LO_FRAC * local_peak)
            # close + fill INSIDE the component: the cut can leave disjoint
            # crescents / hollow flat-press interiors; genuine indenter holes
            # (e.g. the annulus) are already absent from comp, so the final
            # "& comp" cannot re-introduce them
            keep_c = cv2.morphologyEx(keep_c.astype(np.uint8),
                                      cv2.MORPH_CLOSE, k_close) > 0
            keep_c = binary_fill_holes(keep_c) & comp
            # drop speckle: any genuine contact occupies a decent fraction
            # of its own footprint (still allows one merged footprint to
            # split into two comparable contacts)
            n_s, s_lab, s_stats, _ = cv2.connectedComponentsWithStats(
                keep_c.astype(np.uint8))
            for j in range(1, n_s):
                if s_stats[j, cv2.CC_STAT_AREA] < MIN_COMP_FRAC * comp.sum():
                    keep_c[s_lab == j] = False
            refined |= keep_c
        mask = cv2.morphologyEx(refined.astype(np.uint8), cv2.MORPH_OPEN,
                                k_open)

    # smooth the boundary -> blobby contour
    sm = cv2.GaussianBlur(mask.astype(np.float32), (0, 0),
                          max(FINAL_SMOOTH_FRAC * n, 1.5))
    mask = (sm > 0.5).astype(np.uint8)

    # recount contacts on the final mask (bridging may have merged arcs)
    n_kept = max(cv2.connectedComponents(mask)[0] - 1, 0)

    return {
        "mask": mask, "score": score, "dphi": dphi,
        "ref": g_ref, "def": g_def, "roi": roi,
        "carrier": carrier, "sign": sign,
        "peak": peak, "thresholds": (lo, hi), "n_contacts": n_kept,
        "lobe_ratio": ratio, "w_opp": w_opp,
    }


# ----------------------------------------------------------------------
# Output rendering
# ----------------------------------------------------------------------
def render_outputs(res, out_dir, stem):
    os.makedirs(out_dir, exist_ok=True)
    n = res["mask"].shape[0]

    # 1. raw binary mask
    cv2.imwrite(os.path.join(out_dir, f"{stem}_mask.png"), res["mask"] * 255)

    # 2. located-shape figure (white disc + dark-green blob)
    canvas = np.full((n, n, 3), 255, np.uint8)
    yy, xx = np.mgrid[:n, :n]
    disc = np.hypot(yy - n / 2, xx - n / 2) < n * ROI_RADIUS_FRAC
    canvas[disc] = (242, 247, 244)                     # very light green-white
    canvas[res["mask"] > 0] = (23, 64, 23)             # dark green (BGR)
    cv2.circle(canvas, (n // 2, n // 2), int(n * ROI_RADIUS_FRAC),
               (90, 90, 90), 2, cv2.LINE_AA)
    cv2.imwrite(os.path.join(out_dir, f"{stem}_located.png"), canvas)

    # 3. overlay on the deformed image
    g = cv2.normalize(res["def"], None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    over = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    cnts, _ = cv2.findContours(res["mask"], cv2.RETR_LIST,
                               cv2.CHAIN_APPROX_SIMPLE)
    tint = over.copy()
    tint[res["mask"] > 0] = (0, 200, 0)
    over = cv2.addWeighted(over, 0.65, tint, 0.35, 0)
    cv2.drawContours(over, cnts, -1, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.imwrite(os.path.join(out_dir, f"{stem}_overlay.png"), over)

    # 4. diagnostic panel
    def to8(x, pmin=1, pmax=99):
        lo, hi = np.percentile(x, [pmin, pmax])
        return np.clip((x - lo) / (hi - lo + 1e-9) * 255, 0, 255).astype(np.uint8)
    panel = np.hstack([
        cv2.cvtColor(to8(res["def"]), cv2.COLOR_GRAY2BGR),
        cv2.applyColorMap(to8(res["dphi"]), cv2.COLORMAP_TWILIGHT_SHIFTED),
        cv2.applyColorMap(to8(res["score"], 0, 99.5), cv2.COLORMAP_MAGMA),
        cv2.cvtColor(res["mask"] * 255, cv2.COLOR_GRAY2BGR),
    ])
    cv2.imwrite(os.path.join(out_dir, f"{stem}_debug.png"), panel)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--size", type=int, default=PROC_SIZE,
                    help="working resolution (default %(default)s)")
    ap.add_argument("--crop-ratio", type=float, default=CROP_RATIO)
    ap.add_argument("--use-orient", action="store_true",
                    help="add structure-tensor orientation channel")
    ap.add_argument("--use-amp", action="store_true",
                    help="add fringe-amplitude-drop channel")
    ap.add_argument("--tight", action="store_true",
                    help="peak-relative thresholds: segment the indenter "
                         "contact instead of the deformation footprint")
    args = ap.parse_args()

    res = detect(REF_IMAGE, DEF_IMAGE, size=args.size,
                 crop_ratio=args.crop_ratio,
                 use_orient=args.use_orient, use_amp=args.use_amp,
                 tight=args.tight)
    stem = STEM
    render_outputs(res, OUTPUT_PATH, stem)
    area = res["mask"].sum() / res["roi"].sum() * 100
    print(f"carrier (fy,fx) = {res['carrier']}, sign = {res['sign']:+.0f}, "
          f"contact area = {area:.1f}% of ROI")
    print(f"outputs written to {OUTPUT_PATH}/{stem}_(mask|located|overlay|debug).png")


if __name__ == "__main__":
    main()
