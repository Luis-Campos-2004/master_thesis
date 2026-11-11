#!/usr/bin/env python3
"""
audit_shape.py, audits the contact-shape dataset.

Folder layout it expects:
    data/raw/shape_pictures/<Shape Name>/img_XX.jpg
    data/raw/shape_pictures/<Shape Name>/<x>_gt.jpg     (ground truth, optional)

It answers three questions:
    1. Are the shape images technically comparable to the force images?
       (same stripe period, contrast, exposure -- if not, a model calibrated
        on one will not transfer to the other)
    2. Is the stripe carrier strong enough for FTP in every shape folder?
    3. Where a ground-truth image exists, how much of the frame does the
       contact occupy, and does a simple threshold recover a similar area?

Note: this does NOT evaluate the existing shape-detection algorithm. It
checks whether the INPUT data can support shape detection at all, which is
the same question the force audit asked.

Usage from the repo root:
    python audit_shape.py data/raw/shape_pictures
    python audit_shape.py data/raw/shape_pictures --outdir figures
"""

import argparse
import csv
import os
import sys
import time

import cv2
import numpy as np

IMG_EXT = {".jpg", ".jpeg", ".png"}

FFT_CROP = 1024
PAD = 4
SMALL_W = 800
ROI_FRACTION = 0.60          # same membrane disc as the force audit

CARRIER_SNR_MIN = 8.0
CLIP_MAX = 1.0


def _parabolic(y_minus, y_zero, y_plus):
    denom = y_minus - 2.0 * y_zero + y_plus
    if abs(denom) < 1e-12:
        return 0.0
    return 0.5 * (y_minus - y_plus) / denom


def _disc(h, w, frac):
    yy, xx = np.ogrid[:h, :w]
    r = np.hypot(yy - h / 2, xx - w / 2)
    return r < frac * min(h, w) / 2, r


