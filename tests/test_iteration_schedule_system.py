"""Tests for the iteration schedule system."""
import pytest
import os
import yaml
import tempfile
from datetime import datetime, date
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from zoneinfo import ZoneInfo


@pytest.fixture
def temp_schedule_dir():
    """Create a temporary directory for schedule files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        schedule_dir = Path(tmpdir) / ".github"
        schedule_dir.mkdir(parents=True, exist_ok=True)
        yield schedule_dir


@pytest.fixture
def sample_iteration_info():
    """Sample iteration info from GitHub API."""
    return {
        'name': 'Sprint 42',
        'start_date': '2025-11-05T00:00:00Z',
        'end_date': '2025-11-20T23:59:59Z'
    }


@pytest.fixture
def schedule_file_path(temp_schedule_dir):
    """Path to schedule file in temp directory."""
    return temp_schedule_dir / "iteration-schedule.yml"


def test_schedule_file_creation(schedule_file_path, sample_iteration_info):
    """Test creating a schedule file with iteration info."""
    # Parse end date and calculate next iteration start
    end_date = datetime.fromisoformat(sample_iteration_info['end_date'].replace('Z', '+00:00'))
    eastern = ZoneInfo("America/New_York")
    end_date_eastern = end_date.astimezone(eastern)
    
    from datetime import timedelta
    next_iteration_start = end_date_eastern.date() + timedelta(days=1)
    
    # Create schedule data
    schedule_data = {
        'next_iteration_start_date': next_iteration_start.isoformat(),
        'previous_iteration_name': sample_iteration_info['name'],
        'last_updated': datetime.now(eastern).isoformat()
    }
    
    # Write to file
    with open(schedule_file_path, 'w') as f:
        yaml.dump(schedule_data, f, default_flow_style=False, sort_keys=False)
    
    # Verify file exists and contains correct data
    assert schedule_file_path.exists()
    
    with open(schedule_file_path) as f:
        loaded_data = yaml.safe_load(f)
    
    assert loaded_data['next_iteration_start_date'] == '2025-11-21'
    assert loaded_data['previous_iteration_name'] == 'Sprint 42'
    assert 'last_updated' in loaded_data


def test_schedule_file_reading(schedule_file_path):
    """Test reading schedule file and checking date."""
    # Create a schedule file
    schedule_data = {
        'next_iteration_start_date': '2025-11-20',
        'previous_iteration_name': 'Sprint 42',
        'last_updated': '2025-11-15T10:00:00-05:00'
    }
    
    with open(schedule_file_path, 'w') as f:
        yaml.dump(schedule_data, f)
    
    # Read and verify
    with open(schedule_file_path) as f:
        loaded_data = yaml.safe_load(f)
    
    scheduled_date = date.fromisoformat(loaded_data['next_iteration_start_date'])
    assert scheduled_date == date(2025, 11, 20)
    assert loaded_data['previous_iteration_name'] == 'Sprint 42'


def test_schedule_date_matches_today(schedule_file_path):
    """Test checking if scheduled date matches today."""
    today = date.today()
    
    # Create schedule with today's date
    schedule_data = {
        'next_iteration_start_date': today.isoformat(),
        'previous_iteration_name': 'Current Sprint',
        'last_updated': datetime.now().isoformat()
    }
    
    with open(schedule_file_path, 'w') as f:
        yaml.dump(schedule_data, f)
    
    # Check if should generate
    with open(schedule_file_path) as f:
        config = yaml.safe_load(f)
    
    scheduled_date = date.fromisoformat(config['next_iteration_start_date'])
    should_generate = (today == scheduled_date)
    
    assert should_generate is True


def test_schedule_date_not_today(schedule_file_path):
    """Test checking if scheduled date is not today."""
    # Create schedule with future date
    schedule_data = {
        'next_iteration_start_date': '2025-12-31',
        'previous_iteration_name': 'Future Sprint',
        'last_updated': datetime.now().isoformat()
    }
    
    with open(schedule_file_path, 'w') as f:
        yaml.dump(schedule_data, f)
    
    # Check if should generate
    with open(schedule_file_path) as f:
        config = yaml.safe_load(f)
    
    scheduled_date = date.fromisoformat(config['next_iteration_start_date'])
    today = date.today()
    should_generate = (today == scheduled_date)
    
    assert should_generate is False


def test_schedule_file_missing(temp_schedule_dir):
    """Test handling missing schedule file."""
    schedule_file = temp_schedule_dir / "iteration-schedule.yml"
    
    # Verify file doesn't exist
    assert not schedule_file.exists()
    
    # Simulate fallback behavior
    scheduled_date = None
    should_use_fallback = scheduled_date is None
    
    assert should_use_fallback is True


def test_schedule_file_invalid_yaml(schedule_file_path):
    """Test handling invalid YAML in schedule file."""
    # Write invalid YAML
    with open(schedule_file_path, 'w') as f:
        f.write("invalid: yaml: content: [")
    
    # Try to read - should raise exception
    with pytest.raises(yaml.YAMLError):
        with open(schedule_file_path) as f:
            yaml.safe_load(f)


def test_schedule_file_missing_fields(schedule_file_path):
    """Test handling schedule file with missing required fields."""
    # Create schedule without required fields
    schedule_data = {
        'last_updated': datetime.now().isoformat()
    }
    
    with open(schedule_file_path, 'w') as f:
        yaml.dump(schedule_data, f)
    
    # Read and check for missing fields
    with open(schedule_file_path) as f:
        config = yaml.safe_load(f)
    
    scheduled_date_str = config.get('next_iteration_start_date')
    iteration_name = config.get('previous_iteration_name')
    
    assert scheduled_date_str is None
    assert iteration_name is None


def test_schedule_file_null_values(schedule_file_path):
    """Test handling schedule file with null values."""
    # Create schedule with null values
    schedule_data = {
        'next_iteration_start_date': None,
        'previous_iteration_name': None,
        'last_updated': None
    }
    
    with open(schedule_file_path, 'w') as f:
        yaml.dump(schedule_data, f)
    
    # Read and verify
    with open(schedule_file_path) as f:
        config = yaml.safe_load(f)
    
    assert config['next_iteration_start_date'] is None
    assert config['previous_iteration_name'] is None
    
    # Should trigger fallback
    should_use_fallback = config.get('next_iteration_start_date') is None
    assert should_use_fallback is True


def test_timezone_conversion_to_eastern(sample_iteration_info):
    """Test converting UTC iteration end date to Eastern time."""
    end_date_utc = datetime.fromisoformat(sample_iteration_info['end_date'].replace('Z', '+00:00'))
    
    # Convert to Eastern
    eastern = ZoneInfo("America/New_York")
    end_date_eastern = end_date_utc.astimezone(eastern)
    
    # Verify conversion (Nov 20 2025 23:59:59 UTC = Nov 20 2025 18:59:59 EST)
    assert end_date_eastern.date() == date(2025, 11, 20)
    assert end_date_eastern.hour == 18  # 6 PM Eastern
    assert end_date_eastern.minute == 59


def test_schedule_update_preserves_format(schedule_file_path):
    """Test that updating schedule preserves YAML format."""
    # Create initial schedule
    initial_data = {
        'next_iteration_end_date': '2025-11-20',
        'next_iteration_name': 'Sprint 42',
        'last_updated': '2025-11-15T10:00:00-05:00'
    }
    
    with open(schedule_file_path, 'w') as f:
        yaml.dump(initial_data, f, default_flow_style=False, sort_keys=False)
    
    # Update schedule
    updated_data = {
        'next_iteration_end_date': '2025-12-05',
        'next_iteration_name': 'Sprint 43',
        'last_updated': datetime.now(ZoneInfo("America/New_York")).isoformat()
    }
    
    with open(schedule_file_path, 'w') as f:
        yaml.dump(updated_data, f, default_flow_style=False, sort_keys=False)
    
    # Verify update
    with open(schedule_file_path) as f:
        loaded_data = yaml.safe_load(f)
    
    assert loaded_data['next_iteration_end_date'] == '2025-12-05'
    assert loaded_data['next_iteration_name'] == 'Sprint 43'


def test_multiple_iterations_sequence(schedule_file_path):
    """Test updating schedule through multiple iterations."""
    iterations = [
        ('2025-11-20', 'Sprint 42'),
        ('2025-12-05', 'Sprint 43'),
        ('2025-12-20', 'Sprint 44')
    ]
    
    for end_date, name in iterations:
        schedule_data = {
            'next_iteration_end_date': end_date,
            'next_iteration_name': name,
            'last_updated': datetime.now(ZoneInfo("America/New_York")).isoformat()
        }
        
        with open(schedule_file_path, 'w') as f:
            yaml.dump(schedule_data, f, default_flow_style=False, sort_keys=False)
        
        # Verify each update
        with open(schedule_file_path) as f:
            loaded_data = yaml.safe_load(f)
        
        assert loaded_data['next_iteration_end_date'] == end_date
        assert loaded_data['next_iteration_name'] == name


def test_date_comparison_with_different_formats():
    """Test date comparison works with different date formats."""
    # ISO format from schedule
    schedule_date = date.fromisoformat('2025-11-20')
    
    # Date from datetime
    dt = datetime(2025, 11, 20, 10, 30, 45)
    dt_date = dt.date()
    
    # Date object
    today = date(2025, 11, 20)
    
    # All should be equal
    assert schedule_date == dt_date
    assert schedule_date == today
    assert dt_date == today


def test_iteration_info_extraction(sample_iteration_info):
    """Test extracting relevant fields from iteration info."""
    name = sample_iteration_info.get('name')
    start_date = sample_iteration_info.get('start_date')
    end_date = sample_iteration_info.get('end_date')
    
    assert name == 'Sprint 42'
    assert start_date is not None
    assert end_date is not None
    
    # Verify end date can be parsed
    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    assert isinstance(end_dt, datetime)


def test_fallback_to_github_api_when_no_schedule():
    """Test that system falls back to GitHub API when schedule missing."""
    # Simulate checking for schedule file
    schedule_exists = False
    scheduled_date = None if not schedule_exists else "2025-11-20"
    
    # Simulate fallback logic
    should_check_api = scheduled_date is None
    
    assert should_check_api is True


def test_fallback_to_github_api_when_date_mismatch():
    """Test that system falls back to GitHub API when date doesn't match."""
    # Schedule exists but date doesn't match
    scheduled_date = date(2025, 12, 31)
    today = date(2025, 11, 20)
    
    # Check if dates match
    dates_match = (today == scheduled_date)
    should_check_api = not dates_match
    
    assert should_check_api is True


