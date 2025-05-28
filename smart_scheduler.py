#!/usr/bin/env python3
"""
Smart Scheduler for Discord Signal Bot
Runs signal checks at optimal times aligned with market candle closes.
"""

import asyncio
import pytz
from datetime import datetime, timedelta
from typing import Callable, List, Optional
import logging

# Timezone setup
EST = pytz.timezone('US/Eastern')
UTC = pytz.UTC

class SmartScheduler:
    """Smart scheduler that runs signal checks at optimal market times"""
    
    def __init__(self, signal_check_function: Callable, logger: Optional[logging.Logger] = None):
        self.signal_check_function = signal_check_function
        self.logger = logger or logging.getLogger(__name__)
        self.running = False
        self.task = None
        
        # Configuration
        self.run_at_minutes = [2, 17, 32, 47]  # Run 2 minutes after each quarter-hour
        self.priority_run_minutes = [2, 32]     # Priority runs at 2 and 32 minutes (near hourly closes)
        self.market_hours_start = 9  # 9:30 AM EST (market open)
        self.market_hours_end = 16   # 4:00 PM EST (market close)
        self.after_hours_frequency = 2  # Only run twice per hour after market close
        
    def get_next_run_times(self, count: int = 5) -> List[datetime]:
        """Get the next N scheduled run times"""
        now = datetime.now(EST)
        run_times = []
        
        # Start from current hour
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        
        for hour_offset in range(24):  # Check next 24 hours
            check_time = current_hour + timedelta(hours=hour_offset)
            
            # Determine which minutes to run based on market hours
            if self.is_market_hours(check_time):
                # Market hours: run at all configured minutes
                minutes_to_run = self.run_at_minutes
            else:
                # After hours: only run at priority times
                minutes_to_run = self.priority_run_minutes
            
            for minute in minutes_to_run:
                run_time = check_time.replace(minute=minute, second=0, microsecond=0)
                
                # Only add future times
                if run_time > now:
                    run_times.append(run_time)
                    
                # Stop when we have enough
                if len(run_times) >= count:
                    return run_times[:count]
        
        return run_times[:count]
    
    def is_market_hours(self, dt: datetime) -> bool:
        """Check if datetime is during market hours (9:30 AM - 4:00 PM EST, Mon-Fri)"""
        # Convert to EST if needed
        if dt.tzinfo != EST:
            dt = dt.astimezone(EST)
        
        # Check if it's a weekday
        if dt.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
        
        # Check if it's within market hours
        hour = dt.hour
        minute = dt.minute
        
        # Market opens at 9:30 AM
        if hour < 9 or (hour == 9 and minute < 30):
            return False
        
        # Market closes at 4:00 PM
        if hour >= 16:
            return False
            
        return True
    
    def get_time_until_next_run(self) -> timedelta:
        """Get time until next scheduled run"""
        next_runs = self.get_next_run_times(1)
        if next_runs:
            now = datetime.now(EST)
            return next_runs[0] - now
        return timedelta(seconds=300)  # Fallback to 5 minutes
    
    def get_run_reason(self, run_time: datetime) -> str:
        """Get the reason for this scheduled run"""
        minute = run_time.minute
        
        if minute == 2:
            return "Hourly candle close (priority)"
        elif minute == 17:
            return "Mid-hour update"
        elif minute == 32:
            return "Half-hour candle close (priority)"
        elif minute == 47:
            return "Quarter-hour update"
        else:
            return "Scheduled check"
    
    async def wait_until_next_run(self) -> datetime:
        """Wait until the next optimal run time"""
        next_run_time = self.get_next_run_times(1)[0]
        now = datetime.now(EST)
        wait_time = (next_run_time - now).total_seconds()
        
        if wait_time > 0:
            self.logger.info(f"⏰ Next run scheduled for {next_run_time.strftime('%I:%M:%S %p EST')} ({self.get_run_reason(next_run_time)})")
            self.logger.info(f"⏳ Waiting {int(wait_time // 60)}m {int(wait_time % 60)}s...")
            await asyncio.sleep(wait_time)
        
        return next_run_time
    
    async def run_scheduler(self):
        """Main scheduler loop"""
        self.logger.info("🎯 Smart Scheduler started")
        self.logger.info(f"📅 Market hours schedule: {self.run_at_minutes} minutes past each hour")
        self.logger.info(f"🌙 After hours schedule: {self.priority_run_minutes} minutes past each hour")
        
        cycle_count = 0
        
        while self.running:
            try:
                # Wait until next optimal time
                run_time = await self.wait_until_next_run()
                
                if not self.running:
                    break
                
                cycle_count += 1
                reason = self.get_run_reason(run_time)
                is_priority = run_time.minute in self.priority_run_minutes
                
                self.logger.info(f"\n🚀 Starting signal check #{cycle_count}")
                self.logger.info(f"🕐 Run time: {run_time.strftime('%Y-%m-%d %I:%M:%S %p EST')}")
                self.logger.info(f"📋 Reason: {reason}")
                self.logger.info(f"⭐ Priority run: {'Yes' if is_priority else 'No'}")
                self.logger.info(f"📈 Market hours: {'Yes' if self.is_market_hours(run_time) else 'No'}")
                
                # Run the signal check
                await self.signal_check_function(cycle_count, is_priority, reason)
                
                self.logger.info(f"✅ Signal check #{cycle_count} completed")
                
            except asyncio.CancelledError:
                self.logger.info("⏹️ Scheduler cancelled")
                break
            except Exception as e:
                self.logger.error(f"❌ Error in scheduler: {e}")
                # Wait a bit before retrying to avoid rapid failures
                await asyncio.sleep(60)
    
    def start(self):
        """Start the scheduler"""
        if self.running:
            self.logger.warning("⚠️ Scheduler is already running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self.run_scheduler())
        self.logger.info("✅ Smart Scheduler started")
        
        # Show next few run times
        next_runs = self.get_next_run_times(5)
        self.logger.info("📅 Next 5 scheduled runs:")
        for i, run_time in enumerate(next_runs, 1):
            reason = self.get_run_reason(run_time)
            market_status = "📈 Market" if self.is_market_hours(run_time) else "🌙 After"
            self.logger.info(f"   {i}. {run_time.strftime('%I:%M %p EST')} - {reason} ({market_status})")
    
    def stop(self):
        """Stop the scheduler"""
        if not self.running:
            self.logger.warning("⚠️ Scheduler is not running")
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
        self.logger.info("⏹️ Smart Scheduler stopped")
    
    def is_running(self) -> bool:
        """Check if scheduler is running"""
        return self.running and self.task and not self.task.done()
    
    def get_status_info(self) -> dict:
        """Get detailed status information"""
        now = datetime.now(EST)
        next_runs = self.get_next_run_times(3)
        
        return {
            'running': self.is_running(),
            'current_time': now.strftime('%Y-%m-%d %I:%M:%S %p EST'),
            'is_market_hours': self.is_market_hours(now),
            'next_run_time': next_runs[0].strftime('%I:%M:%S %p EST') if next_runs else 'Unknown',
            'next_run_reason': self.get_run_reason(next_runs[0]) if next_runs else 'Unknown',
            'time_until_next': str(self.get_time_until_next_run()).split('.')[0],  # Remove microseconds
            'upcoming_runs': [
                {
                    'time': run_time.strftime('%I:%M %p EST'),
                    'reason': self.get_run_reason(run_time),
                    'is_market_hours': self.is_market_hours(run_time),
                    'is_priority': run_time.minute in self.priority_run_minutes
                }
                for run_time in next_runs
            ]
        }

class SchedulerConfig:
    """Configuration for the smart scheduler"""
    
    # Default schedule: Run 4 times per hour during market hours
    MARKET_HOURS_SCHEDULE = [2, 17, 32, 47]  # Minutes past the hour
    
    # After hours: Only run twice per hour (at priority times)
    AFTER_HOURS_SCHEDULE = [2, 32]  # Minutes past the hour
    
    # Market hours (EST)
    MARKET_OPEN_HOUR = 9    # 9:30 AM
    MARKET_OPEN_MINUTE = 30
    MARKET_CLOSE_HOUR = 16  # 4:00 PM
    
    # Priority run times (align with hourly candle closes)
    PRIORITY_MINUTES = [2, 32]  # 2 minutes after hourly closes
    
    @classmethod
    def create_custom_schedule(cls, 
                             market_minutes: List[int] = None,
                             after_hours_minutes: List[int] = None,
                             priority_minutes: List[int] = None) -> dict:
        """Create a custom schedule configuration"""
        return {
            'market_hours_schedule': market_minutes or cls.MARKET_HOURS_SCHEDULE,
            'after_hours_schedule': after_hours_minutes or cls.AFTER_HOURS_SCHEDULE,
            'priority_minutes': priority_minutes or cls.PRIORITY_MINUTES,
            'market_open': {'hour': cls.MARKET_OPEN_HOUR, 'minute': cls.MARKET_OPEN_MINUTE},
            'market_close': {'hour': cls.MARKET_CLOSE_HOUR, 'minute': 0}
        }

# Convenience function for integration
def create_smart_scheduler(signal_check_function: Callable, 
                          custom_config: dict = None,
                          logger: Optional[logging.Logger] = None) -> SmartScheduler:
    """Create a configured smart scheduler"""
    scheduler = SmartScheduler(signal_check_function, logger)
    
    if custom_config:
        scheduler.run_at_minutes = custom_config.get('market_hours_schedule', scheduler.run_at_minutes)
        scheduler.priority_run_minutes = custom_config.get('after_hours_schedule', scheduler.priority_run_minutes)
        scheduler.priority_run_minutes = custom_config.get('priority_minutes', scheduler.priority_run_minutes)
    
    return scheduler 