#!/usr/bin/env python3
"""
plot_force.py, turns the force audit into the figures for the meeting.

Reads:
    audit_force.csv                                    (from audit_images_v3.py)
    data/processed/csv_files/force_vs_mean_width_ratio_frequency.csv  (Liam's)

Produces in figures/:
    force_period_vs_load.png     period vs force, with the saturation visible
    force_linearity.png          Liam's linear model tested on his own points
    force_sensitivity.png        how much period moves per newton, vs force
    force_noise.png              within-level scatter vs between-level steps

Usage from the repo root:
    python plot_force.py
    python plot_force.py --audit audit_force.csv --outdir figures
"""

import argparse
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")            # no GUI needed; write files directly
import matplotlib.pyplot as plt

CAL_CSV = "data/processed/csv_files/force_vs_mean_width_ratio_frequency.csv"


def load_audit(path):
    """Read the audit CSV and reduce it to one row per force level."""
    df = pd.read_csv(path)

    # Turn folder names like '12N' into numbers; 'reference' becomes NaN.
    def to_force(name):
        try:
            return float(str(name).strip().rstrip("Nn"))
        except ValueError:
            return np.nan

    df["force_N"] = df["folder"].map(to_force)
    # .map() applies the function to every row, creating a new numeric column.

    ref = df[df["force_N"].isna()]                     # 5 reference rows
    loaded = df[df["force_N"].notna()].copy()  # 80 loaded row
    # two different numbers. audit_images_v3.py computed the signal over all folders including the reference, 3.418 %.
    # Here the reference is excluded, 2.631 %.
    #Both correct, measuring different things. Quote 2.631 % , "force resolution over 3-48 N" shouldn't include an unloaded image.

    g = loaded.groupby("force_N").agg(
        period_mean=("period_px", "mean"),
        period_std=("period_px", "std"),
        sharp_mean=("sharpness", "mean"),
        snr_mean=("carrier_snr", "mean"),
        n=("period_px", "size"),
    ).reset_index().sort_values("force_N")

    # groupby("force_N") -> buckets the 80 rows into 16 groups of 5
    # agg(new_name=(column, function)) -> named aggregation. period_mean 
    # comes from averaging period_px within each group
    # reset_index() turns the group key back into a normal column
    # sort_values guarantees ascending force order

    ref_period = ref["period_px"].mean() if len(ref) else np.nan
    return g, ref_period


def fig_period_vs_load(g, ref_period, outdir):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.errorbar(g.force_N, g.period_mean, yerr=g.period_std,
                fmt="o-", capsize=3, lw=1.3, ms=4, label="measured")

    # yerr draws the vertical error bars -> the within-level scatter
    # fmt="o-" -> circles joined by a line
    # capsize=3 -> the little horizontal caps

    if np.isfinite(ref_period):
        ax.axhline(ref_period, ls="--", lw=1, color="0.5",
                   label=f"reference ({ref_period:.3f} px)")
        # Horizontal dashed line at the reference. Visually, notice how far below the 3 N point it sits, that's the 0.19 px anomaly.

    # Straight line through the first four points, extended: makes the
    # departure from linearity obvious without fitting anything fancy.

    k = 4. # k = 4 is arbitrary, chosen by me to make the departure visible. It's a visual aid, not for a fitted model.
    b, a = np.polyfit(g.force_N[:k], g.period_mean[:k], 1)
    xs = np.linspace(g.force_N.min(), g.force_N.max(), 50)
    ax.plot(xs, a + b * xs, ls=":", lw=1.2, color="C3",
            label="linear trend of the first 4 points")

    ax.set_xlabel("applied force (N)")
    ax.set_ylabel("stripe period (px)")
    ax.set_title("Stripe period vs load, response flattens at high force")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(outdir, "force_period_vs_load.png")
    fig.savefig(p, dpi=150)
    plt.close(fig)
    return p


def fig_linearity(outdir):
    """Invert Liam's own linear fit on his own calibration points."""
    if not os.path.exists(CAL_CSV):
        print(f"  (skipped force_linearity: {CAL_CSV} not found)")
        return None

    cal = pd.read_csv(CAL_CSV)
    F = cal["force_N"].values
    R = cal["mean_width_deformation_ratio"].values

    # .values converts a pandas Series to a plain numpy array.

    b, a = np.polyfit(F, R, 1)          # R = a + b*F
    pred_F = (R - a) / b                # invert the model
    err = pred_F - F

    # Fit Liam's linear model to Liam's own calibration points
    # Invert it, the pipeline goes ratio, force, so this is what it actually does
    # Compare against the known applied force

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(F, err, width=2.0, color=["C3" if abs(e) > 1 else "C0" for e in err])
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xlabel("applied force (N)")
    ax.set_ylabel("predicted - actual (N)")
    ax.set_title("Linear model tested on its own calibration points\n"
                 f"(arch shape = fitting a straight line to a curve; "
                 f"max error {np.abs(err).max():.1f} N)")
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    p = os.path.join(outdir, "force_linearity.png")
    fig.savefig(p, dpi=150)
    plt.close(fig)
    return p


