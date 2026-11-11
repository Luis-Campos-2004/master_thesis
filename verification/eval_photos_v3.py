#!/usr/bin/env python3
"""
eval_photos_v3.py — Scores the segmentation of the rotated photo set against
the hand-drawn outlines (v3), photo by photo and with the six angles combined.

For every photo, four segmentations of its adjusted version are compared with
its outline:
    footprint   Liam's default mode
    tight       Liam's contact mode
    contact     contact mode v2 (35% cut)
    contact15   contact mode v2 with the 15% cut used for the rotated set
plus the combined shape ("fused"): the contact15 masks of all angles of a
tip, rotated back to 0 degrees, kept where at least 3 angles agree, then
rotated into each photo's frame (same alignment as fuse_angles.py).

The outline is the set of pixels that differ from the clean photo, with
small gaps closed by joining nearby line ends. It is filled (odd nesting =
inside, so the ring keeps its hole), shifted like its photo onto the
reference, cropped with the same window and resized to the 768 px frame,
where 1 mm = 11.8 px.

Run build_dataset_v3.py and adjust_photos.py first:
    python src/tactile/adjust_photos.py data/raw/shape_pictures_v3 data/processed/shape_pictures_v3
    python verification/eval_photos_v3.py
"""

import argparse
import csv
import os
import re
import sys

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.lines import Line2D
import numpy as np
from scipy import ndimage as ndi
from scipy.stats import wilcoxon
from skimage.morphology import skeletonize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
import tactile.adjust_photos as ap          # noqa: E402
import tactile.detect_shape as ds          # noqa: E402
import eval_segmentation as ev             # noqa: E402
import fuse_angles as fa                   # noqa: E402
import segment_photos_v2 as sp2            # noqa: E402

RAW = "data/raw/shape_pictures_v3"
ADJ = "data/processed/shape_pictures_v3"
ANN = "data/annotations/shape_pictures_v3"
OUT = "results/segmentation_v2/shape_pictures_v3"
MAX_GAP = 90           # px (full resolution, ~4 mm): line ends closer than this are joined
FUSE_K = 3             # combined shape: pixels seen by at least this many angles
METHODS = {
    "footprint": {},
    "tight": {"tight": True},
    "contact": dict(ds.CONTACT_PARAMS),
    "contact15": dict(sp2.PARAMS),
}
EXPECTED = {"Square Circle": 2, "Three Circles": 3}
SURFACE, INK = "#fcfcfb", "#0b0b0b"
C_SINGLE, C_FUSED = "#2a78d6", "#eb6834"


# --- outline -> filled ground truth -------------------------------------------------
def outline(gt_bgr, clean_bgr):
    d = np.abs(gt_bgr.astype(int) - clean_bgr.astype(int)).sum(2)
    b, g, r = (gt_bgr[..., i].astype(int) for i in range(3))
    return (d > 45) & (r - np.maximum(g, b) > 10)


