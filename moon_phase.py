import os
from datetime import datetime, timedelta
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont
import ephem

def generate_moon_phase_image(
    output_dir="./figures",
    latitude=45.5017,      # Montreal latitude
    longitude=-73.5673,    # Montreal longitude
    test_mode=False,
    test_date=None
):
    """
    Generate a 1200x1600 PNG image showing the moon phase with sunrise/sunset times.
    Uses NASA's Dial-A-Moon API to get accurate moon imagery at 9 PM EST.

    Args:
        output_dir: Directory where the generated image will be saved
        latitude: Observer's latitude for sunrise/sunset calculation
        longitude: Observer's longitude for sunrise/sunset calculation
        test_mode: If True, includes date in filename
        test_date: Specific date to use (for testing), default is current date

    Returns:
        str: Full path to the generated image
    """

    # Create directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Image dimensions
    WIDTH, HEIGHT = 1200, 1600

    # Get date to use
    target_date = test_date if test_date else datetime.now()
    date_str = target_date.strftime("%Y%m%d")

    # Convert to 9 PM EST (which is 2 AM UTC the next day during standard time)
    # EST is UTC-5, EDT is UTC-4
    # Using EST (UTC-5) for consistency
    target_datetime_est = target_date.replace(hour=21, minute=0, second=0, microsecond=0)
    target_datetime_utc = target_datetime_est + timedelta(hours=5)  # EST to UTC

    # Format for NASA API (YYYY-MM-DDTHH:MM)
    api_time_str = target_datetime_utc.strftime("%Y-%m-%dT%H:%M")

    # Call NASA Dial-A-Moon API
    api_url = f"https://svs.gsfc.nasa.gov/api/dialamoon/{api_time_str}"

    try:
        print(f"Fetching moon data from NASA for {api_time_str}...")
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Get the image URL from the API response
        if 'image' in data and 'url' in data['image']:
            image_url = data['image']['url']
            print(f"Downloading NASA moon image...")

            # Download the moon image
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()

            # Load the image
            from io import BytesIO
            moon_img = Image.open(BytesIO(img_response.content))
            print(f"Moon image downloaded successfully")
        else:
            raise Exception("No image URL in API response")

    except Exception as e:
        print(f"Error fetching NASA moon image: {e}")
        print("Creating placeholder moon image...")
        # Create a simple placeholder if API fails
        moon_img = Image.new('RGB', (1200, 1200), 'gray')
        draw_temp = ImageDraw.Draw(moon_img)
        draw_temp.ellipse([100, 100, 1100, 1100], fill='lightgray', outline='white', width=5)

    # Resize moon image to fit our canvas width
    moon_size = WIDTH
    if moon_img.size != (moon_size, moon_size):
        moon_img = moon_img.resize((moon_size, moon_size), Image.Resampling.LANCZOS)

    # Create the main image (black background for e-ink)
    img = Image.new('RGB', (WIDTH, HEIGHT), 'black')

    # Paste moon at top of image
    moon_y = 50
    moon_x = 0
    img.paste(moon_img, (moon_x, moon_y))

    # Set up observer for sunrise/sunset calculation
    observer = ephem.Observer()
    observer.lat = str(latitude)
    observer.lon = str(longitude)
    observer.date = target_date

    # Calculate sunrise and sunset
    try:
        sunrise = observer.next_rising(ephem.Sun())
        sunset = observer.next_setting(ephem.Sun())

        sunrise_local = ephem.localtime(sunrise)
        sunset_local = ephem.localtime(sunset)

        sunrise_str = sunrise_local.strftime("%H:%M")
        sunset_str = sunset_local.strftime("%H:%M")
    except:
        sunrise_str = "06:30"
        sunset_str = "18:30"

    # Calculate moonrise and moonset
    try:
        moonrise = observer.next_rising(ephem.Moon())
        moonset = observer.next_setting(ephem.Moon())

        moonrise_local = ephem.localtime(moonrise)
        moonset_local = ephem.localtime(moonset)

        moonrise_str = moonrise_local.strftime("%H:%M")
        moonset_str = moonset_local.strftime("%H:%M")
    except:
        moonrise_str = "18:00"
        moonset_str = "06:00"

    # Load font
    try:
        font = ImageFont.truetype("fonts/lmroman10-regular.otf", 40)
    except:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        except:
            font = ImageFont.load_default()

    # Draw pictograms at bottom
    draw = ImageDraw.Draw(img)

    # Moon rise/set section (top)
    moon_section_y = HEIGHT - 350

    # Moonrise icon (left side)
    moon_x = WIDTH // 6
    moon_radius = 30

    # Draw simple crescent moon (tilted by drawing offset circles)
    import math
    tilt_angle = -20  # degrees
    tilt_rad = math.radians(tilt_angle)

    # Draw main moon circle
    draw.ellipse([moon_x - moon_radius, moon_section_y - moon_radius,
                  moon_x + moon_radius, moon_section_y + moon_radius],
                 fill='white', outline='white')

    # Draw overlapping circle to create crescent, offset and tilted
    offset_x = 10 * math.cos(tilt_rad)
    offset_y = 10 * math.sin(tilt_rad)
    draw.ellipse([moon_x - moon_radius + offset_x, moon_section_y - moon_radius + offset_y,
                  moon_x + moon_radius + offset_x, moon_section_y + moon_radius + offset_y],
                 fill='black', outline='black')

    # Moonrise arrow (up, on left side)
    arrow_size = 20
    arrow_x = moon_x - moon_radius - 35
    arrow_y = moon_section_y  # Center of arrow at moon center
    # Arrow pointing up - tip at top
    arrow_points = [(arrow_x, arrow_y - arrow_size),  # top tip
                    (arrow_x - arrow_size//2, arrow_y),  # bottom left
                    (arrow_x + arrow_size//2, arrow_y)]  # bottom right
    draw.polygon(arrow_points, fill='white')

    # Moonrise time (on the right side of moon)
    draw.text((moon_x + moon_radius + 50, moon_section_y), moonrise_str,
              fill='white', font=font, anchor='lm')

    # Moonset icon (right side)
    moon_x2 = 5 * WIDTH // 6

    # Draw simple crescent moon
    draw.ellipse([moon_x2 - moon_radius, moon_section_y - moon_radius,
                  moon_x2 + moon_radius, moon_section_y + moon_radius],
                 fill='white', outline='white')

    draw.ellipse([moon_x2 - moon_radius + offset_x, moon_section_y - moon_radius + offset_y,
                  moon_x2 + moon_radius + offset_x, moon_section_y + moon_radius + offset_y],
                 fill='black', outline='black')

    # Moonset arrow (down, on left side)
    arrow_x2 = moon_x2 - moon_radius - 35
    # Arrow pointing down - tip at bottom
    arrow_points2 = [(arrow_x2, arrow_y + arrow_size),  # bottom tip
                     (arrow_x2 - arrow_size//2, arrow_y),  # top left
                     (arrow_x2 + arrow_size//2, arrow_y)]  # top right
    draw.polygon(arrow_points2, fill='white')

    # Moonset time (on the right side of moon)
    draw.text((moon_x2 + moon_radius + 50, moon_section_y), moonset_str,
              fill='white', font=font, anchor='lm')

    # Sun rise/set section (bottom)
    sun_section_y = HEIGHT - 180

    # Sunrise icon (left side)
    sun_x = WIDTH // 6
    sun_radius = 35

    # Draw horizon line
    horizon_y = sun_section_y
    draw.line([sun_x - sun_radius - 10, horizon_y,
               sun_x + sun_radius + 10, horizon_y], fill='orange', width=3)

    # Draw half circle sun (top half only, sitting on horizon)
    draw.pieslice([sun_x - sun_radius, horizon_y - sun_radius,
                   sun_x + sun_radius, horizon_y + sun_radius],
                  start=180, end=0, fill='orange', outline='darkorange', width=3)

    # Draw sun rays - all same length (12 pixels), starting from edge of sun
    ray_length = 12
    ray_angles = [-60, -30, 0, 30, 60]  # Five rays
    for angle in ray_angles:
        angle_rad = math.radians(angle)
        # Start from edge of sun (on the semicircle)
        start_angle = 90 + angle  # Angle from horizontal, going around the semicircle
        start_angle_rad = math.radians(start_angle)
        start_x = sun_x + sun_radius * math.cos(start_angle_rad)
        start_y = horizon_y - sun_radius * math.sin(start_angle_rad)

        # End point - extend in the same radial direction
        end_x = sun_x + (sun_radius + ray_length) * math.cos(start_angle_rad)
        end_y = horizon_y - (sun_radius + ray_length) * math.sin(start_angle_rad)

        draw.line([start_x, start_y, end_x, end_y], fill='orange', width=3)

    # Sunrise arrow (up, on left side)
    # Arrow tip should align with top of sunset arrow (which has flat top)
    arrow_x = sun_x - sun_radius - 35
    arrow_y_sun = horizon_y - sun_radius // 2  # Center at middle of half-sun
    # Arrow pointing up - tip at top
    arrow_points = [(arrow_x, arrow_y_sun - arrow_size),  # top tip (aligns with other arrow's flat top)
                    (arrow_x - arrow_size//2, arrow_y_sun),  # bottom left
                    (arrow_x + arrow_size//2, arrow_y_sun)]  # bottom right
    draw.polygon(arrow_points, fill='orange')

    # Sunrise time (on the right side of sun)
    draw.text((sun_x + sun_radius + 50, arrow_y_sun), sunrise_str,
              fill='white', font=font, anchor='lm')

    # Sunset icon (right side)
    sun_x2 = 5 * WIDTH // 6

    # Draw horizon line
    draw.line([sun_x2 - sun_radius - 10, horizon_y,
               sun_x2 + sun_radius + 10, horizon_y], fill='orange', width=3)

    # Draw half circle sun
    draw.pieslice([sun_x2 - sun_radius, horizon_y - sun_radius,
                   sun_x2 + sun_radius, horizon_y + sun_radius],
                  start=180, end=0, fill='orange', outline='darkorange', width=3)

    # Draw sun rays
    for angle in ray_angles:
        angle_rad = math.radians(angle)
        start_angle = 90 + angle
        start_angle_rad = math.radians(start_angle)
        start_x = sun_x2 + sun_radius * math.cos(start_angle_rad)
        start_y = horizon_y - sun_radius * math.sin(start_angle_rad)
        end_x = sun_x2 + (sun_radius + ray_length) * math.cos(start_angle_rad)
        end_y = horizon_y - (sun_radius + ray_length) * math.sin(start_angle_rad)
        draw.line([start_x, start_y, end_x, end_y], fill='orange', width=3)

    # Sunset arrow (down, on left side)
    # Arrow flat top should align with sunrise arrow's pointy tip
    arrow_x2 = sun_x2 - sun_radius - 35
    # Arrow pointing down - flat top at the alignment point
    arrow_points2 = [(arrow_x2, arrow_y_sun - arrow_size + arrow_size),  # bottom tip
                     (arrow_x2 - arrow_size//2, arrow_y_sun - arrow_size),  # top left (flat top aligns with other arrow's tip)
                     (arrow_x2 + arrow_size//2, arrow_y_sun - arrow_size)]  # top right
    draw.polygon(arrow_points2, fill='orange')

    # Sunset time (on the right side of sun)
    draw.text((sun_x2 + sun_radius + 50, arrow_y_sun), sunset_str,
              fill='white', font=font, anchor='lm')

    # Add date in test mode
    if test_mode:
        date_text = target_date.strftime("%B %d, %Y")
        draw.text((WIDTH // 2, HEIGHT - 50), date_text, fill='white',
                  font=font, anchor='mm')

    # Save the image
    if test_mode:
        output_path = os.path.join(output_dir, f"moon_phase_{date_str}.png")
    else:
        output_path = os.path.join(output_dir, "moon_phase.png")

    img.save(output_path, 'PNG')

    return os.path.abspath(output_path)


# Test mode: Generate images for every day of January 2024
if __name__ == "__main__":
    import time

    print("Generating moon phase images for every day of January 2024 at 9 PM EST...\n")

    # Configure for Montreal, Quebec
    base_config = {
        "output_dir": "./figures/moon_images",
        "latitude": 45.5017,      # Montreal latitude
        "longitude": -73.5673,    # Montreal longitude
        "test_mode": True
    }

    # Generate for every day in January 2024
    start_date = datetime(2024, 1, 1)

    total_start = time.time()

    for day in range(31):
        test_date = start_date + timedelta(days=day)

        day_start = time.time()
        image_path = generate_moon_phase_image(
            **base_config,
            test_date=test_date
        )
        day_time = time.time() - day_start

        # Calculate moon phase percentage for display
        obs = ephem.Observer()
        obs.date = test_date
        moon_obj = ephem.Moon(obs)
        phase_pct = moon_obj.phase

        print(f"Day {day+1:2d} - {test_date.strftime('%Y-%m-%d')} - Phase: {phase_pct:5.1f}% - Time: {day_time:.2f}s\n")

    total_time = time.time() - total_start
    avg_time = total_time / 31

    print(f"✓ All test images generated successfully!")
    print(f"Total time: {total_time:.2f}s")
    print(f"Average time per image: {avg_time:.2f}s")
    print(f"\nImages saved to: {base_config['output_dir']}")
    print("\nFor regular use in Montreal, call the function:")
    print("  generate_moon_phase_image(output_dir='./output', latitude=45.5017, longitude=-73.5673)")
