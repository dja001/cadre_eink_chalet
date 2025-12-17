#!/usr/bin/env python3
"""
E-ink Display Scheduler
Manages scheduled and random display updates for e-ink display
"""

import time
import random
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Callable, Optional, Tuple
import sys

from xkcd_image import xkcd_todays_image
from xkcd_image import xkcd_random_image
from todo_image import todo_fermeture_chalet
from random_image_from_dropbox import random_image_from_dropbox

# ============================================================================
# CONFIGURATION - Modify these paths and settings
# ============================================================================

scheduler_dir = '/home/dominik/Documents/cadre_chalet_code/'
#scheduler_dir = '/home/pi/eink_scheduler/'

CONFIG_FILE = scheduler_dir + "schedule.conf"
ERROR_LOG_FILE = scheduler_dir + "error.log"
RANDOM_UPDATE_INTERVAL_MINUTES = 1  # How often to update when not in scheduled period
CHECK_INTERVAL_SECONDS = 30  # How often to check if we need to update

# ============================================================================
# DISPLAY FUNCTIONS - Replace these with your actual functions
# ============================================================================

def function1() -> str:
    """Example display function - replace with your actual implementation"""
    # Your code to generate image
    return "/path/to/generated/image1.png"

def function2() -> str:
    """Example display function - replace with your actual implementation"""
    return "/path/to/generated/image2.png"

def function3() -> str:
    """Example display function - replace with your actual implementation"""
    return "/path/to/generated/image3.png"

# List of available display functions for random selection
AVAILABLE_DISPLAY_FUNCTIONS = [xkcd_todays_image, xkcd_random_image, todo_fermeture_chalet, random_image_from_dropbox]

# Dictionary mapping function names to actual functions
FUNCTION_MAP = {
    "xkcd_todays_image": xkcd_todays_image,
    "xkcd_random_image": xkcd_random_image,
    "todo_fermeture_chalet": todo_fermeture_chalet,
}

# ============================================================================
# E-INK CONTROL FUNCTIONS - Replace with your actual e-ink driver calls
# ============================================================================

def eink_update(image_path: str) -> None:
    """Update e-ink display with given image"""
    logging.info(f"Updating e-ink display with: {image_path}")

    import os
    import shutil

    src = image_path
    dst = 'figures/current_image.png'

    if os.path.isfile(dst):
        os.remove(dst)

    shutil.copyfile(src, dst)


    # Replace with your actual e-ink update code
    # Example: epd.display(epd.getbuffer(Image.open(image_path)))
    pass

def eink_clear() -> None:
    """Clear e-ink display"""
    logging.info("Clearing e-ink display")
    # Replace with your actual e-ink clear code
    # Example: epd.clear()
    pass

# ============================================================================
# SCHEDULER CODE
# ============================================================================

class Schedule:
    """Represents a scheduled display period"""
    def __init__(self, day_of_week: int, hour_start: int, hour_end: int, function_name: str):
        self.day_of_week = day_of_week  # 0=Monday, 6=Sunday
        self.hour_start = hour_start
        self.hour_end = hour_end
        self.function_name = function_name
        
    def is_active(self, dt: datetime) -> bool:
        """Check if this schedule is active at given datetime"""
        return (dt.weekday() == self.day_of_week and 
                self.hour_start <= dt.hour < self.hour_end)
    
    def __repr__(self):
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        return f"Schedule({days[self.day_of_week]} {self.hour_start:02d}:00-{self.hour_end:02d}:00 -> {self.function_name})"


