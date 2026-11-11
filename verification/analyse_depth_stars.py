#!/usr/bin/env python3
"""
analyse_depth_stars.py — The four stars (S1-S4) pressed to known depths on the
MARK-10 (data/raw/depth_stars, depth and force from the log sheet).

For every pressed photo the stripe stretch is measured against the reference of
its own series (strain_map.py). The script then answers:

  1. Does the sensor signal follow the depth? (peak stretch against depth)
  2. Is it repeatable (S1 pressed twice) and independent of the orientation
     (0, 45 and 90 degrees)?
  3. Can depth be read from the signal with a calibration made on the same
     star, and with one made on the other stars (leave one star out)?
  4. Can force be read from the stretch summed over the membrane, calibrated on
     the other stars (leave one star out)?

Calibrations are y = a x + b x^2 (no offset: no stretch, no press).
Writes CSVs, summary.md and figures to results/depth_stars/.
Usage from the repo root:
    python verification/analyse_depth_stars.py
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
import tactile.strain_map as sm              # noqa: E402

ROOT = "data/raw/depth_stars"
OUT = "results/depth_stars"
STARS = ["S1", "S2", "S3", "S4"]
COLOUR = dict(zip(STARS, ["#1baf7a", "#2a78d6", "#eb6834", "#eda100"]))
MARKER = dict(zip(STARS, ["o", "s", "^", "D"]))
INK, INK2, RULE, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"
MAP_LIMIT = 0.06          # colour scale of the stretch maps (+-)
MAP_HALF_MM = 26.0        # half-width of the window shown in the stretch maps


def quad_fit(x, y):
    """y = a x + b x^2 through the origin."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    coef, *_ = np.linalg.lstsq(np.c_[x, x ** 2], y, rcond=None)
    return coef


def quad(coef, x):
    x = np.asarray(x, float)
    return coef[0] * x + coef[1] * x ** 2


def measure_all():
    with open(os.path.join(ROOT, "log_sheet.csv"), newline="", encoding="utf-8") as fh:
        log = [r for r in csv.DictReader(fh)]
    rows, maps, missing = [], {}, []
    for r in log:
        if not r["file"]:
            missing.append(r)
            continue
        m = sm.measure(os.path.join(ROOT, r["ref_file"]), os.path.join(ROOT, r["file"]))
        lo, hi = float(r["force_lo_N"]), float(r["force_hi_N"])
        row = {"star": r["star"], "angle_deg": int(r["angle_deg"]), "repeat": int(r["repeat"]),
               "depth_mm": float(r["depth_mm"]), "force_N": 0.5 * (lo + hi), "force_lo_N": lo, "force_hi_N": hi,
               "peak_stretch": m["peak"], "stretch_integral_mm2": m["integral"],
               "region_mm2": m["area_mm2"], "file": r["file"]}
        rows.append(row)
        fl = m["fields"]
        maps[r["file"]] = (np.where(fl["inside"], m["stretch_fine"], np.nan), fl["px_per_mm"], m["region"])
        print(f"  {r['file']:<34} {row['depth_mm']:.1f} mm {row['force_N']:5.2f} N | peak stretch "
              f"{m['peak']:.4f}  integral {m['integral']:6.2f} mm2  region {m['area_mm2']:4.0f} mm2", flush=True)
    return rows, maps, missing


def series(rows, star, repeat=1, angle=0):
    return sorted((r for r in rows if r["star"] == star and r["repeat"] == repeat and r["angle_deg"] == angle),
                  key=lambda r: r["depth_mm"])


# --- analyses --------------------------------------------------------------------
def slopes(rows):
    out = {}
    for s in STARS:
        r = series(rows, s)
        d = np.array([x["depth_mm"] for x in r])
        p = np.array([x["peak_stretch"] for x in r])
        k, c = np.polyfit(d, p, 1)
        res = p - (k * d + c)
        out[s] = {"slope": float(k), "r2": float(1 - (res ** 2).sum() / ((p - p.mean()) ** 2).sum()),
                  "n": len(r), "max_depth": float(d.max())}
    return out


