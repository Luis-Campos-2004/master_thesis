#!/usr/bin/env python3
"""
adjust_photos.py — Prepares a photo set for shape detection: aligns every
pressed photo to the reference and evens out brightness and contrast, with
exactly the same steps for the reference and the pressed photos.

Steps, per photo:
  1. alignment: the camera can shift a few pixels between shots, so each
     photo is translated onto the reference (phase correlation on the
     housing at the left and right edges, which doesn't deform);
  2. illumination: divide by a heavily blurred copy (sigma well above the
     stripe period) to flatten vignetting and uneven lighting;
  3. contrast: stretch the 1st..99th percentile inside the membrane to the
     full 0..255 range (optionally CLAHE on top, --clahe).

Input layout:   <src>/reference.jpg, <src>/<Shape>/rot_XXX.jpg
Output layout:  <dst>/reference.png, <dst>/<Shape>/rot_XXX.png (grayscale)

Usage from the repo root:
    python src/tactile/adjust_photos.py
    python src/tactile/adjust_photos.py data/raw/shape_pictures_v2 data/processed/shape_pictures_v2 --clahe
"""

import argparse
import os

import cv2
import numpy as np

SRC = "data/raw/shape_pictures_v2"
DST = "data/processed/shape_pictures_v2"
EDGE_BAND = 350        # px at each side used for alignment (housing, no membrane)
FLAT_SIGMA = 150       # illumination blur (px); stripes are ~50 px apart
DISC_FRAC = 0.45       # membrane disc used for the percentiles (fraction of height)
CLIP_PCT = (1, 99)     # percentiles mapped to 0 and 255


def edge_band(gray):
    m = np.zeros_like(gray)
    m[:, :EDGE_BAND] = 1
    m[:, -EDGE_BAND:] = 1
    return gray * m


def align(gray, ref_gray, window):
    """Translate gray onto ref_gray; returns the aligned image and the shift."""
    (sx, sy), _ = cv2.phaseCorrelate(edge_band(ref_gray), edge_band(gray), window)
    shift = np.float32([[1, 0, -sx], [0, 1, -sy]])
    out = cv2.warpAffine(gray, shift, gray.shape[::-1], flags=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_REFLECT)
    return out, (sx, sy)


def adjust(gray, clahe=None):
    """Flat-field, then a percentile stretch inside the membrane disc."""
    flat = gray / np.maximum(cv2.GaussianBlur(gray, (0, 0), FLAT_SIGMA), 1.0)
    h, w = flat.shape
    yy, xx = np.ogrid[:h, :w]
    disc = np.hypot(yy - h / 2, xx - w / 2) < DISC_FRAC * h
    lo, hi = np.percentile(flat[disc], CLIP_PCT)
    out = np.clip((flat - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)
    return clahe.apply(out) if clahe is not None else out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", nargs="?", default=SRC)
    ap.add_argument("dst", nargs="?", default=DST)
    ap.add_argument("--clahe", action="store_true",
                    help="add local contrast equalisation (CLAHE) after the stretch")
    args = ap.parse_args()

    ref_path = os.path.join(args.src, "reference.jpg")
    ref = cv2.imread(ref_path, cv2.IMREAD_GRAYSCALE)
    if ref is None:
        raise FileNotFoundError(ref_path)
    ref = ref.astype(np.float32)
    window = cv2.createHanningWindow(ref.shape[::-1], cv2.CV_32F)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)) if args.clahe else None

    os.makedirs(args.dst, exist_ok=True)
    cv2.imwrite(os.path.join(args.dst, "reference.png"), adjust(ref, clahe))
    n = 0
    for shape in sorted(os.listdir(args.src)):
        folder = os.path.join(args.src, shape)
        if not os.path.isdir(folder):
            continue
        os.makedirs(os.path.join(args.dst, shape), exist_ok=True)
        for f in sorted(os.listdir(folder)):
            if not f.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            gray = cv2.imread(os.path.join(folder, f), cv2.IMREAD_GRAYSCALE)
            if gray is None or gray.shape != ref.shape:
                print(f"  skipped {shape}/{f} (unreadable or not {ref.shape[::-1]})")
                continue
            aligned, (sx, sy) = align(gray.astype(np.float32), ref, window)
            out = os.path.join(args.dst, shape, os.path.splitext(f)[0] + ".png")
            cv2.imwrite(out, adjust(aligned, clahe))
            print(f"  {shape}/{f}: shifted ({-sx:+.1f}, {-sy:+.1f}) px")
            n += 1
    print(f"{n} photos + reference -> {args.dst}/")


if __name__ == "__main__":
    main()
