# shiny-bot (Wi-Fi)

Automated shiny starter hunting for **Pokemon FireRed/LeafGreen** on Nintendo Switch. Soft resets in a loop, picks the starter, opens the summary screen, and checks for the shiny sprite border — all over Wi-Fi.

## How It Works

1. **Soft reset** the game via the Pico's `reset` macro (HOME → close → relaunch).
2. **Run the button sequence** — mash through the title screen, load the save, pick the starter, decline the nickname, wait for the rival battle, then open the Pokemon summary.
3. **Check for shiny** — capture a frame from the USB capture card and sample pixels along the sprite border. If the border color differs from the known normal palette, it's shiny.
4. **Recovery** — if the game state is unexpected (e.g., stuck in dialogue), the bot detects it and navigates back to the summary screen automatically.
5. **Repeat** until a shiny is found.

## Setup

### Prerequisites

- Raspberry Pi Pico W flashed with the Wi-Fi firmware (`pico-fw/build/shinybot_pico_fw.uf2`)
- USB capture card connected to the Switch
- macOS with Python 3.9+

### Install

```bash
cd shiny-bot
python3 -m venv venv
source venv/bin/activate
pip install opencv-python numpy
```

### Configure Pico IP

Set the IP address of your Pico W:

```bash
export PICO_IP=192.168.1.100
```

Or edit the default in `pico.py`.

### Build Firmware (optional)

If you need to rebuild the Pico firmware:

```bash
cd pico-fw/build
cmake .. -DPICO_BOARD=pico_w \
  -DWIFI_SSID='"YourSSID"' \
  -DWIFI_PASSWORD='"YourPassword"'
cmake --build . -j
```

Then flash `shinybot_pico_fw.uf2` to the Pico (hold BOOTSEL, plug in USB, copy the file).

## Usage

### Web Control Panel

```bash
python3 web_control.py
# Open http://localhost:8000
```

The web UI provides:
- **Start / Stop / Restart** the hunt loop
- **Pause After Check** — pause between attempts (useful for inspecting a result)
- **Manual buttons** — A, B, X for testing
- **Check Starter** — navigate to summary screen manually
- **Save Shiny** — run the save sequence when you find one

### Command Line

```bash
# Run the hunt loop directly
python3 hunt_loop.py
# Press ESC at any time to stop gracefully
```

## Files

| File | Purpose |
|------|---------|
| `hunt_loop.py` | Main automation loop (reset → sequence → detect → repeat) |
| `run_sequence.py` | Button sequence for one soft-reset attempt |
| `check_border.py` | Shiny detection via sprite border pixel sampling |
| `web_control.py` | HTTP server for the web control panel |
| `pico.py` | Pico W HTTP communication module |
| `pixel_tools.py` | Live pixel coordinate probing (calibration helper) |
| `record_sequence.py` | Record button sequences via keyboard for tuning |
| `pico-fw/` | Pico W firmware source (C, CMake) |
| `OPTIMIZATIONS.md` | Performance optimization notes |