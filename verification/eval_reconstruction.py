#!/usr/bin/env python3
"""
eval_reconstruction.py — Liam's 3-D reconstruction (uniform_reconstruct.py, v1)
against reconstruct_v2.py, on Liam's photos.

    force photos   flat circle (314 mm^2) on the Mark-10 at known force; the true
                   depth is the Mark-10 depth at that force. v2 is calibrated on
                   img_01-03 of every level, so img_04-05 are the test photos.
                   The 4 extra reference photos (no press) check false contacts.
    shape photos   pressed by hand, no force recorded: only the outline of the
                   3-D surface can be checked (against the hand-drawn outlines),
                   plus whether force and depth stay inside the calibrated range.

Writes CSVs, a summary and figures to results/reconstruction_v2/.
Run `python src/tactile/reconstruct_v2.py --build-calibration` first.

Usage from the repo root:
    python verification/eval_reconstruction.py
"""

import argparse
import contextlib
import csv
import io
import os
import sys

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
import tactile.detect_shape as ds              # noqa: E402
import tactile.estimate_force_depth as efd     # noqa: E402
import tactile.reconstruct_v2 as rv            # noqa: E402
import tactile.uniform_reconstruct as ur       # noqa: E402
import eval_segmentation as ev                 # noqa: E402

OUT = "results/reconstruction_v2"
TEST_FILES = ("img_04.jpg", "img_05.jpg")
NO_PRESS = ("img_02.jpg", "img_03.jpg", "img_04.jpg", "img_05.jpg")
C1, C2, INK, INK2, RULE, SURFACE = "#1baf7a", "#eb6834", "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"
SHOWCASE = [("force 30 N", "data/raw/force_pictures/reference/img_01.jpg", "data/raw/force_pictures/30N/img_04.jpg"),
            ("Square", "data/raw/shape_pictures/Square/img_01.jpg", "data/raw/shape_pictures/Square/img_02.jpg"),
            ("Square Circle", "data/raw/shape_pictures/Square Circle/img_01.jpg",
             "data/raw/shape_pictures/Square Circle/img_02.jpg"),
            ("Three Circles", "data/raw/shape_pictures/Three Circles/img_01.jpg",
             "data/raw/shape_pictures/Three Circles/img_02.jpg")]


def to768(mask):
    return cv2.resize(mask.astype(np.uint8), (ds.PROC_SIZE, ds.PROC_SIZE), interpolation=cv2.INTER_NEAREST) > 0


def run_v1(ref, dfm, cal1):
    """Liam's pipeline; (report, footprint mask in the 768 frame, depth map or None)."""
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            rec = ur.reconstruct_global(ref, dfm, cal1)
        return rec["report"], to768(rec["mask"]), rec
    except RuntimeError:
        return [], np.zeros((ds.PROC_SIZE,) * 2, bool), None


def circle_mask():
    m = cv2.imread(ur.CALIB_MASK_PATH, cv2.IMREAD_GRAYSCALE)
    h, w = m.shape
    r = int(min(h, w) * ds.CROP_RATIO)
    crop = m[h // 2 - r:h // 2 + r, w // 2 - r:w // 2 + r]
    return cv2.resize(crop, (ds.PROC_SIZE,) * 2, interpolation=cv2.INTER_AREA) > 127


def dice(a, b):
    return 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)


# --- force photos ----------------------------------------------------------------
def force_photos(cal1, cal2, mark10, pxmm):
    circ = circle_mask()
    rows = []
    levels = sorted((d for d in os.listdir(rv.FORCE_DIR) if d.endswith("N")), key=lambda d: int(d[:-1]))
    jobs = [(float(lv[:-1]), os.path.join(rv.FORCE_DIR, lv, fn)) for lv in levels for fn in TEST_FILES]
    jobs += [(0.0, os.path.join(rv.FORCE_DIR, "reference", fn)) for fn in NO_PRESS]
    for F, path in jobs:
        true_d = mark10.depth_from_force(F) if F > 0 else 0.0
        rep1, m1, _ = run_v1(rv.FORCE_REF, path, cal1)
        with contextlib.redirect_stdout(io.StringIO()):
            rec2 = rv.reconstruct(rv.FORCE_REF, path, cal2)
        rep2 = rec2["report"]
        for method, rep, mask in (("v1", rep1, m1), ("v2", rep2, rec2["mask"])):
            big = max(rep, key=lambda r: r["force_N"] if method == "v1" else r["area_mm2"]) if rep else None
            rows.append({"photo": os.path.relpath(path, rv.FORCE_DIR), "force_true": F, "depth_true": true_d,
                         "method": method, "n_contacts": len(rep),
                         "force_pred": big["force_N"] if big else 0.0,
                         "depth_pred": big["depth_mm"] if big else 0.0,
                         "area_mm2": float(mask.sum() / pxmm ** 2),
                         "dice_circle": float(dice(mask, circ)) if F > 0 else float("nan"),
                         "beyond": bool(big["beyond_calibration"]) if big else False})
        print(f"  {os.path.relpath(path, rv.FORCE_DIR):<22} true {F:4.0f} N / {true_d:.2f} mm | "
              + " | ".join(f"{r['method']} {r['force_pred']:5.1f} N {r['depth_pred']:.2f} mm "
                           f"({r['n_contacts']} contacts, {r['area_mm2']:.0f} mm2)" for r in rows[-2:]), flush=True)
    return rows


