#!/usr/bin/env python3
"""
fuse_angles.py — Tests whether combining the six rotated photos of a tip
gives a better shape than any single photo.

For each shape in the rotated set:
  1. segment every angle with the same settings as segment_photos_v2.py;
  2. rotate each mask back to the 0-degree frame. The rotation axis is
     estimated as the mean of the six mask centroids (with six equally
     spaced angles the offsets cancel out) and refined by maximising the
     agreement between the rotated masks; the rotation sense is picked the
     same way;
  3. fuse by voting: a pixel belongs to the shape when at least k of the
     angles agree (k = 1 is the union, k = 6 the intersection).

Scoring: there is no ground truth for the rotated set, but five of its tips
also appear in shape_pictures/, where Liam's hand-drawn outline gives the
true shape. Each mask is compared with that outline after the best
rotation, mirror, translation and a small scale change (0.9-1.1), so the
score measures shape, not position: IoU of single angles vs IoU of the fused
shapes.

Run src/tactile/adjust_photos.py first. Usage from the repo root:
    python verification/fuse_angles.py
"""

import argparse
import csv
import hashlib
import os
import re
import sys

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
import tactile.detect_shape as ds          # noqa: E402
import eval_segmentation as ev             # noqa: E402
import segment_photos_v2 as sp2            # noqa: E402

ROOT = "data/processed/shape_pictures_v2"
OLD = "data/raw/shape_pictures"
OUT = "results/segmentation_v2/shape_pictures_v2/fusion"
N = 384                    # working size for alignment (half the detection frame)
SURFACE, INK = "#fcfcfb", "#0b0b0b"
C_SINGLE, C_FUSED, C_TEMPLATE = "#2a78d6", "#eb6834", "#1baf7a"


def small(mask):
    return cv2.resize(mask.astype(np.float32), (N, N), interpolation=cv2.INTER_AREA) > 0.5


def rotate(mask, angle, centre, scale=1.0):
    m = cv2.getRotationMatrix2D((float(centre[0]), float(centre[1])), float(angle), scale)
    return cv2.warpAffine(mask.astype(np.float32), m, (N, N), flags=cv2.INTER_LINEAR) > 0.5


def iou(a, b):
    return (a & b).sum() / max((a | b).sum(), 1)


def centroid(mask):
    ys, xs = np.nonzero(mask)
    return np.array([xs.mean(), ys.mean()]) if len(xs) else np.array([N / 2, N / 2])


def agreement(masks, angles, centre, sense):
    back = [rotate(m, sense * a, centre) for m, a in zip(masks, angles)]
    pairs = [iou(back[i], back[j]) for i in range(len(back)) for j in range(i + 1, len(back))]
    return float(np.mean(pairs)), back


def align_all(masks, angles):
    """Rotation axis and sense that make the rotated-back masks agree best."""
    c0 = np.mean([centroid(m) for m in masks], axis=0)
    best = (-1.0, None, None, None)
    for sense in (1, -1):
        for step, span, start in ((4, 24, c0), (1, 4, None)):
            centre0 = start if start is not None else best[1]
            if start is None and best[2] != sense:
                continue
            for dx in range(-span, span + 1, step):
                for dy in range(-span, span + 1, step):
                    c = centre0 + (dx, dy)
                    score, back = agreement(masks, angles, c, sense)
                    if score > best[0]:
                        best = (score, c, sense, back)
    return best


def shape_iou(mask, template):
    """Best IoU between mask and template over rotation, mirror, shift and +-10% scale."""
    if not mask.any():
        return 0.0, None
    mc = centroid(mask)
    best = (0.0, None)
    for mirror in (False, True):
        t = template[:, ::-1] if mirror else template
        tc = centroid(t)
        for phi in range(0, 360, 4):
            for sc in (0.9, 1.0, 1.1):
                m = cv2.getRotationMatrix2D((float(tc[0]), float(tc[1])), phi, sc)
                m[:, 2] += mc - tc
                tw = cv2.warpAffine(t.astype(np.float32), m, (N, N)) > 0.5
                v = iou(mask, tw)
                if v > best[0]:
                    best = (v, (mirror, phi, sc, m))
    if best[1] is None:
        return best
    # small shift refinement around the best placement
    mirror, phi, sc, m = best[1]
    t = (template[:, ::-1] if mirror else template).astype(np.float32)
    for dx in range(-6, 7, 2):
        for dy in range(-6, 7, 2):
            m2 = m.copy()
            m2[:, 2] += (dx, dy)
            tw = cv2.warpAffine(t, m2, (N, N)) > 0.5
            v = iou(mask, tw)
            if v > best[0]:
                best = (v, (mirror, phi, sc, m2))
    return best


