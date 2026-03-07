#!/usr/bin/env python3
"""
Generate e-ink display images (1200x1600) for learning grocery produce codes.
Shows fruit/vegetable images with French names and PLU codes.

Images are stored manually in fruits_et_legumes/ named after the French produce
name with spaces replaced by underscores, e.g.:
    fruits_et_legumes/Banane.png
    fruits_et_legumes/Pomme_Gala.png
    fruits_et_legumes/Chou-fleur.png

Run directly to generate all display sheets:
    python3 generate_produce_codes.py
"""

import os
import random
from pathlib import Path

IMAGE_DIR = Path('fruits_et_legumes')


def load_produce_list(filepath='produce_list.txt'):
    """Load produce items from text file.

    Expected format: French Name,PLU Code
    Example: Banane,4011
    """
    import csv

    produce = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 2 and not row[0].startswith('#'):
                name = row[0].strip()
                code = row[1].strip()
                produce.append({'name': name, 'code': code})
    return produce


def get_image_path(name):
    """Return the image path for a produce item, or None if not found.

    Expected filename: fruits_et_legumes/{name with spaces→underscores}.png
    Also accepts .jpg and .jpeg.
    """
    safe_name = name.replace(' ', '_')
    for ext in ('.png', '.jpg', '.jpeg', '.webp'):
        p = IMAGE_DIR / f"{safe_name}{ext}"
        if p.exists():
            return str(p)
    return None


def _create_placeholder(name, code, size=(600, 600)):
    """Return a PIL Image placeholder for items with no photo yet."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new('RGB', size, '#f0f0f0')
    draw = ImageDraw.Draw(img)
    draw.rectangle([6, 6, size[0] - 7, size[1] - 7], outline='#bbbbbb', width=4)

    try:
        font = ImageFont.truetype('./fonts/lmroman10-regular.otf', 32)
        small = ImageFont.truetype('./fonts/lmroman10-regular.otf', 24)
    except Exception:
        font = ImageFont.load_default()
        small = font

    cx, cy = size[0] // 2, size[1] // 2
    draw.text((cx, cy - 20), name, fill='#555555', font=font, anchor='mm')
    draw.text((cx, cy + 25), f"PLU {code}", fill='#888888', font=small, anchor='mm')

    return img


def create_produce_image(produce_items, output_file,
                         font_name_size=60, font_code_size=90):
    """Create a 1200x1600 image with up to 6 produce items in a 2×3 grid.

    Args:
        produce_items: List of dicts with 'name' and 'code' keys
        output_file: Output path
        font_name_size: Font size for produce names
        font_code_size: Font size for PLU codes

    Returns:
        Path of the generated file
    """
    from PIL import Image, ImageDraw, ImageFont

    WIDTH, HEIGHT = 1200, 1600
    COLS, ROWS = 2, 3
    cell_w = WIDTH // COLS
    cell_h = HEIGHT // ROWS

    image = Image.new('RGB', (WIDTH, HEIGHT), 'white')
    draw = ImageDraw.Draw(image)

    try:
        font_name = ImageFont.truetype('./fonts/lmroman10-regular.otf', font_name_size)
        font_code = ImageFont.truetype('./fonts/lmroman10-regular.otf', font_code_size)
    except Exception as e:
        print(f"Warning: could not load custom font: {e}")
        font_name = ImageFont.load_default()
        font_code = ImageFont.load_default()

    for idx, item in enumerate(produce_items[:6]):
        col = idx % COLS
        row = idx // COLS
        x = col * cell_w
        y = row * cell_h

        # Cell border
        draw.rectangle([x, y, x + cell_w - 1, y + cell_h - 1],
                        outline='#dddddd', width=2)

        # Produce photo (or placeholder)
        img_path = get_image_path(item['name'])
        if img_path:
            try:
                produce_img = Image.open(img_path).convert('RGB')
            except Exception as e:
                print(f"Warning: could not open {img_path}: {e}")
                produce_img = _create_placeholder(item['name'], item['code'])
        else:
            produce_img = _create_placeholder(item['name'], item['code'])

        max_w = int(cell_w * 0.85)
        max_h = int(cell_h * 0.55)
        produce_img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

        img_x = x + (cell_w - produce_img.width) // 2
        img_y = y + 15
        image.paste(produce_img, (img_x, img_y))

        # French name
        name_y = y + int(cell_h * 0.68)
        draw.text((x + cell_w // 2, name_y), item['name'],
                  fill='black', font=font_name, anchor='mm')

        # PLU code
        code_y = y + int(cell_h * 0.84)
        draw.text((x + cell_w // 2, code_y), item['code'],
                  fill='black', font=font_code, anchor='mm')

    image.save(output_file)
    print(f"  → {output_file}")
    return output_file


def generate_random_sheet(produce_list, num_items=6,
                          output_file='figures/codes_fruits_et_legumes.png'):
    """Pick random items and return a generated image path."""
    selected = random.sample(produce_list, min(num_items, len(produce_list)))
    return create_produce_image(selected, output_file)


def generate_all_sheets(produce_list, items_per_sheet=6):
    """Generate one sheet per page covering all produce items.

    Returns list of generated file paths.
    """
    import math

    os.makedirs('figures', exist_ok=True)
    num_sheets = math.ceil(len(produce_list) / items_per_sheet)
    generated = []

    for i in range(num_sheets):
        items = produce_list[i * items_per_sheet:(i + 1) * items_per_sheet]
        output_file = f'figures/codes_fruits_et_legumes_{i + 1:02d}.png'
        generated.append(create_produce_image(items, output_file))

    print(f"\nGenerated {len(generated)} sheet(s) in figures/")
    return generated


def print_missing_images(produce_list):
    """Print which items are missing a photo in fruits_et_legumes/."""
    missing = [item for item in produce_list if not get_image_path(item['name'])]
    if missing:
        print(f"{len(missing)} item(s) have no image (will show placeholder):")
        for item in missing:
            safe = item['name'].replace(' ', '_')
            print(f"  fruits_et_legumes/{safe}.png  ← {item['name']}")
    else:
        print("All items have images.")
    return missing


def generate_produce_codes_image() -> str:
    """Pick 6 random produce items and return a 1200x1600 e-ink image path.

    Called by the scheduler. Returns the output file path.
    """
    produce_list = load_produce_list('produce_list.txt')
    return generate_random_sheet(produce_list, output_file='figures/codes_fruits_et_legumes.png')


if __name__ == '__main__':
    produce_list = load_produce_list('produce_list.txt')
    print(f"Loaded {len(produce_list)} produce items\n")

    print_missing_images(produce_list)
    print()
    generate_all_sheets(produce_list)
