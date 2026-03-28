#!/usr/bin/env python3
"""
HRDPS forecast spaghetti plot for the e-ink display.

Generates a 1200×1600 PNG with four panels:
  1. Temperature (°C)  — gray spaghetti lines + blue observed
  2. Precipitation (mm) — gray step bars + blue observed bars
  3. Wind speed (km/h)  — gray spaghetti lines + blue observed
  4. Wind barbs         — thin strip showing direction from newest HRDPS run

- X axis:  now−48h  →  now+12h  (60-hour window)
- Each HRDPS run = one gray line; older = lighter, newest = near-black
- Blue = observed data from the nearest Environment Canada weather station
- Red dashed vertical line marks current time

Usage (standalone test):
    python3 hrdps_image.py
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager as _fm
import numpy as np
import requests

from hrdps_fetch import fetch_all_missing, DB_DIR, GORE_LAT, GORE_LON

# ---------------------------------------------------------------------------
# Font setup — Latin Modern Roman (bundled in fonts/)
# ---------------------------------------------------------------------------
_FONTS_DIR = Path(__file__).parent / "fonts"
for _font_file in _FONTS_DIR.glob("lmroman*.otf"):
    _fm.fontManager.addfont(str(_font_file))
plt.rcParams["font.family"] = "Latin Modern Roman"

# Font sizes — deliberately large for the 1200×1600 e-ink display
FS_TITLE  = 32   # main suptitle
FS_PANEL  = 26   # per-panel title
FS_LABEL  = 22   # axis labels
FS_TICK   = 20   # tick labels
FS_LEGEND = 17   # legend text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EASTERN = ZoneInfo("America/New_York")
UTC = timezone.utc

WIDTH_PX  = 1200
HEIGHT_PX = 1600
DPI = 100  # → 12 × 16 inch figure

HOURS_PAST   = 48
HOURS_FUTURE = 24

VAR_TEMP   = "temperature_c"
VAR_PRECIP = "precip_mm"
VAR_WIND_U = "wind_u_ms"
VAR_WIND_V = "wind_v_ms"

# Observed data colour
OBS_COLOR = "#1a6bbf"
OBS_LW    = 4.0

# Barb increments in m/s (equiv. of 5 kt half, 10 kt full, 50 kt flag)
BARB_INCREMENTS = {"half": 2.572, "full": 5.144, "flag": 25.72}

# ---------------------------------------------------------------------------
# Nearest Environment Canada SWOB station (MSC Datamart)
#
# TC_ID is the Transport Canada station identifier (4-letter code).
# To find nearby stations: https://api.weather.gc.ca/collections/swob-stations/items
# (filter by bbox near your location)
#
# Default: CGTL — Mont-Tremblant, QC — ~20 km north of Gore QC.
# ---------------------------------------------------------------------------
OBS_TC_ID        = "CGTL"
OBS_STATION_NAME = "Mont-Tremblant"


# ---------------------------------------------------------------------------
# HRDPS data loading
# ---------------------------------------------------------------------------

def load_all_runs(hours_past: int = HOURS_PAST, hours_future: int = HOURS_FUTURE) -> dict:
    """
    Load all forecast data from monthly SQLite databases.

    Returns {run_time_iso: {variable: [(valid_time_utc, value), ...]}}
    """
    now = datetime.now(UTC)
    window_start = now - timedelta(hours=hours_past)
    window_end   = now + timedelta(hours=hours_future)

    db_files = sorted(DB_DIR.glob("*.sqlite")) if DB_DIR.exists() else []
    all_runs: dict = {}

    for db_path in db_files:
        try:
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT run_time, valid_time, variable, value
                    FROM forecasts
                    WHERE datetime(valid_time) >= datetime(?)
                      AND datetime(valid_time) <= datetime(?)
                    ORDER BY run_time, valid_time
                    """,
                    (window_start.isoformat(), window_end.isoformat()),
                ).fetchall()
        except sqlite3.DatabaseError as e:
            print(f"  DB read error ({db_path.name}): {e}")
            continue

        for run_iso, valid_iso, variable, value in rows:
            if run_iso not in all_runs:
                all_runs[run_iso] = {}
            if variable not in all_runs[run_iso]:
                all_runs[run_iso][variable] = []
            valid_dt = datetime.fromisoformat(valid_iso)
            if valid_dt.tzinfo is None:
                valid_dt = valid_dt.replace(tzinfo=UTC)
            all_runs[run_iso][variable].append((valid_dt, value))

    return all_runs


