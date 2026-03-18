#!/usr/bin/env python3
"""Record button presses from Continue screen to energetic screen.

Press 'a' on keyboard = A button press sent to Pico
Press 'b' on keyboard = B button press sent to Pico
Press 'q' to stop recording

Records timestamps of every press so we can calibrate Phase 3 timing.
Run this while the game is on the Continue screen, then press through
to the energetic screen.
"""
import time
import sys
import tty
import termios
import pico

presses = []
start_time = None

def get_key():
    """Read a single keypress without waiting for Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch

print("=" * 60)
print("PHASE 3 TIMING RECORDER")
print("=" * 60)
print()
print("Navigate to the CONTINUE screen first, then:")
print("  'a' = press A button (sent to Switch)")
print("  'b' = press B button (sent to Switch)")  
print("  'q' = stop recording")
print()
print("Press 'a' to start (this will press A on Continue)...")
print()

while True:
    key = get_key()
    
    if key == 'q':
        print("\nStopped.")
        break
    
    if key in ('a', 'b'):
        now = time.perf_counter()
        
        if start_time is None:
            start_time = now
        
        elapsed_ms = (now - start_time) * 1000
        button = 'A' if key == 'a' else 'B'
        
        result = pico.send_cmd(f"press {button} 120")
        ok = result.startswith("OK")
        
        entry = {
            "button": button,
            "elapsed_ms": elapsed_ms,
            "ok": ok,
        }
        presses.append(entry)
        
        idx = len(presses)
        status = "OK" if ok else "FAIL"
        print(f"  #{idx:2d}  {button}  +{elapsed_ms:8.1f}ms  [{status}]")

# Summary
if presses:
    print()
    print("=" * 60)
    print("RECORDING SUMMARY")
    print("=" * 60)
    total_ms = presses[-1]["elapsed_ms"]
    print(f"Total presses: {len(presses)}")
    print(f"Total time: {total_ms:.1f}ms ({total_ms/1000:.2f}s)")
    print(f"A presses: {sum(1 for p in presses if p['button'] == 'A')}")
    print(f"B presses: {sum(1 for p in presses if p['button'] == 'B')}")
    print()
    
    # Show gaps between presses
    print("Press-by-press timing:")
    for i, p in enumerate(presses):
        gap = p["elapsed_ms"] - presses[i-1]["elapsed_ms"] if i > 0 else 0
        print(f"  #{i+1:2d}  {p['button']}  @ {p['elapsed_ms']:8.1f}ms  (gap: {gap:6.1f}ms)")
    
    print()
    print(f"Average gap between presses: {total_ms / (len(presses)-1):.1f}ms" if len(presses) > 1 else "")
    
    # Save to file
    import json
    with open("phase3_recording.json", "w") as f:
        json.dump({"presses": presses, "total_ms": total_ms}, f, indent=2)
    print(f"\nSaved to phase3_recording.json")
