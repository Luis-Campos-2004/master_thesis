#!/usr/bin/env python3
"""
segment_photos_v2.py — Runs the contact segmentation on the rotated photo
set (one reference + six angles per shape) and reports how stable it is.

There is no hand-drawn ground truth for this set yet, so the checks are
ground-truth-free:
    contacts   the right number of separate contacts (1, or 2 for
               Square Circle, 3 for Three Circles)
    area CV    how much the detected area varies across the six angles of
               the same tip (same tip -> it should barely change)

The photos come from a different camera setup than shape_pictures/, so the
analysis window is scaled from the stripe period to keep 1 mm = 11.8 px in
the 768 px frame, and the tight cut is lowered to 15% of each contact's peak
(the contacts show a phase ramp, and 35% cut off their weak side).

Run src/tactile/adjust_photos.py first. Usage from the repo root:
    python verification/segment_photos_v2.py
"""

import argparse
import csv
import hashlib
import os
import sys

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import tactile.detect_shape as ds          # noqa: E402
import tactile.uniform_reconstruct as ur   # noqa: E402

ROOT = "data/processed/shape_pictures_v2"
PERIOD_768 = 27.14     # stripe period (px) in the 768 frame of shape_pictures/
PX_PER_MM = 11.8       # 768-frame scale of shape_pictures/, kept by the scaling
PARAMS = dict(ds.CONTACT_PARAMS, tight_lo_frac=0.15)
EXPECTED = {"Square Circle": 2, "Three Circles": 3}     # every other shape: 1
COLOUR, SURFACE, INK = "#eb6834", "#fcfcfb", "#0b0b0b"


def crop_ratio_for(ref_path, size=ds.PROC_SIZE):
    """Crop that puts one stripe period at PERIOD_768 px in the size frame."""
    g = cv2.imread(ref_path, cv2.IMREAD_GRAYSCALE).astype(np.float32)
    h, w = g.shape
    s = min(h, w)
    sq = g[(h - s) // 2:(h + s) // 2, (w - s) // 2:(w + s) // 2]
    period = 1.0 / float(np.hypot(*ur.carrier_prior(sq)))
    return size * period / PERIOD_768 / (2 * s), period


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=ROOT)
    ap.add_argument("--out", default="verification/segment_photos_v2.csv")
    ap.add_argument("--figdir", default="figures/shape_pictures_v2")
    args = ap.parse_args()

    ref = os.path.join(args.root, "reference.png")
    crop, period = crop_ratio_for(ref)
    print(f"stripe period {period:.1f} px -> crop_ratio {crop:.3f}")
    os.makedirs(args.figdir, exist_ok=True)

    rows, seen = [], set()
    for shape in sorted(os.listdir(args.root)):
        folder = os.path.join(args.root, shape)
        if not os.path.isdir(folder):
            continue
        shots = []
        for f in sorted(os.listdir(folder)):
            path = os.path.join(folder, f)
            digest = hashlib.md5(open(path, "rb").read()).hexdigest()
            if digest in seen:
                print(f"  {shape}/{f}: same photo as an earlier angle, skipped")
                continue
            seen.add(digest)
            shots.append((f, ds.detect(ref, path, crop_ratio=crop, **PARAMS)))

        fig, axes = plt.subplots(1, len(shots), figsize=(3.2 * len(shots), 3.7),
                                 facecolor=SURFACE)
        for ax, (f, res) in zip(np.atleast_1d(axes), shots):
            angle = os.path.splitext(f)[0].replace("rot_", "")
            area = float(res["mask"].sum()) / PX_PER_MM ** 2
            n_c = res.get("n_contacts", 0)
            rows.append({"shape": shape, "angle_deg": int(angle), "contacts": n_c,
                         "expected": EXPECTED.get(shape, 1),
                         "area_mm2": round(area, 1)})
            img, roi = res["def"], res["roi"]
            lo, hi = np.percentile(img[roi], [1, 99])
            ax.imshow(np.clip((img - lo) / (hi - lo + 1e-9), 0, 1), cmap="gray")
            if res["mask"].any():
                ax.contour((res["mask"] > 0).astype(float), levels=[0.5],
                           colors=COLOUR, linewidths=1.8)
            n = img.shape[0]
            ax.set_xlim(0.12 * n, 0.88 * n)
            ax.set_ylim(0.88 * n, 0.12 * n)
            ax.set_title(f"{int(angle)}°   {n_c} contact(s), {area:.0f} mm²",
                         color=INK, fontsize=9)
            ax.set_axis_off()
        fig.suptitle(shape, color=INK, fontsize=12, fontweight="bold")
        fig.tight_layout(rect=(0, 0, 1, 0.92))
        fig.savefig(os.path.join(args.figdir, shape.replace(" ", "_") + ".png"),
                    dpi=110, facecolor=SURFACE)
        plt.close(fig)

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    print(f"\n{'shape':<15}{'right contact count':>21}{'area mean (mm2)':>17}"
          f"{'area CV':>9}")
    ok_all = 0
    for shape in dict.fromkeys(r["shape"] for r in rows):
        rs = [r for r in rows if r["shape"] == shape]
        ok = sum(r["contacts"] == r["expected"] for r in rs)
        a = np.array([r["area_mm2"] for r in rs])
        ok_all += ok
        print(f"{shape:<15}{ok:>17}/{len(rs)}{a.mean():>17.0f}"
              f"{100 * a.std() / max(a.mean(), 1e-9):>8.0f}%")
    print(f"{'all':<15}{ok_all:>17}/{len(rows)}")
    print(f"\nper-photo results -> {args.out}\nfigures -> {args.figdir}/")


if __name__ == "__main__":
    main()
