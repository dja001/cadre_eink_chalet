#!/usr/bin/env python3
"""
E-ink Display Image Optimizer
Scores, selects, and processes images for optimal display on 7-color e-ink screens
"""

import os
import random
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np
from collections import defaultdict
from multiprocessing import Pool, cpu_count

# ============================================================================
# CONFIGURATION - Adjust these parameters to tune the system
# ============================================================================

# === PATHS ===
INPUT_DIR = "~/Documents/cadre_chalet_code/cropped_pictures/"  # Directory to scan for images
OUTPUT_DIR = "~/Documents/cadre_chalet_code/color_process/"  # Where processed images go


# === DISPLAY SETTINGS ===
DISPLAY_WIDTH = 1200
DISPLAY_HEIGHT = 1600
EINK_PALETTE = (0,0,0, 255,255,255, 255,255,0, 255,0,0, 0,0,0, 0,0,255, 0,255,0)  # 7-color palette
BACKGROUND_COLOR = (255, 255, 255)  # Color for letterboxing
RESIZE_IMAGES = False  # Set to True to resize/letterbox to display dimensions

# === PROCESSING PARAMETERS ===
CONTRAST_BOOST = 1.3    # 1.0 = no change, >1.0 = more contrast (try 1.2-1.5)
SATURATION_BOOST = 1.4  # 1.0 = no change, >1.0 = more saturated (try 1.3-1.6)
SHARPNESS_BOOST = 1.2   # 1.0 = no change, >1.0 = sharper (try 1.1-1.4)
APPLY_QUANTIZATION = True  # Apply 7-color palette reduction

# === FILE HANDLING ===
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}
OUTPUT_FORMAT = 'PNG'  # Output file format


# ============================================================================
# IMAGE PROCESSING
# ============================================================================

def apply_eink_palette(img):
    """Apply 7-color e-ink palette to image"""
    # Create palette image
    pal_img = Image.new('P', (1, 1))
    pal_img.putpalette(EINK_PALETTE + (0,0,0)*249)

    # Convert to palette mode
    #img_quantized = img.quantize(palette=pal_img, dither=Image.FLOYDSTEINBERG)
    img_quantized = img.quantize(palette=pal_img, dither=Image.ORDERED)

    return img_quantized.convert('RGB')

def process_image(img_path, output_path):
    """Apply all processing steps to an image"""
    try:
        with Image.open(img_path) as img:
            # Convert to RGB
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # 1. Enhance contrast
            if CONTRAST_BOOST != 1.0:
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(CONTRAST_BOOST)

            # 2. Enhance saturation
            if SATURATION_BOOST != 1.0:
                enhancer = ImageEnhance.Color(img)
                img = enhancer.enhance(SATURATION_BOOST)

            # 3. Enhance sharpness
            if SHARPNESS_BOOST != 1.0:
                enhancer = ImageEnhance.Sharpness(img)
                img = enhancer.enhance(SHARPNESS_BOOST)

            ## 4. Apply e-ink palette quantization
            #if APPLY_QUANTIZATION:
            #    img = apply_eink_palette(img)

            # 5. Resize/letterbox to display dimensions (if enabled)
            if RESIZE_IMAGES:
                img = letterbox_image(img, DISPLAY_WIDTH, DISPLAY_HEIGHT)

            # 6. Save
            img.save(output_path, OUTPUT_FORMAT)
            return True

    except Exception as e:
        print(f"Error processing {img_path}: {e}")
        return False

def letterbox_image(img, target_width, target_height):
    """Resize image to fit target dimensions with letterboxing"""
    img_ratio = img.width / img.height
    target_ratio = target_width / target_height

    if img_ratio > target_ratio:
        # Image is wider - fit to width
        new_width = target_width
        new_height = int(target_width / img_ratio)
    else:
        # Image is taller - fit to height
        new_height = target_height
        new_width = int(target_height * img_ratio)

    # Resize image
    img = img.resize((new_width, new_height), Image.LANCZOS)

    # Create background canvas
    canvas = Image.new('RGB', (target_width, target_height), BACKGROUND_COLOR)

    # Paste resized image centered
    x_offset = (target_width - new_width) // 2
    y_offset = (target_height - new_height) // 2
    canvas.paste(img, (x_offset, y_offset))

    return canvas

# ============================================================================
# MAIN LOGIC
# ============================================================================

def find_images(directory):
    """Recursively find all supported images in directory"""
    directory = Path(directory).expanduser()
    images = []
    for ext in SUPPORTED_FORMATS:
        images.extend(directory.rglob(f'*{ext}'))
        images.extend(directory.rglob(f'*{ext.upper()}'))
    return images

def main():
    # Expand paths
    input_dir = Path(INPUT_DIR).expanduser()
    output_dir = Path(OUTPUT_DIR).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Scanning for images in: {input_dir}")
    image_files = find_images(input_dir)
    print(f"Found {len(image_files)} images")

    if not image_files:
        print("No images found!")
        return

    # Process selected images
    print(f"\nProcessing {len(image_files)} images...")
    for i, source_image in enumerate(image_files):

        # Create output filename
        output_name = os.path.basename(source_image)
        output_image = output_dir / output_name

        # Process
        success = process_image(source_image, output_image)
        if success:
            print(f"Processed {output_image}")

    print(f"\nDone! Processed images saved to: {output_dir}")

if __name__ == "__main__":
    main()
