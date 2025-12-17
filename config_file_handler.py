
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set, Tuple
import logging

@dataclass
class Schedule:
    days: List[int]  # List of day numbers (0-6)
    hour_start: int
    hour_end: int
    func_name: str
    spans_midnight: bool

    def __str__(self):
        days_str = ','.join(map(str, self.days))
        return f"Days {days_str}: {self.hour_start:02d}:00-{self.hour_end:02d}:00 -> {self.func_name}"

    def is_active(self, dt) -> bool:
        """Check if this schedule is active at given datetime"""
        current_day = dt.weekday()
        current_hour = dt.hour

        if self.spans_midnight:
            # Schedule spans midnight (e.g., 22-6 means 22:00-23:59 and 00:00-05:59)
            # Check if we're on a starting day during late hours
            if current_day in self.days and current_hour >= self.hour_start:
                return True
            # Check if we're on the day after a scheduled day during early hours
            prev_day = (current_day - 1) % 7
            if prev_day in self.days and current_hour < self.hour_end:
                return True
            return False
        else:
            # Normal schedule within a single day
            return (current_day in self.days and
                    self.hour_start <= current_hour < self.hour_end)


def parse_days(days_str: str) -> List[int]:
    """
    Parse day specification into list of day numbers.
    Supports: single (0), ranges (0-4), multiple (0,2,4), mixed (1,3-5), wildcard (*)
    """
    if days_str == '*':
        return list(range(7))

    days = set()
    parts = days_str.split(',')

    for part in parts:
        part = part.strip()
        if '-' in part:
            # Range
            start, end = part.split('-')
            start, end = int(start), int(end)
            if not (0 <= start <= 6 and 0 <= end <= 6):
                raise ValueError(f"Day range out of bounds: {part}")
            if start > end:
                raise ValueError(f"Invalid day range (start > end): {part}")
            days.update(range(start, end + 1))
        else:
            # Single day
            day = int(part)
            if not (0 <= day <= 6):
                raise ValueError(f"Day out of bounds: {day}")
            days.add(day)

    return sorted(list(days))


def get_time_slots(schedule: Schedule) -> Set[Tuple[int, int]]:
    """
    Get all (day, hour) slots occupied by a schedule.
    Handles midnight-spanning schedules.
    """
    slots = set()

    if schedule.spans_midnight:
        # Schedule spans midnight: hour_start to 24, then 0 to hour_end
        for day in schedule.days:
            # Hours on the starting day
            for hour in range(schedule.hour_start, 24):
                slots.add((day, hour))
            # Hours on the next day
            next_day = (day + 1) % 7
            for hour in range(0, schedule.hour_end):
                slots.add((next_day, hour))
    else:
        # Normal schedule within a single day
        for day in schedule.days:
            for hour in range(schedule.hour_start, schedule.hour_end):
                slots.add((day, hour))

    return slots


def check_overlaps(schedules: List[Schedule]) -> bool:
    """
    Check for overlapping schedules.
    Returns True if no overlaps, False if overlaps found (with error logging).
    """
    # Build a map of (day, hour) -> list of (schedule_index, line_num)
    slot_map = {}

    for idx, sched in enumerate(schedules):
        slots = get_time_slots(sched)
        for slot in slots:
            if slot not in slot_map:
                slot_map[slot] = []
            slot_map[slot].append(idx)

    # Check for conflicts
    has_overlap = False
    for slot, schedule_indices in slot_map.items():
        if len(schedule_indices) > 1:
            day, hour = slot
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

            conflicting_schedules = [schedules[i] for i in schedule_indices]
            functions = [s.func_name for s in conflicting_schedules]

            logging.error(
                f"OVERLAP detected at {day_names[day]} {hour:02d}:00: "
                f"Functions {', '.join(functions)} conflict"
            )

            for i in schedule_indices:
                logging.error(f"  - Schedule: {schedules[i]}")

            has_overlap = True

    return not has_overlap


def load_config(config_file: str, function_map: dict) -> Tuple[bool, List[Schedule]]:
    """
    Load and validate schedule configuration.
    Returns (success, schedules)
    """
    try:
        logging.info(f"Loading configuration from {config_file}")
        config_path = Path(config_file)

        if not config_path.exists():
            logging.error(f"Configuration file not found: {config_file}")
            return False, []

        schedules = []
        with open(config_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                parts = line.split()
                if len(parts) != 4:
                    logging.error(f"Invalid config line {line_num}: {line}")
                    logging.error(f"  Expected format: days hour_start hour_end function_name")
                    return False, []

                days_str, hour_start_str, hour_end_str, func_name = parts

                # Parse days
                try:
                    days = parse_days(days_str)
                except ValueError as e:
                    logging.error(f"Invalid day specification in line {line_num}: {e}")
                    return False, []

                # Parse hours
                try:
                    hour_start = int(hour_start_str)
                    hour_end = int(hour_end_str)
                except ValueError:
                    logging.error(f"Invalid hours in config line {line_num}: {line}")
                    return False, []

                if not (0 <= hour_start < 24 and 0 <= hour_end <= 24):
                    logging.error(f"Invalid hours in line {line_num}: {hour_start}-{hour_end} (must be 0-23)")
                    return False, []

                # Check if schedule spans midnight
                spans_midnight = hour_start >= hour_end

                if not spans_midnight and hour_start == hour_end:
                    logging.error(f"Invalid time range in line {line_num}: {hour_start}-{hour_end} (start equals end)")
                    return False, []

                # Validate function name
                if func_name not in function_map:
                    logging.error(f"Unknown function in line {line_num}: {func_name}")
                    logging.error(f"  Available functions: {', '.join(function_map.keys())}")
                    return False, []

                schedules.append(Schedule(days, hour_start, hour_end, func_name, spans_midnight))

        # Check for overlaps
        if not check_overlaps(schedules):
            logging.error("Configuration has overlapping schedules - please fix conflicts")
            return False, []

        logging.info(f"Loaded {len(schedules)} schedules successfully")
        for sched in schedules:
            logging.debug(f"  {sched}")

        return True, schedules

    except Exception as e:
        logging.error(f"Error loading configuration: {e}")
        return False, []


# Example usage for testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Mock function map for testing
    FUNCTION_MAP = {
        'function1': lambda: None,
        'function2': lambda: None,
        'function3': lambda: None,
        'todo_fermeture_chalet': lambda: None,
        'shutdown_display': lambda: None,
    }

    success, schedules = load_config('schedule.conf', FUNCTION_MAP)

    if success:
        print("\n✓ Configuration loaded successfully!")
        print(f"Total schedules: {len(schedules)}")
    else:
        print("\n✗ Configuration failed to load")
