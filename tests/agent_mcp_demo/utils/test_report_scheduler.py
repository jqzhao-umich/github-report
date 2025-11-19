"""Tests for the ReportScheduler class."""
import pytest
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
from zoneinfo import ZoneInfo
from agent_mcp_demo.utils.report_scheduler import ReportScheduler


@pytest.fixture
def mock_callbacks():
    """Create mock callbacks for report generation and publishing."""
    report_generator = AsyncMock(return_value="Test report content")
    publish_callback = AsyncMock(return_value={
        "status": "published",
        "html": "test.html",
        "message": "Report published successfully"
    })
    git_ops = MagicMock()
    git_ops.commit_and_push = MagicMock(return_value={
        "status": "success",
        "message": "Changes committed and pushed"
    })
    return report_generator, publish_callback, git_ops


@pytest.fixture
def scheduler(mock_callbacks):
    """Create a ReportScheduler instance."""
    report_generator, publish_callback, git_ops = mock_callbacks
    return ReportScheduler(report_generator, publish_callback, git_ops)


@pytest.fixture
def env_vars():
    """Set up test environment variables."""
    old_env = os.environ.copy()
    os.environ["GITHUB_ITERATION_END"] = "2025-11-20"
    os.environ["GITHUB_ITERATION_NAME"] = "Sprint 42"
    os.environ["GITHUB_ORG_NAME"] = "test-org"
    os.environ["TZ"] = "America/New_York"
    yield
    os.environ.clear()
    os.environ.update(old_env)


def mock_datetime_for_timezone(mock_dt, mock_now):
    """Helper to properly mock datetime with timezone awareness."""
    mock_dt.now.return_value = mock_now
    # Make strptime return timezone-aware datetime
    def mock_strptime(date_string, format_string):
        dt = datetime.strptime(date_string, format_string)
        return dt.replace(tzinfo=mock_now.tzinfo)
    mock_dt.strptime.side_effect = mock_strptime
    mock_dt.fromisoformat = datetime.fromisoformat


@pytest.mark.asyncio
async def test_scheduler_initialization(mock_callbacks):
    """Test scheduler initializes correctly."""
    report_generator, publish_callback, git_ops = mock_callbacks
    scheduler = ReportScheduler(report_generator, publish_callback, git_ops)
    
    assert scheduler.report_generator == report_generator
    assert scheduler.publish_callback == publish_callback
    assert scheduler.git_ops == git_ops
    assert scheduler.scheduler is not None
    assert scheduler.last_iteration_checked is None
    assert str(scheduler.scheduler.timezone) == "America/New_York"


