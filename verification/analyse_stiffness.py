#!/usr/bin/env python3
"""
analyse_stiffness.py — The four pieces of different stiffness (P1-P4).

  1. True stiffness of each piece: MARK-10 force-distance runs of the piece
     alone (data/raw/stiffness_pieces/mark10_runs, 5 runs per piece). Contact =
     last sample below CONTACT_N before the maximum; stiffness = slope of force
     against compression between FIT_LO and FIT_HI newton.
  2. The pieces pressed on the skin (photos + log sheet): MARK-10 force and the
     stripe stretch measured by the sensor (strain_map.py), against the travel.

Writes CSVs, summary.md and figures to results/stiffness/.
Usage from the repo root:
    python verification/analyse_stiffness.py
"""

import argparse
import csv
import glob
import io
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import tactile.strain_map as sm              # noqa: E402

ROOT = "data/raw/stiffness_pieces"
OUT = "results/stiffness"
CONTACT_N = 1.0            # load below this = not yet touching (sensor resolution 0.5 N)
FIT_LO, FIT_HI = 5.0, 20.0  # force range of the stiffness fit (N)
COMMON_MM = 3.0            # travel range that every piece has on the skin
PIECES = ["P1", "P2", "P3", "P4"]
COLOUR = dict(zip(PIECES, ["#1baf7a", "#2a78d6", "#eb6834", "#eda100"]))
MARKER = dict(zip(PIECES, ["o", "s", "^", "D"]))
END_DY = {"P1": -6, "P2": 6}                      # P1 and P2 end at almost the same signal
POINT_OFFSET = {"P1": (8, 6), "P2": (8, 6), "P3": (8, 6), "P4": (-22, 6)}
INK, INK2, RULE, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"


def read_run(path):
    """Load (N) and compression (mm, positive down) of one MARK-10 export."""
    lines = open(path, encoding="latin-1").read().replace("\r", "").split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith("Reading"))
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])), sep="\t").dropna(axis=1, how="all")
    df.columns = ["reading", "load", "dist", "time"]
    load = df["load"].rolling(15, center=True, min_periods=1).median().to_numpy()
    travel = -df["dist"].to_numpy()
    i_max = int(np.argmax(load))
    i_touch = int(np.nonzero(load[:i_max] < CONTACT_N)[0][-1])
    return travel[i_touch:i_max + 1] - travel[i_touch], load[i_touch:i_max + 1]


def mark10_stiffness():
    rows, curves = [], {}
    grid = np.arange(0, 8.0, 0.01)
    for piece in PIECES:
        runs = []
        for path in sorted(glob.glob(os.path.join(ROOT, "mark10_runs", f"*_{piece}_run*.csv"))):
            x, y = read_run(path)
            fit = (y >= FIT_LO) & (y <= FIT_HI)
            k = float(np.polyfit(x[fit], y[fit], 1)[0])
            rows.append({"piece": piece, "run": int(re.search(r"run(\d+)", path).group(1)),
                         "stiffness_N_per_mm": k, "max_force_N": float(y.max()),
                         "compression_at_max_mm": float(x[-1]),
                         "compression_at_10N_mm": float(x[np.argmax(y >= 10)]),
                         "compression_at_20N_mm": float(x[np.argmax(y >= 20)])})
            runs.append(np.interp(grid, x, y, right=np.nan))
        runs = np.array(runs)
        ok = np.isfinite(runs).all(axis=0)
        curves[piece] = (grid[ok], runs[:, ok].mean(axis=0), runs[:, ok].std(axis=0))
    return rows, curves


def on_skin():
    with open(os.path.join(ROOT, "log_sheet.csv"), newline="", encoding="utf-8") as fh:
        log = list(csv.DictReader(fh))
    rows = []
    for r in log:
        m = sm.measure(os.path.join(ROOT, r["ref_file"]), os.path.join(ROOT, r["file"]))
        lo, hi = float(r["force_lo_N"]), float(r["force_hi_N"])
        rows.append({"piece": r["piece"], "travel_mm": float(r["depth_mm"]), "force_N": 0.5 * (lo + hi),
                     "force_lo_N": lo, "force_hi_N": hi, "peak_stretch": m["peak"],
                     "region_mm2": m["area_mm2"], "stretch_integral_mm2": m["integral"], "file": r["file"]})
        print(f"  {r['file']:<28} {rows[-1]['force_N']:5.2f} N  peak stretch {m['peak']:.4f}  "
              f"region {m['area_mm2']:.0f} mm2", flush=True)
    return rows


