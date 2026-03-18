"""TID/SID auto-detection for FRLG on Switch.

TID Reading:
  Navigate to the trainer card, capture the screen, and read the 5-digit
  Trainer ID using pixel-based digit recognition on the GBA bitmap font.

SID Calculation:
  In FRLG, the LCRNG starts at seed 0 on every boot. TID and SID are
  generated from consecutive LCRNG calls at some advance N (determined by
  how many frames elapsed before the player confirmed New Game).
  Given TID, we search for all advances where high16(state) == TID,
  and SID = high16(advance(state)). Typically yields 1-3 candidates
  in the realistic range.
"""

from __future__ import annotations

import time
import json
import numpy as np
from pathlib import Path

import rng_engine
import pico

try:
    import cv2
except ImportError:
    cv2 = None

BASE_DIR = Path(__file__).resolve().parent
CAPTURE_INDEX = 0

# GBA → capture scaling (dynamically computed from actual frame dimensions)
# GBA native: 240×160, stretched to fill the Switch capture output
GBA_W, GBA_H = 240, 160


def gba_to_cap(gba_x: int, gba_y: int, cap_w: int = 1280, cap_h: int = 720) -> tuple[int, int]:
    """Convert GBA pixel coordinates to capture coordinates."""
    return int(gba_x * cap_w / GBA_W), int(gba_y * cap_h / GBA_H)


# ── SID Calculation from TID ────────────────────────────────────────────────

def find_sids_for_tid(
    tid: int,
    custom_rival_name: bool = True,
    target_advance: int = 1500,
    english_offset: int = 249,
    search_range: int = 40,
) -> list[dict]:
    """Find possible SIDs using Lincoln's tool method.

    Uses TID hex value as the LCRNG initial seed and searches around
    the expected TID generation advance. From Blissey's tutorial:
      actual_advance = (target_advance + english_offset) * 2
      e.g. (1500 + 249) * 2 = 3498

    With custom rival name, only even advances are valid.
    With preset rival name, only odd advances are valid.

    Returns list of {advance, tid, sid} sorted by distance from center.
    """
    center = (target_advance + english_offset) * 2
    min_adv = max(0, center - search_range * 2)
    max_adv = center + search_range * 2

    # Use TID as the initial 32-bit seed (Lincoln's tool approach)
    initial_seed = tid  # 0x0000C169 for TID=49513

    results = []
    for adv in range(min_adv, max_adv + 1):
        # Custom rival name = even advances, preset = odd advances
        if custom_rival_name and adv % 2 != 0:
            continue
        if not custom_rival_name and adv % 2 != 1:
            continue

        state = rng_engine.advance_n(initial_seed, adv)
        sid = rng_engine.high16(state)
        results.append({
            "advance": adv,
            "tid": tid,
            "sid": sid,
        })

    # Sort by distance from center advance (most likely first)
    results.sort(key=lambda r: abs(r["advance"] - center))
    return results


def find_sids_bruteforce(
    tid: int,
    min_advance: int = 1000,
    max_advance: int = 500000,
) -> list[dict]:
    """Find SIDs by brute-force searching LCRNG from seed 0.

    Slower but useful as a fallback. Searches for all advances where
    high16(state) == TID. This finds where the TID would appear in the
    raw LCRNG sequence from seed 0.
    """
    results = []
    seed = rng_engine.advance_n(0, min_advance)
    for adv in range(min_advance, max_advance + 1):
        if rng_engine.high16(seed) == tid:
            sid = rng_engine.high16(rng_engine.advance(seed))
            results.append({
                "advance": adv,
                "tid": tid,
                "sid": sid,
            })
        seed = rng_engine.advance(seed)
    results.sort(key=lambda r: r["advance"])
    return results


