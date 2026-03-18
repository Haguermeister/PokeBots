"""Pico W serial communication module (UART/TTL)."""
import glob
import threading
import serial

BAUD_RATE = 115200
TIMEOUT = 2

_lock = threading.Lock()
_ser = None
_port = None


def find_port():
    """Auto-detect USB-to-serial adapter on macOS."""
    for pattern in ["/dev/tty.usbserial-*", "/dev/tty.SLAB_USBtoUART*", "/dev/tty.wchusbserial*"]:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    return None


def connect(port=None):
    """Open the serial connection. Auto-detects port if not specified."""
    global _ser, _port
    with _lock:
        if _ser and _ser.is_open:
            return
        _port = port or _port or find_port()
        if not _port:
            raise RuntimeError("No serial port found. Pass port= or connect a USB-TTL adapter.")
        _ser = serial.Serial(_port, BAUD_RATE, timeout=TIMEOUT)
        _ser.reset_input_buffer()


def close():
    """Close the serial connection."""
    global _ser
    with _lock:
        if _ser and _ser.is_open:
            _ser.close()
        _ser = None


def send_cmd(command: str) -> str:
    """Send a command and return the response line."""
    with _lock:
        try:
            global _ser
            if _ser is None or not _ser.is_open:
                # Re-acquire outside lock context would deadlock; do inline
                port = _port or find_port()
                if not port:
                    return "Error: no serial port found"
                _ser = serial.Serial(port, BAUD_RATE, timeout=TIMEOUT)
                _ser.reset_input_buffer()

            _ser.write((command.strip() + "\n").encode())
            _ser.flush()
            line = _ser.readline().decode(errors="replace").strip()
            return line if line else "Error: no response"
        except Exception as e:
            return f"Error: {e}"


def send_reset() -> str:
    """Send the soft-reset macro."""
    return send_cmd("reset")
