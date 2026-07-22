import cv2
import numpy as np
import pandas as pd

# ====================================================================
# ColorPredictor
# ====================================================================

class ColorPredictor:
    """
    Predicts temperature from a (purple) stripe pixel using inverse-distance
    weighted k-nearest-neighbours over RGB, HSV, and/or LAB colour spaces.

    The CSV must contain a temperature column plus at least one set of colour
    columns: R/G/B, H/S/V, and/or L/A/B (case-insensitive).
    When color_space='auto' the space whose nearest neighbour is closest is
    used for the final prediction; otherwise the named space
    ('rgb' | 'hsv' | 'lab') is used.

    Each space's features are min-max normalised per channel (using the
    calibration ranges) before distances are computed, so that the 'auto'
    comparison is scale-fair across RGB (0-255), HSV (H 0-180) and LAB.
    """

    _SPACE_COLS = {"rgb": ["R", "G", "B"], "hsv": ["H", "S", "V"], "lab": ["L", "A", "B"]}

    def __init__(self, csv_file, target_col, color_space="auto", n_neighbors=3):
        self.csv_file    = csv_file
        self.target_col  = target_col
        self.color_space = color_space.lower()
        self.n_neighbors = n_neighbors
        self.ref_temps   = None
        self.cal_rgb     = None
        self.cal_hsv     = None
        self.cal_lab     = None
        self._mins       = {}     # per-space channel minimums
        self._rng        = {}     # per-space channel ranges (max-min)
        self._cal_n      = {}     # per-space normalised calibration features

    def load_reference(self):
        df = pd.read_csv(self.csv_file)
        df.columns = [c.strip() for c in df.columns]
        col_upper = {c.upper(): c for c in df.columns}
        self.ref_temps = df[self.target_col].values.astype(float)
        # Load whichever colour-space columns are present
        for space, cols in self._SPACE_COLS.items():
            if all(c in col_upper for c in cols):
                setattr(self, f"cal_{space}",
                        df[[col_upper[c] for c in cols]].values.astype(float))
        available = [s for s in ("rgb", "hsv", "lab") if getattr(self, f"cal_{s}") is not None]
        if not available:
            raise ValueError("CSV must contain at least one of: R/G/B, H/S/V, L/A/B columns.")
        if self.color_space != "auto" and self.color_space not in available:
            raise ValueError(f"Color space '{self.color_space}' columns not found in CSV. "
                             f"Available: {available}")
        # Per-space min-max normalisation (from the calibration data)
        for space in available:
            cal = getattr(self, f"cal_{space}")
            mins = cal.min(axis=0)
            rng = cal.max(axis=0) - mins
            rng = np.where(rng > 0, rng, 1.0)
            self._mins[space] = mins
            self._rng[space] = rng
            self._cal_n[space] = (cal - mins) / rng
        print(f"Reference loaded: {len(self.ref_temps)} points  "
              f"({self.ref_temps.min():.1f} → {self.ref_temps.max():.1f} °)  "
              f"spaces: {available}")

    # ------------------------------------------------------------------
    @staticmethod
    def _pixel_to_all_spaces(R, G, B):
        """Convert a single 0-255 RGB pixel to HSV and LAB via OpenCV."""
        px  = np.array([[[int(B), int(G), int(R)]]], dtype=np.uint8)  # BGR for cv2
        hsv = cv2.cvtColor(px, cv2.COLOR_BGR2HSV)[0, 0].astype(float)
        lab = cv2.cvtColor(px, cv2.COLOR_BGR2LAB)[0, 0].astype(float)
        return np.array([R, G, B], dtype=float), hsv, lab

    @staticmethod
    def _weighted_knn(query, cal_features, cal_temps, k):
        """Inverse-distance weighted k-NN regression."""
        dists = np.linalg.norm(cal_features - query, axis=1)
        idx   = np.argsort(dists)[:k]
        top_dists = dists[idx]
        top_temps = cal_temps[idx]
        if top_dists[0] < 1e-9:           # exact match
            return float(top_temps[0]), top_temps, top_dists
        weights = 1.0 / top_dists
        T_pred  = float(np.dot(weights, top_temps) / weights.sum())
        return T_pred, top_temps, top_dists

    def sample_neighborhood(self, img_rgb, mask, cx, cy, radius):
        """
        Return mean (R, G, B) in a circular patch around (cx, cy) inside mask.
        Sampling is done in RGB so the average pixel can be evaluated in every
        colour space inside predict() (needed for 'auto').
        """
        h, w = mask.shape
        y0, y1 = max(0, cy - radius), min(h, cy + radius + 1)
        x0, x1 = max(0, cx - radius), min(w, cx + radius + 1)
        patch_rgb  = img_rgb[y0:y1, x0:x1].astype(float)
        patch_mask = mask[y0:y1, x0:x1]
        yy, xx   = np.ogrid[:patch_rgb.shape[0], :patch_rgb.shape[1]]
        circ     = (xx - (cx - x0))**2 + (yy - (cy - y0))**2 <= radius**2
        combined = (patch_mask > 0) & circ
        pixels   = patch_rgb[combined]       # (N, 3) RGB
        if len(pixels) == 0:
            return None, 0
        return pixels.mean(axis=0), len(pixels)   # mean RGB

    def predict(self, avg_rgb):
        """
        Predict temperature from an average RGB value (0-255 scale).

        Returns
        -------
        temp       : float  — predicted temperature
        top_temps  : array  — k nearest calibration temperatures
        top_dists  : array  — their Euclidean distances
        cs_used    : str    — colour space chosen ('rgb' | 'hsv' | 'lab')
        confidence : float  — 0-100 %
        """
        if self.ref_temps is None:
            raise RuntimeError("Call load_reference() before predict().")
        R, G, B = avg_rgb
        rgb_feat, hsv_feat, lab_feat = self._pixel_to_all_spaces(R, G, B)
        feat_map = {"rgb": rgb_feat, "hsv": hsv_feat, "lab": lab_feat}

        def query_n(space):
            return (feat_map[space] - self._mins[space]) / self._rng[space]

        cs = self.color_space
        if cs == "auto":
            best_result, best_min_dist = None, np.inf
            for space in ("rgb", "hsv", "lab"):
                if self._cal_n.get(space) is None:
                    continue
                T, tt, td = self._weighted_knn(query_n(space), self._cal_n[space],
                                               self.ref_temps, self.n_neighbors)
                if td[0] < best_min_dist:
                    best_min_dist = td[0]
                    best_result = (T, tt, td, space)
            temp, top_temps, top_dists, cs_used = best_result
        else:
            if self._cal_n.get(cs) is None:
                raise ValueError(f"Color space '{cs}' columns not found in CSV.")
            temp, top_temps, top_dists = self._weighted_knn(query_n(cs), self._cal_n[cs],
                                                            self.ref_temps, self.n_neighbors)
            cs_used = cs

        confidence = (1.0 - top_dists[0] / (top_dists.max() + 1e-9)) * 100
        return temp, top_temps, top_dists, cs_used, confidence