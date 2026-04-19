#!/usr/bin/env python3
"""
Generate e-ink display images (1200x1600) for learning Quebec feeder bird names.

Three card layouts:
  - Regular      : full-card photo, French + English name at the bottom
  - Comparison   : two species side-by-side (e.g. Pic chevelu vs Pic mineur)
  - Dimorphic    : male + female of same species side-by-side

Image files live in oiseaux/ with this naming convention:
  Regular    : {French_name_underscored}_{1-4}.jpg
  Dimorphic  : {French_name_underscored}_mâle_{1-2}.jpg
               {French_name_underscored}_femelle_{1-2}.jpg

Run directly to generate one sample of each card type for review:
    python3 generate_bird_names.py
"""

import os
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

IMAGE_DIR = Path('oiseaux')
FONT_DIR   = Path('fonts')

WIDTH,  HEIGHT   = 1200, 1600
PHOTO_H          = 1150   # photo zone height for regular and comparison cards
TEXT_H           = HEIGHT - PHOTO_H   # 450 px

# Dimorphic-specific zones
DIM_PHOTO_H      = 1000   # photo zone per column
DIM_LABEL_H      = 130    # "(mâle)" / "(femelle)" zone
DIM_SHARED_H     = HEIGHT - DIM_PHOTO_H - DIM_LABEL_H   # 470 px for species name

BG_COLOR         = 'white'
TEXT_COLOR       = '#111111'
SECONDARY_COLOR  = '#555555'
DIVIDER_COLOR    = '#cccccc'


# ── Bird registry ─────────────────────────────────────────────────────────────

REGULAR_BIRDS = [
    ('Mésange à tête noire',       'Black-capped Chickadee'),
    ('Sittelle à poitrine rousse',  'Red-breasted Nuthatch'),
    ('Sittelle à poitrine blanche', 'White-breasted Nuthatch'),
    ('Geai bleu',                   'Blue Jay'),
    ('Tourterelle triste',          'Mourning Dove'),
    ('Chardonneret jaune',          'American Goldfinch'),
    ('Roselin familier',            'House Finch'),
    ('Roselin pourpré',             'Purple Finch'),
    ('Moineau domestique',          'House Sparrow'),
    ('Étourneau sansonnet',         'European Starling'),
    ('Junco ardoisé',               'Dark-eyed Junco'),
    ('Bruant hudsonien',            'American Tree Sparrow'),
    ('Bruant à gorge blanche',      'White-throated Sparrow'),
    ('Bruant chanteur',             'Song Sparrow'),
    ('Sizerin flammé',              'Common Redpoll'),
    ('Gros-bec errant',             'Evening Grosbeak'),
    ('Durbec des sapins',           'Pine Grosbeak'),
    ('Quiscale bronzé',             'Common Grackle'),
    ('Cardinal à poitrine rose',    'Rose-breasted Grosbeak'),
]

# Same species, male and female look very different → shown side-by-side
DIMORPHIC_BIRDS = [
    ('Cardinal rouge',       'Northern Cardinal'),
    ('Carouge à épaulettes', 'Red-winged Blackbird'),
    ('Vacher à tête brune',  'Brown-headed Cowbird'),
]

# Two different-but-similar species → shown side-by-side for comparison
COMPARISON_PAIRS = [
    (('Pic chevelu', 'Hairy Woodpecker'),
     ('Pic mineur',  'Downy Woodpecker')),
]


# ── Font / image helpers ──────────────────────────────────────────────────────

def _font(size, style='regular'):
    names = {
        'regular':    'lmroman10-regular.otf',
        'bold':       'lmroman10-bold.otf',
        'italic':     'lmroman10-italic.otf',
        'bolditalic': 'lmroman10-bolditalic.otf',
    }
    try:
        return ImageFont.truetype(str(FONT_DIR / names[style]), size)
    except Exception:
        try:
            return ImageFont.truetype(str(FONT_DIR / names['regular']), size)
        except Exception:
            return ImageFont.load_default()


def _fitted_font(text, max_width, max_size, style='regular', min_size=32):
    """Return the largest font (≤ max_size) whose rendered text fits max_width."""
    size = max_size
    while size >= min_size:
        f = _font(size, style)
        try:
            w = f.getlength(text)
        except AttributeError:
            bbox = f.getbbox(text)
            w = bbox[2] - bbox[0]
        if w <= max_width:
            return f
        size -= 4
    return _font(min_size, style)


def _fill_photo(path, area_w, area_h):
    """Scale image to cover (area_w × area_h), center-crop, return RGB Image."""
    img = Image.open(path).convert('RGB')
    iw, ih = img.size
    scale = max(area_w / iw, area_h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - area_w) // 2
    top  = (nh - area_h) // 2
    return img.crop((left, top, left + area_w, top + area_h))


