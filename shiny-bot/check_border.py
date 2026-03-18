import cv2
import numpy as np
import argparse
import time
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
CAPTURE_INDEX = 0

# -----------------------------
# Normal (non-shiny) border color of the Pokemon sprite
# -----------------------------
NORMAL_R = 210
NORMAL_G = 168
NORMAL_B = 248

# How far a pixel can deviate from normal and still count as "normal"
COLOR_TOLERANCE = 15
NORMAL_COLOR = np.array([NORMAL_B, NORMAL_G, NORMAL_R], dtype=np.uint8)
NORMAL_COLOR_I16 = NORMAL_COLOR.astype(np.int16)

# Sample points along the Pokemon sprite border (x, y)
# Spread around: top, right, bottom, left edges
BORDER_SAMPLE_POINTS = np.array([
    [800, 151],   # top-center
    [848, 178],   # right-middle
    [800, 202],   # bottom-center
    [775, 169],   # left-middle
], dtype=np.int32)

# Pre-calculated crop region for ROI optimization
CROP_LEFT = 750
CROP_TOP = 130
CROP_RIGHT = 870
CROP_BOTTOM = 220
CROP_POINTS = np.array([
    [p[0] - CROP_LEFT, p[1] - CROP_TOP]
    for p in BORDER_SAMPLE_POINTS
], dtype=np.int32)

# How many sample points must differ from normal to flag shiny
MIN_DEVIANT_POINTS = 3

CONSECUTIVE_FRAMES_REQUIRED = 3
FRAME_SAMPLE_STRIDE = 10
LOG_EVERY_SAMPLED_FRAMES = 3
CONFIRMATION_FRAMES = 8
MIN_CONFIRMATION_HITS = 5

# Calibrated UI state markers (full-frame coordinates)
SUMMARY_MARKER_POINT = (1133, 63)
SUMMARY_MARKER_RGB = (107, 218, 212)
STARTER_BALL_POINT = (958, 413)
UNPICKED_STARTER_RGB = (245, 98, 70)
PICKED_STARTER_RGB = (140, 219, 138)
STATE_TOLERANCE = 16


def confirm_candidate_shiny(cap) -> bool:
    """Run a short high-frequency confirmation pass after a candidate hit."""
    hits = 0
    consecutive_hits = 0

    for _ in range(CONFIRMATION_FRAMES):
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        frame = frame[CROP_TOP:CROP_BOTTOM, CROP_LEFT:CROP_RIGHT]
        shiny, _ = check_border_pixels(frame, CROP_POINTS)
        if shiny:
            hits += 1
            consecutive_hits += 1
        else:
            consecutive_hits = 0

    # Require both a strong hit count and a stable consecutive run.
    return hits >= MIN_CONFIRMATION_HITS and consecutive_hits >= CONSECUTIVE_FRAMES_REQUIRED


def check_border_pixels(frame: np.ndarray, sample_points) -> tuple[bool, int]:
    """Sample border pixels vectorized. Returns (is_shiny, deviant_count)."""
    h, w = frame.shape[:2]
    valid = (
        (sample_points[:, 0] >= 0)
        & (sample_points[:, 1] >= 0)
        & (sample_points[:, 0] < w)
        & (sample_points[:, 1] < h)
    )
    if not np.any(valid):
        return False, 0

    pts = sample_points[valid]
    pixels = frame[pts[:, 1], pts[:, 0]].astype(np.int16)
    diff = np.abs(pixels - NORMAL_COLOR_I16)
    deviant = np.sum(np.any(diff > COLOR_TOLERANCE, axis=1))
    return deviant >= MIN_DEVIANT_POINTS, int(deviant)


