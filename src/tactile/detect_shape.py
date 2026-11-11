#!/usr/bin/env python3
"""
detect_shape.py — Detects the shape of an object pressed into a striped
elastomer surface, from a (reference, deformed) image pair.

Method: measure how the pressed object distorts the stripe pattern (via
FFT phase analysis, aka Fourier Transform Profilometry), turn that
distortion into a robust z-score map, then threshold and clean it up
into a binary mask of the pressed shape.
"""

import argparse
import os

import cv2
import numpy as np
from scipy.ndimage import binary_fill_holes
from skimage.filters import apply_hysteresis_threshold
from skimage.restoration import unwrap_phase
from skimage.segmentation import (inverse_gaussian_gradient,
                                  morphological_geodesic_active_contour)


# --- Config -------------------------------------------------------------
REF_IMAGE = "data/raw/shape_pictures/Ring/img_01.jpg"
DEF_IMAGE = "data/raw/shape_pictures/Ring/img_02.jpg"
OUTPUT_PATH = "output/recon"
STEM = None


# --- Parameters -----------------------------------------------------------
CROP_RATIO = 0.31     # centred square crop, fraction of min(h, w)
PROC_SIZE = 768       # working resolution (px); fringes stay well sampled
BW_FRAC = 0.55       # band-pass width as fraction of |carrier|
HP_SIGMA_FRAC = 0.117  # high-pass sigma as fraction of PROC_SIZE (~90 px @768)
SMOOTH_SIGMA_FRAC = 0.008  # post-smoothing of the score (~6 px @768)
ROI_RADIUS_FRAC = 0.45     # circular analysis mask radius (fraction of size)
HYST_LO, HYST_HI = 2.2, 4.0   # hysteresis thresholds in robust-sigma units
MIN_PEAK_Z = 3.5      # below this peak z-score, declare "no contact"
HI_PEAK_FRAC = 0.45   # adaptive seed threshold = HI_PEAK_FRAC * peak (capped)
TIGHT_LO_FRAC = 0.35  # tight mode: flood down to this fraction of the peak
                      # instead of a fixed sigma threshold
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
MIN_COMP_ABS = 4e-4   # and at least this fraction of the whole frame (absolute floor)
HOLE_FILL_FRAC = 0.15  # fill holes smaller than this fraction of the mask
FINAL_SMOOTH_FRAC = 0.008  # mask boundary smoothing sigma

GAC_SIGMA_FRAC = 0.0026   # edge-map smoothing for the contour snap (~2 px @768)
GAC_ITERS = 20            # geodesic active contour iterations
DISP_BG_MARGIN_FRAC = 0.052  # phase background sampled this far outside the mask
DISP_SMOOTH_FRAC = 0.0052    # smoothing of the displacement field (~4 px @768)
CONTACT_PARAMS = dict(tight=True, smooth_frac=0.004, refine=True,
                      disp_alpha=0.25)


# --- ROI crop (user-supplied) --------------------------------------------
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


# --- FTP demodulation -----------------------------------------------------
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



