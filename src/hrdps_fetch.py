#!/usr/bin/env python3
"""
HRDPS (High Resolution Deterministic Prediction System) data fetcher.

Downloads point forecast data for Gore, QC from ECCC MSC Datamart GRIB2 files
and stores them in monthly SQLite databases under hrdps_data/.

MSC Datamart HRDPS URL pattern (new format as of 2026):
  https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_hrdps/continental/2.5km/{HH}/{FFF}/
  {YYYYMMDD}T{HH}Z_MSC_HRDPS_{VAR}_{LVL}_RLatLon0.0225_PT{FFF}H.grib2

Runs: 00Z, 06Z, 12Z, 18Z  — forecasts to +48h
Files become available ~1-2h after the nominal run time.

Usage:
    python3 hrdps_fetch.py              # fetch all missing data
    python3 hrdps_fetch.py --diagnose   # inspect one GRIB2 file and print metadata
    python3 hrdps_fetch.py --list-urls  # print URLs that would be fetched for last run
"""

import argparse
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import requests

# ---------------------------------------------------------------------------
# Location: Gore, QC, Canada
# ---------------------------------------------------------------------------
GORE_LAT = 45.87
GORE_LON = -74.55

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
UTC = timezone.utc
EASTERN = ZoneInfo("America/New_York")

RUN_HOURS = [0, 6, 12, 18]  # UTC hours at which HRDPS runs start

# Forecast hours to retrieve (every 3 hours, 0 to 48).
# Adjust this if you want finer (every 1h) or coarser (every 6h) resolution.
FORECAST_HOURS = list(range(0, 49, 1))  # [0, 1, 2, ..., 48]  → 49 files per var per run

# Variables to fetch.
# Format: (filename_var, filename_level, db_column_name)
# db_column_name is what gets stored in SQLite and referenced by hrdps_image.py
#
# NOTE: If downloads succeed but values look wrong, run with --diagnose to
# inspect the actual eccodes metadata (shortName, units, paramId) from a file.
VARIABLES = [
    ("TMP",  "AGL-2m",  "temperature_c"),    # 2m air temperature  (°C or K — check units)
    ("APCP", "Sfc",     "precip_mm"),         # accumulated precip since run start (mm)
    ("UGRD", "AGL-10m", "wind_u_ms"),         # 10m U wind component (m/s, eastward)
    ("VGRD", "AGL-10m", "wind_v_ms"),         # 10m V wind component (m/s, northward)
]

DATAMART_ROOT = "https://dd.weather.gc.ca"

# Datamart typically keeps files for ~24-48 hours. We look back 72h to catch
# any runs we may have missed during downtime.
LOOKBACK_HOURS = 72

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DB_DIR = Path(__file__).parent.parent / "hrdps_data"


