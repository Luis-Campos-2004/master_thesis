#!/usr/bin/env python3
"""
audit_temperature.py, audits the thermochromic calibration datasets.

Folder layout it expects:
    <experiment>/<run>/<temperature>/img_XX.jpg
e.g. data/raw/full_color_experiment/Heating Run/32/img_01.jpg

It answers three questions:
    1. Does the colour change monotonically with temperature?
       (if not, the same colour maps to two temperatures -- ambiguous)
    2. Do two independent sessions agree at the same temperature?
       (Heating Run vs Heating Run 2 -- if they disagree, the calibration
        does not transfer between sessions, which is the worst case)
    3. How large is the heating/cooling hysteresis?

Colour is measured in CIE-LAB inside a central disc, which avoids the LED
ring at the edge of the frame. LAB is used because Euclidean distance in it
approximates perceived colour difference (deltaE), so the numbers are
comparable across channels.

Usage from the repo root:
    python audit_temperature.py data/raw/full_color_experiment
    python audit_temperature.py data/raw/black_and_color_experiment --max-per-folder 3
"""

import argparse
import os
import re
import time

import cv2
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

IMG_EXT = {".jpg", ".jpeg", ".png"}
DISC_FRACTION = 0.45  
# Radius of the sampled disc, as a fraction of the inscribed circle. Smaller than the force audit's 0.60.
# Conservative because the temperature images might be framed differently and I hadn't seen them.



def measure_colour(path):
    """Mean LAB and RGB inside a central disc, plus exposure checks."""
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    if bgr is None:
        return None

    h, w = bgr.shape[:2]
    # [:2] because a colour image has shape (h, w, 3), drop the channel count.
    yy, xx = np.ogrid[:h, :w]
    r = np.hypot(yy - h / 2, xx - w / 2)
    mask = r < DISC_FRACTION * min(h, w) / 2

    # Same distance-map pattern as the vignette code. mask is a boolean array, True inside the disc.

    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    # OpenCV packs 8-bit LAB as L in 0..255 and a,b offset by 128.
    L = lab[..., 0][mask] * 100.0 / 255.0
    A = lab[..., 1][mask] - 128.0
    B = lab[..., 2][mask] - 128.0

    # The packing conversion, easy to get wrong. OpenCV stores 8-bit LAB with L in 0-255 (real L* is 0-100) 
    # and a,b offset by +128 so they fit in unsigned bytes. 
    # Without these three lines every number would be wrong.

    # lab[..., 0] selects channel 0 across all pixels; [mask] then keeps only the disc, returning a flat array.

    # Why LAB rather than RGB: in RGB, two colours the same numerical distance apart can look identical or wildly different. LAB is built so Euclidean distance approximates perceived difference. That's what makes ΔE meaningful.

    # L = lightness (0 black - 100 white)
    # a = green-red
    # b = blue-yellow

    b_, g_, r_ = (bgr[..., i][mask].astype(np.float32) for i in range(3))
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)[mask]

    return {
        "L": float(L.mean()), "a": float(A.mean()), "b": float(B.mean()),
        "L_std": float(L.std()),
        "chroma": float(np.sqrt(A.mean() ** 2 + B.mean() ** 2)),
        #Colour saturation -> distance from the neutral axis in the a-b plane. Chroma 0 is grey; high chroma is vivid.
        # This is the metric that shows the full-colour skin collapsing from 22 to 2 by 32 degrees.
        "R": float(r_.mean()), "G": float(g_.mean()), "B_ch": float(b_.mean()),
        "clip_high": float(100.0 * np.mean(gray >= 250)),
        "clip_low": float(100.0 * np.mean(gray <= 5)),
    }


def collect(root, max_per_folder):
    """Walk <run>/<temperature>/ and measure every image."""
    rows = []
    runs = sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)))
    # ["Cooling Run", "Cooling Run 2", "Heating Run", "Heating Run 2", ...]

    for run in runs:
        run_dir = os.path.join(root, run)
        for temp_name in sorted(os.listdir(run_dir)):
            temp_dir = os.path.join(run_dir, temp_name)
            if not os.path.isdir(temp_dir):
                continue
            # Folder name must start with a number to be a temperature.
            mt = re.match(r"^(\d+(?:\.\d+)?)", temp_name.strip())
            if not mt:
                continue
            temp = float(mt.group(1))
            # ^ anchors to the start, \d+ one or more digits, (?:\.\d+)? an optional decimal part (non-capturing)
            # "32" - 32.0, "Calibration images" - no match - skipped
            # This is what silently excluded the Calibration images folder

            files = [f for f in sorted(os.listdir(temp_dir))
                     if os.path.splitext(f)[1].lower() in IMG_EXT]
            if max_per_folder:
                files = files[:max_per_folder]

            for fn in files:
                m = measure_colour(os.path.join(temp_dir, fn))
                if m is None:
                    continue
                rows.append({"run": run, "temp_C": temp, "file": fn, **m})
            print(f"  {run:<20} {temp:>5.0f} C  ({len(files)} imgs)", flush=True)

    return pd.DataFrame(rows)


