"""
reconstruct_v3.py
=================
3-D reconstruction, version 3: for the photos of the new camera on the MARK-10
(data/raw/depth_stars). uniform_reconstruct.py (Liam) and reconstruct_v2.py are
not changed.

Why a new version: v2 gives every contact one flat plateau and reads its depth
and force from a calibration made with Liam's camera and a 20 mm circle. On the
new camera that calibration is wrong, and a plateau cannot show shapes whose
height changes from point to point.

What v3 does, from one reference and one pressed photo:
  * stretch map of the whole membrane (strain_map.py);
  * depth of the press from the peak stretch, and force from the stretch summed
    over the membrane, with calibrations made on this camera (the star photos
    at known depth and force, y = a x + b x^2);
  * relief: the height at every pixel follows the local stretch, scaled so the
    PEAK_AREA_MM2 where it is highest sit at the depth read above (nothing is
    drawn deeper than that depth). Stretch below FLOOR_FRAC of the peak counts
    as untouched membrane.

What is and is not validated: the depth and the force are checked against the
MARK-10 (verification/eval_reconstruction_v3.py, calibration never containing
the star under test). The relief is the measured stretch, not a measured
height: the stripes only show stretch across them, so parts of a shape that run
across the stripes come out lower than parts that run along them.

Usage from the repo root:
  python src/tactile/reconstruct_v3.py --build-calibration
  python src/tactile/reconstruct_v3.py --reference REF.jpg --deformed DEF.jpg
"""

# ═══ CONFIG ═══
REF_IMAGE = ""
DEF_IMAGE = ""
OUTPUT_PATH = "output/recon_v3"
CALIB_CSV = "data/processed/csv_files/star_stretch_calibration_v3.csv"
STARS_DIR = "data/raw/depth_stars"
WINDOW_MM = 26.0        # half-width of the square shown in the figures
SURF_GRID = 140         # 3-D rendering grid
# ═══════════════════════════════

import argparse
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tactile.strain_map as sm  # noqa: E402


# --- Calibration ------------------------------------------------------------------
def _quad_fit(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    coef, *_ = np.linalg.lstsq(np.c_[x, x ** 2], y, rcond=None)
    return coef


class StretchCalibration:
    """peak stretch -> depth (mm) and summed stretch -> force (N), y = a x + b x^2
    through the origin. `exclude` leaves one star out (for testing on that star).
    Beyond the calibrated range the value at its end is returned (a lower bound)."""

    def __init__(self, csv_path=CALIB_CSV, exclude=None):
        with open(csv_path, newline="", encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh) if r["star"] != exclude]
        peak = np.array([float(r["peak_stretch"]) for r in rows])
        integral = np.array([float(r["stretch_integral_mm2"]) for r in rows])
        self.cd = _quad_fit(peak, [float(r["depth_mm"]) for r in rows])
        self.cf = _quad_fit(integral, [float(r["force_N"]) for r in rows])
        self.peak_max, self.integral_max = float(peak.max()), float(integral.max())
        self.n = len(rows)

    @staticmethod
    def _eval(coef, x):
        return max(0.0, float(coef[0] * x + coef[1] * x ** 2))

    def depth(self, peak):
        return self._eval(self.cd, min(peak, self.peak_max))

    def force(self, integral):
        return self._eval(self.cf, min(integral, self.integral_max))

    def beyond(self, peak, integral):
        return peak > self.peak_max or integral > self.integral_max


