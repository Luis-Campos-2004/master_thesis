#!/usr/bin/env python3
"""
build_dataset_v3.py — Builds the annotated rotated photo set (v3) from the
v2 photos and the hand-drawn outlines (<name>_<angle>º_gt.jpg).

For every outline it finds the v2 photo it was drawn on (the same pixels
everywhere except the thin line), so the angle labels follow the outline
file names. An outline drawn on a photo that is not in v2 gets its clean
photo back by inpainting the line (it is only 1-2 px wide).

Output (v2 is left untouched):
    data/raw/shape_pictures_v3/reference.jpg, <Shape>/rot_XXX.jpg   clean photos
    data/annotations/shape_pictures_v3/<Shape>/rot_XXX_gt.jpg        outlines

Usage from the repo root:
    python verification/build_dataset_v3.py [folder with the *_shape_data dirs]
"""

import argparse
import os
import re
import shutil

import cv2
import numpy as np

V2 = "data/raw/shape_pictures_v2"
V3 = "data/raw/shape_pictures_v3"
ANN = "data/annotations/shape_pictures_v3"
FOLDERS = {"F_shape_data": "F shape", "P_shape_data": "P shape", "M_shape_data": "M shape",
           "Ring_shape_data": "Ring", "Square_shape_data": "Square",
           "Square_Circle_Shape_data": "Square Circle", "Star_shape_data": "Star",
           "Three-Circles_shape_data": "Three Circles"}
SAME_PHOTO = 1.0       # mean |gray diff| below this = the outline was drawn on that photo


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", nargs="?", default=os.path.expanduser("~/Desktop"))
    args = ap.parse_args()

    os.makedirs(V3, exist_ok=True)
    shutil.copy2(os.path.join(V2, "reference.jpg"), os.path.join(V3, "reference.jpg"))
    for folder, shape in FOLDERS.items():
        src = os.path.join(args.src, folder)
        if not os.path.isdir(src):
            print(f"  missing {src}, skipped")
            continue
        os.makedirs(os.path.join(V3, shape), exist_ok=True)
        os.makedirs(os.path.join(ANN, shape), exist_ok=True)
        photos = {f: cv2.imread(os.path.join(V2, shape, f), cv2.IMREAD_GRAYSCALE).astype(np.float32)
                  for f in sorted(os.listdir(os.path.join(V2, shape))) if f.endswith(".jpg")}
        for g in sorted(os.listdir(src)):
            m = re.search(r"_(\d+)\D*_gt\.(jpe?g|png)$", g, re.I)
            if not m:
                continue
            angle = int(m.group(1))
            name = f"rot_{angle:03d}"
            gt = cv2.imread(os.path.join(src, g))
            gray = cv2.cvtColor(gt, cv2.COLOR_BGR2GRAY).astype(np.float32)
            diffs = {f: float(np.abs(gray - p).mean()) for f, p in photos.items()}
            best = min(diffs, key=diffs.get)
            out_photo = os.path.join(V3, shape, name + ".jpg")
            if diffs[best] < SAME_PHOTO:
                shutil.copy2(os.path.join(V2, shape, best), out_photo)
                note = f"drawn on v2 {best}" + ("" if best == name + ".jpg" else "  (relabelled)")
            else:
                b, gch, r = (gt[..., i].astype(int) for i in range(3))
                line = ((r - np.maximum(gch, b)) > 30).astype(np.uint8)
                line = cv2.dilate(line, np.ones((5, 5), np.uint8))
                clean = cv2.inpaint(gt, line, 3, cv2.INPAINT_TELEA)
                cv2.imwrite(out_photo, clean, [cv2.IMWRITE_JPEG_QUALITY, 98])
                note = "photo not in v2: clean copy rebuilt by inpainting the line"
            shutil.copy2(os.path.join(src, g), os.path.join(ANN, shape, name + "_gt.jpg"))
            print(f"  {shape:14s} {g:28s} -> {name}  ({note})")
    print(f"photos -> {V3}/, outlines -> {ANN}/")


if __name__ == "__main__":
    main()
