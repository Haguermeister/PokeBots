"""Screen reader for FRLG on Switch — shiny detection + nature detection.

Uses the same AVFoundation capture device as shiny-bot's check_border.py.
All reference coordinates are defined at 1280x720 and scaled automatically
to the actual capture resolution (e.g. 1920x1080).

Nature detection: On the Gen 3 stats page, the boosted stat name is tinted
red/orange and the lowered stat is tinted blue. By sampling pixel colors at
each stat label position, we can identify the nature without OCR.

Shiny detection: Reuses the proven border color sampling from check_border.
"""

from __future__ import annotations

import cv2
import numpy as np
import time
from pathlib import Path
import json

CAPTURE_INDEX = 0
BASE_DIR = Path(__file__).resolve().parent
CALIBRATION_FILE = BASE_DIR / "screen_calibration.json"

# ── Shiny border detection (from check_border.py) ─────────────────────────
NORMAL_R, NORMAL_G, NORMAL_B = 210, 168, 248
COLOR_TOLERANCE = 15
NORMAL_COLOR = np.array([NORMAL_B, NORMAL_G, NORMAL_R], dtype=np.uint8)
NORMAL_COLOR_I16 = NORMAL_COLOR.astype(np.int16)

# Reference resolution for all pixel coordinates below
REF_W, REF_H = 1280, 720

BORDER_SAMPLE_POINTS_REF = np.array([
    [800, 151], [848, 178], [800, 202], [775, 169],
], dtype=np.int32)
MIN_DEVIANT_POINTS = 3

# Summary screen marker (cyan icon top-right)
SUMMARY_MARKER_POINT_REF = (1133, 63)
SUMMARY_MARKER_RGB = (107, 218, 212)
STATE_TOLERANCE = 16


def _scale_point(x: int, y: int, cap_w: int, cap_h: int) -> tuple[int, int]:
    """Scale a 720p reference coordinate to actual capture resolution."""
    return int(x * cap_w / REF_W), int(y * cap_h / REF_H)


def _scale_points_array(pts: np.ndarray, cap_w: int, cap_h: int) -> np.ndarray:
    """Scale an array of 720p reference points to actual capture resolution."""
    sx = cap_w / REF_W
    sy = cap_h / REF_H
    scaled = pts.astype(np.float64)
    scaled[:, 0] *= sx
    scaled[:, 1] *= sy
    return scaled.astype(np.int32)

# ── Nature detection via stat label colors ─────────────────────────────────
# On the FRLG stats page, stat labels are normally white/light gray.
# Boosted stat: reddish tint (R > G, R > B significantly)
# Lowered stat: bluish tint (B > R, B > G significantly)
#
# These pixel positions point to the middle of each stat name text.
# Default positions assume standard NSO GBA rendering on 720p output.
# User should calibrate with pixel_tools if these don't match.

DEFAULT_STAT_LABEL_POINTS_REF = {
    "atk": (283, 256),
    "def": (283, 288),
    "spa": (283, 336),
    "spd": (283, 368),
    "spe": (283, 400),
}

# Thresholds for color classification
RED_THRESHOLD = 30    # R - max(G,B) must exceed this for "boosted"
BLUE_THRESHOLD = 30   # B - max(R,G) must exceed this for "lowered"

# Nature lookup: (boosted_stat, lowered_stat) -> nature name
# Stats: atk=1, def=2, spe=3, spa=4, spd=5
_STAT_NAMES = ["atk", "def", "spe", "spa", "spd"]
NATURE_FROM_STATS: dict[tuple[str, str], str] = {}
NATURES = [
    "Hardy", "Lonely", "Brave", "Adamant", "Naughty",
    "Bold", "Docile", "Relaxed", "Impish", "Lax",
    "Timid", "Hasty", "Serious", "Jolly", "Naive",
    "Modest", "Mild", "Quiet", "Bashful", "Rash",
    "Calm", "Gentle", "Sassy", "Careful", "Quirky",
]
for _i, _name in enumerate(NATURES):
    _up = _i // 5
    _down = _i % 5
    if _up != _down:
        NATURE_FROM_STATS[(_STAT_NAMES[_up], _STAT_NAMES[_down])] = _name