def narrow_sid_candidates(
    candidates: list[dict],
    initial_seed: int,
    tid: int,
    test_advance: int,
    was_shiny: bool,
) -> list[dict]:
    """Narrow SID candidates using a test RNG manipulation result.

    Given that we did a manipulation at test_advance from initial_seed,
    and the result was/wasn't shiny, eliminate incompatible SIDs.
    """
    # Get the PID at test_advance
    pkmn = rng_engine.method1_pokemon(
        rng_engine.advance_n(initial_seed, test_advance), tid, 0,
    )
    pid_high = (pkmn["pid"] >> 16) & 0xFFFF
    pid_low = pkmn["pid"] & 0xFFFF

    narrowed = []
    for c in candidates:
        sid = c["sid"]
        shiny_val = tid ^ sid ^ pid_high ^ pid_low
        would_be_shiny = shiny_val < 8
        if would_be_shiny == was_shiny:
            narrowed.append(c)

    return narrowed


# ── TID Screen Reading ──────────────────────────────────────────────────────

# FRLG Trainer Card layout (GBA pixel coordinates, approximate):
# The ID number "XXXXX" appears on the trainer card.
# These positions are for the FRLG English trainer card.
# The IDNo. label is at approximately GBA (96, 41), digits start at (128, 41)
# Each digit is 6 pixels wide with 1px spacing in GBA coords.

# Capture coordinates for the ID number region
ID_REGION_GBA = {
    "x_start": 128,   # GBA x where first digit starts
    "y": 41,           # GBA y of the digit baseline
    "digit_w": 6,      # GBA width per digit
    "digit_h": 10,     # GBA height per digit
    "digit_gap": 1,    # GBA gap between digits
    "num_digits": 5,
}

# Pre-computed digit templates (pixel patterns at GBA resolution).
# These are filled in during calibration or from known GBA font data.
# Format: dict mapping digit (0-9) to set of (dx, dy) positions that
# should be "on" (bright) relative to the digit's top-left corner.
# We'll use runtime calibration instead of hardcoding these.


def navigate_to_trainer_card() -> bool:
    """Navigate from overworld to the trainer card screen.

    Start menu → 4th option (player name/trainer card).
    """
    def press(btn, hold=120, delay=0.3):
        result = pico.send_cmd(f"press {btn} {hold}")
        if not result.startswith("OK"):
            return False
        if delay > 0:
            time.sleep(delay)
        return True

    def dpad(direction, hold=120, delay=0.25):
        result = pico.send_cmd(f"dpad {direction} {hold}")
        if not result.startswith("OK"):
            return False
        if delay > 0:
            time.sleep(delay)
        return True

    # Open menu (X = GBA Start on NSO)
    press("X", delay=1.0)

    # Navigate down to trainer card (4th item: POKéDEX, POKéMON, BAG, [name])
    dpad("DOWN")
    dpad("DOWN")
    dpad("DOWN")

    # Select trainer card
    press("A", delay=1.5)

    return True


def navigate_back_from_trainer_card() -> bool:
    """Go back from trainer card to overworld."""
    result = pico.send_cmd("press B 120")
    time.sleep(0.5)
    result = pico.send_cmd("press B 120")
    time.sleep(0.5)
    return True


