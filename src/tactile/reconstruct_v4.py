"""
reconstruct_v4.py
=================
3-D reconstruction, version 4: same measurements and calibration as
reconstruct_v3.py (depth from the peak stretch, force from the summed stretch),
but the surface is built differently. reconstruct_v3.py is not changed.

In v3 the height at every pixel followed the local stretch, so every bump of
the stretch map became a peak and the shape was lost in 3-D. In v4 the shape is
taken from the 2-D stretch map first and the height is added afterwards:

  1. outline = where the stretch is above OUTLINE_FRAC of its peak (small
     separate pieces are dropped, the edge is smoothed a little);
  2. everything inside the outline is put at the depth read by the sensor
     (the indenters are flat-ended), with a soft rim.

Usage from the repo root:
  python src/tactile/reconstruct_v4.py --reference REF.jpg --deformed DEF.jpg
"""

# ═══ CONFIG ═══
REF_IMAGE = ""
DEF_IMAGE = ""
OUTPUT_PATH = "output/recon_v4"
OUTLINE_FRAC = 0.30     # outline = stretch above this fraction of the peak
MIN_PIECE_FRAC = 0.10   # pieces smaller than this fraction of the largest are dropped
EDGE_SMOOTH_MM = 0.4    # smoothing of the outline
RIM_MM = 0.5            # softening of the plateau edge
WINDOW_MM = 20.0        # half-width of the square shown in the figures
SURF_GRID = 200
# ═══════════════════════════════

import argparse
import os
import sys

import cv2
import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tactile.reconstruct_v3 as rv3  # noqa: E402
import tactile.strain_map as sm  # noqa: E402


def outline_mask(stretch_fine, inside, pxmm):
    """Shape of the contact from the 2-D stretch map."""
    fine = np.where(inside, stretch_fine, 0.0)
    top = max(1, int(round(sm.PEAK_AREA_MM2 * pxmm ** 2)))
    peak = float(np.sort(fine[inside])[-top:].mean())
    mask = fine > OUTLINE_FRAC * peak
    lab, nl = ndi.label(mask)
    if nl:
        sizes = ndi.sum(mask, lab, range(1, nl + 1))
        mask = np.isin(lab, 1 + np.nonzero(sizes >= MIN_PIECE_FRAC * sizes.max())[0])
    soft = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), EDGE_SMOOTH_MM * pxmm)
    return soft > 0.5


def reconstruct(ref_path, def_path, cal):
    m = sm.measure(ref_path, def_path)
    fl = m["fields"]
    pxmm = fl["px_per_mm"]
    depth, force = cal.depth(m["peak"]), cal.force(m["integral"])
    mask = outline_mask(m["stretch_fine"], fl["inside"], pxmm)
    depth_map = cv2.GaussianBlur(depth * mask.astype(np.float32), (0, 0), RIM_MM * pxmm)
    return {"depth": depth_map, "mask": mask, "depth_mm": depth, "force_N": force,
            "peak_stretch": m["peak"], "stretch_integral_mm2": m["integral"],
            "area_mm2": float(mask.sum() / pxmm ** 2), "n_pieces": int(ndi.label(mask)[1]),
            "beyond_calibration": cal.beyond(m["peak"], m["integral"]),
            "stretch_fine": np.where(fl["inside"], m["stretch_fine"], np.nan),
            "n": fl["n"], "px_per_mm": pxmm, "deformed": fl["def"], "inside": fl["inside"]}