def load_calibration() -> dict:
    """Load calibrated pixel positions if available."""
    if CALIBRATION_FILE.exists():
        try:
            with open(CALIBRATION_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_calibration(data: dict):
    """Save calibrated pixel positions."""
    with open(CALIBRATION_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_stat_label_points_ref() -> dict[str, tuple[int, int]]:
    """Get stat label pixel positions at 720p reference resolution."""
    cal = load_calibration()
    if "stat_labels" in cal:
        return {k: tuple(v) for k, v in cal["stat_labels"].items()}
    return dict(DEFAULT_STAT_LABEL_POINTS_REF)


def detect_game_area(frame: np.ndarray) -> tuple[int, int, int, int] | None:
    """Find the GBA game area within the capture frame (black border detection).

    Returns (x0, y0, x1, y1) of the game area, or None if not detected.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    col_means = gray.mean(axis=0)
    row_means = gray.mean(axis=1)

    non_black_cols = np.where(col_means > 10)[0]
    non_black_rows = np.where(row_means > 10)[0]

    if len(non_black_cols) < 10 or len(non_black_rows) < 10:
        return None

    x0 = int(non_black_cols[0])
    x1 = int(non_black_cols[-1])
    y0 = int(non_black_rows[0])
    y1 = int(non_black_rows[-1])

    game_w = x1 - x0
    game_h = y1 - y0
    if game_w < 100 or game_h < 100:
        return None

    return (x0, y0, x1, y1)


class ScreenReader:
    """Capture and analyze Switch screen output."""

    def __init__(self):
        self.cap = None
        self.cap_w = REF_W
        self.cap_h = REF_H
        self.stat_points_ref = get_stat_label_points_ref()
        # Scaled versions (updated in open())
        self.border_points = BORDER_SAMPLE_POINTS_REF.copy()
        self.summary_marker = SUMMARY_MARKER_POINT_REF
        self.stat_points: dict[str, tuple[int, int]] = dict(self.stat_points_ref)

    def _update_scaling(self, w: int, h: int):
        """Recompute all scaled coordinates for actual capture resolution."""
        self.cap_w, self.cap_h = w, h
        self.border_points = _scale_points_array(BORDER_SAMPLE_POINTS_REF, w, h)
        self.summary_marker = _scale_point(*SUMMARY_MARKER_POINT_REF, w, h)
        self.stat_points = {
            k: _scale_point(*v, w, h) for k, v in self.stat_points_ref.items()
        }
        print(f"Screen reader: capture {w}x{h}, scale {w/REF_W:.2f}x{h/REF_H:.2f}")

    def open(self) -> bool:
        """Open the capture device and detect resolution."""
        if self.cap is not None and self.cap.isOpened():
            return True
        self.cap = cv2.VideoCapture(CAPTURE_INDEX, cv2.CAP_AVFOUNDATION)
        if not self.cap.isOpened():
            print("Could not open capture device")
            return False
        # Warm up and detect resolution
        for _ in range(5):
            ret, frame = self.cap.read()
        if ret and frame is not None:
            h, w = frame.shape[:2]
            if w != self.cap_w or h != self.cap_h:
                self._update_scaling(w, h)
        return True

    def close(self):
        """Release the capture device."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def grab_frame(self) -> np.ndarray | None:
        """Capture a single frame."""
        if self.cap is None or not self.cap.isOpened():
            if not self.open():
                return None
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return None
        return frame

    def save_debug_frame(self, frame: np.ndarray, name: str = "debug_frame"):
        """Save a frame for debugging."""
        path = BASE_DIR / f"{name}.png"
        cv2.imwrite(str(path), frame)
        print(f"Saved debug frame: {path}")

    # ── Shiny Detection ──

    def check_shiny(self, seconds: float = 3.0) -> bool:
        """Watch for shiny border color over a time window.

        Returns True if a shiny is detected (consistent deviant border).
        First verifies we're actually on the summary page by checking that
        most border points currently match NORMAL_COLOR.
        """
        if not self.open():
            return False

        # Baseline check: verify we're on the summary page.
        # At least 2 of the border points must match NORMAL_COLOR
        # before we start watching for deviations.
        baseline_ok = False
        for _ in range(10):
            ret, frame = self.cap.read()
            if not ret or frame is None:
                continue
            normal_count = self._count_border_normals(frame)
            if normal_count >= 2:
                baseline_ok = True
                break
        if not baseline_ok:
            self.save_debug_frame(frame if frame is not None else np.zeros((1,1,3), dtype=np.uint8), "shiny_baseline_fail")
            return False

        start = time.time()
        consecutive_hits = 0
        frame_count = 0

        while time.time() - start < seconds:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                continue

            frame_count += 1
            if frame_count % 5 != 0:  # sample every 5th frame
                continue

            deviant = self._count_border_deviants(frame)
            if deviant >= MIN_DEVIANT_POINTS:
                consecutive_hits += 1
            else:
                consecutive_hits = 0

            if consecutive_hits >= 3:
                # Confirmation pass
                confirm_hits = 0
                for _ in range(8):
                    ret2, frame2 = self.cap.read()
                    if ret2 and frame2 is not None:
                        if self._count_border_deviants(frame2) >= MIN_DEVIANT_POINTS:
                            confirm_hits += 1
                if confirm_hits >= 5:
                    self.save_debug_frame(frame, "shiny_detected")
                    return True
                consecutive_hits = 0

        return False

    def _count_border_normals(self, frame: np.ndarray) -> int:
        """Count how many border sample points match the normal color."""
        count = 0
        for (x, y) in self.border_points:
            h, w = frame.shape[:2]
            if x < 0 or y < 0 or x >= w or y >= h:
                continue
            pixel = frame[y, x].astype(np.int16)
            diff = np.abs(pixel - NORMAL_COLOR_I16)
            if np.all(diff <= COLOR_TOLERANCE):
                count += 1
        return count

    def _count_border_deviants(self, frame: np.ndarray) -> int:
        """Count how many border sample points deviate from normal color."""
        count = 0
        for (x, y) in self.border_points:
            h, w = frame.shape[:2]
            if x < 0 or y < 0 or x >= w or y >= h:
                continue
            pixel = frame[y, x].astype(np.int16)
            diff = np.abs(pixel - NORMAL_COLOR_I16)
            if np.any(diff > COLOR_TOLERANCE):
                count += 1
        return count

    # ── Summary Screen Detection ──

    def is_on_summary(self, frame: np.ndarray | None = None) -> bool:
        """Check if the screen shows the Pokemon summary page."""
        if frame is None:
            frame = self.grab_frame()
        if frame is None:
            return False

        x, y = self.summary_marker
        h, w = frame.shape[:2]
        if x >= w or y >= h:
            return False

        b, g, r = frame[y, x]
        expected = SUMMARY_MARKER_RGB
        return (abs(int(r) - expected[0]) <= STATE_TOLERANCE
                and abs(int(g) - expected[1]) <= STATE_TOLERANCE
                and abs(int(b) - expected[2]) <= STATE_TOLERANCE)

    # ── Screen State Detection ──

    def detect_screen_state(self, frame: np.ndarray | None = None) -> str:
        """Detect current screen state from capture.

        Returns one of:
            "home_menu"   - Switch HOME menu (game closed or suspended)
            "game"        - GBA game is visible (no HOME overlay)
            "black"       - Black/loading screen
            "unknown"     - Cannot determine
        """
        if frame is None:
            frame = self.grab_frame()
        if frame is None:
            return "unknown"

        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Check overall brightness
        mean_brightness = float(gray.mean())

        # Very dark = black/loading screen
        if mean_brightness < 15:
            return "black"

        # GBA game: has black borders (sides are dark, center is bright)
        # Check if there's a clear game area with black borders
        game_area = detect_game_area(frame)
        if game_area is not None:
            x0, y0, x1, y1 = game_area
            game_region = gray[y0:y1, x0:x1]
            game_brightness = float(game_region.mean())

            # Left and right borders should be very dark
            left_border = gray[:, :max(1, x0)].mean() if x0 > 10 else 999
            right_border = gray[:, min(w-1, x1):].mean() if x1 < w - 10 else 999

            # GBA game: bright center, dark borders
            if game_brightness > 30 and left_border < 15 and right_border < 15:
                return "game"

        # HOME menu: medium brightness, no sharp black borders
        # HOME has a distinctive UI with rounded corners, icons, etc.
        # Sample specific HOME menu landmarks
        if 40 < mean_brightness < 120:
            # HOME menu typically has a darker top bar and brighter bottom
            top_strip = gray[0:h//8, :].mean()
            bottom_strip = gray[7*h//8:, :].mean()
            # HOME menu has consistent mid-brightness across the frame
            if abs(top_strip - bottom_strip) < 40:
                return "home_menu"

        # Bright frame without clear black borders = likely HOME or overlay
        if mean_brightness > 40 and game_area is None:
            return "home_menu"

        return "unknown"

    def is_game_visible(self, frame: np.ndarray | None = None) -> bool:
        """Check if the GBA game is currently rendering (no HOME overlay)."""
        return self.detect_screen_state(frame) == "game"

    def is_on_home(self, frame: np.ndarray | None = None) -> bool:
        """Check if we're on the Switch HOME menu."""
        return self.detect_screen_state(frame) == "home_menu"

    def wait_for_game(self, timeout: float = 15.0) -> bool:
        """Wait until the GBA game is visible on screen."""
        if not self.open():
            return False
        start = time.time()
        hits = 0
        while time.time() - start < timeout:
            frame = self.grab_frame()
            if frame is not None and self.is_game_visible(frame):
                hits += 1
                if hits >= 3:
                    return True
            else:
                hits = 0
            time.sleep(0.1)
        return False

    def wait_for_home(self, timeout: float = 10.0) -> bool:
        """Wait until the HOME menu appears."""
        if not self.open():
            return False
        start = time.time()
        hits = 0
        while time.time() - start < timeout:
            frame = self.grab_frame()
            if frame is not None and self.is_on_home(frame):
                hits += 1
                if hits >= 3:
                    return True
            else:
                hits = 0
            time.sleep(0.1)
        return False

        x, y = self.summary_marker
        h, w = frame.shape[:2]
        if x >= w or y >= h:
            return False

        b, g, r = frame[y, x]
        expected = SUMMARY_MARKER_RGB
        return (abs(int(r) - expected[0]) <= STATE_TOLERANCE
                and abs(int(g) - expected[1]) <= STATE_TOLERANCE
                and abs(int(b) - expected[2]) <= STATE_TOLERANCE)

    def wait_for_summary(self, timeout: float = 10.0) -> bool:
        """Wait until the summary screen appears."""
        if not self.open():
            return False
        start = time.time()
        hits = 0
        while time.time() - start < timeout:
            frame = self.grab_frame()
            if frame is not None and self.is_on_summary(frame):
                hits += 1
                if hits >= 3:
                    return True
            else:
                hits = 0
            time.sleep(0.05)
        return False

    # ── Nature Detection ──

    def detect_nature(self, frame: np.ndarray | None = None) -> str | None:
        """Detect the nature from stat label colors on the stats page.

        Must be on the stats page of the summary (press Right from info page).
        Returns nature name or None if detection fails.
        Uses scan-based detection: finds red and blue text regions in the
        game area's left side where stat labels appear.
        """
        if frame is None:
            frame = self.grab_frame()
        if frame is None:
            return None

        # Try scan-based detection first (more robust)
        scan_result = self._scan_nature(frame)
        if scan_result is not None:
            return scan_result

        # Fall back to fixed-position sampling
        return self._detect_nature_fixed(frame)

    def _scan_nature(self, frame: np.ndarray) -> str | None:
        """Scan for red/blue tinted text in the game area to detect nature.

        Looks for clusters of red-tinted and blue-tinted pixels in the
        left portion of the game area (where stat labels are).
        Maps pixel y-positions to stat names based on vertical ordering.
        """
        game_area = detect_game_area(frame)
        if game_area is None:
            return None

        x0, y0, x1, y1 = game_area
        game_w = x1 - x0
        game_h = y1 - y0

        # Stat labels are in the left 35% of the game, middle 85% vertically
        # In GBA: stats are roughly x=8-70, y=40-140 out of 240x160
        search_x0 = x0
        search_x1 = x0 + int(game_w * 0.35)
        search_y0 = y0 + int(game_h * 0.2)
        search_y1 = y0 + int(game_h * 0.9)

        region = frame[search_y0:search_y1, search_x0:search_x1]
        if region.size == 0:
            return None

        rf = region[:, :, 2].astype(np.float32)
        gf = region[:, :, 1].astype(np.float32)
        bf = region[:, :, 0].astype(np.float32)

        # Minimum brightness to avoid dark background pixels.
        # Stat label text is bright (>160), background purple is dimmer (~150).
        brightness = np.maximum(np.maximum(rf, gf), bf)

        # Check if the search region has a predominantly white/light background.
        # The stats page has white background for stat labels.
        # The info page has purple background.
        median_brightness = float(np.median(brightness))
        if median_brightness < 160:
            # Background is too dark — probably not on the stats page
            return None

        # Find red-tinted pixels (stat boosted by nature)
        # Stat label red text: R>180, G<130, B<130 → r_excess > 50
        r_excess = rf - np.maximum(gf, bf)
        red_mask = (r_excess > 40) & (brightness > 160)

        # Find blue-tinted pixels (stat lowered by nature)
        # Stat label blue text: R<130, G<130, B>180 → b_excess > 50
        b_excess = bf - np.maximum(rf, gf)
        blue_mask = (b_excess > 40) & (brightness > 160)

        red_count = int(red_mask.sum())
        blue_count = int(blue_mask.sum())

        # Need at least some colored pixels to detect nature
        MIN_COLORED_PX = 15

        if red_count < MIN_COLORED_PX and blue_count < MIN_COLORED_PX:
            # No colored text found on a bright background.
            # This means either neutral nature (no colored stats) or
            # we're on the stats page with a neutral-nature Pokemon.
            return "neutral"

        boosted = None
        lowered = None

        # Define stat y-bands relative to the search region
        # Stats are evenly spaced vertically: ATK, DEF, SP.ATK, SP.DEF, SPEED
        # The region covers about y=0.2 to y=0.9 of game area
        # Stats occupy the middle of that range
        region_h = search_y1 - search_y0
        stat_names_ordered = ["atk", "def", "spa", "spd", "spe"]

        if red_count >= MIN_COLORED_PX:
            red_y_positions = np.where(red_mask)[0]
            red_y_center = float(np.median(red_y_positions))
            # Map y-position to stat index (0-4)
            red_ratio = red_y_center / region_h
            red_idx = min(4, max(0, int(red_ratio * 5)))
            boosted = stat_names_ordered[red_idx]

        if blue_count >= MIN_COLORED_PX:
            blue_y_positions = np.where(blue_mask)[0]
            blue_y_center = float(np.median(blue_y_positions))
            blue_ratio = blue_y_center / region_h
            blue_idx = min(4, max(0, int(blue_ratio * 5)))
            lowered = stat_names_ordered[blue_idx]

        if boosted is not None and lowered is not None:
            key = (boosted, lowered)
            result = NATURE_FROM_STATS.get(key, None)
            if result:
                return result

        # Partial detection
        return None

    def _detect_nature_fixed(self, frame: np.ndarray) -> str | None:
        """Detect nature using fixed pixel positions (legacy method)."""
        boosted = None
        lowered = None

        for stat_name, (x, y) in self.stat_points.items():
            h, w = frame.shape[:2]
            if x >= w or y >= h:
                continue

            # Sample a small region around the point for stability
            y1 = max(0, y - 2)
            y2 = min(h, y + 3)
            x1 = max(0, x - 2)
            x2 = min(w, x + 3)
            region = frame[y1:y2, x1:x2]
            avg_bgr = region.mean(axis=(0, 1))
            b, g, r = avg_bgr[0], avg_bgr[1], avg_bgr[2]

            # Check if this is a colored stat label
            r_excess = r - max(g, b)
            b_excess = b - max(r, g)

            if r_excess > RED_THRESHOLD:
                boosted = stat_name
            elif b_excess > BLUE_THRESHOLD:
                lowered = stat_name

        # Neutral nature: no colored stats
        if boosted is None and lowered is None:
            return "neutral"

        if boosted is not None and lowered is not None:
            key = (boosted, lowered)
            return NATURE_FROM_STATS.get(key, None)

        # Partial detection (shouldn't happen with working calibration)
        return None

    def is_on_stats_page(self, frame: np.ndarray | None = None) -> bool:
        """Check if we're on the summary STATS/SKILLS page (not INFO page).

        The stats page has visible colored stat labels for non-neutral natures,
        and a distinctive HP bar. We check for the presence of any colored
        (red/blue) text in the stat label region.
        """
        if frame is None:
            frame = self.grab_frame()
        if frame is None:
            return False

        game_area = detect_game_area(frame)
        if game_area is None:
            return False

        x0, y0, x1, y1 = game_area
        game_w = x1 - x0
        game_h = y1 - y0

        # The stats page has stat values (numbers) on the right side
        # and a distinctive layout. Check for the presence of any numeric
        # text or colored labels in the stat region.
        # Also: the stats page has a different background pattern than info page.
        # On stats page, the top area shows "POKéMON SKILLS" header with a
        # distinctive bar. Check for non-white, non-purple pixels in the
        # stat label area that indicate stat values are displayed.

        # Sample the center area - on stats page there are numbers,
        # on info page there's a text box with nature description
        mid_x = x0 + int(game_w * 0.5)
        mid_y = y0 + int(game_h * 0.35)

        # On stats page, around this position we should see stat layout
        # On info page, this would be the nature description text box
        # The stat page has a specific orange/brown header bar area
        header_y = y0 + int(game_h * 0.12)
        header_x = x0 + int(game_w * 0.25)

        h, w = frame.shape[:2]
        if header_x >= w or header_y >= h:
            return False

        # Sample a region around the header
        hy1 = max(0, header_y - 5)
        hy2 = min(h, header_y + 5)
        hx1 = max(0, header_x - 20)
        hx2 = min(w, header_x + 20)
        header_region = frame[hy1:hy2, hx1:hx2]
        avg = header_region.mean(axis=(0, 1))
        b, g, r = float(avg[0]), float(avg[1]), float(avg[2])

        # Stats page header has an orange/tan color bar
        # Info page header area would be different (white/purple)
        # This is a heuristic - may need calibration
        if r > 150 and g > 100 and b < 150 and r > b:
            return True

        return False

    def detect_nature_stable(self, num_reads: int = 5, save_debug: bool = True) -> str | None:
        """Read nature multiple times for stability. Saves debug frame."""
        if not self.open():
            return None

        results = []
        debug_frame = None
        for i in range(num_reads):
            frame = self.grab_frame()
            if frame is not None:
                if i == 0 and save_debug:
                    debug_frame = frame.copy()
                nature = self.detect_nature(frame)
                if nature is not None:
                    results.append(nature)
            time.sleep(0.1)

        if debug_frame is not None and save_debug:
            self.save_debug_frame(debug_frame, "nature_detection")

        if not results:
            return None

        # Return the most common result
        from collections import Counter
        most_common = Counter(results).most_common(1)[0]
        if most_common[1] >= 3:  # at least 3 out of 5 agree
            return most_common[0]
        return None

    # ── Pixel Probing (for calibration) ──

    def probe_pixel(self, x: int, y: int, seconds: float = 2.0) -> dict | None:
        """Sample a pixel over time and return RGB statistics."""
        if not self.open():
            return None

        start = time.time()
        samples = []

        while time.time() - start < seconds:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                continue
            h, w = frame.shape[:2]
            if x >= w or y >= h:
                return None
            b, g, r = frame[y, x]
            samples.append((int(r), int(g), int(b)))
            time.sleep(0.02)

        if not samples:
            return None

        arr = np.array(samples)
        return {
            "samples": len(samples),
            "r_avg": float(arr[:, 0].mean()),
            "g_avg": float(arr[:, 1].mean()),
            "b_avg": float(arr[:, 2].mean()),
            "r_min": int(arr[:, 0].min()),
            "g_min": int(arr[:, 1].min()),
            "b_min": int(arr[:, 2].min()),
            "r_max": int(arr[:, 0].max()),
            "g_max": int(arr[:, 1].max()),
            "b_max": int(arr[:, 2].max()),
        }

    def dump_stat_colors(self) -> dict:
        """Debug: capture RGB values at all stat label positions."""
        frame = self.grab_frame()
        if frame is None:
            return {}

        result = {}
        for stat_name, (x, y) in self.stat_points.items():
            h, w = frame.shape[:2]
            if x >= w or y >= h:
                result[stat_name] = {"error": "out of bounds"}
                continue

            y1 = max(0, y - 2)
            y2 = min(h, y + 3)
            x1 = max(0, x - 2)
            x2 = min(w, x + 3)
            region = frame[y1:y2, x1:x2]
            avg_bgr = region.mean(axis=(0, 1))

            result[stat_name] = {
                "r": float(avg_bgr[2]),
                "g": float(avg_bgr[1]),
                "b": float(avg_bgr[0]),
                "position": [x, y],
            }

        self.save_debug_frame(frame, "stat_colors_debug")
        return result


# ── CLI for calibration ──

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Screen reader calibration tools")
    parser.add_argument("--probe", nargs=2, type=int, metavar=("X", "Y"),
                        help="Probe pixel at (X, Y) for 2 seconds")
    parser.add_argument("--dump-stats", action="store_true",
                        help="Dump RGB values at all stat label positions")
    parser.add_argument("--check-shiny", type=float, default=3.0,
                        help="Check for shiny border for N seconds")
    parser.add_argument("--detect-nature", action="store_true",
                        help="Detect nature from stats page")
    parser.add_argument("--save-frame", type=str,
                        help="Save current frame with given name")
    args = parser.parse_args()

    reader = ScreenReader()

    if args.probe:
        x, y = args.probe
        result = reader.probe_pixel(x, y)
        if result:
            print(f"Pixel ({x}, {y}):")
            print(f"  R: {result['r_avg']:.1f} ({result['r_min']}-{result['r_max']})")
            print(f"  G: {result['g_avg']:.1f} ({result['g_min']}-{result['g_max']})")
            print(f"  B: {result['b_avg']:.1f} ({result['b_min']}-{result['b_max']})")
            print(f"  Samples: {result['samples']}")

    elif args.dump_stats:
        result = reader.dump_stat_colors()
        for stat, data in result.items():
            if "error" in data:
                print(f"  {stat}: {data['error']}")
            else:
                print(f"  {stat}: R={data['r']:.0f} G={data['g']:.0f} B={data['b']:.0f} @ ({data['position'][0]}, {data['position'][1]})")

    elif args.check_shiny:
        print(f"Checking for shiny ({args.check_shiny}s)...")
        is_shiny = reader.check_shiny(args.check_shiny)
        print(f"Result: {'SHINY!' if is_shiny else 'Not shiny'}")

    elif args.detect_nature:
        nature = reader.detect_nature_stable()
        print(f"Detected nature: {nature}")

    elif args.save_frame:
        frame = reader.grab_frame()
        if frame is not None:
            reader.save_debug_frame(frame, args.save_frame)

    reader.close()


if __name__ == "__main__":
    main()