def placed_template(template, placement):
    mirror, _, _, m = placement
    t = (template[:, ::-1] if mirror else template).astype(np.float32)
    return cv2.warpAffine(t, m, (N, N)) > 0.5


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=OUT)
    args = p.parse_args()
    os.makedirs(args.out, exist_ok=True)

    ref = os.path.join(ROOT, "reference.png")
    crop, _ = sp2.crop_ratio_for(ref)
    templates = {shape: small(ev.gt_mask(gt)) for shape, _, _, _, gt in ev.find_pairs(OLD)}

    rows, seen = [], set()
    for shape in sorted(os.listdir(ROOT)):
        folder = os.path.join(ROOT, shape)
        if not os.path.isdir(folder):
            continue
        masks, angles, photo = [], [], None
        for f in sorted(os.listdir(folder)):
            path = os.path.join(folder, f)
            digest = hashlib.md5(open(path, "rb").read()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            res = ds.detect(ref, path, crop_ratio=crop, **sp2.PARAMS)
            masks.append(small(res["mask"]))
            angles.append(int(re.search(r"(\d+)", f).group(1)))
            if photo is None:
                photo = cv2.resize(res["def"], (N, N), interpolation=cv2.INTER_AREA)

        agree, centre, sense, back = align_all(masks, angles)
        votes = np.sum(back, axis=0)
        fused = {k: votes >= k for k in range(1, len(back) + 1)}
        template = templates.get(shape)

        row = {"shape": shape, "angles": len(back), "agreement_iou": round(agree, 3),
               "rotation_sense": sense}
        if template is not None:
            singles = [shape_iou(m, template)[0] for m in masks]
            row.update(single_mean=round(float(np.mean(singles)), 3),
                       single_best=round(float(np.max(singles)), 3))
            for k, fm in fused.items():
                row[f"fused_k{k}"] = round(shape_iou(fm, template)[0], 3)
        rows.append(row)

        # figure: rotated-back single contours | vote map | fused shape (+ template)
        k_major = (len(back) + 1) // 2
        fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.6), facecolor=SURFACE)
        for ax in axes:
            ax.imshow(photo, cmap="gray", vmin=0, vmax=255)
            ax.set_axis_off()
        for m in back:
            if m.any():
                axes[0].contour(m.astype(float), levels=[0.5], colors=C_SINGLE,
                                linewidths=1.0, alpha=0.8)
        axes[0].set_title("each angle, rotated back to 0°", color=INK, fontsize=10)
        im = axes[1].imshow(np.ma.masked_equal(votes, 0), cmap="viridis",
                            vmin=1, vmax=len(back), alpha=0.85)
        fig.colorbar(im, ax=axes[1], fraction=0.046, pad=0.02, label="angles agreeing")
        axes[1].set_title("how many angles see each pixel", color=INK, fontsize=10)
        fm = fused[k_major]
        if fm.any():
            axes[2].contour(fm.astype(float), levels=[0.5], colors=C_FUSED, linewidths=2)
        title = f"fused (≥{k_major} of {len(back)} angles)"
        if template is not None:
            v, placement = shape_iou(fm, template)
            if placement is not None:
                axes[2].contour(placed_template(template, placement).astype(float),
                                levels=[0.5], colors=C_TEMPLATE, linewidths=1.6,
                                linestyles="dashed")
            title += f"\nshape IoU {100 * v:.0f}% (green dashed = true shape)"
        axes[2].set_title(title, color=INK, fontsize=10)
        ys, xs = np.nonzero(votes > 0)
        if len(xs):
            pad = 25
            for ax in axes:
                ax.set_xlim(max(xs.min() - pad, 0), min(xs.max() + pad, N - 1))
                ax.set_ylim(min(ys.max() + pad, N - 1), max(ys.min() - pad, 0))
        fig.suptitle(shape, color=INK, fontsize=12, fontweight="bold")
        fig.tight_layout(rect=(0, 0, 1, 0.93))
        fig.savefig(os.path.join(args.out, shape.replace(" ", "_") + ".png"),
                    dpi=110, facecolor=SURFACE)
        plt.close(fig)
        print(f"  {shape}: {len(back)} angles, agreement IoU {agree:.2f}, sense {sense:+d}",
              flush=True)

    keys = sorted({k for r in rows for k in r})
    order = ["shape", "angles", "agreement_iou", "rotation_sense", "single_mean",
             "single_best"] + [k for k in keys if k.startswith("fused_k")]
    with open(os.path.join(args.out, "fusion.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=order)
        wr.writeheader()
        wr.writerows(rows)

    scored = [r for r in rows if "single_mean" in r]
    print(f"\nshape IoU against the true shape (Liam's outline), {len(scored)} shapes:")
    print(f"{'shape':<15}{'single (mean)':>14}{'single (best)':>14}" +
          "".join(f"{'fused k=' + str(k):>11}" for k in range(1, 7)))
    for r in scored:
        print(f"{r['shape']:<15}{100 * r['single_mean']:>13.1f}%{100 * r['single_best']:>13.1f}%" +
              "".join(f"{100 * r[f'fused_k{k}']:>10.1f}%" if f"fused_k{k}" in r else f"{'':>11}"
                      for k in range(1, 7)))
    mean = lambda key: 100 * np.mean([r[key] for r in scored if key in r])
    print(f"{'MEAN':<15}{mean('single_mean'):>13.1f}%{mean('single_best'):>13.1f}%" +
          "".join(f"{mean(f'fused_k{k}'):>10.1f}%" for k in range(1, 7)))
    print(f"\nfigures + fusion.csv -> {args.out}/")


if __name__ == "__main__":
    main()
