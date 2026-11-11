"""
strain_map.py
=============
Local stripe-stretch map of the whole membrane, for the photos taken on the
MARK-10 test stand with the new camera (data/raw/depth_stars and
data/raw/stiffness_pieces). detect_shape.py, uniform_reconstruct.py and
reconstruct_v2.py are not changed.

A press squeezes the soft elastomer under the skin sideways, so the stripes
under the contact move apart: the local stripe period grows. This module
measures that stretch at every pixel,

    stretch = period_deformed / period_reference - 1,

from the gradient of the FTP phase difference between a pressed photo and its
reference. Differences from reconstruct_v2.fields():
  * the frame is the full image height, so the whole membrane is in view;
  * the slow background of the image is removed before the FTP and the
    band-pass is narrower (BW_FRAC), which removes the stripe-frequency ripple
    of the phase;
  * the phase is unwrapped inside the membrane only.

Signals returned by measure():
  peak        mean stretch of the PEAK_AREA_MM2 of membrane where it is highest
  area_mm2    region where the stretch is above REGION_FRAC x peak
  integral    stretch summed over the pixels above FLOOR_FRAC x peak (mm^2);
              it grows with the pressed area and with the depth
"""

import os
import sys

import cv2
import numpy as np
from scipy import ndimage as ndi
from skimage.restoration import unwrap_phase

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tactile.detect_shape as ds  # noqa: E402

FRAME = 768            # side of the analysis frame (px)
CROP = 0.5             # half-side of the crop / image height: 0.5 = full height
BW_FRAC = 0.4          # FTP band-pass width (fraction of the carrier)
BG_SIGMA_T = 1.0       # background blur removed before the FTP (stripe periods)
EDGE_MARGIN_T = 2.0    # membrane pixels this close to its edge are not used (periods)
SIGMA_T = 1.0          # smoothing of the phase for the signals (periods)
SIGMA_FINE_T = 0.5     # smoothing of the map kept for figures (periods)
PEAK_AREA_MM2 = 25.0   # the peak is the mean over this much of the membrane (~5 periods^2)
WINDOW_MIN = 0.01      # frame border where the FFT window is below this is not used
REGION_FRAC = 0.5      # contact region = stretch above this fraction of the peak
FLOOR_FRAC = 0.1       # the integral counts stretch above this fraction of the peak
PERIOD_MM = 2.30       # stripe period on the skin (27.14 px at 11.8 px/mm, Liam's skin)


def load_frame(path, size=FRAME, crop=CROP):
    """Central square of the photo (grayscale), resized to size x size."""
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if g is None:
        raise FileNotFoundError(path)
    g = g.astype(np.float32)
    h, w = g.shape
    r = int(min(h, w) * crop)
    return cv2.resize(g[h // 2 - r:h // 2 + r, w // 2 - r:w // 2 + r], (size, size),
                      interpolation=cv2.INTER_AREA)


def membrane_mask(amp, period):
    """Where the reference has stripes: the membrane. Largest region of high fringe
    amplitude; the amplitude is first divided by the Hann window that find_carrier
    applies to the frame, which otherwise makes it fade towards the border."""
    n = amp.shape[0]
    win = np.outer(np.hanning(n), np.hanning(n)).astype(np.float32)
    a = cv2.GaussianBlur(amp.astype(np.float32), (0, 0), period) / np.maximum(
        cv2.GaussianBlur(win, (0, 0), period), 1e-4)
    yy, xx = np.mgrid[:n, :n]
    centre = np.hypot(yy - n / 2, xx - n / 2) < 0.25 * n
    lab, nl = ndi.label((a > 0.35 * np.median(a[centre])) & (win > WINDOW_MIN))
    if nl == 0:
        return np.zeros((n, n), bool)
    big = lab == 1 + int(np.argmax(ndi.sum(np.ones_like(a), lab, range(1, nl + 1))))
    return ndi.binary_fill_holes(big)


def phase_difference(ref_path, def_path):
    """Unwrapped FTP phase difference inside the membrane, and the frame geometry."""
    g_ref, g_def = load_frame(ref_path), load_frame(def_path)
    _, car0 = ds.find_carrier(g_ref)
    t0 = g_ref.shape[0] / float(np.hypot(*car0))
    hp = lambda g: g - cv2.GaussianBlur(g, (0, 0), BG_SIGMA_T * t0)      # noqa: E731
    z_ref, car = ds.demodulate(hp(g_ref), car0, bw_frac=BW_FRAC)
    z_def, _ = ds.demodulate(hp(g_def), car0, bw_frac=BW_FRAC)
    n = g_ref.shape[0]
    f = np.array(car, float) / n                       # (fy, fx), cycles/px
    period = float(1 / np.hypot(*f))
    membrane = membrane_mask(np.abs(z_ref), period)
    inside = ndi.binary_erosion(membrane, iterations=int(round(EDGE_MARGIN_T * period)))
    wrapped = np.ma.masked_array(np.angle(z_def * np.conj(z_ref)), mask=~membrane)
    dphi = np.ma.filled(unwrap_phase(wrapped), 0.0).astype(np.float32)
    rim = membrane & ~ndi.binary_erosion(membrane, iterations=int(round(period)))
    dphi -= np.median(dphi[inside & ndi.binary_dilation(rim, iterations=int(round(3 * period)))])
    return {"dphi": dphi, "f": f, "period": period, "membrane": membrane, "inside": inside,
            "def": g_def, "n": n, "px_per_mm": period / PERIOD_MM}


def stretch_map(fl, sigma_t=SIGMA_T):
    """period_deformed / period_reference - 1 at every pixel."""
    f = fl["f"]
    ph = cv2.GaussianBlur(fl["dphi"], (0, 0), sigma_t * fl["period"])
    gy, gx = np.gradient(ph)
    return (np.hypot(*f) / np.hypot(f[0] + gy / (2 * np.pi), f[1] + gx / (2 * np.pi)) - 1).astype(np.float32)


def measure(ref_path, def_path):
    """Stretch signals of one pressed photo against its reference."""
    fl = phase_difference(ref_path, def_path)
    inside, pxmm = fl["inside"], fl["px_per_mm"]
    s = stretch_map(fl)
    top = max(1, int(round(PEAK_AREA_MM2 * pxmm ** 2)))
    peak = float(np.sort(s[inside])[-top:].mean())
    region = ndi.binary_opening((s > REGION_FRAC * peak) & inside, iterations=2)
    lab, nl = ndi.label(region)
    if nl:
        sizes = ndi.sum(region, lab, range(1, nl + 1))
        region = np.isin(lab, 1 + np.nonzero(sizes >= 0.25 * sizes.max())[0])
    counted = (s > FLOOR_FRAC * peak) & inside
    return {"peak": peak, "area_mm2": float(region.sum() / pxmm ** 2),
            "integral": float(s[counted].sum() / pxmm ** 2),
            "mean_region": float(s[region].mean()) if region.any() else 0.0,
            "n_regions": int(ndi.label(region)[1]), "region": region, "stretch": s,
            "stretch_fine": stretch_map(fl, SIGMA_FINE_T), "fields": fl}
