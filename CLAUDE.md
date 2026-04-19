# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python scheduler for a 13.3-inch 7-color Waveshare e-ink display (1200×1600 pixels) running on a Raspberry Pi. It cycles through generated images on a configurable weekly schedule, and picks random images outside scheduled periods. The service runs as `eink-scheduler.service` on the Pi at `/home/pilist/eink_scheduler/`.

**Code layout:** all Python source lives in `src/`. Data assets (`figures/`, `fonts/`, `hrdps_data/`, `oiseaux/`, `fruits_et_legumes/`) and config (`schedule.conf`) stay at the project root. Tools are in `tools/`, tests in `tests/`.

## Service Management (Pi)

```bash
# Status / logs
sudo systemctl status eink-scheduler.service
sudo journalctl -u eink-scheduler.service -f        # live log tail
sudo journalctl -u eink-scheduler.service -n 100    # last 100 lines

# Start / stop / restart
sudo systemctl start eink-scheduler.service
sudo systemctl stop eink-scheduler.service
sudo systemctl restart eink-scheduler.service

# Enable / disable autostart on boot
sudo systemctl enable eink-scheduler.service
sudo systemctl disable eink-scheduler.service
```

After copying updated code to the Pi, always `sudo systemctl restart eink-scheduler.service`.

## Running Tests

```bash
python3 -m pytest tests/
# or
python3 -m unittest tests/test_schedule_parser.py
```

`tests/conftest.py` adds `src/` to `sys.path` automatically so imports work.

## Testing Individual Image Generators

Run from the **project root** so CWD-relative paths (`figures/`, `fonts/`, etc.) resolve correctly:

```bash
python3 src/xkcd_image.py
python3 src/moon_phase.py
python3 src/nhl_classification.py
python3 src/todo_image.py
python3 src/random_image_from_dropbox.py
python3 src/hrdps_image.py
python3 src/nhl_playoff_bracket.py
```

## Running the Scheduler Manually (Without Hardware)

Set `test_mode=True` in `src/scheduler.py` before running (from project root):
```bash
python3 src/scheduler.py
```

In `test_mode`, `eink_update()` copies the image to `figures/current_image.png` but does not touch the display hardware.

## Image Processing Tools

```bash
# Crop photos to 3:4 ratio (GUI tool):
python3 tools/cropper.py /path/to/photos   # First run: scan and build list
python3 tools/cropper.py                    # Subsequent runs: crop pictures one by one

# Batch process images for e-ink (contrast/saturation boost):
python3 tools/process_for_eink.py
```

## Architecture

### Core Flow

1. `src/scheduler.py` (`EinkScheduler`) reads `schedule.conf`, checks every 30s which `Schedule` is active.
2. During a scheduled period: calls the mapped display function once on entry.
3. Outside scheduled periods: calls a random function from `DISPLAY_FUNCTIONS_TO_RUN_RANDOMLY` every 10 minutes.
4. Every display function returns a **file path string** (or `"shutdown"` to clear the screen). Returning `None` signals failure.
5. `src/eink_driver.py` receives the path, atomically copies the file to `figures/current_image.png`, then drives the hardware.

### Adding a New Display Function

1. Create a new `src/my_module.py` with a function that returns a file path string or `None` on failure.
2. Add it to `FUNCTION_MAP` in `src/scheduler.py` (required for scheduling).
3. Optionally add it (multiple times for higher probability) to `DISPLAY_FUNCTIONS_TO_RUN_RANDOMLY`.
4. Reference it by name in `schedule.conf` if you want it scheduled.

### Key Files

| File | Purpose |
|------|---------|
| `src/scheduler.py` | Main loop; `FUNCTION_MAP` and `DISPLAY_FUNCTIONS_TO_RUN_RANDOMLY` |
| `src/config_file_handler.py` | Parses `schedule.conf`; `Schedule.is_active()` handles midnight-spanning ranges |
| `src/eink_driver.py` | Wraps Waveshare EPD library (lives at `/home/pilist/bin/e-Paper/…`) |
| `schedule.conf` | Weekly display schedule (project root) |
| `src/dropbox_access.py` | Dropbox OAuth client; credentials from `~/.config/Dropbox/.env` |

### Image Generators

| Module | Content |
|--------|---------|
| `src/xkcd_image.py` | Today's or random XKCD comic with alt-text caption |
| `src/moon_phase.py` | NASA Dial-A-Moon image + sunrise/sunset/moonrise/moonset times via `ephem` |
| `src/nhl_classification.py` | NHL standings (Canadiens highlighted in red) |
| `src/nhl_playoff_bracket.py` | NHL playoff bracket tree diagram |
| `src/todo_image.py` | Chalet closing checklist fetched from Dropbox `/listes/fermeture_du_chalet.txt` |
| `src/random_image_from_dropbox.py` | Random image from Dropbox `/random_images`, synced locally |
| `src/music_charts.py` | Top 5 tracks in 6 cities from Apple Music RSS |
| `src/generate_produce_codes.py` | PLU produce codes with images |
| `src/generate_bird_names.py` | Bird identification cards from `oiseaux/` |
| `src/hrdps_image.py` | HRDPS weather forecast spaghetti plots |
| `src/patent_image.py` | WIP — Google Patents scraper, not yet integrated into scheduler |

### Schedule Config Format

`schedule.conf` uses: `days hour_start hour_end function_name`

- Days: `0`=Monday … `6`=Sunday; supports ranges (`0-4`), lists (`0,2,4`), mixed (`1,3-5`), wildcard (`*`)
- Hours: 0–23; `hour_start > hour_end` means the schedule spans midnight
- Overlapping schedules are detected and cause a startup error

### Path Conventions

- **CWD-relative** (`figures/`, `fonts/`, `oiseaux/`, etc.): most image generators — always run from project root.
- **`__file__`-relative to project root** (`Path(__file__).parent.parent / ...`): `hrdps_fetch.py` (database), `hrdps_image.py`, `todo_image.py`, `music_charts.py`, `nhl_playoff_bracket.py` (fonts).
- The systemd service sets `WorkingDirectory=/home/pilist/eink_scheduler/` (project root), so both conventions work correctly in production.

### Display Dimensions & Image Pipeline

- All output images must be **1200×1600 px** (portrait, 3:4 ratio)
- Palette: 7-color e-ink (black, white, yellow, red, orange, blue, green) — quantization is optional in `process_for_eink.py`
- `tools/cropper.py` → `cropped_pictures/` → `tools/process_for_eink.py` → `color_process/` → used by `random_image_from_dropbox.py`
- Output images land in `figures/`; `figures/current_image.png` is always the last displayed image

### Dropbox Credentials

Stored in `~/.config/Dropbox/.env` (not in repo):
```
DROPBOX_APP_KEY=...
DROPBOX_APP_SECRET=...
DROPBOX_REFRESH_TOKEN=...
```

### Fonts

Latin Modern Roman OTF fonts are bundled in `fonts/` (lmroman10-regular.otf, lmroman10-bold.otf, etc.). The XKCD script font (`xkcd-script.ttf`) is auto-downloaded on first use to the project root.

### Hardware Note

The Waveshare EPD library (`epd13in3E`) is **not** in this repo — it lives at `/home/pilist/bin/e-Paper/…` on the Pi. All image-generating code runs fine without it; only `src/eink_driver.py` with `test_mode=False` requires it.
