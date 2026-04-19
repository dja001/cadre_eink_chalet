"""NHL playoff bracket image generator for 1200×1600 e-ink display.

Layout: West Conference on the LEFT, East Conference on the RIGHT
(matches geographic map orientation).
"""
import os
import datetime
import requests
import numpy as np
from PIL import Image as PILImage
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import matplotlib.font_manager as fm

SCRIPT_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONT_BOLD  = os.path.join(SCRIPT_DIR, 'fonts', 'lmroman10-bold.otf')
_FONT_REG   = os.path.join(SCRIPT_DIR, 'fonts', 'lmroman10-regular.otf')
_LOGO_DIR   = os.path.join(SCRIPT_DIR, 'figures', 'logos_cache')

MTL_COLOR  = '#AF1E2D'
BACKGROUND = '#F7F3EE'
BOX_BG     = '#FFFFFF'
BOX_EDGE   = '#AAAAAA'
WIRE_COLOR = '#444444'
TEXT_COLOR = '#111111'
DIM_COLOR  = '#888888'
GOLD_COLOR = '#B8860B'

# Series letters: A-D = East R1, E-H = West R1, I-J = East R2,
# K-L = West R2, M = ECF, N = WCF, O = SCF
_EAST_R1 = ['A', 'B', 'C', 'D']
_WEST_R1 = ['E', 'F', 'G', 'H']

# ESPN abbreviation overrides (NHL code → ESPN URL key, lowercase)
_ESPN_KEY = {
    'NJD': 'nj', 'LAK': 'la', 'SJS': 'sj',
    'TBL': 'tb', 'UTA': 'utah',
}


# ── Fonts ─────────────────────────────────────────────────────────────────────

def _load_fonts():
    try:
        fm.fontManager.addfont(_FONT_BOLD)
        fm.fontManager.addfont(_FONT_REG)
        return (fm.FontProperties(fname=_FONT_BOLD),
                fm.FontProperties(fname=_FONT_REG))
    except Exception:
        return None, None


# ── NHL API ───────────────────────────────────────────────────────────────────

def _fetch_bracket(year):
    url = f"https://api-web.nhle.com/v1/playoff-bracket/{year}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data if data and data.get('series') else None


def _get_bracket():
    """Return (data, year), trying current then previous season."""
    now = datetime.datetime.now()
    for y in [now.year, now.year - 1]:
        try:
            data = _fetch_bracket(y)
            if data:
                return data, y
        except Exception as e:
            print(f"nhl_playoff_bracket: {y} fetch failed: {e}")
    return None, None


def _parse_team(d):
    if not d:
        return 'TBD', 'TBD'
    return d.get('abbrev', 'TBD'), (d.get('commonName') or {}).get('default', d.get('abbrev', 'TBD'))


def _parse_series(data):
    """Return {letter: series_dict}."""
    result = {}
    for s in data.get('series', []):
        letter = s['seriesLetter']
        t1a, t1n = _parse_team(s.get('topSeedTeam'))
        t2a, t2n = _parse_team(s.get('bottomSeedTeam'))
        result[letter] = {
            'letter': letter, 'round': s['playoffRound'],
            't1': t1a, 't1_name': t1n, 't1_wins': s.get('topSeedWins', 0) or 0,
            't2': t2a, 't2_name': t2n, 't2_wins': s.get('bottomSeedWins', 0) or 0,
        }
    return result


def _winner(s):
    if s['t1_wins'] == 4: return s['t1']
    if s['t2_wins'] == 4: return s['t2']
    return None


_TBD = {'letter': '?', 'round': 0,
        't1': 'TBD', 't1_name': 'TBD', 't1_wins': 0,
        't2': 'TBD', 't2_name': 'TBD', 't2_wins': 0}


# ── Logo fetching & caching ───────────────────────────────────────────────────

def _logo_url(abbrev):
    key = _ESPN_KEY.get(abbrev, abbrev.lower())
    return f"https://a.espncdn.com/i/teamlogos/nhl/500/{key}.png"


