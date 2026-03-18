#!/usr/bin/env python3
"""
Record a button sequence by pressing keyboard keys in sync with your Switch controller.
Outputs a run_sequence.sh-compatible script when done.

Key mappings:
  a → A button
  s → B button
  d → Y button
  SPACE → rand_wait marker
  q → stop recording and print results
"""

import sys
import tty
import termios
import time

KEY_MAP = {
    'a': 'A',
    's': 'B',
    'd': 'Y',
    ' ': 'RAND_WAIT',
}


def read_key(fd):
    """Read a single keypress."""
    ch = sys.stdin.read(1)
    if ch == '\x1b':
        sys.stdin.read(2)  # consume escape sequence
        return None
    return ch


def main():
    print("=== Sequence Recorder ===")
    print()
    print("Key mappings:")
    print("  a=A  s=B  d=Y  SPACE=rand_wait")
    print("  q = stop and output sequence")
    print()
    print("Press keys in sync with your Switch controller.")
    print("Recording starts on first keypress...")
    print()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    events = []
    started = False

    try:
        tty.setraw(fd)

        while True:
            key = read_key(fd)
            if key is None:
                continue

            now = time.monotonic()

            if key == 'q':
                break

            # Map the key
            if key in KEY_MAP:
                button = KEY_MAP[key]
            else:
                continue  # ignore unmapped keys

            if not started:
                started = True
                start_time = now

            elapsed = now - start_time if started else 0
            gap = now - events[-1][0] if events else 0

            events.append((now, button, gap))

            # Show feedback (write raw since terminal is in raw mode)
            label = f"  [{elapsed:7.2f}s] {button} (gap: {gap:.2f}s)\r\n"
            sys.stdout.write(label)
            sys.stdout.flush()

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    print()
    print()

    if not events:
        print("No events recorded.")
        return

    # Generate script output
    print("=" * 50)
    print("RECORDED SEQUENCE (paste into run_sequence.sh)")
    print("=" * 50)
    print()

    for i, (ts, button, gap) in enumerate(events):
        delay = round(gap, 1) if gap > 0 else 0.5
        if button == 'RAND_WAIT':
            print('rand_wait 0.1 2.0')
        else:
            print(f'press {button} {delay}')

    print()
    print("=" * 50)
    print(f"Total events: {len(events)}")
    total = events[-1][0] - events[0][0] if len(events) > 1 else 0
    print(f"Total time: {total:.1f}s")
    print("=" * 50)


if __name__ == '__main__':
    main()
