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
INPUT_DIR = "~/Pictures"  # Directory to scan for images
OUTPUT_DIR = "~/Documents/cadre_chalet_code/preprocessed_for_eink"  # Where processed images go

# === MODE ===
TEST_MODE = False  # True: sample images across score range, False: only process above threshold

# === PERFORMANCE ===
NUM_PROCESSES = 8  # Number of parallel processes for scoring (set to your CPU count)
TEST_SAMPLE_SIZE = 500  # In test mode, only score this many randomly selected images

# === DISPLAY SETTINGS ===
DISPLAY_WIDTH = 1200
DISPLAY_HEIGHT = 1600
EINK_PALETTE = (0,0,0, 255,255,255, 255,255,0, 255,0,0, 0,0,0, 0,0,255, 0,255,0)  # 7-color palette
BACKGROUND_COLOR = (255, 255, 255)  # Color for letterboxing
RESIZE_IMAGES = False  # Set to True to resize/letterbox to display dimensions

# === TEST MODE SETTINGS ===
IMAGES_PER_BIN = 5  # How many images to sample from each 10% percentile bin
BIN_SIZE = 10  # Percentile bin size (10 = 0-10%, 10-20%, etc.)

# === SCORING WEIGHTS (these determine what makes a "good" image) ===
# Scores are now multiplicative - all metrics must be good for a high score
WEIGHT_SATURATION = 1.0      # Higher = prefer colorful images
WEIGHT_EDGE_STRENGTH = 1.8   # Higher = prefer sharp, high-contrast images
WEIGHT_COLOR_SIMPLICITY = 2.0  # Higher = prefer images with fewer colors
WEIGHT_BRIGHTNESS_RANGE = 1.9  # Higher = prefer images with good contrast

# Scoring curve adjustments - use to emphasize differences
SATURATION_POWER = 1.5    # >1 = penalize low saturation more heavily
EDGE_POWER = 1.3          # >1 = penalize soft edges more heavily
BRIGHTNESS_POWER = 1.4    # >1 = penalize low contrast more heavily
COLOR_SIMPLICITY_POWER = 1.2  # >1 = reward simple palettes more

# === SELECTION THRESHOLDS (for normal mode) ===
MIN_SCORE = 40  # Minimum score (0-100) to process an image

# === PROCESSING PARAMETERS ===
CONTRAST_BOOST = 1.3    # 1.0 = no change, >1.0 = more contrast (try 1.2-1.5)
SATURATION_BOOST = 1.4  # 1.0 = no change, >1.0 = more saturated (try 1.3-1.6)
SHARPNESS_BOOST = 1.2   # 1.0 = no change, >1.0 = sharper (try 1.1-1.4)
APPLY_QUANTIZATION = True  # Apply 7-color palette reduction

# === FILE HANDLING ===
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}
OUTPUT_FORMAT = 'PNG'  # Output file format

# ============================================================================
# SCORING FUNCTIONS
# ============================================================================

def calculate_color_saturation(img):
    """Calculate average color saturation (0-100)"""
    img_hsv = img.convert('HSV')
    hsv_data = np.array(img_hsv)
    saturation = hsv_data[:, :, 1]
    # Use 90th percentile instead of mean to focus on the vibrant parts
    return float(np.percentile(saturation, 90)) / 255 * 100

def calculate_edge_strength(img):
    """Calculate edge strength using Sobel filter (0-100)"""
    gray = img.convert('L')
    # Resize for consistent scoring across different resolutions
    gray.thumbnail((800, 800))
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_data = np.array(edges)
    # Use 95th percentile to focus on strongest edges
    return float(np.percentile(edge_data, 95)) / 255 * 100

def calculate_color_simplicity(img):
    """Calculate color palette simplicity - fewer unique colors = higher score (0-100)"""
    img_small = img.copy()
    img_small.thumbnail((100, 100))

    # Quantize to reduce similar colors
    img_quant = img_small.quantize(colors=64)
    colors = img_quant.getcolors()

    if colors is None:
        unique_colors = 64
    else:
        unique_colors = len(colors)

    # Nonlinear scaling: 1-10 colors = 90-100, 20 colors = 70, 40 colors = 40, 64+ colors = 0-20
    if unique_colors <= 10:
        score = 90 + (10 - unique_colors)
    elif unique_colors <= 20:
        score = 70 + (20 - unique_colors) * 2
    elif unique_colors <= 40:
        score = 40 + (40 - unique_colors) * 1.5
    else:
        score = max(0, 40 - (unique_colors - 40))

    return score

def calculate_brightness_range(img):
    """Calculate brightness contrast range (0-100)"""
    gray = img.convert('L')
    gray_data = np.array(gray)

    # Use percentiles to ignore outliers
    low = np.percentile(gray_data, 5)
    high = np.percentile(gray_data, 95)
    brightness_range = high - low

    # Apply nonlinear scaling - reward high contrast more
    score = (brightness_range / 255) ** 0.7 * 100
    return score

