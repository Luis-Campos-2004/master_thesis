#!/usr/bin/env python3
"""
compare_methods_table.py — One table with every segmentation method on both
photo sets: Dice, IoU and contour accuracy (F@1mm), mean ± sd per set.

    old photos   data/raw/shape_pictures, 5 photos, Liam's outlines
                 (computed here)
    new photos   data/raw/shape_pictures_v3, 48 photos, Luís's outlines
                 (read from eval_photos_v3.py's CSV; run that first)

Writes a PNG table, a CSV and a Markdown version to results/segmentation_v2/.

Usage from the repo root:
    python verification/compare_methods_table.py
"""

import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import wilcoxon

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
import tactile.detect_shape as ds          # noqa: E402
import eval_segmentation as ev             # noqa: E402
import segment_photos_v2 as sp2            # noqa: E402

NEW_CSV = "results/segmentation_v2/shape_pictures_v3/eval_photos_v3.csv"
OUT = "results/segmentation_v2/method_comparison"
METHODS = [  # key, label, colour (same identity colours as the other figures)
    ("footprint", "Liam: default (footprint)", "#1baf7a"),
    ("tight", "Liam: tight", "#2a78d6"),
    ("contact", "Contact mode (35% cut)", "#eb6834"),
    ("contact15", "Contact mode, 15% cut", "#eda100"),
    ("fused", "Contact 15% + 6 angles combined", "#e87ba4"),
]
OLD_KW = {"footprint": {}, "tight": {"tight": True}, "contact": dict(ds.CONTACT_PARAMS),
          "contact15": dict(sp2.PARAMS)}
METRICS = [("dice", "Dice"), ("iou", "IoU"), ("f_1mm", "Contour ≤1 mm")]
INK, INK2, MUTED, RULE, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"


def old_rows():
    rows = []
    px_mm = ev.px_per_mm()
    for shape, name, ref, dfm, gt_path in ev.find_pairs("data/raw/shape_pictures"):
        gt = ev.gt_mask(gt_path)
        for m, kw in OLD_KW.items():
            res = ds.detect(ref, dfm, **kw)
            rows.append({"set": "old", "shape": shape, "photo": name, "method": m,
                         **ev.score_mask(res["mask"], gt, res["roi"], px_mm)})
    return rows


