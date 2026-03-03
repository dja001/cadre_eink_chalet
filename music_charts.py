"""
Music Charts Display
Shows the top 5 most-played songs in 8 cities across two columns,
fetched from the Apple Music RSS feed.
"""

import json
import os
import requests
from datetime import date
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HISTORY_PATH = "figures/music_charts_history.json"
OUTPUT_PATH = "figures/music_charts.png"

CITIES = [
    # Left column
    {"name": "New York",   "flag": "🇺🇸", "cc": "us", "color": "#1A3A6B"},
    {"name": "London",     "flag": "🇬🇧", "cc": "gb", "color": "#C8102E"},
    {"name": "Paris",      "flag": "🇫🇷", "cc": "fr", "color": "#6B2D8B"},
    {"name": "Montreal",   "flag": "🇨🇦", "cc": "ca", "color": "#005A9C"},
    # Right column
    {"name": "Seoul",      "flag": "🇰🇷", "cc": "kr", "color": "#1A7A6B"},
    {"name": "São Paulo",  "flag": "🇧🇷", "cc": "br", "color": "#1F6B2D"},
    {"name": "Tokyo",      "flag": "🇯🇵", "cc": "jp", "color": "#C8374A"},
    {"name": "Sydney",     "flag": "🇦🇺", "cc": "au", "color": "#CC5500"},
]

PACKAGE_ROOT = Path(__file__).resolve().parent
FONT_DIR = PACKAGE_ROOT / "fonts"

# Layout
IMG_W, IMG_H = 1200, 1600
TITLE_H = 80
COL_W = 600                                           # two equal columns
CITY_HEADER_H = 55
ROW_H = 65
ROWS_PER_CITY = 5
CITY_BLOCK_H = CITY_HEADER_H + ROWS_PER_CITY * ROW_H  # 55 + 325 = 380
# 4 city blocks × 380px + 80px title = 1600px ✓

# Per-column element offsets (relative to x_col)
_RANK_X  = 10    # left edge of rank number
_ART_X   = 42    # left edge of album art (60×60)
_TEXT_X  = 108   # left edge of text block
_TREND_X = 575   # centre of trend indicator
_TEXT_MAX_W = _TREND_X - 30 - _TEXT_X  # ≈ 437px

# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

# Noto Serif CJK covers Japanese, Korean, and Chinese (matches our serif style)
_CJK_FONT_PATHS = {
    "regular": Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
    "bold":    Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"),
    "fallback_regular": Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    "fallback_bold":    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
}


def _has_cjk(text: str) -> bool:
    """Return True if text contains Japanese, Korean, or Chinese characters."""
    for ch in text:
        cp = ord(ch)
        if (
            0x3040 <= cp <= 0x30FF    # Hiragana + Katakana
            or 0x4E00 <= cp <= 0x9FFF  # CJK Unified Ideographs
            or 0xAC00 <= cp <= 0xD7AF  # Hangul Syllables
            or 0x1100 <= cp <= 0x11FF  # Hangul Jamo
            or 0x3400 <= cp <= 0x4DBF  # CJK Extension A
        ):
            return True
    return False


def _load_cjk_font(size: int, bold: bool = False) -> "ImageFont.FreeTypeFont | None":
    """Load a CJK-capable font at the given size, or None if unavailable."""
    key = "bold" if bold else "regular"
    for path in (_CJK_FONT_PATHS[key], _CJK_FONT_PATHS[f"fallback_{key}"]):
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return None


