"""
integrated_pipeline.py

Combines the temperature/colour segmentation stage with the tactile 3-D
reconstruction stage, run on one reference + one deformed image.

Steps: (1) interactive pop-up on the deformed image — click a stripe to see
its predicted temperature; (2) saves a colour-change segmentation figure
(reference vs deformed); (3) reconstructs force/depth for each detected
contact and shows the shape overlay and 3-D surface.

Set REF_IMAGE and DEF_IMAGE below to your image paths.
"""

import cv2
import numpy as np

import argparse
import os
import sys

import temperature.color_merged as cm               # colour / temperature stage
import tactile.uniform_reconstruct as ur     # tactile reconstruction stage
import tactile.estimate_force_depth as efd      # tactile calibration

from scipy.ndimage import gaussian_filter
import matplotlib.pyplot as plt       

# ═══════════════════════════════════════════════════════════
#  CONFIG

REF_IMAGE = "data/raw/final_images/ref_image.jpg"
DEF_IMAGE = "data/raw/final_images/def_image.jpg"
OUTPUT_PATH = "output/temp_shape_recon"

# --- temperature-change gating -----------------------------------------
# Temperature shifts LAB chroma (a*/b*) but a press doesn't, so we gate on
# chroma; 6.0 sits between a press's ~2.5 and a real change's ~8-12.
SEG_MIN_CHROMA_DELTA = 6.0
SEG_MIN_AREA_FRAC    = 0.003
SEG_MIN_BLOB_FRAC    = 0.01

# --- tactile real-deformation gating -----------------------------------
# Temperature-only contacts leave stripe spacing unchanged (ratio ~1 -> ~0 N);
# a real press compresses/stretches stripes (ratio > 1). Gate on MIN_FORCE_N.
MIN_FORCE_N = 0.5

# ═══════════════════════════════════════════════════════════

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

