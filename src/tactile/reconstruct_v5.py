"""
reconstruct_v5.py
=================
3-D reconstruction, version 5: same depth, force and flat-top surface as
reconstruct_v4.py, with a better outline. reconstruct_v3.py and
reconstruct_v4.py are not changed.

v4 took the outline from the stretch map alone. The stripes only show stretch
across them, so parts of a shape that cross the stripes were missing or came
out as separate blobs.

v5 adds a second cue from the same photo: where the indenter's edge is, the
stripes are broken and their contrast (fringe amplitude) drops. That edge line
shows in every direction. The outline is a marker-based watershed:
  * inside marker  = the main body of high stretch (pieces of high stretch
    that the edge line separates from it are left out);
  * outside marker = membrane with almost no stretch;
  * the boundary between them settles on the edge line (amplitude drop, with
    the gaps between its dots closed), or on the v4 level where there is none.
The edge line only appears once the press is deep enough; for light presses
the outline is therefore close to the v4 one.

Usage from the repo root:
  python src/tactile/reconstruct_v5.py --reference REF.jpg --deformed DEF.jpg
"""

# ═══ CONFIG ═══
REF_IMAGE = ""
DEF_IMAGE = ""
OUTPUT_PATH = "output/recon_v5"
EDGE_BW_FRAC = 0.6      # FTP band-pass for the amplitude (wider = sharper edge line)
EDGE_SMOOTH_T = 0.25    # smoothing of the amplitude drop (stripe periods)
EDGE_CLOSE_MM = 1.5     # gaps of the edge line shorter than this are closed
CORE_FRAC = 0.6         # inside marker = stretch above this fraction of the peak
OUTSIDE_FRAC = 0.12     # outside marker = stretch below this fraction of the peak
EDGE_CUT = 0.3          # edge strength (0-1.5) above which the edge line separates regions
LEVEL_WEIGHT = 0.15     # weight of the v4 level where there is no edge line
WINDOW_MM = 27.0        # half-width of the square shown in the figures
# ═══════════════════════════════

import argparse
import os
import sys

import cv2
import numpy as np
from scipy import ndimage as ndi
from skimage.segmentation import watershed

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tactile.detect_shape as ds  # noqa: E402
import tactile.reconstruct_v3 as rv3  # noqa: E402
import tactile.reconstruct_v4 as rv4  # noqa: E402
import tactile.strain_map as sm  # noqa: E402


def amplitude_drop(ref_path, def_path, period):
    """Relative loss of fringe amplitude, pressed photo against reference (0 = none)."""
    g_ref, g_def = sm.load_frame(ref_path), sm.load_frame(def_path)
    hp = lambda g: g - cv2.GaussianBlur(g, (0, 0), sm.BG_SIGMA_T * period)      # noqa: E731
    _, car = ds.find_carrier(g_ref)
    z_ref, _ = ds.demodulate(hp(g_ref), car, bw_frac=EDGE_BW_FRAC)
    z_def, _ = ds.demodulate(hp(g_def), car, bw_frac=EDGE_BW_FRAC)
    drop = np.clip(1 - np.abs(z_def) / np.maximum(np.abs(z_ref), 1e-6), 0, None).astype(np.float32)
    return cv2.GaussianBlur(drop, (0, 0), EDGE_SMOOTH_T * period)


def edge_outline(rel, drop, inside, pxmm):
    """Watershed outline and how strongly its boundary sits on the edge line (0-1.5)."""
    scale = np.percentile(drop[inside & (rel > 0.1)], 99) + 1e-9
    edge = np.clip(drop / scale, 0, 1.5)
    r = int(round(EDGE_CLOSE_MM * pxmm))
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    edge = ndi.grey_closing(edge, footprint=(yy ** 2 + xx ** 2) <= r ** 2)
    land = edge + LEVEL_WEIGHT * np.exp(-((rel - rv4.OUTLINE_FRAC) / 0.1) ** 2)
    core = (rel > CORE_FRAC) & (edge < EDGE_CUT)
    lab, nl = ndi.label(core)
    if nl == 0:
        return np.zeros_like(inside), 0.0
    biggest = lab == 1 + int(np.argmax(ndi.sum(core, lab, range(1, nl + 1))))
    # keep the other pieces of high stretch only if they join the biggest one without crossing the edge line
    body, _ = ndi.label((rel > rv4.OUTLINE_FRAC) & (edge < EDGE_CUT))
    core &= body == np.bincount(body[biggest]).argmax()
    markers = np.zeros(rel.shape, np.int32)
    markers[(rel < OUTSIDE_FRAC) | ~inside] = 1
    markers[core] = 2
    mask = ndi.binary_opening(watershed(land, markers) == 2, iterations=1)
    boundary = ndi.binary_dilation(mask, iterations=2) & ~ndi.binary_erosion(mask, iterations=2)
    return mask, float(edge[boundary].mean()) if boundary.any() else 0.0


