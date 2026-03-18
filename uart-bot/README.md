# uart-bot (Wired Serial)

Automated shiny starter hunting for **Pokemon FireRed/LeafGreen** on Nintendo Switch — identical logic to [shiny-bot](../shiny-bot/), but communicates with the Pico W over a **wired UART/serial** connection instead of Wi-Fi.

## Why UART?

- **Lower latency** — serial commands arrive faster than HTTP over Wi-Fi
- **More reliable** — no dropped packets or Wi-Fi reconnects
- **Simpler firmware** — no Wi-Fi stack, smaller binary, faster boot
- **No IP configuration** — the serial port is auto-detected on macOS

## How It Works

Same loop as shiny-bot:

1. Soft reset → run button sequence → open summary → check for shiny → repeat.
2. The only difference is the transport layer: Python sends commands over a USB-to-TTL serial adapter wired to the Pico's UART0 pins (GP0/GP1).

## Setup

### Prerequisites

- Raspberry Pi Pico W flashed with the UART firmware (`pico-fw/build/shinybot_uart_fw.uf2`)
- **USB-to-TTL serial adapter** (CP2102, CH340, FTDI, etc.) wired to the Pico:
  - Adapter TX → Pico GP1 (UART0 RX)
  - Adapter RX → Pico GP0 (UART0 TX)
  - Adapter GND → Pico GND
- USB capture card connected to the Switch
- macOS with Python 3.9+

### Install

```bash
cd uart-bot
python3 -m venv venv
source venv/bin/activate
pip install opencv-python numpy pyserial
```

### Build Firmware (optional)

```bash
cd pico-fw/build
cmake .. -DPICO_BOARD=pico_w
cmake --build . -j
```

Then flash `shinybot_uart_fw.uf2` to the Pico (hold BOOTSEL, plug in USB, copy the file).

No Wi-Fi credentials needed for this firmware.

## Usage

### Web Control Panel

```bash
python3 web_control.py
# Open http://localhost:8000
```

Optionally specify a serial port (auto-detected by default):

```bash
python3 web_control.py --port /dev/tty.usbserial-1420
```

The web UI is identical to shiny-bot: Start/Stop/Restart, Pause, manual buttons, Check Starter, Save Shiny.

### Command Line

```bash
python3 hunt_loop.py
# Press ESC at any time to stop gracefully
```

## Serial Port Auto-Detection

The `pico.py` module auto-detects common USB-TTL adapters on macOS:

- `/dev/tty.usbserial-*`
- `/dev/tty.SLAB_USBtoUART*`
- `/dev/tty.wchusbserial*`

If your adapter isn't detected, pass the port explicitly via `web_control.py --port` or call `pico.connect(port="/dev/tty.yourdevice")`.

## Files

| File | Purpose |
|------|---------|
| `hunt_loop.py` | Main automation loop (reset → sequence → detect → repeat) |
| `run_sequence.py` | Button sequence for one soft-reset attempt |
| `check_border.py` | Shiny detection via sprite border pixel sampling |
| `web_control.py` | HTTP server for the web control panel |
| `pico.py` | Pico serial/UART communication module (auto-detect) |
| `pixel_tools.py` | Live pixel coordinate probing (calibration helper) |
| `pico-fw/` | Pico W UART firmware source (C, CMake) |
