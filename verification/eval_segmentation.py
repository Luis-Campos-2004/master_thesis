#!/usr/bin/env python3
"""
eval_segmentation.py, scores the shape segmentation against hand-drawn
ground truth.

Ground truth is a closed red (#FF0000) outline drawn on a copy of the
deformed photo. Two folder layouts are understood:

    <root>/<Shape>/img_01.jpg, img_02.jpg, ..., <name>_gt.(png|jpg)
        img_01 is the reference; each *_gt image is matched to the photo it
        was drawn on (identical pixels outside the red line).
    <root>/<Shape>/pair_XX/ref.jpg, def.jpg, def_gt.(png|jpg)

Every pair is segmented three ways: `footprint` (detect() default, what the
force chain uses), `tight` (the original contact mode, the baseline) and
`contact` (detect(**CONTACT_PARAMS), the improved mode).

Metrics, in the detection frame (mm through the 20 mm calibration circle):
    IoU, Dice, precision, recall   region overlap
    F@0.5/1/2mm                    contour accuracy: how much of each boundary
                                   lies within the tolerance of the other one
    ASSD, HD95 (mm)                mean / 95th-percentile boundary distance

--search runs a leave-one-shape-out grid search over the contact-mode
parameters: the setting is picked on all shapes but one and scored on the
one left out, for every shape in turn. That held-out score is the honest
number to report; the setting picked on all shapes is printed as the
CONTACT_PARAMS to use.

Usage from the repo root:
    python verification/eval_segmentation.py
    python verification/eval_segmentation.py --search
    python verification/eval_segmentation.py data/raw/shape_pictures_v2
"""

import argparse
import csv
import itertools
import os
import sys
import time

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.lines import Line2D
import numpy as np
from scipy import ndimage as ndi
from scipy.stats import wilcoxon

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import tactile.detect_shape as ds          # noqa: E402
import tactile.uniform_reconstruct as ur   # noqa: E402

IMG_EXT = (".jpg", ".jpeg", ".png")
RED_MIN = 70           # R - max(G, B) above this is the drawn outline
MATCH_MAX_DIFF = 3.0   # mean |gray diff| off the line for a GT <-> photo match
TOLS_MM = (0.5, 1.0, 2.0)

METHODS = {
    "footprint": {},
    "tight": {"tight": True},
    "contact": ds.CONTACT_PARAMS,
}

# contact-mode grid for --search; must contain the detect() defaults so the
# baseline (tight, no refine, no compensation) is one of the settings
SEARCH_GRID = {
    "bw_frac": (0.55, 0.7),
    "smooth_frac": (0.003, 0.004, 0.006, 0.008),
    "tight_lo_frac": (0.30, 0.35, 0.40),
    "refine": (False, True),
    "disp_alpha": (0.0, 0.25, 0.5, 0.75),
}

# figure colours: categorical slots 1-3 (colour-blind safe as a set), one per
# method in every figure, plus ink
COLOURS = {"footprint": "#1baf7a", "tight": "#2a78d6", "contact": "#eb6834"}
LABELS = {"footprint": "old default (footprint)", "tight": "old tight",
          "contact": "new (contact)"}
SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
GRID, AXIS = "#e1e0d9", "#c3c2b7"


# --- Finding annotated pairs ---------------------------------------------------
def _is_gt(fname):
    return os.path.splitext(fname)[0].lower().endswith("_gt")


def _red(bgr):
    b, g, r = (bgr[..., i].astype(np.int16) for i in range(3))
    return (r - np.maximum(g, b)) > RED_MIN


def _prefer_png(gt_files):
    """One GT per name; a redrawn .png wins over the old .jpg."""
    by_stem = {}
    for f in sorted(gt_files):
        stem = os.path.splitext(f)[0].lower()
        if stem not in by_stem or f.lower().endswith(".png"):
            by_stem[stem] = f
    return sorted(by_stem.values())