def new_rows():
    with open(NEW_CSV, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["set"] = "new"
        r["photo"] = f"{r['shape']}/{r['angle_deg']}"
        for k, _ in METRICS:
            r[k] = float(r[k])
    return rows


def summary(rows):
    tab = {}
    for s in ("old", "new"):
        for m, _, _ in METHODS:
            for k, _ in METRICS:
                v = np.array([r[k] for r in rows if r["set"] == s and r["method"] == m], float)
                tab[(s, m, k)] = (100 * v.mean(), 100 * v.std(), len(v)) if len(v) else None
    return tab


def p_vs_tight(rows, m, k):
    x = {r["photo"]: r[k] for r in rows if r["set"] == "new" and r["method"] == m}
    y = {r["photo"]: r[k] for r in rows if r["set"] == "new" and r["method"] == "tight"}
    keys = sorted(set(x) & set(y))
    if m == "tight" or not keys:
        return None
    return wilcoxon([x[q] for q in keys], [y[q] for q in keys]).pvalue


def draw(tab, n_old, n_new, path):
    cols = [(s, k) for s in ("old", "new") for k, _ in METRICS]
    best = {c: max((tab[(c[0], m, c[1])][0], m) for m, _, _ in METHODS
                   if tab[(c[0], m, c[1])])[1] for c in cols}
    fig = plt.figure(figsize=(13, 5.2), facecolor=SURFACE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 5.2)
    ax.axis("off")
    x_name, x0, dx = 0.35, 5.0, 1.33
    y = 4.85
    for x, title, sub in ((x0 + dx, "Old photos", f"{n_old} photos · Liam's camera and outlines"),
                          (x0 + 4 * dx, "New photos", f"{n_new} photos · 6 angles · your outlines")):
        ax.text(x, y, title, ha="center", fontsize=11.5, fontweight="bold", color=INK)
        ax.text(x, y - 0.27, sub, ha="center", fontsize=9, color=INK2)
    y -= 0.7
    ax.text(x_name, y, "Method", fontsize=10, fontweight="bold", color=INK2)
    for i, (s, k) in enumerate(cols):
        ax.text(x0 + i * dx, y, dict(METRICS)[k], ha="center", fontsize=10,
                fontweight="bold", color=INK2)
    y -= 0.18
    ax.plot([0.25, 12.8], [y, y], color=INK2, lw=1)
    for m, label, colour in METHODS:
        y -= 0.55
        ax.add_patch(plt.Rectangle((x_name, y - 0.03), 0.16, 0.16, color=colour))
        ax.text(x_name + 0.28, y, label, fontsize=10.5, color=INK, va="bottom")
        for i, c in enumerate(cols):
            v = tab[(c[0], m, c[1])]
            if v is None:
                ax.text(x0 + i * dx, y, "—", ha="center", fontsize=10.5, color=MUTED, va="bottom")
                continue
            ax.text(x0 + i * dx, y + 0.02, f"{v[0]:.1f}", ha="right", fontsize=11,
                    color=INK, va="bottom", fontweight="bold" if best[c] == m else "normal")
            ax.text(x0 + i * dx + 0.04, y + 0.03, f"±{v[1]:.0f}", ha="left", fontsize=8,
                    color=MUTED, va="bottom")
        ax.plot([0.25, 12.8], [y - 0.14, y - 0.14], color=RULE, lw=0.8)
    ax.plot([x0 + 2.5 * dx, x0 + 2.5 * dx], [y - 0.14, 4.95], color=RULE, lw=1)
    notes = ("Values in %, mean ± sd over photos; bold = best in the column. "
             "Old photos: the contact mode was tuned on these same 5 photos, so its numbers are optimistic.\n"
             "New photos: none of them were used for tuning (only the 15% cut was chosen on them, without "
             "the outlines). Combining angles needs the 6 rotated photos, so it has no value for the old set.")
    ax.text(0.3, 0.12, notes, fontsize=8.3, color=INK2, va="bottom")
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main():
    rows = old_rows() + new_rows()
    tab = summary(rows)
    n_old = len({r["photo"] for r in rows if r["set"] == "old"})
    n_new = len({r["photo"] for r in rows if r["set"] == "new"})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    draw(tab, n_old, n_new, OUT + ".png")

    with open(OUT + ".csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["method"] + [f"{s}_{k}_{stat}" for s in ("old", "new")
                                  for k, _ in METRICS for stat in ("mean", "sd")])
        for m, label, _ in METHODS:
            line = [label]
            for s in ("old", "new"):
                for k, _ in METRICS:
                    v = tab[(s, m, k)]
                    line += [f"{v[0]:.1f}", f"{v[1]:.1f}"] if v else ["", ""]
            wr.writerow(line)

    md = ["| Method | Old: Dice | Old: IoU | Old: Contour ≤1 mm | New: Dice | New: IoU | "
          "New: Contour ≤1 mm |", "|---|---|---|---|---|---|---|"]
    for m, label, _ in METHODS:
        cells = []
        for s in ("old", "new"):
            for k, _ in METRICS:
                v = tab[(s, m, k)]
                cells.append(f"{v[0]:.1f} ± {v[1]:.1f}" if v else "—")
        md.append(f"| {label} | " + " | ".join(cells) + " |")
    with open(OUT + ".md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    print("\n".join(md))
    print("\nnew photos, paired Wilcoxon against Liam's tight (48 photos):")
    for m, label, _ in METHODS[2:] + METHODS[:1]:
        ps = ", ".join(f"{name} p = {p_vs_tight(rows, m, k):.1g}" for k, name in METRICS)
        print(f"  {label:<34} {ps}")
    print(f"\n-> {OUT}.png / .csv / .md")


if __name__ == "__main__":
    main()