def fig_sensitivity(g, outdir):
    """Local slope: how many px of period change per newton."""
    F = g.force_N.values
    P = g.period_mean.values
    mid = 0.5 * (F[1:] + F[:-1])
    sens = np.diff(P) / np.diff(F)

    # F[1:] drops the first element, F[:-1] drops the last, averaging them gives midpoints between consecutive levels
    # np.diff gives consecutive differences, so (delta P/delta de F) is the local slope, a discrete derivative
    # 16 points in, 15 out

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(mid, sens * 1000, "o-", lw=1.3, ms=4)
    ax.set_xlabel("force (N)")
    ax.set_ylabel("sensitivity (milli-px per N)")
    ax.set_title("Sensitivity halves across the range — the sensor saturates")
    ax.grid(alpha=0.3)
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    p = os.path.join(outdir, "force_sensitivity.png")
    fig.savefig(p, dpi=150)
    plt.close(fig)
    return p


def fig_noise(g, outdir):
    """Step between consecutive levels vs the scatter within a level."""
    F = g.force_N.values
    P = g.period_mean.values
    S = g.period_std.values

    steps = np.abs(np.diff(P))
    mid = 0.5 * (F[1:] + F[:-1])
    noise3 = 3.0 * 0.5 * (S[1:] + S[:-1])      # 3-sigma band

    # steps, how much the period changes between consecutive levels. The signal
    # noise3 -> 3*sigma, with sigma averaged across the two levels being compared. The noise
    # Both have 15 entries, plotted against mid

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(mid, steps, "o-", lw=1.3, ms=4, label="step between levels")
    ax.plot(mid, noise3, "s--", lw=1.3, ms=4, color="C3",
            label="3x within-level scatter")
    ax.fill_between(mid, 0, noise3, color="C3", alpha=0.12)
    # Shades the region under the noise curve. Where the blue line enters that shaded band, consecutive levels stop being distinguishable.
    ax.set_xlabel("force (N)")
    ax.set_ylabel("period change (px)")
    ax.set_title("Where the signal drops into the noise")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(outdir, "force_noise.png")
    fig.savefig(p, dpi=150)
    plt.close(fig)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", default="audit_force.csv")
    ap.add_argument("--outdir", default="figures")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    g, ref_period = load_audit(args.audit)

    print(f"{len(g)} force levels, reference period = {ref_period:.4f} px\n")

    # console summary, so the numbers are quotable 
    sig = 100 * (g.period_mean.max() - g.period_mean.min()) / g.period_mean.min()
    noi = 100 * (g.period_std / g.period_mean).mean()
    # sig,  total range as a percentage. Loaded folders only
    # noi, mean CV. Note: mean of the ratios, not ratio of the means
    print(f"signal (period range)      : {sig:.3f} %")
    print(f"noise  (mean within-level) : {noi:.4f} %")
    print(f"signal / noise             : {sig / noi:.0f}")
    print(f"distinguishable levels (3s): {sig / (3 * noi):.0f}")

    first_step = g.period_mean.iloc[0] - ref_period
    print(f"\nreference -> {g.force_N.iloc[0]:.0f}N jump : {first_step:+.4f} px")
    print(f"typical later step          : "
          f"{np.median(np.diff(g.period_mean)):+.4f} px")
    
    if abs(first_step) > 2 * abs(np.median(np.diff(g.period_mean))):
        print("  ^ the first step is anomalously large — check the reference set")

    # An automatic check. Median rather than mean for the typical step, so one outlier can't skew the comparison.
    # Your data: 0.1916 vs 0.0373, so it fires

    last = g.period_mean.iloc[-1] - g.period_mean.iloc[-2]
    last_noise = g.period_std.iloc[-1]
    print(f"\nlast step ({g.force_N.iloc[-2]:.0f}->{g.force_N.iloc[-1]:.0f}N): "
          f"{last:+.4f} px   vs within-level sigma {last_noise:.4f} px")
    if abs(last) < 3 * last_noise:
        print("  ^ below 3 sigma: these two levels are NOT distinguishable")
    # Same 3*sigma convention as everywhere else. Fires on 45-48 N.

    print()
    for fn in (fig_period_vs_load(g, ref_period, args.outdir),
               fig_linearity(args.outdir),
               fig_sensitivity(g, args.outdir),
               fig_noise(g, args.outdir)):
    # All four functions run first (a tuple evaluates all its elements), then the loop prints. 
    # if fn skips fig_linearity if it returned None because the calibration CSV was missing.
        if fn:
            print(f"  wrote {fn}")


if __name__ == "__main__":
    main()