def _get_logo(abbrev):
    """Return RGBA PIL.Image for team logo, using disk cache. Returns None on failure."""
    os.makedirs(_LOGO_DIR, exist_ok=True)
    path = os.path.join(_LOGO_DIR, f"{abbrev}.png")

    if not os.path.exists(path):
        try:
            r = requests.get(_logo_url(abbrev), timeout=10)
            r.raise_for_status()
            with open(path, 'wb') as f:
                f.write(r.content)
        except Exception as e:
            print(f"Logo fetch failed for {abbrev}: {e}")
            return None

    try:
        return PILImage.open(path).convert('RGBA')
    except Exception:
        return None


def _preload_logos(series_dict):
    """Fetch all non-TBD team logos. Returns {abbrev: PIL.Image or None}."""
    abbrevs = {t for s in series_dict.values() for t in (s['t1'], s['t2']) if t != 'TBD'}
    return {a: _get_logo(a) for a in abbrevs}


# ── Drawing ───────────────────────────────────────────────────────────────────

def _draw_logo(ax, logo, cx, cy, size):
    """Draw a PIL logo centred at data-coords (cx, cy) with given size (inches)."""
    if logo is None:
        return
    h = size / 2
    ax.imshow(np.array(logo),
              extent=[cx - h, cx + h, cy - h, cy + h],
              aspect='auto', zorder=6, interpolation='bilinear')


def _draw_box(ax, cx, cy, s, bw, bh, fp_bold, fp_reg, logos):
    """Draw a matchup box centred at (cx, cy) with team logos."""
    x0, y0  = cx - bw / 2, cy - bh / 2
    is_mtl  = s['t1'] == 'MTL' or s['t2'] == 'MTL'
    winner  = _winner(s)

    # Background and border
    rect = FancyBboxPatch(
        (x0, y0), bw, bh,
        boxstyle="round,pad=0.04",
        facecolor=BOX_BG,
        edgecolor=MTL_COLOR if is_mtl else BOX_EDGE,
        linewidth=2.5 if is_mtl else 1.0,
        zorder=3,
    )
    ax.add_patch(rect)

    # Divider line
    ax.plot([x0 + 0.1, x0 + bw - 0.1], [cy, cy],
            color='#DDDDDD', lw=0.8, zorder=4)

    # Row centres (vertical midpoints of each team half)
    y1 = cy + bh * 0.26   # top team
    y2 = cy - bh * 0.26   # bottom team

    LOGO_SIZE = 0.54        # inches; fits within row height bh*0.5=0.7"
    LOGO_CX   = x0 + 0.38  # logo centre x (left margin 0.08 + half-size 0.27)
    TEXT_X    = x0 + 0.72  # team abbreviation starts here (after logo)

    for abbrev, row_y in [(s['t1'], y1), (s['t2'], y2)]:
        is_winner  = winner == abbrev
        is_mtl_row = abbrev == 'MTL'
        fp    = fp_bold if (is_winner and fp_bold) else fp_reg
        color = MTL_COLOR if is_mtl_row else TEXT_COLOR

        logo = logos.get(abbrev)
        if logo is not None:
            _draw_logo(ax, logo, LOGO_CX, row_y, LOGO_SIZE)
            text_x = TEXT_X
        else:
            # No logo (TBD or fetch failed): use full-width text area
            text_x = x0 + 0.14

        ax.text(text_x, row_y, abbrev,
                ha='left', va='center', fontsize=18,
                fontproperties=fp, color=color,
                fontweight='bold' if is_winner else 'normal',
                zorder=7)

    # Series score on the divider line, right-aligned — separate y from both
    # team rows so it can never overlap abbreviation text.
    if s['t1_wins'] + s['t2_wins'] > 0:
        score = f"{s['t1_wins']}\u2013{s['t2_wins']}"   # en-dash: "4–1"
        ax.text(x0 + bw - 0.10, cy, score,
                ha='right', va='center', fontsize=18,
                fontproperties=fp_reg, color='#555555', zorder=5)


