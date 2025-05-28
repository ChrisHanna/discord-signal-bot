#!/usr/bin/env python3
"""
Priority Management System for Discord Signal Bot
Manages signal priority scoring and filtering with database-backed configuration
"""

import os
import re
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple

# ✅ NEW: Database-first priority configuration
class DatabasePriorityConfig:
    """Manage priority configuration using PostgreSQL database as single source of truth"""
    
    def __init__(self):
        # Default values (used if database is unavailable)
        self.config_name = 'default'
        self.min_priority_level = 'MEDIUM'
        self.critical_threshold = 90
        self.high_threshold = 70
        self.medium_threshold = 50
        self.low_threshold = 30
        self.vip_tickers = set(['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA'])
        self.vip_timeframes = set(['1d', '4h'])
        
    async def load_from_database(self, config_name: str = 'default') -> bool:
        """Load priority configuration from PostgreSQL database"""
        try:
            from database import db_manager
            
            print(f"🎯 Loading priority configuration from database: {config_name}")
            
            async with db_manager.pool.acquire() as conn:
                config_row = await conn.fetchrow('''
                    SELECT * FROM priority_config 
                    WHERE config_name = $1 AND is_active = true
                ''', config_name)
                
                if config_row:
                    # Load from database
                    self.config_name = config_row['config_name']
                    self.min_priority_level = config_row['min_priority_level']
                    self.critical_threshold = config_row['critical_threshold']
                    self.high_threshold = config_row['high_threshold']
                    self.medium_threshold = config_row['medium_threshold']
                    self.low_threshold = config_row['low_threshold']
                    
                    # Convert database arrays to sets
                    self.vip_tickers = set(config_row['vip_tickers'] or [])
                    self.vip_timeframes = set(config_row['vip_timeframes'] or [])
                    
                    print(f"✅ Loaded priority config from database:")
                    print(f"   Min Priority Level: {self.min_priority_level}")
                    print(f"   VIP Tickers: {sorted(self.vip_tickers)}")
                    print(f"   VIP Timeframes: {sorted(self.vip_timeframes)}")
                    return True
                else:
                    # Create default configuration in database
                    print(f"📊 Creating default priority configuration in database")
                    await self.save_to_database()
                    return True
                    
        except Exception as e:
            print(f"❌ Error loading priority config from database: {e}")
            self.load_from_environment()
            return False
    
    def load_from_environment(self):
        """Fallback: Load configuration from environment variables"""
        print("⚠️ Falling back to environment variable priority configuration")
        
        # Load thresholds from environment
        self.critical_threshold = int(os.getenv('PRIORITY_CRITICAL_THRESHOLD', '90'))
        self.high_threshold = int(os.getenv('PRIORITY_HIGH_THRESHOLD', '70'))
        self.medium_threshold = int(os.getenv('PRIORITY_MEDIUM_THRESHOLD', '50'))
        self.low_threshold = int(os.getenv('PRIORITY_LOW_THRESHOLD', '30'))
        
        # Minimum priority level to send notifications
        self.min_priority_level = os.getenv('MIN_PRIORITY_LEVEL', 'MEDIUM')
        
        # Load VIP tickers from environment
        env_vip_tickers = os.getenv('VIP_TICKERS', 'SPY,QQQ,AAPL,TSLA,NVDA').split(',')
        self.vip_tickers = set(ticker.strip().upper() for ticker in env_vip_tickers if ticker.strip())
        
        # Load VIP timeframes from environment
        env_vip_timeframes = os.getenv('VIP_TIMEFRAMES', '1d,4h').split(',')
        self.vip_timeframes = set(tf.strip() for tf in env_vip_timeframes if tf.strip())
        
        print(f"📊 Loaded from environment: {len(self.vip_tickers)} VIP tickers, {len(self.vip_timeframes)} VIP timeframes")
    
    async def save_to_database(self, config_name: str = None) -> bool:
        """Save current configuration to database"""
        try:
            from database import db_manager
            
            config_name = config_name or self.config_name
            
            async with db_manager.pool.acquire() as conn:
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
                ''', config_name, self.min_priority_level, self.critical_threshold,
                     self.high_threshold, self.medium_threshold, self.low_threshold,
                     list(self.vip_tickers), list(self.vip_timeframes))
                
                print(f"💾 Saved priority configuration to database: {config_name}")
                return True
                
        except Exception as e:
            print(f"❌ Error saving priority config to database: {e}")
            return False
    
    async def add_vip_ticker(self, ticker: str) -> bool:
        """Add VIP ticker and save to database"""
        ticker = ticker.upper().strip()
        if ticker not in self.vip_tickers:
            self.vip_tickers.add(ticker)
            return await self.save_to_database()
        return True
    
    async def remove_vip_ticker(self, ticker: str) -> bool:
        """Remove VIP ticker and save to database"""
        ticker = ticker.upper().strip()
        if ticker in self.vip_tickers:
            self.vip_tickers.discard(ticker)
            return await self.save_to_database()
        return True
    
    async def set_min_priority_level(self, level: str) -> bool:
        """Set minimum priority level and save to database"""
        valid_levels = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'MINIMAL']
        if level.upper() in valid_levels:
            self.min_priority_level = level.upper()
            return await self.save_to_database()
        return False

class PriorityLevel(Enum):
    MINIMAL = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    CRITICAL = 5

class Urgency(Enum):
    ANCIENT = 0    # More than 1 day old
    OLD = 1        # 4-24 hours old
    MODERATE = 2   # 1-4 hours old
    RECENT = 3     # 15 minutes - 1 hour old
    IMMEDIATE = 4  # Within 15 minutes

@dataclass
class PriorityScore:
    base_score: int
    strength_bonus: int
    system_bonus: int
    ticker_bonus: int
    timeframe_bonus: int
    urgency_bonus: int
    pattern_bonus: int
    total_score: int
    priority_level: PriorityLevel

class SignalPriorityManager:
    """Manages signal priority scoring and filtering using database configuration"""
    
    def __init__(self):
        # ✅ NEW: Use database-backed configuration
        self.db_config = DatabasePriorityConfig()
        
        # System priority weights
        self.SYSTEM_WEIGHTS = {
            'Wave Trend': 20,
            'RSI3M3+': 18,
            'Divergence Detection': 16,
            'Fast Money': 14,
            'Trend Exhaustion': 12,
            'RSI Trend Break': 10,
            'Zero Line': 8,
            'Default': 5
        }
        
        # Strength multipliers
        self.STRENGTH_WEIGHTS = {
            'Very Strong': 25,
            'Strong': 20,
            'Moderate': 10,
            'Weak': 5
        }
        
        # Signal pattern bonuses
        self.SIGNAL_PATTERNS = {
            r'gold|extreme': 30,      # Gold signals, extreme conditions
            r'fast money': 25,        # Fast Money patterns
            r'divergence': 20,        # Divergence signals
            r'breakout|breakdown': 15, # Price breakouts/breakdowns
            r'reversal': 12,          # Reversal patterns
            r'cross': 8               # Simple crosses
        }
    
    async def initialize(self):
        """Initialize priority manager with database configuration"""
        success = await self.db_config.load_from_database()
        if success:
            print("✅ Priority manager initialized with database configuration")
        else:
            print("⚠️ Priority manager initialized with environment fallback")
        return success
    
    # ✅ NEW: Properties that reference database config
    @property
    def CRITICAL_THRESHOLD(self) -> int:
        return self.db_config.critical_threshold
    
    @property 
    def HIGH_THRESHOLD(self) -> int:
        return self.db_config.high_threshold
    
    @property
    def MEDIUM_THRESHOLD(self) -> int:
        return self.db_config.medium_threshold
    
    @property
    def LOW_THRESHOLD(self) -> int:
        return self.db_config.low_threshold
    
    @property
    def MIN_PRIORITY_LEVEL(self) -> str:
        return self.db_config.min_priority_level
    
    @property
    def VIP_TICKERS(self) -> Set[str]:
        return self.db_config.vip_tickers
    
    @property
    def VIP_TIMEFRAMES(self) -> Set[str]:
        return self.db_config.vip_timeframes
    
    # ✅ SIMPLIFIED: Database management methods
    async def add_vip_ticker(self, ticker: str) -> bool:
        """Add VIP ticker"""
        return await self.db_config.add_vip_ticker(ticker)
    
    async def remove_vip_ticker(self, ticker: str) -> bool:
        """Remove VIP ticker"""
        return await self.db_config.remove_vip_ticker(ticker)
    
    async def set_min_priority_level(self, level: str) -> bool:
        """Set minimum priority level"""
        return await self.db_config.set_min_priority_level(level)
    
    async def reload_from_database(self) -> bool:
        """Reload configuration from database"""
        return await self.db_config.load_from_database()
    
    def calculate_urgency(self, signal_date: str) -> Urgency:
        """Calculate urgency based on signal date"""
        if not signal_date:
            return Urgency.ANCIENT
        
        try:
            if ' ' in signal_date:
                signal_time = datetime.strptime(signal_date, '%Y-%m-%d %H:%M:%S')
            else:
                signal_time = datetime.strptime(signal_date, '%Y-%m-%d')
            
            time_diff = datetime.now() - signal_time
            hours_ago = time_diff.total_seconds() / 3600
            
            if hours_ago <= 0.25:      # Within 15 minutes
                return Urgency.IMMEDIATE
            elif hours_ago <= 1:       # Within 1 hour
                return Urgency.RECENT
            elif hours_ago <= 4:       # Within 4 hours
                return Urgency.MODERATE
            elif hours_ago <= 24:      # Within 24 hours
                return Urgency.OLD
            else:                      # More than 24 hours
                return Urgency.ANCIENT
                
        except (ValueError, TypeError):
            return Urgency.ANCIENT

    def calculate_priority_score(self, signal: Dict, ticker: str, timeframe: str) -> PriorityScore:
        """Calculate comprehensive priority score for a signal"""
        
        # Base score
        base_score = 10
        
        # Strength bonus
        strength = signal.get('strength', 'Unknown')
        strength_bonus = self.STRENGTH_WEIGHTS.get(strength, 0)
        
        # System bonus
        system = signal.get('system', 'Unknown')
        system_bonus = 0
        for system_name, weight in self.SYSTEM_WEIGHTS.items():
            if system_name.lower() in system.lower():
                system_bonus = weight
                break
        if system_bonus == 0:
            system_bonus = self.SYSTEM_WEIGHTS['Default']
        
        # Ticker bonus (VIP tickers get priority)
        ticker_bonus = 15 if ticker in self.VIP_TICKERS else 0
        
        # Timeframe bonus
        timeframe_bonus = 10 if timeframe in self.VIP_TIMEFRAMES else 0
        
        # Urgency bonus
        urgency = self.calculate_urgency(signal.get('date', ''))
        urgency_bonus = urgency.value * 4
        
        # Pattern bonus (based on signal type)
        signal_type = signal.get('type', '')
        pattern_bonus = 0
        for pattern, bonus in self.SIGNAL_PATTERNS.items():
            if re.search(pattern, signal_type, re.IGNORECASE):
                pattern_bonus = max(pattern_bonus, bonus)
        
        # Calculate total score
        total_score = (base_score + strength_bonus + system_bonus + 
                      ticker_bonus + timeframe_bonus + urgency_bonus + pattern_bonus)
        
        # Determine priority level
        if total_score >= self.CRITICAL_THRESHOLD:
            priority_level = PriorityLevel.CRITICAL
        elif total_score >= self.HIGH_THRESHOLD:
            priority_level = PriorityLevel.HIGH
        elif total_score >= self.MEDIUM_THRESHOLD:
            priority_level = PriorityLevel.MEDIUM
        elif total_score >= self.LOW_THRESHOLD:
            priority_level = PriorityLevel.LOW
        else:
            priority_level = PriorityLevel.MINIMAL
        
        return PriorityScore(
            base_score=base_score,
            strength_bonus=strength_bonus,
            system_bonus=system_bonus,
            ticker_bonus=ticker_bonus,
            timeframe_bonus=timeframe_bonus,
            urgency_bonus=urgency_bonus,
            pattern_bonus=pattern_bonus,
            total_score=total_score,
            priority_level=priority_level
        )
    
    def should_send_notification(self, signal: Dict, ticker: str, timeframe: str) -> Tuple[bool, PriorityScore]:
        """Determine if a signal meets notification criteria"""
        priority_score = self.calculate_priority_score(signal, ticker, timeframe)
        
        # Check against minimum priority level
        min_priority = getattr(PriorityLevel, self.MIN_PRIORITY_LEVEL, PriorityLevel.MEDIUM)
        should_send = priority_score.priority_level.value >= min_priority.value
        
        return should_send, priority_score
    
    def rank_signals_by_priority(self, signals: List[Tuple[Dict, str, str]]) -> List[Tuple[Dict, str, str, PriorityScore]]:
        """Rank signals by priority score"""
        scored_signals = []
        for signal, ticker, timeframe in signals:
            priority_score = self.calculate_priority_score(signal, ticker, timeframe)
            scored_signals.append((signal, ticker, timeframe, priority_score))
        
        # Sort by total score (highest first)
        scored_signals.sort(key=lambda x: x[3].total_score, reverse=True)
        return scored_signals
    
    def filter_by_priority(self, signals: List[Tuple[Dict, str, str]], 
                          min_priority: PriorityLevel = None) -> List[Tuple[Dict, str, str, PriorityScore]]:
        """Filter signals by minimum priority level"""
        if min_priority is None:
            min_priority = getattr(PriorityLevel, self.MIN_PRIORITY_LEVEL, PriorityLevel.MEDIUM)
        
        filtered_signals = []
        for signal, ticker, timeframe in signals:
            priority_score = self.calculate_priority_score(signal, ticker, timeframe)
            if priority_score.priority_level.value >= min_priority.value:
                filtered_signals.append((signal, ticker, timeframe, priority_score))
        
        return filtered_signals
    
    def get_priority_summary(self, signals: List[Tuple[Dict, str, str]]) -> Dict:
        """Get summary of signal priorities"""
        priority_counts = {level.name: 0 for level in PriorityLevel}
        total_signals = len(signals)
        
        for signal, ticker, timeframe in signals:
            priority_score = self.calculate_priority_score(signal, ticker, timeframe)
            priority_counts[priority_score.priority_level.name] += 1
        
        return {
            'total_signals': total_signals,
            'priority_breakdown': priority_counts,
            'critical_signals': priority_counts['CRITICAL'],
            'high_signals': priority_counts['HIGH'],
            'medium_signals': priority_counts['MEDIUM'],
            'low_signals': priority_counts['LOW'],
            'minimal_signals': priority_counts['MINIMAL']
        }
    
    def get_priority_display(self, priority_score: PriorityScore) -> str:
        """Format priority information for Discord display"""
        priority_emojis = {
            PriorityLevel.CRITICAL: '🚨🔥',
            PriorityLevel.HIGH: '⚠️🔥',
            PriorityLevel.MEDIUM: '📊⭐',
            PriorityLevel.LOW: '📢💙',
            PriorityLevel.MINIMAL: '📝💚'
        }
        
        emoji = priority_emojis.get(priority_score.priority_level, '📊')
        
        return f"\n{emoji} **Priority: {priority_score.priority_level.name}** (Score: {priority_score.total_score})"
    
    def get_debug_breakdown(self, priority_score: PriorityScore) -> str:
        """Get detailed priority score breakdown for debugging"""
        return f"""
**Priority Score Breakdown:**
• Base Score: {priority_score.base_score}
• Strength Bonus: {priority_score.strength_bonus}
• System Bonus: {priority_score.system_bonus}
• Ticker Bonus: {priority_score.ticker_bonus}
• Timeframe Bonus: {priority_score.timeframe_bonus}
• Urgency Bonus: {priority_score.urgency_bonus}
• Pattern Bonus: {priority_score.pattern_bonus}
**Total: {priority_score.total_score} → {priority_score.priority_level.name}**
        """.strip()

# ✅ NEW: Global priority manager instance with database configuration
priority_manager = SignalPriorityManager()

# ✅ SIMPLIFIED: Export functions (backward compatibility)
def should_send_notification(signal: Dict, ticker: str, timeframe: str) -> Tuple[bool, PriorityScore]:
    """Determine if a signal meets notification criteria"""
    return priority_manager.should_send_notification(signal, ticker, timeframe)

def calculate_signal_priority(signal: Dict, ticker: str, timeframe: str) -> PriorityScore:
    """Calculate priority score for a signal"""
    return priority_manager.calculate_priority_score(signal, ticker, timeframe)

def rank_signals_by_priority(signals: List[Tuple[Dict, str, str]]) -> List[Tuple[Dict, str, str, PriorityScore]]:
    """Rank signals by priority score"""
    return priority_manager.rank_signals_by_priority(signals)

def get_priority_display(priority_score: PriorityScore) -> str:
    """Format priority information for Discord display"""
    return priority_manager.get_priority_display(priority_score)

# ✅ REMOVED: Old environment-based initialization
# Priority manager now uses database configuration loaded at startup 