def close_gaps(line):
    """Join line ends that are closer than MAX_GAP, nearest pairs first."""
    line = cv2.morphologyEx(line.astype(np.uint8), cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    skel = skeletonize(line)
    nb = ndi.convolve(skel.astype(np.uint8), np.ones((3, 3), np.uint8), mode="constant")
    ys, xs = np.nonzero(skel & (nb == 2))
    pts = np.stack([xs, ys], 1)
    out = line.astype(np.uint8)
    used = set()
    if len(pts) > 1:
        dist = np.hypot(*(pts[:, None, :] - pts[None, :, :]).transpose(2, 0, 1))
        np.fill_diagonal(dist, np.inf)
        for i, j in sorted(zip(*np.triu_indices(len(pts), 1)), key=lambda p: dist[p]):
            if dist[i, j] > MAX_GAP:
                break
            if i in used or j in used:
                continue
            cv2.line(out, tuple(int(v) for v in pts[i]), tuple(int(v) for v in pts[j]), 1, 3)
            used.update((i, j))
    return out > 0


def fill(line):
    """Inside = enclosed by an odd number of outlines; the line goes to its nearer side."""
    lab, n = ndi.label(line, structure=np.ones((3, 3)))
    sizes = ndi.sum(line, lab, range(1, n + 1)) if n else []
    inside = [ndi.binary_fill_holes(lab == i + 1) for i, s in enumerate(sizes) if s > 150]
    regions, nr = ndi.label(~line)
    obj = np.zeros(line.shape, bool)
    for i in range(1, nr + 1):
        reg = regions == i
        if reg.sum() < 300:
            continue
        ys, xs = np.nonzero(reg)
        if (ys.min() == 0 or xs.min() == 0 or ys.max() == reg.shape[0] - 1
                or xs.max() == reg.shape[1] - 1):
            continue
        py, px = np.unravel_index(np.argmax(ndi.distance_transform_edt(reg)), reg.shape)
        if sum(int(f[py, px]) for f in inside) % 2:
            obj |= reg
    near = ndi.distance_transform_edt(line, return_distances=False, return_indices=True)
    return obj[near[0], near[1]]


def to_frame(mask, shift, crop, size=ds.PROC_SIZE):
    """Same shift, crop window and resize as the photo goes through."""
    h, w = mask.shape
    m = cv2.warpAffine(mask.astype(np.float32), np.float32([[1, 0, -shift[0]], [0, 1, -shift[1]]]),
                       (w, h), flags=cv2.INTER_NEAREST)
    r = int(min(h, w) * crop)
    m = m[h // 2 - r:h // 2 + r, w // 2 - r:w // 2 + r]
    return cv2.resize(m, (size, size), interpolation=cv2.INTER_AREA) > 0.5


def up(mask, size=ds.PROC_SIZE):
    return cv2.resize(mask.astype(np.float32), (size, size), interpolation=cv2.INTER_LINEAR) > 0.5


# --- main ----------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=OUT)
    args = p.parse_args()
    os.makedirs(os.path.join(args.out, "figures"), exist_ok=True)

    ref_adj = os.path.join(ADJ, "reference.png")
    crop, _ = sp2.crop_ratio_for(ref_adj)
    ref_g = cv2.imread(os.path.join(RAW, "reference.jpg"), cv2.IMREAD_GRAYSCALE).astype(np.float32)
    window = cv2.createHanningWindow(ref_g.shape[::-1], cv2.CV_32F)

    rows = []
    for shape in sorted(os.listdir(RAW)):
        if not os.path.isdir(os.path.join(RAW, shape)):
            continue
        shots = []
        for f in sorted(os.listdir(os.path.join(RAW, shape))):
            stem = os.path.splitext(f)[0]
            gt_path = os.path.join(ANN, shape, stem + "_gt.jpg")
            if not os.path.exists(gt_path):
                print(f"  {shape}/{f}: no outline, skipped")
                continue
            clean = cv2.imread(os.path.join(RAW, shape, f))
            _, shift = ap.align(cv2.cvtColor(clean, cv2.COLOR_BGR2GRAY).astype(np.float32),
                                ref_g, window)
            gt_full = fill(close_gaps(outline(cv2.imread(gt_path), clean)))
            gt = to_frame(gt_full, shift, crop)
            n_gt = ndi.label(gt, structure=np.ones((3, 3)))[1]
            if not gt.any():
                print(f"  {shape}/{stem}: outline could not be filled, skipped")
                continue
            if n_gt != EXPECTED.get(shape, 1):
                print(f"  {shape}/{stem}: outline has {n_gt} parts "
                      f"(expected {EXPECTED.get(shape, 1)})")
            res = {m: ds.detect(ref_adj, os.path.join(ADJ, shape, stem + ".png"),
                                crop_ratio=crop, **kw) for m, kw in METHODS.items()}
            shots.append((stem, int(re.search(r"(\d+)", stem).group(1)), gt, res))

        # combined shape from the contact15 masks of all angles
        masks = [fa.small(r["contact15"]["mask"]) for _, _, _, r in shots]
        angles = [a for _, a, _, _ in shots]
        _, centre, sense, back = fa.align_all(masks, angles)
        fused0 = np.sum(back, axis=0) >= FUSE_K

        for stem, angle, gt, res in shots:
            roi = res["contact15"]["roi"]
            preds = {m: r["mask"] for m, r in res.items()}
            preds["fused"] = up(fa.rotate(fused0, -sense * angle, centre))
            for m, pred in preds.items():
                s = ev.score_mask(pred, gt, roi, sp2.PX_PER_MM)
                rows.append({"shape": shape, "angle_deg": angle, "method": m,
                             **{k: (round(v, 4) if isinstance(v, float) else v)
                                for k, v in s.items()}})
            shots_view = (res["contact15"]["def"], gt, preds["contact15"], preds["fused"])
            res["_view"] = shots_view

        # figure: one panel per angle, outline (white) + single photo (blue) + combined (orange)
        fig, axes = plt.subplots(1, len(shots), figsize=(3.2 * len(shots), 3.9),
                                 facecolor=SURFACE, squeeze=False)
        stroke = [patheffects.withStroke(linewidth=3.8, foreground=INK)]
        for ax, (stem, angle, gt, res) in zip(axes[0], shots):
            img, gt_m, single, fused = res["_view"]
            ax.imshow(img, cmap="gray", vmin=0, vmax=255)
            ax.contour(gt_m.astype(float), levels=[0.5], colors="white",
                       linewidths=1.8).set_path_effects(stroke)
            for m, col in ((single, C_SINGLE), (fused, C_FUSED)):
                if m.any():
                    ax.contour(m.astype(float), levels=[0.5], colors=col, linewidths=1.6)
            d1 = [r["dice"] for r in rows if r["shape"] == shape and r["angle_deg"] == angle
                  and r["method"] == "contact15"][0]
            d2 = [r["dice"] for r in rows if r["shape"] == shape and r["angle_deg"] == angle
                  and r["method"] == "fused"][0]
            ax.set_title(f"{angle}°   Dice: single {100 * d1:.0f}%, combined {100 * d2:.0f}%",
                         color=INK, fontsize=8.5)
            n = img.shape[0]
            ax.set_xlim(0.12 * n, 0.88 * n)
            ax.set_ylim(0.88 * n, 0.12 * n)
            ax.set_axis_off()
        fig.legend(handles=[Line2D([], [], color="white", lw=1.8, path_effects=stroke,
                                   label="hand-drawn outline"),
                            Line2D([], [], color=C_SINGLE, lw=1.6, label="single photo"),
                            Line2D([], [], color=C_FUSED, lw=1.6,
                                   label=f"combined (≥{FUSE_K} angles)")],
                   loc="lower center", ncol=3, frameon=False, fontsize=9)
        fig.suptitle(shape, color=INK, fontsize=12, fontweight="bold")
        fig.tight_layout(rect=(0, 0.07, 1, 0.93))
        fig.savefig(os.path.join(args.out, "figures", shape.replace(" ", "_") + ".png"),
                    dpi=100, facecolor=SURFACE)
        plt.close(fig)
        print(f"  {shape}: {len(shots)} photos scored", flush=True)

    with open(os.path.join(args.out, "eval_photos_v3.csv"), "w", newline="",
              encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    # summary
    methods = list(METHODS) + ["fused"]
    keys = [("dice", "Dice %", 100), ("iou", "IoU %", 100), ("f_1mm", "F@1mm %", 100),
            ("f_2mm", "F@2mm %", 100), ("assd_mm", "ASSD mm", 1)]
    n_photos = len({(r["shape"], r["angle_deg"]) for r in rows})
    print(f"\n{n_photos} photos with outlines\n{'method':<11}" +
          "".join(f"{label:>15}" for _, label, _ in keys))
    for m in methods:
        line = f"{m:<11}"
        for k, _, sc in keys:
            v = np.array([r[k] for r in rows if r["method"] == m], float) * sc
            line += f"{np.nanmean(v):8.1f} ± {np.nanstd(v):4.1f}"
        print(line)

    def paired(a, b, key):
        x = {(r["shape"], r["angle_deg"]): r[key] for r in rows if r["method"] == a}
        y = {(r["shape"], r["angle_deg"]): r[key] for r in rows if r["method"] == b}
        ks = sorted(set(x) & set(y))
        dx = np.array([x[k] - y[k] for k in ks])
        pv = wilcoxon([x[k] for k in ks], [y[k] for k in ks]).pvalue if np.any(dx) else 1.0
        return 100 * dx.mean(), int((dx > 0).sum()), len(ks), pv

    print("\npaired comparisons (Wilcoxon, per photo):")
    for a, b in (("contact15", "tight"), ("fused", "contact15"), ("fused", "tight")):
        for key, label in (("dice", "Dice"), ("iou", "IoU"), ("f_1mm", "F@1mm")):
            dm, better, n, pv = paired(a, b, key)
            print(f"  {a:>9} vs {b:<9} {label:<6} {dm:+5.1f} points, better on "
                  f"{better}/{n} photos, p = {pv:.2g}")

    print(f"\nper shape, Dice % (mean over angles):\n{'shape':<15}" +
          "".join(f"{m:>11}" for m in methods))
    for shape in dict.fromkeys(r["shape"] for r in rows):
        print(f"{shape:<15}" + "".join(
            f"{100 * np.mean([r['dice'] for r in rows if r['shape'] == shape and r['method'] == m]):>10.1f}%"
            for m in methods))
    print(f"\nper-photo metrics -> {args.out}/eval_photos_v3.csv\nfigures -> {args.out}/figures/")


if __name__ == "__main__":
    main()
