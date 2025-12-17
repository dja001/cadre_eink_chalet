import unittest
from datetime import datetime
from config_file_handler import Schedule, parse_days, get_time_slots, check_overlaps


class TestScheduleIsActive(unittest.TestCase):
    """Tests for Schedule.is_active() method"""
    
    def test_single_day_normal_hours(self):
        """Test schedule on single day with normal hours (9am-5pm)"""
        # Monday 9am-5pm
        schedule = Schedule([0], 9, 17, "work", False)
        
        # Monday 10am - should be active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 16, 10, 0)))  # Monday
        
        # Monday 9am - should be active (start hour inclusive)
        self.assertTrue(schedule.is_active(datetime(2024, 12, 16, 9, 0)))
        
        # Monday 5pm - should NOT be active (end hour exclusive)
        self.assertFalse(schedule.is_active(datetime(2024, 12, 16, 17, 0)))
        
        # Monday 8am - should NOT be active
        self.assertFalse(schedule.is_active(datetime(2024, 12, 16, 8, 0)))
        
        # Tuesday 10am - should NOT be active (wrong day)
        self.assertFalse(schedule.is_active(datetime(2024, 12, 17, 10, 0)))
    
    def test_weekday_range(self):
        """Test schedule spanning multiple weekdays (Mon-Fri 9am-5pm)"""
        # Monday through Friday 9am-5pm
        schedule = Schedule([0, 1, 2, 3, 4], 9, 17, "work", False)
        
        # Monday 10am - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 16, 10, 0)))
        
        # Wednesday 2pm - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 18, 14, 0)))
        
        # Friday 4pm - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 20, 16, 0)))
        
        # Saturday 10am - NOT active
        self.assertFalse(schedule.is_active(datetime(2024, 12, 21, 10, 0)))
        
        # Sunday 10am - NOT active
        self.assertFalse(schedule.is_active(datetime(2024, 12, 22, 10, 0)))
    
    def test_weekend_schedule(self):
        """Test schedule for weekends only (Sat-Sun 2pm-8pm)"""
        # Saturday and Sunday 2pm-8pm
        schedule = Schedule([5, 6], 14, 20, "weekend", False)
        
        # Saturday 3pm - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 21, 15, 0)))
        
        # Sunday 7pm - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 22, 19, 0)))
        
        # Friday 3pm - NOT active
        self.assertFalse(schedule.is_active(datetime(2024, 12, 20, 15, 0)))
        
        # Monday 3pm - NOT active
        self.assertFalse(schedule.is_active(datetime(2024, 12, 16, 15, 0)))
    
    def test_midnight_spanning_single_day(self):
        """Test schedule spanning midnight on a single day (Friday 10pm-6am)"""
        # Friday 10pm to Saturday 6am
        schedule = Schedule([4], 22, 6, "night", True)
        
        # Friday 11pm - active (on scheduled day, late hours)
        self.assertTrue(schedule.is_active(datetime(2024, 12, 20, 23, 0)))
        
        # Friday 10pm - active (start hour)
        self.assertTrue(schedule.is_active(datetime(2024, 12, 20, 22, 0)))
        
        # Saturday 3am - active (day after Friday, early hours)
        self.assertTrue(schedule.is_active(datetime(2024, 12, 21, 3, 0)))
        
        # Saturday 5am - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 21, 5, 0)))
        
        # Saturday 6am - NOT active (end hour exclusive)
        self.assertFalse(schedule.is_active(datetime(2024, 12, 21, 6, 0)))
        
        # Friday 9pm - NOT active (before start hour)
        self.assertFalse(schedule.is_active(datetime(2024, 12, 20, 21, 0)))
        
        # Saturday 11pm - NOT active (wrong day for late hours)
        self.assertFalse(schedule.is_active(datetime(2024, 12, 21, 23, 0)))
    
    def test_midnight_spanning_multiple_days(self):
        """Test schedule spanning midnight on multiple days (Fri-Sat 10pm-6am)"""
        # Friday and Saturday 10pm to 6am
        schedule = Schedule([4, 5], 22, 6, "night", True)
        
        # Friday 11pm - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 20, 23, 0)))
        
        # Saturday 3am - active (after Friday)
        self.assertTrue(schedule.is_active(datetime(2024, 12, 21, 3, 0)))
        
        # Saturday 11pm - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 21, 23, 0)))
        
        # Sunday 3am - active (after Saturday)
        self.assertTrue(schedule.is_active(datetime(2024, 12, 22, 3, 0)))
        
        # Thursday 11pm - NOT active (not a scheduled day)
        self.assertFalse(schedule.is_active(datetime(2024, 12, 19, 23, 0)))
        
        # Sunday 11pm - NOT active (not a scheduled day for late hours)
        self.assertFalse(schedule.is_active(datetime(2024, 12, 22, 23, 0)))
        
        # Monday 3am - NOT active (Sunday not scheduled)
        self.assertFalse(schedule.is_active(datetime(2024, 12, 23, 3, 0)))
    
    def test_every_day_midnight_spanning(self):
        """Test schedule every night spanning midnight (all days 11pm-7am)"""
        # Every day 11pm to 7am
        schedule = Schedule([0, 1, 2, 3, 4, 5, 6], 23, 7, "shutdown", True)
        
        # Any day at midnight - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 16, 0, 0)))
        
        # Any day at 11pm - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 18, 23, 0)))
        
        # Any day at 3am - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 20, 3, 0)))
        
        # Any day at 6am - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 22, 6, 0)))
        
        # Any day at 7am - NOT active (end hour)
        self.assertFalse(schedule.is_active(datetime(2024, 12, 16, 7, 0)))
        
        # Any day at 10pm - NOT active (before start)
        self.assertFalse(schedule.is_active(datetime(2024, 12, 18, 22, 0)))
        
        # Any day at noon - NOT active
        self.assertFalse(schedule.is_active(datetime(2024, 12, 20, 12, 0)))
    
    def test_non_contiguous_days(self):
        """Test schedule on non-contiguous days (Mon, Wed, Fri 7am-9am)"""
        # Monday, Wednesday, Friday 7am-9am
        schedule = Schedule([0, 2, 4], 7, 9, "morning", False)
        
        # Monday 8am - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 16, 8, 0)))
        
        # Wednesday 8am - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 18, 8, 0)))
        
        # Friday 8am - active
        self.assertTrue(schedule.is_active(datetime(2024, 12, 20, 8, 0)))
        
        # Tuesday 8am - NOT active
        self.assertFalse(schedule.is_active(datetime(2024, 12, 17, 8, 0)))
        
        # Thursday 8am - NOT active
        self.assertFalse(schedule.is_active(datetime(2024, 12, 19, 8, 0)))


