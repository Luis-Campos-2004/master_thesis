"""
reconstruct_v2.py
=================
3-D reconstruction, version 2. Liam's uniform_reconstruct.py is left unchanged;
this file is the new version, built and tested on Liam's photos.

One flat plateau per contact (all the tips are flat-ended), like v1, but every
number behind it is measured differently:

  * Contact region. v1 used detect_shape's default footprint, halo included.
    v2 takes the region from the signal the press leaves on the stripes:
      - stripes shifted as a block (the shape photos, pressed by hand): the
        contact-mode mask of detect_shape, i.e. the improved contour;
      - stripes stretched (the flat circle on the Mark-10 test stand): the
        thresholded local period-ratio map, which detect_shape cannot see
        because its high-pass filter removes a uniform stretch.
    Which one applies is decided by the phase plateau under the contact-mode
    mask (PLATEAU_MIN_RAD). For a stretched contact the outline (and area) is
    the ratio map above REGION_FRAC of its peak, and the stretch is measured in
    the slightly wider region above MEASURE_FRAC.
  * Stretch. v1 took one FFT of the eroded interior. v2 measures the local
    stripe period from the gradient of the FTP phase, smoothing only with
    pixels inside the contact so the phase step at the edge of a sheared
    contact does not leak in, and subtracts the stretch of the membrane around
    the contact.
  * Calibration. v1 mapped ratio to force with a straight line through Liam's
    ratio table and needed CALIB_FOOTPRINT_SCALE = 1.874 for the area. v2 fits
    stretch -> pressure and stretch -> depth with quadratics on the force photos
    themselves (calibration photos only, see build_calibration), with areas in
    mm^2: pressure = force / 314 mm^2 of the calibration circle,
    force = pressure x contact area, and the depth is the circle's depth at the
    same stretch (same pressure, same depth).
  * The 3-D surface is drawn in mm on the accurate outline, with a soft rim.

Usage:
  python src/tactile/reconstruct_v2.py --build-calibration
  python src/tactile/reconstruct_v2.py --reference REF.jpg --deformed DEF.jpg
"""

# ═══ CONFIG ═══
REF_IMAGE = ""
DEF_IMAGE = ""
OUTPUT_PATH = "output/recon_v2"
CALIB_CSV = "data/processed/csv_files/force_vs_local_stretch_v2.csv"
DEPTH_CSV = "data/processed/csv_files/force_vs_mean_depth.csv"   # Mark-10, Liam
RATIO_CSV = "data/processed/csv_files/force_vs_mean_width_ratio_frequency.csv"
FORCE_DIR = "data/raw/force_pictures"
FORCE_REF = "data/raw/force_pictures/reference/img_01.jpg"
CALIB_FILES = ("img_01.jpg", "img_02.jpg", "img_03.jpg")   # img_04-05 kept for tests
CALIB_AREA_MM2 = 314.0      # flat circle used for the force photos (20 mm)

PLATEAU_MIN_RAD = 1.1       # |phase plateau| that marks a block shift (shapes: 1.4-4.7 rad,
                            # force photos: 0.3-0.8 rad)
REGION_SIGMA_T = 1.0        # smoothing of the ratio map for the region, in periods
REGION_FRAC = 0.55          # outline = stretch above this fraction of its peak (circle: 316 mm2)
MEASURE_FRAC = 0.5          # wider region the stretch is measured in
REGION_MIN_PEAK = 0.003     # peak stretch below this = no press (no-press pairs: <= 0.0009,
                            # 3 N: >= 0.009)
STRETCH_SIGMA_T = 0.75      # smoothing of the phase for the stretch, in periods
STRETCH_ERODE_PX = 13       # contact pixels this close to the edge are not used (~half a period)
BG_MARGIN_PX = 60           # background = membrane at least this far from contacts
MIN_CONTACT_MM2 = 10.0
RIM_SIGMA_MM = 0.5          # softening of the plateau edge in the 3-D surface
SURF_GRID = 160
# ═══════════════════════════════

import argparse
import csv
import os
import sys

import cv2
import numpy as np
from scipy import ndimage as ndi
from skimage.restoration import unwrap_phase

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tactile.detect_shape as ds  # noqa: E402
import tactile.estimate_force_depth as efd  # noqa: E402
import tactile.uniform_reconstruct as ur  # noqa: E402


def px_per_mm(size=ds.PROC_SIZE):
    """Detection-frame scale from the calibration circle's mask (11.8 px/mm)."""
    return float(np.sqrt(ur.calib_area_from_mask(ur.CALIB_MASK_PATH, size) / CALIB_AREA_MM2))