class EinkScheduler:
    """Main scheduler class"""
    
    def __init__(self):
        self.schedules: List[Schedule] = []
        self.last_update_time: Optional[datetime] = None
        self.current_schedule: Optional[Schedule] = None
        self.setup_logging()
        
    def setup_logging(self):
        """Setup logging configuration"""
        # Console logging (verbose)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_format)
        
        # Error file logging (less verbose)
        error_handler = logging.FileHandler(ERROR_LOG_FILE)
        error_handler.setLevel(logging.ERROR)
        error_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        error_handler.setFormatter(error_format)
        
        # Configure root logger
        logging.basicConfig(level=logging.DEBUG, handlers=[console_handler, error_handler])

        # Silence noisy libraries
        for noisy in ("PIL", "PIL.Image", "urllib3", "matplotlib"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
        
    def load_config(self) -> bool:
        """Load and validate schedule configuration"""
        try:
            logging.info(f"Loading configuration from {CONFIG_FILE}")
            config_path = Path(CONFIG_FILE)
            
            if not config_path.exists():
                logging.error(f"Configuration file not found: {CONFIG_FILE}")
                return False
            
            schedules = []
            with open(config_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    parts = line.split()
                    if len(parts) != 4:
                        logging.error(f"Invalid config line {line_num}: {line}")
                        return False
                    
                    day_str, hour_start_str, hour_end_str, func_name = parts
                    
                    try:
                        day = int(day_str)
                        hour_start = int(hour_start_str)
                        hour_end = int(hour_end_str)
                    except ValueError:
                        logging.error(f"Invalid numbers in config line {line_num}: {line}")
                        return False
                    
                    if not (0 <= day <= 6):
                        logging.error(f"Invalid day_of_week in line {line_num}: {day} (must be 0-6)")
                        return False
                    
                    if not (0 <= hour_start < 24 and 0 <= hour_end <= 24):
                        logging.error(f"Invalid hours in line {line_num}: {hour_start}-{hour_end}")
                        return False
                    
                    if hour_start >= hour_end:
                        logging.error(f"hour_start must be < hour_end in line {line_num}")
                        return False
                    
                    if func_name not in FUNCTION_MAP:
                        logging.error(f"Unknown function in line {line_num}: {func_name}")
                        return False
                    
                    schedules.append(Schedule(day, hour_start, hour_end, func_name))
            
            # Check for overlaps
            if not self.check_overlaps(schedules):
                return False
            
            self.schedules = schedules
            logging.info(f"Loaded {len(self.schedules)} schedules successfully")
            for sched in self.schedules:
                logging.debug(f"  {sched}")
            
            return True
            
        except Exception as e:
            logging.error(f"Error loading configuration: {e}")
            return False
    
    def check_overlaps(self, schedules: List[Schedule]) -> bool:
        """Check for overlapping schedules"""
        for i, s1 in enumerate(schedules):
            for s2 in schedules[i+1:]:
                if s1.day_of_week == s2.day_of_week:
                    # Check if hours overlap
                    if not (s1.hour_end <= s2.hour_start or s2.hour_end <= s1.hour_start):
                        logging.error(f"Overlapping schedules detected: {s1} and {s2}")
                        return False
        return True
    
    def get_active_schedule(self, dt: datetime) -> Optional[Schedule]:
        """Get the active schedule for given datetime"""
        for schedule in self.schedules:
            if schedule.is_active(dt):
                return schedule
        return None
    
    def run_display_function(self, func: Callable) -> Optional[str]:
        """Run a display function with error handling"""
        try:
            logging.debug(f"Running display function: {func.__name__}")
            image_path = func()
            logging.debug(f"Display function returned: {image_path}")
            return image_path
        except Exception as e:
            logging.error(f"Display function {func.__name__} crashed: {e}")
            return None
    
    def run_random_function(self) -> Optional[str]:
        """Run a random display function, retry if it fails"""
        attempted = set()
        
        while len(attempted) < len(AVAILABLE_DISPLAY_FUNCTIONS):
            func = random.choice(AVAILABLE_DISPLAY_FUNCTIONS)
            
            if func in attempted:
                continue
            
            attempted.add(func)
            image_path = self.run_display_function(func)
            
            if image_path is not None:
                return image_path
            
            logging.warning(f"Function {func.__name__} failed, trying another...")
        
        logging.error("All display functions failed!")
        return None
    
    def update_display(self, image_path: str) -> bool:
        """Update the e-ink display with error handling"""
        try:
            eink_update(image_path)
            return True
        except Exception as e:
            logging.error(f"E-ink update command crashed: {e}")
            raise  # Re-raise to stop scheduler
    
    def clear_display(self) -> bool:
        """Clear the e-ink display with error handling"""
        try:
            eink_clear()
            return True
        except Exception as e:
            logging.error(f"E-ink clear command crashed: {e}")
            raise  # Re-raise to stop scheduler
    
    def should_update_random(self) -> bool:
        """Check if it's time for a random update"""
        if self.last_update_time is None:
            return True
        
        elapsed = datetime.now() - self.last_update_time
        return elapsed >= timedelta(minutes=RANDOM_UPDATE_INTERVAL_MINUTES)
    
    def run(self):
        """Main scheduler loop"""
        logging.info("E-ink Display Scheduler starting...")
        
        if not self.load_config():
            logging.error("Failed to load configuration. Exiting.")
            sys.exit(1)
        
        logging.info("Scheduler initialized successfully")
        
        # On startup, update display for current period
        now = datetime.now()
        active_schedule = self.get_active_schedule(now)
        
        if active_schedule:
            logging.info(f"Starting in scheduled period: {active_schedule}")
            func = FUNCTION_MAP[active_schedule.function_name]
            image_path = self.run_display_function(func)
            if image_path:
                self.update_display(image_path)
                self.current_schedule = active_schedule
        else:
            logging.info("Starting in random period")
            image_path = self.run_random_function()
            if image_path:
                self.update_display(image_path)
        
        self.last_update_time = now
        
        # Main loop
        while True:
            try:
                time.sleep(CHECK_INTERVAL_SECONDS)
                now = datetime.now()
                
                active_schedule = self.get_active_schedule(now)
                
                # Check if we've entered a new scheduled period
                if active_schedule and active_schedule != self.current_schedule:
                    logging.info(f"Entering scheduled period: {active_schedule}")
                    func = FUNCTION_MAP[active_schedule.function_name]
                    image_path = self.run_display_function(func)
                    if image_path:
                        self.update_display(image_path)
                    self.current_schedule = active_schedule
                    self.last_update_time = now
                
                # Check if we've exited a scheduled period
                elif not active_schedule and self.current_schedule is not None:
                    logging.info(f"Exiting scheduled period: {self.current_schedule}")
                    self.current_schedule = None
                    # Immediately run random function
                    image_path = self.run_random_function()
                    if image_path:
                        self.update_display(image_path)
                    self.last_update_time = now
                
                # Random update during non-scheduled time
                elif not active_schedule and self.should_update_random():
                    logging.info("Time for random update")
                    image_path = self.run_random_function()
                    if image_path:
                        self.update_display(image_path)
                    self.last_update_time = now
                
            except KeyboardInterrupt:
                logging.info("Scheduler stopped by user")
                break
            except Exception as e:
                logging.error(f"Fatal error in scheduler: {e}")
                sys.exit(1)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    scheduler = EinkScheduler()
    scheduler.run()
