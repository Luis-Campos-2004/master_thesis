#!/usr/bin/env python3
"""
show_adjusted.py — Before/after pictures of the brightness/contrast step
(src/tactile/adjust_photos.py): original photo on top, adjusted photo below,
cropped to the analysis window.

    <out>/overview.png      every shape at its first angle
    <out>/<Shape>.png       every angle of one shape

Run adjust_photos.py first. Usage from the repo root:
    python verification/show_adjusted.py
    python verification/show_adjusted.py data/raw/shape_pictures_v3 data/processed/shape_pictures_v3
"""

import argparse
import os
import sys

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
import segment_photos_v2 as sp2            # noqa: E402

SURFACE, INK = "#fcfcfb", "#0b0b0b"


def crop(img, ratio):
    h, w = img.shape[:2]
    r = int(min(h, w) * ratio)
    return img[h // 2 - r:h // 2 + r, w // 2 - r:w // 2 + r]


def pair(raw_root, adj_root, shape, name, ratio):
    raw = cv2.cvtColor(cv2.imread(os.path.join(raw_root, shape, name + ".jpg")), cv2.COLOR_BGR2RGB)
    adj = cv2.imread(os.path.join(adj_root, shape, name + ".png"), cv2.IMREAD_GRAYSCALE)
    return crop(raw, ratio), crop(adj, ratio)


def sheet(path, columns, title):
    """columns: list of (label, original, adjusted)."""
    fig, axes = plt.subplots(2, len(columns), figsize=(2.9 * len(columns), 6.4),
                             facecolor=SURFACE, squeeze=False)
    for j, (label, raw, adj) in enumerate(columns):
        axes[0, j].imshow(raw)
        axes[1, j].imshow(adj, cmap="gray", vmin=0, vmax=255)
        axes[0, j].set_title(label, color=INK, fontsize=10)
        for ax in axes[:, j]:
            ax.set_axis_off()
    axes[0, 0].text(-0.06, 0.5, "original", transform=axes[0, 0].transAxes, rotation=90,
                    ha="right", va="center", color=INK, fontsize=11)
    axes[1, 0].text(-0.06, 0.5, "adjusted", transform=axes[1, 0].transAxes, rotation=90,
                    ha="right", va="center", color=INK, fontsize=11)
    fig.suptitle(title, color=INK, fontsize=12, fontweight="bold")
    fig.subplots_adjust(left=0.04, right=0.995, bottom=0.01, top=0.88, wspace=0.04, hspace=0.12)
    fig.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("raw", nargs="?", default="data/raw/shape_pictures_v3")
    p.add_argument("adjusted", nargs="?", default="data/processed/shape_pictures_v3")
    p.add_argument("--out", default="results/segmentation_v2/shape_pictures_v3/before_after")
    args = p.parse_args()
    os.makedirs(args.out, exist_ok=True)
    ratio, _ = sp2.crop_ratio_for(os.path.join(args.adjusted, "reference.png"))

    first = []
    for shape in sorted(os.listdir(args.adjusted)):
        folder = os.path.join(args.adjusted, shape)
        if not os.path.isdir(folder):
            continue
        names = sorted(os.path.splitext(f)[0] for f in os.listdir(folder) if f.endswith(".png"))
        cols = [(f"{int(n.replace('rot_', ''))}°" if n.startswith("rot_") else n,
                 *pair(args.raw, args.adjusted, shape, n, ratio)) for n in names]
        sheet(os.path.join(args.out, shape.replace(" ", "_") + ".png"), cols,
              f"{shape}: brightness/contrast adjustment")
        first.append((shape, *cols[0][1:]))
        print(f"  {shape}: {len(cols)} photos")
    sheet(os.path.join(args.out, "overview.png"), first,
          "Brightness/contrast adjustment: one photo per shape")
    print(f"-> {args.out}/ (overview.png + one image per shape)")


if __name__ == "__main__":
    main()
