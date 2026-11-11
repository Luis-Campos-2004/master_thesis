#!/usr/bin/env python3
"""
audit_images.py (v3), image quality audit for the striped tactile skin.

PURPOSE
    Answers two questions with numbers instead of eyeballs:
      1. Are the photos technically good (focus, exposure, lighting, contrast)?
      2. Does the stripe spacing change more BETWEEN force levels than it
         wobbles BETWEEN repeat shots of the SAME force?
    Question 2 decides whether the dataset can resolve force at all.

USAGE (from the repo root)
    python audit_images_v3.py data/raw/force_pictures --out audit_force.csv
"""

import argparse                       # command-line arguments
import csv                            # writing the results table
import os                             # walking folders, splitting paths
import sys                            # sys.exit on fatal errors
import time                           # timing the run
from collections import defaultdict   # dict that auto-creates empty lists

import cv2                            # OpenCV: image loading and filtering
import numpy as np                    # arrays, FFT, statistics


# Which file types count as images. A set (not a list) because membership
# testing is O(1). Everything else in the folder is skipped.
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

FFT_CROP = 1024
PAD = 4
SMALL_W = 800

# Radius of the membrane region, as a fraction of the inscribed circle.
# Outside it: housing, silicone debris, LED ring. Measuring there is what
# made all 85 images flag. Verify with DEBUG_MASK before trusting the value.
ROI_FRACTION = 0.60

# Warning thresholds. These are first guesses, not validated values.
CLIP_HIGH_MAX = 1.0      # max % of pure-white pixels before flagging
CLIP_LOW_MAX = 1.0       # max % of pure-black pixels
CARRIER_SNR_MIN = 8.0    # min stripe-peak strength
VIGNETTE_LO = 0.80       # min acceptable edge/centre brightness ratio
VIGNETTE_HI = 1.20       # max acceptable ratio
# NOTE: on this dataset the clipping and vignette flags fire on the LED ring,
# which sits inside the frame, not on any problem with the membrane itself.
# Applying the ROI mask before measuring would fix that.


def _parabolic(y_minus, y_zero, y_plus):
    denom = y_minus - 2.0 * y_zero + y_plus
    if abs(denom) < 1e-12:
        return 0.0
    return 0.5 * (y_minus - y_plus) / denom



def _disc(h, w, frac):
    """Boolean mask of a centred disc, plus the distance map."""
    yy, xx = np.ogrid[:h, :w]
    r = np.hypot(yy - h / 2, xx - w / 2)
    return r < frac * min(h, w) / 2, r

