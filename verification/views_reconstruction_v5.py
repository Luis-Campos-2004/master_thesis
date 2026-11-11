#!/usr/bin/env python3
"""
views_reconstruction_v5.py — The 3-D reconstruction (reconstruct_v5.py) of each
star seen from several sides, next to the photo it was made from.

One figure per star at its deepest press: the pressed photo with the outline,
the depth map from above, and the surface from four viewpoints (two oblique,
one low from the side, one straight from above). Plus one figure with the four
stars together. Calibration from the other three stars, as in the evaluation.

Writes results/reconstruction_v5/views/.
Usage from the repo root:
    python verification/views_reconstruction_v5.py
"""

import argparse
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import tactile.reconstruct_v3 as rv3           # noqa: E402
import tactile.reconstruct_v4 as rv4           # noqa: E402
import tactile.reconstruct_v5 as rv5           # noqa: E402

ROOT = rv3.STARS_DIR
OUT = "results/reconstruction_v5/views"
STARS = ["S1", "S2", "S3", "S4"]
VIEWS = [("oblique, front left", 42, -65), ("oblique, back right", 42, 115),
         ("low, from the side", 14, -90), ("from above", 89.9, -90)]
INK, SURFACE = "#0b0b0b", "#fcfcfb"


def photo_view(ax, rec, title):
    sub, axis = rv4.window(rec["deformed"], rec, rv5.WINDOW_MM)
    msk, _ = rv4.window(rec["mask"], rec, rv5.WINDOW_MM)
    lo, hi = np.percentile(sub, [1, 99])
    ax.imshow(sub, cmap="gray", vmin=lo, vmax=hi, extent=[axis[0], axis[-1], axis[-1], axis[0]])
    ax.contour(axis, axis, msk.astype(float), levels=[0.5], colors="#eb6834", linewidths=1.5)
    ax.set_xlabel("x (mm)", fontsize=8)
    ax.set_ylabel("y (mm)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_title(title, fontsize=9)


def depth_view(ax, rec, zmax, title):
    sub, axis = rv4.window(rec["depth"], rec, rv5.WINDOW_MM)
    im = ax.imshow(sub, cmap="viridis", vmin=0, vmax=zmax, extent=[axis[0], axis[-1], axis[-1], axis[0]])
    ax.set_xlabel("x (mm)", fontsize=8)
    ax.set_ylabel("y (mm)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_title(title, fontsize=9)
    return im


def numbers(r, rec):
    ge = "≥ " if rec["beyond_calibration"] else ""
    return (f"MARK-10: {float(r['depth_mm']):.1f} mm, "
            f"{0.5 * (float(r['force_lo_N']) + float(r['force_hi_N'])):.1f} N   ·   "
            f"sensor: {ge}{rec['depth_mm']:.2f} mm, {ge}{rec['force_N']:.1f} N")


def star_figure(star, r, rec, path):
    zmax = max(rec["depth_mm"], 0.1)
    fig = plt.figure(figsize=(17, 10.5), facecolor=SURFACE)
    photo_view(fig.add_subplot(2, 3, 1), rec, "pressed photo and outline found")
    rv4.stretch_view(fig.add_subplot(2, 3, 2), rec, "stripe stretch and outline", rv5.WINDOW_MM)
    im = depth_view(fig.add_subplot(2, 3, 3), rec, zmax, "reconstructed depth, from above")
    fig.colorbar(im, ax=fig.axes[-1], shrink=0.8, label="depth (mm)")
    for k, (name, elev, azim) in enumerate(VIEWS[:3]):
        ax = fig.add_subplot(2, 3, 4 + k, projection="3d")
        rv4.surface(ax, rec, zmax, name, rv5.WINDOW_MM)
        ax.view_init(elev=elev, azim=azim)
    fig.suptitle(f"{star}: 3-D reconstruction from several sides\n{numbers(r, rec)}", color=INK, fontsize=12,
                 fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=100, facecolor=SURFACE)
    plt.close(fig)


def all_figure(items, path):
    fig = plt.figure(figsize=(4.3 * len(items), 4.1 * (len(VIEWS) + 1)), facecolor=SURFACE)
    for j, (star, r, rec) in enumerate(items):
        photo_view(fig.add_subplot(len(VIEWS) + 1, len(items), j + 1), rec,
                   f"{star}\n" + numbers(r, rec).replace("   ·   ", "\n"))
        for k, (name, elev, azim) in enumerate(VIEWS):
            ax = fig.add_subplot(len(VIEWS) + 1, len(items), (k + 1) * len(items) + j + 1, projection="3d")
            rv4.surface(ax, rec, max(rec["depth_mm"], 0.1), name if j == 0 else "", rv5.WINDOW_MM)
            ax.view_init(elev=elev, azim=azim)
    fig.suptitle("The four stars at their deepest press: photo with the outline (top) and the reconstruction "
                 "from four viewpoints", color=INK, fontsize=12, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path, dpi=100, facecolor=SURFACE)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=OUT)
    args = p.parse_args()
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(ROOT, "log_sheet.csv"), newline="", encoding="utf-8") as fh:
        log = [r for r in csv.DictReader(fh) if r["file"] and r["angle_deg"] == "0" and r["repeat"] == "1"]
    items = []
    for star in STARS:
        r = max((x for x in log if x["star"] == star), key=lambda x: float(x["depth_mm"]))
        rec = rv5.reconstruct(os.path.join(ROOT, r["ref_file"]), os.path.join(ROOT, r["file"]),
                              rv3.StretchCalibration(rv3.CALIB_CSV, exclude=star))
        star_figure(star, r, rec, os.path.join(args.out, f"{star}_views.png"))
        items.append((star, r, rec))
        print(f"  {star}: {r['file']} -> {args.out}/{star}_views.png", flush=True)
    all_figure(items, os.path.join(args.out, "all_stars_views.png"))
    print(f"-> {args.out}/ (one figure per star + all_stars_views.png)")


if __name__ == "__main__":
    main()
