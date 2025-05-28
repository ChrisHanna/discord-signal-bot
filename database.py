import asyncio
import asyncpg
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import json

class DatabaseManager:
    def __init__(self):
        self.pool = None
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize database connection pool"""
        try:
            database_url = os.getenv('DATABASE_URL')
            if not database_url:
                self.logger.error("DATABASE_URL environment variable not found")
                return False
            
            # Create connection pool
            self.pool = await asyncpg.create_pool(
                database_url,
                min_size=1,
                max_size=5,
                server_settings={
                    'application_name': 'discord-signal-bot',
                    'timezone': 'EST'
                }
            )
            
            # Create tables if they don't exist
            await self.create_tables()
            
            self.logger.info("✅ Database connection established")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Database initialization failed: {e}")
            return False
    
    async def create_tables(self):
        """Create necessary tables if they don't exist"""
        async with self.pool.acquire() as conn:
            # Create tickers table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tickers (
                    symbol VARCHAR(10) PRIMARY KEY,
                    name VARCHAR(100),
                    exchange VARCHAR(20),
                    active BOOLEAN DEFAULT true,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            ''')
            
            # Enhanced signal_notifications table with priority tracking
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS signal_notifications (
                    id SERIAL PRIMARY KEY,
                    ticker VARCHAR(10) NOT NULL,
                    timeframe VARCHAR(5) NOT NULL,
                    signal_type VARCHAR(50) NOT NULL,
                    signal_date TIMESTAMPTZ NOT NULL,
                    notified_at TIMESTAMPTZ DEFAULT NOW(),
                    strength VARCHAR(20),
                    system VARCHAR(50),
                    discord_message_id BIGINT,
                    priority_score INTEGER DEFAULT 0,
                    priority_level VARCHAR(10),
                    was_vip_ticker BOOLEAN DEFAULT FALSE,
                    was_vip_timeframe BOOLEAN DEFAULT FALSE,
                    urgency_bonus INTEGER DEFAULT 0,
                    pattern_bonus INTEGER DEFAULT 0,
                    CONSTRAINT unique_signal UNIQUE(ticker, timeframe, signal_type, signal_date)
                )
            ''')
            
            # New signals_detected table to track ALL signals, not just notifications
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS signals_detected (
                    id SERIAL PRIMARY KEY,
                    ticker VARCHAR(10) NOT NULL,
                    timeframe VARCHAR(5) NOT NULL,
                    signal_type VARCHAR(50) NOT NULL,
                    signal_date TIMESTAMPTZ NOT NULL,
                    detected_at TIMESTAMPTZ DEFAULT NOW(),
                    strength VARCHAR(20),
                    system VARCHAR(50),
                    priority_score INTEGER NOT NULL,
                    priority_level VARCHAR(10) NOT NULL,
                    was_sent BOOLEAN DEFAULT FALSE,
                    skip_reason VARCHAR(100),
                    signal_data JSONB,
                    CONSTRAINT unique_detected_signal UNIQUE(ticker, timeframe, signal_type, signal_date)
                )
            ''')
            
            # Priority configuration table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS priority_config (
                    id SERIAL PRIMARY KEY,
                    config_name VARCHAR(50) UNIQUE NOT NULL,
                    min_priority_level VARCHAR(10) NOT NULL,
                    critical_threshold INTEGER NOT NULL,
                    high_threshold INTEGER NOT NULL,
                    medium_threshold INTEGER NOT NULL,
                    low_threshold INTEGER NOT NULL,
                    vip_tickers TEXT[],
                    vip_timeframes TEXT[],
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            ''')
            
            # Signal performance tracking
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS signal_performance (
                    id SERIAL PRIMARY KEY,
                    ticker VARCHAR(10) NOT NULL,
                    timeframe VARCHAR(5) NOT NULL,
                    signal_type VARCHAR(50) NOT NULL,
                    signal_date TIMESTAMPTZ NOT NULL,
                    performance_date TIMESTAMPTZ NOT NULL,
                    price_at_signal DECIMAL(10,2),
                    price_after_1h DECIMAL(10,2),
                    price_after_4h DECIMAL(10,2),
                    price_after_1d DECIMAL(10,2),
                    price_after_3d DECIMAL(10,2),
                    max_gain_1d DECIMAL(5,2),
                    max_loss_1d DECIMAL(5,2),
                    success_1h BOOLEAN,
                    success_4h BOOLEAN,
                    success_1d BOOLEAN,
                    success_3d BOOLEAN,
                    CONSTRAINT unique_performance UNIQUE(ticker, timeframe, signal_type, signal_date)
                )
            ''')
            
            # Signal analytics summary
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS signal_analytics (
                    id SERIAL PRIMARY KEY,
                    date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    timeframe VARCHAR(5) NOT NULL,
                    system VARCHAR(50) NOT NULL,
                    total_signals INTEGER DEFAULT 0,
                    sent_signals INTEGER DEFAULT 0,
                    skipped_signals INTEGER DEFAULT 0,
                    avg_priority_score DECIMAL(5,1),
                    priority_distribution JSONB,
                    success_rate_1h DECIMAL(5,2),
                    success_rate_1d DECIMAL(5,2),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    CONSTRAINT unique_analytics UNIQUE(date, ticker, timeframe, system)
                )
            ''')
            
            # User_preferences table with enhanced priority settings
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    discord_user_id BIGINT PRIMARY KEY,
                    tickers TEXT[],
                    min_strength VARCHAR(20) DEFAULT 'Medium',
                    min_priority_level VARCHAR(10) DEFAULT 'MEDIUM',
                    custom_vip_tickers TEXT[],
                    custom_vip_timeframes TEXT[],
                    notifications_enabled BOOLEAN DEFAULT true,
                    priority_boost_multiplier DECIMAL(3,1) DEFAULT 1.0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            ''')
            
            # Create comprehensive indexes for performance
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_signal_date 
                ON signal_notifications(signal_date DESC)
            ''')
            
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_ticker_timeframe 
                ON signal_notifications(ticker, timeframe)
            ''')
            
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_notified_at 
                ON signal_notifications(notified_at DESC)
            ''')
            
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_priority_score 
                ON signal_notifications(priority_score DESC)
            ''')
            
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_detected_signals_date
                ON signals_detected(detected_at DESC)
            ''')
            
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_detected_priority
                ON signals_detected(priority_score DESC, was_sent)
            ''')
            
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_performance_ticker_date
                ON signal_performance(ticker, signal_date DESC)
            ''')
            
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_analytics_date
                ON signal_analytics(date DESC, ticker, system)
            ''')
            
            self.logger.info("✅ Database tables created/verified")
    
    async def record_detected_signal(self, ticker: str, timeframe: str, signal_type: str,
                                   signal_date: str, strength: str, system: str,
                                   priority_score: int, priority_level: str,
                                   was_sent: bool, skip_reason: str = None,
                                   signal_data: dict = None) -> bool:
        """Record every signal detected, whether sent or not"""
        try:
            async with self.pool.acquire() as conn:
                # Parse signal date
                if ' ' in signal_date:
                    parsed_date = datetime.strptime(signal_date, '%Y-%m-%d %H:%M:%S')
                else:
                    parsed_date = datetime.strptime(signal_date, '%Y-%m-%d')
                
                # Insert detected signal record
                await conn.execute('''
                    INSERT INTO signals_detected 
                    (ticker, timeframe, signal_type, signal_date, strength, system,
                     priority_score, priority_level, was_sent, skip_reason, signal_data)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (ticker, timeframe, signal_type, signal_date) 
                    DO UPDATE SET 
                        detected_at = NOW(),
                        was_sent = EXCLUDED.was_sent,
                        skip_reason = EXCLUDED.skip_reason,
                        priority_score = EXCLUDED.priority_score,
                        priority_level = EXCLUDED.priority_level
                ''', ticker, timeframe, signal_type, parsed_date, strength, system,
                     priority_score, priority_level, was_sent, skip_reason, 
                     json.dumps(signal_data) if signal_data else None)
                
                return True
                
        except Exception as e:
            self.logger.error(f"❌ Error recording detected signal: {e}")
            return False
    
    async def check_duplicate_notification(self, ticker: str, timeframe: str, 
                                         signal_type: str, signal_date: str) -> bool:
        """Check if we've already sent this notification"""
        try:
            async with self.pool.acquire() as conn:
                # Parse signal date
                if ' ' in signal_date:
                    parsed_date = datetime.strptime(signal_date, '%Y-%m-%d %H:%M:%S')
                else:
                    parsed_date = datetime.strptime(signal_date, '%Y-%m-%d')
                
                # Check if notification exists
                result = await conn.fetchval('''
                    SELECT COUNT(*) FROM signal_notifications 
                    WHERE ticker = $1 AND timeframe = $2 
                    AND signal_type = $3 AND signal_date = $4
                ''', ticker, timeframe, signal_type, parsed_date)
                
                return result > 0
                
        except Exception as e:
            self.logger.error(f"❌ Error checking duplicate: {e}")
            return False
    
    async def record_notification(self, ticker: str, timeframe: str, signal_type: str,
                                signal_date: str, strength: str = None, system: str = None,
                                discord_message_id: int = None, priority_score: int = 0,
                                priority_level: str = 'MEDIUM', was_vip_ticker: bool = False,
                                was_vip_timeframe: bool = False, urgency_bonus: int = 0,
                                pattern_bonus: int = 0) -> bool:
        """Record a sent notification with enhanced priority tracking"""
        try:
            async with self.pool.acquire() as conn:
                # Parse signal date
                if ' ' in signal_date:
                    parsed_date = datetime.strptime(signal_date, '%Y-%m-%d %H:%M:%S')
                else:
                    parsed_date = datetime.strptime(signal_date, '%Y-%m-%d')
                
                # Insert notification record
                await conn.execute('''
                    INSERT INTO signal_notifications 
                    (ticker, timeframe, signal_type, signal_date, strength, system, 
                     discord_message_id, priority_score, priority_level, was_vip_ticker,
                     was_vip_timeframe, urgency_bonus, pattern_bonus)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (ticker, timeframe, signal_type, signal_date) 
                    DO UPDATE SET 
                        notified_at = NOW(),
                        discord_message_id = EXCLUDED.discord_message_id,
                        priority_score = EXCLUDED.priority_score,
                        priority_level = EXCLUDED.priority_level
                ''', ticker, timeframe, signal_type, parsed_date, strength, system, 
                     discord_message_id, priority_score, priority_level, was_vip_ticker,
                     was_vip_timeframe, urgency_bonus, pattern_bonus)
                
                return True
                
        except Exception as e:
            self.logger.error(f"❌ Error recording notification: {e}")
            return False
    
    async def get_priority_analytics(self, days: int = 7) -> Dict:
        """Get comprehensive priority analytics"""
        try:
            async with self.pool.acquire() as conn:
                since_date = datetime.now() - timedelta(days=days)
                
                # Get detected vs sent signal stats
                detection_stats = await conn.fetchrow('''
                    SELECT 
                        COUNT(*) as total_detected,
                        COUNT(*) FILTER (WHERE was_sent = true) as total_sent,
                        COUNT(*) FILTER (WHERE was_sent = false) as total_skipped,
                        AVG(priority_score) as avg_priority_score,
                        COUNT(*) FILTER (WHERE priority_level = 'CRITICAL') as critical_count,
                        COUNT(*) FILTER (WHERE priority_level = 'HIGH') as high_count,
                        COUNT(*) FILTER (WHERE priority_level = 'MEDIUM') as medium_count,
                        COUNT(*) FILTER (WHERE priority_level = 'LOW') as low_count,
                        COUNT(*) FILTER (WHERE priority_level = 'MINIMAL') as minimal_count
                    FROM signals_detected 
                    WHERE detected_at >= $1
                ''', since_date)
                
                # Get top skipped signals by priority
                top_skipped = await conn.fetch('''
                    SELECT ticker, signal_type, priority_score, skip_reason, COUNT(*) as count
                    FROM signals_detected 
                    WHERE detected_at >= $1 AND was_sent = false
                    GROUP BY ticker, signal_type, priority_score, skip_reason
                    ORDER BY priority_score DESC, count DESC
                    LIMIT 10
                ''', since_date)
                
                # Get system performance
                system_stats = await conn.fetch('''
                    SELECT 
                        system,
                        COUNT(*) as total_signals,
                        COUNT(*) FILTER (WHERE was_sent = true) as sent_signals,
                        AVG(priority_score) as avg_priority,
                        MAX(priority_score) as max_priority
                    FROM signals_detected 
                    WHERE detected_at >= $1
                    GROUP BY system
                    ORDER BY avg_priority DESC
                ''', since_date)
                
                # Get ticker performance
                ticker_stats = await conn.fetch('''
                    SELECT 
                        ticker,
                        COUNT(*) as total_signals,
                        COUNT(*) FILTER (WHERE was_sent = true) as sent_signals,
                        AVG(priority_score) as avg_priority
                    FROM signals_detected 
                    WHERE detected_at >= $1
                    GROUP BY ticker
                    ORDER BY total_signals DESC
                    LIMIT 20
                ''', since_date)
                
                return {
                    'detection_stats': dict(detection_stats) if detection_stats else {},
                    'top_skipped': [dict(row) for row in top_skipped],
                    'system_stats': [dict(row) for row in system_stats],
                    'ticker_stats': [dict(row) for row in ticker_stats],
                    'period_days': days
                }
                
        except Exception as e:
            self.logger.error(f"❌ Error getting priority analytics: {e}")
            return {}
    
    async def get_signal_utilization_report(self) -> Dict:
        """Get comprehensive signal utilization analysis"""
        try:
            async with self.pool.acquire() as conn:
                # Last 24 hours analysis
                since_24h = datetime.now() - timedelta(hours=24)
                
                # Signal type utilization
                signal_type_stats = await conn.fetch('''
                    SELECT 
                        signal_type,
                        COUNT(*) as detected,
                        COUNT(*) FILTER (WHERE was_sent = true) as sent,
                        AVG(priority_score) as avg_priority,
                        COUNT(*) FILTER (WHERE priority_score >= 70) as high_priority
                    FROM signals_detected 
                    WHERE detected_at >= $1
                    GROUP BY signal_type
                    ORDER BY detected DESC
                ''', since_24h)
                
                # Timeframe utilization
                timeframe_stats = await conn.fetch('''
                    SELECT 
                        timeframe,
                        COUNT(*) as detected,
                        COUNT(*) FILTER (WHERE was_sent = true) as sent,
                        AVG(priority_score) as avg_priority
                    FROM signals_detected 
                    WHERE detected_at >= $1
                    GROUP BY timeframe
                    ORDER BY detected DESC
                ''', since_24h)
                
                # System utilization
                system_utilization = await conn.fetch('''
                    SELECT 
                        system,
                        COUNT(*) as detected,
                        COUNT(*) FILTER (WHERE was_sent = true) as sent,
                        COUNT(*) FILTER (WHERE skip_reason LIKE '%priority%') as skipped_priority,
                        COUNT(*) FILTER (WHERE skip_reason LIKE '%duplicate%') as skipped_duplicate,
                        AVG(priority_score) as avg_priority
                    FROM signals_detected 
                    WHERE detected_at >= $1
                    GROUP BY system
                    ORDER BY detected DESC
                ''', since_24h)
                
                # Opportunity analysis - high priority signals we skipped
                missed_opportunities = await conn.fetch('''
                    SELECT 
                        ticker, timeframe, signal_type, system, priority_score, skip_reason,
                        detected_at
                    FROM signals_detected 
                    WHERE detected_at >= $1 
                        AND was_sent = false 
                        AND priority_score >= 60
                    ORDER BY priority_score DESC
                    LIMIT 20
                ''', since_24h)
                
                return {
                    'signal_type_stats': [dict(row) for row in signal_type_stats],
                    'timeframe_stats': [dict(row) for row in timeframe_stats],
                    'system_utilization': [dict(row) for row in system_utilization],
                    'missed_opportunities': [dict(row) for row in missed_opportunities],
                    'analysis_period': '24 hours'
                }
                
        except Exception as e:
            self.logger.error(f"❌ Error getting utilization report: {e}")
            return {}
    
    async def save_priority_config(self, config_name: str, min_priority_level: str,
                                 critical_threshold: int, high_threshold: int,
                                 medium_threshold: int, low_threshold: int,
                                 vip_tickers: List[str], vip_timeframes: List[str]) -> bool:
        """Save priority configuration to database"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO priority_config 
                    (config_name, min_priority_level, critical_threshold, high_threshold,
                     medium_threshold, low_threshold, vip_tickers, vip_timeframes)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (config_name)
                    DO UPDATE SET
                        min_priority_level = EXCLUDED.min_priority_level,
                        critical_threshold = EXCLUDED.critical_threshold,
                        high_threshold = EXCLUDED.high_threshold,
                        medium_threshold = EXCLUDED.medium_threshold,
                        low_threshold = EXCLUDED.low_threshold,
                        vip_tickers = EXCLUDED.vip_tickers,
                        vip_timeframes = EXCLUDED.vip_timeframes,
                        updated_at = NOW()
                ''', config_name, min_priority_level, critical_threshold, high_threshold,
                     medium_threshold, low_threshold, vip_tickers, vip_timeframes)
                
                return True
                
        except Exception as e:
            self.logger.error(f"❌ Error saving priority config: {e}")
            return False
    
    async def load_priority_config(self, config_name: str = 'default') -> Optional[Dict]:
        """Load priority configuration from database"""
        try:
            async with self.pool.acquire() as conn:
                config = await conn.fetchrow('''
                    SELECT * FROM priority_config 
                    WHERE config_name = $1 AND is_active = true
                ''', config_name)
                
                return dict(config) if config else None
                
        except Exception as e:
            self.logger.error(f"❌ Error loading priority config: {e}")
            return None
    
    async def get_recent_notifications(self, hours: int = 24) -> List[Dict]:
        """Get notifications sent in the last N hours"""
        try:
            async with self.pool.acquire() as conn:
                since_time = datetime.now() - timedelta(hours=hours)
                
                rows = await conn.fetch('''
                    SELECT ticker, timeframe, signal_type, signal_date, 
                           notified_at, strength, system, priority_score, priority_level
                    FROM signal_notifications 
                    WHERE notified_at >= $1
                    ORDER BY notified_at DESC
                ''', since_time)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            self.logger.error(f"❌ Error getting recent notifications: {e}")
            return []
    
    async def cleanup_old_notifications(self, days: int = 30) -> int:
        """Clean up notifications older than N days"""
        try:
            async with self.pool.acquire() as conn:
                cutoff_date = datetime.now() - timedelta(days=days)
                
                # Clean up notifications
                result1 = await conn.execute('''
                    DELETE FROM signal_notifications 
                    WHERE notified_at < $1
                ''', cutoff_date)
                
                # Clean up detected signals
                result2 = await conn.execute('''
                    DELETE FROM signals_detected 
                    WHERE detected_at < $1
                ''', cutoff_date)
                
                deleted_count = int(result1.split()[-1]) + int(result2.split()[-1])
                self.logger.info(f"🧹 Cleaned up {deleted_count} old signal records")
                return deleted_count
                
        except Exception as e:
            self.logger.error(f"❌ Error cleaning up notifications: {e}")
            return 0
    
    async def get_notification_stats(self) -> Dict:
        """Get enhanced statistics about notifications and signal detection"""
        try:
            async with self.pool.acquire() as conn:
                # Total notifications
                total = await conn.fetchval('SELECT COUNT(*) FROM signal_notifications')
                
                # Last 24 hours notifications
                since_24h = datetime.now() - timedelta(hours=24)
                last_24h = await conn.fetchval('''
                    SELECT COUNT(*) FROM signal_notifications 
                    WHERE notified_at >= $1
                ''', since_24h)
                
                # Last 7 days
                since_7d = datetime.now() - timedelta(days=7)
                last_7d = await conn.fetchval('''
                    SELECT COUNT(*) FROM signal_notifications 
                    WHERE notified_at >= $1
                ''', since_7d)
                
                # Total signals detected (sent + skipped)
                total_detected = await conn.fetchval('SELECT COUNT(*) FROM signals_detected')
                
                # Detection vs notification ratio
                detected_24h = await conn.fetchval('''
                    SELECT COUNT(*) FROM signals_detected 
                    WHERE detected_at >= $1
                ''', since_24h)
                
                # Priority distribution
                priority_dist = await conn.fetchrow('''
                    SELECT 
                        COUNT(*) FILTER (WHERE priority_level = 'CRITICAL') as critical,
                        COUNT(*) FILTER (WHERE priority_level = 'HIGH') as high,
                        COUNT(*) FILTER (WHERE priority_level = 'MEDIUM') as medium,
                        COUNT(*) FILTER (WHERE priority_level = 'LOW') as low,
                        COUNT(*) FILTER (WHERE priority_level = 'MINIMAL') as minimal
                    FROM signals_detected 
                    WHERE detected_at >= $1
                ''', since_24h)
                
                # Most active ticker
                most_active = await conn.fetchrow('''
                    SELECT ticker, COUNT(*) as count 
                    FROM signal_notifications 
                    GROUP BY ticker 
                    ORDER BY count DESC 
                    LIMIT 1
                ''')
                
                # Most common signal type
                most_common = await conn.fetchrow('''
                    SELECT signal_type, COUNT(*) as count 
                    FROM signal_notifications 
                    GROUP BY signal_type 
                    ORDER BY count DESC 
                    LIMIT 1
                ''')
                
                return {
                    'total_notifications': total,
                    'total_detected': total_detected,
                    'last_24h': last_24h,
                    'last_7d': last_7d,
                    'detected_24h': detected_24h,
                    'utilization_rate_24h': round((last_24h / max(detected_24h, 1)) * 100, 1),
                    'priority_distribution': dict(priority_dist) if priority_dist else {},
                    'most_active_ticker': dict(most_active) if most_active else None,
                    'most_common_signal': dict(most_common) if most_common else None
                }
                
        except Exception as e:
            self.logger.error(f"❌ Error getting stats: {e}")
            return {}
    
    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            self.logger.info("📤 Database connection closed")