def wind_speed_series(run_data: dict) -> list[tuple]:
    """Wind speed (km/h) from U/V components — sorted (time, speed) pairs."""
    u_dict = dict(run_data.get(VAR_WIND_U, []))
    v_dict = dict(run_data.get(VAR_WIND_V, []))
    common = sorted(set(u_dict) & set(v_dict))
    return [(t, np.sqrt(u_dict[t] ** 2 + v_dict[t] ** 2) * 3.6) for t in common]


def adjust_temperature(values: list[float]) -> list[float]:
    """Convert Kelvin → °C if the median exceeds 100."""
    if float(np.median(values)) > 100:
        print("  Temperature looks like Kelvin — converting to °C")
        return [v - 273.15 for v in values]
    return list(values)


def adjust_precip(values: list[float]) -> list[float]:
    """Convert kg/m²/s → mm/h if max value is suspiciously small."""
    max_val = max(values) if values else 0
    if 0 < max_val < 0.01:
        print("  Precip looks like kg/m²/s — converting to mm/h")
        return [v * 3600 for v in values]
    return [max(0.0, v) for v in values]


def precip_rate_series(accum_series: list[tuple]) -> list[tuple]:
    """Convert accumulated precip (from run start) to hourly rates (mm/h)."""
    rates = []
    for i in range(1, len(accum_series)):
        t_prev, v_prev = accum_series[i - 1]
        t_curr, v_curr = accum_series[i]
        dt_h = (t_curr - t_prev).total_seconds() / 3600
        if dt_h > 0:
            rates.append((t_curr, max(0.0, (v_curr - v_prev) / dt_h)))
    return rates


# ---------------------------------------------------------------------------
# Environment Canada observed data — MSC Datamart SWOB-ML XML
# ---------------------------------------------------------------------------

import re as _re
import xml.etree.ElementTree as _ET
_SWOB_BASE = "https://dd.weather.gc.ca/{date}/WXO-DD/observations/swob-ml/{date}/{tc_id}/"


def _fetch_swob_day(tc_id: str, date_str: str) -> list[dict]:
    """
    Download all SWOB-ML XML files for one UTC date (YYYYMMDD) and station.
    Returns a list of observation dicts keyed by element name.
    """
    url = _SWOB_BASE.format(date=date_str, tc_id=tc_id)
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []
        filenames = sorted(_re.findall(r'href="([^"]+\.xml)"', r.text))
    except Exception as e:
        print(f"  SWOB directory error ({date_str}): {e}")
        return []

    obs_list = []
    for fname in filenames:
        try:
            xr = requests.get(url + fname, timeout=10)
            if xr.status_code != 200:
                continue
            root = _ET.fromstring(xr.text)
            data: dict = {}
            for el in root.iter():
                name = el.get("name")
                val  = el.get("value")
                uom  = el.get("uom", "")
                if name and val and val != "MSNG":
                    data[name] = (val, uom)
            if data:
                obs_list.append(data)
        except Exception:
            pass
    return obs_list


def _swob_float(obs: dict, key: str) -> float | None:
    entry = obs.get(key)
    if entry is None:
        return None
    try:
        return float(entry[0])
    except (ValueError, TypeError):
        return None


