#!/usr/bin/env python3
"""
compare_liam_figures.py — The 3-D figures Liam showed in his thesis, next to
reconstruct_v2.py on the same photo.

Left: Liam's figure exactly as he saved it (results/images_report/).
Right: v2 on the photo it was made from, drawn with Liam's own plotting
function (uniform_reconstruct.show_3d), so only the algorithm differs.
Only figures whose photo is in the repository can be compared; the others are
listed at the end.

Writes results/reconstruction_v2/liam_vs_v2/<case>.png.
Usage from the repo root:
    python verification/compare_liam_figures.py
"""

import contextlib
import io
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import tactile.estimate_force_depth as efd     # noqa: E402
import tactile.reconstruct_v2 as rv            # noqa: E402
import tactile.uniform_reconstruct as ur       # noqa: E402

OUT = "results/reconstruction_v2/liam_vs_v2"
FIG = "results/images_report"
INK, INK2, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"
# (case, Liam's figure, reference, deformed, how sure the photo is, true force N or None)
CASES = [
    ("circle_30N", f"{FIG}/3d_recon/circle_30.png", rv.FORCE_REF, "data/raw/force_pictures/30N/img_04.jpg",
     "probable: Liam's thesis does not say which of the five 30 N photos (img_04 is a v2 test photo)", 30.0),
    ("square_circle", f"{FIG}/figures/square_circle_side.png", "data/raw/shape_pictures/Square Circle/img_01.jpg",
     "data/raw/shape_pictures/Square Circle/img_02.jpg", "the only square + circle tip in the data", None),
    ("three_circles", f"{FIG}/3d_recon/three_circ_same.png", "data/raw/shape_pictures/Three Circles/img_01.jpg",
     "data/raw/shape_pictures/Three Circles/img_02.jpg", "probable: same layout of three circles", None),
    ("integrated_pipeline", f"{FIG}/figures_final/depth_3d.png", "data/raw/final_images/ref_image.jpg",
     "data/raw/final_images/def_image.jpg", "the example pair of the final figures (README)", None),
]
NO_PHOTO = ["3d_recon/circle_40.png (40 N)", "3d_recon/circle_50.png (50 N)", "figures/circle_depth.png",
            "figures/square_depth.png", "3d_recon/big_square.png", "3d_recon/small_square.png",
            "3d_recon/three_circ_diff.png"]


def main():
    os.makedirs(OUT, exist_ok=True)
    cal1 = efd.Calibration(ur.RATIO_CSV, ur.DEPTH_CSV)
    cal2 = rv.StretchCalibration(rv.CALIB_CSV)
    for case, liam_png, ref, dfm, sure, F in CASES:
        with contextlib.redirect_stdout(io.StringIO()):
            rec2 = rv.reconstruct(ref, dfm, cal2)
            v2_png = os.path.join(OUT, f"_{case}_v2_render.png")
            ur.show_3d(rec2, title="v2", show=False, save_png=v2_png)
            try:
                now = ur.reconstruct_global(ref, dfm, cal1)["report"]
            except RuntimeError:
                now = []
        v2_txt = " | ".join(("≥ " if r["beyond_calibration"] else "") + f"{r['depth_mm']:.2f} mm, "
                            + ("≥ " if r["beyond_calibration"] else "") + f"{r['force_N']:.1f} N"
                            for r in rec2["report"]) or "no contact"
        now_txt = " | ".join(f"{r['depth_mm']:.2f} mm, {r['force_N']:.1f} N" for r in now) or "no contact"
        truth = (f"true: {F:.0f} N, {cal1.depth_from_force(F):.2f} mm (Mark-10)" if F
                 else "true force and depth: not recorded")
        fig, axes = plt.subplots(1, 2, figsize=(15, 6.6), facecolor=SURFACE)
        for ax, png, title in ((axes[0], liam_png, "Liam, figure from his thesis"),
                               (axes[1], v2_png, f"v2 on the same photo\n{v2_txt}")):
            ax.imshow(plt.imread(png))
            ax.set_title(title, color=INK, fontsize=11)
            ax.axis("off")
        fig.suptitle(f"{case.replace('_', ' ')}  ·  {os.path.relpath(dfm)}", color=INK, fontsize=12, fontweight="bold")
        fig.text(0.5, 0.02, f"{truth}   ·   photo: {sure}   ·   Liam's code as it is in the repository today "
                 f"gives: {now_txt}", ha="center", color=INK2, fontsize=9)
        fig.tight_layout(rect=(0, 0.05, 1, 0.94))
        path = os.path.join(OUT, f"{case}.png")
        fig.savefig(path, dpi=110, facecolor=SURFACE)
        plt.close(fig)
        os.remove(v2_png)
        print(f"  {path}\n     v2: {v2_txt}\n     Liam's current code: {now_txt}\n     {truth}", flush=True)
    print("\nLiam figures without their photo in the repository (cannot be compared):")
    for f in NO_PHOTO:
        print(f"  results/images_report/{f}")
    print(f"-> {OUT}/")


if __name__ == "__main__":
    main()