def measure(path):

    bgr = cv2.imread(path, cv2.IMREAD_COLOR)   # load (OpenCV order: B,G,R)
    if bgr is None:                            # OpenCV returns None, no raise
        return None
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)  # stripes are B/W: colour
                                                  # carries no extra info
    H, W = gray.shape                          # height, width in pixels

    m = {}                                     # results accumulator

    scale = SMALL_W / float(W)                 # shrink factor
    # Scale --> 800/4608 ~ 0.174
    small = cv2.resize(gray, (SMALL_W, int(H * scale)), interpolation=cv2.INTER_AREA)
    # INTER_AREA averages merged pixels instead of picking one.
    s = small.astype(np.float32)               # float to avoid uint8 overflow
    # arithmetic wraps around at 255


    # Membrane-only masks. Everything below is measured inside these.
    roi_full, _ = _disc(H, W, ROI_FRACTION)              # full resolution
    h2, w2 = s.shape
    roi_small, r_small = _disc(h2, w2, ROI_FRACTION)     # shrunk copy
    r_roi = ROI_FRACTION * min(h2, w2) / 2               # membrane radius

    # Laplacian = second derivative = edge detector. A sharp image has strong
    # edges, so its Laplacian has high variance. Standard autofocus metric.
    lap = cv2.Laplacian(small, cv2.CV_64F)
    m["sharpness"] = float(lap[roi_small].var())   # membrane only

    # Still FULL-RES: downscaling averages clipping away. But masked, so the
    # LED ring no longer counts as blown highlights.
    g_roi = gray[roi_full]
    m["clip_high"] = float(100.0 * np.mean(g_roi >= 250))
    m["clip_low"] = float(100.0 * np.mean(g_roi <= 5))
    m["mean"] = float(s[roi_small].mean())     # brightness, membrane only
    m["std"] = float(s[roi_small].std())       # contrast, membrane only

    #Preparing the stripe crop, n its the crop side (1024 unless the image is smaller)
    #  STRIPE MEASUREMENT: centred crop, full resolution 
    n = min(FFT_CROP, H, W)                    # don't exceed the image
    n -= n % 2                                 # force even so the FFT centre is an exact pixel
    # forces even so the FFT centre lands on an exact pixel

    # Slice a centred square: rows first, then columns.
    sub = gray[(H - n) // 2:(H + n) // 2,
               (W - n) // 2:(W + n) // 2].astype(np.float32)

    # Hanning window: a bell curve fading to zero at both ends.
    # WHY: the FFT assumes the image tiles infinitely, so the right edge is
    # treated as adjacent to the left edge. Unless they happen to match, that
    # fake discontinuity smears energy across ALL frequencies and buries the
    # real stripe peak. np.outer builds the 2D window from the 1D one.
    win = np.outer(np.hanning(n), np.hanning(n))

    # Subtract the mean so overall brightness (the DC term) doesn't dominate,
    # then apply the window.
    windowed = (sub - sub.mean()) * win

    N = n * PAD                                # padded size: 1024 -> 4096
    # s=(N, N) pads with zeros before transforming -> 4x finer frequency bins.
    # fftshift moves zero frequency from the corner to the centre.
    # np.abs discards phase, keeps "how much of each frequency is present" (magnitude).
    mag = np.abs(np.fft.fftshift(np.fft.fft2(windowed, s=(N, N))))


    c = N // 2                                 # index of zero frequency

    # The centre bin means "no repetition at all" and is always the brightest
    # thing in the transform. Blank a disc around it on a COPY, so argmax
    # finds the stripes instead. (mag itself stays intact, the parabolic
    # refinement and the median below both need the original.)
    search = mag.copy()
    dc_r = max(6 * PAD, N // 40)               # blanking radius
    search[c - dc_r:c + dc_r + 1, c - dc_r:c + dc_r + 1] = 0.0

    # argmax returns a FLAT index; unravel_index converts it to (row, col).
    iy, ix = np.unravel_index(np.argmax(search), search.shape)
    peak = float(search[iy, ix])               # peak height, for the SNR

    # Refine the peak position to sub-bin precision in each axis.
    dy = dx = 0.0
    if 0 < iy < N - 1:                         # guard: peak not on an edge
        dy = _parabolic(mag[iy - 1, ix], mag[iy, ix], mag[iy + 1, ix])
    if 0 < ix < N - 1:
        dx = _parabolic(mag[iy, ix - 1], mag[iy, ix], mag[iy, ix + 1])

    fy = (iy + dy) - c                         # refined position relative to
    fx = (ix + dx) - c                         # the centre
    # Straight-line distance from the centre = the spatial frequency,
    # independent of stripe ORIENTATION. This is why diagonal stripes need
    # no rotation correction.
    fr = float(np.hypot(fy, fx))

    fr_orig = fr / PAD                         # padded bins -> cycles per crop
    # period = crop size / number of cycles across it.
    # The >0.5 guard prevents dividing by ~0 if peak detection failed.
    m["period_px"] = float(n / fr_orig) if fr_orig > 0.5 else float("nan")

    # Stripe orientation. Not used yet, but a drift here means the skin
    # rotated in the housing between sessions — worth watching.
    m["angle_deg"] = float(np.degrees(np.arctan2(fy, fx)))

    # Median, not mean: the mean would be inflated by the peak itself.
    med = float(np.median(mag))
    m["carrier_snr"] = peak / med if med > 0 else float("nan")

    # fringe modulation: how strong is the black-to-white contrast
    # Blur with a radius of about one stripe period: this ERASES the stripes
    # and leaves only the slow illumination background.
    sigma = max(m["period_px"], 2.0) if not np.isnan(m["period_px"]) else 8.0
    k = int(6 * sigma) | 1                     # |1 forces odd (OpenCV requires)
    local_mean = cv2.GaussianBlur(sub, (k, k), sigma)
    bp = sub - local_mean                      # subtract -> only stripes left
    denom = float(local_mean.mean())
    # Dividing by mean brightness makes this a RELATIVE contrast, so it
    # doesn't change if the exposure changes.
    m["modulation"] = float(bp.std() / denom) if denom > 1e-6 else float("nan")
    #sigma --> blur radius of about one stripe period. Erases the stripes, keeps the slow illumination background
    # k -> kernel size. | 1 is bitwise OR forcing odd, which OpenCV requires
    # local_mean -> the background alone
    # bp -> subtract it -> only the stripes remain
    # bp.std() is their amplitude; dividing by mean brightness makes it relative, so exposure changes don't affect it



    # vignetting: is the ring light even ACROSS THE MEMBRANE?
    # Same 30 % / 70-95 % proportions, but of the membrane radius rather than
    # the whole frame, so the outer ring no longer lands on the LEDs.
    centre = s[r_small < 0.3 * r_roi].mean()
    outer = s[(r_small > 0.7 * r_roi) & (r_small < 0.95 * r_roi)].mean()
    # 1.0 = perfectly uniform. <1 = dark edges. >1 = bright edges.


    m["vignette"] = float(outer / centre) if centre > 1e-6 else float("nan")


    if os.environ.get("DEBUG_MASK"):
        dbg = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
        cv2.circle(dbg, (w2 // 2, h2 // 2), int(r_roi), (0, 0, 255), 2)
        cv2.imwrite("debug_mask.png", dbg)

    return m

# Flagging and sorting


def flags(m):
    out = []
    if m["clip_high"] > CLIP_HIGH_MAX:
        out.append("BLOWN_HIGHLIGHTS")
    if m["clip_low"] > CLIP_LOW_MAX:
        out.append("CRUSHED_BLACKS")
    # np.isnan guard: a failed measurement must not trigger a false warning.
    if not np.isnan(m["carrier_snr"]) and m["carrier_snr"] < CARRIER_SNR_MIN:
        out.append("WEAK_CARRIER")
    v = m["vignette"]
    if not np.isnan(v) and not (VIGNETTE_LO <= v <= VIGNETTE_HI):
        out.append("UNEVEN_LIGHT")
    return out


def folder_sort_key(name):
    base = name.strip().rstrip("Nn")           # "12N" -> "12"
    try:
        return (0, float(base))
    except ValueError:                         # e.g. "reference"
        return (1, name)


# Main thing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")                    # required, no dashes
    ap.add_argument("--out", default="audit.csv") # optional, takes a value
    ap.add_argument("--quiet", action="store_true")  # optional, no value
    args = ap.parse_args()

    # root is positional, you must supply it
    #store_true means --quiet is present or absent; args.quiet becomes True/False

    if not os.path.isdir(args.root):
        sys.exit(f"Not a directory: {args.root}")

    # Collect every image path FIRST, so we can print "[i/85]" progress.
    paths = []
    for dirpath, _, filenames in os.walk(args.root):   # recurses subfolders;
        for fn in sorted(filenames):                   # _ discards subdir list
            if os.path.splitext(fn)[1].lower() in IMG_EXT:
                paths.append(os.path.join(dirpath, fn))
    # os.walk recurses through every subfolder, yielding (folder, subfolders, files)
    #_ discards the subfolder list, recursion already handles it
    #splitext(fn)[1] is the extension; .lower() so .JPG works
    #Collected first so we know the total and can print [i/85]

    if not paths:
        sys.exit(f"No images found under {args.root}")

    print(f"Found {len(paths)} images. Measuring (zero-pad {PAD}x)...", flush=True)

    rows = []                        # one dict per image -> becomes the CSV
    by_folder = defaultdict(list)    # folder -> list of metric dicts
    t0 = time.time()

    for i, path in enumerate(paths, 1):        # start counting at 1
        m = measure(path)
        if m is None:
            print(f"  [{i}/{len(paths)}] UNREADABLE: {path}", flush=True)
            continue
        # relpath strips the root prefix, so the label is "12N" not the
        # whole absolute path.
        folder = os.path.relpath(os.path.dirname(path), args.root)
        fl = flags(m)
        # **m unpacks the 8 measurements as separate keys in the row.
        rows.append({"folder": folder, "file": os.path.basename(path),
                     **m, "flags": "|".join(fl)})
        by_folder[folder].append(m)
        if not args.quiet:
            # flush=True forces immediate output; without it Python buffers
            # and you see NOTHING until the script finishes.
            print(f"  [{i}/{len(paths)}] {folder}/{os.path.basename(path)}  "f"period={m['period_px']:.4f}  snr={m['carrier_snr']:.0f}",flush=True)
    # Forces immediate output. Without it Python buffers and you see nothing until the end
    print(f"\nDone in {time.time() - t0:.0f} s.\n", flush=True)
    # Forces immediate output. Without it Python buffers and you see nothing until the end

    #  write the full table 
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        # Column names taken from the first row's keys, so adding a metric
        # to measure() automatically adds a CSV column.
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    order = sorted(by_folder, key=folder_sort_key)   # 3N, 6N, ... reference

    # per-folder summary table
    print(f"{'folder':<12}{'n':>3}{'period_px':>22}{'sharpness':>16}"
          f"{'carrier_snr':>14}{'modulation':>14}{'vignette':>12}")
    print("-" * 94)
    for folder in order:
        ms = by_folder[folder]
        p = np.array([x["period_px"] for x in ms], float)
        line = f"{folder:<12}{len(ms):>3}"
        line += f"{np.nanmean(p):>14.4f}±{np.nanstd(p):<7.4f}"
        # List comprehension pulls one metric from all five dicts into an array
        # nanmean/nanstd ignore failed measurements instead of letting one NaN poison the average
        # :>14.4f is right-aligned in 14 characters with 4 decimals — that's what keeps the columns lined up
        for k in ["sharpness", "carrier_snr", "modulation", "vignette"]:
            v = np.array([x[k] for x in ms], float)
            # nanmean/nanstd ignore failed measurements instead of letting
            # one NaN poison the whole average.
            line += f"{np.nanmean(v):>14.2f}"
        print(line)

    # repeatability: the noise floor 
    # Five photos in one folder are the SAME force with nothing changed, so
    # their spread is pure measurement noise.
    print("\nWithin-folder period repeatability:")
    means = {}
    for folder in order:
        v = np.array([x["period_px"] for x in by_folder[folder]], float)
        mu = np.nanmean(v)
        means[folder] = mu
        if len(v) > 1 and mu > 0:
            # Coefficient of variation: std as a % of the mean, so folders
            # with different absolute periods stay comparable.
            cv_pct = 100 * np.nanstd(v) / mu
            # Coefficient of variation: standard deviation as a percentage of the mean
            # Percentage rather than absolute, so folders with different periods stay comparable
            # Five photos at the same force with nothing changed, their spread is pure measurement noise
            note = "  <-- noisy" if cv_pct > 0.1 else ""
            print(f"  {folder:<12} mean={mu:9.4f} px   CV = {cv_pct:7.4f} %{note}")

    # Average noise across all folders.
    noise = np.nanmean([100 * np.nanstd([x["period_px"] for x in by_folder[f]])
                        / means[f] for f in order if np.isfinite(means[f])])

    #  THE ANSWER: signal vs noise 
    finite = {k: v for k, v in means.items() if np.isfinite(v)}
    if len(finite) > 1:
        lo, hi = min(finite.values()), max(finite.values())
        signal = 100 * (hi - lo) / lo          # total change across the range
        print(f"\nSignal  (period range across folders): {signal:.3f} %")
        print(f"Noise   (mean within-folder CV): {noise:.4f} %")
        if noise > 0:
            print(f"Signal / noise ratio:                  {signal / noise:.0f}")
            # 3 sigma is the conventional threshold for calling two
            # measurements genuinely different.
            print(f"=> roughly {signal / (3 * noise):.0f} distinguishable levels "
                  f"across the range (3-sigma separation)")

    # flag summary
    flagged = [r for r in rows if r["flags"]]
    print(f"\nFlagged: {len(flagged)} / {len(rows)} images")
    seen = {}
    for r in flagged:
        seen[r["flags"]] = seen.get(r["flags"], 0) + 1
    for k, v in sorted(seen.items(), key=lambda kv: -kv[1]):   # most common 1st
        print(f"  {v:>4}x  {k}")
    print(f"\nFull results written to {args.out}")


# Runs main() only when executed directly, not when imported as a module.
if __name__ == "__main__":
    main()