def style(ax, xlabel, ylabel, title):
    ax.set_xlabel(xlabel, color=INK)
    ax.set_ylabel(ylabel, color=INK)
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    ax.grid(color=RULE, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def fig_mark10(curves, stats, path):
    fig, ax = plt.subplots(figsize=(8.2, 5.2), facecolor=SURFACE)
    for piece in PIECES:
        x, mean, sd = curves[piece]
        ax.fill_between(x, mean - sd, mean + sd, color=COLOUR[piece], alpha=0.25, lw=0)
        k, ks = stats[piece]
        ax.plot(x, mean, color=COLOUR[piece], lw=2, label=f"{piece}: {k:.1f} ± {ks:.2f} N/mm")
        ax.annotate(piece, (x[-1], mean[-1]), xytext=(0, 6), textcoords="offset points", ha="center",
                    color=INK, fontsize=10)
    ax.set_xlim(0, max(c[0][-1] for c in curves.values()) * 1.05)
    ax.set_ylim(0, 24.5)
    ax.legend(frameon=False, loc="lower right", title=f"stiffness ({FIT_LO:.0f}–{FIT_HI:.0f} N)")
    style(ax, "compression of the piece (mm)", "force (N)",
          "Pieces alone on the MARK-10: mean of 5 runs (band = ± 1 sd)")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def fig_on_skin(rows, path):
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.0), facecolor=SURFACE)
    for piece in PIECES:
        r = [x for x in rows if x["piece"] == piece]
        t = [x["travel_mm"] for x in r]
        f = np.array([x["force_N"] for x in r])
        err = [f - [x["force_lo_N"] for x in r], [x["force_hi_N"] for x in r] - f]
        axes[0].errorbar(t, f, yerr=err, color=COLOUR[piece], marker=MARKER[piece], ms=6, lw=1.6,
                         mec=SURFACE, mew=1.0, capsize=2, label=piece)
        axes[1].plot(t, [x["peak_stretch"] for x in r], color=COLOUR[piece], marker=MARKER[piece],
                     ms=6, lw=1.6, mec=SURFACE, mew=1.0, label=piece)
        for ax, y, dy in ((axes[0], f[-1], 0), (axes[1], r[-1]["peak_stretch"], END_DY.get(piece, 0))):
            ax.annotate(piece, (t[-1], y), xytext=(7, dy), textcoords="offset points", va="center",
                        color=INK, fontsize=9)
    style(axes[0], "travel after touch (mm)", "MARK-10 force (N)", "On the skin: force")
    style(axes[1], "travel after touch (mm)", "peak stripe stretch (sensor)", "On the skin: sensor signal")
    for ax in axes:
        ax.set_xlim(0, 7.7)
        ax.set_ylim(0, None)
        ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def fig_vs_stiffness(table, path):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), facecolor=SURFACE)
    panels = (("signal_per_mm", "sensor signal per mm of travel", "Sensor signal per mm"),
              ("skin_force_per_mm", "MARK-10 force per mm of travel (N/mm)", "Force per mm on the skin"),
              ("stretch_per_N", "sensor signal per newton", "Sensor signal per newton"))
    for ax, (key, ylabel, title) in zip(axes, panels):
        for piece in PIECES:
            t = table[piece]
            ax.errorbar(t["stiffness"], t[key], xerr=t["stiffness_sd"], color=COLOUR[piece],
                        marker=MARKER[piece], ms=9, mec=SURFACE, mew=1.2, capsize=2)
            ax.annotate(piece, (t["stiffness"], t[key]), xytext=POINT_OFFSET[piece],
                        textcoords="offset points", color=INK, fontsize=10)
        ax.set_xlim(0, 36)
        ax.set_ylim(0, 1.25 * max(table[p][key] for p in PIECES))
        style(ax, "true stiffness of the piece (N/mm, MARK-10)", ylabel, title)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


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

    print("pieces alone (MARK-10 runs)")
    runs, curves = mark10_stiffness()
    write_csv(os.path.join(args.out, "mark10_stiffness_runs.csv"), runs)
    stats = {}
    for piece in PIECES:
        k = np.array([r["stiffness_N_per_mm"] for r in runs if r["piece"] == piece])
        stats[piece] = (float(k.mean()), float(k.std(ddof=1)))
        print(f"  {piece}: {len(k)} runs, stiffness {k.mean():.2f} ± {k.std(ddof=1):.2f} N/mm "
              f"(min {k.min():.2f}, max {k.max():.2f})")

    print("\npieces on the skin (photos)")
    rows = on_skin()
    write_csv(os.path.join(args.out, "pieces_on_skin.csv"), rows)

    table = {}
    for piece in PIECES:
        r = [x for x in rows if x["piece"] == piece and x["travel_mm"] <= COMMON_MM]
        t = np.array([x["travel_mm"] for x in r])
        allr = [x for x in rows if x["piece"] == piece]
        force = np.array([x["force_N"] for x in allr])
        peak = np.array([x["peak_stretch"] for x in allr])
        table[piece] = {
            "stiffness": stats[piece][0], "stiffness_sd": stats[piece][1],
            "signal_per_mm": float(np.polyfit(t, [x["peak_stretch"] for x in r], 1)[0]),
            "skin_force_per_mm": float(np.polyfit(t, [x["force_N"] for x in r], 1)[0]),
            "stretch_per_N": float((force * peak).sum() / (force ** 2).sum()),
            "max_travel": max(x["travel_mm"] for x in allr), "n_photos": len(allr)}

    fig_mark10(curves, stats, os.path.join(fig_dir, "piece_stiffness_mark10.png"))
    fig_on_skin(rows, os.path.join(fig_dir, "on_skin_force_and_signal.png"))
    fig_vs_stiffness(table, os.path.join(fig_dir, "signal_vs_stiffness.png"))

    lines = ["# Rigidez das quatro peças (P1–P4)", "",
             "## Rigidez real (peça sozinha na MARK-10, 5 corridas por peça)", "",
             f"Rigidez = declive da força contra a compressão entre {FIT_LO:.0f} e {FIT_HI:.0f} N.", "",
             "| peça | rigidez (N/mm), média ± dp | compressão a 10 N (mm) | compressão a 20 N (mm) |", "|---|---|---|---|"]
    for piece in PIECES:
        r = [x for x in runs if x["piece"] == piece]
        lines.append(f"| {piece} | {stats[piece][0]:.2f} ± {stats[piece][1]:.2f} | "
                     f"{np.mean([x['compression_at_10N_mm'] for x in r]):.2f} | "
                     f"{np.mean([x['compression_at_20N_mm'] for x in r]):.2f} |")
    lines += ["", "## Na pele (fotos + folha de registo)", "",
              f"Declives ajustados entre 0.5 e {COMMON_MM:.1f} mm de curso, a gama comum às quatro peças. "
              "O sinal por newton é ajustado em todos os pontos de cada peça.", "",
              "| peça | fotos | curso máximo (mm) | força por mm (N/mm) | sinal do sensor por mm | sinal do sensor por N |",
              "|---|---|---|---|---|---|"]
    for piece in PIECES:
        t = table[piece]
        lines.append(f"| {piece} | {t['n_photos']} | {t['max_travel']:.1f} | {t['skin_force_per_mm']:.1f} | "
                     f"{t['signal_per_mm']:.4f} | {t['stretch_per_N']:.5f} |")
    with open(os.path.join(args.out, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))
    print(f"\n-> {args.out}/ (summary.md, CSVs, figures/)")


if __name__ == "__main__":
    main()