# --- Phase and local stripe period ---------------------------------------------
def fields(ref_path, def_path):
    """Unwrapped FTP phase difference, carrier (cycles/px) and ROI disc."""
    g_ref, g_def = ds.load_roi(ref_path), ds.load_roi(def_path)
    z_ref, car = ds.demodulate(g_ref)
    z_def, _ = ds.demodulate(g_def, car)
    n = g_ref.shape[0]
    f = np.array(car, float) / n
    yy, xx = np.mgrid[:n, :n]
    roi = np.hypot(yy - n / 2, xx - n / 2) < ds.ROI_RADIUS_FRAC * n
    dphi = unwrap_phase(np.angle(z_def * np.conj(z_ref))).astype(np.float32)
    return {"dphi": dphi, "f": f, "period": float(1 / np.hypot(*f)), "roi": roi,
            "def": g_def, "n": n}


def _ratio(phase, f):
    """Local period ratio (deformed / reference) from a smooth phase."""
    gy, gx = np.gradient(phase)
    return np.hypot(*f) / np.hypot(f[0] + gy / (2 * np.pi), f[1] + gx / (2 * np.pi))


def ratio_map(fl, sigma_t=REGION_SIGMA_T):
    return _ratio(cv2.GaussianBlur(fl["dphi"], (0, 0), sigma_t * fl["period"]), fl["f"])


def stretch_inside(fl, mask, sigma_t=STRETCH_SIGMA_T, erode=STRETCH_ERODE_PX):
    """Median stretch (period ratio - 1) of `mask`, smoothing with its own pixels only."""
    m = ndi.binary_erosion(mask, iterations=erode) if erode else mask
    if m.sum() < 50:
        m = mask
    w = m.astype(np.float32)
    s = sigma_t * fl["period"]
    den = cv2.GaussianBlur(w, (0, 0), s)
    ph = cv2.GaussianBlur(fl["dphi"] * w, (0, 0), s) / np.maximum(den, 1e-3)
    core = ndi.binary_erosion(m, iterations=2) if m.sum() > 400 else m
    return float(np.median(_ratio(ph, fl["f"])[core])) - 1.0


def background_stretch(fl, contacts, sigma_t=STRETCH_SIGMA_T):
    free = fl["roi"] & ~ndi.binary_dilation(contacts, iterations=BG_MARGIN_PX)
    if free.sum() < 2000:
        free = fl["roi"] & ~contacts
    return stretch_inside(fl, free, sigma_t, 0)


# --- Contact region ---------------------------------------------------------------
def stretch_region(fl, sigma_t=REGION_SIGMA_T, frac=REGION_FRAC):
    """Where the stripes are stretched: the ratio map above frac x its peak."""
    roi = fl["roi"]
    d = ratio_map(fl, sigma_t)
    d = d - np.median(d[roi])
    peak = float(np.percentile(d[roi], 99.5))
    if peak < REGION_MIN_PEAK:
        return np.zeros_like(roi)
    mk = ndi.binary_opening((d > frac * peak) & roi, iterations=3)
    lab, nl = ndi.label(mk)
    if nl == 0:
        return mk
    sizes = ndi.sum(mk, lab, range(1, nl + 1))
    keep = np.isin(lab, 1 + np.nonzero(sizes >= 0.25 * sizes.max())[0])
    return ndi.binary_fill_holes(keep)


def phase_plateau(fl, mask):
    """Phase under the mask minus the phase just around it (rad)."""
    if not mask.any():
        return 0.0
    ring = (ndi.binary_dilation(mask, iterations=40) & ~ndi.binary_dilation(mask, iterations=15)
            & fl["roi"])
    return float(np.median(fl["dphi"][mask]) - np.median(fl["dphi"][ring]))


def contact_regions(ref_path, def_path, fl):
    """Outline mask, the mask the stretch is measured in, and the kind of signal
    ('shift' or 'stretch')."""
    shift = (ds.detect(ref_path, def_path, **ds.CONTACT_PARAMS)["mask"] > 0) & fl["roi"]
    plateau = phase_plateau(fl, shift)
    if abs(plateau) >= PLATEAU_MIN_RAD:
        return shift, shift, "shift", plateau
    return stretch_region(fl, frac=REGION_FRAC), stretch_region(fl, frac=MEASURE_FRAC), "stretch", plateau