def reconstruct(ref_path, def_path, cal):
    m = sm.measure(ref_path, def_path)
    fl = m["fields"]
    inside, pxmm = fl["inside"], fl["px_per_mm"]
    depth, force = cal.depth(m["peak"]), cal.force(m["integral"])

    fine = np.where(inside, m["stretch_fine"], 0.0)
    top = max(1, int(round(sm.PEAK_AREA_MM2 * pxmm ** 2)))
    rel = fine / max(float(np.sort(fine[inside])[-top:].mean()), 1e-9)
    drop = amplitude_drop(ref_path, def_path, fl["period"])
    mask, strength = edge_outline(rel, drop, inside, pxmm)
    if not mask.any():
        mask = rv4.outline_mask(m["stretch_fine"], inside, pxmm)
    depth_map = cv2.GaussianBlur(depth * mask.astype(np.float32), (0, 0), rv4.RIM_MM * pxmm)
    return {"depth": depth_map, "mask": mask, "depth_mm": depth, "force_N": force,
            "peak_stretch": m["peak"], "stretch_integral_mm2": m["integral"],
            "area_mm2": float(mask.sum() / pxmm ** 2), "n_pieces": int(ndi.label(mask)[1]),
            "edge_strength": strength,
            "beyond_calibration": cal.beyond(m["peak"], m["integral"]),
            "stretch_fine": np.where(inside, m["stretch_fine"], np.nan), "amplitude_drop": drop,
            "n": fl["n"], "px_per_mm": pxmm, "deformed": fl["def"], "inside": inside}


def edge_view(ax, recon, title=""):
    """The amplitude drop (edge line) with the outline taken."""
    sub, axis = rv4.window(recon["amplitude_drop"], recon, WINDOW_MM)
    msk, _ = rv4.window(recon["mask"], recon, WINDOW_MM)
    ax.imshow(sub, cmap="magma", vmin=0, vmax=max(float(np.percentile(sub, 99.5)), 0.05),
              extent=[axis[0], axis[-1], axis[-1], axis[0]])
    ax.contour(axis, axis, msk.astype(float), levels=[0.5], colors="#7fe3ff", linewidths=1.2)
    ax.set_xlabel("x (mm)", fontsize=8)
    ax.set_ylabel("y (mm)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_title(title, fontsize=9)


def show(recon, title="", show_window=True, save_png=None):
    import matplotlib
    if not show_window:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(17, 5.6))
    rv4.stretch_view(fig.add_subplot(131), recon, "stretch map and outline", WINDOW_MM)
    edge_view(fig.add_subplot(132), recon, "loss of stripe contrast (edge line) and outline")
    rv4.surface(fig.add_subplot(133, projection="3d"), recon, max(recon["depth_mm"], 0.1), "3-D reconstruction",
                WINDOW_MM)
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
    print(f"outline {recon['area_mm2']:.0f} mm2 in {recon['n_pieces']} piece(s), edge strength "
          f"{recon['edge_strength']:.2f} | depth {recon['depth_mm']:.2f} mm, "
          f"force {recon['force_N']:.1f} N{warn}")
    show(recon, title=stem, show_window=not args.no_show, save_png=os.path.join(args.out, f"{stem}_3d.png"))
    print(f"saved {args.out}/{stem}_depth_mm.npy, {stem}_3d.png")


if __name__ == "__main__":
    main()