def load_station_obs(hours_past: int = HOURS_PAST) -> dict:
    """
    Fetch hourly SWOB-ML observations from the nearest EC station (OBS_TC_ID)
    via MSC Datamart.

    Returns {
        "temp":   [(datetime_utc, °C), ...],
        "precip": [(datetime_utc, mm), ...],
        "wind":   [(datetime_utc, km/h), ...],
        "wind_u": [(datetime_utc, m/s), ...],   # eastward component
        "wind_v": [(datetime_utc, m/s), ...],   # northward component
    }
    """
    now_utc = datetime.now(UTC)
    cutoff  = now_utc - timedelta(hours=hours_past)

    # Collect all SWOB observations for the relevant dates
    dates_needed = set()
    for d in range(hours_past // 24 + 2):
        dates_needed.add((now_utc - timedelta(days=d)).strftime("%Y%m%d"))

    all_obs: list[dict] = []
    for date_str in sorted(dates_needed):
        print(f"  Fetching SWOB for {OBS_STATION_NAME} ({OBS_TC_ID}) {date_str} …")
        all_obs.extend(_fetch_swob_day(OBS_TC_ID, date_str))

    result: dict = {"temp": [], "precip": [], "wind": [], "wind_u": [], "wind_v": []}

    for obs in all_obs:
        dt_entry = obs.get("date_tm")
        if not dt_entry:
            continue
        try:
            dt_utc = datetime.fromisoformat(dt_entry[0].replace("Z", "+00:00"))
        except ValueError:
            continue

        if not (cutoff <= dt_utc <= now_utc):
            continue

        temp = _swob_float(obs, "air_temp")
        if temp is not None:
            result["temp"].append((dt_utc, temp))

        precip = _swob_float(obs, "pcpn_amt_pst1hr")
        if precip is not None:
            result["precip"].append((dt_utc, max(0.0, precip)))

        spd_kmh = _swob_float(obs, "avg_wnd_spd_10m_pst1hr")
        wdir    = _swob_float(obs, "avg_wnd_dir_10m_pst1hr")
        if spd_kmh is not None:
            result["wind"].append((dt_utc, spd_kmh))
            if wdir is not None:
                spd_ms  = spd_kmh / 3.6
                dir_rad = wdir * np.pi / 180
                result["wind_u"].append((dt_utc, -spd_ms * np.sin(dir_rad)))
                result["wind_v"].append((dt_utc, -spd_ms * np.cos(dir_rad)))

    for key in result:
        result[key].sort()

    print(f"  SWOB obs loaded: { {k: len(v) for k, v in result.items()} }")
    return result


# ---------------------------------------------------------------------------
# Figure helpers
# ---------------------------------------------------------------------------

def _run_color(run_idx: int, n_runs: int) -> tuple:
    if n_runs <= 1:
        return (0.1, 0.1, 0.1)
    lightness = 0.80 - (run_idx / (n_runs - 1)) * 0.70
    return (lightness, lightness, lightness)


def _run_linewidth(run_idx: int, n_runs: int) -> float:
    if n_runs <= 1:
        return 2.0
    return 1.0 + (run_idx / (n_runs - 1)) * 2.0  # 1.0 → 3.0


# ---------------------------------------------------------------------------
# Figure generation
# ---------------------------------------------------------------------------

def generate_hrdps_image(output_dir: str = "./figures", fetch: bool = False) -> str | None:
    """Render the four-panel figure, return PNG path.

    Args:
        fetch: If True (default), download any missing HRDPS data first.
               Pass False to plot immediately from whatever is in the DB.
    """
    # 1. Optionally fetch missing HRDPS data
    if fetch:
        try:
            fetch_all_missing()
        except Exception as e:
            print(f"Data fetch error (will plot existing data): {e}")

    # 2. Load model data
    all_runs = load_all_runs()
    if not all_runs:
        print("No HRDPS data available — cannot generate image.")
        return None

    sorted_run_keys = sorted(all_runs.keys())
    n_runs = len(sorted_run_keys)
    print(f"Plotting {n_runs} HRDPS runs.")

    # 3. Load station observations (blue overlay)
    obs = load_station_obs()

    now          = datetime.now(UTC)
    window_start = now - timedelta(hours=HOURS_PAST)
    window_end   = now + timedelta(hours=HOURS_FUTURE)

    # 4. Build four-panel figure
    #    Rows: temperature | precipitation | wind speed | wind barbs (thin)
    fig, axes = plt.subplots(
        4, 1,
        figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI),
        dpi=DPI,
        sharex=True,
        gridspec_kw={"height_ratios": [4, 3, 4, 1]},
    )
    fig.patch.set_facecolor("white")
    ax_temp, ax_precip, ax_wind, ax_barbs = axes

    # ── 5a. Temperature ──────────────────────────────────────────────────────
    for run_idx, run_key in enumerate(sorted_run_keys):
        run_data = all_runs[run_key]
        color = _run_color(run_idx, n_runs)
        lw    = _run_linewidth(run_idx, n_runs)

        temp_series = sorted(run_data.get(VAR_TEMP, []))
        if temp_series:
            times, values = zip(*temp_series)
            values = adjust_temperature(list(values))
            ax_temp.plot(times, values, color=color, linewidth=lw, alpha=0.85)

    if obs["temp"]:
        times, values = zip(*obs["temp"])
        ax_temp.plot(times, values, color=OBS_COLOR, linewidth=OBS_LW,
                     alpha=0.95, zorder=5, solid_capstyle="round")

    # ── 5b. Precipitation rate (mm/h bars) ───────────────────────────────────
    BAR_WIDTH = timedelta(hours=0.9)  # slightly narrower than 1h gaps

    for run_idx, run_key in enumerate(sorted_run_keys):
        run_data = all_runs[run_key]
        color = _run_color(run_idx, n_runs)
        lw    = _run_linewidth(run_idx, n_runs)
        is_newest = run_idx == n_runs - 1

        accum_series = sorted(run_data.get(VAR_PRECIP, []))
        if not accum_series:
            continue
        # Convert accumulated → rates, then correct units
        _, accum_vals = zip(*accum_series)
        accum_series_adj = list(zip(
            [t for t, _ in accum_series],
            adjust_precip(list(accum_vals)),
        ))
        rate_series = precip_rate_series(accum_series_adj)
        if not rate_series:
            continue
        times, values = zip(*rate_series)

        if is_newest:
            ax_precip.bar(
                times, values,
                width=BAR_WIDTH,
                color=color, alpha=0.75, linewidth=0, zorder=3,
            )
        else:
            ax_precip.step(
                times, values, where="post",
                color=color, linewidth=max(0.6, lw * 0.5), alpha=0.6,
            )

    # Observed hourly precip: blue bars
    if obs["precip"]:
        times, values = zip(*obs["precip"])
        ax_precip.bar(
            times, values,
            width=timedelta(hours=0.85),
            color=OBS_COLOR, alpha=0.85, zorder=5, linewidth=0,
        )

    # ── 5c. Wind speed ───────────────────────────────────────────────────────
    for run_idx, run_key in enumerate(sorted_run_keys):
        run_data = all_runs[run_key]
        color = _run_color(run_idx, n_runs)
        lw    = _run_linewidth(run_idx, n_runs)

        wind_series = wind_speed_series(run_data)
        if wind_series:
            times, speeds = zip(*wind_series)
            ax_wind.plot(times, speeds, color=color, linewidth=lw, alpha=0.85)

    if obs["wind"]:
        times, values = zip(*obs["wind"])
        ax_wind.plot(times, values, color=OBS_COLOR, linewidth=OBS_LW,
                     alpha=0.95, zorder=5, solid_capstyle="round")

    # ── 5d. Wind barbs (newest run with wind data, every 3 h) ─────────────────
    # Use the newest run that has both U and V components (latest run may be
    # partially downloaded with wind data still missing).
    latest_wind_key = next(
        (k for k in reversed(sorted_run_keys)
         if all_runs[k].get(VAR_WIND_U) and all_runs[k].get(VAR_WIND_V)),
        None,
    )
    latest_data = all_runs[latest_wind_key] if latest_wind_key else {}
    u_dict = dict(latest_data.get(VAR_WIND_U, []))
    v_dict = dict(latest_data.get(VAR_WIND_V, []))
    barb_times = sorted(
        t for t in set(u_dict) & set(v_dict)
        if window_start <= t <= window_end and t.minute == 0 and t.hour % 3 == 0
    )
    # HRDPS forecast barbs (black, y=0.75)
    if barb_times:
        u_vals = np.array([u_dict[t] for t in barb_times])
        v_vals = np.array([v_dict[t] for t in barb_times])
        ax_barbs.barbs(
            barb_times, np.full(len(barb_times), 0.75), u_vals, v_vals,
            barb_increments=BARB_INCREMENTS,
            length=7, linewidth=1.2, color="black", zorder=5,
        )

    # Observed barbs (blue, y=0.25)
    if obs["wind_u"] and obs["wind_v"]:
        obs_u = dict(obs["wind_u"])
        obs_v = dict(obs["wind_v"])
        obs_barb_times = sorted(
            t for t in set(obs_u) & set(obs_v)
            if window_start <= t <= window_end and t.hour % 3 == 0
        )
        if obs_barb_times:
            ax_barbs.barbs(
                obs_barb_times,
                np.full(len(obs_barb_times), 0.25),
                np.array([obs_u[t] for t in obs_barb_times]),
                np.array([obs_v[t] for t in obs_barb_times]),
                barb_increments=BARB_INCREMENTS,
                length=7, linewidth=1.2, color=OBS_COLOR, zorder=6,
            )

    ax_barbs.set_ylim(0, 1)
    ax_barbs.set_yticks([])
    ax_barbs.set_ylabel("Dir.", fontsize=FS_LABEL - 4, labelpad=2)

    # ── 6. Axes formatting ───────────────────────────────────────────────────
    now_label = now.astimezone(EASTERN).strftime("%Y-%m-%d %H:%M %Z")
    fig.suptitle(
        f"HRDPS Forecast — Gore, QC\n{now_label}  ({n_runs} runs)",
        fontsize=FS_TITLE, fontweight="bold", y=0.99,
    )

    panel_configs = [
        (ax_temp,   "Temperature",   "°C",   None),
        (ax_precip, "Precipitation rate", "mm/h", (0, None)),
        (ax_wind,   "Wind Speed",    "km/h", (0, None)),
    ]
    for ax, title, ylabel, ylim in panel_configs:
        ax.axvline(now, color="red", linewidth=2.0, linestyle="--", zorder=10)
        ax.set_xlim(window_start, window_end)
        if ylim is not None:
            ax.set_ylim(bottom=ylim[0], top=ylim[1])
        ax.set_ylabel(ylabel, fontsize=FS_LABEL)
        ax.set_title(title, fontsize=FS_PANEL, loc="left", pad=6)
        ax.tick_params(axis="both", labelsize=FS_TICK)

    ax_barbs.axvline(now, color="red", linewidth=2.0, linestyle="--", zorder=10)
    ax_barbs.set_xlim(window_start, window_end)

    # X-axis: hour labels every 6h; show "day Mon" only at midnight
    def _x_fmt(x, pos):
        dt = mdates.num2date(x).replace(tzinfo=UTC)
        if dt.hour == 0:
            return f"00Z\n{dt.day} {dt.strftime('%b')}"
        return f"{dt.hour:02d}Z"

    import matplotlib.ticker as mticker
    ax_barbs.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
    ax_barbs.xaxis.set_major_formatter(mticker.FuncFormatter(_x_fmt))
    ax_barbs.set_xlabel("UTC", fontsize=FS_LABEL)
    ax_barbs.tick_params(axis="x", labelsize=FS_TICK, pad=12)

    # ── 7. Legend ─────────────────────────────────────────────────────────────
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    legend_elements = []
    if n_runs >= 2:
        legend_elements += [
            Line2D([0], [0], color=_run_color(0, n_runs),        linewidth=1.5, label="Oldest HRDPS run"),
            Line2D([0], [0], color=_run_color(n_runs-1, n_runs), linewidth=3.0, label="Newest HRDPS run"),
        ]
    legend_elements += [
        Line2D([0], [0], color="red",      linewidth=2.0, linestyle="--", label="Now"),
        Line2D([0], [0], color=OBS_COLOR,  linewidth=4.0,                 label=f"Observed ({OBS_TC_ID})"),
    ]
    ax_temp.legend(
        handles=legend_elements,
        loc="lower right",
        bbox_to_anchor=(1.0, 1.01),
        ncol=2,
        fontsize=FS_LEGEND,
        framealpha=0.9,
        borderaxespad=0,
    )

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    # ── 8. Save ───────────────────────────────────────────────────────────────
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    out_file = output_path / "hrdps_forecast.png"
    # Do NOT use bbox_inches="tight" — it resizes the canvas away from 1200×1600
    plt.savefig(out_file, dpi=DPI, facecolor="white")
    plt.close(fig)

    print(f"Saved: {out_file.absolute()}")
    return str(out_file.absolute())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate HRDPS forecast image.")
    parser.add_argument(
        "--no-fetch", action="store_true",
        help="Skip downloading new data; plot from existing DB only.",
    )
    args = parser.parse_args()

    path = generate_hrdps_image(fetch=not args.no_fetch)
    if path:
        print(f"\nImage generated: {path}")
    else:
        print("\nFailed to generate image.")
        raise SystemExit(1)