def force_summary(rows):
    out = {}
    for m in ("v1", "v2"):
        t = [r for r in rows if r["method"] == m and r["force_true"] > 0]
        fe = np.array([r["force_pred"] - r["force_true"] for r in t])
        de = np.array([r["depth_pred"] - r["depth_true"] for r in t])
        nop = [r for r in rows if r["method"] == m and r["force_true"] == 0]
        out[m] = {"n": len(t), "force_mae": np.abs(fe).mean(), "force_rmse": np.sqrt((fe ** 2).mean()),
                  "force_max": np.abs(fe).max(), "force_bias": fe.mean(),
                  "depth_mae": np.abs(de).mean(), "depth_rmse": np.sqrt((de ** 2).mean()),
                  "depth_max": np.abs(de).max(),
                  "area_median": np.median([r["area_mm2"] for r in t]),
                  "dice_median": np.median([r["dice_circle"] for r in t]),
                  "one_contact": sum(r["n_contacts"] == 1 for r in t),
                  "zero_force": sum(r["force_pred"] == 0 for r in t),
                  "nopress_false": sum(r["n_contacts"] > 0 for r in nop), "nopress_n": len(nop)}
    return out


def calibration_cv(mark10):
    """Leave-one-force-level-out on the calibration photos (what chose the settings)."""
    with open(rv.CALIB_CSV, newline="", encoding="utf-8") as fh:
        R = list(csv.DictReader(fh))
    s = np.array([float(r["stretch"]) for r in R])
    F = np.array([float(r["force_N"]) for r in R])
    A = np.array([float(r["area_mm2"]) for r in R])
    D = np.array([float(r["depth_mm"]) for r in R])
    fe, de = [], []
    for lv in np.unique(F):
        tr, te = F != lv, F == lv
        cp = np.polyfit(s[tr], F[tr] / rv.CALIB_AREA_MM2, 2)
        cd = np.polyfit(s[tr], D[tr], 2)
        fe += list(np.maximum(np.polyval(cp, s[te]), 0) * A[te] - F[te])
        de += list(np.maximum(np.polyval(cd, s[te]), 0) - D[te])
    return np.abs(fe).mean(), np.abs(de).mean(), len(R)


# --- shape photos ----------------------------------------------------------------
def shape_photos(cal1, cal2, pxmm):
    gts = {os.path.normpath(dfm): gtp for _, _, _, dfm, gtp in ev.find_pairs("data/raw/shape_pictures")}
    rows, scores = [], []
    root = "data/raw/shape_pictures"
    for shape in sorted(os.listdir(root)):
        d = os.path.join(root, shape)
        if not os.path.isdir(d):
            continue
        imgs = sorted(f for f in os.listdir(d) if f.startswith("img_") and f.endswith(".jpg"))
        for f in imgs[1:]:
            ref, dfm = os.path.join(d, imgs[0]), os.path.join(d, f)
            rep1, m1, _ = run_v1(ref, dfm, cal1)
            with contextlib.redirect_stdout(io.StringIO()):
                rec2 = rv.reconstruct(ref, dfm, cal2)
            for method, rep in (("v1", rep1), ("v2", rec2["report"])):
                for r in rep:
                    rows.append({"shape": shape, "photo": f, "method": method, "contact": r["contact"],
                                 "area_mm2": r["contact_area_mm2"] if method == "v1" else r["area_mm2"],
                                 "force_N": r["force_N"], "depth_mm": r["depth_mm"],
                                 "beyond": bool(r["beyond_calibration"]),
                                 "kind": rec2["kind"] if method == "v2" else "footprint"})
            if os.path.normpath(dfm) in gts:
                gt = ev.gt_mask(gts[os.path.normpath(dfm)])
                for method, mask in (("v1", m1), ("v2", rec2["mask"])):
                    scores.append({"shape": shape, "photo": f, "method": method,
                                   **ev.score_mask(mask, gt, rec2["roi"], pxmm)})
            print(f"  {shape}/{f}: v2 signal '{rec2['kind']}' (plateau {rec2['plateau']:+.2f} rad), "
                  f"v1 {len(rep1)} / v2 {len(rec2['report'])} contacts", flush=True)
    return rows, scores


