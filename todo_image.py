import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import re


def parse_markdown_todo(todo_list):
    """
    Parse markdown-formatted todo list into structured items.

    Returns list of dicts with:
    - 'type': 'header', 'item', or 'subitem'
    - 'text': the text content
    - 'level': header level (1, 2, etc.) for headers
    """
    parsed_items = []

    for line in todo_list:
        line = line.strip()
        if not line:
            continue

        # Check for headers (# or ##)
        header_match = re.match(r'^(#{1,2})\s+(.+)$', line)
        if header_match:
            level = len(header_match.group(1))
            text = header_match.group(2)
            parsed_items.append({
                'type': 'header',
                'text': text,
                'level': level
            })
            continue

        # Check for sub-items (indented * or starting with spaces/tabs)
        subitem_match = re.match(r'^\s+[\*\-]\s+(.+)$', line)
        if subitem_match:
            text = subitem_match.group(1)
            parsed_items.append({
                'type': 'subitem',
                'text': text
            })
            continue

        # Check for regular items (* or -)
        item_match = re.match(r'^[\*\-]\s+(.+)$', line)
        if item_match:
            text = item_match.group(1)
            parsed_items.append({
                'type': 'item',
                'text': text
            })
            continue

        # If no markdown, treat as regular item
        if line:
            parsed_items.append({
                'type': 'item',
                'text': line
            })

    return parsed_items