def _connect(ax, x1, y1, x2, y2):
    """L-shaped bracket connector from edge (x1,y1) to edge (x2,y2)."""
    mx = (x1 + x2) / 2
    kw = dict(color=WIRE_COLOR, lw=2.0, zorder=2, solid_capstyle='butt')
    ax.plot([x1, mx], [y1, y1], **kw)
    ax.plot([mx, mx], [y1, y2], **kw)
    ax.plot([mx, x2], [y2, y2], **kw)


# ── Main ──────────────────────────────────────────────────────────────────────

def make_nhl_playoff_image():
    """Generate a 1200×1600 NHL playoff bracket image. Returns file path."""
    data, year = _get_bracket()
    fp_bold, fp_reg = _load_fonts()

    fig = plt.figure(figsize=(12, 16), dpi=100)
    ax  = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 16)
    ax.axis('off')
    ax.set_facecolor(BACKGROUND)
    fig.patch.set_facecolor(BACKGROUND)

    if not data:
        ax.text(6, 8.5, 'NHL PLAYOFF DATA\nNOT AVAILABLE',
                ha='center', va='center', fontsize=32,
                fontproperties=fp_bold, color=TEXT_COLOR,
                multialignment='center')
        return _save(fig)

    series = _parse_series(data)
    logos  = _preload_logos(series)

    def g(letter):
        return series.get(letter, _TBD)

    # ── Geometry ────────────────────────────────────────────────────
    # West on LEFT, East on RIGHT (map orientation)
    BW, BH = 1.65, 1.40   # box width × height (inches = data units at 100 dpi)
    HW = BW / 2            # half-width

    # 7 columns, symmetric around x=6, step=1.7 (BW=1.65, gap=0.05)
    # col centres: 0.9  2.6  4.3  6.0  7.7  9.4  11.1
    xw1, xw2, xwc = 0.9, 2.6, 4.3   # West R1, R2, Conf Final
    xs             = 6.0              # Stanley Cup Final (centre)
    xec, xe2, xe1 = 7.7, 9.4, 11.1  # East Conf Final, R2, R1

    # 4 R1 y-slots over y ∈ [0.9, 14.5], step=3.4; top→bottom = index 3→0
    y_r1 = [0.9 + (i + 0.5) * 3.4 for i in range(4)]     # 2.6, 6.0, 9.4, 12.8
    y_r2 = [(y_r1[0] + y_r1[1]) / 2,
            (y_r1[2] + y_r1[3]) / 2]                      # 4.3, 11.1
    y_cf = (y_r2[0] + y_r2[1]) / 2                        # 7.7

    # ── Title ───────────────────────────────────────────────────────
    ax.text(6, 15.35, f"{year} NHL PLAYOFFS",
            ha='center', va='center', fontsize=30,
            fontproperties=fp_bold, color=TEXT_COLOR)

    # ── Conference labels ────────────────────────────────────────────
    ax.text((xw1 + xwc) / 2, 14.9, 'WESTERN CONFERENCE',
            ha='center', va='center', fontsize=20,
            fontproperties=fp_bold, color='#444444')
    ax.text((xec + xe1) / 2, 14.9, 'EASTERN CONFERENCE',
            ha='center', va='center', fontsize=20,
            fontproperties=fp_bold, color='#444444')

    # ── West R1 (top→bottom: E F G H) ───────────────────────────────
    for i, letter in enumerate(_WEST_R1):
        _draw_box(ax, xw1, y_r1[3 - i], g(letter), BW, BH, fp_bold, fp_reg, logos)

    # ── West R2 (K above, L below) ───────────────────────────────────
    _draw_box(ax, xw2, y_r2[1], g('K'), BW, BH, fp_bold, fp_reg, logos)
    _draw_box(ax, xw2, y_r2[0], g('L'), BW, BH, fp_bold, fp_reg, logos)

    # ── WCF ──────────────────────────────────────────────────────────
    _draw_box(ax, xwc, y_cf, g('N'), BW, BH, fp_bold, fp_reg, logos)

    # ── East R1 (top→bottom: A B C D) ───────────────────────────────
    for i, letter in enumerate(_EAST_R1):
        _draw_box(ax, xe1, y_r1[3 - i], g(letter), BW, BH, fp_bold, fp_reg, logos)

    # ── East R2 (I above, J below) ───────────────────────────────────
    _draw_box(ax, xe2, y_r2[1], g('I'), BW, BH, fp_bold, fp_reg, logos)
    _draw_box(ax, xe2, y_r2[0], g('J'), BW, BH, fp_bold, fp_reg, logos)

    # ── ECF ──────────────────────────────────────────────────────────
    _draw_box(ax, xec, y_cf, g('M'), BW, BH, fp_bold, fp_reg, logos)

    # ── SCF ──────────────────────────────────────────────────────────
    scf = g('O')
    _draw_box(ax, xs, y_cf, scf, BW, BH, fp_bold, fp_reg, logos)

    if _winner(scf):
        ax.text(xs, y_cf + BH / 2 + 0.28, '* STANLEY CUP CHAMPION *',
                ha='center', va='center', fontsize=16,
                fontproperties=fp_bold, color=GOLD_COLOR, zorder=6)

    # ── Connectors ───────────────────────────────────────────────────
    # West: R1 → R2 → WCF → SCF  (lines go RIGHT toward centre)
    _connect(ax, xw1 + HW, y_r1[3], xw2 - HW, y_r2[1])   # E → K
    _connect(ax, xw1 + HW, y_r1[2], xw2 - HW, y_r2[1])   # F → K
    _connect(ax, xw1 + HW, y_r1[1], xw2 - HW, y_r2[0])   # G → L
    _connect(ax, xw1 + HW, y_r1[0], xw2 - HW, y_r2[0])   # H → L
    _connect(ax, xw2 + HW, y_r2[1], xwc - HW, y_cf)      # K → N
    _connect(ax, xw2 + HW, y_r2[0], xwc - HW, y_cf)      # L → N
    _connect(ax, xwc + HW, y_cf,    xs  - HW, y_cf)       # N → SCF

    # East: R1 → R2 → ECF → SCF  (lines go LEFT toward centre)
    _connect(ax, xe1 - HW, y_r1[3], xe2 + HW, y_r2[1])   # A → I
    _connect(ax, xe1 - HW, y_r1[2], xe2 + HW, y_r2[1])   # B → I
    _connect(ax, xe1 - HW, y_r1[1], xe2 + HW, y_r2[0])   # C → J
    _connect(ax, xe1 - HW, y_r1[0], xe2 + HW, y_r2[0])   # D → J
    _connect(ax, xe2 - HW, y_r2[1], xec + HW, y_cf)      # I → M
    _connect(ax, xe2 - HW, y_r2[0], xec + HW, y_cf)      # J → M
    _connect(ax, xec - HW, y_cf,    xs  + HW, y_cf)       # M → SCF

    # ── Column labels ────────────────────────────────────────────────
    for x, label in [
        (xw1, 'ROUND 1'),  (xw2, 'ROUND 2'),  (xwc, 'CONF.\nFINAL'),
        (xs,  'STANLEY CUP\nFINAL'),
        (xec, 'CONF.\nFINAL'), (xe2, 'ROUND 2'), (xe1, 'ROUND 1'),
    ]:
        ax.text(x, 0.58, label, ha='center', va='center', fontsize=14,
                fontproperties=fp_bold, color=DIM_COLOR,
                multialignment='center')

    # ── Footer ───────────────────────────────────────────────────────
    today = datetime.datetime.now().strftime('%B %d, %Y')
    ax.text(6, 0.13, today, ha='center', va='bottom', fontsize=14,
            fontproperties=fp_reg, color=DIM_COLOR)

    return _save(fig)


def _save(fig):
    os.makedirs(os.path.join(SCRIPT_DIR, 'figures'), exist_ok=True)
    path = os.path.join(SCRIPT_DIR, 'figures', 'nhl_playoffs.png')
    fig.savefig(path, dpi=100, facecolor=BACKGROUND)
    plt.close(fig)
    return path


if __name__ == '__main__':
    out = make_nhl_playoff_image()
    print(f"Saved: {out}")
