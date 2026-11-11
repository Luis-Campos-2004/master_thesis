#!/usr/bin/env python3
"""
eval_reconstruction_v3.py — 3-D reconstruction of the four stars pressed on the
MARK-10 (data/raw/depth_stars), with reconstruct_v3.py, against the depth and
force of the log sheet. reconstruct_v2.py with Liam's calibration is run on the
same photos as the starting point.

Every star is reconstructed with a v3 calibration made on the other three stars
only, so its depth and force are out-of-sample.

Writes results/reconstruction_v3/: results.csv, summary.md and figures/
(one 3-D series per star, an overview at the deepest press, sensor against
MARK-10). Run `python src/tactile/reconstruct_v3.py --build-calibration` first.

Usage from the repo root:
    python verification/eval_reconstruction_v3.py
"""

import argparse
import contextlib
import csv
import io
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
import tactile.detect_shape as ds              # noqa: E402
import tactile.reconstruct_v2 as rv2           # noqa: E402
import tactile.reconstruct_v3 as rv3           # noqa: E402
import segment_photos_v2 as sp2                # noqa: E402

ROOT = rv3.STARS_DIR
OUT = "results/reconstruction_v3"
STARS = ["S1", "S2", "S3", "S4"]
COLOUR = dict(zip(STARS, ["#1baf7a", "#2a78d6", "#eb6834", "#eda100"]))
MARKER = dict(zip(STARS, ["o", "s", "^", "D"]))
INK, INK2, RULE, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"


def run_v2(ref, dfm, cal2, pxmm):
    """reconstruct_v2 as it is. It has no crop argument, so the crop that keeps the stripe
    period of the new camera at Liam's value is passed through detect_shape's defaults."""
    crop, _ = sp2.crop_ratio_for(ref)
    old_roi, old_det = ds.load_roi.__defaults__, ds.detect.__defaults__
    old_px = rv2.px_per_mm
    try:
        ds.load_roi.__defaults__ = (ds.PROC_SIZE, crop)
        ds.detect.__defaults__ = (old_det[0], crop) + old_det[2:]
        rv2.px_per_mm = lambda size=ds.PROC_SIZE: pxmm
        with contextlib.redirect_stdout(io.StringIO()):
            rep = rv2.reconstruct(ref, dfm, cal2)["report"]
    finally:
        ds.load_roi.__defaults__, ds.detect.__defaults__, rv2.px_per_mm = old_roi, old_det, old_px
    return (max((c["depth_mm"] for c in rep), default=0.0), sum(c["force_N"] for c in rep))


def style(ax, xlabel, ylabel, title):
    ax.set_xlabel(xlabel, color=INK)
    ax.set_ylabel(ylabel, color=INK)
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    ax.grid(color=RULE, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def label(r):
    ge = "≥ " if r["beyond_v3"] else ""         # above the calibrated range: lower bounds
    return (f"MARK-10: {r['depth_true']:.1f} mm, {r['force_true']:.1f} N\n"
            f"sensor: {ge}{r['depth_v3']:.2f} mm, {ge}{r['force_v3']:.1f} N")


def fig_series(star, items, path):
    zmax = max(max(float(rec["depth"].max()) for _, rec in items), 0.1)
    fig = plt.figure(figsize=(3.5 * len(items), 7.0), facecolor=SURFACE)
    im = None
    for j, (r, rec) in enumerate(items):
        rv3.surface(fig.add_subplot(2, len(items), j + 1, projection="3d"), rec, zmax, label(r))
        im = rv3.top_view(fig.add_subplot(2, len(items), len(items) + j + 1), rec, zmax)
    fig.suptitle(f"{star}: 3-D reconstruction at each depth (calibration from the other three stars)",
                 color=INK, fontsize=12, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 0.96, 0.95))
    fig.colorbar(im, cax=fig.add_axes([0.968, 0.1, 0.008, 0.3]), label="depth (mm)")
    fig.savefig(path, dpi=100, facecolor=SURFACE)
    plt.close(fig)


