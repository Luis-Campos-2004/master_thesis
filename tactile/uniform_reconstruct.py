"""
reconstruct_3d_global.py
========================
3-D reconstruction (matplotlib, mouse-rotatable) where each detected contact
SHAPE gets ONE global FFT measurement taken from its MIDDLE, and therefore
one force and one depth.  No windowed/tiled scanning.

  * The contact shape(s) come from detect_shape.detect(): every connected
    component is treated as a distinct contact, so a press with three
    objects can read e.g. 2.0 mm, 2.5 mm and 3.0 mm.
  * For each contact, the rim band is eroded away (the stripe ratio near the
    edge is kinematic artefact, not pressure) and the stripe period is
    measured by a single masked + windowed FFT over the remaining INTERIOR,
    at full camera resolution, with sub-pixel (parabolic, zero-padded) peak
    refinement.  Reference and deformed use the SAME interior mask and the
    same carrier prior, so they cannot lock onto different peaks/harmonics.
  * ratio = period_def / period_ref  ->  force  ->  depth through the
    calibration of estimate_force_depth.Calibration (your CSVs).
  * The 3-D surface is a flat plateau per contact at its calibrated depth,
    feathered at the rim — by construction, since one global measurement
    per shape carries no interior depth variation.

Requires in the same folder:  detect_shape.py, estimate_force_depth.py,
force_vs_mean_width_ratio.csv, force_vs_mean_depth.csv.

Usage:
  python reconstruct_3d_global.py                       (uses CONFIG paths)
  python reconstruct_3d_global.py --reference r.jpg --deformed d.jpg
  python reconstruct_3d_global.py --no-show -o out
"""

# ═══════════════════════════════════════════════════════════
#  CONFIG  —  edit these paths, then run (or use CLI flags)
# ═══════════════════════════════════════════════════════════

REF_IMAGE = "C:/Users/liamg/OneDrive/Pictures/Camera Roll/WIN_20260613_12_11_37_Pro.jpg"
DEF_IMAGE = "C:/Users/liamg/OneDrive/Pictures/Camera Roll/WIN_20260613_12_11_55_Pro.jpg"
RATIO_CSV = "tactile/force_vs_mean_width_ratio_frequency.csv"
DEPTH_CSV = "tactile/force_vs_mean_depth.csv"
OUTPUT_PATH = "output/recon_global"

# --- contact-area correction -------------------------------------------
# The ratio calibration CSV was acquired with a circular indenter of
# ~314 mm^2 (r = 10 mm).  The membrane responds to PRESSURE (F / A), so a
# shape with a different area produces a different stripe-ratio change for
# the same force.  To first order  (ratio - 1) is proportional to F / A, so the
# measured ratio is mapped onto the calibration circle's equivalent ratio:
#
#     ratio_equivalent = 1 + (ratio - 1) * (CONTACT_AREA_MM2 / CALIB_AREA_MM2)
#
# before the force lookup.  Set CONTACT_AREA_MM2 to the area of the shape
# you pressed with (mm^2); leave CALIB_AREA_MM2 at the calibration value.
CONTACT_AREA_MM2 = 400.0   # area of the shape used in THIS experiment (mm^2)
CALIB_AREA_MM2 = 314.0     # area of the circle used for the calibration CSVs

# --- per-shape area (handles two+ shapes with DIFFERENT areas) ----------
# Each detected contact has its own pixel area (comp.sum() in the detection
# frame). The membrane responds to pressure F/A, so the correction factor for
# each shape is just the PIXEL-AREA RATIO against the calibration circle
# (the mm-per-pixel scale is the same for both and cancels):
#
#     ratio_eq_i = 1 + (ratio_i - 1) * (area_i_px / CALIB_AREA_PX)
#
# Set CALIB_AREA_PX to the calibration circle's pixel area MEASURED IN THE SAME
# FRAME the script counts contacts in. With FULL_RES_GEOMETRY = True that frame
# is full camera resolution, so this is simply the white-pixel count of your
# full-res calibration mask (e.g. 340037). With FULL_RES_GEOMETRY = False it is
# the ~768-frame count instead - read it from the printed "area ... px".
# Leave at 0 to keep the old single-area (CONTACT_AREA_MM2) behaviour.
CALIB_AREA_PX = 0          # circle's pixel area in the detection frame; 0 -> off