def _drawn_on(gt_path, photos):
    """The photo the outline was drawn on (and its mismatch), or (None, d)."""
    gt = cv2.imread(gt_path)
    off_line = cv2.dilate(_red(gt).astype(np.uint8),
                          np.ones((31, 31), np.uint8)) == 0
    g = cv2.cvtColor(gt, cv2.COLOR_BGR2GRAY).astype(np.float32)
    best, best_d = None, np.inf
    for p in photos:
        im = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
        h, w = min(im.shape[0], g.shape[0]), min(im.shape[1], g.shape[1])
        d = float(np.abs(im[:h, :w] - g[:h, :w])[off_line[:h, :w]].mean())
        if d < best_d:
            best, best_d = p, d
    return (best if best_d < MATCH_MAX_DIFF else None), best_d


def find_pairs(root):
    """[(shape, name, ref, deformed, gt)] for every annotated pair under root."""
    pairs = []
    for d, _, files in sorted(os.walk(root)):
        files = sorted(f for f in files if f.lower().endswith(IMG_EXT))
        rel = os.path.relpath(d, root)
        shape = os.path.basename(os.path.abspath(root)) if rel == "." \
            else rel.split(os.sep)[0]
        stems = {os.path.splitext(f)[0].lower(): f for f in files}
        gts = _prefer_png([f for f in files if _is_gt(f)])

        if "ref" in stems and "def" in stems:           # pair_XX layout
            if gts:
                pairs.append((shape, rel, os.path.join(d, stems["ref"]),
                              os.path.join(d, stems["def"]),
                              os.path.join(d, gts[0])))
            continue
        if "img_01" not in stems or not gts:
            continue
        photos = [os.path.join(d, f) for f in files
                  if not _is_gt(f) and os.path.splitext(f)[0].lower() != "img_01"]
        for gt in gts:
            match, diff = _drawn_on(os.path.join(d, gt), photos)
            if match is None:
                print(f"  skipped {rel}/{gt}: not drawn on any photo in the "
                      f"folder (closest mean diff {diff:.1f})")
                continue
            name = f"{rel}/{os.path.splitext(os.path.basename(match))[0]}"
            pairs.append((shape, name, os.path.join(d, stems["img_01"]),
                          match, os.path.join(d, gt)))
    return pairs