# --- figures ---------------------------------------------------------------------
def fig_force(rows, path):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), facecolor=SURFACE)
    for ax, key, truth, unit, title in ((axes[0], "force_pred", "force_true", "N", "Force"),
                                        (axes[1], "depth_pred", "depth_true", "mm", "Depth")):
        t = [r for r in rows if r["force_true"] > 0]
        top = max(max(r[truth] for r in t), max(r[key] for r in t)) * 1.08
        ax.plot([0, top], [0, top], color=INK2, lw=1, ls=(0, (4, 3)), zorder=1)
        for m, col, lab in (("v1", C1, "Liam (v1)"), ("v2", C2, "v2")):
            x = [r[truth] for r in t if r["method"] == m]
            y = [r[key] for r in t if r["method"] == m]
            ax.scatter(x, y, s=34, color=col, edgecolor=SURFACE, linewidth=1.2, label=lab, zorder=3)
        ax.set_xlim(0, top)
        ax.set_ylim(0, top)
        ax.set_xlabel(f"true {title.lower()} ({unit})", color=INK)
        ax.set_ylabel(f"reconstructed {title.lower()} ({unit})", color=INK)
        ax.set_title(f"{title}: test photos (img_04-05), flat circle", color=INK, fontsize=11)
        ax.grid(color=RULE, lw=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def surface(ax, depth_768, pxmm, title, zmax):
    n = depth_768.shape[0]
    step = max(1, n // 150)
    Z = depth_768[::step, ::step]
    Y, X = (np.mgrid[:n:step, :n:step].astype(np.float32) - n / 2) / pxmm
    ax.plot_surface(X, Y, Z, facecolors=cm.viridis(np.clip(Z / zmax, 0, 1)), rstride=1, cstride=1,
                    linewidth=0, antialiased=False, shade=True)
    ax.set_zlim(0, zmax * 1.1)
    ax.set_xlabel("x (mm)", fontsize=8)
    ax.set_ylabel("y (mm)", fontsize=8)
    ax.set_zlabel("depth (mm)", fontsize=8)
    ax.set_title(title, fontsize=9, color=INK)
    ax.view_init(elev=35, azim=-60)


def fig_showcase(cal1, cal2, pxmm, out_dir):
    for name, ref, dfm in SHOWCASE:
        rep1, _, rec1 = run_v1(ref, dfm, cal1)
        with contextlib.redirect_stdout(io.StringIO()):
            rec2 = rv.reconstruct(ref, dfm, cal2)
        d1 = cv2.resize(rec1["depth"], (ds.PROC_SIZE,) * 2, interpolation=cv2.INTER_AREA) if rec1 else \
            np.zeros((ds.PROC_SIZE,) * 2, np.float32)
        d2 = rec2["depth"]
        zmax = max(float(d1.max()), float(d2.max()), 0.1)
        fig = plt.figure(figsize=(13, 5.6), facecolor=SURFACE)
        t1 = " | ".join(f"{r['depth_mm']:.2f} mm, {r['force_N']:.0f} N" for r in rep1) or "no contact"
        t2 = " | ".join(("≥ " if r["beyond_calibration"] else "") + f"{r['depth_mm']:.2f} mm, {r['force_N']:.1f} N"
                        for r in rec2["report"])
        surface(fig.add_subplot(121, projection="3d"), d1, pxmm, f"Liam (v1)\n{t1}", zmax)
        surface(fig.add_subplot(122, projection="3d"), d2, pxmm, f"v2\n{t2 or 'no contact'}", zmax)
        fig.suptitle(name, color=INK, fontsize=12, fontweight="bold")
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, "3d_" + name.replace(" ", "_") + ".png"), dpi=110, facecolor=SURFACE)
        plt.close(fig)
        rv.show_overlay(rec2, title=name, show=False,
                        save_png=os.path.join(out_dir, "contacts_v2_" + name.replace(" ", "_") + ".png"))


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=OUT)
    args = p.parse_args()
    fig_dir = os.path.join(args.out, "figures")
    os.makedirs(fig_dir, exist_ok=True)
    cal1 = efd.Calibration(ur.RATIO_CSV, ur.DEPTH_CSV)
    cal2 = rv.StretchCalibration(rv.CALIB_CSV)
    mark10 = cal1
    pxmm = rv.px_per_mm()

    print("force photos (test: img_04-05 of every level; no-press: reference img_02-05)")
    frows = force_photos(cal1, cal2, mark10, pxmm)
    write_csv(os.path.join(args.out, "force_photos.csv"), frows)
    fs = force_summary(frows)
    cv_f, cv_d, n_cal = calibration_cv(mark10)

    print("\nshape photos")
    srows, sscores = shape_photos(cal1, cal2, pxmm)
    write_csv(os.path.join(args.out, "shape_contacts.csv"), srows)
    write_csv(os.path.join(args.out, "shape_outline_scores.csv"), sscores)

    fig_force(frows, os.path.join(fig_dir, "force_depth_vs_true.png"))
    fig_showcase(cal1, cal2, pxmm, fig_dir)

    lines = ["# Reconstrução 3D: Liam (v1) contra v2", "",
             f"## Fotos de força (círculo de 314 mm², {fs['v1']['n']} fotos de teste: img_04-05 de cada nível)", "",
             "| | Liam (v1) | v2 |", "|---|---|---|"]
    def row(label, key, fmt):
        lines.append(f"| {label} | {fmt.format(fs['v1'][key])} | {fmt.format(fs['v2'][key])} |")
    row("erro médio da força (N)", "force_mae", "{:.2f}")
    row("RMSE da força (N)", "force_rmse", "{:.2f}")
    row("erro máximo da força (N)", "force_max", "{:.1f}")
    row("viés da força (N)", "force_bias", "{:+.2f}")
    row("erro médio da profundidade (mm)", "depth_mae", "{:.3f}")
    row("RMSE da profundidade (mm)", "depth_rmse", "{:.3f}")
    row("erro máximo da profundidade (mm)", "depth_max", "{:.2f}")
    row("área mediana da região (mm², real 314)", "area_median", "{:.0f}")
    row("Dice mediano contra o círculo (%)", "dice_median", "{:.1%}")
    row("fotos com 1 só contacto", "one_contact", "{:d}")
    row("fotos com força 0", "zero_force", "{:d}")
    lines.append(f"| fotos sem toque com contacto falso (de {fs['v1']['nopress_n']}) | "
                 f"{fs['v1']['nopress_false']} | {fs['v2']['nopress_false']} |")
    lines += ["", f"Validação da calibração v2 (deixando um nível de força de fora, {n_cal} fotos de calibração): "
              f"erro médio da força {cv_f:.2f} N, da profundidade {cv_d:.3f} mm.", "",
              "## Fotos de formas: contorno da superfície 3D contra o contorno desenhado", "",
              "| forma | Liam (v1): Dice / IoU / contorno 1 mm | v2: Dice / IoU / contorno 1 mm |", "|---|---|---|"]
    for shape in sorted({s["shape"] for s in sscores}):
        cells = []
        for m in ("v1", "v2"):
            s = [x for x in sscores if x["shape"] == shape and x["method"] == m][0]
            cells.append(f"{100 * s['dice']:.1f} / {100 * s['iou']:.1f} / {100 * s['f_1mm']:.1f}")
        lines.append(f"| {shape} | {cells[0]} | {cells[1]} |")
    means = []
    for m in ("v1", "v2"):
        s = [x for x in sscores if x["method"] == m]
        means.append(" / ".join(f"{np.mean([100 * x[k] for x in s]):.1f}" for k in ("dice", "iou", "f_1mm")))
    lines.append(f"| **média** | **{means[0]}** | **{means[1]}** |")
    lines += ["", "## Fotos de formas: força e profundidade (sem valor real conhecido)", "",
              "| forma | foto | método | contacto | área (mm²) | força (N) | profundidade (mm) | fora da calibração |",
              "|---|---|---|---|---|---|---|---|"]
    for r in srows:
        lines.append(f"| {r['shape']} | {r['photo']} | {r['method']} | {r['contact']} | {r['area_mm2']:.0f} | "
                     f"{'≥ ' if r['beyond'] and r['method'] == 'v2' else ''}{r['force_N']:.1f} | "
                     f"{'≥ ' if r['beyond'] and r['method'] == 'v2' else ''}{r['depth_mm']:.2f} | "
                     f"{'sim' if r['beyond'] else ''} |")
    with open(os.path.join(args.out, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines[:22]))
    print(f"\n-> {args.out}/ (summary.md, CSVs, figures/)")


if __name__ == "__main__":
    main()
