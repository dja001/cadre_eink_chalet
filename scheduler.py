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

# config file and Schedule class
from config_file_handler import load_config
from config_file_handler import Schedule

# eink update / clear functions
from eink_driver import eink_update
from eink_driver import eink_clear

# image generating functions
from xkcd_image import xkcd_todays_image
from xkcd_image import xkcd_random_image
from todo_image import todo_fermeture_chalet
from random_image_from_dropbox import random_image_from_dropbox
from nhl_classification import make_nhl_standings_image
from moon_phase import generate_moon_phase_image

# ============================================================================
# CONFIGURATION - Modify these paths and settings
# ============================================================================

#scheduler_dir = '/home/dominik/Documents/cadre_chalet_code/'
scheduler_dir = '/home/pilist/eink_scheduler/'

CONFIG_FILE = scheduler_dir + "schedule.conf"
ERROR_LOG_FILE = scheduler_dir + "error.log"
RANDOM_UPDATE_INTERVAL_MINUTES = 10  # How often to update when not in scheduled period
CHECK_INTERVAL_SECONDS = 30  # How often to check if we need to update

# ============================================================================
# DISPLAY FUNCTIONS - Replace these with your actual functions
# ============================================================================

def shutdown_display() -> str:
    """Function that does nothing but output shutdown instruction"""
    return "shutdown"

# repeat functions to increase their chance of being randomly choosen
repeated_random_imgs = [random_image_from_dropbox]*6

# List of available display functions for random selection
DISPLAY_FUNCTIONS_TO_RUN_RANDOMLY = [xkcd_random_image, 
                                     *repeated_random_imgs, 
                                     make_nhl_standings_image,
                                     generate_moon_phase_image,
                                    ]

# Dictionary mapping function names to actual functions
# These are necessary for functions to be scheduled
FUNCTION_MAP = {
    "shutdown_display": shutdown_display,
    "xkcd_todays_image": xkcd_todays_image,
    "xkcd_random_image": xkcd_random_image,
    "todo_fermeture_chalet": todo_fermeture_chalet,
    "random_image_from_dropbox": random_image_from_dropbox,
    "make_nhl_standings_image": make_nhl_standings_image,
    "generate_moon_phase_image": generate_moon_phase_image,
}

# ============================================================================
# SCHEDULER CODE
# ============================================================================

class EinkScheduler:
    """Main scheduler class"""
    
    def __init__(self, test_mode=False):
        self.schedules: List[Schedule] = []
        self.last_update_time: Optional[datetime] = None
        self.current_schedule: Optional[Schedule] = None
        self.setup_logging()
        self.test_mode = test_mode
        
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
        """load pre-programmed schedule times"""

        success, schedules = load_config('schedule.conf', FUNCTION_MAP)
        if success:
            logging.info("\n Configuration loaded successfully!")
            logging.info(f"Total schedules: {len(schedules)}")
            self.schedules = schedules
        else:
            logging.error("Failed to load configuration. Exiting.")
            sys.exit(1)
    
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
        
        while len(attempted) < len(DISPLAY_FUNCTIONS_TO_RUN_RANDOMLY):
            func = random.choice(DISPLAY_FUNCTIONS_TO_RUN_RANDOMLY)
            
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
            eink_update(image_path, test_mode=self.test_mode)
            return True
        except Exception as e:
            logging.error(f"E-ink update command crashed: {e}")
            raise  # Re-raise to stop scheduler
    
    def clear_display(self) -> bool:
        """Clear the e-ink display with error handling"""
        try:
            eink_clear(test_mode=self.test_mode)
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
        
        self.load_config()
        
        # On startup, update display for current period
        now = datetime.now()
        active_schedule = self.get_active_schedule(now)
        
        if active_schedule:
            logging.info(f"Starting in scheduled period: {active_schedule}")
            func = FUNCTION_MAP[active_schedule.func_name]
            image_path = self.run_display_function(func)
            if image_path == 'shutdown':
                self.clear_display()
            else:
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
                    func = FUNCTION_MAP[active_schedule.func_name]
                    image_path = self.run_display_function(func)
                    if image_path == 'shutdown':
                        self.clear_display()
                    else:
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
    scheduler = EinkScheduler(test_mode=False)
    scheduler.run()