def fig_overview(items, path, title):
    fig = plt.figure(figsize=(4.2 * len(items), 8.2), facecolor=SURFACE)
    for j, (r, rec) in enumerate(items):
        zmax = max(float(rec["depth"].max()), 0.1)
        rv3.surface(fig.add_subplot(2, len(items), j + 1, projection="3d"), rec, zmax,
                    f"{r['star']}" + (f" at {r['angle_deg']}°" if r["angle_deg"] else "") + "\n" + label(r))
        im = rv3.top_view(fig.add_subplot(2, len(items), len(items) + j + 1), rec, zmax)
        fig.colorbar(im, ax=fig.axes[-1], shrink=0.75, label="depth (mm)")
    fig.suptitle(title, color=INK, fontsize=12, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=100, facecolor=SURFACE)
    plt.close(fig)


def fig_scatter(rows, path):
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.2), facecolor=SURFACE)
    for ax, kt, k2, k3, unit, title in ((axes[0], "depth_true", "depth_v2", "depth_v3", "mm", "Depth"),
                                        (axes[1], "force_true", "force_v2", "force_v3", "N", "Force")):
        top = 1.08 * max(max(r[kt] for r in rows), max(r[k3] for r in rows))
        ax.plot([0, top], [0, top], color=INK2, lw=1, ls=(0, (4, 3)), zorder=1)
        ax.scatter([r[kt] for r in rows], [min(r[k2], top) for r in rows], marker="x", s=30, lw=1.2,
                   color="#898781", label="v2, Liam's calibration", zorder=2)
        for s in STARS:
            pts = [r for r in rows if r["star"] == s]
            ax.scatter([r[kt] for r in pts], [r[k3] for r in pts], marker=MARKER[s], s=44, color=COLOUR[s],
                       edgecolor=SURFACE, linewidth=1.0, label=f"v3, {s}", zorder=3)
        ax.set_xlim(0, top)
        ax.set_ylim(0, top)
        style(ax, f"true {title.lower()} ({unit}, MARK-10)", f"reconstructed {title.lower()} ({unit})",
              f"{title}: sensor against MARK-10")
        ax.legend(frameon=False, loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=OUT)
    args = p.parse_args()
    fig_dir = os.path.join(args.out, "figures")
    os.makedirs(fig_dir, exist_ok=True)
    with open(os.path.join(ROOT, "log_sheet.csv"), newline="", encoding="utf-8") as fh:
        log = [r for r in csv.DictReader(fh) if r["file"]]
    cal2 = rv2.StretchCalibration(rv2.CALIB_CSV)
    pxmm2 = rv2.px_per_mm()
    cals = {s: rv3.StretchCalibration(rv3.CALIB_CSV, exclude=s) for s in STARS}

    rows, recs = [], {}
    for r in log:
        ref, dfm = os.path.join(ROOT, r["ref_file"]), os.path.join(ROOT, r["file"])
        rec = rv3.reconstruct(ref, dfm, cals[r["star"]])
        d2, f2 = run_v2(ref, dfm, cal2, pxmm2)
        row = {"star": r["star"], "angle_deg": int(r["angle_deg"]), "repeat": int(r["repeat"]),
               "depth_true": float(r["depth_mm"]),
               "force_true": 0.5 * (float(r["force_lo_N"]) + float(r["force_hi_N"])),
               "depth_v3": rec["depth_mm"], "force_v3": rec["force_N"], "depth_v2": d2, "force_v2": f2,
               "beyond_v3": rec["beyond_calibration"], "file": r["file"]}
        rows.append(row)
        recs[r["file"]] = rec
        print(f"  {r['file']:<34} true {row['depth_true']:.1f} mm {row['force_true']:5.1f} N | "
              f"v3 {row['depth_v3']:.2f} mm {row['force_v3']:5.1f} N | v2 {d2:.2f} mm {f2:5.1f} N", flush=True)
    with open(os.path.join(args.out, "results.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)

    first = lambda r: r["angle_deg"] == 0 and r["repeat"] == 1                      # noqa: E731
    for s in STARS:
        items = sorted(((r, recs[r["file"]]) for r in rows if r["star"] == s and first(r)),
                       key=lambda it: it[0]["depth_true"])
        fig_series(s, items, os.path.join(fig_dir, f"{s}_series_3d.png"))
    deepest = [max((r for r in rows if r["star"] == s and first(r)), key=lambda r: r["depth_true"]) for s in STARS]
    fig_overview([(r, recs[r["file"]]) for r in deepest], os.path.join(fig_dir, "overview_3d.png"),
                 "3-D reconstruction of the four stars at their deepest press")
    for s in STARS:
        turned = sorted((r for r in rows if r["star"] == s and r["depth_true"] == deepest[STARS.index(s)]["depth_true"]
                         and (r["angle_deg"] != 0 or first(r))), key=lambda r: r["angle_deg"])
        fig_overview([(r, recs[r["file"]]) for r in turned], os.path.join(fig_dir, f"{s}_orientations_3d.png"),
                     f"{s}: same depth, different orientations")
    fig_scatter(rows, os.path.join(fig_dir, "sensor_vs_mark10.png"))

    def stats(items, kp, kt):
        e = np.array([r[kp] - r[kt] for r in items], float)
        return np.abs(e).mean(), e.mean(), np.abs(e).max()

    lines = ["# Reconstrução 3D das estrelas (MARK-10): v3 contra v2", "",
             f"{len(rows)} fotos. v3: calibração feita nas outras três estrelas. "
             "v2: calibração do Liam (círculo de 20 mm, outra câmara).", "",
             "| | v2 (calibração do Liam) | v3 |", "|---|---|---|"]
    for name, kt, k2, k3, fmt in (("profundidade", "depth_true", "depth_v2", "depth_v3", "{:.2f} mm"),
                                  ("força", "force_true", "force_v2", "force_v3", "{:.1f} N")):
        a, b = stats(rows, k2, kt), stats(rows, k3, kt)
        lines.append(f"| erro médio da {name} | {fmt.format(a[0])} | **{fmt.format(b[0])}** |")
        lines.append(f"| viés da {name} | {fmt.format(a[1])} | {fmt.format(b[1])} |")
        lines.append(f"| erro máximo da {name} | {fmt.format(a[2])} | {fmt.format(b[2])} |")
    lines += ["", "## Por estrela (v3)", "",
              "Fotos acima da gama calibrada: a v3 não extrapola e dá o valor do fim da gama (limite inferior).", "",
              "| estrela | fotos | erro médio da profundidade (mm) | erro médio da força (N) | fotos acima da gama calibrada |",
              "|---|---|---|---|---|"]
    for s in STARS:
        it = [r for r in rows if r["star"] == s]
        lines.append(f"| {s} | {len(it)} | {stats(it, 'depth_v3', 'depth_true')[0]:.2f} | "
                     f"{stats(it, 'force_v3', 'force_true')[0]:.1f} | {sum(r['beyond_v3'] for r in it)} |")
    lines += ["", "## Por foto", "",
              "| estrela | ângulo | série | profundidade real (mm) | v3 (mm) | v2 (mm) | força real (N) | v3 (N) | v2 (N) |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['star']} | {r['angle_deg']}° | {r['repeat']} | {r['depth_true']:.1f} | {r['depth_v3']:.2f} | "
                     f"{r['depth_v2']:.2f} | {r['force_true']:.1f} | {r['force_v3']:.1f} | {r['force_v2']:.1f} |")
    with open(os.path.join(args.out, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines[:lines.index("## Por foto")]))
    print(f"\n-> {args.out}/ (summary.md, results.csv, figures/)")


if __name__ == "__main__":
    main()