def score_image(img_path):
    """Calculate composite score for an image (0-100)"""
    try:
        with Image.open(img_path) as img:
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Calculate individual metrics (0-100 scale)
            saturation = calculate_color_saturation(img)
            edges = calculate_edge_strength(img)
            simplicity = calculate_color_simplicity(img)
            brightness = calculate_brightness_range(img)

            # Apply power curves to emphasize differences
            saturation_scaled = (saturation / 100) ** SATURATION_POWER * 100
            edges_scaled = (edges / 100) ** EDGE_POWER * 100
            simplicity_scaled = (simplicity / 100) ** COLOR_SIMPLICITY_POWER * 100
            brightness_scaled = (brightness / 100) ** BRIGHTNESS_POWER * 100

            # Weighted geometric mean (multiplicative) - all must be good
            # This creates better separation than additive scoring
            total_weight = (WEIGHT_SATURATION + WEIGHT_EDGE_STRENGTH +
                          WEIGHT_COLOR_SIMPLICITY + WEIGHT_BRIGHTNESS_RANGE)

            # Convert to geometric mean: product of weighted values
            score = (
                (saturation_scaled ** WEIGHT_SATURATION) *
                (edges_scaled ** WEIGHT_EDGE_STRENGTH) *
                (simplicity_scaled ** WEIGHT_COLOR_SIMPLICITY) *
                (brightness_scaled ** WEIGHT_BRIGHTNESS_RANGE)
            ) ** (1 / total_weight)

            return img_path, score, {
                'saturation': saturation,
                'edges': edges,
                'simplicity': simplicity,
                'brightness': brightness,
                'final_sat': saturation_scaled,
                'final_edge': edges_scaled,
                'final_simp': simplicity_scaled,
                'final_bright': brightness_scaled
            }
    except Exception as e:
        print(f"Error scoring {img_path}: {e}")
        return img_path, 0, {}

# ============================================================================
# IMAGE PROCESSING
# ============================================================================

def apply_eink_palette(img):
    """Apply 7-color e-ink palette to image"""
    # Create palette image
    pal_img = Image.new('P', (1, 1))
    pal_img.putpalette(EINK_PALETTE + (0,0,0)*249)

    # Convert to palette mode
    img_quantized = img.quantize(palette=pal_img, dither=Image.FLOYDSTEINBERG)
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

            # 4. Apply e-ink palette quantization
            if APPLY_QUANTIZATION:
                img = apply_eink_palette(img)

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

    # In test mode, randomly sample images to score
    if TEST_MODE and len(image_files) > TEST_SAMPLE_SIZE:
        print(f"TEST MODE: Randomly sampling {TEST_SAMPLE_SIZE} images from {len(image_files)} total")
        image_files = random.sample(image_files, TEST_SAMPLE_SIZE)

    # Score all images in parallel
    print(f"\nScoring {len(image_files)} images using {NUM_PROCESSES} processes...")
    with Pool(processes=NUM_PROCESSES) as pool:
        results = pool.map(score_image, image_files)

    # Unpack results
    scored_images = [(score, img_path, metrics) for img_path, score, metrics in results]
    scored_images.sort(reverse=True)  # Highest scores first

    # Print score statistics
    scores = [s[0] for s in scored_images]
    print(f"\nScore Statistics:")
    print(f"  Min: {min(scores):.1f}")
    print(f"  Max: {max(scores):.1f}")
    print(f"  Mean: {np.mean(scores):.1f}")
    print(f"  Median: {np.median(scores):.1f}")

    # Select images to process
    if TEST_MODE:
        print(f"\n=== TEST MODE ===")
        print(f"Sampling {IMAGES_PER_BIN} images from each {BIN_SIZE}% percentile bin")

        # Group by percentile bins
        bins = defaultdict(list)
        for score, img_path, metrics in scored_images:
            percentile = int(score / BIN_SIZE) * BIN_SIZE
            bins[percentile].append((score, img_path, metrics))

        # Sample from each bin
        to_process = []
        for percentile in sorted(bins.keys(), reverse=True):
            bin_images = bins[percentile]
            sample_size = min(IMAGES_PER_BIN, len(bin_images))
            sampled = random.sample(bin_images, sample_size)
            to_process.extend([(percentile, score, img_path, metrics)
                             for score, img_path, metrics in sampled])
            print(f"  {percentile}-{percentile+BIN_SIZE}%: {len(bin_images)} images, sampling {sample_size}")

    else:
        print(f"\n=== NORMAL MODE ===")
        print(f"Processing images with score >= {MIN_SCORE}")
        to_process = [(None, score, img_path, metrics)
                     for score, img_path, metrics in scored_images
                     if score >= MIN_SCORE]
        print(f"Selected {len(to_process)} images")

    # Process selected images
    print(f"\nProcessing {len(to_process)} images...")
    for i, item in enumerate(to_process):
        if TEST_MODE:
            percentile, score, img_path, metrics = item
            prefix = f"{percentile:02d}"
        else:
            _, score, img_path, metrics = item
            prefix = f"{score:.1f}"

        # Create output filename
        output_name = f"{prefix}_{img_path.stem}.png" if prefix else f"{img_path.stem}.png"
        output_path = output_dir / output_name

        # Process
        success = process_image(img_path, output_path)
        if success:
            print(f"  [{i+1}/{len(to_process)}] Score {score:.1f} - {img_path.name} -> {output_name}")

    print(f"\nDone! Processed images saved to: {output_dir}")

if __name__ == "__main__":
    main()