# Global database manager instance
db_manager = DatabaseManager()

async def init_database():
    """Initialize database connection"""
    return await db_manager.initialize()

async def check_duplicate(ticker: str, timeframe: str, signal_type: str, signal_date: str) -> bool:
    """Check if we've already sent this notification"""
    return await db_manager.check_duplicate_notification(ticker, timeframe, signal_type, signal_date)

async def record_notification(ticker: str, timeframe: str, signal_type: str, signal_date: str,
                            strength: str = None, system: str = None, discord_message_id: int = None,
                            priority_score: int = 0, priority_level: str = 'MEDIUM',
                            was_vip_ticker: bool = False, was_vip_timeframe: bool = False,
                            urgency_bonus: int = 0, pattern_bonus: int = 0) -> bool:
    """Record a sent notification with priority data"""
    return await db_manager.record_notification(ticker, timeframe, signal_type, signal_date, 
                                              strength, system, discord_message_id, priority_score,
                                              priority_level, was_vip_ticker, was_vip_timeframe,
                                              urgency_bonus, pattern_bonus)

async def record_detected_signal(ticker: str, timeframe: str, signal_type: str, signal_date: str,
                               strength: str, system: str, priority_score: int, priority_level: str,
                               was_sent: bool, skip_reason: str = None, signal_data: dict = None) -> bool:
    """Record every detected signal"""
    return await db_manager.record_detected_signal(ticker, timeframe, signal_type, signal_date,
                                                  strength, system, priority_score, priority_level,
                                                  was_sent, skip_reason, signal_data)

async def get_stats() -> Dict:
    """Get notification statistics"""
    return await db_manager.get_notification_stats()

async def get_priority_analytics(days: int = 7) -> Dict:
    """Get priority system analytics"""
    return await db_manager.get_priority_analytics(days)

async def get_signal_utilization() -> Dict:
    """Get signal utilization report"""
    return await db_manager.get_signal_utilization_report()

async def cleanup_old(days: int = 30) -> int:
    """Clean up old notification entries"""
    return await db_manager.cleanup_old_notifications(days) 