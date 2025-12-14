import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io

def get_todo_from_dropbox():

    import os
    import dropbox

    access_token = os.getenv('DROPBOX_API_TOKEN')
    if access_token is None:
        raise ValueError('Pleas load dropbox api token in env before running this script')
    
    dbx = dropbox.Dropbox(access_token)
    
    metadata, res = dbx.files_download("/listes/fermeture_du_chalet.txt")
    #print(metadata)
    #print(res)
    #print(res.content)
    #f.write(res.content)

    text = res.content.decode("utf-8")
    lines = text.splitlines()

    return lines


def create_todo_display_image(todo_list, npix_h=1200, npix_v=1600, bg_image=None,
                              font_path=None, padding=40, output_name='figures/todo.png'):
    """
    Create an e-ink display image with a todo list.

    Parameters:
    -----------
    todo_list : list of str
        List of todo items to display
    npix_h : int
        Horizontal resolution in pixels (default: 1200)
    npix_v : int
        Vertical resolution in pixels (default: 1600)
    bg_image : PIL.Image or str, optional
        Background image (PIL Image object or path to image file)
    font_path : str, optional
        Path to Latin Modern font file (.ttf). If None, uses default font.
    padding : int
        Padding around edges in pixels (default: 40)

    Returns:
    --------
    PIL.Image
        Generated image ready for e-ink display
    """

    # Create base image
    if bg_image is not None:
        if isinstance(bg_image, str):
            img = Image.open(bg_image).convert('RGB')
        else:
            img = bg_image.convert('RGB')
        img = img.resize((npix_h, npix_v), Image.LANCZOS)
    else:
        img = Image.new('RGB', (npix_h, npix_v), color='white')

    draw = ImageDraw.Draw(img, 'RGBA')

    n_items = len(todo_list)
    if n_items == 0:
        return img

    # Determine number of columns and font size
    if n_items <= 8:
        n_cols = 1
        base_font_size = 80
    elif n_items <= 16:
        n_cols = 1
        base_font_size = 60
    elif n_items <= 24:
        n_cols = 2
        base_font_size = 55
    else:
        n_cols = 2
        base_font_size = max(35, 70 - (n_items - 24) * 2)

    # Load font
    try:
        if font_path:
            font = ImageFont.truetype(font_path, base_font_size)
        else:
            # Try to find Latin Modern font in common locations
            lm_paths = [
                '/usr/share/fonts/opentype/lmodern/lmroman10-regular.otf',
                '/usr/share/fonts/truetype/lmodern/lmroman10-regular.ttf',
                'C:\\Windows\\Fonts\\lmroman10-regular.otf',
            ]
            font = None
            for path in lm_paths:
                try:
                    font = ImageFont.truetype(path, base_font_size)
                    break
                except:
                    continue
            if font is None:
                font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()

    # Calculate layout
    col_width = (npix_h - padding * 2) // n_cols
    col_gap = 20  # Gap between columns
    available_height = npix_v - 2 * padding

    # First pass: calculate wrapped text for all items to determine heights
    items_data = []
    for item in todo_list:
        text = f"• {item}"
        max_width = col_width - 40  # Account for padding
        wrapped_lines = wrap_text(text, font, max_width, draw)
        items_data.append(wrapped_lines)

    # Distribute items across columns
    items_per_col = (n_items + n_cols - 1) // n_cols

    # Calculate if items fit; if not, reduce font size
    line_spacing = base_font_size + 8
    box_padding = 15
    item_spacing = 20

    max_iterations = 10
    iteration = 0

    while iteration < max_iterations:
        # Calculate total height needed for each column
        col_heights = [0] * n_cols

        for idx in range(n_items):
            col = idx // items_per_col
            if col >= n_cols:
                col = n_cols - 1

            num_lines = len(items_data[idx])
            item_height = num_lines * line_spacing + 2 * box_padding + item_spacing
            col_heights[col] += item_height

        # Check if tallest column fits
        if max(col_heights) <= available_height:
            break

        # Reduce font size and recalculate
        base_font_size = int(base_font_size * 0.9)
        line_spacing = base_font_size + 8

        try:
            if font_path:
                font = ImageFont.truetype(font_path, base_font_size)
            else:
                for path in lm_paths:
                    try:
                        font = ImageFont.truetype(path, base_font_size)
                        break
                    except:
                        continue
        except:
            font = ImageFont.load_default()

        # Recalculate wrapped text with new font size
        items_data = []
        for item in todo_list:
            text = f"• {item}"
            max_width = col_width - 40
            wrapped_lines = wrap_text(text, font, max_width, draw)
            items_data.append(wrapped_lines)

        iteration += 1

    # Draw items
    col_y_positions = [padding] * n_cols  # Track current y position for each column

    for idx, wrapped_lines in enumerate(items_data):
        col = idx // items_per_col
        if col >= n_cols:
            col = n_cols - 1

        # Calculate position
        x = padding + col * (col_width + col_gap)
        y = col_y_positions[col]

        # Calculate item height based on number of lines
        num_lines = len(wrapped_lines)
        text_height = num_lines * line_spacing
        item_height = text_height + 2 * box_padding

        # Draw semi-transparent background box
        box_coords = [
            x + 5,
            y,
            x + col_width - 5,
            y + item_height
        ]

        # Semi-transparent white background
        draw.rectangle(box_coords, fill=(255, 255, 255, 200))

        # Add subtle border
        #draw.rectangle(box_coords, outline=(200, 200, 200, 255), width=2)

        # Draw text
        text_x = x + 20
        text_y = y + box_padding

        for line in wrapped_lines:
            draw.text((text_x, text_y), line, fill='black', font=font)
            text_y += line_spacing

        # Update column y position
        col_y_positions[col] = y + item_height + item_spacing

    img.save(output_name)

    return output_name