def demodulate(gray, carrier=None, bw_frac=BW_FRAC):
    """Return the complex fringe field with the carrier ramp removed.

    carrier : (fy, fx) in FFT bins, or None to auto-detect.
    bw_frac : band-pass width as a fraction of |carrier|.
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


# --- Robust statistics -----------------------------------------------------
def robust_z(x, roi, n_iter=4):
    """Z-score using a background-only noise estimate, refined over a few
    iterations so a large contact can't inflate the scale and dilute its
    own score.
    """
    x = x - np.median(x[roi])
    a = np.abs(x[roi])
    # start from the quietest 60% of pixels, so a big contact can't skew
    # the initial scale estimate
    s = np.median(a[a < np.percentile(a, 60)]) * 1.4826 + 1e-9
    for _ in range(n_iter):
        bg = roi & (np.abs(x) < 3 * s)
        if bg.sum() < 100:
            break
        s = np.median(np.abs(x[bg])) * 1.4826 + 1e-9
    return x / s


# --- Optional auxiliary channels -------------------------------------------
def orientation_anomaly(gray_def, gray_ref, sigma_i=12):
    """Structure-tensor fringe-orientation difference (double-angle)."""
    def tensor(g):
        gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=5)
        gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=5)
        jxx = cv2.GaussianBlur(gx * gx, (0, 0), sigma_i)
        jyy = cv2.GaussianBlur(gy * gy, (0, 0), sigma_i)
        jxy = cv2.GaussianBlur(gx * gy, (0, 0), sigma_i)
        return np.arctan2(2 * jxy, jxx - jyy)     
    a_r, a_d = tensor(gray_ref), tensor(gray_def)
    dor = np.abs(np.angle(np.exp(1j * (a_d - a_r))))
    return cv2.GaussianBlur(dor.astype(np.float32), (0, 0), 6)


def amplitude_drop(z_def, z_ref):
    """Log ratio of fringe modulation amplitude (contact blurs fringes)."""
    a = np.log(np.abs(z_def) + 1e-6) - np.log(np.abs(z_ref) + 1e-6)
    return -cv2.GaussianBlur(a.astype(np.float32), (0, 0), 6)


# --- Contact-mode refinements ----------------------------------------------
def refine_contour(mask, score, roi, carrier, iters=GAC_ITERS):
    """Snap the mask boundary onto the steepest part of the score.

    A geodesic active contour pulls the boundary towards high score
    gradient, but only inside a band one fringe period wide around the
    current boundary, so it can re-place an edge without leaking into the
    halo or swallowing a contact.
    """
    if not mask.any():
        return mask
    n = mask.shape[0]
    s = score.astype(np.float64) / max(float(np.percentile(score[roi], 99.5)), 1e-9)
    edges = inverse_gaussian_gradient(s, sigma=max(GAC_SIGMA_FRAC * n, 1.0))
    snapped = morphological_geodesic_active_contour(
        edges, num_iter=iters, init_level_set=mask, smoothing=1,
        threshold="auto", balloon=0)
    period = int(round(n / np.hypot(*carrier)))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * period + 1,) * 2)
    band = (cv2.dilate(mask, k) > 0) & (cv2.erode(mask, k) == 0)
    out = mask.copy()
    out[band] = snapped[band]
    # the snap can leave pixel-sized specks or pinholes in the band; drop them
    floor = MIN_COMP_ABS * out.size
    for val in (1, 0):
        n_c, c_lab, c_stats, _ = cv2.connectedComponentsWithStats(
            (out == val).astype(np.uint8))
        for j in range(1, n_c):
                        if c_stats[j, cv2.CC_STAT_AREA] < floor:
                            out[c_lab == j] = 1 - val
    # the snap follows the fringes a little; smooth it like the final mask
    sm = cv2.GaussianBlur(out.astype(np.float32), (0, 0),
                          max(FINAL_SMOOTH_FRAC * n, 1.5))
    return (sm > 0.5).astype(np.uint8)



def compensate_displacement(mask, dphi, carrier, roi, alpha):
    """Move a mask from the deformed image back onto the undeformed membrane.

    The FTP phase change is the stripe pattern's displacement along the
    carrier, u = -dphi * n / (2 pi |f|) px, so a pressed region is imaged
    shifted along the carrier. Sampling the mask at y + alpha * u(y) * f_hat
    takes back a fraction alpha of that shift.
    """
    if alpha == 0 or not mask.any():
        return mask
    n = mask.shape[0]
    fy, fx = float(carrier[0]), float(carrier[1])
    fr = np.hypot(fy, fx)
    r = int(round(DISP_BG_MARGIN_FRAC * n))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1,) * 2)
    bg = roi & (cv2.dilate(mask, k) == 0)
    if not bg.any():
        bg = roi
    ph = cv2.GaussianBlur((dphi - np.median(dphi[bg])).astype(np.float32),
                          (0, 0), max(DISP_SMOOTH_FRAC * n, 1.0))
    u = -ph * (n / (2 * np.pi * fr))
    yy, xx = np.mgrid[:n, :n].astype(np.float32)
    map_x = (xx + alpha * (fx / fr) * u).astype(np.float32)
    map_y = (yy + alpha * (fy / fr) * u).astype(np.float32)
    warped = cv2.remap(mask.astype(np.float32), map_x, map_y, cv2.INTER_LINEAR)
    return ((warped > 0.5) & roi).astype(np.uint8)


# --- Main detection ---------------------------------------------------------

def detect(ref_path, def_path, size=PROC_SIZE, crop_ratio=CROP_RATIO,
           use_orient=False, use_amp=False, tight=False, bw_frac=None,
           smooth_frac=None, tight_lo_frac=None, refine=False,
           disp_alpha=0.0):

    """tight=False (default): segment the full deformation footprint,
    including the membrane halo around the indenter. This is what the force
    pipeline's CALIB_FOOTPRINT_SCALE expects.

    tight=True: segment just the indenter contact, cutting each contact back
    to its own peak-relative threshold. Better for shape recognition, but
    don't feed it into the area-corrected force chain without recalibrating
        CALIB_FOOTPRINT_SCALE first.

    Contact mode (shape recognition): pass **CONTACT_PARAMS. On top of the
    tight cut it keeps the score sharper (smooth_frac), snaps each boundary
    onto the steepest part of the score (refine) and moves the mask back
    onto the undeformed membrane (disp_alpha). bw_frac, smooth_frac and
    tight_lo_frac default to BW_FRAC, SMOOTH_SIGMA_FRAC and TIGHT_LO_FRAC,
    so calls that don't pass them behave exactly as before.
    """
    if bw_frac is None:
        bw_frac = BW_FRAC
    if smooth_frac is None:
        smooth_frac = SMOOTH_SIGMA_FRAC
    if tight_lo_frac is None:
        tight_lo_frac = TIGHT_LO_FRAC

    g_ref = load_roi(ref_path, size, crop_ratio)

    g_def = load_roi(def_path, size, crop_ratio)

    # use the same carrier (from the reference) for both images
    z_ref, carrier = demodulate(g_ref, bw_frac=bw_frac)
    z_def, _ = demodulate(g_def, carrier=carrier, bw_frac=bw_frac)


    n = size
    yy, xx = np.mgrid[:n, :n]
    roi = np.hypot(yy - n / 2, xx - n / 2) < n * ROI_RADIUS_FRAC

    # --- phase-difference channel -------------------------------------
    dphi = unwrap_phase(np.angle(z_def * np.conj(z_ref))).astype(np.float32)
    hp = dphi - cv2.GaussianBlur(dphi, (0, 0), HP_SIGMA_FRAC * n)
    hp = cv2.GaussianBlur(hp, (0, 0), max(smooth_frac * n, 1.5))
    zp = robust_z(hp, roi)

    # detect_shape.py already computes a full per-pixel phase map at line 173, then throws it away and keeps a binary mask. 
    # So the depth output is a flat plateau, not a height field. I'd like to recover a real height map from that phase.
    # It also gives proper contact area instead of a threshold, which everything spatially resolved depends on later.

    # Dragging shifts phase mostly one way (one dominant lobe); a straight
    # press splits it into two comparable lobes (gated by DIPOLE_LO..HI).
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

    # Strain fills the seam left by straight-down presses (sign-agnostic);
    # only add it when dipole weight indicates a straight press.
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
    # Anchor to the score's own peak — a fixed threshold would collapse
    # weak presses to an empty mask.
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

    # Surviving components already have a strong seed pixel, so this
    # filter only needs to drop tiny fragments.
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

    # Straight presses show two crescents split by a seam; bridge them
    # with a generous closing (dipole mode only, so drags keep concavities).
    if w_opp > 0:
        k_bridge = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (int(RING_BRIDGE_FRAC * n) | 1,) * 2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k_bridge)

    # A hole bordered by both +/- signal is a seam artifact (fill it); one
    # bordered by a single sign is a genuine hole (e.g. a ring) — keep it.
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
    # Cut each contact to pixels above TIGHT_LO_FRAC of ITS OWN peak, so
    # shallow contacts aren't erased by a global threshold.
    if tight:
        n_cc2, lab2 = cv2.connectedComponents(mask)
        refined = np.zeros(mask.shape, bool)
        for i in range(1, n_cc2):
            comp = lab2 == i
            local_peak = float(np.percentile(score[comp], 99.5))
            keep_c = comp & (score > tight_lo_frac * local_peak)

            # close + fill within the component to patch gaps left by the
            # cut (genuine holes aren't in `comp`, so they can't return).
            keep_c = cv2.morphologyEx(keep_c.astype(np.uint8),
                                      cv2.MORPH_CLOSE, k_close) > 0
            keep_c = binary_fill_holes(keep_c) & comp
            # drop speckle: a real contact takes up a decent share of its
            # footprint (a merged footprint can still split into two contacts)
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

    # contact mode: snap the edges, then undo the stripe displacement
    if refine:
        mask = refine_contour(mask, score, roi, carrier)
    mask = compensate_displacement(mask, dphi, carrier, roi, disp_alpha)

    # recount contacts on the final mask (bridging may have merged arcs)

    n_kept = max(cv2.connectedComponents(mask)[0] - 1, 0)

    return {
        "mask": mask, "score": score, "dphi": dphi,
        "ref": g_ref, "def": g_def, "roi": roi,
        "carrier": carrier, "sign": sign,
        "peak": peak, "thresholds": (lo, hi), "n_contacts": n_kept,
        "lobe_ratio": ratio, "w_opp": w_opp,
    }


# --- Output rendering -------------------------------------------------------
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
    ap.add_argument("--reference", default=REF_IMAGE)
    ap.add_argument("--deformed", default=DEF_IMAGE)
    ap.add_argument("--stem", default=STEM,
                    help="output file prefix (default: <folder>_<file> of "
                         "the deformed image)")
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
    ap.add_argument("--contact", action="store_true",
                    help="shape-recognition preset (CONTACT_PARAMS): tight "
                         "cut + contour snap + displacement compensation")
    args = ap.parse_args()


    opts = dict(CONTACT_PARAMS) if args.contact else dict(tight=args.tight)
    res = detect(args.reference, args.deformed, size=args.size,
                 crop_ratio=args.crop_ratio,
                 use_orient=args.use_orient, use_amp=args.use_amp, **opts)
    stem = args.stem or "_".join([
        os.path.basename(os.path.dirname(os.path.abspath(args.deformed))),
        os.path.splitext(os.path.basename(args.deformed))[0]]).replace(" ", "_")

    render_outputs(res, OUTPUT_PATH, stem)
    area = res["mask"].sum() / res["roi"].sum() * 100
    print(f"carrier (fy,fx) = {res['carrier']}, sign = {res['sign']:+.0f}, "
          f"contact area = {area:.1f}% of ROI")
    print(f"outputs written to {OUTPUT_PATH}/{stem}_(mask|located|overlay|debug).png")


if __name__ == "__main__":
    main()