def zero_offset(rows):
    """How far S1's second series is shifted in depth against the first (signal and force)."""
    r1, r2 = series(rows, "S1", 1), series(rows, "S1", 2)
    d1 = np.array([x["depth_mm"] for x in r1])
    out = {}
    for key in ("peak_stretch", "force_N", "stretch_integral_mm2"):
        v1 = np.array([x[key] for x in r1])
        shifts = [float(np.interp(x[key], v1, d1)) - x["depth_mm"] for x in r2 if v1[0] <= x[key] <= v1[-1]]
        out[key] = (float(np.mean(shifts)), float(np.std(shifts)), len(shifts))
    return out


def orientation(rows):
    out = []
    for s in STARS:
        turned = [r for r in rows if r["star"] == s and r["angle_deg"] != 0]
        if not turned:
            continue
        depth = turned[0]["depth_mm"]
        same = [dict(r, integral_per_N=r["stretch_integral_mm2"] / r["force_N"])
                for r in rows if r["star"] == s and r["depth_mm"] == depth]
        for key in ("peak_stretch", "stretch_integral_mm2", "force_N", "integral_per_N"):
            v = np.array([r[key] for r in same])
            out.append({"star": s, "depth_mm": depth, "signal": key, "n": len(v),
                        "values": " / ".join(f"{r['angle_deg']}°{'' if r['repeat'] == 1 else ' (2.ª)'}: "
                                             f"{r[key]:.3g}" for r in same),
                        "spread_pct": float(100 * (v.max() - v.min()) / v.mean())})
    return out


def predictions(rows):
    """Depth and force of every photo, from calibrations that never saw that star."""
    pred = []
    for s in STARS:
        train = [r for r in rows if r["star"] != s]
        cd = quad_fit([r["peak_stretch"] for r in train], [r["depth_mm"] for r in train])
        cf = quad_fit([r["stretch_integral_mm2"] for r in train], [r["force_N"] for r in train])
        for r in (x for x in rows if x["star"] == s):
            pred.append({**{k: r[k] for k in ("star", "angle_deg", "repeat", "depth_mm", "force_N", "file")},
                         "depth_pred_other_stars": float(quad(cd, r["peak_stretch"])),
                         "force_pred_other_stars": float(quad(cf, r["stretch_integral_mm2"]))})
    own = quad_fit([r["peak_stretch"] for r in series(rows, "S1", 1)],
                   [r["depth_mm"] for r in series(rows, "S1", 1)])
    for p in pred:
        r = next(x for x in rows if x["file"] == p["file"])
        first = p["star"] == "S1" and p["repeat"] == 1 and p["angle_deg"] == 0
        p["depth_pred_same_star"] = float(quad(own, r["peak_stretch"])) if p["star"] == "S1" and not first else ""
    return pred


