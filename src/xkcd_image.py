import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import textwrap
import random
import os

def download_xkcd_font():
    """
    Download XKCD font if not already present.
    Returns the font path.
    """
    font_path = "xkcd-script.ttf"
    if not os.path.exists(font_path):
        print("Downloading XKCD font...")
        font_url = "https://github.com/ipython/xkcd-font/raw/master/xkcd-script/font/xkcd-script.ttf"
        response = requests.get(font_url)
        with open(font_path, 'wb') as f:
            f.write(response.content)
        print("Font downloaded.")
    return font_path

def fetch_xkcd(comic_id=None):
    """
    Fetch XKCD comic data.
    If comic_id is None, fetches the latest comic.
    """
    if comic_id:
        url = f"https://xkcd.com/{comic_id}/info.0.json"
    else:
        url = "https://xkcd.com/info.0.json"

    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def calculate_text_height(text, font, max_width, margin=20):
    """
    Calculate the actual height needed for wrapped text.
    """
    # Create a temporary image to measure text
    temp_img = Image.new('RGB', (1, 1))
    draw = ImageDraw.Draw(temp_img)

    # Wrap text
    chars_per_line = (max_width - 2 * margin) // (font.size // 2)
    wrapped_text = textwrap.fill(text, width=chars_per_line)

    # Get bounding box of wrapped text
    bbox = draw.textbbox((0, 0), wrapped_text, font=font)
    text_height = bbox[3] - bbox[1]

    return text_height, wrapped_text

def create_eink_image(comic_data, width=1200, height=1600, output_path="figures/xkcd_eink.png"):
    """
    Create an e-ink formatted image with XKCD comic and legend.

    Args:
        comic_data: Dictionary with 'img' (image URL) and 'alt' (legend text)
        width: Target width in pixels (default 1200)
        height: Target height in pixels (default 1600)
        output_path: Path to save the output PNG
    """
    # Download the comic image
    img_response = requests.get(comic_data['img'])
    img_response.raise_for_status()
    comic_img = Image.open(BytesIO(img_response.content))

    # Convert to RGB if necessary
    if comic_img.mode != 'RGB':
        comic_img = comic_img.convert('RGB')

    # Create white canvas
    canvas = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(canvas)

    # Load XKCD font
    legend_text = comic_data['alt']
    text_length = len(legend_text)

    # Determine font size based on text length
    if text_length < 50:
        font_size = 32
    elif text_length < 150:
        font_size = 24
    elif text_length < 300:
        font_size = 20
    else:
        font_size = 16

    # Try to load XKCD font
    try:
        font_path = download_xkcd_font()
        font = ImageFont.truetype(font_path, font_size)
    except Exception as e:
        print(f"Could not load XKCD font: {e}, using fallback")
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        except:
            font = ImageFont.load_default()

    # Calculate actual text height needed
    margin = 20
    text_height, wrapped_text = calculate_text_height(legend_text, font, width, margin)
    legend_height = text_height + 2 * margin  # Add padding top and bottom

    # Calculate available space for comic
    comic_space_height = height - legend_height

    # Resize comic to fit available space while maintaining aspect ratio
    comic_ratio = comic_img.width / comic_img.height
    target_ratio = width / comic_space_height

    if comic_ratio > target_ratio:
        # Image is wider - fit to width
        new_width = width - 40  # 20px padding on each side
        new_height = int(new_width / comic_ratio)
    else:
        # Image is taller - fit to height
        new_height = comic_space_height - 40
        new_width = int(new_height * comic_ratio)

    comic_img = comic_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Center the comic horizontally and vertically in available space
    x_offset = (width - new_width) // 2
    y_offset = (comic_space_height - new_height) // 2
    canvas.paste(comic_img, (x_offset, y_offset))

    # Add legend text at bottom
    text_y = height - legend_height + margin

    # Draw text
    draw.text((margin, text_y), wrapped_text, fill='black', font=font)

    # Save the image
    canvas.save(output_path)
    print(f"Saved e-ink image to {output_path}")
    print(f"Comic: {comic_data['title']} (#{comic_data['num']})")

    return output_path

def xkcd_todays_image():
    comic_data = fetch_xkcd()
    return create_eink_image(comic_data, output_path='figures/todays_xkcd.png')

def xkcd_random_image():

    # Get latest comic number
    latest = fetch_xkcd()
    latest_num = latest['num']

    # Fetch a random comic
    random_num = random.randint(1, latest_num)
    print(f"Fetching random XKCD #{random_num}...")

    comic_data = fetch_xkcd(random_num)
    return create_eink_image(comic_data, output_path='figures/random_xkcd.png')


# Main execution - fetch random comic for testing
if __name__ == "__main__":
    #xkcd_todays_image()
    xkcd_random_image()

