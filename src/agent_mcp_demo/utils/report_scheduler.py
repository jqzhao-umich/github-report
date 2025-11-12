"""Automatic report scheduling at iteration end."""
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)


class ReportScheduler:
    def __init__(self, report_generator_callback, publish_callback, git_operations):
        """Initialize the report scheduler.
        
        Args:
            report_generator_callback: Async function to generate report
            publish_callback: Async function to publish report
            git_operations: GitOperations instance for commit/push
        """
        self.report_generator = report_generator_callback
        self.publish_callback = publish_callback
        self.git_ops = git_operations
        self.scheduler = AsyncIOScheduler(timezone=ZoneInfo(os.environ.get("TZ", "America/New_York")))
        self.last_iteration_checked = None
        
    async def check_and_generate_report(self):
        """Check if iteration has ended and generate report if needed."""
        try:
            logger.info("Checking for iteration end...")
            
            # Get iteration info from environment or API
            iteration_end = os.getenv("GITHUB_ITERATION_END")
            iteration_name = os.getenv("GITHUB_ITERATION_NAME")
            org_name = os.getenv("GITHUB_ORG_NAME")
            
            if not all([iteration_end, iteration_name, org_name]):
                logger.warning("Missing iteration configuration, skipping check")
                return
            
            # Parse end date
            try:
                # Handle both formats: YYYY-MM-DD and ISO format with time
                if 'T' in iteration_end:
                    end_date = datetime.fromisoformat(iteration_end.replace('Z', '+00:00'))
                else:
                    end_date = datetime.strptime(iteration_end, "%Y-%m-%d")
                    # Set to end of day
                    end_date = end_date.replace(hour=23, minute=59, second=59)
            except ValueError as e:
                logger.error(f"Invalid iteration end date format: {iteration_end}, {e}")
                return
            
            now = datetime.now(ZoneInfo(os.environ.get("TZ", "America/New_York")))
            
            # Check if iteration has ended and we haven't generated report yet
            if now >= end_date and self.last_iteration_checked != iteration_name:
                logger.info(f"Iteration {iteration_name} has ended. Generating report...")
                
                # Generate report
                report_text = await self.report_generator()
                
                if not report_text or report_text.startswith("GitHub token not set"):
                    logger.error("Failed to generate report")
                    return
                
                # Publish report
                result = await self.publish_callback(
                    report_text=report_text,
                    org_name=org_name,
                    iteration_name=iteration_name,
                    skip_duplicate_check=False
                )
                
                if result.get("status") == "skipped":
                    logger.info(f"Report already exists: {result.get('message')}")
                    self.last_iteration_checked = iteration_name
                    return
                
                logger.info(f"Report published: {result.get('html', 'Unknown')}")
                
                # Auto-commit and push
                if result.get("status") == "published":
                    commit_msg = f"Auto-generate report for {iteration_name}\n\n- Organization: {org_name}\n- End date: {iteration_end}\n- Generated: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                    
                    git_result = self.git_ops.commit_and_push(
                        file_paths=["docs/", "reports/"],
                        commit_message=commit_msg
                    )
                    
                    logger.info(f"Git operation: {git_result.get('status')} - {git_result.get('message')}")
                    
                # Mark this iteration as processed
                self.last_iteration_checked = iteration_name
                
        except Exception as e:
            logger.error(f"Error in check_and_generate_report: {e}", exc_info=True)
    
    def start(self):
        """Start the scheduler.
        
        Checks for iteration end every hour.
        """
        # Check every hour
        self.scheduler.add_job(
            self.check_and_generate_report,
            trigger=CronTrigger(minute=0, timezone=ZoneInfo(os.environ.get("TZ", "America/New_York"))),
            id='iteration_check',
            replace_existing=True
        )
        
        # Also check on startup (after 1 minute to allow server to be ready)
        startup_time = datetime.now() + timedelta(minutes=1)
        self.scheduler.add_job(
            self.check_and_generate_report,
            trigger='date',
            run_date=startup_time,
            id='startup_check'
        )
        
        self.scheduler.start()
        logger.info("Report scheduler started - checking hourly for iteration end")
    
    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Report scheduler stopped")