# --- Ground truth ------------------------------------------------------------------
def gt_mask(path, size=ds.PROC_SIZE, crop_ratio=ds.CROP_RATIO):
    """Region enclosed by the red outline, in the detection frame.

    A region counts as object when an odd number of outlines encloses it,
    so a ring keeps its hole. Line pixels go to whichever side is nearer,
    which puts the boundary on the centre of the drawn line.
    """
    bgr = cv2.imread(path)
    if bgr is None:
        raise FileNotFoundError(path)
    h, w = bgr.shape[:2]
    r = int(min(h, w) * crop_ratio)                     # same window as ds.crop_roi
    crop = bgr[h // 2 - r:h // 2 + r, w // 2 - r:w // 2 + r]
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    red = cv2.morphologyEx(_red(crop).astype(np.uint8), cv2.MORPH_CLOSE, k) > 0

    lines, n_lines = ndi.label(red, structure=np.ones((3, 3)))
    inside = [ndi.binary_fill_holes(lines == i) for i in range(1, n_lines + 1)]
    regions, n_regions = ndi.label(~red)
    obj = np.zeros(red.shape, bool)
    for i in range(1, n_regions + 1):
        reg = regions == i
        ys, xs = np.nonzero(reg)
        if (ys.min() == 0 or xs.min() == 0 or ys.max() == reg.shape[0] - 1
                or xs.max() == reg.shape[1] - 1):
            continue                                    # outside every outline
        py, px = np.unravel_index(np.argmax(ndi.distance_transform_edt(reg)),
                                  reg.shape)
        if sum(int(f[py, px]) for f in inside) % 2:
            obj |= reg

    near = ndi.distance_transform_edt(red, return_distances=False,
                                      return_indices=True)
    obj = obj[near[0], near[1]]
    return cv2.resize(obj.astype(np.float32), (size, size),
                      interpolation=cv2.INTER_AREA) > 0.5


def px_per_mm(size=ds.PROC_SIZE):
    """Detection-frame scale from the calibration circle's mask."""
    area = ur.calib_area_from_mask(ur.CALIB_MASK_PATH, size)
    return float(np.sqrt(area / ur.CALIB_AREA_MM2))


# --- Metrics -----------------------------------------------------------------------
def _edge(m):
    return m & ~ndi.binary_erosion(m)


def score_mask(pred, gt, roi, px_mm):
    p, g = (pred > 0) & roi, gt & roi
    tp, fp, fn = int((p & g).sum()), int((p & ~g).sum()), int((~p & g).sum())
    eight = np.ones((3, 3))
    out = {
        "iou": tp / max(tp + fp + fn, 1),
        "dice": 2 * tp / max(2 * tp + fp + fn, 1),
        "precision": tp / max(tp + fp, 1),
        "recall": tp / max(tp + fn, 1),
        "area_err_pct": 100.0 * (int(p.sum()) - int(g.sum())) / max(int(g.sum()), 1),
        "n_pred": ndi.label(p, structure=eight)[1],
        "n_gt": ndi.label(g, structure=eight)[1],
    }
    ep, eg = _edge(p), _edge(g)
    if not (ep.any() and eg.any()):
        out.update({f"f_{t:g}mm": 0.0 for t in TOLS_MM},
                   assd_mm=float("nan"), hd95_mm=float("nan"))
        return out
    d_pg = ndi.distance_transform_edt(~eg)[ep] / px_mm   # predicted edge -> GT edge
    d_gp = ndi.distance_transform_edt(~ep)[eg] / px_mm   # GT edge -> predicted edge
    for t in TOLS_MM:
        prec, rec = float((d_pg <= t).mean()), float((d_gp <= t).mean())
        out[f"f_{t:g}mm"] = 2 * prec * rec / max(prec + rec, 1e-9)
    both = np.concatenate([d_pg, d_gp])
    out["assd_mm"] = float(both.mean())
    out["hd95_mm"] = float(np.percentile(both, 95))
    return out


# --- Evaluation --------------------------------------------------------------------
def evaluate(pairs, gts, px_mm):
    rows, views = [], {}
    for shape, name, ref, dfm, _ in pairs:
        t0 = time.time()
        preds, scores = {}, {}
        for method, kw in METHODS.items():
            res = ds.detect(ref, dfm, **kw)
            preds[method] = res["mask"]
            scores[method] = score_mask(res["mask"], gts[name], res["roi"], px_mm)
            rows.append({"shape": shape, "pair": name, "method": method,
                         **scores[method]})
        views[name] = (res["def"], res["roi"], preds, scores)
        print(f"  {name:<32} tight F@1mm {100 * scores['tight']['f_1mm']:5.1f}%"
              f" -> contact {100 * scores['contact']['f_1mm']:5.1f}%"
              f"   ({time.time() - t0:.1f} s)", flush=True)
    return rows, views


def print_summary(rows, n_pairs):
    keys = [("iou", "IoU %", 100), ("dice", "Dice %", 100),
            ("f_0.5mm", "F@0.5mm %", 100), ("f_1mm", "F@1mm %", 100),
            ("f_2mm", "F@2mm %", 100), ("assd_mm", "ASSD mm", 1),
            ("hd95_mm", "HD95 mm", 1)]
    print(f"\n{'method':<11}" + "".join(f"{label:>15}" for _, label, _ in keys))
    print("-" * (11 + 15 * len(keys)))
    for method in METHODS:
        line = f"{method:<11}"
        for k, _, scale in keys:
            v = np.array([r[k] for r in rows if r["method"] == method], float) * scale
            line += f"{np.nanmean(v):8.1f} ± {np.nanstd(v):4.1f}"
        print(line)

    tight = {r["pair"]: r for r in rows if r["method"] == "tight"}
    contact = {r["pair"]: r for r in rows if r["method"] == "contact"}
    names = sorted(tight)
    print(f"\ncontact vs tight over {n_pairs} pairs (paired Wilcoxon):")
    for k, label in (("f_1mm", "F@1mm"), ("iou", "IoU")):
        diff = np.array([contact[n][k] - tight[n][k] for n in names])
        better = int((diff > 0).sum())
        if n_pairs >= 5 and np.any(diff != 0):
            p = wilcoxon([contact[n][k] for n in names],
                         [tight[n][k] for n in names]).pvalue
            ptxt = f"p = {p:.4f}"
        else:
            ptxt = "p = n/a"
        print(f"  {label:<6} mean change {100 * diff.mean():+5.1f} points, "
              f"better on {better}/{n_pairs} pairs, {ptxt}")
    if n_pairs < 6:
        print("  (with fewer than 6 pairs p can never drop below 0.05; the "
              "new photo set provides the significance test)")


def write_csv(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        for r in rows:
            wr.writerow({k: round(v, 4) if isinstance(v, float) else v
                         for k, v in r.items()})


# --- Figures -----------------------------------------------------------------------
def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


_GT_STROKE = [patheffects.withStroke(linewidth=4.5, foreground=INK)]


def save_pair_figure(path, name, view, gt):
    """One panel per method: its contour and the GT outline on the photo."""
    img, roi, preds, scores = view
    ys, xs = np.nonzero(gt | np.any([preds[m] > 0 for m in METHODS], axis=0))
    half = max(ys.max() - ys.min(), xs.max() - xs.min()) / 2 + 40
    cy, cx = (ys.max() + ys.min()) / 2, (xs.max() + xs.min()) / 2
    n = img.shape[0]
    y0, y1 = max(cy - half, 0), min(cy + half, n - 1)
    x0, x1 = max(cx - half, 0), min(cx + half, n - 1)

    # muted photo, so the contour lines stand out against the stripes
    lo, hi = np.percentile(img[roi], [1, 99])
    photo = 0.2 + 0.6 * np.clip((img - lo) / (hi - lo + 1e-9), 0, 1)

    fig, axes = plt.subplots(1, len(METHODS), figsize=(4.6 * len(METHODS), 5.4),
                             facecolor=SURFACE)
    for ax, method in zip(axes, METHODS):
        ax.imshow(photo, cmap="gray", vmin=0, vmax=1)
        ax.contour(gt.astype(float), levels=[0.5], colors="white",
                   linewidths=2).set_path_effects(_GT_STROKE)
        ax.contour((preds[method] > 0).astype(float), levels=[0.5],
                   colors=COLOURS[method], linewidths=2.2)
        s = scores[method]
        ax.set_title(f"{LABELS[method]}\nDice {100 * s['dice']:.1f}%   "
                     f"IoU {100 * s['iou']:.1f}%   "
                     f"contour F@1mm {100 * s['f_1mm']:.1f}%",
                     color=INK, fontsize=10)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y1, y0)
        ax.set_axis_off()
    handles = [Line2D([], [], color="white", linewidth=2,
                      path_effects=_GT_STROKE, label="ground truth (hand-drawn)")]
    handles += [Line2D([], [], color=COLOURS[m], linewidth=2.2, label=LABELS[m])
                for m in METHODS]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles),
               frameon=False, fontsize=9, labelcolor=INK2)
    fig.suptitle(name, color=INK, fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0.06, 1, 0.93))
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def save_summary_figure(path, rows):
    shapes = list(dict.fromkeys(r["shape"] for r in rows))
    labels = shapes + ["mean"]
    x = np.arange(len(labels))
    w = 0.27
    panels = (("dice", "Segmentation (Dice)"), ("iou", "Segmentation (IoU)"),
              ("f_1mm", "Contour accuracy (F@1mm)"))
    fig, axes = plt.subplots(1, len(panels), figsize=(18, 4.8), sharey=True,
                             facecolor=SURFACE)
    for ax, (key, title) in zip(axes, panels):
        _style(ax)
        for j, method in enumerate(METHODS):
            vals = [100 * np.mean([r[key] for r in rows
                                   if r["shape"] == s and r["method"] == method])
                    for s in shapes]
            vals.append(100 * np.mean([r[key] for r in rows
                                       if r["method"] == method]))
            bars = ax.bar(x + (j - 1) * w, vals, w, color=COLOURS[method],
                          edgecolor=SURFACE, linewidth=2, label=LABELS[method],
                          zorder=2)
            ax.bar_label(bars, labels=[""] * (len(vals) - 1) + [f"{vals[-1]:.1f}"],
                         padding=3, color=INK, fontsize=8)
        ax.set_xticks(x, labels)
        ax.set_title(title, color=INK, fontsize=11)
        ax.set_ylim(0, 100)
    axes[0].set_ylabel("%", color=INK2)
    axes[0].legend(frameon=False, fontsize=9, labelcolor=INK2, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


# --- Leave-one-shape-out search ------------------------------------------------------
def search(pairs, gts, px_mm, out_csv):
    keys = list(SEARCH_GRID)
    pre = list(itertools.product(SEARCH_GRID["bw_frac"],
                                 SEARCH_GRID["smooth_frac"],
                                 SEARCH_GRID["tight_lo_frac"]))
    n_cfg = len(pre) * len(SEARCH_GRID["refine"]) * len(SEARCH_GRID["disp_alpha"])
    print(f"\nsearching {n_cfg} settings x {len(pairs)} pairs "
          f"(this takes a few minutes) ...", flush=True)
    results = {}                          # setting -> {pair: (iou, f_1mm)}
    t0 = time.time()
    for i, (bw, sm, tl) in enumerate(pre, 1):
        for _, name, ref, dfm, _ in pairs:
            res = ds.detect(ref, dfm, tight=True, bw_frac=bw, smooth_frac=sm,
                            tight_lo_frac=tl)
            for refine in SEARCH_GRID["refine"]:
                m1 = (ds.refine_contour(res["mask"], res["score"], res["roi"],
                                        res["carrier"])
                      if refine else res["mask"])
                for a in SEARCH_GRID["disp_alpha"]:
                    m2 = ds.compensate_displacement(m1, res["dphi"],
                                                    res["carrier"], res["roi"], a)
                    s = score_mask(m2, gts[name], res["roi"], px_mm)
                    results.setdefault((bw, sm, tl, refine, a), {})[name] = \
                        (s["iou"], s["f_1mm"])
        print(f"  {i}/{len(pre)} ({time.time() - t0:.0f} s)", flush=True)

    def mean(cfg, names, k):
        return float(np.mean([results[cfg][n][k] for n in names]))

    def pick(names):
        """Best F@1mm among settings whose IoU is at least the baseline's."""
        base_iou = mean(baseline, names, 0)
        ok = [c for c in results if mean(c, names, 0) >= base_iou] or list(results)
        return max(ok, key=lambda c: mean(c, names, 1))

    def fmt(cfg):
        return ", ".join(f"{k}={v}" for k, v in zip(keys, cfg))

    baseline = (ds.BW_FRAC, ds.SMOOTH_SIGMA_FRAC, ds.TIGHT_LO_FRAC, False, 0.0)
    shapes = list(dict.fromkeys(p[0] for p in pairs))
    names_of = {s: [p[1] for p in pairs if p[0] == s] for s in shapes}
    all_names = [p[1] for p in pairs]

    print("\nleave-one-shape-out (setting picked without the held-out shape):")
    held = []
    for s in shapes:
        cfg = pick([n for n in all_names if n not in names_of[s]])
        iou, f1 = mean(cfg, names_of[s], 0), mean(cfg, names_of[s], 1)
        b_iou, b_f1 = mean(baseline, names_of[s], 0), mean(baseline, names_of[s], 1)
        held.append((iou, f1, b_iou, b_f1))
        print(f"  {s:<16} IoU {100 * b_iou:5.1f} -> {100 * iou:5.1f}   "
              f"F@1mm {100 * b_f1:5.1f} -> {100 * f1:5.1f}   [{fmt(cfg)}]")
    h = np.array(held)
    print(f"  {'MEAN':<16} IoU {100 * h[:, 2].mean():5.1f} -> "
          f"{100 * h[:, 0].mean():5.1f}   F@1mm {100 * h[:, 3].mean():5.1f} -> "
          f"{100 * h[:, 1].mean():5.1f}   <- honest (held-out) estimate")

    best = pick(all_names)
    print(f"\nsetting picked on all shapes: {fmt(best)}")
    print(f"  IoU {100 * mean(best, all_names, 0):.1f}%, "
          f"F@1mm {100 * mean(best, all_names, 1):.1f}% (in-sample)")
    defaults = dict(zip(keys, baseline))
    extra = [f"{k}={v}" for k, v in zip(keys, best) if v != defaults[k]]
    print("  as CONTACT_PARAMS: dict(" + ", ".join(["tight=True"] + extra) + ")")

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(keys + ["mean_iou", "mean_f_1mm"] +
                    [f"{n} {m}" for n in all_names for m in ("iou", "f_1mm")])
        for cfg, per in results.items():
            wr.writerow(list(cfg) +
                        [round(mean(cfg, all_names, 0), 4),
                         round(mean(cfg, all_names, 1), 4)] +
                        [round(v, 4) for n in all_names for v in per[n]])
    print(f"  all {len(results)} settings -> {out_csv}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default="data/raw/shape_pictures")
    ap.add_argument("--out", default="verification/eval_segmentation.csv")
    ap.add_argument("--figdir", default="figures/segmentation")
    ap.add_argument("--no-figures", action="store_true")
    ap.add_argument("--search", action="store_true",
                    help="leave-one-shape-out search over the contact-mode "
                         "parameters (a few minutes)")
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        sys.exit(f"Not a directory: {args.root}")
    print(f"looking for annotated pairs under {args.root} ...", flush=True)
    pairs = find_pairs(args.root)
    if not pairs:
        sys.exit("No annotated pairs found (need a *_gt image with a red outline).")

    gts = {}
    for _, name, _, _, gt_path in pairs:
        gts[name] = gt_mask(gt_path)
        if not gts[name].any():
            sys.exit(f"Empty ground truth (no closed red outline?): {gt_path}")
    px_mm = px_per_mm()
    print(f"{len(pairs)} pairs, scale {px_mm:.2f} px/mm in the "
          f"{ds.PROC_SIZE} px frame\n", flush=True)

    rows, views = evaluate(pairs, gts, px_mm)
    print_summary(rows, len(pairs))
    write_csv(args.out, rows)
    print(f"\nper-pair metrics -> {args.out}")

    if not args.no_figures:
        os.makedirs(args.figdir, exist_ok=True)
        for _, name, _, _, _ in pairs:
            fname = name.replace(os.sep, "_").replace("/", "_").replace(" ", "_")
            save_pair_figure(os.path.join(args.figdir, f"{fname}.png"), name,
                             views[name], gts[name])
        save_summary_figure(os.path.join(args.figdir, "summary.png"), rows)
        print(f"figures -> {args.figdir}/ (one per pair + summary.png)")

    if args.search:
        search(pairs, gts, px_mm,
               os.path.splitext(args.out)[0] + "_search.csv")


if __name__ == "__main__":
    main()