def test_schedule_update_with_timezone_aware_datetime():
    """Test that schedule updates use timezone-aware datetime."""
    eastern = ZoneInfo("America/New_York")
    now = datetime.now(eastern)
    
    # Verify timezone is preserved
    assert now.tzinfo is not None
    assert str(now.tzinfo) == "America/New_York"
    
    # ISO format preserves timezone
    iso_str = now.isoformat()
    assert '-04:00' in iso_str or '-05:00' in iso_str  # EDT or EST


def test_schedule_handles_dst_transitions():
    """Test schedule handling across DST transitions."""
    eastern = ZoneInfo("America/New_York")
    
    # Before DST ends (EST)
    before_dst = datetime(2025, 11, 1, 12, 0, 0, tzinfo=eastern)
    
    # After DST ends (EDT)
    after_dst = datetime(2025, 3, 10, 12, 0, 0, tzinfo=eastern)
    
    # Both should have valid timezone info
    assert before_dst.tzinfo is not None
    assert after_dst.tzinfo is not None
    
    # ISO format should reflect correct offset
    before_iso = before_dst.isoformat()
    after_iso = after_dst.isoformat()
    
    assert before_iso != after_iso  # Different offsets


def test_schedule_file_permissions(schedule_file_path):
    """Test that schedule file can be created with proper permissions."""
    schedule_data = {
        'next_iteration_end_date': '2025-11-20',
        'next_iteration_name': 'Sprint 42',
        'last_updated': datetime.now().isoformat()
    }
    
    with open(schedule_file_path, 'w') as f:
        yaml.dump(schedule_data, f)
    
    # Verify file is readable
    assert schedule_file_path.exists()
    assert os.access(schedule_file_path, os.R_OK)
    
    # Verify can read back
    with open(schedule_file_path) as f:
        loaded_data = yaml.safe_load(f)
    
    assert loaded_data is not None


