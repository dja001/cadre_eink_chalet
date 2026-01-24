import os
from datetime import datetime, timedelta
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont
import ephem
import numpy as np

def generate_moon_phase_image(
    output_dir="./figures",
    cache_dir="./__pycache__/moon_cache",
    latitude=45.5017,      # Montreal latitude
    longitude=-73.5673,    # Montreal longitude
    test_mode=False,
    test_date=None
):
    """
    Generate a 1200x1600 PNG image showing the moon phase with sunrise/sunset times.
    
    Args:
        output_dir: Directory where the generated image will be saved
        cache_dir: Directory for caching moon texture images
        latitude: Observer's latitude for sunrise/sunset calculation
        longitude: Observer's longitude for sunrise/sunset calculation
        test_mode: If True, includes date in filename
        test_date: Specific date to use (for testing), default is current date
    
    Returns:
        str: Full path to the generated image
    """
    
    # Create directories if they don't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    
    # Image dimensions
    WIDTH, HEIGHT = 1200, 1600
    
    # Get date to use
    target_date = test_date if test_date else datetime.now()
    date_str = target_date.strftime("%Y%m%d")
    
    # Create the main image (black background for e-ink)
    img = Image.new('RGB', (WIDTH, HEIGHT), 'black')
    draw = ImageDraw.Draw(img)
    
    # Set up observer
    observer = ephem.Observer()
    observer.lat = str(latitude)
    observer.lon = str(longitude)
    observer.date = target_date
    
    # Calculate moon and sun positions
    moon = ephem.Moon(observer)
    sun = ephem.Sun(observer)
    
    # Get equatorial coordinates (right ascension and declination)
    moon_ra = float(moon.ra)  # radians
    moon_dec = float(moon.dec)  # radians
    sun_ra = float(sun.ra)  # radians
    sun_dec = float(sun.dec)  # radians
    
    # Get altitude and azimuth for display orientation
    moon_alt = float(moon.alt)
    
    # Convert equatorial to Cartesian coordinates (unit vectors)
    # Moon position vector (as seen from Earth)
    moon_x = np.cos(moon_dec) * np.cos(moon_ra)
    moon_y = np.cos(moon_dec) * np.sin(moon_ra)
    moon_z = np.sin(moon_dec)
    moon_vec = np.array([moon_x, moon_y, moon_z])
    
    # Sun position vector (as seen from Earth)
    sun_x = np.cos(sun_dec) * np.cos(sun_ra)
    sun_y = np.cos(sun_dec) * np.sin(sun_ra)
    sun_z = np.sin(sun_dec)
    sun_vec = np.array([sun_x, sun_y, sun_z])
    
    # The sun illuminates the moon from the direction of sun_vec
    light_dir = sun_vec  # Direction from which light comes
    
    # Calculate parallactic angle
    lat_rad = np.radians(latitude)
    hour_angle = observer.sidereal_time() - moon_ra
    
    sin_q = np.sin(hour_angle) * np.cos(lat_rad) / np.cos(moon_alt)
    cos_q = (np.sin(lat_rad) - np.sin(moon_alt) * np.sin(moon_dec)) / (np.cos(moon_alt) * np.cos(moon_dec))
    parallactic_angle = np.arctan2(sin_q, cos_q)
    
    # Download/cache high-res moon texture
    moon_texture_path = os.path.join(cache_dir, "moon_texture.jpg")
    if not os.path.exists(moon_texture_path):
        moon_url = "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e001982/GSFC_20171208_Archive_e001982~orig.jpg"
        try:
            response = requests.get(moon_url, timeout=30)
            with open(moon_texture_path, 'wb') as f:
                f.write(response.content)
        except:
            # Create a simple moon texture if download fails
            moon_tex = Image.new('L', (1024, 1024), 180)
            draw_tex = ImageDraw.Draw(moon_tex)
            for _ in range(50):
                x, y = np.random.randint(0, 1024, 2)
                r = np.random.randint(10, 80)
                shade = np.random.randint(100, 150)
                draw_tex.ellipse([x-r, y-r, x+r, y+r], fill=shade)
            moon_tex.save(moon_texture_path)
    
    # Load and prepare moon texture
    moon_tex = Image.open(moon_texture_path).convert('L')
    
    # Find and crop the moon in the texture
    tex_array = np.array(moon_tex)
    threshold = 30
    moon_mask = tex_array > threshold
    
    rows = np.any(moon_mask, axis=1)
    cols = np.any(moon_mask, axis=0)
    
    if rows.any() and cols.any():
        rmin, rmax = np.where(rows)[0][[0, -1]]
        cmin, cmax = np.where(cols)[0][[0, -1]]
        
        moon_center_y = (rmin + rmax) // 2
        moon_center_x = (cmin + cmax) // 2
        moon_radius = max(rmax - rmin, cmax - cmin) // 2
        
        padding = int(moon_radius * 0.05)
        
        left = max(0, moon_center_x - moon_radius - padding)
        top = max(0, moon_center_y - moon_radius - padding)
        right = min(moon_tex.width, moon_center_x + moon_radius + padding)
        bottom = min(moon_tex.height, moon_center_y + moon_radius + padding)
        
        moon_tex = moon_tex.crop((left, top, right, bottom))
    
    # Resize moon texture
    moon_size = WIDTH
    moon_tex = moon_tex.resize((moon_size, moon_size), Image.Resampling.LANCZOS)
    texture_array = np.array(moon_tex, dtype=np.float32)
    
    # Create coordinate grids - VECTORIZED
    y_coords, x_coords = np.mgrid[0:moon_size, 0:moon_size]
    
    # Calculate distance from center - VECTORIZED
    center = moon_size / 2
    radius = moon_size / 2
    dx = x_coords - center
    dy = y_coords - center
    dist = np.sqrt(dx**2 + dy**2)
    
    # Create mask for pixels inside the moon
    moon_mask = dist <= radius
    
    # Normalize pixel coordinates to [-1, 1] - VECTORIZED
    px = dx / radius
    py = dy / radius
    
    # Apply parallactic angle rotation - VECTORIZED
    cos_p = np.cos(-parallactic_angle)
    sin_p = np.sin(-parallactic_angle)
    px_rot = px * cos_p - py * sin_p
    py_rot = px * sin_p + py * cos_p
    
    # Calculate 3D position on sphere - VECTORIZED
    r_squared = px_rot**2 + py_rot**2
    # Clamp to avoid sqrt of negative numbers at edges
    r_squared = np.minimum(r_squared, 1.0)
    pz = np.sqrt(1 - r_squared)
    
    # Create coordinate system for the moon - VECTORIZED
    if abs(moon_vec[2]) < 0.9:
        temp = np.array([0, 0, 1])
    else:
        temp = np.array([1, 0, 0])
    
    moon_right = np.cross(moon_vec, temp)
    moon_right = moon_right / np.linalg.norm(moon_right)
    
    moon_up = np.cross(moon_vec, moon_right)
    moon_up = moon_up / np.linalg.norm(moon_up)
    
    # Transform surface normal to celestial coordinates - VECTORIZED
    # Broadcasting: (H, W) arrays with (3,) vectors
    surface_normal_celestial_x = (px_rot * moon_right[0] + 
                                   py_rot * moon_up[0] + 
                                   pz * moon_vec[0])
    surface_normal_celestial_y = (px_rot * moon_right[1] + 
                                   py_rot * moon_up[1] + 
                                   pz * moon_vec[1])
    surface_normal_celestial_z = (px_rot * moon_right[2] + 
                                   py_rot * moon_up[2] + 
                                   pz * moon_vec[2])
    
    # Calculate illumination - VECTORIZED dot product
    illumination = (surface_normal_celestial_x * light_dir[0] +
                    surface_normal_celestial_y * light_dir[1] +
                    surface_normal_celestial_z * light_dir[2])
    
    # Calculate brightness based on illumination - VECTORIZED
    terminator_width = 0.05
    
    # Create brightness array
    brightness = np.zeros((moon_size, moon_size), dtype=np.uint8)
    
    # Fully illuminated regions
    bright_mask = illumination > terminator_width
    brightness[bright_mask] = texture_array[bright_mask]
    
    # Fully dark regions
    dark_mask = illumination < -terminator_width
    brightness[dark_mask] = (texture_array[dark_mask] * 0.05).astype(np.uint8)
    
    # Terminator gradient regions
    gradient_mask = ~bright_mask & ~dark_mask
    blend = (illumination[gradient_mask] + terminator_width) / (2 * terminator_width)
    dark_val = (texture_array[gradient_mask] * 0.05).astype(np.float32)
    bright_val = texture_array[gradient_mask]
    brightness[gradient_mask] = (dark_val + (bright_val - dark_val) * blend).astype(np.uint8)
    
    # Apply limb darkening - VECTORIZED
    limb_factor = 1.0 - (dist / radius) ** 2
    limb_factor = 0.7 + 0.3 * limb_factor
    brightness = (brightness * limb_factor).astype(np.uint8)
    
    # Apply moon mask (pixels outside moon are black)
    brightness[~moon_mask] = 0
    
    # Create RGBA image from brightness array
    moon_img_array = np.zeros((moon_size, moon_size, 4), dtype=np.uint8)
    moon_img_array[:, :, 0] = brightness  # R
    moon_img_array[:, :, 1] = brightness  # G
    moon_img_array[:, :, 2] = brightness  # B
    moon_img_array[:, :, 3] = (moon_mask * 255).astype(np.uint8)  # Alpha
    
    moon_img = Image.fromarray(moon_img_array, 'RGBA')
    
    # Paste moon at top of image
    moon_y = 50
    moon_x = 0
    img.paste(moon_img, (moon_x, moon_y), moon_img)
    
    # Calculate sunrise and sunset
    observer.date = target_date
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
    
    # Draw sunrise/sunset pictogram at bottom
    picto_y = HEIGHT - 200
    
    # Sunrise icon
    sun_x = WIDTH // 6
    sun_radius = 35
    draw.ellipse([sun_x - sun_radius, picto_y - sun_radius, 
                  sun_x + sun_radius, picto_y + sun_radius], 
                 fill='orange', outline='darkorange', width=3)
    
    arrow_size = 20
    arrow_points = [(sun_x, picto_y - sun_radius - 25), 
                    (sun_x - arrow_size, picto_y - sun_radius - 5), 
                    (sun_x + arrow_size, picto_y - sun_radius - 5)]
    draw.polygon(arrow_points, fill='orange')
    
    # Sunset icon
    sun_x2 = 5 * WIDTH // 6
    draw.ellipse([sun_x2 - sun_radius, picto_y - sun_radius, 
                  sun_x2 + sun_radius, picto_y + sun_radius], 
                 fill='orange', outline='darkorange', width=3)
    
    arrow_points2 = [(sun_x2, picto_y + sun_radius + 25), 
                     (sun_x2 - arrow_size, picto_y + sun_radius + 5), 
                     (sun_x2 + arrow_size, picto_y + sun_radius + 5)]
    draw.polygon(arrow_points2, fill='orange')
    
    # Add time text
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
    except:
        try:
            font = ImageFont.truetype("arial.ttf", 40)
        except:
            font = ImageFont.load_default()
    
    draw.text((sun_x, picto_y + 130), sunrise_str, fill='white', 
              font=font, anchor='mm')
    draw.text((sun_x2, picto_y + 130), sunset_str, fill='white', 
              font=font, anchor='mm')
    
    # Add date in test mode
    if test_mode:
        date_text = target_date.strftime("%B %d, %Y")
        try:
            date_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        except:
            try:
                date_font = ImageFont.truetype("arial.ttf", 40)
            except:
                date_font = font
        
        draw.text((WIDTH // 2, HEIGHT - 50), date_text, fill='white', 
                  font=date_font, anchor='mm')
    
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
    
    print("Generating moon phase images for every day of January 2024...\n")
    
    # Configure for Montreal, Quebec
    base_config = {
        "output_dir": "./figures/moon_images",
        "cache_dir": "./__pycache__/moon_cache",
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
        
        # Determine phase name
        if phase_pct < 5:
            phase_name = "New Moon"
        elif phase_pct < 45:
            phase_name = "Waxing Crescent"
        elif 45 <= phase_pct < 55:
            phase_name = "First Quarter"
        elif 55 <= phase_pct < 95:
            phase_name = "Waxing Gibbous"
        elif 95 <= phase_pct:
            phase_name = "Full Moon"
        
        # Check if waning
        obs2 = ephem.Observer()
        obs2.date = test_date + timedelta(days=1)
        moon_obj2 = ephem.Moon(obs2)
        if moon_obj2.phase < phase_pct:
            if phase_pct >= 95:
                phase_name = "Full Moon"
            elif phase_pct >= 55:
                phase_name = "Waning Gibbous"
            elif phase_pct >= 45:
                phase_name = "Last Quarter"
            else:
                phase_name = "Waning Crescent"
        
        print(f"Day {day+1:2d} - {test_date.strftime('%Y-%m-%d')} - {phase_name:16} - Phase: {phase_pct:5.1f}% - Time: {day_time:.2f}s")
    
    total_time = time.time() - total_start
    avg_time = total_time / 31
    
    print(f"\n✓ All test images generated successfully!")
    print(f"Total time: {total_time:.2f}s")
    print(f"Average time per image: {avg_time:.2f}s")
    print(f"\nImages saved to: {base_config['output_dir']}")
    print("\nFor regular use in Montreal, call the function:")
    print("  generate_moon_phase_image(output_dir='./output', latitude=45.5017, longitude=-73.5673)")
