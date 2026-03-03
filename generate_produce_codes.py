#!/usr/bin/env python3
"""
Generate e-ink display images (1200x1600) for learning grocery produce codes.
Shows fruit/vegetable images with French names and PLU codes.
"""

import os
import random
from pathlib import Path


def load_produce_list(filepath='produce_list.txt'):
    """Load produce items from text file.
    
    Expected format: French Name,Code
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


def download_image(search_term, code, cache_dir='fruits_et_legumes'):
    """Download an image for a produce item and cache it locally.
    
    Args:
        search_term: Term to search for
        code: PLU code (used as filename)
        cache_dir: Directory to cache images
    
    Returns:
        Path to cached image file
    """
    import requests
    from PIL import Image
    from io import BytesIO
    import re
    
    cache_path = Path(cache_dir)
    cache_path.mkdir(exist_ok=True)
    
    image_file = cache_path / f"{code}.png"
    
    # Return cached image if it exists
    if image_file.exists():
        return str(image_file)
    
    # Use DuckDuckGo image search
    try:
        # DuckDuckGo image search endpoint
        search_url = "https://duckduckgo.com/"
        
        # Get search token
        params = {'q': search_term}
        response = requests.get(search_url, params=params, timeout=10)
        
        # Extract vqd token from response
        vqd_match = re.search(r'vqd=([\d-]+)', response.text)
        if not vqd_match:
            raise Exception("Could not get search token")
        
        vqd = vqd_match.group(1)
        
        # Search for images
        image_search_url = "https://duckduckgo.com/i.js"
        params = {
            'l': 'us-en',
            'o': 'json',
            'q': search_term,
            'vqd': vqd,
            'f': ',,,',
            'p': '1',
            'v7exp': 'a'
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        }
        
        response = requests.get(image_search_url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        # Get first image URL
        if data.get('results') and len(data['results']) > 0:
            image_url = data['results'][0]['image']
            
            # Download the image
            img_response = requests.get(image_url, timeout=10, headers=headers)
            img = Image.open(BytesIO(img_response.content))
            
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Save to cache
            img.save(image_file)
            print(f"Downloaded and cached image for {search_term} (code: {code})")
            return str(image_file)
        
    except Exception as e:
        print(f"Warning: Could not download image for {search_term}: {e}")
    
    # Create a placeholder if download fails
    from PIL import Image, ImageDraw, ImageFont
    
    placeholder = Image.new('RGB', (400, 400), 'white')
    draw = ImageDraw.Draw(placeholder)
    
    # Draw a simple colored rectangle as background
    draw.rectangle([50, 50, 350, 350], fill='#f0f0f0', outline='#cccccc', width=3)
    
    # Add text
    try:
        font = ImageFont.truetype('./fonts/lmroman10-regular.otf', 30)
    except:
        font = ImageFont.load_default()
    
    draw.text((200, 180), search_term, fill='#666666', font=font, anchor='mm')
    draw.text((200, 220), f"Code: {code}", fill='#999999', font=font, anchor='mm')
    
    placeholder.save(image_file)
    print(f"Created placeholder for {search_term} (code: {code})")
    
    return str(image_file)


def create_produce_image(produce_items, output_file='codes_fruits_et_legumes.png',
                        font_name_size=60, font_code_size=90):
    """Create a 1200x1600 image with 6 produce items in 2x3 grid.
    
    Args:
        produce_items: List of up to 6 produce dicts with 'name' and 'code'
        output_file: Output filename
        font_name_size: Font size for produce names
        font_code_size: Font size for PLU codes
    
    Returns:
        Name of the generated file
    """
    from PIL import Image, ImageDraw, ImageFont
    
    # Image dimensions
    WIDTH = 1200
    HEIGHT = 1600
    
    # Layout: 2 columns x 3 rows
    COLS = 2
    ROWS = 3
    
    # Calculate cell dimensions
    cell_width = WIDTH // COLS
    cell_height = HEIGHT // ROWS
    
    # Create white background
    image = Image.new('RGB', (WIDTH, HEIGHT), 'white')
    draw = ImageDraw.Draw(image)
    
    # Load font
    try:
        font_name = ImageFont.truetype('./fonts/lmroman10-regular.otf', font_name_size)
        font_code = ImageFont.truetype('./fonts/lmroman10-regular.otf', font_code_size)
    except Exception as e:
        print(f"Warning: Could not load custom font: {e}")
        font_name = ImageFont.load_default()
        font_code = ImageFont.load_default()
    
    # Place each produce item in grid
    for idx, item in enumerate(produce_items[:6]):  # Max 6 items
        col = idx % COLS
        row = idx // COLS
        
        # Calculate cell position
        x = col * cell_width
        y = row * cell_height
        
        # Load and resize produce image
        try:
            produce_img = Image.open(item['image_path'])
            
            # Resize to fit in cell (leave space for text)
            img_max_width = int(cell_width * 0.8)
            img_max_height = int(cell_height * 0.5)
            
            produce_img.thumbnail((img_max_width, img_max_height), Image.Resampling.LANCZOS)
            
            # Center the image horizontally in cell
            img_x = x + (cell_width - produce_img.width) // 2
            img_y = y + 20  # Small top margin
            
            image.paste(produce_img, (img_x, img_y))
            
        except Exception as e:
            print(f"Warning: Could not load image for {item['name']}: {e}")
        
        # Draw name (below image)
        name_y = y + int(cell_height * 0.55)
        draw.text((x + cell_width // 2, name_y), item['name'], 
                 fill='black', font=font_name, anchor='mm')
        
        # Draw code (below name, larger)
        code_y = y + int(cell_height * 0.75)
        draw.text((x + cell_width // 2, code_y), item['code'], 
                 fill='black', font=font_code, anchor='mm')
        
        # Draw cell borders (optional, for debugging)
        # draw.rectangle([x, y, x + cell_width, y + cell_height], outline='lightgray')
    
    # Save image
    image.save(output_file)
    print(f"Generated: {output_file}")
    return output_file


def generate_random_sheet(produce_list, num_items=6):
    """Generate a random selection sheet with specified number of items."""
    selected = random.sample(produce_list, min(num_items, len(produce_list)))
    
    # Download images for selected items
    for item in selected:
        item['image_path'] = download_image(item['name'], item['code'])
    
    return create_produce_image(selected)


def generate_all_sheets(produce_list, items_per_sheet=6):
    """Generate multiple sheets to display all produce items.
    
    For testing: creates multiple images with 6 items each until all are shown.
    """
    import math
    
    # Download all images first
    print("Downloading and caching all images...")
    for item in produce_list:
        item['image_path'] = download_image(item['name'], item['code'])
    
    # Calculate number of sheets needed
    num_sheets = math.ceil(len(produce_list) / items_per_sheet)
    
    generated_files = []
    for i in range(num_sheets):
        start_idx = i * items_per_sheet
        end_idx = min(start_idx + items_per_sheet, len(produce_list))
        
        items = produce_list[start_idx:end_idx]
        output_file = f'figures/codes_fruits_et_legumes_{i+1:02d}.png'
        
        filename = create_produce_image(items, output_file)
        generated_files.append(filename)
    
    print(f"\nGenerated {len(generated_files)} sheets total")
    return generated_files


def main():
    """Main function for testing - generates all sheets."""
    # Load produce list
    produce_list = load_produce_list('produce_list.txt')
    print(f"Loaded {len(produce_list)} produce items")
    
    # Generate all sheets for testing
    generate_all_sheets(produce_list, items_per_sheet=6)


if __name__ == '__main__':
    main()
