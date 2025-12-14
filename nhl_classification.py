from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO

def get_nhl_standings_image():
    """
    Generate a 1200x1600 PNG image displaying current NHL standings.
    Montreal Canadiens are highlighted with bold text and red background.

    Returns:
        PIL.Image: The generated standings image
    """
    # Fetch current NHL standings
    url = "https://api-web.nhle.com/v1/standings/now"
    response = requests.get(url)
    data = response.json()

    # Create image
    img = Image.new('RGB', (1200, 1600), 'white')
    draw = ImageDraw.Draw(img)

    # Add Canadiens logo as watermark
    try:
        logo_url = "https://assets.nhle.com/logos/nhl/svg/MTL_light.svg"
        # Try to get PNG version instead
        logo_url = "https://a.espncdn.com/combiner/i?img=/i/teamlogos/nhl/500/mtl.png"
        logo_response = requests.get(logo_url)
        logo = Image.open(BytesIO(logo_response.content))

        # Resize logo to fit nicely as watermark (full width)
        logo_width = 1200
        aspect_ratio = logo.size[1] / logo.size[0]
        logo_height = int(logo_width * aspect_ratio)
        logo = logo.resize((logo_width, logo_height), Image.LANCZOS)

        # Make it semi-transparent
        if logo.mode != 'RGBA':
            logo = logo.convert('RGBA')

        # Reduce opacity
        alpha = logo.split()[3]
        alpha = alpha.point(lambda p: int(p * 0.08))  # 8% opacity
        logo.putalpha(alpha)

        # Center the logo
        logo_x = (1200 - logo_width) // 2
        logo_y = (1600 - logo_height) // 2

        img.paste(logo, (logo_x, logo_y), logo)
    except Exception as e:
        print(f"Could not load Canadiens logo: {e}")

    draw = ImageDraw.Draw(img)

    # Try to load fonts, fall back to default if unavailable
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        team_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        team_font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    except:
        title_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        team_font = ImageFont.load_default()
        team_font_bold = ImageFont.load_default()

    # Draw title
    draw.text((600, 20), "NHL STANDINGS", fill='black', font=title_font, anchor='mt')

    y_offset = 80

    # Process standings by conference and division
    conferences = {}
    for team_data in data['standings']:
        conf_name = team_data['conferenceName']
        div_name = team_data['divisionName']

        if conf_name not in conferences:
            conferences[conf_name] = {}
        if div_name not in conferences[conf_name]:
            conferences[conf_name][div_name] = []

        conferences[conf_name][div_name].append({
            'name': team_data['teamName']['default'],
            'abbrev': team_data['teamAbbrev']['default'],
            'wins': team_data['wins'],
            'losses': team_data['losses'],
            'otLosses': team_data['otLosses'],
            'points': team_data['points'],
            'gamesPlayed': team_data['gamesPlayed']
        })

    # Sort teams by points (descending)
    for conf in conferences:
        for div in conferences[conf]:
            conferences[conf][div].sort(key=lambda x: x['points'], reverse=True)

    # Draw standings
    for conf_name in sorted(conferences.keys()):
        # Conference header
        draw.text((600, y_offset), conf_name.upper(), fill='black', font=header_font, anchor='mt')
        y_offset += 40

        for div_name in sorted(conferences[conf_name].keys()):
            # Division header
            draw.text((100, y_offset), div_name, fill='black', font=header_font, anchor='lt')
            y_offset += 38

            # Column headers
            draw.text((700, y_offset), "GP", fill='gray', font=team_font, anchor='lt')
            draw.text((780, y_offset), "W", fill='gray', font=team_font, anchor='lt')
            draw.text((860, y_offset), "L", fill='gray', font=team_font, anchor='lt')
            draw.text((940, y_offset), "OT", fill='gray', font=team_font, anchor='lt')
            draw.text((1030, y_offset), "PTS", fill='gray', font=team_font, anchor='lt')
            y_offset += 30

            # Draw teams
            for team in conferences[conf_name][div_name]:
                is_habs = team['abbrev'] == 'MTL'

                # Highlight Canadiens with red background
                if is_habs:
                    draw.rectangle([90, y_offset - 5, 1110, y_offset + 25], fill='#AF1E2D')

                font = team_font_bold if is_habs else team_font
                color = 'white' if is_habs else 'black'

                draw.text((120, y_offset), team['name'], fill=color, font=font, anchor='lt')
                draw.text((700, y_offset), str(team['gamesPlayed']), fill=color, font=font, anchor='lt')
                draw.text((780, y_offset), str(team['wins']), fill=color, font=font, anchor='lt')
                draw.text((860, y_offset), str(team['losses']), fill=color, font=font, anchor='lt')
                draw.text((940, y_offset), str(team['otLosses']), fill=color, font=font, anchor='lt')
                draw.text((1030, y_offset), str(team['points']), fill=color, font=font, anchor='lt')
                y_offset += 30

            y_offset += 15

        y_offset += 10

    return img


# Example usage
if __name__ == "__main__":
    standings_img = get_nhl_standings_image()
    standings_img.save("nhl_standings.png")
    print("NHL standings image saved as 'nhl_standings.png'")