def draw_debug(frame, sample_points, shiny, deviant_count):
    preview = frame.copy()
    for (x, y) in sample_points:
        if y >= frame.shape[0] or x >= frame.shape[1]:
            continue
        b, g, r = frame[y, x]
        diff = np.abs(np.array([b, g, r], dtype=np.int16) - NORMAL_COLOR_I16)
        normal = np.all(diff <= COLOR_TOLERANCE)
        color = (0, 255, 0) if normal else (0, 0, 255)
        cv2.circle(preview, (x, y), 4, color, -1)

    label = f"{'SHINY DETECTED' if shiny else 'Normal'} | deviant={deviant_count}/{len(sample_points)}"
    color = (0, 255, 0) if shiny else (0, 0, 255)
    cv2.putText(preview, label, (40, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)

    # Draw bounding box around sample region
    xs = [p[0] for p in sample_points]
    ys = [p[1] for p in sample_points]
    cv2.rectangle(preview, (min(xs) - 5, min(ys) - 5), (max(xs) + 5, max(ys) + 5), color, 2)

    return preview


def test_from_file(path, show_windows: bool):
    frame = cv2.imread(str(path))

    if frame is None:
        print("Could not load image:", path)
        return 2

    shiny, deviant_count = check_border_pixels(frame, BORDER_SAMPLE_POINTS)
    print(f"deviant={deviant_count}/{len(BORDER_SAMPLE_POINTS)}")
    print("SHINY_DETECTED" if shiny else "NO_SHINY")

    if show_windows:
        preview = draw_debug(frame, BORDER_SAMPLE_POINTS, shiny, deviant_count)
        cv2.imshow("Image Test", preview)
        print("Press ESC or q to close")

        while True:
            key = cv2.waitKey(20) & 0xFF
            if key == 27 or key == ord("q"):
                break

        cv2.destroyAllWindows()

    return 0 if shiny else 1


def watch_live(seconds: float, show_windows: bool):
    cap = cv2.VideoCapture(CAPTURE_INDEX, cv2.CAP_AVFOUNDATION)

    if not cap.isOpened():
        print("Could not open capture device")
        return 2

    start_time = time.time()
    consecutive_hits = 0
    frame_count = 0
    sampled_frames = 0

    while time.time() - start_time < seconds:
        ret, frame = cap.read()

        if not ret or frame is None:
            print("Failed to read frame")
            cap.release()
            return 2

        # Crop to region of interest (reduces processing by ~98%)
        frame = frame[CROP_TOP:CROP_BOTTOM, CROP_LEFT:CROP_RIGHT]

        frame_count += 1
        if frame_count % FRAME_SAMPLE_STRIDE != 0:
            continue

        sampled_frames += 1

        shiny, deviant_count = check_border_pixels(frame, CROP_POINTS)

        if shiny:
            consecutive_hits += 1
        else:
            consecutive_hits = 0

        if shiny or sampled_frames % LOG_EVERY_SAMPLED_FRAMES == 0:
            if shiny:
                print(f"deviant={deviant_count}/{len(BORDER_SAMPLE_POINTS)} consecutive_hits={consecutive_hits}")

        if show_windows:
            preview = draw_debug(frame, CROP_POINTS, shiny, deviant_count)
            cv2.imshow("Switch", preview)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord("q"):
                cap.release()
                cv2.destroyAllWindows()
                return 130

        if consecutive_hits >= CONSECUTIVE_FRAMES_REQUIRED:
            print("Candidate deviant found, running confirmation pass...")
            if confirm_candidate_shiny(cap):
                # Save the frame that triggered detection for debugging
                debug_path = SCRIPT_DIR / "debug_shiny_frame.png"
                cv2.imwrite(str(debug_path), frame)
                print(f"Saved debug frame to {debug_path}")
                cap.release()
                if show_windows:
                    cv2.destroyAllWindows()
                print("SHINY_DETECTED")
                return 0
            print("Candidate rejected after confirmation pass.")
            consecutive_hits = 0

    cap.release()
    if show_windows:
        cv2.destroyAllWindows()
    print("NO_SHINY")
    return 1


def _sample_rgb(frame: np.ndarray, point) -> tuple[int, int, int] | None:
    x, y = point
    h, w = frame.shape[:2]
    if x < 0 or y < 0 or x >= w or y >= h:
        return None
    b, g, r = frame[y, x]
    return int(r), int(g), int(b)


def _is_close(rgb, expected, tol: int) -> bool:
    return (
        abs(rgb[0] - expected[0]) <= tol
        and abs(rgb[1] - expected[1]) <= tol
        and abs(rgb[2] - expected[2]) <= tol
    )


def detect_screen_state(seconds: float) -> int:
    """Classify state before shiny check.

    Return codes:
      0  -> SUMMARY_READY
      10 -> STARTER_NOT_CHOSEN
      11 -> STARTER_CHOSEN_NOT_SUMMARY
      2  -> capture/error
    """
    cap = cv2.VideoCapture(CAPTURE_INDEX, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        print("Could not open capture device")
        return 2

    start = time.time()
    summary_hits = 0
    unpicked_hits = 0
    picked_hits = 0
    frames = 0

    while time.time() - start < seconds:
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        frames += 1

        summary_rgb = _sample_rgb(frame, SUMMARY_MARKER_POINT)
        ball_rgb = _sample_rgb(frame, STARTER_BALL_POINT)
        if summary_rgb and _is_close(summary_rgb, SUMMARY_MARKER_RGB, STATE_TOLERANCE):
            summary_hits += 1
        if ball_rgb and _is_close(ball_rgb, UNPICKED_STARTER_RGB, STATE_TOLERANCE):
            unpicked_hits += 1
        if ball_rgb and _is_close(ball_rgb, PICKED_STARTER_RGB, STATE_TOLERANCE):
            picked_hits += 1

    cap.release()

    if frames == 0:
        print("STATE_ERROR frames=0")
        return 2

    if summary_hits >= 3:
        print(f"STATE_SUMMARY_READY summary_hits={summary_hits} unpicked_hits={unpicked_hits} picked_hits={picked_hits} frames={frames}")
        return 0
    if unpicked_hits >= 3:
        print(f"STATE_STARTER_NOT_CHOSEN summary_hits={summary_hits} unpicked_hits={unpicked_hits} picked_hits={picked_hits} frames={frames}")
        return 10

    print(f"STATE_STARTER_CHOSEN_NOT_SUMMARY summary_hits={summary_hits} unpicked_hits={unpicked_hits} picked_hits={picked_hits} frames={frames}")
    return 11


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", help="Test image from Downloads folder")
    parser.add_argument("--watch-seconds", type=float, help="Watch live feed for N seconds")
    parser.add_argument("--state-check", action="store_true", help="Check if screen is summary / starter-not-chosen / other")
    parser.add_argument("--state-seconds", type=float, default=1.2, help="Seconds to sample for state check")
    parser.add_argument("--show", action="store_true", help="Show debug windows")
    args = parser.parse_args()

    if args.state_check:
        sys.exit(detect_screen_state(args.state_seconds))

    if args.image:
        image_path = Path(args.image)
        if not image_path.exists():
            image_path = SCRIPT_DIR / args.image
        if not image_path.exists():
            image_path = Path.home() / "Downloads" / args.image
        print("Testing image:", image_path)
        sys.exit(test_from_file(image_path, args.show))

    if args.watch_seconds:
        sys.exit(watch_live(args.watch_seconds, args.show))

    sys.exit(watch_live(999999, True))


if __name__ == "__main__":
    main()