def deltaE(r1, r2):
    """CIE76 colour difference between two rows. 
    CIE76, plain Euclidean distance in LAB. Thresholds:

    delta E ~ 1 ->just noticeable
    delta E > 3 -> clearly different
    delta E > 10 -> obviously different colours

That's the scale on which your session error (1-2) is acceptable and your hysteresis (5.9-8.8) is not.

CIE76 is the oldest formula and is known to overstate differences in saturated regions. CIEDE2000 is the modern one.
Fine for comparing runs against each other; don't over-interpret absolute values.
    """
    return float(np.sqrt((r1.L - r2.L) ** 2 +
                         (r1.a - r2.a) ** 2 +
                         (r1.b - r2.b) ** 2))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--out", default=None)
    ap.add_argument("--outdir", default="figures")
    ap.add_argument("--max-per-folder", type=int, default=3,
                    help="images per temperature (default 3 of 10, for speed)")
    args = ap.parse_args()

    tag = os.path.basename(args.root.rstrip("/")).replace(" ", "_")
    out_csv = args.out or f"audit_temp_{tag}.csv"
    os.makedirs(args.outdir, exist_ok=True)

    t0 = time.time()
    df = collect(args.root, args.max_per_folder)
    if df.empty:
        raise SystemExit("No temperature folders found.")
    df.to_csv(out_csv, index=False)
    print(f"\nMeasured {len(df)} images in {time.time() - t0:.0f} s "
          f"-> {out_csv}\n")

    g = df.groupby(["run", "temp_C"]).agg(
        L=("L", "mean"), a=("a", "mean"), b=("b", "mean"),
        chroma=("chroma", "mean"), L_spread=("L", "std"),
        clip=("clip_high", "mean"), n=("L", "size"),
    ).reset_index()

    #  1. monotonicity 
    print("=" * 68)
    print("1. MONOTONICITY  (does colour change consistently with T?)")
    print("=" * 68)
    for run, sub in g.groupby("run"):
        sub = sub.sort_values("temp_C")
        d = np.diff(sub.L.values)
        frac_up = float(np.mean(d > 0))
        verdict = ("monotonic" if frac_up in (0.0, 1.0)
                   else f"{100 * max(frac_up, 1 - frac_up):.0f} % consistent")

        #d -> consecutive differences in lightness
        #frac_up -> fraction of steps that increase
        #All up (1.0) or all down (0.0) -> monotonic
        #Otherwise report whichever direction dominates

        #Why monotonicity matters: you need to invert the curve -> go from colour back to temperature. 
        # If L* goes up then down, the same colour corresponds to two temperatures and the inversion is ambiguous.
        print(f"  {run:<22} L: {sub.L.iloc[0]:6.2f} -> {sub.L.iloc[-1]:6.2f}"
              f"   range {sub.L.max() - sub.L.min():5.2f}   {verdict}")

    # 2. session reproducibility 
    print("\n" + "=" * 68)
    print("2. SESSION REPRODUCIBILITY  (does run 1 match run 2?)")
    print("=" * 68)
    runs = sorted(g.run.unique())
    pairs = []
    for r in runs:
        if r.endswith(" 2") and r[:-2] in runs:
            pairs.append((r[:-2], r))
    if not pairs:
        print("  (no paired runs found)")
    for r1, r2 in pairs:
        s1 = g[g.run == r1].set_index("temp_C")
        s2 = g[g.run == r2].set_index("temp_C")
        common = sorted(set(s1.index) & set(s2.index))
        if not common:
            continue
        des = [deltaE(s1.loc[t], s2.loc[t]) for t in common]
        print(f"  {r1}  vs  {r2}")
        print(f"    mean dE = {np.mean(des):5.2f}   max dE = {np.max(des):5.2f}"
              f"   (at {common[int(np.argmax(des))]:.0f} C)")
        # Convert the disagreement into an equivalent temperature error.
        s1s = s1.loc[common].sort_index()
        """
        np.gradient(y, x) -> derivative using central differences, respecting uneven x-spacing (your 1 degree then 5 degree steps)
        np.where(slope < 1e-6, np.nan, slope) -> blanks near-zero slopes to avoid division explosions
        delta E + (delta L per degree) = degrees

        This is the weakest number in the script. Where sensitivity is near zero -> above 33 degrees in the full-colour skin,
         
        a small delta E divides by a tiny slope and produces a huge apparent error. 
        
        The median mitigates it but doesn't remove it.

        So "4.7 degrees" is inflated by the dead region. If you want a defensible number, restrict to 24-33 degrees.
         
        Otherwise quote it with the caveat.

        The black-on-colour figures (0.4-1.4 degrees) are more trustworthy, because that skin responds across the whole range.


        """

        slope = np.abs(np.gradient(s1s.L.values, s1s.index.values))
        slope = np.where(slope < 1e-6, np.nan, slope)


        err_C = np.nanmedian(np.array(des) / slope)
        print(f"    => roughly {err_C:.1f} C of apparent temperature error")
        if np.mean(des) > 3:
            print("    ^ above the just-noticeable threshold: the calibration "
                  "does NOT transfer cleanly between sessions")

    # 3. hysteresis 
    print("\n" + "=" * 68)
    print("3. HYSTERESIS  (heating vs cooling at the same temperature)")
    print("=" * 68)
    heat = [r for r in runs if "heat" in r.lower()]
    cool = [r for r in runs if "cool" in r.lower()]
    for h in heat:
        for c in cool:
            # pair run N with run N (both plain, or both '2')
            if h.endswith(" 2") != c.endswith(" 2"):
                continue
            # Comparing two booleans with != is XOR -> skip unless both are run 1 or both are run 2. 
            # Prevents comparing Heating Run against Cooling Run 2, which would confound hysteresis with session drift.

            # The key comparison to state out loud: hysteresis (5.9-8.8) against session reproducibility (1-2). 
            #Roughly five times larger. Two independent sessions agree far better than heating agrees with cooling -> 
            # -> so the discrepancy is physical, not experimental noise.
            s1 = g[g.run == h].set_index("temp_C")
            s2 = g[g.run == c].set_index("temp_C")
            common = sorted(set(s1.index) & set(s2.index))
            if not common:
                continue
            des = [deltaE(s1.loc[t], s2.loc[t]) for t in common]
            worst = common[int(np.argmax(des))]
            print(f"  {h}  vs  {c}")
            print(f"    mean dE = {np.mean(des):5.2f}   max dE = "
                  f"{np.max(des):5.2f}  (at {worst:.0f} C)")

    # figures 
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    for run, sub in g.groupby("run"):
        sub = sub.sort_values("temp_C")
        style = "--" if run.endswith(" 2") else "-"
        axes[0].plot(sub.temp_C, sub.L, style, marker="o", ms=3, lw=1.2,
                     label=run)
        axes[1].plot(sub.temp_C, sub.chroma, style, marker="o", ms=3, lw=1.2,
                     label=run)
    axes[0].set_xlabel("bed temperature (C)")
    axes[0].set_ylabel("lightness L*")
    axes[0].set_title("Lightness vs temperature")
    axes[1].set_xlabel("bed temperature (C)")
    axes[1].set_ylabel("chroma")
    axes[1].set_title("Colour saturation vs temperature")
    for ax in axes:
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7)
    fig.suptitle(tag.replace("_", " "))
    fig.tight_layout()
    p = os.path.join(args.outdir, f"temp_{tag}_curves.png")
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"\n  wrote {p}")

    # sensitivity: dL per degree, shows where the useful range is
    fig, ax = plt.subplots(figsize=(7, 4.4))
    for run, sub in g.groupby("run"):
        sub = sub.sort_values("temp_C")
        if len(sub) < 3:
            continue
        mid = 0.5 * (sub.temp_C.values[1:] + sub.temp_C.values[:-1])
        dL = np.abs(np.diff(sub.L.values) / np.diff(sub.temp_C.values))
        # Same discrete-derivative pattern as fig_sensitivity in plot_force.py. 
        # This produced your clearest result: all response between 24-32 degrees,
        # essentially zero above 33 degrees for the full-colour skin.
    ax.plot(mid, dL, marker="o", ms=3, lw=1.2, label=run)
    ax.set_xlabel("bed temperature (C)")
    ax.set_ylabel("|dL*| per degree")
    ax.set_title("Where the pigments actually respond")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    p2 = os.path.join(args.outdir, f"temp_{tag}_sensitivity.png")
    fig.savefig(p2, dpi=150)
    plt.close(fig)
    print(f"  wrote {p2}")


if __name__ == "__main__":
    main()