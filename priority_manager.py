#!/usr/bin/env python3
"""
Priority Management System for Discord Signal Bot
Handles priority scoring, filtering, and ranking of trading signals.
"""

import os
from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import re

class SignalPriority(Enum):
    """Signal priority levels"""
    CRITICAL = 5      # Must notify immediately
    HIGH = 4          # Very important signals
    MEDIUM = 3        # Standard importance
    LOW = 2           # Less important
    MINIMAL = 1       # Only for completeness

class SignalUrgency(Enum):
    """Signal urgency based on timing"""
    IMMEDIATE = 5     # Real-time/just happened
    RECENT = 4        # Within last hour
    CURRENT = 3       # Within last 4 hours
    STALE = 2         # Within last day
    OLD = 1           # Older than a day

@dataclass
class PriorityScore:
    """Priority scoring breakdown"""
    base_score: int
    strength_bonus: int
    system_bonus: int
    ticker_bonus: int
    timeframe_bonus: int
    urgency_bonus: int
    pattern_bonus: int
    total_score: int
    priority_level: SignalPriority

class SignalPriorityManager:
    """Manages signal priority scoring and filtering"""
    
    def __init__(self):
        self.load_priority_config()
    
    def load_priority_config(self):
        """Load priority configuration from environment variables"""
        # Priority thresholds
        self.CRITICAL_THRESHOLD = int(os.getenv('PRIORITY_CRITICAL_THRESHOLD', '90'))
        self.HIGH_THRESHOLD = int(os.getenv('PRIORITY_HIGH_THRESHOLD', '70'))
        self.MEDIUM_THRESHOLD = int(os.getenv('PRIORITY_MEDIUM_THRESHOLD', '50'))
        self.LOW_THRESHOLD = int(os.getenv('PRIORITY_LOW_THRESHOLD', '30'))
        
        # Minimum priority level to send notifications
        self.MIN_PRIORITY_LEVEL = os.getenv('MIN_PRIORITY_LEVEL', 'MEDIUM')
        
        # High-priority tickers (get bonus points)
        self.VIP_TICKERS = set(os.getenv('VIP_TICKERS', 'SPY,QQQ,AAPL,TSLA,NVDA').split(','))
        
        # High-priority timeframes
        self.VIP_TIMEFRAMES = set(os.getenv('VIP_TIMEFRAMES', '1d,4h').split(','))
        
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
        
        # Signal strength weights
        self.STRENGTH_WEIGHTS = {
            'Very Strong': 25,
            'Strong': 20,
            'Moderate': 15,
            'Medium': 10,
            'Weak': 5,
            'Unknown': 0
        }
        
        # Signal type patterns and their importance
        self.SIGNAL_PATTERNS = {
            # Critical patterns
            'Gold Buy Signal': 30,
            'Zero Line Reject': 25,
            'Extreme Oversold': 25,
            'Extreme Overbought': 25,
            
            # High importance patterns
            'Fast Money': 20,
            'Bullish Divergence': 18,
            'Bearish Divergence': 18,
            'Hidden.*Divergence': 15,
            
            # Medium importance
            'WT.*Signal': 12,
            'RSI3M3.*Entry': 12,
            'Trend Break': 10,
            
            # Lower importance
            'Cross': 8,
            'Reversal': 6
        }
    
    def calculate_urgency(self, signal_date: str) -> SignalUrgency:
        """Calculate signal urgency based on timing"""
        try:
            if ' ' in signal_date:
                signal_datetime = datetime.strptime(signal_date, '%Y-%m-%d %H:%M:%S')
            else:
                signal_datetime = datetime.strptime(signal_date, '%Y-%m-%d')
                # Assume market open time for date-only signals
                signal_datetime = signal_datetime.replace(hour=9, minute=30)
            
            now = datetime.now()
            time_diff = now - signal_datetime
            
            if time_diff.total_seconds() < 300:  # 5 minutes
                return SignalUrgency.IMMEDIATE
            elif time_diff.total_seconds() < 3600:  # 1 hour
                return SignalUrgency.RECENT
            elif time_diff.total_seconds() < 14400:  # 4 hours
                return SignalUrgency.CURRENT
            elif time_diff.total_seconds() < 86400:  # 24 hours
                return SignalUrgency.STALE
            else:
                return SignalUrgency.OLD
                
        except Exception:
            return SignalUrgency.STALE
    
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
            priority_level = SignalPriority.CRITICAL
        elif total_score >= self.HIGH_THRESHOLD:
            priority_level = SignalPriority.HIGH
        elif total_score >= self.MEDIUM_THRESHOLD:
            priority_level = SignalPriority.MEDIUM
        elif total_score >= self.LOW_THRESHOLD:
            priority_level = SignalPriority.LOW
        else:
            priority_level = SignalPriority.MINIMAL
        
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
    
    def should_notify(self, signal: Dict, ticker: str, timeframe: str) -> Tuple[bool, PriorityScore]:
        """Determine if signal should trigger notification based on priority"""
        priority_score = self.calculate_priority_score(signal, ticker, timeframe)
        
        # Check against minimum priority level
        min_priority = getattr(SignalPriority, self.MIN_PRIORITY_LEVEL, SignalPriority.MEDIUM)
        should_send = priority_score.priority_level.value >= min_priority.value
        
        return should_send, priority_score
    
    def rank_signals(self, signals: List[Tuple[Dict, str, str]]) -> List[Tuple[Dict, str, str, PriorityScore]]:
        """Rank signals by priority score (highest first)"""
        scored_signals = []
        
        for signal, ticker, timeframe in signals:
            priority_score = self.calculate_priority_score(signal, ticker, timeframe)
            scored_signals.append((signal, ticker, timeframe, priority_score))
        
        # Sort by total score (descending)
        scored_signals.sort(key=lambda x: x[3].total_score, reverse=True)
        
        return scored_signals
    
    def filter_by_priority(self, signals: List[Tuple[Dict, str, str]], 
                          min_priority: SignalPriority = None) -> List[Tuple[Dict, str, str, PriorityScore]]:
        """Filter signals by minimum priority level"""
        if min_priority is None:
            min_priority = getattr(SignalPriority, self.MIN_PRIORITY_LEVEL, SignalPriority.MEDIUM)
        
        filtered_signals = []
        
        for signal, ticker, timeframe in signals:
            priority_score = self.calculate_priority_score(signal, ticker, timeframe)
            if priority_score.priority_level.value >= min_priority.value:
                filtered_signals.append((signal, ticker, timeframe, priority_score))
        
        return filtered_signals
    
    def get_priority_summary(self, signals: List[Tuple[Dict, str, str]]) -> Dict:
        """Get summary of signal priorities"""
        priority_counts = {level.name: 0 for level in SignalPriority}
        total_signals = len(signals)
        
        if total_signals == 0:
            return priority_counts
        
        for signal, ticker, timeframe in signals:
            priority_score = self.calculate_priority_score(signal, ticker, timeframe)
            priority_counts[priority_score.priority_level.name] += 1
        
        # Add percentages
        for level in priority_counts:
            count = priority_counts[level]
            priority_counts[f"{level}_PCT"] = round((count / total_signals) * 100, 1) if total_signals > 0 else 0
        
        return priority_counts
    
    def format_priority_for_discord(self, priority_score: PriorityScore) -> str:
        """Format priority information for Discord display"""
        priority_emojis = {
            SignalPriority.CRITICAL: '🚨🔥',
            SignalPriority.HIGH: '⚠️🔥',
            SignalPriority.MEDIUM: '📊⭐',
            SignalPriority.LOW: '📢💙',
            SignalPriority.MINIMAL: '📝💚'
        }
        
        emoji = priority_emojis.get(priority_score.priority_level, '📊')
        
        return f"{emoji} **Priority:** {priority_score.priority_level.name} ({priority_score.total_score})"
    
    def get_debug_breakdown(self, priority_score: PriorityScore) -> str:
        """Get detailed priority score breakdown for debugging"""
        return f"""
**Priority Score Breakdown:**
• Base Score: {priority_score.base_score}
• Strength Bonus: +{priority_score.strength_bonus}
• System Bonus: +{priority_score.system_bonus}
• Ticker Bonus: +{priority_score.ticker_bonus}
• Timeframe Bonus: +{priority_score.timeframe_bonus}
• Urgency Bonus: +{priority_score.urgency_bonus}
• Pattern Bonus: +{priority_score.pattern_bonus}
**Total Score: {priority_score.total_score}**
**Priority Level: {priority_score.priority_level.name}**
        """.strip()

# Global priority manager instance
priority_manager = SignalPriorityManager()

# Convenience functions for integration
def calculate_signal_priority(signal: Dict, ticker: str, timeframe: str) -> PriorityScore:
    """Calculate priority score for a signal"""
    return priority_manager.calculate_priority_score(signal, ticker, timeframe)

def should_send_notification(signal: Dict, ticker: str, timeframe: str) -> Tuple[bool, PriorityScore]:
    """Check if signal should trigger notification"""
    return priority_manager.should_notify(signal, ticker, timeframe)

def rank_signals_by_priority(signals: List[Tuple[Dict, str, str]]) -> List[Tuple[Dict, str, str, PriorityScore]]:
    """Rank signals by priority (highest first)"""
    return priority_manager.rank_signals(signals)

def get_priority_display(priority_score: PriorityScore) -> str:
    """Get priority display for Discord"""
    return priority_manager.format_priority_for_discord(priority_score) 