# --- auto calibration area from the original ROI mask -------------------
# Instead of hard-coding CALIB_AREA_PX, point this at the binary mask that was
# used to build the ratio calibration CSV (white shape on black). Its white
# pixel count IS the calibration shape's area. The mask is centre-cropped with
# the SAME CROP_RATIO as the data and its white FRACTION is rescaled to the
# data geometry frame, so it works regardless of the mask's own resolution.
# Used only when CALIB_AREA_PX <= 0 and KNOWN_AREAS_MM2 is empty. Set to "" to
# disable (then the old single-area CONTACT_AREA_MM2 behaviour applies).
CALIB_MASK_PATH = "roi_mask_width_stripe.png"

# --- mask -> detected-footprint scale ----------------------------------
# IMPORTANT: roi_mask_width_stripe.png is the TIGHT inscribed FFT measurement
# window, whereas detect_shape segments the broader deformation footprint a
# press produces (the "halo"). On this rig the circular calibration indenter
# masks 340 037 px but detect_shape gives it a ~637 000 px footprint, i.e. the
# footprint is ~1.87x the ROI mask. Since the area correction compares each
# test shape's *detected footprint* against the calibration area, the mask area
# must be brought onto the footprint scale before use:
#       A_cal = (mask white px, in data frame) * CALIB_FOOTPRINT_SCALE
# Set this to 1.0 to use the raw mask area (this OVER-corrects here, ~40 N mean
# error). The default 1.874 matches the calibration circle's measured footprint
# and unifies circle/square to ~6 N mean error. Re-measure it for a new rig by
# running batch_validate.py and taking (mean calibration-shape footprint /
# mask white px).
CALIB_FOOTPRINT_SCALE = 1.874

# --- known areas override (optional) -----------------------------------
# If you KNOW the true area of each pressed shape, list them here in mm^2 and
# they are assigned to the detected contacts in descending-size order (largest
# detected blob -> largest listed area). This bypasses the pixel scale
# (CALIB_AREA_PX) entirely: area_factor = known_mm2 / CALIB_AREA_MM2.
# Use only when the contact area really equals these nominal areas and the
# shapes are clearly different in size (so size-order matching is unambiguous).
# Example for the square+circle pair:  KNOWN_AREAS_MM2 = [225.0, 177.0]
KNOWN_AREAS_MM2 = []       # empty -> measure each shape's area from its pixels

# --- full-resolution geometry ------------------------------------------
# detect_shape works on a downsized (~768 px) frame, so by default the mask,
# areas and depth map live in that frame. With FULL_RES_GEOMETRY = True the
# mask returned by detect_shape is upscaled to full camera resolution and ALL
# geometry (connected components, areas, distance-transform erosion, depth) is
# done full-res. The stripe FFT is already full-res either way. NOTE: this
# does not make the segmentation itself sharper (that decision is still made
# at 768 inside detect_shape) - it only puts areas/coords/depth in full-res
# pixels, so CALIB_AREA_PX must then be the circle's FULL-RES pixel count.
FULL_RES_GEOMETRY = True

ERODE_FRAC = 0.45      # interior = distance > min(30px, ERODE_FRAC * max dist)
ERODE_MAX_768 = 30     # cap (768-frame px) on the rim erosion
MIN_INTERIOR_PX = 400  # smallest usable interior (768-frame px)
FFT_PAD = 1024         # zero-padded FFT size for sub-bin peak localisation
EDGE_FEATHER = 9       # sigma (768-frame px) tapering depth at the rim
SURF_GRID = 80        # 3-D rendering grid resolution

