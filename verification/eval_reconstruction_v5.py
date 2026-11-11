#!/usr/bin/env python3
"""
eval_reconstruction_v5.py — Figures of the 3-D reconstruction of the four stars
with reconstruct_v5.py (outline from the stretch map and the edge line, then
the depth read by the sensor), and how steady the outline is.

A rigid star has one outline whatever the depth or the orientation, so the
area of the outline found should stay the same from photo to photo. The script
compares that with reconstruct_v4.py (results/reconstruction_v4/results.csv,
run verification/eval_reconstruction_v4.py first).

Every star is reconstructed with a calibration made on the other three stars.
Writes results/reconstruction_v5/: results.csv, summary.md and figures/.

Usage from the repo root:
    python verification/eval_reconstruction_v5.py
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
OUT = "results/reconstruction_v5"
V4_CSV = "results/reconstruction_v4/results.csv"
STARS = ["S1", "S2", "S3", "S4"]
INK, SURFACE = "#0b0b0b", "#fcfcfb"


def label(r):
    ge = "≥ " if r["beyond"] else ""            # above the calibrated range: lower bounds
    head = r["star"] + (f" at {r['angle_deg']}°" if r["angle_deg"] else "")
    return (f"{head}\nMARK-10: {r['depth_true']:.1f} mm, {r['force_true']:.1f} N\n"
            f"sensor: {ge}{r['depth_mm']:.2f} mm, {ge}{r['force_N']:.1f} N")


def sheet(items, path, title):
    """Rows: stretch map with the outline, edge line with the outline, 3-D surface."""
    n = len(items)
    zmax = max(max(rec["depth_mm"] for _, rec in items), 0.1)
    fig = plt.figure(figsize=(3.9 * n, 12.4), facecolor=SURFACE)
    for j, (r, rec) in enumerate(items):
        rv4.stretch_view(fig.add_subplot(3, n, j + 1), rec, label(r), rv5.WINDOW_MM)
        rv5.edge_view(fig.add_subplot(3, n, n + j + 1), rec, f"outline {rec['area_mm2']:.0f} mm²")
        rv4.surface(fig.add_subplot(3, n, 2 * n + j + 1, projection="3d"), rec, zmax, half_mm=rv5.WINDOW_MM)
    fig.suptitle(title, color=INK, fontsize=12, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, dpi=100, facecolor=SURFACE)
    plt.close(fig)


def steadiness(rows, key="outline_mm2"):
    """Per star: mean outline area and its spread over all photos (sd / mean, %)."""
    out = {}
    for s in STARS:
        a = np.array([float(r[key]) for r in rows if r["star"] == s])
        out[s] = (float(a.mean()), float(100 * a.std() / a.mean()), float(a.min()), float(a.max()), len(a))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=OUT)
    args = p.parse_args()
    fig_dir = os.path.join(args.out, "figures")
    os.makedirs(fig_dir, exist_ok=True)
    with open(os.path.join(ROOT, "log_sheet.csv"), newline="", encoding="utf-8") as fh:
        log = [r for r in csv.DictReader(fh) if r["file"]]
    cals = {s: rv3.StretchCalibration(rv3.CALIB_CSV, exclude=s) for s in STARS}

    rows, recs = [], {}
    for r in log:
        rec = rv5.reconstruct(os.path.join(ROOT, r["ref_file"]), os.path.join(ROOT, r["file"]), cals[r["star"]])
        rows.append({"star": r["star"], "angle_deg": int(r["angle_deg"]), "repeat": int(r["repeat"]),
                     "depth_true": float(r["depth_mm"]),
                     "force_true": 0.5 * (float(r["force_lo_N"]) + float(r["force_hi_N"])),
                     "depth_mm": rec["depth_mm"], "force_N": rec["force_N"], "beyond": rec["beyond_calibration"],
                     "outline_mm2": rec["area_mm2"], "outline_pieces": rec["n_pieces"],
                     "edge_strength": rec["edge_strength"], "file": r["file"]})
        recs[r["file"]] = rec
        print(f"  {r['file']:<34} outline {rec['area_mm2']:4.0f} mm2 in {rec['n_pieces']} piece(s), edge strength "
              f"{rec['edge_strength']:.2f} | {rec['depth_mm']:.2f} mm, {rec['force_N']:5.1f} N", flush=True)
    with open(os.path.join(args.out, "results.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)

    first = lambda r: r["angle_deg"] == 0 and r["repeat"] == 1                      # noqa: E731
    deepest = {}
    for s in STARS:
        ser = sorted((r for r in rows if r["star"] == s and first(r)), key=lambda r: r["depth_true"])
        deepest[s] = ser[-1]
        sheet([(r, recs[r["file"]]) for r in ser], os.path.join(fig_dir, f"{s}_series_3d.png"),
              f"{s} at each depth: stretch map, edge line and 3-D reconstruction (black / blue line = outline)")
        turned = sorted((r for r in rows if r["star"] == s and r["angle_deg"] != 0), key=lambda r: r["angle_deg"])
        same0 = [r for r in rows if r["star"] == s and first(r) and r["depth_true"] == turned[0]["depth_true"]]
        sheet([(r, recs[r["file"]]) for r in same0 + turned], os.path.join(fig_dir, f"{s}_orientations_3d.png"),
              f"{s}: same depth, different orientations")
    sheet([(deepest[s], recs[deepest[s]["file"]]) for s in STARS], os.path.join(fig_dir, "overview_3d.png"),
          "The four stars at their deepest press: stretch map, edge line and 3-D reconstruction")

    st5 = steadiness(rows)
    lines = ["# Reconstrução 3D das estrelas: contorno da v5 contra o da v4", "",
             "Uma estrela rígida tem sempre o mesmo contorno, qualquer que seja a profundidade ou a orientação. "
             "Por isso a área do contorno encontrado devia ser igual em todas as fotos da mesma estrela. "
             "Variação = desvio-padrão / média.", ""]
    if os.path.exists(V4_CSV):
        with open(V4_CSV, newline="", encoding="utf-8") as fh:
            st4 = steadiness(list(csv.DictReader(fh)))
        lines += ["| estrela | fotos | v4: área média (mm²) | v4: variação (%) | v4: mín–máx | v5: área média (mm²) | "
                  "v5: variação (%) | v5: mín–máx |", "|---|---|---|---|---|---|---|---|"]
        for s in STARS:
            a, b = st4[s], st5[s]
            lines.append(f"| {s} | {b[4]} | {a[0]:.0f} | {a[1]:.0f} | {a[2]:.0f}–{a[3]:.0f} | {b[0]:.0f} | "
                         f"**{b[1]:.0f}** | {b[2]:.0f}–{b[3]:.0f} |")
    else:
        lines += ["| estrela | fotos | área média (mm²) | variação (%) | mín–máx |", "|---|---|---|---|---|"]
        for s in STARS:
            b = st5[s]
            lines.append(f"| {s} | {b[4]} | {b[0]:.0f} | {b[1]:.0f} | {b[2]:.0f}–{b[3]:.0f} |")
    lines += ["", "## Por foto (v5)", "",
              "| estrela | ângulo | série | profundidade (mm) | contorno (mm²) | peças | nitidez da borda |",
              "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['star']} | {r['angle_deg']}° | {r['repeat']} | {r['depth_true']:.1f} | "
                     f"{r['outline_mm2']:.0f} | {r['outline_pieces']} | {r['edge_strength']:.2f} |")
    with open(os.path.join(args.out, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines[:lines.index("## Por foto (v5)")]))
    print(f"\n-> {args.out}/ (results.csv, summary.md, figures/)")


if __name__ == "__main__":
    main()