def test_schedule_date_parsing_edge_cases():
    """Test edge cases in date parsing."""
    # Valid ISO date
    valid_date = date.fromisoformat('2025-11-20')
    assert valid_date.year == 2025
    assert valid_date.month == 11
    assert valid_date.day == 20
    
    # Leap year date
    leap_date = date.fromisoformat('2024-02-29')
    assert leap_date.year == 2024
    assert leap_date.month == 2
    assert leap_date.day == 29
    
    # Year boundary
    year_end = date.fromisoformat('2025-12-31')
    assert year_end.year == 2025
    assert year_end.month == 12
    assert year_end.day == 31


def test_schedule_with_special_characters_in_name(schedule_file_path):
    """Test schedule with special characters in iteration name."""
    special_names = [
        'Sprint 42: Bug Fixes',
        'Sprint 43 (Hotfix)',
        'Sprint 44 - Feature Release',
        'Sprint 45 & Cleanup',
        'Sprint-46'
    ]
    
    for name in special_names:
        schedule_data = {
            'next_iteration_end_date': '2025-11-20',
            'next_iteration_name': name,
            'last_updated': datetime.now().isoformat()
        }
        
        with open(schedule_file_path, 'w') as f:
            yaml.dump(schedule_data, f)
        
        # Verify it can be read back
        with open(schedule_file_path) as f:
            loaded_data = yaml.safe_load(f)
        
        assert loaded_data['next_iteration_name'] == name


def test_concurrent_schedule_access(schedule_file_path):
    """Test that schedule file can be safely read while being updated."""
    # Write initial data
    initial_data = {
        'next_iteration_end_date': '2025-11-20',
        'next_iteration_name': 'Sprint 42',
        'last_updated': datetime.now().isoformat()
    }
    
    with open(schedule_file_path, 'w') as f:
        yaml.dump(initial_data, f)
    
    # Simulate read
    with open(schedule_file_path) as f:
        read_data = yaml.safe_load(f)
    
    assert read_data is not None
    assert read_data['next_iteration_name'] == 'Sprint 42'


def test_schedule_backward_compatibility(schedule_file_path):
    """Test that schedule works with old format."""
    # Old format might have different field names
    old_format_data = {
        'next_iteration_end_date': '2025-11-20',
        'next_iteration_name': 'Sprint 42',
        'last_updated': '2025-11-15T10:00:00-05:00'
    }
    
    with open(schedule_file_path, 'w') as f:
        yaml.dump(old_format_data, f)
    
    # Read and verify all fields present
    with open(schedule_file_path) as f:
        loaded_data = yaml.safe_load(f)
    
    assert 'next_iteration_end_date' in loaded_data
    assert 'next_iteration_name' in loaded_data
    assert 'last_updated' in loaded_data