@pytest.mark.asyncio
async def test_iteration_ended_generates_report(scheduler, mock_callbacks, env_vars):
    """Test that report is generated when iteration has ended."""
    report_generator, publish_callback, git_ops = mock_callbacks
    
    # Mock datetime to be after iteration end
    with patch('agent_mcp_demo.utils.report_scheduler.datetime') as mock_dt:
        mock_now = datetime(2025, 11, 21, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        mock_datetime_for_timezone(mock_dt, mock_now)
        
        await scheduler.check_and_generate_report()
    
    # Verify report was generated
    report_generator.assert_called_once()
    
    # Verify report was published
    publish_callback.assert_called_once_with(
        report_text="Test report content",
        org_name="test-org",
        iteration_name="Sprint 42",
        skip_duplicate_check=False
    )
    
    # Verify git operations were performed
    git_ops.commit_and_push.assert_called_once()
    call_args = git_ops.commit_and_push.call_args
    assert call_args[1]["file_paths"] == ["docs/", "reports/"]
    assert "Sprint 42" in call_args[1]["commit_message"]
    assert "test-org" in call_args[1]["commit_message"]
    
    # Verify iteration was marked as checked
    assert scheduler.last_iteration_checked == "Sprint 42"


@pytest.mark.asyncio
async def test_iteration_not_ended_skips_generation(scheduler, mock_callbacks, env_vars):
    """Test that no report is generated when iteration has not ended."""
    report_generator, publish_callback, git_ops = mock_callbacks
    
    # Mock datetime to be before iteration end
    with patch('agent_mcp_demo.utils.report_scheduler.datetime') as mock_dt:
        mock_now = datetime(2025, 11, 19, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        mock_datetime_for_timezone(mock_dt, mock_now)
        
        await scheduler.check_and_generate_report()
    
    # Verify no report was generated
    report_generator.assert_not_called()
    publish_callback.assert_not_called()
    git_ops.commit_and_push.assert_not_called()
    assert scheduler.last_iteration_checked is None


@pytest.mark.asyncio
async def test_same_iteration_not_processed_twice(scheduler, mock_callbacks, env_vars):
    """Test that the same iteration is not processed multiple times."""
    report_generator, publish_callback, git_ops = mock_callbacks
    
    # Mock datetime to be after iteration end
    with patch('agent_mcp_demo.utils.report_scheduler.datetime') as mock_dt:
        mock_now = datetime(2025, 11, 21, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        mock_datetime_for_timezone(mock_dt, mock_now)
        
        # First check - should generate report
        await scheduler.check_and_generate_report()
        
        # Reset mocks
        report_generator.reset_mock()
        publish_callback.reset_mock()
        git_ops.commit_and_push.reset_mock()
        
        # Second check - should skip
        await scheduler.check_and_generate_report()
    
    # Verify no second report was generated
    report_generator.assert_not_called()
    publish_callback.assert_not_called()
    git_ops.commit_and_push.assert_not_called()


@pytest.mark.asyncio
async def test_missing_env_vars_skips_generation(scheduler, mock_callbacks):
    """Test that missing environment variables prevents report generation."""
    report_generator, publish_callback, git_ops = mock_callbacks
    
    # Clear all environment variables
    old_env = os.environ.copy()
    os.environ.clear()
    os.environ["TZ"] = "America/New_York"
    
    try:
        await scheduler.check_and_generate_report()
        
        # Verify no report was generated
        report_generator.assert_not_called()
        publish_callback.assert_not_called()
        git_ops.commit_and_push.assert_not_called()
    finally:
        os.environ.clear()
        os.environ.update(old_env)


@pytest.mark.asyncio
async def test_invalid_date_format_skips_generation(scheduler, mock_callbacks):
    """Test that invalid date format prevents report generation."""
    report_generator, publish_callback, git_ops = mock_callbacks
    
    old_env = os.environ.copy()
    os.environ["GITHUB_ITERATION_END"] = "invalid-date"
    os.environ["GITHUB_ITERATION_NAME"] = "Sprint 42"
    os.environ["GITHUB_ORG_NAME"] = "test-org"
    os.environ["TZ"] = "America/New_York"
    
    try:
        await scheduler.check_and_generate_report()
        
        # Verify no report was generated
        report_generator.assert_not_called()
        publish_callback.assert_not_called()
        git_ops.commit_and_push.assert_not_called()
    finally:
        os.environ.clear()
        os.environ.update(old_env)


@pytest.mark.asyncio
async def test_iso_format_date_parsing(scheduler, mock_callbacks):
    """Test that ISO format dates with time are parsed correctly."""
    report_generator, publish_callback, git_ops = mock_callbacks
    
    old_env = os.environ.copy()
    os.environ["GITHUB_ITERATION_END"] = "2025-11-20T23:59:59Z"
    os.environ["GITHUB_ITERATION_NAME"] = "Sprint 42"
    os.environ["GITHUB_ORG_NAME"] = "test-org"
    os.environ["TZ"] = "America/New_York"
    
    try:
        # Mock datetime to be after iteration end
        with patch('agent_mcp_demo.utils.report_scheduler.datetime') as mock_dt:
            mock_now = datetime(2025, 11, 21, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
            mock_datetime_for_timezone(mock_dt, mock_now)
            
            await scheduler.check_and_generate_report()
        
        # Verify report was generated (date was parsed correctly)
        report_generator.assert_called_once()
        publish_callback.assert_called_once()
    finally:
        os.environ.clear()
        os.environ.update(old_env)


@pytest.mark.asyncio
async def test_failed_report_generation_skips_publish(scheduler, mock_callbacks, env_vars):
    """Test that failed report generation prevents publishing."""
    report_generator, publish_callback, git_ops = mock_callbacks
    
    # Mock report generator to return error
    report_generator.return_value = "GitHub token not set"
    
    # Mock datetime to be after iteration end
    with patch('agent_mcp_demo.utils.report_scheduler.datetime') as mock_dt:
        mock_now = datetime(2025, 11, 21, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        mock_datetime_for_timezone(mock_dt, mock_now)
        
        await scheduler.check_and_generate_report()
    
    # Verify report generator was called but publish was not
    report_generator.assert_called_once()
    publish_callback.assert_not_called()
    git_ops.commit_and_push.assert_not_called()
    assert scheduler.last_iteration_checked is None


@pytest.mark.asyncio
async def test_empty_report_skips_publish(scheduler, mock_callbacks, env_vars):
    """Test that empty report prevents publishing."""
    report_generator, publish_callback, git_ops = mock_callbacks
    
    # Mock report generator to return empty string
    report_generator.return_value = ""
    
    # Mock datetime to be after iteration end
    with patch('agent_mcp_demo.utils.report_scheduler.datetime') as mock_dt:
        mock_now = datetime(2025, 11, 21, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        mock_datetime_for_timezone(mock_dt, mock_now)
        
        await scheduler.check_and_generate_report()
    
    # Verify report generator was called but publish was not
    report_generator.assert_called_once()
    publish_callback.assert_not_called()
    git_ops.commit_and_push.assert_not_called()


@pytest.mark.asyncio
async def test_skipped_publish_marks_iteration_checked(scheduler, mock_callbacks, env_vars):
    """Test that skipped publish (duplicate) still marks iteration as checked."""
    report_generator, publish_callback, git_ops = mock_callbacks
    
    # Mock publish callback to return skipped status
    publish_callback.return_value = {
        "status": "skipped",
        "message": "Report already exists"
    }
    
    # Mock datetime to be after iteration end
    with patch('agent_mcp_demo.utils.report_scheduler.datetime') as mock_dt:
        mock_now = datetime(2025, 11, 21, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        mock_datetime_for_timezone(mock_dt, mock_now)
        
        await scheduler.check_and_generate_report()
    
    # Verify report was generated and publish was attempted
    report_generator.assert_called_once()
    publish_callback.assert_called_once()
    
    # Verify git operations were NOT performed
    git_ops.commit_and_push.assert_not_called()
    
    # Verify iteration was still marked as checked
    assert scheduler.last_iteration_checked == "Sprint 42"


@pytest.mark.asyncio
async def test_failed_publish_prevents_git_operations(scheduler, mock_callbacks, env_vars):
    """Test that failed publish prevents git operations."""
    report_generator, publish_callback, git_ops = mock_callbacks
    
    # Mock publish callback to return error status
    publish_callback.return_value = {
        "status": "error",
        "message": "Failed to publish report"
    }
    
    # Mock datetime to be after iteration end
    with patch('agent_mcp_demo.utils.report_scheduler.datetime') as mock_dt:
        mock_now = datetime(2025, 11, 21, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        mock_datetime_for_timezone(mock_dt, mock_now)
        
        await scheduler.check_and_generate_report()
    
    # Verify report was generated and publish was attempted
    report_generator.assert_called_once()
    publish_callback.assert_called_once()
    
    # Verify git operations were NOT performed
    git_ops.commit_and_push.assert_not_called()


@pytest.mark.asyncio
async def test_exception_in_check_is_caught(scheduler, mock_callbacks, env_vars):
    """Test that exceptions during check are caught and logged."""
    report_generator, publish_callback, git_ops = mock_callbacks
    
    # Mock report generator to raise exception
    report_generator.side_effect = Exception("Test exception")
    
    # Mock datetime to be after iteration end
    with patch('agent_mcp_demo.utils.report_scheduler.datetime') as mock_dt:
        mock_now = datetime(2025, 11, 21, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        mock_datetime_for_timezone(mock_dt, mock_now)
        
        # Should not raise exception
        await scheduler.check_and_generate_report()
    
    # Verify report generator was called
    report_generator.assert_called_once()
    
    # Verify publish and git operations were not called
    publish_callback.assert_not_called()
    git_ops.commit_and_push.assert_not_called()


def test_scheduler_start_adds_jobs(scheduler):
    """Test that starting scheduler adds the hourly and startup jobs."""
    with patch.object(scheduler.scheduler, 'add_job') as mock_add_job:
        with patch.object(scheduler.scheduler, 'start') as mock_start:
            scheduler.start()
            
            # Verify hourly job was added
            assert mock_add_job.call_count == 2
            
            # Check first call (hourly job)
            hourly_call = mock_add_job.call_args_list[0]
            assert hourly_call[1]['id'] == 'iteration_check'
            assert hourly_call[1]['replace_existing'] is True
            
            # Check second call (startup job)
            startup_call = mock_add_job.call_args_list[1]
            assert startup_call[1]['id'] == 'startup_check'
            assert startup_call[1]['trigger'] == 'date'
            
            # Verify scheduler was started
            mock_start.assert_called_once()


def test_scheduler_stop_shuts_down(scheduler):
    """Test that stopping scheduler shuts it down."""
    # Start scheduler first so it's running
    with patch.object(scheduler.scheduler, 'start'):
        scheduler.start()
    
    # Mock the running property to return True
    with patch.object(type(scheduler.scheduler), 'running', new_callable=lambda: property(lambda self: True)):
        with patch.object(scheduler.scheduler, 'shutdown') as mock_shutdown:
            scheduler.stop()
            mock_shutdown.assert_called_once()


def test_scheduler_stop_when_not_running(scheduler):
    """Test that stopping scheduler when not running does nothing."""
    # Scheduler is not running by default (never started)
    with patch.object(scheduler.scheduler, 'shutdown') as mock_shutdown:
        scheduler.stop()
        mock_shutdown.assert_not_called()


@pytest.mark.asyncio
async def test_different_timezone_handling(mock_callbacks):
    """Test that scheduler respects different timezones."""
    report_generator, publish_callback, git_ops = mock_callbacks
    
    old_env = os.environ.copy()
    os.environ["GITHUB_ITERATION_END"] = "2025-11-20"
    os.environ["GITHUB_ITERATION_NAME"] = "Sprint 42"
    os.environ["GITHUB_ORG_NAME"] = "test-org"
    os.environ["TZ"] = "UTC"
    
    try:
        scheduler = ReportScheduler(report_generator, publish_callback, git_ops)
        
        # Verify timezone is set correctly
        assert str(scheduler.scheduler.timezone) == "UTC"
        
        # Mock datetime to be after iteration end in UTC
        with patch('agent_mcp_demo.utils.report_scheduler.datetime') as mock_dt:
            mock_now = datetime(2025, 11, 21, 5, 0, 0, tzinfo=ZoneInfo("UTC"))
            mock_datetime_for_timezone(mock_dt, mock_now)
            
            await scheduler.check_and_generate_report()
        
        # Verify report was generated
        report_generator.assert_called_once()
    finally:
        os.environ.clear()
        os.environ.update(old_env)


@pytest.mark.asyncio
async def test_iteration_boundary_exact_end_time(scheduler, mock_callbacks, env_vars):
    """Test behavior at exact iteration end time."""
    report_generator, publish_callback, git_ops = mock_callbacks
    
    # Mock datetime to be exactly at iteration end (end of day)
    with patch('agent_mcp_demo.utils.report_scheduler.datetime') as mock_dt:
        mock_now = datetime(2025, 11, 20, 23, 59, 59, tzinfo=ZoneInfo("America/New_York"))
        mock_datetime_for_timezone(mock_dt, mock_now)
        
        await scheduler.check_and_generate_report()
    
    # Verify report was generated (>= comparison should trigger)
    report_generator.assert_called_once()
    publish_callback.assert_called_once()


@pytest.mark.asyncio
async def test_new_iteration_can_be_processed(scheduler, mock_callbacks):
    """Test that a new iteration can be processed after previous one."""
    report_generator, publish_callback, git_ops = mock_callbacks
    
    # Set up first iteration
    old_env = os.environ.copy()
    os.environ["GITHUB_ITERATION_END"] = "2025-11-20"
    os.environ["GITHUB_ITERATION_NAME"] = "Sprint 42"
    os.environ["GITHUB_ORG_NAME"] = "test-org"
    os.environ["TZ"] = "America/New_York"
    
    try:
        # Process first iteration
        with patch('agent_mcp_demo.utils.report_scheduler.datetime') as mock_dt:
            mock_now = datetime(2025, 11, 21, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
            mock_datetime_for_timezone(mock_dt, mock_now)
            
            await scheduler.check_and_generate_report()
        
        # Verify first iteration was processed
        assert scheduler.last_iteration_checked == "Sprint 42"
        report_generator.assert_called_once()
        
        # Reset mocks
        report_generator.reset_mock()
        publish_callback.reset_mock()
        git_ops.commit_and_push.reset_mock()
        
        # Change to new iteration
        os.environ["GITHUB_ITERATION_END"] = "2025-12-05"
        os.environ["GITHUB_ITERATION_NAME"] = "Sprint 43"
        
        # Process second iteration
        with patch('agent_mcp_demo.utils.report_scheduler.datetime') as mock_dt:
            mock_now = datetime(2025, 12, 6, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
            mock_datetime_for_timezone(mock_dt, mock_now)
            
            await scheduler.check_and_generate_report()
        
        # Verify second iteration was processed
        assert scheduler.last_iteration_checked == "Sprint 43"
        report_generator.assert_called_once()
        publish_callback.assert_called_once()
    finally:
        os.environ.clear()
        os.environ.update(old_env)