class TestParseDays(unittest.TestCase):
    """Tests for parse_days() function"""
    
    def test_single_day(self):
        """Test parsing single day"""
        self.assertEqual(parse_days("0"), [0])
        self.assertEqual(parse_days("6"), [6])
    
    def test_day_range(self):
        """Test parsing day ranges"""
        self.assertEqual(parse_days("0-4"), [0, 1, 2, 3, 4])
        self.assertEqual(parse_days("5-6"), [5, 6])
        self.assertEqual(parse_days("0-6"), [0, 1, 2, 3, 4, 5, 6])
    
    def test_multiple_days(self):
        """Test parsing multiple specific days"""
        self.assertEqual(parse_days("0,2,4"), [0, 2, 4])
        self.assertEqual(parse_days("1,3,5"), [1, 3, 5])
    
    def test_mixed_format(self):
        """Test parsing mixed day specifications"""
        self.assertEqual(parse_days("0,2-4"), [0, 2, 3, 4])
        self.assertEqual(parse_days("1,3-5,6"), [1, 3, 4, 5, 6])
    
    def test_wildcard(self):
        """Test parsing wildcard"""
        self.assertEqual(parse_days("*"), [0, 1, 2, 3, 4, 5, 6])
    
    def test_invalid_day(self):
        """Test that invalid days raise errors"""
        with self.assertRaises(ValueError):
            parse_days("7")  # Day 7 doesn't exist
        
        with self.assertRaises(ValueError):
            parse_days("-1")  # Negative day
        
        with self.assertRaises(ValueError):
            parse_days("0-7")  # Range includes invalid day


class TestOverlapDetection(unittest.TestCase):
    """Tests for overlap detection"""
    
    def test_no_overlap_different_days(self):
        """Test schedules on different days don't overlap"""
        schedules = [
            Schedule([0], 9, 17, "func1", False),  # Monday 9-5
            Schedule([1], 9, 17, "func2", False),  # Tuesday 9-5
        ]
        self.assertTrue(check_overlaps(schedules))
    
    def test_no_overlap_different_times(self):
        """Test schedules on same day but different times don't overlap"""
        schedules = [
            Schedule([0], 9, 12, "func1", False),  # Monday 9-12
            Schedule([0], 14, 17, "func2", False),  # Monday 2-5
        ]
        self.assertTrue(check_overlaps(schedules))
    
    def test_overlap_same_day_and_time(self):
        """Test schedules on same day and time do overlap"""
        schedules = [
            Schedule([0], 9, 17, "func1", False),  # Monday 9-5
            Schedule([0], 14, 18, "func2", False),  # Monday 2-6 (overlaps 2-5)
        ]
        self.assertFalse(check_overlaps(schedules))
    
    def test_overlap_day_range_conflict(self):
        """Test overlapping day ranges"""
        schedules = [
            Schedule([0, 1, 2], 9, 17, "func1", False),  # Mon-Wed 9-5
            Schedule([2, 3, 4], 10, 15, "func2", False),  # Wed-Fri 10-3 (Wed overlaps)
        ]
        self.assertFalse(check_overlaps(schedules))
    
    def test_overlap_midnight_spanning(self):
        """Test midnight-spanning schedules overlap correctly"""
        schedules = [
            Schedule([4], 22, 6, "func1", True),   # Fri 10pm-6am
            Schedule([5], 3, 9, "func2", False),   # Sat 3am-9am (overlaps 3-6am)
        ]
        self.assertFalse(check_overlaps(schedules))
    
    def test_no_overlap_midnight_spanning_adjacent(self):
        """Test adjacent midnight-spanning schedules don't overlap"""
        schedules = [
            Schedule([4], 22, 6, "func1", True),   # Fri 10pm-6am
            Schedule([5], 6, 12, "func2", False),  # Sat 6am-12pm (starts where other ends)
        ]
        self.assertTrue(check_overlaps(schedules))


if __name__ == '__main__':
    unittest.main()
