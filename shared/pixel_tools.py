#!/usr/bin/env python3
import argparse
import time

import cv2
import numpy as np

CAPTURE_INDEX = 0


def probe_pixel_live(x: int, y: int, seconds: float):
    """Sample one full-frame pixel over time and print RGB stats."""
    cap = cv2.VideoCapture(CAPTURE_INDEX, cv2.CAP_AVFOUNDATION)

    if not cap.isOpened():
        print("Could not open capture device")
        return 2

    start_time = time.time()
    samples = []

    while time.time() - start_time < seconds:
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        h, w = frame.shape[:2]
        if x < 0 or y < 0 or x >= w or y >= h:
            cap.release()
            print(f"Pixel out of bounds: ({x}, {y}) for frame {w}x{h}")
            return 2

        b, g, r = frame[y, x]
        samples.append((int(r), int(g), int(b)))
        time.sleep(0.02)

    cap.release()

    if not samples:
        print("No samples captured")
        return 2

    arr = np.array(samples, dtype=np.int16)
    mins = arr.min(axis=0)
    maxs = arr.max(axis=0)
    avgs = arr.mean(axis=0)

    print(f"Probe pixel: ({x}, {y})")
    print(f"Samples: {len(samples)}")
    print(f"R avg/min/max: {avgs[0]:.1f} / {mins[0]} / {maxs[0]}")
    print(f"G avg/min/max: {avgs[1]:.1f} / {mins[1]} / {maxs[1]}")
    print(f"B avg/min/max: {avgs[2]:.1f} / {mins[2]} / {maxs[2]}")
    return 0


def pick_pixel_from_live() -> int:
    """Open live preview and print pixel coordinate/RGB on click."""
    cap = cv2.VideoCapture(CAPTURE_INDEX, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        print("Could not open capture device")
        return 2

    picked = {"done": False}

    def on_mouse(event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        frame = param.get("frame")
        if frame is None:
            return
        b, g, r = frame[y, x]
        print(f"Picked pixel: x={x} y={y} RGB=({int(r)}, {int(g)}, {int(b)})")
        picked["done"] = True

    state = {"frame": None}
    cv2.namedWindow("Pick Pixel")
    cv2.setMouseCallback("Pick Pixel", on_mouse, state)
    print("Click a pixel in the preview window. Press q or ESC to cancel.")

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        state["frame"] = frame
        cv2.imshow("Pick Pixel", frame)

        key = cv2.waitKey(1) & 0xFF
        if picked["done"]:
            break
        if key == 27 or key == ord("q"):
            cap.release()
            cv2.destroyAllWindows()
            return 130

    cap.release()
    cv2.destroyAllWindows()
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pick-point", action="store_true", help="Open live preview and click pixel to get coordinates")
    parser.add_argument("--probe-x", type=int, help="Probe X pixel on full frame")
    parser.add_argument("--probe-y", type=int, help="Probe Y pixel on full frame")
    parser.add_argument("--probe-seconds", type=float, default=2.0, help="Seconds to sample probe pixel")
    args = parser.parse_args()

    if args.pick_point:
        raise SystemExit(pick_pixel_from_live())

    if args.probe_x is not None or args.probe_y is not None:
        if args.probe_x is None or args.probe_y is None:
            print("Both --probe-x and --probe-y are required")
            raise SystemExit(2)
        raise SystemExit(probe_pixel_live(args.probe_x, args.probe_y, args.probe_seconds))

    parser.print_help()
    raise SystemExit(0)


if __name__ == "__main__":
    main()