def _fit_photo(path, area_w, area_h, bg=BG_COLOR):
    """Scale image to fit within (area_w × area_h), centered on background.

    Used for side-by-side columns where cropping would risk cutting out the bird.
    """
    img = Image.open(path).convert('RGB')
    img.thumbnail((area_w, area_h), Image.LANCZOS)
    canvas = Image.new('RGB', (area_w, area_h), bg)
    x = (area_w - img.width) // 2
    y = (area_h - img.height) // 2
    canvas.paste(img, (x, y))
    return canvas


def _find_images(name, suffix=''):
    """Return sorted list of image paths for a bird name (+ optional suffix)."""
    safe = name.replace(' ', '_')
    prefix = f"{safe}{suffix}_"
    exts = {'.jpg', '.jpeg', '.png', '.webp'}
    return sorted(p for p in IMAGE_DIR.iterdir()
                  if p.stem.startswith(prefix) and p.suffix.lower() in exts)


# ── Card generators ───────────────────────────────────────────────────────────

def _make_regular_card(french, english, output_path):
    """Single bird: full-width photo + French/English name below."""
    images = _find_images(french)
    if not images:
        print(f"  Warning: no images found for '{french}'")
        return None

    canvas = Image.new('RGB', (WIDTH, HEIGHT), BG_COLOR)
    photo  = _fill_photo(random.choice(images), WIDTH, PHOTO_H)
    canvas.paste(photo, (0, 0))

    draw = ImageDraw.Draw(canvas)
    draw.line([(0, PHOTO_H), (WIDTH, PHOTO_H)], fill=DIVIDER_COLOR, width=2)

    margin   = 40
    max_w    = WIDTH - 2 * margin
    font_fr  = _fitted_font(french,  max_w, 90, 'bold')
    font_en  = _fitted_font(english, max_w, 55, 'italic')
    cx       = WIDTH // 2

    draw.text((cx, PHOTO_H + TEXT_H // 3),      french,  fill=TEXT_COLOR,      font=font_fr, anchor='mm')
    draw.text((cx, PHOTO_H + TEXT_H * 2 // 3),  english, fill=SECONDARY_COLOR, font=font_en, anchor='mm')

    canvas.save(output_path)
    return output_path


def _make_comparison_card(fr1, en1, fr2, en2, output_path):
    """Two species side-by-side for visual comparison."""
    imgs1 = _find_images(fr1)
    imgs2 = _find_images(fr2)
    if not imgs1 or not imgs2:
        print(f"  Warning: missing images for comparison '{fr1}' / '{fr2}'")
        return None

    col_w  = WIDTH // 2   # 600
    margin = 25
    max_w  = col_w - 2 * margin

    canvas = Image.new('RGB', (WIDTH, HEIGHT), BG_COLOR)
    canvas.paste(_fit_photo(random.choice(imgs1), col_w, PHOTO_H), (0,     0))
    canvas.paste(_fit_photo(random.choice(imgs2), col_w, PHOTO_H), (col_w, 0))

    draw = ImageDraw.Draw(canvas)
    draw.line([(col_w, 0), (col_w, PHOTO_H)],  fill=DIVIDER_COLOR, width=3)
    draw.line([(0, PHOTO_H), (WIDTH, PHOTO_H)], fill=DIVIDER_COLOR, width=2)

    for cx, fr, en in [(col_w // 2, fr1, en1), (col_w + col_w // 2, fr2, en2)]:
        font_fr = _fitted_font(fr, max_w, 72, 'bold')
        font_en = _fitted_font(en, max_w, 44, 'italic')
        draw.text((cx, PHOTO_H + TEXT_H // 3),     fr, fill=TEXT_COLOR,      font=font_fr, anchor='mm')
        draw.text((cx, PHOTO_H + TEXT_H * 2 // 3), en, fill=SECONDARY_COLOR, font=font_en, anchor='mm')

    canvas.save(output_path)
    return output_path


def _make_dimorphic_card(french, english, output_path):
    """Same species, male and female side-by-side with shared species label."""
    male_imgs   = _find_images(french, '_mâle')
    female_imgs = _find_images(french, '_femelle')
    if not male_imgs or not female_imgs:
        print(f"  Warning: missing male/female images for '{french}'")
        return None

    col_w  = WIDTH // 2   # 600
    margin = 25
    max_w  = WIDTH - 2 * margin

    canvas = Image.new('RGB', (WIDTH, HEIGHT), BG_COLOR)
    canvas.paste(_fit_photo(random.choice(male_imgs),   col_w, DIM_PHOTO_H), (0,     0))
    canvas.paste(_fit_photo(random.choice(female_imgs), col_w, DIM_PHOTO_H), (col_w, 0))

    draw = ImageDraw.Draw(canvas)

    # Vertical divider — stops at the shared text zone
    draw.line([(col_w, 0), (col_w, DIM_PHOTO_H + DIM_LABEL_H)], fill=DIVIDER_COLOR, width=3)
    # Horizontal line under photos
    draw.line([(0, DIM_PHOTO_H), (WIDTH, DIM_PHOTO_H)], fill=DIVIDER_COLOR, width=2)
    # Horizontal line under sublabels
    draw.line([(0, DIM_PHOTO_H + DIM_LABEL_H), (WIDTH, DIM_PHOTO_H + DIM_LABEL_H)],
              fill=DIVIDER_COLOR, width=2)

    # "(mâle)" / "(femelle)" sub-labels in respective columns
    label_y    = DIM_PHOTO_H + DIM_LABEL_H // 2
    font_sub   = _font(50, 'italic')
    draw.text((col_w // 2,           label_y), '(mâle)',    fill=SECONDARY_COLOR, font=font_sub, anchor='mm')
    draw.text((col_w + col_w // 2,   label_y), '(femelle)', fill=SECONDARY_COLOR, font=font_sub, anchor='mm')

    # Shared species name spanning full width
    shared_top = DIM_PHOTO_H + DIM_LABEL_H
    font_fr    = _fitted_font(french,  max_w, 90, 'bold')
    font_en    = _fitted_font(english, max_w, 55, 'italic')
    cx         = WIDTH // 2

    draw.text((cx, shared_top + DIM_SHARED_H // 3),     french,  fill=TEXT_COLOR,      font=font_fr, anchor='mm')
    draw.text((cx, shared_top + DIM_SHARED_H * 2 // 3), english, fill=SECONDARY_COLOR, font=font_en, anchor='mm')

    canvas.save(output_path)
    return output_path


# ── Public API ────────────────────────────────────────────────────────────────

def _build_card_list():
    """Build the full list of available cards as (type, args) tuples."""
    cards = []

    for fr, en in REGULAR_BIRDS:
        if _find_images(fr):
            cards.append(('regular', (fr, en)))

    for fr, en in DIMORPHIC_BIRDS:
        if _find_images(fr, '_mâle') and _find_images(fr, '_femelle'):
            cards.append(('dimorphic', (fr, en)))

    for (fr1, en1), (fr2, en2) in COMPARISON_PAIRS:
        if _find_images(fr1) and _find_images(fr2):
            cards.append(('comparison', (fr1, en1, fr2, en2)))

    return cards


def generate_bird_names_image(output_path='figures/oiseaux.png'):
    """Pick a random bird card and return the output file path.

    Called by the scheduler. Returns the output path or None on failure.
    """
    os.makedirs('figures', exist_ok=True)
    cards = _build_card_list()
    if not cards:
        print("No bird images found in oiseaux/")
        return None

    card_type, args = random.choice(cards)

    if card_type == 'regular':
        return _make_regular_card(*args, output_path)
    elif card_type == 'comparison':
        return _make_comparison_card(*args, output_path)
    elif card_type == 'dimorphic':
        return _make_dimorphic_card(*args, output_path)

    return None


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys

    os.makedirs('figures', exist_ok=True)
    cards = _build_card_list()

    total = len(cards)
    missing = (len(REGULAR_BIRDS) - sum(1 for t, _ in cards if t == 'regular') +
               len(DIMORPHIC_BIRDS) - sum(1 for t, _ in cards if t == 'dimorphic') +
               len(COMPARISON_PAIRS) - sum(1 for t, _ in cards if t == 'comparison'))

    print(f"Cards available: {total}  |  Missing images: {missing}\n")

    if '--all' in sys.argv:
        # Generate every card (useful for a full review)
        for card_type, args in cards:
            if card_type == 'regular':
                fr, en = args
                out = f"figures/bird_{fr.replace(' ', '_')}.png"
                _make_regular_card(fr, en, out)
                print(f"  {out}")
            elif card_type == 'comparison':
                fr1, en1, fr2, en2 = args
                out = f"figures/bird_{fr1.replace(' ', '_')}_vs_{fr2.replace(' ', '_')}.png"
                _make_comparison_card(fr1, en1, fr2, en2, out)
                print(f"  {out}")
            elif card_type == 'dimorphic':
                fr, en = args
                out = f"figures/bird_{fr.replace(' ', '_')}_dimorphic.png"
                _make_dimorphic_card(fr, en, out)
                print(f"  {out}")
    else:
        # Generate one random card
        path = generate_bird_names_image()
        if path:
            print(f"Generated: {path}")
        print("\nRun with --all to generate every card for review.")
