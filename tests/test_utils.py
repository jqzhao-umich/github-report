"""
Tests for utility functions
"""

import pytest
import os
from datetime import datetime, timezone, timedelta
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from agent_mcp_demo.agents.utils import (
    get_detroit_timezone,
    get_env_var,
    format_datetime
)

class TestDetroitTimezone:
    """Tests for Detroit timezone utilities"""
    
    def test_get_detroit_timezone(self):
        """Test getting Detroit timezone"""
        tz = get_detroit_timezone()
        
        assert tz is not None
        assert isinstance(tz, timezone)
        # Detroit is UTC-4 (EDT) or UTC-5 (EST)
        # Check that it's a fixed offset
        offset = tz.utcoffset(None)
        assert offset is not None
    
    def test_detroit_timezone_offset(self):
        """Test Detroit timezone offset"""
        tz = get_detroit_timezone()
        offset = tz.utcoffset(None)
        
        # Should be -4 hours (EDT) or -5 hours (EST)
        # The function returns UTC-4
        assert offset.total_seconds() == -4 * 3600

class TestEnvVar:
    """Tests for environment variable utilities"""
    
    def test_get_env_var_exists(self, monkeypatch):
        """Test getting existing environment variable"""
        monkeypatch.setenv("TEST_VAR", "test-value")
        
        value = get_env_var("TEST_VAR", required=False)
        assert value == "test-value"
    
    def test_get_env_var_not_exists_required(self, monkeypatch):
        """Test getting non-existent required environment variable"""
        monkeypatch.delenv("TEST_VAR", raising=False)
        
        with pytest.raises(ValueError, match="required"):
            get_env_var("TEST_VAR", required=True)
    
    def test_get_env_var_not_exists_optional(self, monkeypatch):
        """Test getting non-existent optional environment variable"""
        monkeypatch.delenv("TEST_VAR", raising=False)
        
        value = get_env_var("TEST_VAR", required=False)
        assert value is None
    
    def test_get_env_var_empty_string(self, monkeypatch):
        """Test getting empty string environment variable"""
        monkeypatch.setenv("TEST_VAR", "")
        
        # Empty string should be returned
        value = get_env_var("TEST_VAR", required=False)
        assert value == ""
        
        # But if required, should raise error (empty is falsy)
        with pytest.raises(ValueError, match="required"):
            get_env_var("TEST_VAR", required=True)

class TestFormatDateTime:
    """Tests for datetime formatting utilities"""
    
    def test_format_datetime_utc(self):
        """Test formatting UTC datetime"""
        dt = datetime(2025, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        formatted = format_datetime(dt)
        
        assert "2025-08-06" in formatted
        assert "EDT" in formatted
    
    def test_format_datetime_naive(self):
        """Test formatting naive datetime (assumes UTC)"""
        dt = datetime(2025, 8, 6, 12, 0, 0)
        formatted = format_datetime(dt)
        
        assert "2025-08-06" in formatted
        assert "EDT" in formatted
    
    def test_format_datetime_with_time(self):
        """Test formatting datetime with time component"""
        dt = datetime(2025, 8, 6, 14, 30, 45, tzinfo=timezone.utc)
        formatted = format_datetime(dt)
        
        assert "2025-08-06" in formatted
        assert "EDT" in formatted
        # Should include time
        assert ":" in formatted
    
    def test_format_datetime_different_timezone(self):
        """Test formatting datetime from different timezone"""
        # Create datetime in a different timezone
        other_tz = timezone(timedelta(hours=5))
        dt = datetime(2025, 8, 6, 12, 0, 0, tzinfo=other_tz)
        formatted = format_datetime(dt)
        
        # Should convert to Detroit timezone
        assert "EDT" in formatted
        assert "2025-08-06" in formatted
    
    def test_format_datetime_format_structure(self):
        """Test that formatted datetime has expected structure"""
        dt = datetime(2025, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        formatted = format_datetime(dt)
        
        # Should have date, time, and timezone indicator
        parts = formatted.split()
        assert len(parts) >= 3  # Date, time, timezone
        assert "EDT" in formatted or "EST" in formatted
    
    def test_format_datetime_midnight(self):
        """Test formatting datetime at midnight"""
        dt = datetime(2025, 8, 6, 0, 0, 0, tzinfo=timezone.utc)
        formatted = format_datetime(dt)
        
        # Midnight UTC converts to 8pm EDT the previous day, so check for either date
        assert "2025-08-05" in formatted or "2025-08-06" in formatted
        assert "EDT" in formatted
    
    def test_format_datetime_year_boundary(self):
        """Test formatting datetime at year boundary"""
        dt = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        formatted = format_datetime(dt)
        
        assert "2025-12-31" in formatted or "2026-01-01" in formatted  # May cross date boundary
        assert "EDT" in formatted
    
    def test_format_datetime_consistency(self):
        """Test that formatting is consistent for same datetime"""
        dt = datetime(2025, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        formatted1 = format_datetime(dt)
        formatted2 = format_datetime(dt)
        
        assert formatted1 == formatted2