def measure(path):
    """Same metrics as the force audit, so the two are directly comparable."""
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape

    m = {}
    scale = SMALL_W / float(W)
    small = cv2.resize(gray, (SMALL_W, int(H * scale)),
                       interpolation=cv2.INTER_AREA)
    s = small.astype(np.float32)

    roi_full, _ = _disc(H, W, ROI_FRACTION)
    h2, w2 = s.shape
    roi_small, r_small = _disc(h2, w2, ROI_FRACTION)
    r_roi = ROI_FRACTION * min(h2, w2) / 2

    lap = cv2.Laplacian(small, cv2.CV_64F)
    m["sharpness"] = float(lap[roi_small].var())
    g_roi = gray[roi_full]
    m["clip_high"] = float(100.0 * np.mean(g_roi >= 250))
    m["clip_low"] = float(100.0 * np.mean(g_roi <= 5))
    m["mean"] = float(s[roi_small].mean())
    m["std"] = float(s[roi_small].std())

    # carrier 
    n = min(FFT_CROP, H, W)
    n -= n % 2
    sub = gray[(H - n) // 2:(H + n) // 2,
               (W - n) // 2:(W + n) // 2].astype(np.float32)

    win = np.outer(np.hanning(n), np.hanning(n))
    N = n * PAD
    mag = np.abs(np.fft.fftshift(np.fft.fft2((sub - sub.mean()) * win,
                                             s=(N, N))))
    c = N // 2
    search = mag.copy()
    dc_r = max(6 * PAD, N // 40)
    search[c - dc_r:c + dc_r + 1, c - dc_r:c + dc_r + 1] = 0.0

    iy, ix = np.unravel_index(np.argmax(search), search.shape)
    peak = float(search[iy, ix])

    dy = dx = 0.0
    if 0 < iy < N - 1:
        dy = _parabolic(mag[iy - 1, ix], mag[iy, ix], mag[iy + 1, ix])
    if 0 < ix < N - 1:
        dx = _parabolic(mag[iy, ix - 1], mag[iy, ix], mag[iy, ix + 1])

    fy, fx = (iy + dy) - c, (ix + dx) - c
    fr = float(np.hypot(fy, fx)) / PAD
    m["period_px"] = float(n / fr) if fr > 0.5 else float("nan")
    m["angle_deg"] = float(np.degrees(np.arctan2(fy, fx)))

    med = float(np.median(mag))
    m["carrier_snr"] = peak / med if med > 0 else float("nan")

    sigma = max(m["period_px"], 2.0) if not np.isnan(m["period_px"]) else 8.0
    k = int(6 * sigma) | 1
    local_mean = cv2.GaussianBlur(sub, (k, k), sigma)
    bp = sub - local_mean
    denom = float(local_mean.mean())
    m["modulation"] = float(bp.std() / denom) if denom > 1e-6 else float("nan")

    centre = s[r_small < 0.3 * r_roi].mean()
    outer = s[(r_small > 0.7 * r_roi) & (r_small < 0.95 * r_roi)].mean()
    m["vignette"] = float(outer / centre) if centre > 1e-6 else float("nan")

    return m


def gt_area_fraction(path):
    """Fraction of the membrane disc covered by the contact in a GT image."""
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape
    roi, _ = _disc(H, W, ROI_FRACTION)

    # Otsu picks the threshold automatically from the histogram, so this does
    # not depend on a hand-chosen value.
    vals = gray[roi]
    thr, _ = cv2.threshold(vals, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Otsu's method automatically picks the threshold that best separates a histogram into two classes, by maximising between-class variance. 
    # The 0 is ignored when THRESH_OTSU is set -> Otsu computes it. thr is the chosen value.
    # The idea was: no hand-tuned threshold, so the measurement isn't arbitrary.
    dark = float(np.mean(vals < thr))
    # Report whichever class is the minority -- the contact patch is the
    # smaller region, whether it came out darker or lighter than the skin.
    return min(dark, 1.0 - dark) * 100.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default="data/raw/shape_pictures")
    ap.add_argument("--out", default="audit_shape.csv")
    ap.add_argument("--force-csv", default="audit_force.csv",
                    help="for comparing against the force dataset")
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        sys.exit(f"Not a directory: {args.root}")

    rows = []
    by_shape = {}
    gt_files = {}
    t0 = time.time()

    shapes = sorted(d for d in os.listdir(args.root)
                    if os.path.isdir(os.path.join(args.root, d)))
    if not shapes:
        sys.exit("No shape folders found.")

    for shape in shapes:
        d = os.path.join(args.root, shape)
        files = [f for f in sorted(os.listdir(d))
                 if os.path.splitext(f)[1].lower() in IMG_EXT]
        # Ground-truth images are named *_gt.jpg -- keep them separate.
        gts = [f for f in files if "_gt" in f.lower()]
        imgs = [f for f in files if "_gt" not in f.lower()]
        if gts:
            gt_files[shape] = os.path.join(d, gts[0])

        ms = []
        for fn in imgs:
            m = measure(os.path.join(d, fn))
            if m is None:
                print(f"  UNREADABLE: {shape}/{fn}")
                continue
            ms.append(m)
            rows.append({"shape": shape, "file": fn, **m})
        by_shape[shape] = ms
        print(f"  {shape:<18} {len(ms)} images"
              + (f"  (+1 ground truth)" if shape in gt_files else ""),
              flush=True)

    if not rows:
        sys.exit("No images measured.")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    print(f"\nMeasured {len(rows)} images in {time.time() - t0:.0f} s "
          f"-> {args.out}\n")

    # per-shape summary 
    keys = ["period_px", "carrier_snr", "modulation", "sharpness",
            "vignette", "clip_high"]
    print(f"{'shape':<18}{'n':>3}" + "".join(f"{k:>14}" for k in keys))
    print("-" * (21 + 14 * len(keys)))
    for shape in shapes:
        ms = by_shape[shape]
        if not ms:
            continue
        line = f"{shape:<18}{len(ms):>3}"
        for k in keys:
            v = np.array([x[k] for x in ms], float)
            line += f"{np.nanmean(v):>14.2f}"
        print(line)

    #  consistency across shapes 
    print("\n" + "=" * 70)
    print("1. CONSISTENCY ACROSS SHAPE FOLDERS")
    print("=" * 70)
    for k in ["period_px", "carrier_snr", "modulation", "vignette"]:
        per = [np.nanmean([x[k] for x in by_shape[s]])
               for s in shapes if by_shape[s]]
        per = np.array(per, float)
        spread = 100 * np.nanstd(per) / np.nanmean(per)

        """
        Nested comprehension: inner averages a metric within one shape, outer collects those seven averages. 
        
        Then the CV across shapes.

        This is the key measurement of the script.
         
        Different indenter shapes should not change the stripe period, 
        
        the period is a property of the skin and the camera, not of what's pressing on it.

        The result: 4.44 % spread, larger than the entire force signal of 2.63 %. 
        
        That can only come from a different camera distance, zoom, or skin.
        """
        note = "  <-- varies between shapes" if spread > 2 else ""
        print(f"  {k:<14} mean {np.nanmean(per):9.3f}   "
              f"spread {spread:5.2f} %{note}")

    # comparison with the force dataset 
    print("\n" + "=" * 70)
    print("2. COMPARABLE TO THE FORCE DATASET?")
    print("=" * 70)
    if os.path.exists(args.force_csv):
        import csv as _csv
        with open(args.force_csv, encoding="utf-8") as f:
            frows = list(_csv.DictReader(f))
        fref = [r for r in frows if "reference" in r["folder"].lower()]
        fall = frows
        for label, subset in (("force (all)", fall),
                              ("force (reference)", fref)):
            if not subset:
                continue
            for k in ["period_px", "modulation", "carrier_snr"]:
                pass
            p = np.nanmean([float(r["period_px"]) for r in subset])
            mo = np.nanmean([float(r["modulation"]) for r in subset])
            sn = np.nanmean([float(r["carrier_snr"]) for r in subset])
            print(f"  {label:<20} period {p:8.3f}   modulation {mo:5.3f}"
                  f"   snr {sn:8.0f}")
        sp = np.nanmean([r["period_px"] for r in rows])
        sm = np.nanmean([r["modulation"] for r in rows])
        ss = np.nanmean([r["carrier_snr"] for r in rows])
        print(f"  {'shape (all)':<20} period {sp:8.3f}   modulation {sm:5.3f}"
              f"   snr {ss:8.0f}")
        print("\n  If the shape images differ substantially in period or")
        print("  modulation, they were captured under different conditions")
        print("  and a model calibrated on the force set will not transfer.")
    else:
        print(f"  ({args.force_csv} not found -- skipped)")

    # ground truth 
    print("\n" + "=" * 70)
    print("3. GROUND-TRUTH CONTACT AREA")
    print("=" * 70)
    if not gt_files:
        print("  (no *_gt.jpg files found)")
    for shape in shapes:
        if shape not in gt_files:
            print(f"  {shape:<18} no ground truth")
            continue
        frac = gt_area_fraction(gt_files[shape])
        print(f"  {shape:<18} contact covers {frac:5.1f} % of the membrane disc")
    print("\n  Very small contacts are the hard case: fewer stripes inside")
    print("  the contact means a weaker local carrier and a noisier phase.")

    #  flags 
    bad = [r for r in rows
           if (not np.isnan(r["carrier_snr"]) and r["carrier_snr"] < CARRIER_SNR_MIN)
           or r["clip_high"] > CLIP_MAX or r["clip_low"] > CLIP_MAX]
    print(f"\nImages failing basic quality checks: {len(bad)} / {len(rows)}")
    for r in bad[:20]:
        print(f"  {r['shape']}/{r['file']}")


if __name__ == "__main__":
    main()