# --- figures ---------------------------------------------------------------------
def style(ax, xlabel, ylabel, title):
    ax.set_xlabel(xlabel, color=INK)
    ax.set_ylabel(ylabel, color=INK)
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    ax.grid(color=RULE, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def show_map(ax, entry, title):
    smap, pxmm, _ = entry
    n = smap.shape[0]
    half = n / 2 / pxmm
    im = ax.imshow(smap, cmap="RdBu_r", vmin=-MAP_LIMIT, vmax=MAP_LIMIT, extent=[-half, half, half, -half])
    ax.set_xlim(-MAP_HALF_MM, MAP_HALF_MM)
    ax.set_ylim(MAP_HALF_MM, -MAP_HALF_MM)
    ax.set_title(title, fontsize=8.5, color=INK)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_facecolor("#eeeeea")
    return im


def fig_maps(rows, maps, path):
    lines = [("S1", 1), ("S1", 2), ("S2", 1), ("S3", 1), ("S4", 1)]
    depths = sorted({r["depth_mm"] for r in rows})
    fig, axes = plt.subplots(len(lines), len(depths), figsize=(1.95 * len(depths) + 1.2, 2.1 * len(lines) + 0.7),
                             facecolor=SURFACE, squeeze=False)
    im = None
    for i, (s, rep) in enumerate(lines):
        got = {r["depth_mm"]: r for r in series(rows, s, rep)}
        for j, d in enumerate(depths):
            ax = axes[i, j]
            if d in got:
                r = got[d]
                im = show_map(ax, maps[r["file"]], f"{d:.1f} mm · {r['force_N']:.1f} N")
            else:
                ax.axis("off")
        axes[i, 0].set_ylabel(f"{s}" + (" (2nd time)" if rep == 2 else ""), color=INK, fontsize=10)
    fig.suptitle(f"Stripe stretch seen by the sensor, each star at each depth (window {2 * MAP_HALF_MM:.0f} mm wide)",
                 color=INK, fontsize=12, fontweight="bold", x=0.02, ha="left")
    fig.subplots_adjust(left=0.035, right=0.90, top=0.93, bottom=0.02, wspace=0.05, hspace=0.18)
    cb = fig.colorbar(im, cax=fig.add_axes([0.915, 0.25, 0.012, 0.5]))
    cb.set_label("stretch (period ratio − 1)", color=INK)
    fig.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(fig)


def fig_orientation(rows, maps, path):
    fig, axes = plt.subplots(len(STARS), 3, figsize=(7.6, 2.45 * len(STARS) + 0.6), facecolor=SURFACE)
    im = None
    for i, s in enumerate(STARS):
        turned = [r for r in rows if r["star"] == s and r["angle_deg"] != 0]
        depth = turned[0]["depth_mm"]
        for j, ang in enumerate((0, 45, 90)):
            ax = axes[i, j]
            cand = [r for r in rows if r["star"] == s and r["angle_deg"] == ang and r["depth_mm"] == depth]
            if cand:
                r = cand[-1]
                im = show_map(ax, maps[r["file"]], f"{ang}° · {depth:.1f} mm · {r['force_N']:.1f} N")
            else:
                ax.text(0.5, 0.5, "photo missing", ha="center", va="center", color=INK2, transform=ax.transAxes)
                ax.set_xticks([])
                ax.set_yticks([])
                ax.set_title(f"{ang}°", fontsize=8.5, color=INK)
        axes[i, 0].set_ylabel(s, color=INK, fontsize=10)
    fig.suptitle("Same star, same depth, three orientations", color=INK, fontsize=12, fontweight="bold",
                 x=0.03, ha="left")
    fig.subplots_adjust(left=0.06, right=0.80, top=0.93, bottom=0.02, wspace=0.05, hspace=0.18)
    cb = fig.colorbar(im, cax=fig.add_axes([0.83, 0.3, 0.02, 0.4]))
    cb.set_label("stretch (period ratio − 1)", color=INK)
    fig.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(fig)


def fig_signals(rows, path):
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.0), facecolor=SURFACE)
    panels = (("depth_mm", "peak_stretch", "depth after touch (mm)", "peak stripe stretch (sensor)",
               "Sensor signal against depth"),
              ("depth_mm", "force_N", "depth after touch (mm)", "MARK-10 force (N)", "Force against depth"),
              ("stretch_integral_mm2", "force_N", "stretch summed over the membrane (mm²)", "MARK-10 force (N)",
               "Force against summed stretch"))
    for ax, (kx, ky, xl, yl, title) in zip(axes, panels):
        for s in STARS:
            r = series(rows, s)
            ax.plot([x[kx] for x in r], [x[ky] for x in r], color=COLOUR[s], marker=MARKER[s], ms=6.5, lw=1.7,
                    mec=SURFACE, mew=1.0, label=s)
            ax.annotate(s, (r[-1][kx], r[-1][ky]), xytext=(7, 0), textcoords="offset points", va="center",
                        color=INK, fontsize=9)
        r2 = series(rows, "S1", 2)
        ax.plot([x[kx] for x in r2], [x[ky] for x in r2], color=COLOUR["S1"], marker=MARKER["S1"], ms=6.5,
                lw=1.4, ls=(0, (4, 2)), mfc=SURFACE, mec=COLOUR["S1"], mew=1.4, label="S1, 2nd time")
        turned = [x for x in rows if x["angle_deg"] != 0]
        ax.scatter([x[kx] for x in turned], [x[ky] for x in turned], marker="x", s=46, lw=1.6, color=INK,
                   zorder=5, label="45° and 90°")
        style(ax, xl, yl, title)
        ax.set_xlim(0, None)
        ax.set_ylim(0, None)
        ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def fig_predictions(pred, path):
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.2), facecolor=SURFACE)
    for ax, kt, kp, unit, title in ((axes[0], "depth_mm", "depth_pred_other_stars", "mm", "Depth"),
                                    (axes[1], "force_N", "force_pred_other_stars", "N", "Force")):
        top = 1.08 * max(max(p[kt] for p in pred), max(p[kp] for p in pred))
        ax.plot([0, top], [0, top], color=INK2, lw=1, ls=(0, (4, 3)), zorder=1)
        for s in STARS:
            pts = [p for p in pred if p["star"] == s]
            ax.scatter([p[kt] for p in pts], [p[kp] for p in pts], marker=MARKER[s], s=42, color=COLOUR[s],
                       edgecolor=SURFACE, linewidth=1.0, label=s, zorder=3)
        ax.set_xlim(0, top)
        ax.set_ylim(0, top)
        style(ax, f"true {title.lower()} ({unit}, MARK-10)", f"{title.lower()} from the sensor ({unit})",
              f"{title}: calibrated on the other three stars")
        ax.legend(frameon=False, loc="upper left")
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

    rows, maps, missing = measure_all()
    write_csv(os.path.join(args.out, "signals.csv"), rows)
    sl, off, ori, pred = slopes(rows), zero_offset(rows), orientation(rows), predictions(rows)
    write_csv(os.path.join(args.out, "predictions.csv"), pred)

    fig_maps(rows, maps, os.path.join(fig_dir, "stretch_maps.png"))
    fig_orientation(rows, maps, os.path.join(fig_dir, "orientation.png"))
    fig_signals(rows, os.path.join(fig_dir, "signals.png"))
    fig_predictions(pred, os.path.join(fig_dir, "predicted_vs_true.png"))

    def mae(items, kp, kt):
        e = np.array([p[kp] - p[kt] for p in items], float)
        return float(np.abs(e).mean()), float(e.mean()), float(np.abs(e).max()), len(e)

    lines = ["# Estrelas S1–S4 a profundidades conhecidas (MARK-10)", "",
             f"{len(rows)} fotos pressionadas medidas"
             + (f"; {len(missing)} linha(s) da folha sem foto: "
                + ", ".join(f"{m['star']} {m['angle_deg']}° {m['depth_mm']} mm" for m in missing) if missing else "")
             + ".", "",
             "## 1. O sinal segue a profundidade?", "",
             "Reta ajustada ao esticamento máximo contra a profundidade (série a 0°, 1.ª vez).", "",
             "| estrela | fotos | profundidade máxima (mm) | esticamento por mm | R² da reta |", "|---|---|---|---|---|"]
    for s in STARS:
        lines.append(f"| {s} | {sl[s]['n']} | {sl[s]['max_depth']:.1f} | {sl[s]['slope']:.4f} | {sl[s]['r2']:.4f} |")
    lines += ["", "## 2. Repetibilidade e orientação", "",
              "Desvio em profundidade da 2.ª série da S1 face à 1.ª (quanto é preciso deslocar a 2.ª para coincidir):", "",
              "| grandeza | desvio médio (mm) | dp (mm) | pontos |", "|---|---|---|---|"]
    names = {"peak_stretch": "esticamento máximo (sensor)", "force_N": "força (MARK-10, N)",
             "stretch_integral_mm2": "esticamento somado (sensor, mm²)",
             "integral_per_N": "esticamento somado por newton"}
    for key in ("peak_stretch", "stretch_integral_mm2", "force_N"):
        lines.append(f"| {names[key]} | {off[key][0]:+.2f} | {off[key][1]:.2f} | {off[key][2]} |")
    lines += ["", "Mesma estrela e profundidade, orientações diferentes (variação = (máx − mín) / média). "
              "O zero da profundidade foi refeito em cada orientação, por isso a força também varia; "
              "o esticamento por newton retira esse efeito.", "",
              "| estrela | profundidade (mm) | grandeza | valores | variação (%) |", "|---|---|---|---|---|"]
    for o in ori:
        lines.append(f"| {o['star']} | {o['depth_mm']:.1f} | {names[o['signal']]} | {o['values']} | {o['spread_pct']:.1f} |")
    same = [p for p in pred if p["depth_pred_same_star"] != ""]
    m_same = mae(same, "depth_pred_same_star", "depth_mm")
    lines += ["", "## 3. Profundidade lida do sensor", "",
              f"- **Calibração na mesma estrela** (curva da S1, 1.ª série; testada nas outras {m_same[3]} fotos da S1): "
              f"erro médio {m_same[0]:.2f} mm, viés {m_same[1]:+.2f} mm, máximo {m_same[2]:.2f} mm.",
              "- **Calibração nas outras três estrelas** (a estrela testada nunca entra na calibração):", "",
              "| estrela testada | fotos | erro médio (mm) | viés (mm) | erro máximo (mm) |", "|---|---|---|---|---|"]
    for s in STARS:
        m = mae([p for p in pred if p["star"] == s], "depth_pred_other_stars", "depth_mm")
        lines.append(f"| {s} | {m[3]} | {m[0]:.2f} | {m[1]:+.2f} | {m[2]:.2f} |")
    m = mae(pred, "depth_pred_other_stars", "depth_mm")
    lines.append(f"| **todas** | {m[3]} | **{m[0]:.2f}** | {m[1]:+.2f} | {m[2]:.2f} |")
    lines += ["", "## 4. Força lida do sensor (esticamento somado, calibração nas outras três estrelas)", "",
              "| estrela testada | fotos | erro médio (N) | viés (N) | erro máximo (N) | erro médio (% da força) |",
              "|---|---|---|---|---|---|"]
    for s in STARS + ["todas"]:
        items = pred if s == "todas" else [p for p in pred if p["star"] == s]
        m = mae(items, "force_pred_other_stars", "force_N")
        rel = float(np.mean([abs(p["force_pred_other_stars"] - p["force_N"]) / p["force_N"] for p in items]))
        lines.append(f"| {s} | {m[3]} | {m[0]:.1f} | {m[1]:+.1f} | {m[2]:.1f} | {100 * rel:.0f} |")
    lines += ["", "## Dados por foto", "",
              "| estrela | ângulo | série | profundidade (mm) | força (N) | esticamento máximo | esticamento somado (mm²) | região (mm²) |",
              "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['star']} | {r['angle_deg']}° | {r['repeat']} | {r['depth_mm']:.1f} | {r['force_N']:.2f} | "
                     f"{r['peak_stretch']:.4f} | {r['stretch_integral_mm2']:.2f} | {r['region_mm2']:.0f} |")
    with open(os.path.join(args.out, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines[:lines.index("## Dados por foto")]))
    print(f"\n-> {args.out}/ (summary.md, CSVs, figures/)")


if __name__ == "__main__":
    main()
