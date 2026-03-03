# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python scheduler for a 13.3-inch 7-color Waveshare e-ink display (1200×1600 pixels) running on a Raspberry Pi. It cycles through generated images on a configurable weekly schedule, and picks random images outside scheduled periods. The service runs as `eink-scheduler.service` on the Pi at `/home/pilist/eink_scheduler/`.

## Running Tests

```bash
python3 -m unittest tests/test_schedule_parser.py
# or
python3 -m pytest tests/
```

## Testing Individual Image Generators

Each image module can be run directly:

```bash
python3 xkcd_image.py
python3 moon_phase.py
python3 nhl_classification.py
python3 todo_image.py
python3 random_image_from_dropbox.py
```

## Running the Scheduler Manually (Without Hardware)

Set `test_mode=True` in `scheduler.py` before running:
```bash
python3 scheduler.py
```

In `test_mode`, `eink_update()` copies the image to `figures/current_image.png` but does not touch the display hardware.

## Image Processing Tools

```bash
# Crop photos to 3:4 ratio (GUI tool):
python3 cropper.py /path/to/photos   # First run: scan and build list
python3 cropper.py                    # Subsequent runs: crop pictures one by one

# Batch process images for e-ink (contrast/saturation boost):
python3 process_for_eink.py
```

## Systemd Service Management

```bash
sudo systemctl status eink-scheduler.service
sudo systemctl restart eink-scheduler.service
sudo journalctl -u eink-scheduler.service -f
```

## Architecture

### Core Flow

1. `scheduler.py` (`EinkScheduler`) reads `schedule.conf`, checks every 30s which `Schedule` is active.
2. During a scheduled period: calls the mapped display function once on entry.
3. Outside scheduled periods: calls a random function from `DISPLAY_FUNCTIONS_TO_RUN_RANDOMLY` every 10 minutes.
4. Every display function returns a **file path string** (or `"shutdown"` to clear the screen). Returning `None` signals failure.
5. `eink_driver.py` receives the path, atomically copies the file to `figures/current_image.png`, then drives the hardware.

### Adding a New Display Function

1. Create a function that returns a file path string or `None` on failure.
2. Add it to `FUNCTION_MAP` in `scheduler.py` (required for scheduling).
3. Optionally add it (multiple times for higher probability) to `DISPLAY_FUNCTIONS_TO_RUN_RANDOMLY`.
4. Reference it by name in `schedule.conf` if you want it scheduled.

### Key Files

| File | Purpose |
|------|---------|
| `scheduler.py` | Main loop; `FUNCTION_MAP` and `DISPLAY_FUNCTIONS_TO_RUN_RANDOMLY` |
| `config_file_handler.py` | Parses `schedule.conf`; `Schedule.is_active()` handles midnight-spanning ranges |
| `eink_driver.py` | Wraps Waveshare EPD library (lives at `/home/pilist/bin/e-Paper/…`) |
| `schedule.conf` | Weekly display schedule |
| `dropbox_access.py` | Dropbox OAuth client; credentials from `~/.config/Dropbox/.env` |

### Image Generators

| Module | Content |
|--------|---------|
| `xkcd_image.py` | Today's or random XKCD comic with alt-text caption |
| `moon_phase.py` | NASA Dial-A-Moon image + sunrise/sunset/moonrise/moonset times via `ephem` |
| `nhl_classification.py` | NHL standings (Canadiens highlighted in red) |
| `todo_image.py` | Chalet closing checklist fetched from Dropbox `/listes/fermeture_du_chalet.txt` |
| `random_image_from_dropbox.py` | Random image from Dropbox `/random_images`, synced locally |
| `patent_image.py` | WIP — Google Patents scraper, not yet integrated into scheduler |

### Schedule Config Format

`schedule.conf` uses: `days hour_start hour_end function_name`

- Days: `0`=Monday … `6`=Sunday; supports ranges (`0-4`), lists (`0,2,4`), mixed (`1,3-5`), wildcard (`*`)
- Hours: 0–23; `hour_start > hour_end` means the schedule spans midnight
- Overlapping schedules are detected and cause a startup error

### Display Dimensions & Image Pipeline

- All output images must be **1200×1600 px** (portrait, 3:4 ratio)
- Palette: 7-color e-ink (black, white, yellow, red, orange, blue, green) — quantization is optional in `process_for_eink.py`
- `cropper.py` → `cropped_pictures/` → `process_for_eink.py` → `color_process/` → used by `random_image_from_dropbox.py`
- Output images land in `figures/`; `figures/current_image.png` is always the last displayed image

### Dropbox Credentials

Stored in `~/.config/Dropbox/.env` (not in repo):
```
DROPBOX_APP_KEY=...
DROPBOX_APP_SECRET=...
DROPBOX_REFRESH_TOKEN=...
```

### Fonts

Latin Modern Roman OTF fonts are bundled in `fonts/` (lmroman10-regular.otf, lmroman10-bold.otf, etc.). The XKCD script font (`xkcd-script.ttf`) is auto-downloaded on first use.

### Hardware Note

The Waveshare EPD library (`epd13in3E`) is **not** in this repo — it lives at `/home/pilist/bin/e-Paper/…` on the Pi. All image-generating code runs fine without it; only `eink_driver.py` with `test_mode=False` requires it.
