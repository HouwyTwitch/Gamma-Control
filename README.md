# Gamma Control

A lightweight Windows tray application for toggling display gamma with a single hotkey. Built with PyQt5, featuring a dark modern GUI with per-monitor support.

---

## Features

- **Hotkey toggle** — press a configurable key (default: `Num 9`) to switch between two gamma presets
- **Multi-monitor support** — enumerate all connected displays and choose which ones to control independently
- **Modern dark GUI** — deep dark theme with violet accent, animated toggle switches, and a real-time gamma indicator
- **System tray** — minimize to tray; double-click to restore; right-click for quick actions
- **Settings tab** — change the hotkey by clicking and pressing a key, adjust trigger/polling delays, save to config

---

## Requirements

- Windows 10 / 11
- Python 3.9+

Install dependencies:

```bash
pip install -r requirements.txt
```

`requirements.txt`:
```
PyQt5
keyboard
configparser
```

> **Note:** The `keyboard` library requires administrator privileges on Windows for global hotkey detection.

---

## Running

```bash
python src/gamma.py
```

Or build a standalone executable (see [Building](#building)).

---

## Usage

### Control tab

| Element | Description |
|---|---|
| Monitor cards | Each connected display is shown as a card. Toggle the switch to include/exclude it from gamma changes. |
| Normal slider | Gamma value applied when in "normal" mode (default `1.0` = no change). |
| Reduced slider | Gamma value applied when in "reduced" mode (default `0.7` = darker/warmer). |
| Status panel | Shows the current mode (`NORMAL` / `REDUCED`), the exact gamma value, and a fill bar. |
| Toggle Gamma | Manually switch between Normal and Reduced without using the hotkey. |
| Stop / Start | Disable or re-enable the background hotkey listener. |

### Settings tab

| Setting | Description |
|---|---|
| Hotkey | Click the key-cap button, then press any key or combination. Click again to cancel. |
| Trigger delay | How long to wait after a toggle before accepting the next one (prevents double-trigger). Default: `0.1 s`. |
| Polling delay | How often the background thread checks the keyboard state. Lower = more responsive, higher CPU. Default: `0.006 s`. |
| Save settings | Writes current values to `config.ini`. |
| Reset defaults | Restores `num 9`, `0.1 s`, `0.006 s` without saving. |

### Tray icon

Right-click the tray icon for:
- **Show** — restore the window
- **Toggle Gamma** — switch preset without opening the window
- **Quit** — exit completely

Closing the window minimizes to tray. To quit, use the tray menu.

---

## Configuration

Settings are stored in `config.ini` next to the executable (or in the project root when running from source):

```ini
[GammaSettings]
gamma1 = 1.0
gamma2 = 0.7
delay_trigger = 0.1
delay_polling = 0.006
toggle_key = num 9

[App]
start_minimized = false
```

You can edit this file manually; changes take effect on the next launch.

**Common `toggle_key` values:** `num 9`, `f9`, `ctrl+alt+g`, `insert`, `scroll lock`

---

## Building

Requires [PyInstaller](https://pyinstaller.org):

```bash
pip install pyinstaller
pyinstaller gamma.spec
```

The output is placed in `dist/GammaControl/`. Run `GammaControl.exe` — no installer needed.

---

## How it works

1. On startup, the app reads `config.ini` and enumerates monitors via `EnumDisplayMonitors` (Win32 API).
2. A background `QThread` polls `keyboard.is_pressed()` every `delay_polling` seconds.
3. On hotkey press, it builds a gamma ramp using `(i/255)^gamma * 65535` and applies it via `SetDeviceGammaRamp` (GDI32) for each selected monitor's device context (`CreateDCW`).
4. The toggle alternates between `gamma1` and `gamma2` with a `delay_trigger` cooldown.

---

## Project structure

```
Gamma-Control/
├── src/
│   └── gamma.py        # Main application (GUI + logic)
├── config.ini          # User configuration
├── gamma.spec          # PyInstaller build spec
└── requirements.txt
```

---

## License

MIT