_HERE = os.path.dirname(os.path.abspath(__file__))
for _sub in ("tactile", "color_segmentation"):
    _p = os.path.join(_HERE, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ----------------------------------------------------------------------
# Stage 1 + 2 — colour: interactive temperature pop-up, then segmentation
def segment_temperature_change(ref_bgr, img_bgr,
                               min_chroma_delta=SEG_MIN_CHROMA_DELTA,
                               min_area_frac=SEG_MIN_AREA_FRAC,
                               min_blob_frac=SEG_MIN_BLOB_FRAC):
    """Detects a colour/temperature change between reference and deformed
    images, using LAB chroma (a*/b*) difference since it's insensitive to
    the brightness changes a press produces.

    Returns a dict: mask (uint8), ref/img RGB crops, `changed` (bool),
    `area_frac`, and `max_delta` (largest chroma shift seen, LAB units)."""
    def crop_bgr(bgr, rr):
        hh, ww = bgr.shape[:2]
        ccx, ccy = ww // 2, hh // 2
        return bgr[ccy - rr:ccy + rr, ccx - rr:ccx + rr]

    hh, ww = ref_bgr.shape[:2]
    r = int(min(hh, ww) * cm.CROP_RATIO)
    ref_c = crop_bgr(ref_bgr, r)
    img_c = crop_bgr(img_bgr, r)

    h, w = ref_c.shape[:2]
    cx, cy = w // 2, h // 2
    r_outer = int(min(h, w) * 0.48)
    r_inner = int(min(h, w) * 0.02)
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    circle_mask = (dist < r_outer) & (dist > r_inner)

    # LAB chrominance difference, blurred over the stripes
    lab_r = cv2.cvtColor(ref_c, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab_d = cv2.cvtColor(img_c, cv2.COLOR_BGR2LAB).astype(np.float32)
    s = cm.SIGMA
    da = gaussian_filter(lab_d[:, :, 1], s) - gaussian_filter(lab_r[:, :, 1], s)
    db = gaussian_filter(lab_d[:, :, 2], s) - gaussian_filter(lab_r[:, :, 2], s)
    # remove any white-balance drift between the two shots
    da = da - float(np.median(da[circle_mask]))
    db = db - float(np.median(db[circle_mask]))
    chroma = np.sqrt(da ** 2 + db ** 2)

    chroma_mask = (chroma > min_chroma_delta) & circle_mask

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                       (cm.MORPH_SIZE, cm.MORPH_SIZE))
    m = cv2.morphologyEx(chroma_mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
    bright_clean = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel)

    roi_area = int(circle_mask.sum())

    # drop small blobs (bubbles, dust) — keep only sizable regions
    min_blob_px = int(min_blob_frac * roi_area)
    if min_blob_px > 0:
        n_lab, lab, stats, _ = cv2.connectedComponentsWithStats(bright_clean,
                                                                connectivity=8)
        kept_mask = np.zeros_like(bright_clean)
        for i in range(1, n_lab):
            if stats[i, cv2.CC_STAT_AREA] >= min_blob_px:
                kept_mask[lab == i] = 255
        bright_clean = kept_mask

    seg_area = int((bright_clean > 0).sum())
    area_frac = seg_area / max(roi_area, 1)
    max_delta = float(chroma[circle_mask].max()) if roi_area else 0.0
    changed = seg_area > 0 and area_frac >= min_area_frac

    ref_crop_rgb = cv2.cvtColor(ref_c, cv2.COLOR_BGR2RGB)
    img_crop_rgb = cv2.cvtColor(img_c, cv2.COLOR_BGR2RGB)

    return {"mask": bright_clean, "ref": ref_crop_rgb, "img": img_crop_rgb,
            "changed": changed, "area_frac": area_frac, "max_delta": max_delta}


def render_segmentation(seg, out_path=None, show=True):
    """Render the 3-panel colour-segmentation figure; save and/or pop it up."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.patch.set_facecolor("#1a1a2e")

    def show_panel(ax, data, title, cmap="gray"):
        ax.imshow(data, cmap=cmap)
        ax.set_title(title, color="white", fontsize=12, fontweight="bold")
        ax.axis("off")

    show_panel(axes[0], seg["ref"], "Reference Image")
    show_panel(axes[1], seg["img"], "Coloured Image")

    # RETR_CCOMP keeps inner hole boundaries, so a ring-shaped stamp is
    # outlined as a ring rather than a filled disc.
    contours, _ = cv2.findContours(seg["mask"], cv2.RETR_CCOMP,
                                   cv2.CHAIN_APPROX_SIMPLE)
    img_contour = seg["img"].copy()
    cv2.drawContours(img_contour, contours, -1, (255, 120, 0), 6)
    show_panel(axes[2], img_contour, "Temperature Segmentation")

    plt.suptitle(f"Colour-based Segmentation  "
                 f"(area {seg['area_frac'] * 100:.2f}% of ROI, "
                 f"max chroma shift {seg['max_delta']:.1f} LAB)",
                 color="white", fontsize=14, fontweight="bold", y=1.01)
    plt.tight_layout()
    if out_path:
        plt.savefig(out_path, dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        print(f"Segmentation image saved → {out_path}")
    if show:
        print("Showing temperature segmentation — close the window to continue.")
        plt.show()
    plt.close(fig)


def run_colour_stage(ref_path, def_path, out_dir, show=True,
                     min_chroma_delta=SEG_MIN_CHROMA_DELTA,
                     min_area_frac=SEG_MIN_AREA_FRAC,
                     min_blob_frac=SEG_MIN_BLOB_FRAC):
    """Runs the colour stage: stripe detection + interactive temperature
    pop-up on the deformed image, then a gated colour-change segmentation
    that only pops up when a real temperature change is found."""
    # --- stripe detection on the deformed (pressed / coloured) image ---
    img_bgr, img_rgb, img_hsv, val, H, W = cm.load_image(def_path)
    cx, cy, radius = cm.get_center_radius(H, W)
    wafer_mask = cm.build_wafer_mask(H, W, cx, cy, radius)

    print("Running row-adaptive stripe detection...")
    label_map = cm.get_stripes(
        val, H, W, cx, cy, radius,
        smooth_win=cm.SMOOTH_WIN,
        smooth_poly=cm.SMOOTH_POLY,
        min_peak_dist=cm.MIN_PEAK_DIST,
        min_peak_prom=cm.MIN_PEAK_PROM,
        vert_smooth=cm.VERT_SMOOTH,
    )
    purple_mask, black_mask = cm.build_masks(
        label_map, wafer_mask, cm.MORPH_OPEN_K, cm.MORPH_CLOSE_K)

    # --- temperature predictors ---
    predictor = cm.ColorPredictor(
        csv_file=cm.COLOR_CSV_PATH, target_col=cm.TARGET_COL,
        color_space=cm.COLOR_SPACE, n_neighbors=cm.N_NEIGHBORS)
    try:
        predictor.load_reference()
    except Exception as e:
        print(f"Warning: could not load colour reference CSV ({e}). "
              "Colour temperature prediction will be disabled.")
        predictor = None

    black_predictor = cm.BlackPredictor(
        csv_file=cm.BLACK_CSV_PATH, target_col=cm.TARGET_COL,
        color_space=cm.BLACK_COLOR_SPACE, n_neighbors=cm.N_NEIGHBORS)
    try:
        black_predictor.load_reference()
    except Exception as e:
        print(f"Warning: could not load black reference CSV ({e}). "
              "Black temperature prediction will be disabled.")
        black_predictor = None

    # --- interactive pop-up: click a stripe to see its predicted temperature ---
    if show:
        print("Launching interactive temperature viewer — "
              "click to read temperatures, close the window to continue.")
        cm.launch_interactive(img_rgb, img_bgr, purple_mask, black_mask,
                              wafer_mask, predictor=predictor,
                              black_predictor=black_predictor)
    else:
        print("--no-show: skipping the interactive temperature viewer.")

    # --- gated colour-change segmentation (reference vs deformed) ---
    print("Checking for a colour/temperature change...")
    ref_bgr = cv2.imread(ref_path)
    seg_bgr = cv2.imread(def_path)
    if ref_bgr is None:
        raise FileNotFoundError(ref_path)
    if seg_bgr is None:
        raise FileNotFoundError(def_path)

    seg = segment_temperature_change(ref_bgr, seg_bgr,
                                     min_chroma_delta=min_chroma_delta,
                                     min_area_frac=min_area_frac,
                                     min_blob_frac=min_blob_frac)

    if not seg["changed"]:
        print(f"No temperature change detected "
              f"(max chroma shift {seg['max_delta']:.1f} < "
              f"{min_chroma_delta:.1f} LAB threshold, or area "
              f"{seg['area_frac'] * 100:.2f}% < "
              f"{min_area_frac * 100:.2f}% of ROI). "
              f"Skipping temperature segmentation.")
        return

    print(f"Temperature change detected — segmenting "
          f"({seg['area_frac'] * 100:.2f}% of ROI, "
          f"max chroma shift {seg['max_delta']:.1f} LAB).")
    os.makedirs(out_dir, exist_ok=True)
    out_png = os.path.join(out_dir, "temperature_segmentation.png")
    render_segmentation(seg, out_path=out_png, show=show)


# ----------------------------------------------------------------------
# Stage 3 — tactile: shape detection + 3-D reconstruction (force + depth)
def save_located_shape(mask, out_path, roi_frac=None):
    """Saves a simple figure of the detected contact shape (dark blob) on a
    light wafer disc, without stripe/overlay clutter. `mask` is the final
    reconstruction mask, with phantom contacts already removed."""
    if roi_frac is None:
        roi_frac = ur.ds.ROI_RADIUS_FRAC
    mask = (np.asarray(mask) > 0).astype(np.uint8)
    n = mask.shape[0]
    canvas = np.full((n, n, 3), 255, np.uint8)
    yy, xx = np.mgrid[:n, :n]
    disc = np.hypot(yy - n / 2, xx - n / 2) < n * roi_frac
    canvas[disc] = (242, 247, 244)                     # very light green-white
    canvas[mask > 0] = (23, 64, 23)                    # dark green (BGR)
    cv2.circle(canvas, (n // 2, n // 2), int(n * roi_frac),
               (90, 90, 90), 2, cv2.LINE_AA)
    cv2.imwrite(out_path, canvas)
    print(f"Shape detection image saved → {out_path}")


def run_tactile_stage(ref_path, def_path, out_dir, ratio_csv, depth_csv,
                      area, z_exaggeration=None, show=True,
                      min_force_n=MIN_FORCE_N):
    """Runs the tactile stage: one global FFT per contact -> force -> depth,
    then the shape/interior overlay and 3-D surface. Contacts with force
    <= min_force_n are discarded as temperature artefacts."""
    cal = efd.Calibration(ratio_csv, depth_csv)
    try:
        recon = ur.reconstruct_global(ref_path, def_path, cal,
                                      contact_area_mm2=area)
    except RuntimeError as e:
        # No contact found (e.g. a temperature-only capture) raises here;
        # treat that as a valid result, not a crash.
        print(f"[tactile] {e}")
        print("[tactile] No shape detected — skipping 3-D reconstruction "
              "(the colour/temperature stage above is unaffected).")
        return

    # --- drop phantom contacts with no real stripe deformation ---
    # Temperature-only contacts keep ratio ~1 (~0 N); zero them out so only
    # genuine presses remain in the depth map, overlay, and 3-D surface.
    kept = [r for r in recon["report"] if r["force_N"] > min_force_n]
    dropped = [r for r in recon["report"] if r["force_N"] <= min_force_n]
    if dropped:
        _, lab = cv2.connectedComponents(recon["mask"].astype(np.uint8))
        for r in dropped:
            comp = lab == r["contact"]
            recon["depth"][comp] = 0.0
            recon["interiors"][recon["interiors"] == r["contact"]] = 0
            recon["mask"][comp] = False
            print(f"[tactile] contact #{r['contact']}: ratio "
                  f"{r['ratio']:.5f} -> {r['force_N']:.1f} N "
                  f"(<= {min_force_n} N) — discarded as a temperature artefact "
                  f"(no real stripe deformation).")
    recon["report"] = kept

    if not kept:
        print("[tactile] No real 3-D shape detected — every contact showed an "
              "unchanged stripe period (temperature change only). "
              "Skipping 3-D reconstruction.")
        return

    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(def_path))[0]
    np.save(os.path.join(out_dir, f"{stem}_depth_mm.npy"), recon["depth"])

    # simple figure showing the final detected shape
    save_located_shape(recon["mask"],
                       os.path.join(out_dir, f"{stem}_shape.png"))

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

    ur.show_overlay(recon, title=stem, show=show,
                    save_png=os.path.join(out_dir, f"{stem}_interiors.png"))
    ur.show_3d(recon, z_exaggeration=z_exaggeration, title=stem, show=show,
               save_png=os.path.join(out_dir, f"{stem}_3d.png"))
    print(f"saved {out_dir}/{stem}_depth_mm.npy, {stem}_3d.png, "
          f"{stem}_interiors.png, {stem}_shape.png")


# ----------------------------------------------------------------------
# Main
def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reference", default=REF_IMAGE)
    ap.add_argument("--deformed", default=DEF_IMAGE)
    ap.add_argument("-o", "--out", default=OUTPUT_PATH)
    ap.add_argument("--ratio-csv", default=ur.RATIO_CSV)
    ap.add_argument("--depth-csv", default=ur.DEPTH_CSV)
    ap.add_argument("--area", type=float, default=ur.CONTACT_AREA_MM2,
                    help="contact area of the pressed shape in mm^2 "
                         f"(default {ur.CONTACT_AREA_MM2}; calibration circle "
                         f"is {ur.CALIB_AREA_MM2} mm^2)")
    ap.add_argument("--z-exaggeration", type=float, default=None)
    ap.add_argument("--seg-chroma", type=float, default=SEG_MIN_CHROMA_DELTA,
                    help="minimum local LAB chroma (a*,b*) shift to count as a "
                         f"temperature change (default {SEG_MIN_CHROMA_DELTA}); "
                         "raise it to ignore presses, lower it to catch faint "
                         "colour changes")
    ap.add_argument("--seg-min-area", type=float, default=SEG_MIN_AREA_FRAC,
                    help="minimum TOTAL segmented area as a fraction of the ROI "
                         f"(default {SEG_MIN_AREA_FRAC})")
    ap.add_argument("--seg-min-blob", type=float, default=SEG_MIN_BLOB_FRAC,
                    help="minimum size of each individual segmented blob as a "
                         f"fraction of the ROI (default {SEG_MIN_BLOB_FRAC}); "
                         "raise it to drop bubbles/specks")
    ap.add_argument("--min-force", type=float, default=MIN_FORCE_N,
                    help="minimum force (N) for a detected contact to count as "
                         f"a real press (default {MIN_FORCE_N}); contacts at or "
                         "below this are discarded as temperature artefacts")
    ap.add_argument("--no-show", action="store_true",
                    help="skip all pop-up windows; only save output files")
    args = ap.parse_args()
    show = not args.no_show

    print("=" * 64)
    print(" STAGE 1/2 — colour: temperature pop-up + segmentation")
    print("=" * 64)
    run_colour_stage(args.reference, args.deformed, args.out, show=show,
                     min_chroma_delta=args.seg_chroma,
                     min_area_frac=args.seg_min_area,
                     min_blob_frac=args.seg_min_blob)

    print("\n" + "=" * 64)
    print(" STAGE 3 — tactile: shape + 3-D reconstruction (force + depth)")
    print("=" * 64)
    run_tactile_stage(args.reference, args.deformed, args.out,
                      args.ratio_csv, args.depth_csv, args.area,
                      z_exaggeration=args.z_exaggeration, show=show,
                      min_force_n=args.min_force)

    print("\nAll done.")


if __name__ == "__main__":
    main()