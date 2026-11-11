#!/usr/bin/env python3
"""
eval_reconstruction_v4.py — Figures of the 3-D reconstruction of the four stars
with reconstruct_v4.py (outline from the 2-D stretch map, then the depth read
by the sensor). Depth and force are the same as in v3
(verification/eval_reconstruction_v3.py); what changes is the surface.

Every star is reconstructed with a calibration made on the other three stars.
Writes results/reconstruction_v4/: results.csv and figures/ (overview at the
deepest press, one series per star, the orientations of each star).

Usage from the repo root:
    python verification/eval_reconstruction_v4.py
"""

import argparse
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import tactile.reconstruct_v3 as rv3           # noqa: E402
import tactile.reconstruct_v4 as rv4           # noqa: E402

ROOT = rv3.STARS_DIR
OUT = "results/reconstruction_v4"
STARS = ["S1", "S2", "S3", "S4"]
INK, SURFACE = "#0b0b0b", "#fcfcfb"


def label(r):
    ge = "≥ " if r["beyond"] else ""            # above the calibrated range: lower bounds
    head = r["star"] + (f" at {r['angle_deg']}°" if r["angle_deg"] else "")
    return (f"{head}\nMARK-10: {r['depth_true']:.1f} mm, {r['force_true']:.1f} N\n"
            f"sensor: {ge}{r['depth_mm']:.2f} mm, {ge}{r['force_N']:.1f} N")


def sheet(items, path, title):
    """Top row: stretch map with the outline. Bottom row: the 3-D surface."""
    n = len(items)
    zmax = max(max(rec["depth_mm"] for _, rec in items), 0.1)
    fig = plt.figure(figsize=(3.9 * n, 8.6), facecolor=SURFACE)
    for j, (r, rec) in enumerate(items):
        rv4.stretch_view(fig.add_subplot(2, n, j + 1), rec, label(r))
        rv4.surface(fig.add_subplot(2, n, n + j + 1, projection="3d"), rec, zmax)
    fig.suptitle(title, color=INK, fontsize=12, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=100, facecolor=SURFACE)
    plt.close(fig)


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
        rec = rv4.reconstruct(os.path.join(ROOT, r["ref_file"]), os.path.join(ROOT, r["file"]), cals[r["star"]])
        rows.append({"star": r["star"], "angle_deg": int(r["angle_deg"]), "repeat": int(r["repeat"]),
                     "depth_true": float(r["depth_mm"]),
                     "force_true": 0.5 * (float(r["force_lo_N"]) + float(r["force_hi_N"])),
                     "depth_mm": rec["depth_mm"], "force_N": rec["force_N"], "beyond": rec["beyond_calibration"],
                     "outline_mm2": rec["area_mm2"], "outline_pieces": rec["n_pieces"], "file": r["file"]})
        recs[r["file"]] = rec
        print(f"  {r['file']:<34} outline {rec['area_mm2']:4.0f} mm2 in {rec['n_pieces']} piece(s) | "
              f"{rec['depth_mm']:.2f} mm, {rec['force_N']:5.1f} N", flush=True)
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
              f"{s}: outline from the stretch map (top) and 3-D reconstruction (bottom) at each depth")
        turned = sorted((r for r in rows if r["star"] == s and r["angle_deg"] != 0), key=lambda r: r["angle_deg"])
        same0 = [r for r in rows if r["star"] == s and first(r) and r["depth_true"] == turned[0]["depth_true"]]
        sheet([(r, recs[r["file"]]) for r in same0 + turned], os.path.join(fig_dir, f"{s}_orientations_3d.png"),
              f"{s}: same depth, different orientations")
    sheet([(deepest[s], recs[deepest[s]["file"]]) for s in STARS], os.path.join(fig_dir, "overview_3d.png"),
          "The four stars at their deepest press: outline from the stretch map (top), 3-D reconstruction (bottom)")
    print(f"\n-> {args.out}/ (results.csv, figures/)")


if __name__ == "__main__":
    main()