def create_todo_display_image(todo_list, npix_h=1200, npix_v=1600, bg_image=None,
                              font_path=None, padding=40, output_name='figures/todo.png'):
    """
    Create an e-ink display image with a markdown-formatted todo list.

    Parameters:
    -----------
    todo_list : list of str
        List of todo items with markdown formatting (# for headers, * for items, indented * for subitems)
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

    # Parse markdown
    parsed_items = parse_markdown_todo(todo_list)
    n_items = len(parsed_items)

    if n_items == 0:
        return img

    # Determine number of columns and base font sizes
    if n_items <= 15:
        n_cols = 1
        base_font_size = 60
    elif n_items <= 30:
        n_cols = 2
        base_font_size = 50
    else:
        n_cols = 2
        base_font_size = max(40, 55 - (n_items - 30) * 1)

    # Font paths
    lm_paths = [
        '/usr/share/fonts/opentype/lmodern/lmroman10-regular.otf',
        '/usr/share/fonts/truetype/lmodern/lmroman10-regular.ttf',
        'C:\\Windows\\Fonts\\lmroman10-regular.otf',
    ]
    lm_bold_paths = [
        '/usr/share/fonts/opentype/lmodern/lmroman10-bold.otf',
        '/usr/share/fonts/truetype/lmodern/lmroman10-bold.ttf',
        'C:\\Windows\\Fonts\\lmroman10-bold.otf',
    ]

    # Load fonts
    def load_font(size, bold=False):
        try:
            if font_path:
                return ImageFont.truetype(font_path, size)
            else:
                paths = lm_bold_paths if bold else lm_paths
                for path in paths:
                    try:
                        return ImageFont.truetype(path, size)
                    except:
                        continue
                return ImageFont.load_default()
        except:
            return ImageFont.load_default()

    # Create fonts for different elements
    header_font = load_font(int(base_font_size * 1.3), bold=True)
    item_font = load_font(base_font_size)
    subitem_font = load_font(int(base_font_size * 0.85))

    # Calculate layout
    col_width = (npix_h - padding * 2) // n_cols
    col_gap = 20
    available_height = npix_v - 2 * padding

    # Calculate spacing (reduced from previous version)
    header_spacing = int(base_font_size * 1.3) + 8
    item_spacing = base_font_size + 4
    subitem_spacing = int(base_font_size * 0.85) + 3

    section_gap = 15  # Extra space after sections (reduced from 25)
    item_gap = 4      # Gap between items (reduced from 8)

    # Auto-scale if content doesn't fit
    max_iterations = 10
    iteration = 0

    while iteration < max_iterations:
        # Prepare wrapped text for all items
        items_data = []
        for item in parsed_items:
            if item['type'] == 'header':
                wrapped_lines = wrap_text(item['text'], header_font, col_width - 60, draw)
                items_data.append({
                    'type': 'header',
                    'lines': wrapped_lines,
                    'level': item.get('level', 1)
                })
            elif item['type'] == 'item':
                text = f"• {item['text']}"
                wrapped_lines = wrap_text(text, item_font, col_width - 80, draw)
                items_data.append({
                    'type': 'item',
                    'lines': wrapped_lines
                })
            elif item['type'] == 'subitem':
                text = f"◦ {item['text']}"
                wrapped_lines = wrap_text(text, subitem_font, col_width - 120, draw)
                items_data.append({
                    'type': 'subitem',
                    'lines': wrapped_lines
                })

        # Calculate height for each column to find optimal distribution
        # Group items into sections (header + following items)
        sections = []
        current_section = []

        for item_data in items_data:
            if item_data['type'] == 'header' and current_section:
                sections.append(current_section)
                current_section = [item_data]
            else:
                current_section.append(item_data)

        if current_section:
            sections.append(current_section)

        # Calculate height of each section
        section_heights = []
        for section in sections:
            section_height = 0
            for item_data in section:
                if item_data['type'] == 'header':
                    section_height += len(item_data['lines']) * header_spacing + section_gap
                elif item_data['type'] == 'item':
                    section_height += len(item_data['lines']) * item_spacing + 20 + item_gap
                elif item_data['type'] == 'subitem':
                    section_height += len(item_data['lines']) * subitem_spacing + item_gap
            section_heights.append(section_height)

        # Distribute sections across columns to balance height
        col_heights = [0] * n_cols
        col_sections = [[] for _ in range(n_cols)]

        for idx, (section, height) in enumerate(zip(sections, section_heights)):
            # Find column with least height
            min_col = col_heights.index(min(col_heights))
            col_sections[min_col].append(section)
            col_heights[min_col] += height

        # Check if tallest column fits
        max_col_height = max(col_heights)
        if max_col_height <= available_height:
            break

        # Reduce font sizes
        base_font_size = int(base_font_size * 0.92)
        header_spacing = int(base_font_size * 1.3) + 8
        item_spacing = base_font_size + 4
        subitem_spacing = int(base_font_size * 0.85) + 3

        # Reload fonts
        header_font = load_font(int(base_font_size * 1.3), bold=True)
        item_font = load_font(base_font_size)
        subitem_font = load_font(int(base_font_size * 0.85))

        iteration += 1

    # Draw items column by column
    for col_idx in range(n_cols):
        x_base = padding + col_idx * (col_width + col_gap)
        y = padding

        for section in col_sections[col_idx]:
            for item_data in section:
                if item_data['type'] == 'header':
                    # Draw header (no background box)
                    x = x_base + 20
                    for line in item_data['lines']:
                        draw.text((x, y), line, fill='black', font=header_font)
                        y += header_spacing
                    y += section_gap

                elif item_data['type'] == 'item':
                    # Draw item with background box
                    x = x_base + 30
                    num_lines = len(item_data['lines'])
                    text_height = num_lines * item_spacing
                    box_height = text_height + 20

                    # Semi-transparent background box
                    box_coords = [x_base + 10, y, x_base + col_width - 10, y + box_height]
                    draw.rectangle(box_coords, fill=(255, 255, 255, 200))

                    # Draw text
                    text_y = y + 10
                    for line in item_data['lines']:
                        draw.text((x, text_y), line, fill='black', font=item_font)
                        text_y += item_spacing

                    y += box_height + item_gap

                elif item_data['type'] == 'subitem':
                    # Draw subitem (indented, smaller)
                    x = x_base + 60
                    for line in item_data['lines']:
                        draw.text((x, y), line, fill='black', font=subitem_font)
                        y += subitem_spacing
                    y += item_gap

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
    from dropbox_access import get_todo_list

    todos = get_todo_list()
    return create_todo_display_image(todos)


# Example usage
if __name__ == "__main__":
    res = todo_fermeture_chalet()
    print(res)
