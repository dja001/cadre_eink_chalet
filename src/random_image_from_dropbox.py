import os
import random
from PIL import Image, ImageStat
from pathlib import Path

def process_random_figure(figure_dir, output_dir=None):
    """
    Picks a random image from figure_dir, resizes it to fit 1200x1600
    while maintaining aspect ratio (scaling up if needed), adds borders
    with the average color, and saves it as PNG.

    Args:
        figure_dir: Directory containing figure images
        output_dir: Directory to save the output (defaults to figure_dir)

    Returns:
        str: Name of the generated PNG file (without path)
    """
    # Set output directory to figure_dir if not specified
    if output_dir is None:
        output_dir = figure_dir

    # Get all image files
    figure_path = Path(figure_dir)
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tiff'}
    image_files = [f for f in figure_path.iterdir()
                   if f.is_file() and f.suffix.lower() in image_extensions]

    if not image_files:
        raise ValueError(f"No image files found in {figure_dir}")

    # Pick random image
    selected_file = random.choice(image_files)

    # Open image
    img = Image.open(selected_file)

    # Convert to RGB if necessary (for consistent color handling)
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGB')

    # Calculate average color
    stat = ImageStat.Stat(img)
    avg_color = tuple(int(c) for c in stat.mean[:3])  # RGB values

    # Calculate scaling to fit within 1200x1600 while maintaining aspect ratio
    target_width, target_height = 1200, 1600
    width_ratio = target_width / img.width
    height_ratio = target_height / img.height

    # Use the smaller ratio to ensure the image fits within bounds
    scale_ratio = min(width_ratio, height_ratio)

    # Calculate new dimensions
    new_width = int(img.width * scale_ratio)
    new_height = int(img.height * scale_ratio)

    # Resize image (will scale up if smaller, down if larger)
    img_resized = img.resize((new_width, new_height), Image.LANCZOS)

    # Create new image with target size and average color background
    new_img = Image.new('RGB', (target_width, target_height), avg_color)

    # Calculate position to center the resized image
    x = (target_width - new_width) // 2
    y = (target_height - new_height) // 2

    # Paste resized image onto the colored background
    if img_resized.mode == 'RGBA':
        new_img.paste(img_resized, (x, y), img_resized)  # Use alpha channel as mask
    else:
        new_img.paste(img_resized, (x, y))

    # Generate output filename
    output_name = 'random_dropbox_image.png'
    output_path = Path(output_dir) / output_name

    # Save as PNG
    new_img.save(output_path, 'PNG')

    return output_path


def random_image_from_dropbox():

    from dropbox_access import sync_dropbox_dir

    image_dir = 'figures/dropbox_random_images/'

    # sync dropbox directory
    sync_dropbox_dir('/random_images', image_dir)

    # make the image and return its name
    return process_random_figure(image_dir, output_dir='figures/')


if __name__ == '__main__':
    res = random_image_from_dropbox()
    print(f'done with {res}')