def get_db_path(run_time: datetime) -> Path:
    """Monthly SQLite file path for a given run time (UTC)."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return DB_DIR / f"{run_time.strftime('%Y%m')}.sqlite"


def init_db(db_path: Path):
    """Create the forecasts table if it doesn't exist."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS forecasts (
                run_time   TEXT NOT NULL,
                valid_time TEXT NOT NULL,
                variable   TEXT NOT NULL,
                value      REAL NOT NULL,
                PRIMARY KEY (run_time, valid_time, variable)
            )
        """)
        conn.commit()


def is_in_db(db_path: Path, run_time: datetime, forecast_hour: int, variable: str) -> bool:
    """Return True if this (run, valid_time, variable) row already exists."""
    valid_time = run_time + timedelta(hours=forecast_hour)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM forecasts WHERE run_time=? AND valid_time=? AND variable=?",
            (run_time.isoformat(), valid_time.isoformat(), variable),
        ).fetchone()
    return row is not None


def store_value(db_path: Path, run_time: datetime, forecast_hour: int, variable: str, value: float):
    """Insert or replace a single forecast value."""
    valid_time = run_time + timedelta(hours=forecast_hour)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO forecasts (run_time, valid_time, variable, value) VALUES (?,?,?,?)",
            (run_time.isoformat(), valid_time.isoformat(), variable, value),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def build_url(run_time: datetime, forecast_hour: int, var: str, level: str) -> str:
    """Build the MSC Datamart URL for one HRDPS GRIB2 file."""
    date_str = run_time.strftime("%Y%m%d")
    hh  = f"{run_time.hour:02d}"
    fff = f"{forecast_hour:03d}"
    filename = f"{date_str}T{hh}Z_MSC_HRDPS_{var}_{level}_RLatLon0.0225_PT{fff}H.grib2"
    return f"{DATAMART_ROOT}/{date_str}/WXO-DD/model_hrdps/continental/2.5km/{hh}/{fff}/{filename}"


def recent_run_times(hours_back: int = LOOKBACK_HOURS) -> list[datetime]:
    """Return all HRDPS run times within the past N hours, oldest first."""
    now = datetime.now(UTC)
    # Align back to the most recent run hour before (now - hours_back)
    start = now - timedelta(hours=hours_back)
    # Round down to nearest 6h boundary
    anchor_hour = (start.hour // 6) * 6
    current = start.replace(hour=anchor_hour, minute=0, second=0, microsecond=0)

    runs = []
    while current <= now:
        if current.hour in RUN_HOURS:
            runs.append(current)
        current += timedelta(hours=6)
    return runs


# ---------------------------------------------------------------------------
# GRIB2 extraction using eccodes Python bindings
# ---------------------------------------------------------------------------

def _try_import_eccodes():
    try:
        import eccodes
        return eccodes
    except ImportError:
        return None


def extract_point_from_grib2(filepath: str, lat: float, lon: float, verbose: bool = False):
    """
    Open a GRIB2 file and extract the value at the grid point nearest (lat, lon).

    Returns (value: float, metadata: dict) or (None, metadata) on failure.
    metadata contains GRIB2 fields useful for debugging (shortName, units, etc.)
    """
    eccodes = _try_import_eccodes()
    if eccodes is None:
        print("ERROR: eccodes Python package not available.")
        print("  Install with:  mamba install -c conda-forge eccodes")
        return None, {}

    metadata = {}
    try:
        with open(filepath, "rb") as f:
            gid = eccodes.codes_grib_new_from_file(f)
            if gid is None:
                print(f"  WARNING: eccodes returned no message from {filepath}")
                return None, metadata

            try:
                # Gather metadata (best-effort — some keys may not exist)
                for key in ("shortName", "paramId", "name", "units",
                            "stepRange", "level", "typeOfLevel",
                            "missingValue", "dataDate", "dataTime"):
                    try:
                        metadata[key] = eccodes.codes_get(gid, key)
                    except eccodes.CodesInternalError:
                        pass

                if verbose:
                    print("  GRIB2 metadata:")
                    for k, v in metadata.items():
                        print(f"    {k}: {v}")

                # Values (1-D array, row-major)
                values = eccodes.codes_get_values(gid)

                # Geographic coordinates (also 1-D, same ordering as values)
                lats = eccodes.codes_get_array(gid, "latitudes")
                lons = eccodes.codes_get_array(gid, "longitudes")

                # Nearest grid point (simple Euclidean in lat/lon degrees — fine for
                # distances of a few degrees at mid-latitudes)
                dist = np.sqrt((lats - lat) ** 2 + (lons - lon) ** 2)
                idx = int(dist.argmin())

                value = float(values[idx])
                min_dist_km = dist[idx] * 111  # rough km conversion
                if verbose:
                    print(f"  Nearest grid point: lat={lats[idx]:.4f}, lon={lons[idx]:.4f}, "
                          f"dist≈{min_dist_km:.1f} km, value={value}")

                return value, metadata

            finally:
                eccodes.codes_release(gid)

    except Exception as e:
        print(f"  GRIB2 parse error: {e}")
        return None, metadata


def download_and_extract(url: str, lat: float, lon: float, verbose: bool = False):
    """
    Download one GRIB2 file from Datamart, extract point value, delete temp file.

    Returns float value or None (on 404, network error, or parse failure).
    """
    try:
        resp = requests.get(url, timeout=90, stream=True)
        if resp.status_code == 404:
            # File simply not yet available on Datamart
            return None
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  Network error: {e}")
        return None

    # Write to a temp file (eccodes needs a real file path)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".grib2")
    try:
        with os.fdopen(tmp_fd, "wb") as tmp_f:
            for chunk in resp.iter_content(chunk_size=131072):  # 128 KB chunks
                tmp_f.write(chunk)

        value, metadata = extract_point_from_grib2(tmp_path, lat, lon, verbose=verbose)
        return value

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Main fetch logic
# ---------------------------------------------------------------------------

def fetch_all_missing(verbose: bool = False):
    """
    Check all recent HRDPS runs and download any missing data points.

    For each run × forecast_hour × variable combination not yet in the database,
    attempts to download the corresponding GRIB2 file from MSC Datamart.
    Files already present in the database are skipped (idempotent).
    """
    eccodes = _try_import_eccodes()
    if eccodes is None:
        print("eccodes not available — cannot fetch data.")
        return

    runs = recent_run_times()
    print(f"Checking {len(runs)} HRDPS runs (looking back {LOOKBACK_HOURS}h)…")

    total_fetched = 0
    total_skipped = 0

    for run_time in runs:
        db_path = get_db_path(run_time)
        init_db(db_path)

        print(f"\n  Run {run_time.strftime('%Y-%m-%d %H:%M UTC')}")

        for var, level, db_name in VARIABLES:
            missing = [fhr for fhr in FORECAST_HOURS
                       if not is_in_db(db_path, run_time, fhr, db_name)]

            if not missing:
                total_skipped += len(FORECAST_HOURS)
                print(f"    {db_name:20s}: all {len(FORECAST_HOURS)} hours present — skipping")
                continue

            print(f"    {db_name:20s}: {len(missing)} files to download", end="", flush=True)

            for fhr in missing:
                url = build_url(run_time, fhr, var, level)
                value = download_and_extract(url, GORE_LAT, GORE_LON, verbose=verbose)

                if value is not None:
                    store_value(db_path, run_time, fhr, db_name, value)
                    total_fetched += 1
                    print(".", end="", flush=True)
                else:
                    print("x", end="", flush=True)  # 404 or error

            print()  # newline after progress dots

    print(f"\nDone. Fetched {total_fetched} new values, skipped {total_skipped} existing.")


# ---------------------------------------------------------------------------
# Diagnostic / debug helpers
# ---------------------------------------------------------------------------

def diagnose_one_file():
    """Download the P000 temperature file for the most recent run and print full metadata."""
    runs = recent_run_times(hours_back=24)
    if not runs:
        print("No recent runs found.")
        return

    run_time = runs[-1]
    var, level, _ = VARIABLES[0]  # temperature
    url = build_url(run_time, 0, var, level)
    print(f"Diagnosing: {url}\n")

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".grib2")
    try:
        resp = requests.get(url, timeout=90, stream=True)
        if resp.status_code == 404:
            print("404 — file not found. The Datamart URL pattern may be wrong.")
            print("Browse https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_hrdps/continental/2.5km/ to verify.")
            return
        resp.raise_for_status()

        with os.fdopen(tmp_fd, "wb") as f:
            for chunk in resp.iter_content(chunk_size=131072):
                f.write(chunk)

        size_mb = os.path.getsize(tmp_path) / 1e6
        print(f"Downloaded {size_mb:.1f} MB")

        value, metadata = extract_point_from_grib2(tmp_path, GORE_LAT, GORE_LON, verbose=True)
        if value is not None:
            print(f"\nExtracted value at Gore, QC: {value}")
        else:
            print("\nFailed to extract value.")

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def list_urls():
    """Print URLs that would be fetched for the most recent run."""
    runs = recent_run_times(hours_back=24)
    if not runs:
        print("No runs in lookback window.")
        return
    run_time = runs[-1]
    print(f"URLs for run {run_time.strftime('%Y-%m-%d %H:%M UTC')}:\n")
    for var, level, db_name in VARIABLES:
        print(f"  [{db_name}]")
        for fhr in FORECAST_HOURS[:3]:  # show first 3 only
            print(f"    {build_url(run_time, fhr, var, level)}")
        print(f"    … ({len(FORECAST_HOURS)} total forecast hours)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HRDPS data fetcher for Gore, QC")
    parser.add_argument("--diagnose",  action="store_true",
                        help="Download one GRIB2 file and print its metadata (for debugging)")
    parser.add_argument("--list-urls", action="store_true",
                        help="Print example URLs without downloading")
    parser.add_argument("--verbose",   action="store_true",
                        help="Print grid-point metadata for every file")
    args = parser.parse_args()

    if args.diagnose:
        diagnose_one_file()
    elif args.list_urls:
        list_urls()
    else:
        fetch_all_missing(verbose=args.verbose)