def capture_frame() -> np.ndarray | None:
    """Capture a single frame from the Switch output."""
    if cv2 is None:
        return None
    cap = cv2.VideoCapture(CAPTURE_INDEX, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        return None

    # Warm up
    for _ in range(5):
        cap.read()

    # Capture
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        return None
    return frame


def capture_stable_frame(num_frames: int = 10) -> np.ndarray | None:
    """Capture multiple frames and return the last one (most stable)."""
    if cv2 is None:
        return None
    cap = cv2.VideoCapture(CAPTURE_INDEX, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        return None

    frame = None
    for _ in range(num_frames):
        ret, f = cap.read()
        if ret and f is not None:
            frame = f
        time.sleep(0.05)

    cap.release()
    return frame


def read_tid_from_frame(frame: np.ndarray) -> int | None:
    """Attempt to read the 5-digit TID from a trainer card screenshot.

    Uses color-based text extraction and connected component analysis
    to identify digits in the ID number region.
    """
    if cv2 is None:
        return None

    # Convert the ID region to capture coordinates
    cfg = ID_REGION_GBA
    h, w = frame.shape[:2]
    x1, y1 = gba_to_cap(cfg["x_start"] - 4, cfg["y"] - 2, w, h)
    total_w_gba = cfg["num_digits"] * (cfg["digit_w"] + cfg["digit_gap"]) + 8
    x2, y2 = gba_to_cap(cfg["x_start"] + total_w_gba, cfg["y"] + cfg["digit_h"] + 2, w, h)

    h, w = frame.shape[:2]
    x1 = max(0, min(x1, w - 1))
    x2 = max(0, min(x2, w - 1))
    y1 = max(0, min(y1, h - 1))
    y2 = max(0, min(y2, h - 1))

    # Crop the region
    roi = frame[y1:y2, x1:x2]

    # Save debug image
    debug_path = BASE_DIR / "debug_tid_region.png"
    cv2.imwrite(str(debug_path), roi)

    # Convert to grayscale
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    # The text on the trainer card is bright (white/light) on a darker background.
    # Apply adaptive threshold to extract text.
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Save debug binary
    cv2.imwrite(str(BASE_DIR / "debug_tid_binary.png"), binary)

    # Find contours (connected components = potential digits)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Filter contours by size (digits should be roughly the right height)
    x_scale = w / GBA_W
    y_scale = h / GBA_H
    digit_h_cap = int(cfg["digit_h"] * y_scale)
    digit_w_cap = int(cfg["digit_w"] * x_scale)

    digit_candidates = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        # Digit should be taller than wide and within expected size range
        if ch > digit_h_cap * 0.3 and cw > digit_w_cap * 0.3:
            if ch < digit_h_cap * 2.5 and cw < digit_w_cap * 2.5:
                digit_candidates.append((x, y, cw, ch))

    if len(digit_candidates) < 5:
        # Try inverted threshold
        _, binary_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        cv2.imwrite(str(BASE_DIR / "debug_tid_binary_inv.png"), binary_inv)
        contours, _ = cv2.findContours(binary_inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        digit_candidates = []
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            if ch > digit_h_cap * 0.3 and cw > digit_w_cap * 0.3:
                if ch < digit_h_cap * 2.5 and cw < digit_w_cap * 2.5:
                    digit_candidates.append((x, y, cw, ch))
        binary = binary_inv

    # Sort by x position (left to right)
    digit_candidates.sort(key=lambda d: d[0])

    # We need exactly 5 digits
    if len(digit_candidates) < 5:
        return None

    # Take the 5 most likely contiguous digits
    # Group by proximity — digits should be roughly evenly spaced
    if len(digit_candidates) > 5:
        # Find the best group of 5 with consistent spacing
        best_group = digit_candidates[:5]
        # TODO: smarter grouping if needed
        digit_candidates = best_group

    # Extract each digit image and try to recognize it
    digits = []
    for x, y, cw, ch in digit_candidates[:5]:
        digit_img = binary[y:y+ch, x:x+cw]
        digit_val = _recognize_digit(digit_img)
        if digit_val is None:
            return None
        digits.append(digit_val)

    if len(digits) == 5:
        tid = int("".join(str(d) for d in digits))
        if 0 <= tid <= 65535:
            return tid

    return None


def _recognize_digit(img: np.ndarray) -> int | None:
    """Recognize a single digit from a binary image.

    Uses a simple feature-based approach:
    - Divide digit into a 3×5 grid
    - Count white pixels in each cell
    - Match against known patterns
    """
    if img is None or img.size == 0:
        return None

    h, w = img.shape[:2]
    if h < 3 or w < 3:
        return None

    # Resize to standard size for consistent matching
    std = cv2.resize(img, (12, 20), interpolation=cv2.INTER_NEAREST)

    # Divide into 3 columns × 5 rows grid
    grid = []
    cell_h = 20 // 5  # 4 pixels
    cell_w = 12 // 3  # 4 pixels

    for row in range(5):
        for col in range(3):
            cell = std[row*cell_h:(row+1)*cell_h, col*cell_w:(col+1)*cell_w]
            # Fraction of white pixels
            frac = np.sum(cell > 127) / cell.size
            grid.append(1 if frac > 0.4 else 0)

    # Known digit patterns (3×5 grid, row-major):
    # These patterns represent the Gen 3 bitmap font
    patterns = {
        0: [1,1,1, 1,0,1, 1,0,1, 1,0,1, 1,1,1],
        1: [0,1,0, 1,1,0, 0,1,0, 0,1,0, 1,1,1],
        2: [1,1,1, 0,0,1, 1,1,1, 1,0,0, 1,1,1],
        3: [1,1,1, 0,0,1, 1,1,1, 0,0,1, 1,1,1],
        4: [1,0,1, 1,0,1, 1,1,1, 0,0,1, 0,0,1],
        5: [1,1,1, 1,0,0, 1,1,1, 0,0,1, 1,1,1],
        6: [1,1,1, 1,0,0, 1,1,1, 1,0,1, 1,1,1],
        7: [1,1,1, 0,0,1, 0,1,0, 0,1,0, 0,1,0],
        8: [1,1,1, 1,0,1, 1,1,1, 1,0,1, 1,1,1],
        9: [1,1,1, 1,0,1, 1,1,1, 0,0,1, 1,1,1],
    }

    # Find best match
    best_digit = None
    best_score = -1
    for digit, pattern in patterns.items():
        score = sum(1 for a, b in zip(grid, pattern) if a == b)
        if score > best_score:
            best_score = score
            best_digit = digit

    # Require at least 80% match
    if best_score >= 12:  # 12/15 = 80%
        return best_digit

    return None


def auto_detect_tid_sid() -> dict:
    """Full automated TID/SID detection flow.

    1. Navigate to trainer card
    2. Capture screen
    3. Read TID using digit recognition
    4. Compute SID candidates from LCRNG
    5. Return results

    Returns dict with tid, sid_candidates, status, etc.
    """
    result = {
        "status": "error",
        "tid": None,
        "sid": None,
        "sid_candidates": [],
        "message": "",
        "debug_image": None,
    }

    # Navigate to trainer card
    if not navigate_to_trainer_card():
        result["message"] = "Failed to navigate to trainer card"
        return result

    # Wait for card to render
    time.sleep(1.0)

    # Capture screen
    frame = capture_stable_frame(num_frames=15)
    if frame is None:
        result["message"] = "Could not capture screen"
        navigate_back_from_trainer_card()
        return result

    # Save full debug frame
    debug_path = BASE_DIR / "debug_trainer_card.png"
    if cv2 is not None:
        cv2.imwrite(str(debug_path), frame)
    result["debug_image"] = str(debug_path)

    # Try to read TID
    tid = read_tid_from_frame(frame)

    # Navigate back
    navigate_back_from_trainer_card()

    if tid is None:
        result["message"] = (
            "Could not read TID from screen. "
            "Debug images saved to rng-bot/debug_*.png. "
            "Please enter TID manually."
        )
        result["status"] = "manual_needed"
        return result

    result["tid"] = tid

    # Compute SID candidates
    candidates = find_sids_for_tid(tid)
    result["sid_candidates"] = candidates

    if len(candidates) == 0:
        result["message"] = f"TID {tid} read successfully but no SID candidates found. Try entering SID manually."
        result["status"] = "tid_only"
    elif len(candidates) == 1:
        result["sid"] = candidates[0]["sid"]
        result["message"] = f"TID={tid} SID={candidates[0]['sid']} (auto-detected, advance {candidates[0]['advance']})"
        result["status"] = "success"
    else:
        # Multiple candidates — use the most likely one (lowest advance = fastest menu nav)
        result["sid"] = candidates[0]["sid"]
        result["message"] = (
            f"TID={tid}, {len(candidates)} possible SIDs found. "
            f"Using most likely: SID={candidates[0]['sid']} (advance {candidates[0]['advance']}). "
            f"If shinies don't work, try other candidates."
        )
        result["status"] = "success_multiple"

    return result