# --- Figures ----------------------------------------------------------------------
def window(arr, recon, half_mm=None):
    half_mm = WINDOW_MM if half_mm is None else half_mm
    n, pxmm = recon["n"], recon["px_per_mm"]
    r = min(int(round(half_mm * pxmm)), n // 2)
    return arr[n // 2 - r:n // 2 + r, n // 2 - r:n // 2 + r], (np.arange(2 * r) - r) / pxmm


def surface(ax, recon, zmax, title="", half_mm=None):
    from matplotlib import cm
    from matplotlib.colors import LightSource
    sub, axis = window(recon["depth"], recon, half_mm)
    step = max(1, sub.shape[0] // SURF_GRID)
    Z = sub[::step, ::step]
    X, Y = np.meshgrid(axis[::step], axis[::step])
    rgb = LightSource(azdeg=315, altdeg=50).shade(Z, cmap=cm.viridis, vmin=0, vmax=zmax, blend_mode="soft",
                                                  vert_exag=4)
    ax.plot_surface(X, Y, Z, facecolors=rgb, rstride=1, cstride=1, linewidth=0, antialiased=False, shade=False)
    ax.set_zlim(0, 1.15 * zmax)
    ax.set_ylim(axis[-1], axis[0])                  # image orientation: y grows downwards
    ax.set_box_aspect((1, 1, 0.3))
    ax.set_xlabel("x (mm)", fontsize=8)
    ax.set_ylabel("y (mm)", fontsize=8)
    ax.set_zlabel("depth (mm)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_title(title, fontsize=9)
    ax.view_init(elev=52, azim=-75)


def stretch_view(ax, recon, title="", half_mm=None):
    """The 2-D stretch map with the outline v4 took from it."""
    sub, axis = window(recon["stretch_fine"], recon, half_mm)
    msk, _ = window(recon["mask"], recon, half_mm)
    lim = max(1.6 * recon["peak_stretch"], 0.005)
    ext = [axis[0], axis[-1], axis[-1], axis[0]]
    ax.imshow(sub, cmap="RdBu_r", vmin=-lim, vmax=lim, extent=ext)
    ax.contour(axis, axis, msk.astype(float), levels=[0.5], colors="#0b0b0b", linewidths=1.4)
    ax.set_xlabel("x (mm)", fontsize=8)
    ax.set_ylabel("y (mm)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_title(title, fontsize=9)


def show(recon, title="", show_window=True, save_png=None):
    import matplotlib
    if not show_window:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(12.5, 5.6))
    stretch_view(fig.add_subplot(121), recon, "stretch map and outline")
    surface(fig.add_subplot(122, projection="3d"), recon, max(recon["depth_mm"], 0.1), "3-D reconstruction")
    ge = "≥ " if recon["beyond_calibration"] else ""
    fig.suptitle(f"{title}\nsensor: {ge}{recon['depth_mm']:.2f} mm, {ge}{recon['force_N']:.1f} N")
    fig.tight_layout()
    if save_png:
        fig.savefig(save_png, dpi=110, bbox_inches="tight")
    if show_window:
        plt.show()
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reference", default=REF_IMAGE)
    ap.add_argument("--deformed", default=DEF_IMAGE)
    ap.add_argument("-o", "--out", default=OUTPUT_PATH)
    ap.add_argument("--calibration", default=rv3.CALIB_CSV)
    ap.add_argument("--exclude-star", default=None, help="leave this star (e.g. S1) out of the calibration")
    ap.add_argument("--no-show", action="store_true")
    args = ap.parse_args()
    if not (args.reference and args.deformed):
        ap.error("--reference and --deformed are needed")
    cal = rv3.StretchCalibration(args.calibration, exclude=args.exclude_star)
    recon = reconstruct(args.reference, args.deformed, cal)
    os.makedirs(args.out, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.deformed))[0]
    np.save(os.path.join(args.out, f"{stem}_depth_mm.npy"), recon["depth"])
    warn = "  [beyond calibration: lower bounds]" if recon["beyond_calibration"] else ""
    print(f"outline {recon['area_mm2']:.0f} mm2 in {recon['n_pieces']} piece(s) | depth {recon['depth_mm']:.2f} mm, "
          f"force {recon['force_N']:.1f} N{warn}")
    show(recon, title=stem, show_window=not args.no_show, save_png=os.path.join(args.out, f"{stem}_3d.png"))
    print(f"saved {args.out}/{stem}_depth_mm.npy, {stem}_3d.png")


if __name__ == "__main__":
    main()