# ═══════════════════════════════════════════════════════════

import argparse
import os

import cv2
import numpy as np

import detect_shape as ds
import estimate_force_depth as efd


# ----------------------------------------------------------------------
# Full-resolution crop (same window detect_shape uses, without downsizing)
# ----------------------------------------------------------------------
def load_crop_fullres(path):
    bgr = cv2.imread(path)
    if bgr is None:
        raise FileNotFoundError(path)
    h, w = bgr.shape[:2]
    r = int(min(h, w) * ds.CROP_RATIO)
    crop = bgr[h // 2 - r:h // 2 + r, w // 2 - r:w // 2 + r]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return gray                                   # square, side = 2r


# ----------------------------------------------------------------------
# Calibration area straight from the original ROI mask
# ----------------------------------------------------------------------
def calib_area_from_mask(mask_path, n_full):
    """White-pixel area of the calibration mask, expressed in the n_full
    geometry frame (px). The mask is centre-cropped with the same CROP_RATIO
    used on the data, then its white FRACTION is rescaled to n_full**2 so the
    result is independent of the mask file's own resolution."""
    m = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if m is None:
        raise FileNotFoundError(f"calibration mask not found: {mask_path}")
    h, w = m.shape
    r = int(min(h, w) * ds.CROP_RATIO)
    crop = m[h // 2 - r:h // 2 + r, w // 2 - r:w // 2 + r]
    frac = float((crop > 127).sum()) / float(crop.size)
    return frac * float(n_full ** 2)


# ----------------------------------------------------------------------
# Carrier prior on the reference (true fundamental, harmonic-safe)
# ----------------------------------------------------------------------
def carrier_prior(gray_full):
    """Stripe fundamental of the whole reference crop, in cycles/px.
    Small DC exclusion + walk-down to the fundamental when a comparable
    peak exists at f/k (square-wave stripes have strong odd harmonics)."""
    n = min(gray_full.shape)
    g = gray_full[:n, :n]
    win = np.outer(np.hanning(n), np.hanning(n))
    F = np.fft.fftshift(np.fft.fft2((g - g.mean()) * win))
    mag = np.abs(F)
    c = n // 2
    search = mag.copy()
    dc = 4
    search[c - dc:c + dc + 1, c - dc:c + dc + 1] = 0.0
    iy, ix = np.unravel_index(np.argmax(search), search.shape)

    def local_max_near(fy0, fx0, rad=2):
        y0, x0 = int(round(c + fy0)), int(round(c + fx0))
        if not (rad <= y0 < n - rad and rad <= x0 < n - rad):
            return None, 0.0
        wnd = search[y0 - rad:y0 + rad + 1, x0 - rad:x0 + rad + 1]
        j = np.unravel_index(np.argmax(wnd), wnd.shape)
        return (y0 - rad + j[0], x0 - rad + j[1]), float(wnd[j])

    changed = True
    while changed:
        changed = False
        pv = float(search[iy, ix])
        fy_i, fx_i = iy - c, ix - c
        for k in (2, 3, 4):
            if np.hypot(fy_i / k, fx_i / k) <= dc + 1.5:
                continue
            pos, val = local_max_near(fy_i / k, fx_i / k)
            if pos is not None and val >= 0.30 * pv:
                iy, ix = pos
                changed = True
                break

    fy, fx = iy - c, ix - c
    if fy > 0 or (fy == 0 and fx > 0):
        fy, fx = -fy, -fx
    return fy / n, fx / n                          # cycles per pixel


# ----------------------------------------------------------------------
# Masked global FFT period of one shape interior
# ----------------------------------------------------------------------
def period_masked_fft(gray_full, weight, f_cpp, pad=FFT_PAD):
    """Stripe period (px) of the region selected by `weight` (same shape as
    gray_full window): the image is multiplied by the smooth interior weight
    (Hann x eroded mask), embedded in a zero-padded array, and the carrier
    peak is searched only near the prior f_cpp (cycles/px), then refined
    parabolically.  Using one identical weight for reference and deformed
    makes the ratio insensitive to the mask's own spectral footprint."""
    h, w = weight.shape
    g = (gray_full - gray_full[weight > 0.01].mean()) * weight
    N = int(2 ** np.ceil(np.log2(max(h, w, pad // 2) * 2)))
    N = max(N, pad)
    emb = np.zeros((N, N), np.float32)
    emb[:h, :w] = g
    F = np.fft.fftshift(np.fft.fft2(emb))
    mag = np.abs(F)
    c = N // 2
    fy0, fx0 = f_cpp[0] * N, f_cpp[1] * N          # prior in padded bins
    r0 = float(np.hypot(fy0, fx0))
    yy, xx = np.ogrid[:N, :N]
    near = np.hypot((yy - c) - fy0, (xx - c) - fx0) < max(3.0, 0.20 * r0)
    m = np.where(near, mag, 0.0)
    iy, ix = np.unravel_index(np.argmax(m), m.shape)
    if m[iy, ix] <= 0:
        return None
    lm = np.log(mag + 1e-9)

    def _p(a, b, cc):
        d = a - 2 * b + cc
        return 0.0 if abs(d) < 1e-12 else float(np.clip(0.5 * (a - cc) / d,
                                                        -0.5, 0.5))
    fy = (iy - c) + _p(lm[iy - 1, ix], lm[iy, ix], lm[iy + 1, ix])
    fx = (ix - c) + _p(lm[iy, ix - 1], lm[iy, ix], lm[iy, ix + 1])
    fr = float(np.hypot(fy, fx))
    if fr < 1.0:
        return None
    return N / fr


# ----------------------------------------------------------------------
# Reconstruction
# ----------------------------------------------------------------------
def reconstruct_global(ref_path, def_path, cal, contact_area_mm2=None):
    if contact_area_mm2 is None:
        contact_area_mm2 = CONTACT_AREA_MM2
    if contact_area_mm2 <= 0:
        raise ValueError("contact_area_mm2 must be positive")
    res = ds.detect(ref_path, def_path)
    n = res["mask"].shape[0]
    mask = res["mask"] > 0
    if mask.sum() == 0:
        raise RuntimeError("no contact detected - nothing to reconstruct")

    gf_ref = load_crop_fullres(ref_path)
    gf_def = load_crop_fullres(def_path)
    N_full = gf_ref.shape[0]
    scale = N_full / n                              # 768 -> full-res factor

    # --- choose the geometry frame -------------------------------------
    # m = side of the frame all geometry (mask/areas/depth) lives in.
    # s2f maps geometry-frame coords -> full-res for the FFT windows.
    # cscale converts the 768-tuned px constants into the geometry frame.
    if FULL_RES_GEOMETRY:
        mask = cv2.resize(mask.astype(np.uint8), (N_full, N_full),
                          interpolation=cv2.INTER_NEAREST) > 0
        m = N_full
        s2f = 1.0
        cscale = scale
        deformed_img = gf_def                       # full-res, matches mask
        print(f"[global] full-res geometry: {m}x{m} px "
              f"(detect frame was {n}x{n})")
    else:
        m = n
        s2f = scale
        cscale = 1.0
        deformed_img = ds.load_roi(def_path)

    # --- resolve the calibration area (px, in the geometry frame m) -------
    # priority: explicit CALIB_AREA_PX  >  mask-derived  >  off (single area)
    calib_area_px = float(CALIB_AREA_PX)
    if calib_area_px <= 0 and not KNOWN_AREAS_MM2 and CALIB_MASK_PATH:
        a_mask = calib_area_from_mask(CALIB_MASK_PATH, m)
        calib_area_px = a_mask * CALIB_FOOTPRINT_SCALE
        print(f"[global] calibration area from mask '{CALIB_MASK_PATH}': "
              f"{a_mask:.0f} px x footprint-scale {CALIB_FOOTPRINT_SCALE:.3f} "
              f"= {calib_area_px:.0f} px (in {m}x{m} frame)")
    if calib_area_px > 0:
        print(f"[global] per-shape area mode: each contact footprint / "
              f"{calib_area_px:.0f} px -> ratio rescaled to the calibration "
              f"shape ({CALIB_AREA_MM2:.1f} mm^2)")
    else:
        print(f"[global] contact area: {contact_area_mm2:.1f} mm^2 "
              f"(calibration circle: {CALIB_AREA_MM2:.1f} mm^2, "
              f"ratio-deviation scale x{contact_area_mm2 / CALIB_AREA_MM2:.3f})")

    f_cpp = carrier_prior(gf_ref)                   # cycles/px, fundamental
    period_prior = 1.0 / float(np.hypot(*f_cpp))
    print(f"[global] carrier prior: fundamental period "
          f"{period_prior:.2f} px (full resolution)")

    n_cc, lab = cv2.connectedComponents(mask.astype(np.uint8))
    depth = np.zeros((m, m), np.float32)
    report = []
    interiors = np.zeros((m, m), np.uint8)

    # Optional: assign user-supplied true areas to components by size order
    known_map = {}
    if KNOWN_AREAS_MM2:
        sizes = sorted(((int((lab == c).sum()), c) for c in range(1, n_cc)),
                       reverse=True)                       # largest first
        known = sorted(KNOWN_AREAS_MM2, reverse=True)
        if len(known) != len(sizes):
            print(f"WARNING: KNOWN_AREAS_MM2 has {len(known)} entries but "
                  f"{len(sizes)} contacts were detected; unmatched contacts "
                  f"fall back to the pixel/global area.")
        for (a_px, c), a_mm2 in zip(sizes, known):
            known_map[c] = a_mm2
        print(f"[global] known-area mode: {known_map} (label -> mm^2)")

    for cidx in range(1, n_cc):
        comp = lab == cidx
        area = int(comp.sum())                      # geometry-frame px

        # --- middle part: erode the rim band away (adaptive) ---
        dist = cv2.distanceTransform(comp.astype(np.uint8), cv2.DIST_L2, 5)
        er = min(ERODE_MAX_768 * cscale,
                 max(4 * cscale, ERODE_FRAC * float(dist.max())))
        inner = dist > er
        if inner.sum() < MIN_INTERIOR_PX * cscale ** 2:
            inner = dist > max(2 * cscale, 0.25 * float(dist.max()))
        if inner.sum() < 50 * cscale ** 2:
            print(f"contact {cidx}: too small ({area}px) - skipped")
            continue
        interiors |= inner.astype(np.uint8) * cidx

        # --- bounding window at full resolution, weight = Hann x interior ---
        ys, xs = np.nonzero(inner)
        pad = max(1, int(round(6 * cscale)))
        y1 = max(0, ys.min() - pad); y2 = min(m, ys.max() + 1 + pad)
        x1 = max(0, xs.min() - pad); x2 = min(m, xs.max() + 1 + pad)
        Y1, Y2 = int(y1 * s2f), int(y2 * s2f)
        X1, X2 = int(x1 * s2f), int(x2 * s2f)
        sub_ref = gf_ref[Y1:Y2, X1:X2]
        sub_def = gf_def[Y1:Y2, X1:X2]
        m_full = cv2.resize(inner[y1:y2, x1:x2].astype(np.float32),
                            (sub_ref.shape[1], sub_ref.shape[0]),
                            interpolation=cv2.INTER_LINEAR)
        m_full = cv2.GaussianBlur(m_full, (0, 0), 0.15 * period_prior)
        wy = np.hanning(sub_ref.shape[0])[:, None]
        wx = np.hanning(sub_ref.shape[1])[None, :]
        weight = (m_full * wy * wx).astype(np.float32)

        p_ref = period_masked_fft(sub_ref, weight, f_cpp)
        p_def = period_masked_fft(sub_def, weight, f_cpp)
        if p_ref is None or p_def is None:
            print(f"contact {cidx}: FFT peak not found in interior - skipped")
            continue
        ratio = p_def / p_ref

        # --- per-shape area, in priority order:
        #     1) user-supplied true area for this contact (known_map),
        #     2) measured pixel area vs the calibration circle (CALIB_AREA_PX),
        #     3) single global CONTACT_AREA_MM2.
        #     Two shapes are always corrected independently. ---
        if cidx in known_map:
            shape_area_mm2 = known_map[cidx]
            area_factor = shape_area_mm2 / CALIB_AREA_MM2
        elif calib_area_px > 0:
            area_factor = area / calib_area_px          # area = comp.sum() (px)
            shape_area_mm2 = area_factor * CALIB_AREA_MM2  # for the report only
        else:
            area_factor = contact_area_mm2 / CALIB_AREA_MM2  # old single-area
            shape_area_mm2 = contact_area_mm2

        # --- area correction: map the measured ratio onto the equivalent
        #     ratio of the calibration circle (same pressure) ---
        ratio_eq = 1.0 + (ratio - 1.0) * area_factor

        force = cal.force_from_ratio(ratio_eq)
        d_mm = cal.depth_from_force(force)
        beyond = cal.beyond_calibration(ratio_eq)

        depth[comp] = d_mm
        report.append({
            "contact": cidx, "area_px": area,
            "interior_px": int(inner.sum()),
            "window_px_full": (sub_ref.shape[1], sub_ref.shape[0]),
            "period_ref_px": float(p_ref), "period_def_px": float(p_def),
            "ratio": float(ratio), "ratio_equivalent": float(ratio_eq),
            "contact_area_mm2": float(shape_area_mm2),
            "force_N": float(force),
            "depth_mm": float(d_mm), "beyond_calibration": bool(beyond),
        })

    if not report:
        raise RuntimeError("no contact yielded a valid FFT measurement")

    # feather the rims so plateaus meet the membrane smoothly
    feather = cv2.GaussianBlur(mask.astype(np.float32), (0, 0),
                               EDGE_FEATHER * cscale)
    depth = depth * feather
    depth = cv2.GaussianBlur(depth, (0, 0), 3 * cscale)

    return {"depth": depth, "mask": mask, "n": m, "report": report,
            "interiors": interiors, "deformed": deformed_img}


# ----------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------
def show_overlay(recon, title="", show=True, save_png=None):
    """Shapes + the interior regions actually used for each global FFT."""
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.5, 8.5))
    ax.imshow(recon["deformed"], cmap="gray")
    ax.contour(recon["mask"], levels=[0.5], colors="lime", linewidths=1.5)
    inter = recon["interiors"]
    ov = np.zeros((*inter.shape, 4), np.float32)
    ov[inter > 0] = (1.0, 0.55, 0.0, 0.45)
    ax.imshow(ov)
    for r in recon["report"]:
        ys, xs = np.nonzero(inter == r["contact"])
        if len(xs) == 0:
            continue
        ax.text(xs.mean(), ys.mean(),
                f"#{r['contact']}\n{r['depth_mm']:.2f} mm\n"
                f"{r['force_N']:.0f} N",
                color="white", fontsize=10, fontweight="bold",
                ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.25", fc="black", alpha=0.55))
    ax.set_title(f"{title}\ngreen = detected shape | orange = interior used "
                 f"for the global FFT (rim excluded)")
    ax.axis("off")
    fig.tight_layout()
    if save_png:
        fig.savefig(save_png, dpi=110, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)


def show_3d(recon, z_exaggeration=None, title="", show=True, save_png=None):
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import cm

    n = recon["n"]
    depth = recon["depth"]
    step = max(1, n // SURF_GRID)
    Z = depth[::step, ::step]                       # press goes DOWN
    Y, X = np.mgrid[:n:step, :n:step].astype(np.float32)

    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(111, projection="3d")
    dmax = max(depth.max(), 1e-6)
    norm = plt.Normalize(0, dmax)
    ax.plot_surface(X, Y, Z, facecolors=cm.viridis(norm(Z)),
                    rstride=2, cstride=2, linewidth=0,
                    antialiased=False, shade=True)
    m = cm.ScalarMappable(cmap=cm.viridis, norm=norm)
    cb = fig.colorbar(m, ax=ax, shrink=0.6, pad=0.08)
    cb.set_label("height (mm, 0 = undeformed membrane)")
    ax.set_xlabel("x (px)"); ax.set_ylabel("y (px)")
    ax.set_zlabel("depth (mm)")
    span = float(X.max() - X.min())
    if z_exaggeration is None:
        ax.set_zlim(-0.15* dmax, 1.05 * dmax)
    else:
        zspan = span / z_exaggeration
        ax.set_zlim(-0.05*zspan, zspan)
    parts = [f"#{r['contact']}: {r['depth_mm']:.2f} mm ({r['force_N']:.0f} N)"
             for r in recon["report"]]
    ax.set_title(title + "\n" + "   |   ".join(parts))
    ax.view_init(elev=35, azim=-60)
    if save_png:
        fig.savefig(save_png, dpi=110, bbox_inches="tight")
    if show:
        print("Drag with the mouse to rotate; close the window to exit.")
        plt.show()
    plt.close(fig)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reference", default=REF_IMAGE)
    ap.add_argument("--deformed", default=DEF_IMAGE)
    ap.add_argument("-o", "--out", default=OUTPUT_PATH)
    ap.add_argument("--ratio-csv", default=RATIO_CSV)
    ap.add_argument("--depth-csv", default=DEPTH_CSV)
    ap.add_argument("--area", type=float, default=CONTACT_AREA_MM2,
                    help="contact area of the pressed shape in mm^2 "
                         f"(default {CONTACT_AREA_MM2}; calibration circle "
                         f"is {CALIB_AREA_MM2} mm^2)")
    ap.add_argument("--z-exaggeration", type=float, default=None)
    ap.add_argument("--no-show", action="store_true")
    args = ap.parse_args()

    cal = efd.Calibration(args.ratio_csv, args.depth_csv)
    recon = reconstruct_global(args.reference, args.deformed, cal,
                               contact_area_mm2=args.area)

    os.makedirs(args.out, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.deformed))[0]
    np.save(os.path.join(args.out, f"{stem}_depth_mm.npy"), recon["depth"])

    for r in recon["report"]:
        warn = "  [WARNING: beyond calibration range, extrapolated]" \
            if r["beyond_calibration"] else ""
        print(f"contact #{r['contact']}: area {r['area_px']} px "
              f"(interior {r['interior_px']} px, window "
              f"{r['window_px_full'][0]}x{r['window_px_full'][1]} px) | "
              f"period {r['period_ref_px']:.2f} -> {r['period_def_px']:.2f} "
              f"px | ratio {r['ratio']:.5f} "
              f"(area-corrected {r['ratio_equivalent']:.5f}, "
              f"{r['contact_area_mm2']:.0f} mm^2) -> {r['force_N']:.1f} N, "
              f"depth {r['depth_mm']:.2f} mm{warn}")

    show_overlay(recon, title=stem, show=not args.no_show,
                 save_png=os.path.join(args.out, f"{stem}_interiors.png"))
    show_3d(recon, z_exaggeration=args.z_exaggeration,
            show=not args.no_show,
            save_png=os.path.join(args.out, f"{stem}_3d.png"))
    print(f"saved {args.out}/{stem}_depth_mm.npy, {stem}_3d.png, "
          f"{stem}_interiors.png")


if __name__ == "__main__":
    main()