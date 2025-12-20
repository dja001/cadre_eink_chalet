import os
from datetime import datetime, timedelta
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont
import ephem
import numpy as np

def generate_moon_phase_image(
    output_dir="./figures",
    cache_dir="./figures/moon_cache",
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
    
    # Calculate moon phase
    observer = ephem.Observer()
    observer.lat = str(latitude)
    observer.lon = str(longitude)
    observer.date = target_date
    
    moon = ephem.Moon(observer)
    moon_phase = moon.phase / 100.0  # Convert to 0-1 range
    
    # Get moon's elongation (angle from sun) to determine actual phase
    sun = ephem.Sun(observer)
    elongation = float(ephem.separation(sun, moon))  # Angle in radians
    
    # Determine if waxing or waning more reliably
    # Check the rate of change of elongation
    next_observer = ephem.Observer()
    next_observer.lat = str(latitude)
    next_observer.lon = str(longitude)
    next_observer.date = target_date + timedelta(hours=1)
    next_moon = ephem.Moon(next_observer)
    next_sun = ephem.Sun(next_observer)
    next_elongation = float(ephem.separation(next_sun, next_moon))
    
    waxing = next_elongation > elongation
    
    # Download/cache high-res moon texture (Northern hemisphere view)
    moon_texture_path = os.path.join(cache_dir, "moon_texture.jpg")
    if not os.path.exists(moon_texture_path):
        # Using NASA's familiar northern hemisphere moon view
        moon_url = "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e001982/GSFC_20171208_Archive_e001982~orig.jpg"
        try:
            response = requests.get(moon_url, timeout=30)
            with open(moon_texture_path, 'wb') as f:
                f.write(response.content)
        except:
            # Create a simple moon texture if download fails
            moon_tex = Image.new('L', (1024, 1024), 180)
            draw_tex = ImageDraw.Draw(moon_tex)
            # Add some crater-like circles
            for _ in range(50):
                x, y = np.random.randint(0, 1024, 2)
                r = np.random.randint(10, 80)
                shade = np.random.randint(100, 150)
                draw_tex.ellipse([x-r, y-r, x+r, y+r], fill=shade)
            moon_tex.save(moon_texture_path)
    
    # Load and prepare moon texture
    moon_tex = Image.open(moon_texture_path).convert('L')
    
    # The NASA image has the moon centered but not filling the frame
    # We need to find the moon's actual circle and crop/scale appropriately
    
    # Convert to numpy for analysis
    tex_array = np.array(moon_tex)
    
    # Find the bounds of the moon (non-black pixels)
    # Threshold to find moon pixels (assuming moon is brighter than background)
    threshold = 30
    moon_mask = tex_array > threshold
    
    # Find bounding box of moon
    rows = np.any(moon_mask, axis=1)
    cols = np.any(moon_mask, axis=0)
    
    if rows.any() and cols.any():
        rmin, rmax = np.where(rows)[0][[0, -1]]
        cmin, cmax = np.where(cols)[0][[0, -1]]
        
        # Calculate center and radius
        moon_center_y = (rmin + rmax) // 2
        moon_center_x = (cmin + cmax) // 2
        moon_radius = max(rmax - rmin, cmax - cmin) // 2
        
        # Crop to moon with some padding
        padding = int(moon_radius * 0.05)  # 5% padding
        crop_size = (moon_radius + padding) * 2
        
        left = max(0, moon_center_x - moon_radius - padding)
        top = max(0, moon_center_y - moon_radius - padding)
        right = min(moon_tex.width, moon_center_x + moon_radius + padding)
        bottom = min(moon_tex.height, moon_center_y + moon_radius + padding)
        
        moon_tex = moon_tex.crop((left, top, right, bottom))
    
    # Moon occupies full width
    moon_size = WIDTH
    moon_tex = moon_tex.resize((moon_size, moon_size), Image.Resampling.LANCZOS)
    
    # Create moon with crescent-like phase shading
    moon_img = Image.new('RGBA', (moon_size, moon_size), (0, 0, 0, 0))
    
    # Calculate phase angle for terminator position
    # moon_phase ranges from 0 (new) to 1 (new again), with 0.5 being full
    # ephem gives us phase as percentage illuminated (0-100)
    
    for y in range(moon_size):
        for x in range(moon_size):
            # Calculate distance from center
            dx = x - moon_size / 2
            dy = y - moon_size / 2
            dist = np.sqrt(dx**2 + dy**2)
            radius = moon_size / 2
            
            if dist <= radius:
                # Get base texture value
                texture_val = moon_tex.getpixel((x, y))
                
                # Normalize coordinates to -1 to 1
                x_norm = dx / radius
                y_norm = dy / radius
                
                # Calculate the z-coordinate on the sphere (depth)
                # For a point on a sphere: x² + y² + z² = 1
                z_norm = np.sqrt(max(0, 1 - x_norm**2 - y_norm**2))
                
                # Calculate illumination angle based on moon phase
                # moon_phase from ephem is percentage illuminated (0.0 to 1.0 where):
                # 0.0 = new moon (completely dark, sun behind moon)
                # 0.5 = half illuminated (first or last quarter)
                # 1.0 = full moon (completely lit, sun opposite Earth)
                
                # The sun angle should be:
                # New moon (phase=0): sun from behind (-180° or +180°), moon is dark
                # First quarter (phase=0.5, waxing): sun from right (+90°), right half lit
                # Full moon (phase=1.0): sun from front (0°), fully lit
                # Last quarter (phase=0.5, waning): sun from left (-90°), left half lit
                
                # Convert phase to sun angle
                if waxing:
                    # Waxing: phase 0 to 1.0 (new to full)
                    # Sun angle from +180° (behind) to 0° (front)
                    sun_angle = np.pi * (1.0 - moon_phase)
                else:
                    # Waning: phase 1.0 to 0 (full to new)
                    # Sun angle from 0° (front) to -180° (behind)
                    sun_angle = -np.pi * (1.0 - moon_phase)
                
                # Sun direction vector (sun shines from this direction)
                sun_x = np.sin(sun_angle)
                sun_z = np.cos(sun_angle)
                
                # Calculate dot product of surface normal with sun direction
                # Surface normal at this point is (x_norm, y_norm, z_norm)
                # Sun direction is (sun_x, 0, sun_z)
                illumination = x_norm * sun_x + z_norm * sun_z
                
                # Determine if this point is illuminated
                # The terminator is where illumination = 0
                # Positive values are lit, negative are dark
                
                terminator_width = 0.04  # Width of the gradient at the terminator
                
                if illumination > terminator_width:
                    # Fully illuminated
                    brightness = texture_val
                elif illumination < -terminator_width:
                    # Fully in shadow - very dark but visible
                    brightness = int(texture_val * 0.08)
                else:
                    # In the terminator gradient zone
                    blend = (illumination + terminator_width) / (2 * terminator_width)
                    dark_val = int(texture_val * 0.08)
                    brightness = int(dark_val + (texture_val - dark_val) * blend)
                
                # Apply subtle limb darkening for realism
                limb_factor = 1.0 - (dist / radius) ** 2
                limb_factor = 0.7 + 0.3 * limb_factor
                brightness = int(brightness * limb_factor)
                
                moon_img.putpixel((x, y), (brightness, brightness, brightness, 255))
    
    # Paste moon at top of image
    moon_y = 50
    moon_x = 0
    img.paste(moon_img, (moon_x, moon_y), moon_img)
    
    # Calculate sunrise and sunset
    observer.date = target_date
    try:
        sunrise = observer.next_rising(ephem.Sun())
        sunset = observer.next_setting(ephem.Sun())
        
        # Convert to local time (automatically handles DST)
        sunrise_local = ephem.localtime(sunrise)
        sunset_local = ephem.localtime(sunset)
        
        sunrise_str = sunrise_local.strftime("%H:%M")
        sunset_str = sunset_local.strftime("%H:%M")
    except:
        sunrise_str = "06:30"
        sunset_str = "18:30"
    
    # Draw sunrise/sunset pictogram at bottom - more spread out
    picto_y = HEIGHT - 200
    
    # Draw sunrise icon (sun with up arrow) - positioned at 1/6 width
    sun_x = WIDTH // 6
    sun_radius = 35
    draw.ellipse([sun_x - sun_radius, picto_y - sun_radius, 
                  sun_x + sun_radius, picto_y + sun_radius], 
                 fill='orange', outline='darkorange', width=3)
    
    # Sunrise arrow (up) - smaller
    arrow_size = 20
    arrow_points = [(sun_x, picto_y - sun_radius - 25), 
                    (sun_x - arrow_size, picto_y - sun_radius - 5), 
                    (sun_x + arrow_size, picto_y - sun_radius - 5)]
    draw.polygon(arrow_points, fill='orange')
    
    # Draw sunset icon (sun with down arrow) - positioned at 5/6 width
    sun_x2 = 5 * WIDTH // 6
    draw.ellipse([sun_x2 - sun_radius, picto_y - sun_radius, 
                  sun_x2 + sun_radius, picto_y + sun_radius], 
                 fill='orange', outline='darkorange', width=3)
    
    # Sunset arrow (down) - smaller
    arrow_points2 = [(sun_x2, picto_y + sun_radius + 25), 
                     (sun_x2 - arrow_size, picto_y + sun_radius + 5), 
                     (sun_x2 + arrow_size, picto_y + sun_radius + 5)]
    draw.polygon(arrow_points2, fill='orange')
    
    # Add time text (white text on black background) - same size as date
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
    except:
        try:
            font = ImageFont.truetype("arial.ttf", 40)
        except:
            font = ImageFont.load_default()
    
    # Sunrise time
    draw.text((sun_x, picto_y + 130), sunrise_str, fill='white', 
              font=font, anchor='mm')
    
    # Sunset time
    draw.text((sun_x2, picto_y + 130), sunset_str, fill='white', 
              font=font, anchor='mm')
    
    # Add date at bottom in test mode
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


# Test mode: Generate images for different moon phases
if __name__ == "__main__":
    print("Generating test images for different moon phases...\n")
    
    # Configure for Montreal, Quebec
    base_config = {
        "output_dir": "./moon_images",
        "cache_dir": "./moon_cache",
        "latitude": 45.5017,      # Montreal latitude
        "longitude": -73.5673,    # Montreal longitude
        "test_mode": True
    }
    
    # Calculate actual moon phase dates using ephem
    start_date = datetime(2024, 1, 1)
    observer = ephem.Observer()
    observer.date = start_date
    
    # Find actual moon phase dates
    new_moon = ephem.localtime(ephem.next_new_moon(observer.date))
    first_quarter = ephem.localtime(ephem.next_first_quarter_moon(observer.date))
    full_moon = ephem.localtime(ephem.next_full_moon(observer.date))
    last_quarter = ephem.localtime(ephem.next_last_quarter_moon(observer.date))
    
    # Also get dates between phases for crescents and gibbous
    waxing_crescent = new_moon + timedelta(days=3.7)  # ~25% through cycle
    waxing_gibbous = first_quarter + timedelta(days=3.7)  # ~62% through cycle
    waning_gibbous = full_moon + timedelta(days=3.7)  # ~87% through cycle
    waning_crescent = last_quarter + timedelta(days=3.7)  # ~12% through cycle (next cycle)
    
    test_dates = [
        ("New Moon", new_moon),
        ("Waxing Crescent", waxing_crescent),
        ("First Quarter", first_quarter),
        ("Waxing Gibbous", waxing_gibbous),
        ("Full Moon", full_moon),
        ("Waning Gibbous", waning_gibbous),
        ("Last Quarter", last_quarter),
        ("Waning Crescent", waning_crescent)
    ]
    
    for phase_name, test_date in test_dates:
        image_path = generate_moon_phase_image(
            **base_config,
            test_date=test_date
        )
        # Calculate actual phase percentage for this date
        obs = ephem.Observer()
        obs.date = test_date
        moon_obj = ephem.Moon(obs)
        phase_pct = moon_obj.phase
        
        print(f"{phase_name:15} - {test_date.strftime('%Y-%m-%d')} - Phase: {phase_pct:5.1f}% - Generated: {image_path}")
    
    print("\n✓ All test images generated successfully!")
    print("\nFor regular use in Montreal, call the function:")
    print("  generate_moon_phase_image(output_dir='./output', latitude=45.5017, longitude=-73.5673)")