def _load_font(size: int, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    """Load a Latin Modern Roman font, falling back to DejaVu then default."""
    if bold and italic:
        candidates = [FONT_DIR / "lmroman10-bolditalic.otf"]
    elif bold:
        candidates = [FONT_DIR / "lmroman10-bold.otf"]
    elif italic:
        candidates = [FONT_DIR / "lmroman10-italic.otf"]
    else:
        candidates = [FONT_DIR / "lmroman10-regular.otf"]

    candidates += [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf") if bold
        else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]

    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_charts(country_code: str) -> list:
    """
    Fetch top 5 most-played songs for a country from Apple Music RSS.

    Returns a list of dicts with keys: song_id, title, artist, artwork_url.
    Returns [] on failure.
    """
    url = (
        f"https://rss.applemarketingtools.com/api/v2/"
        f"{country_code}/music/most-played/5/songs.json"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        feed = resp.json().get("feed", {})
        results = feed.get("results", [])
        songs = []
        for i, item in enumerate(results[:5], start=1):
            songs.append({
                "rank": i,
                "song_id": item.get("id", ""),
                "title": item.get("name", "Unknown"),
                "artist": item.get("artistName", "Unknown"),
                "artwork_url": item.get("artworkUrl100", ""),
            })
        return songs
    except Exception as e:
        print(f"fetch_charts({country_code}) failed: {e}")
        return []


# ---------------------------------------------------------------------------
# History persistence
# ---------------------------------------------------------------------------

def load_history() -> dict:
    """Load history JSON from disk; return empty dict if missing/corrupt."""
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_history(history: dict) -> None:
    """Save history dict to disk."""
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Trend computation
# ---------------------------------------------------------------------------

def compute_trends(current_songs: list, country: str, history: dict) -> list:
    """
    Add trend and days_at_1 fields to each song in current_songs.
    Updates history[country] in-place.

    trend values: "up", "down", "same", "new"
    """
    today_str = date.today().isoformat()
    prev = history.get(country, {})
    prev_songs = prev.get("songs", [])
    prev_number_one = prev.get("number_one", {})

    # Build lookup: song_id -> previous rank
    prev_rank_by_id = {s["song_id"]: s["rank"] for s in prev_songs}

    enriched = []
    for song in current_songs:
        sid = song["song_id"]
        rank = song["rank"]

        if sid not in prev_rank_by_id:
            trend = "new"
        else:
            prev_rank = prev_rank_by_id[sid]
            if rank < prev_rank:
                trend = "up"
            elif rank > prev_rank:
                trend = "down"
            else:
                trend = "same"

        days_at_1 = None
        if rank == 1:
            if prev_number_one.get("song_id") == sid:
                days_at_1 = prev_number_one.get("days", 1) + 1
            else:
                days_at_1 = 1

        enriched.append({**song, "trend": trend, "days_at_1": days_at_1})

    # Update history for this country
    new_number_one = prev_number_one  # keep old if no songs returned
    if enriched:
        top = enriched[0]
        new_number_one = {
            "song_id": top["song_id"],
            "days": top["days_at_1"] or 1,
            "since": prev_number_one.get("since", today_str)
            if prev_number_one.get("song_id") == top["song_id"]
            else today_str,
        }

    history[country] = {
        "songs": [
            {"rank": s["rank"], "song_id": s["song_id"],
             "title": s["title"], "artist": s["artist"]}
            for s in enriched
        ],
        "number_one": new_number_one,
    }

    return enriched


# ---------------------------------------------------------------------------
# Artwork
# ---------------------------------------------------------------------------

def fetch_artwork(url: str) -> Image.Image | None:
    """Download album artwork and return a 60×60 RGB PIL Image, or None."""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        return img.resize((60, 60), Image.LANCZOS)
    except Exception as e:
        print(f"fetch_artwork failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def draw_trend_indicator(draw: ImageDraw.ImageDraw, x: int, y: int,
                         trend: str, row_h: int = ROW_H) -> None:
    """
    Draw trend symbol centred vertically at (x, y_top_of_row).
    trend: "up" → green ↑, "down" → red ↓, "same" → gray —, "new" → blue NEW
    """
    font_arrow = _load_font(28, bold=True)
    font_new = _load_font(18, bold=True)

    center_y = y + row_h // 2

    if trend == "up":
        draw.text((x, center_y), "↑", fill="#2E8B57", font=font_arrow, anchor="mm")
    elif trend == "down":
        draw.text((x, center_y), "↓", fill="#CC2200", font=font_arrow, anchor="mm")
    elif trend == "same":
        draw.text((x, center_y), "—", fill="#888888", font=font_arrow, anchor="mm")
    else:  # "new"
        draw.text((x, center_y), "NEW", fill="#1A5FA8", font=font_new, anchor="mm")


# ---------------------------------------------------------------------------
# Main image generator
# ---------------------------------------------------------------------------

def generate_music_charts_image() -> str | None:
    """
    Build a 1200×1600 PNG showing the top 5 Apple Music songs in 8 cities
    arranged in two side-by-side columns of 4 cities each.
    Returns the output file path, or None on fatal error.
    """
    os.makedirs("figures", exist_ok=True)

    history = load_history()

    # Fetch all charts
    city_data = []
    for city in CITIES:
        songs = fetch_charts(city["cc"])
        if not songs:
            print(f"No data for {city['name']}, skipping.")
            songs = []
        songs = compute_trends(songs, city["cc"], history)
        city_data.append(songs)

    save_history(history)

    # Pre-fetch all artwork
    artwork_cache: dict[str, Image.Image | None] = {}
    for songs in city_data:
        for song in songs:
            url = song.get("artwork_url", "")
            if url and url not in artwork_cache:
                artwork_cache[url] = fetch_artwork(url)

    # ---------------------------------------------------------------------------
    # Build image
    # ---------------------------------------------------------------------------
    img = Image.new("RGB", (IMG_W, IMG_H), "white")
    draw = ImageDraw.Draw(img, "RGBA")

    # Fonts — Latin (used for most cities)
    font_title      = _load_font(44, bold=True)
    font_city       = _load_font(24, bold=True)
    font_rank       = _load_font(26, bold=True)
    font_song_lat   = _load_font(22, bold=True)
    font_artist_lat = _load_font(18)
    font_days       = _load_font(14, italic=True)

    # CJK variants — fall back to Latin if Noto CJK is not installed
    font_song_cjk   = _load_cjk_font(22, bold=True) or font_song_lat
    font_artist_cjk = _load_cjk_font(18)             or font_artist_lat

    # Title bar (full width)
    draw.rectangle([0, 0, IMG_W, TITLE_H], fill="#1C1C1E")
    draw.text((IMG_W // 2, TITLE_H // 2), "Global Music Charts",
              fill="white", font=font_title, anchor="mm")

    # Vertical divider between columns
    draw.line([(COL_W, TITLE_H), (COL_W, IMG_H)], fill="#444444", width=1)

    # Two columns: left = CITIES[0:4], right = CITIES[4:8]
    for col_idx, (col_cities, col_songs) in enumerate(
        [(CITIES[:4], city_data[:4]), (CITIES[4:], city_data[4:])]
    ):
        x_col = col_idx * COL_W
        y = TITLE_H

        for city, songs in zip(col_cities, col_songs):
            city_rgb = _hex_to_rgb(city["color"])

            # City header
            draw.rectangle([x_col, y, x_col + COL_W, y + CITY_HEADER_H],
                           fill=city["color"])
            city_label = f"{city['flag']}  {city['name']}"
            draw.text((x_col + COL_W // 2, y + CITY_HEADER_H // 2),
                      city_label, fill="white", font=font_city, anchor="mm")
            y += CITY_HEADER_H

            for i, song in enumerate(songs):
                row_y = y + i * ROW_H

                # Alternating row tint
                if i % 2 == 0:
                    draw.rectangle(
                        [x_col, row_y, x_col + COL_W, row_y + ROW_H],
                        fill=(*city_rgb, 18),
                    )

                # Rank number
                draw.text(
                    (x_col + _RANK_X, row_y + ROW_H // 2),
                    str(song["rank"]), fill="#333333",
                    font=font_rank, anchor="lm",
                )

                # Album art (y-centered in row)
                art_x = x_col + _ART_X
                art_y = row_y + (ROW_H - 60) // 2
                url = song.get("artwork_url", "")
                art = artwork_cache.get(url)
                if art:
                    img.paste(art, (art_x, art_y))
                else:
                    draw.rectangle([art_x, art_y, art_x + 60, art_y + 60],
                                   fill="#CCCCCC")

                # Text block
                text_x = x_col + _TEXT_X
                has_days_line = (song["rank"] == 1 and song.get("days_at_1"))

                if has_days_line:
                    title_y  = row_y + 4
                    artist_y = title_y + 23
                    days_y   = artist_y + 19
                else:
                    total_h  = 23 + 4 + 19
                    title_y  = row_y + (ROW_H - total_h) // 2
                    artist_y = title_y + 27

                # Pick CJK font when title/artist contain Japanese or Korean
                f_song   = font_song_cjk   if _has_cjk(song["title"])  else font_song_lat
                f_artist = font_artist_cjk if _has_cjk(song["artist"]) else font_artist_lat

                song_title  = _truncate_text(song["title"],  f_song,   _TEXT_MAX_W, draw)
                artist_name = _truncate_text(song["artist"], f_artist, _TEXT_MAX_W, draw)

                draw.text((text_x, title_y),  song_title,  fill="#1C1C1E", font=f_song)
                draw.text((text_x, artist_y), artist_name, fill="#555555",  font=f_artist)

                if has_days_line:
                    n = song["days_at_1"]
                    days_label = f"★ {n} day{'s' if n != 1 else ''} at #1"
                    draw.text((text_x, days_y), days_label, fill="#B8860B", font=font_days)

                # Trend indicator
                draw_trend_indicator(draw, x_col + _TREND_X, row_y, song["trend"])

            y += ROWS_PER_CITY * ROW_H

    img.save(OUTPUT_PATH)
    print(f"Music charts image saved: {OUTPUT_PATH}")
    return OUTPUT_PATH


def _truncate_text(text: str, font: ImageFont.FreeTypeFont,
                   max_width: int, draw: ImageDraw.ImageDraw) -> str:
    """Truncate text with ellipsis if it exceeds max_width pixels."""
    bbox = draw.textbbox((0, 0), text, font=font)
    if bbox[2] - bbox[0] <= max_width:
        return text
    while len(text) > 1:
        text = text[:-1]
        test = text.rstrip() + "…"
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return test
    return text


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    path = generate_music_charts_image()
    if path:
        print(f"Done: {path}")
    else:
        print("Image generation failed.")