def contacts(outline, measure, min_px):
    """(outline component, measuring component) pairs, largest first."""
    lab, nl = ndi.label(outline, structure=np.ones((3, 3)))
    mlab, _ = ndi.label(measure, structure=np.ones((3, 3)))
    out = []
    for i in range(1, nl + 1):
        comp = lab == i
        if comp.sum() < min_px:
            continue
        hits = np.bincount(mlab[comp], minlength=1)
        hits[0] = 0
        meas = (mlab == int(np.argmax(hits))) if hits.any() else comp
        out.append((comp, meas | comp))
    return sorted(out, key=lambda c: -c[0].sum())


# --- Calibration ------------------------------------------------------------------
class StretchCalibration:
    """stretch -> pressure (N/mm^2) and stretch -> depth (mm), quadratic fits to the
    calibration photos. Beyond the calibrated stretch nothing is extrapolated: the
    value at the largest calibrated stretch is returned as a lower bound."""

    def __init__(self, csv_path=CALIB_CSV):
        with open(csv_path, newline="", encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh)]
        s = np.array([float(r["stretch"]) for r in rows])
        F = np.array([float(r["force_N"]) for r in rows])
        D = np.array([float(r["depth_mm"]) for r in rows])
        self.cp = np.polyfit(s, F / CALIB_AREA_MM2, 2)
        self.cd = np.polyfit(s, D, 2)
        self.s_min, self.s_max = float(s.min()), float(s.max())

    def _eval(self, c, s):
        return max(0.0, float(np.polyval(c, min(s, self.s_max))))

    def pressure(self, s):
        return self._eval(self.cp, s)

    def depth(self, s):
        return self._eval(self.cd, s)

    def beyond(self, s):
        return s > self.s_max


def measure_force_photo(path, ref=FORCE_REF):
    """Stretch and area of the largest contact in one force photo."""
    fl = fields(ref, path)
    outline, measure, kind, plateau = contact_regions(ref, path, fl)
    pxmm = px_per_mm(fl["n"])
    found = contacts(outline, measure, MIN_CONTACT_MM2 * pxmm ** 2)
    if not found:
        return None
    comp, meas = found[0]
    s = stretch_inside(fl, meas) - background_stretch(fl, measure | outline)
    return {"stretch": s, "area_mm2": comp.sum() / pxmm ** 2, "kind": kind,
            "plateau": plateau, "mask": comp, "n_contacts": len(found)}


def build_calibration(out_csv=CALIB_CSV, files=CALIB_FILES, force_dir=FORCE_DIR):
    """Calibration table from the force photos: one row per calibration photo."""
    mark10 = efd.Calibration(RATIO_CSV, DEPTH_CSV)
    rows = []
    levels = sorted((d for d in os.listdir(force_dir) if d.endswith("N")), key=lambda d: int(d[:-1]))
    for lv in levels:
        F = float(lv[:-1])
        for fn in files:
            m = measure_force_photo(os.path.join(force_dir, lv, fn))
            if m is None:
                print(f"  {lv}/{fn}: no contact found, skipped")
                continue
            rows.append({"force_N": F, "depth_mm": mark10.depth_from_force(F), "file": f"{lv}/{fn}",
                         "stretch": m["stretch"], "area_mm2": m["area_mm2"], "kind": m["kind"]})
            print(f"  {lv}/{fn}: stretch {m['stretch']:+.5f}, area {m['area_mm2']:.0f} mm2 ({m['kind']})")
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print(f"calibration: {len(rows)} photos -> {out_csv}")
    return out_csv


# --- Reconstruction ---------------------------------------------------------------
def reconstruct(ref_path, def_path, cal):
    fl = fields(ref_path, def_path)
    n = fl["n"]
    pxmm = px_per_mm(n)
    outline, measure, kind, plateau = contact_regions(ref_path, def_path, fl)
    found = contacts(outline, measure, MIN_CONTACT_MM2 * pxmm ** 2)
    depth = np.zeros((n, n), np.float32)
    report, masks = [], []
    bg = background_stretch(fl, measure | outline) if found else 0.0
    mask = np.zeros_like(outline)
    for comp, meas in found:
        area = comp.sum() / pxmm ** 2
        mask |= comp
        s = stretch_inside(fl, meas) - bg
        p = cal.pressure(s)
        d = cal.depth(s)
        depth[comp] = d
        masks.append(comp)
        report.append({"contact": len(report) + 1, "kind": kind, "area_mm2": float(area),
                       "stretch": float(s), "pressure_kPa": 1000.0 * p,
                       "force_N": p * area, "depth_mm": d, "beyond_calibration": cal.beyond(s)})
    depth = cv2.GaussianBlur(depth, (0, 0), RIM_SIGMA_MM * pxmm)
    return {"depth": depth, "mask": mask, "masks": masks, "kind": kind, "plateau": plateau,
            "report": report, "n": n, "px_per_mm": pxmm, "deformed": fl["def"], "roi": fl["roi"]}