def build_calibration(out_csv=CALIB_CSV, stars_dir=STARS_DIR):
    """Measure every pressed star photo of the log sheet and write the calibration table."""
    with open(os.path.join(stars_dir, "log_sheet.csv"), newline="", encoding="utf-8") as fh:
        log = [r for r in csv.DictReader(fh) if r["file"]]
    rows = []
    for r in log:
        m = sm.measure(os.path.join(stars_dir, r["ref_file"]), os.path.join(stars_dir, r["file"]))
        rows.append({"star": r["star"], "angle_deg": r["angle_deg"], "repeat": r["repeat"],
                     "depth_mm": float(r["depth_mm"]),
                     "force_N": 0.5 * (float(r["force_lo_N"]) + float(r["force_hi_N"])),
                     "peak_stretch": m["peak"], "stretch_integral_mm2": m["integral"], "file": r["file"]})
        print(f"  {r['file']}: peak stretch {m['peak']:.4f}, summed stretch {m['integral']:.2f} mm2", flush=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print(f"calibration: {len(rows)} photos -> {out_csv}")
    return out_csv


# --- Reconstruction ---------------------------------------------------------------
def reconstruct(ref_path, def_path, cal):
    m = sm.measure(ref_path, def_path)
    fl = m["fields"]
    inside, pxmm = fl["inside"], fl["px_per_mm"]
    depth = cal.depth(m["peak"])
    force = cal.force(m["integral"])

    fine = np.where(inside, m["stretch_fine"], 0.0)
    top = max(1, int(round(sm.PEAK_AREA_MM2 * pxmm ** 2)))
    peak_fine = float(np.sort(fine[inside])[-top:].mean())
    rel = np.clip((fine / max(peak_fine, 1e-9) - sm.FLOOR_FRAC) / (1.0 - sm.FLOOR_FRAC), 0.0, 1.0)
    depth_map = (depth * rel).astype(np.float32)
    return {"depth": depth_map, "depth_mm": depth, "force_N": force, "peak_stretch": m["peak"],
            "stretch_integral_mm2": m["integral"], "area_mm2": m["area_mm2"], "region": m["region"],
            "beyond_calibration": cal.beyond(m["peak"], m["integral"]),
            "n": fl["n"], "px_per_mm": pxmm, "deformed": fl["def"], "inside": inside}


# --- Figures ----------------------------------------------------------------------
def window(recon, half_mm=WINDOW_MM):
    """Central square of the depth map and its axis (mm)."""
    n, pxmm = recon["n"], recon["px_per_mm"]
    r = min(int(round(half_mm * pxmm)), n // 2)
    sub = recon["depth"][n // 2 - r:n // 2 + r, n // 2 - r:n // 2 + r]
    return sub, (np.arange(sub.shape[0]) - r) / pxmm


def surface(ax, recon, zmax, title=""):
    from matplotlib import cm
    sub, axis = window(recon)
    step = max(1, sub.shape[0] // SURF_GRID)
    Z = sub[::step, ::step]
    X, Y = np.meshgrid(axis[::step], axis[::step])
    ax.plot_surface(X, Y, Z, facecolors=cm.viridis(np.clip(Z / zmax, 0, 1)), rstride=1, cstride=1,
                    linewidth=0, antialiased=False, shade=True)
    ax.set_zlim(0, 1.1 * zmax)
    ax.set_ylim(axis[-1], axis[0])                  # image orientation: y grows downwards
    ax.set_xlabel("x (mm)", fontsize=8)
    ax.set_ylabel("y (mm)", fontsize=8)
    ax.set_zlabel("depth (mm)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_title(title, fontsize=9)
    ax.view_init(elev=38, azim=-60)


def top_view(ax, recon, zmax, title=""):
    sub, axis = window(recon)
    im = ax.imshow(sub, cmap="viridis", vmin=0, vmax=zmax, extent=[axis[0], axis[-1], axis[-1], axis[0]])
    ax.set_xlabel("x (mm)", fontsize=8)
    ax.set_ylabel("y (mm)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_title(title, fontsize=9)
    return im


def show(recon, title="", show_window=True, save_png=None):
    import matplotlib
    if not show_window:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    zmax = max(float(recon["depth"].max()), 0.1)
    fig = plt.figure(figsize=(12.5, 5.6))
    surface(fig.add_subplot(121, projection="3d"), recon, zmax)
    im = top_view(fig.add_subplot(122), recon, zmax, "seen from above")
    fig.colorbar(im, ax=fig.axes[1], shrink=0.8, label="depth (mm)")
    ge = "≥ " if recon["beyond_calibration"] else ""
    fig.suptitle(f"{title}\nsensor: {ge}{recon['depth_mm']:.2f} mm, {ge}{recon['force_N']:.1f} N")
    fig.tight_layout()
    if save_png:
        fig.savefig(save_png, dpi=110, bbox_inches="tight")
    if show_window:
        plt.show()
    plt.close(fig)


# --- Main -------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reference", default=REF_IMAGE)
    ap.add_argument("--deformed", default=DEF_IMAGE)
    ap.add_argument("-o", "--out", default=OUTPUT_PATH)
    ap.add_argument("--calibration", default=CALIB_CSV)
    ap.add_argument("--exclude-star", default=None,
                    help="leave this star (e.g. S1) out of the calibration")
    ap.add_argument("--build-calibration", action="store_true",
                    help="measure the star photos and write --calibration")
    ap.add_argument("--no-show", action="store_true")
    args = ap.parse_args()

    if args.build_calibration:
        build_calibration(args.calibration)
        if not args.deformed:
            return
    if not (args.reference and args.deformed):
        ap.error("--reference and --deformed are needed")
    cal = StretchCalibration(args.calibration, exclude=args.exclude_star)
    recon = reconstruct(args.reference, args.deformed, cal)
    os.makedirs(args.out, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.deformed))[0]
    np.save(os.path.join(args.out, f"{stem}_depth_mm.npy"), recon["depth"])
    warn = "  [beyond calibration: lower bounds]" if recon["beyond_calibration"] else ""
    print(f"peak stretch {recon['peak_stretch']:.4f}, summed stretch {recon['stretch_integral_mm2']:.2f} mm2 "
          f"-> depth {recon['depth_mm']:.2f} mm, force {recon['force_N']:.1f} N{warn}")
    show(recon, title=stem, show_window=not args.no_show, save_png=os.path.join(args.out, f"{stem}_3d.png"))
    print(f"saved {args.out}/{stem}_depth_mm.npy, {stem}_3d.png")


if __name__ == "__main__":
    main()