def wrap_text(text, font, max_width, draw):
    """Wrap text to fit within max_width."""
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        width = bbox[2] - bbox[0]

        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]

    if current_line:
        lines.append(' '.join(current_line))

    return lines if lines else [text]


def todo_fermeture_chalet():

    todos = get_todo_from_dropbox()
    return create_todo_display_image(todos)

    


# Example usage
if __name__ == "__main__":



    todo_fermeture_chalet()


    # Example todo list
    #todos = [
    #    "Buy groceries",
    #    "Call dentist",
    #    "Finish project report",
    #    "Exercise for 30 minutes",
    #    "Read chapter 5",
    #    "Pay electricity bill",
    #    "Pay electricity bill",
    #    "New",
    #    "another",
    #    "yet another",
    #    "Pay ptl"
    #]
    #todos = [
    #    "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
    #    "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
    #    "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.",
    #    "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.",
    #    "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.",
    #    "Fusce dapibus, tellus ac cursus commodo, tortor mauris condimentum nibh, ut fermentum massa justo sit amet risus.",
    #    "Aenean lacinia bibendum nulla sed consectetur. Cras mattis consectetur purus sit amet fermentum.",
    #    "Maecenas sed diam eget risus varius blandit sit amet non magna.",
    #    "Curabitur blandit tempus porttitor. Cum sociis natoque penatibus et magnis dis parturient montes, nascetur ridiculus mus.",
    #    "Donec id elit non mi porta gravida at eget metus.",
    #    "Etiam porta sem malesuada magna mollis euismod.",
    #    "Vivamus sagittis lacus vel augue laoreet rutrum faucibus dolor auctor.",
    #    "Nullam quis risus eget urna mollis ornare vel eu leo.",
    #    "Praesent commodo cursus magna, vel scelerisque nisl consectetur et.",
    #    "Vestibulum id ligula porta felis euismod semper.",
    #    "Aenean eu leo quam. Pellentesque ornare sem lacinia quam venenatis vestibulum.",
    #    "Sed posuere consectetur est at lobortis.",
    #    "Integer posuere erat a ante venenatis dapibus posuere velit aliquet.",
    #    "Duis mollis, est non commodo luctus, nisi erat porttitor ligula, eget lacinia odio sem nec elit.",
    #    "Blandit tempus porttitor. Integer posuere erat a ante venenatis dapibus posuere velit aliquet.",
    #    "Donec sed odio dui. Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
    #    "Nullam id dolor id nibh ultricies vehicula ut id elit.",
    #    "Morbi leo risus, porta ac consectetur ac, vestibulum at eros.",
    #    "Praesent commodo cursus magna, vel scelerisque nisl consectetur et.",
    #    "Sed posuere consectetur est at lobortis.",
    #    "Sum qui ratione voluptatem sequi nesciunt. Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet.",
    #    "Consectetur, adipisci velit, sed quia non numquam eius modi tempora incidunt ut labore et dolore magnam aliquam quaerat voluptatem.",
    #    "Ut enim ad minima veniam, quis nostrum exercitationem ullam corporis suscipit laboriosam, nisi ut aliquid ex ea commodi consequatur?",
    #    "Quis autem vel eum iure reprehenderit qui in ea voluptate velit esse quam nihil molestiae consequatur.",
    #    "Vel illum qui dolorem eum fugiat quo voluptas nulla pariatur?",
    #]
    
    # Create display without background
    #img = create_todo_display_image(todos)
    
    # Example with background image (uncomment if you have a background)
    # img_with_bg = create_todo_display_image(todos, bg_image="background.jpg")
    # img_with_bg.save("todo_display_with_bg.png")
