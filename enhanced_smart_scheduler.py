#!/usr/bin/env python3
"""
Enhanced Smart Scheduler for Discord Signal Bot
Properly aligns signal checks with different timeframe candle closes:
- 1h candles: Every hour at xx:00
- 3h candles: Every 3 hours (00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00)
- 6h candles: Every 6 hours (00:00, 06:00, 12:00, 18:00)
- Daily candles: Once per day (after market close for stocks, 00:00 UTC for crypto)
"""

import asyncio
import pytz
from datetime import datetime, timedelta
from typing import Callable, List, Optional, Set
import logging

# Timezone setup
EST = pytz.timezone('US/Eastern')
UTC = pytz.UTC

class EnhancedSmartScheduler:
    """Enhanced scheduler that aligns with all timeframe candle closes"""
    
    def __init__(self, signal_check_function: Callable, timeframes: List[str], logger: Optional[logging.Logger] = None):
        self.signal_check_function = signal_check_function
        self.timeframes = timeframes
        self.logger = logger or logging.getLogger(__name__)
        self.running = False
        self.task = None
        
        # Delay after candle close to ensure data is available
        self.check_delay_minutes = 2
        
    def get_timeframe_close_times(self, base_time: datetime) -> Set[datetime]:
        """Get all candle close times for enabled timeframes within next 24 hours"""
        close_times = set()
        
        # Start from beginning of current hour
        current_hour = base_time.replace(minute=0, second=0, microsecond=0)
        
        for hour_offset in range(25):  # Check next 25 hours to ensure we don't miss any
            check_time = current_hour + timedelta(hours=hour_offset)
            
            for timeframe in self.timeframes:
                if self.is_candle_close_time(check_time, timeframe):
                    # Add delay after candle close
                    alert_time = check_time + timedelta(minutes=self.check_delay_minutes)
                    # Only add future times
                    if alert_time > base_time:
                        close_times.add(alert_time)
        
        return close_times
    
    def is_candle_close_time(self, dt: datetime, timeframe: str) -> bool:
        """Check if datetime aligns with candle close for specific timeframe"""
        hour = dt.hour
        minute = dt.minute
        
        # Only consider exact hour boundaries for candle closes
        if minute != 0:
            return False
            
        if timeframe == '1h':
            # Every hour
            return True
        elif timeframe == '3h':
            # Every 3 hours: 00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00
            return hour % 3 == 0
        elif timeframe == '6h':
            # Every 6 hours: 00:00, 06:00, 12:00, 18:00
            return hour % 6 == 0
        elif timeframe == '1d':
            # Daily candles close at market close (4:00 PM EST) for stocks
            # For crypto, they typically close at 00:00 UTC
            # We'll check at market close time (4:00 PM EST)
            return hour == 16  # 4:00 PM EST
        else:
            # Default: treat as hourly
            return True
    
    def get_next_run_times(self, count: int = 10) -> List[datetime]:
        """Get the next N scheduled run times across all timeframes"""
        now = datetime.now(EST)
        close_times = self.get_timeframe_close_times(now)
        
        # Sort and return the next count times
        sorted_times = sorted(list(close_times))
        return sorted_times[:count]
    
    def get_run_reason(self, run_time: datetime) -> str:
        """Get the reason for this scheduled run based on which timeframes close"""
        # Calculate original candle close time (subtract delay)
        close_time = run_time - timedelta(minutes=self.check_delay_minutes)
        hour = close_time.hour
        
        reasons = []
        
        for timeframe in self.timeframes:
            if self.is_candle_close_time(close_time, timeframe):
                if timeframe == '1h':
                    reasons.append("1h candle close")
                elif timeframe == '3h':
                    reasons.append("3h candle close")
                elif timeframe == '6h':
                    reasons.append("6h candle close")
                elif timeframe == '1d':
                    reasons.append("Daily candle close")
                else:
                    reasons.append(f"{timeframe} candle close")
        
        if not reasons:
            return "Scheduled check"
        
        return " + ".join(reasons)
    
    def is_priority_run(self, run_time: datetime) -> bool:
        """Check if this is a priority run (multiple timeframes or daily)"""
        close_time = run_time - timedelta(minutes=self.check_delay_minutes)
        
        # Count how many timeframes close at this time
        closing_timeframes = 0
        has_daily = False
        
        for timeframe in self.timeframes:
            if self.is_candle_close_time(close_time, timeframe):
                closing_timeframes += 1
                if timeframe == '1d':
                    has_daily = True
        
        # Priority if multiple timeframes close or if daily closes
        return closing_timeframes > 1 or has_daily
    
    def get_time_until_next_run(self) -> timedelta:
        """Get time until next scheduled run"""
        next_runs = self.get_next_run_times(1)
        if next_runs:
            now = datetime.now(EST)
            return next_runs[0] - now
        return timedelta(minutes=15)  # Fallback
    
    async def wait_until_next_run(self) -> datetime:
        """Wait until the next optimal run time"""
        next_run_time = self.get_next_run_times(1)[0]
        now = datetime.now(EST)
        wait_time = (next_run_time - now).total_seconds()
        
        if wait_time > 0:
            reason = self.get_run_reason(next_run_time)
            self.logger.info(f"⏰ Next run scheduled for {next_run_time.strftime('%I:%M:%S %p EST')}")
            self.logger.info(f"📋 Reason: {reason}")
            self.logger.info(f"⏳ Waiting {int(wait_time // 60)}m {int(wait_time % 60)}s...")
            await asyncio.sleep(wait_time)
        
        return next_run_time
    
    async def run_scheduler(self):
        """Main scheduler loop"""
        self.logger.info("🎯 Enhanced Smart Scheduler started")
        self.logger.info(f"📅 Monitoring timeframes: {', '.join(self.timeframes)}")
        self.logger.info(f"⏰ Check delay: {self.check_delay_minutes} minutes after candle close")
        
        cycle_count = 0
        
        while self.running:
            try:
                # Wait until next optimal time
                run_time = await self.wait_until_next_run()
                
                if not self.running:
                    break
                
                cycle_count += 1
                reason = self.get_run_reason(run_time)
                is_priority = self.is_priority_run(run_time)
                
                self.logger.info(f"\n🚀 Starting enhanced signal check #{cycle_count}")
                self.logger.info(f"🕐 Run time: {run_time.strftime('%Y-%m-%d %I:%M:%S %p EST')}")
                self.logger.info(f"📋 Reason: {reason}")
                self.logger.info(f"⭐ Priority run: {'Yes' if is_priority else 'No'}")
                
                # Run the signal check
                await self.signal_check_function(cycle_count, is_priority, reason)
                
                self.logger.info(f"✅ Enhanced signal check #{cycle_count} completed")
                
            except asyncio.CancelledError:
                self.logger.info("⏹️ Enhanced Scheduler cancelled")
                break
            except Exception as e:
                self.logger.error(f"❌ Error in enhanced scheduler: {e}")
                # Wait a bit before retrying to avoid rapid failures
                await asyncio.sleep(60)
    
    def start(self):
        """Start the enhanced scheduler"""
        if self.running:
            self.logger.warning("⚠️ Enhanced Scheduler is already running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self.run_scheduler())
        self.logger.info("✅ Enhanced Smart Scheduler started")
        
        # Show next few run times
        next_runs = self.get_next_run_times(8)
        self.logger.info("📅 Next 8 scheduled runs:")
        for i, run_time in enumerate(next_runs, 1):
            reason = self.get_run_reason(run_time)
            priority = "⭐" if self.is_priority_run(run_time) else "📊"
            self.logger.info(f"   {i}. {run_time.strftime('%I:%M %p EST')} {priority} - {reason}")
    
    def stop(self):
        """Stop the enhanced scheduler"""
        if not self.running:
            self.logger.warning("⚠️ Enhanced Scheduler is not running")
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
        self.logger.info("⏹️ Enhanced Smart Scheduler stopped")
    
    def is_running(self) -> bool:
        """Check if enhanced scheduler is running"""
        return self.running and self.task and not self.task.done()
    
    def get_status_info(self) -> dict:
        """Get detailed status information"""
        now = datetime.now(EST)
        next_runs = self.get_next_run_times(5)
        
        return {
            'running': self.is_running(),
            'current_time': now.strftime('%Y-%m-%d %I:%M:%S %p EST'),
            'timeframes': self.timeframes,
            'check_delay_minutes': self.check_delay_minutes,
            'next_run_time': next_runs[0].strftime('%I:%M:%S %p EST') if next_runs else 'Unknown',
            'next_run_reason': self.get_run_reason(next_runs[0]) if next_runs else 'Unknown',
            'time_until_next': str(self.get_time_until_next_run()).split('.')[0],
            'upcoming_runs': [
                {
                    'time': run_time.strftime('%I:%M %p EST'),
                    'reason': self.get_run_reason(run_time),
                    'is_priority': self.is_priority_run(run_time)
                }
                for run_time in next_runs
            ]
        }

def create_enhanced_scheduler(signal_check_function: Callable, 
                            timeframes: List[str],
                            check_delay_minutes: int = 2,
                            logger: Optional[logging.Logger] = None) -> EnhancedSmartScheduler:
    """Create a configured enhanced smart scheduler"""
    scheduler = EnhancedSmartScheduler(signal_check_function, timeframes, logger)
    scheduler.check_delay_minutes = check_delay_minutes
    return scheduler 