# --- Figures ----------------------------------------------------------------------
def show_overlay(recon, title="", show=True, save_png=None):
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7.5, 7.5))
    ax.imshow(recon["deformed"], cmap="gray")
    for r, comp in zip(recon["report"], recon["masks"]):
        ax.contour(comp, levels=[0.5], colors="#eb6834", linewidths=1.6)
        ys, xs = np.nonzero(comp)
        ge = "≥ " if r["beyond_calibration"] else ""
        ax.text(xs.mean(), ys.mean(), f"{ge}{r['depth_mm']:.2f} mm\n{ge}{r['force_N']:.1f} N",
                color="white", fontsize=10, fontweight="bold", ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.25", fc="black", alpha=0.55))
    ax.set_title(f"{title}\ncontact from the {'shifted' if recon['kind'] == 'shift' else 'stretched'} stripes")
    ax.axis("off")
    fig.tight_layout()
    if save_png:
        fig.savefig(save_png, dpi=110, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)


def show_3d(recon, title="", show=True, save_png=None, ax=None, zmax=None):
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import cm
    n, pxmm, depth = recon["n"], recon["px_per_mm"], recon["depth"]
    step = max(1, n // SURF_GRID)
    Z = depth[::step, ::step]
    Y, X = (np.mgrid[:n:step, :n:step].astype(np.float32) - n / 2) / pxmm
    own = ax is None
    if own:
        fig = plt.figure(figsize=(9, 7))
        ax = fig.add_subplot(111, projection="3d")
    top = zmax or max(float(depth.max()), 1e-6)
    ax.plot_surface(X, Y, Z, facecolors=cm.viridis(np.clip(Z / top, 0, 1)), rstride=1, cstride=1,
                    linewidth=0, antialiased=False, shade=True)
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_zlabel("depth (mm)")
    ax.set_zlim(0, 1.1 * top)
    ax.set_title(title, fontsize=10)
    ax.view_init(elev=35, azim=-60)
    if own:
        if save_png:
            fig.savefig(save_png, dpi=110, bbox_inches="tight")
        if show:
            plt.show()
        plt.close(fig)


# --- Main -------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reference", default=REF_IMAGE)
    ap.add_argument("--deformed", default=DEF_IMAGE)
    ap.add_argument("-o", "--out", default=OUTPUT_PATH)
    ap.add_argument("--calibration", default=CALIB_CSV)
    ap.add_argument("--build-calibration", action="store_true",
                    help="measure the calibration photos and write --calibration")
    ap.add_argument("--no-show", action="store_true")
    args = ap.parse_args()

    if args.build_calibration:
        build_calibration(args.calibration)
        if not args.deformed:
            return
    if not (args.reference and args.deformed):
        ap.error("--reference and --deformed are needed")
    cal = StretchCalibration(args.calibration)
    recon = reconstruct(args.reference, args.deformed, cal)
    os.makedirs(args.out, exist_ok=True)
    stem = (os.path.basename(os.path.dirname(args.deformed)) + "_"
            + os.path.splitext(os.path.basename(args.deformed))[0]).replace(" ", "_")
    np.save(os.path.join(args.out, f"{stem}_depth_mm.npy"), recon["depth"])
    print(f"signal: {recon['kind']} (phase plateau {recon['plateau']:+.2f} rad)")
    for r in recon["report"]:
        warn = "  [beyond calibration: lower bounds]" if r["beyond_calibration"] else ""
        print(f"contact #{r['contact']}: {r['area_mm2']:.0f} mm2 | stretch {r['stretch']:+.5f} | "
              f"{r['pressure_kPa']:.0f} kPa -> {r['force_N']:.1f} N, depth {r['depth_mm']:.2f} mm{warn}")
    show_overlay(recon, title=stem, show=not args.no_show,
                 save_png=os.path.join(args.out, f"{stem}_contacts.png"))
    show_3d(recon, title=stem, show=not args.no_show, save_png=os.path.join(args.out, f"{stem}_3d.png"))
    print(f"saved {args.out}/{stem}_depth_mm.npy, {stem}_contacts.png, {stem}_3d.png")


if __name__ == "__main__":
    main()
