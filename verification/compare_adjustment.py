#!/usr/bin/env python3
"""
compare_adjustment.py — Shows what the brightness/contrast adjustment
(src/tactile/adjust_photos.py) changes in the contact segmentation of the
rotated photo set.

For every shape it draws one figure with two rows over the six angles:
    top     original photo (only aligned to the reference)
    bottom  adjusted photo (aligned + flat-field + contrast stretch)
each with the detected contour, its number of contacts and area. It also
lists the photos whose contact count went from wrong to right (improved)
or right to wrong (worse) with the adjustment.

Run src/tactile/adjust_photos.py first. Usage from the repo root:
    python verification/compare_adjustment.py
"""

import argparse
import csv
import hashlib
import os
import sys
import tempfile

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
import tactile.adjust_photos as ap          # noqa: E402
import tactile.detect_shape as ds          # noqa: E402
import segment_photos_v2 as sp2            # noqa: E402

RAW = "data/raw/shape_pictures_v2"
ADJ = "data/processed/shape_pictures_v2"
OUT = "results/segmentation_v2/shape_pictures_v2/brightness_contrast"
RIGHT, WRONG, SURFACE, INK = "#1baf7a", "#eb6834", "#fcfcfb", "#0b0b0b"


def show(ax, res, title, ok):
    """Photo as it is (0..255, so the adjustment is visible) + contour."""
    img = res["def"]
    ax.imshow(img, cmap="gray", vmin=0, vmax=255)
    if res["mask"].any():
        ax.contour((res["mask"] > 0).astype(float), levels=[0.5],
                   colors=RIGHT if ok else WRONG, linewidths=1.8)
    n = img.shape[0]
    ax.set_xlim(0.12 * n, 0.88 * n)
    ax.set_ylim(0.88 * n, 0.12 * n)
    ax.set_title(title, color=INK, fontsize=8.5)
    ax.set_axis_off()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=OUT)
    args = p.parse_args()
    os.makedirs(args.out, exist_ok=True)

    ref_raw = os.path.join(RAW, "reference.jpg")
    ref_adj = os.path.join(ADJ, "reference.png")
    crop, _ = sp2.crop_ratio_for(ref_adj)
    ref_g = cv2.imread(ref_raw, cv2.IMREAD_GRAYSCALE).astype(np.float32)
    window = cv2.createHanningWindow(ref_g.shape[::-1], cv2.CV_32F)

    rows, seen = [], set()
    with tempfile.TemporaryDirectory() as tmp:
        for shape in sorted(os.listdir(RAW)):
            folder = os.path.join(RAW, shape)
            if not os.path.isdir(folder):
                continue
            expected = sp2.EXPECTED.get(shape, 1)
            pairs = []
            for f in sorted(os.listdir(folder)):
                path = os.path.join(folder, f)
                digest = hashlib.md5(open(path, "rb").read()).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                stem = os.path.splitext(f)[0]
                gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE).astype(np.float32)
                aligned, _ = ap.align(gray, ref_g, window)
                raw_path = os.path.join(tmp, f"{shape}_{stem}.png")
                cv2.imwrite(raw_path, np.clip(aligned, 0, 255).astype(np.uint8))
                r_raw = ds.detect(ref_raw, raw_path, crop_ratio=crop, **sp2.PARAMS)
                r_adj = ds.detect(ref_adj, os.path.join(ADJ, shape, stem + ".png"),
                                  crop_ratio=crop, **sp2.PARAMS)
                pairs.append((stem, r_raw, r_adj))
                n_raw, n_adj = r_raw.get("n_contacts", 0), r_adj.get("n_contacts", 0)
                change = ("improved" if n_raw != expected and n_adj == expected else
                          "worse" if n_raw == expected and n_adj != expected else "same")
                rows.append({"shape": shape, "angle_deg": int(stem.replace("rot_", "")),
                             "expected": expected, "contacts_original": n_raw,
                             "contacts_adjusted": n_adj, "change": change,
                             "area_original_mm2": round(float(r_raw["mask"].sum()) / sp2.PX_PER_MM ** 2, 1),
                             "area_adjusted_mm2": round(float(r_adj["mask"].sum()) / sp2.PX_PER_MM ** 2, 1)})

            fig, axes = plt.subplots(2, len(pairs), figsize=(3.1 * len(pairs), 7.8),
                                     facecolor=SURFACE, squeeze=False,
                                     gridspec_kw={"hspace": 0.35})
            for j, (stem, r_raw, r_adj) in enumerate(pairs):
                angle = int(stem.replace("rot_", ""))
                for i, (label, res) in enumerate((("original", r_raw), ("adjusted", r_adj))):
                    n_c = res.get("n_contacts", 0)
                    area = float(res["mask"].sum()) / sp2.PX_PER_MM ** 2
                    show(axes[i, j], res, f"{label} {angle}°\n{n_c} contact(s), {area:.0f} mm²",
                         n_c == expected)
            fig.suptitle(f"{shape}: green = right number of contacts ({expected}), "
                         f"orange = wrong", color=INK, fontsize=11, fontweight="bold")
            fig.subplots_adjust(left=0.01, right=0.99, bottom=0.01, top=0.88,
                                wspace=0.05)
            fig.savefig(os.path.join(args.out, shape.replace(" ", "_") + ".png"),
                        dpi=100, facecolor=SURFACE)
            plt.close(fig)

    with open(os.path.join(args.out, "comparison.csv"), "w", newline="",
              encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    for kind in ("improved", "worse"):
        hits = [r for r in rows if r["change"] == kind]
        print(f"{kind} with the adjustment: {len(hits)}")
        for r in hits:
            print(f"  {r['shape']} {r['angle_deg']}°: {r['contacts_original']} -> "
                  f"{r['contacts_adjusted']} contacts (expected {r['expected']})")
    ok_raw = sum(r["contacts_original"] == r["expected"] for r in rows)
    ok_adj = sum(r["contacts_adjusted"] == r["expected"] for r in rows)
    print(f"\nright number of contacts: original {ok_raw}/{len(rows)}, "
          f"adjusted {ok_adj}/{len(rows)}")
    print(f"figures + comparison.csv -> {args.out}/")


if __name__ == "__main__":
    main()
