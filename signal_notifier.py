#!/usr/bin/env python3
"""
Discord Signal Notifier
Fetches signal timeline data from your local web API and sends Discord notifications.
"""

import requests
import json
import time
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import pytz
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:5000')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '1600'))  # Default ~26 minutes
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))

# File paths
LAST_NOTIFICATION_FILE = 'last_notifications.json'
TICKERS_CONFIG_FILE = 'tickers.json'

# Timezone setup
EST = pytz.timezone('US/Eastern')

def convert_to_est(dt: datetime) -> datetime:
    """Convert datetime to EST timezone"""
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(EST)

def format_est_timestamp(timestamp_str: str, show_time: bool = True) -> str:
    """Format timestamp string to EST with readable format"""
    if not timestamp_str:
        return "N/A"
    
    try:
        # Parse the timestamp
        if ' ' in timestamp_str:
            # Full timestamp (e.g., "2025-01-27 09:30:00")
            dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        else:
            # Date only (e.g., "2025-01-27")
            dt = datetime.strptime(timestamp_str, '%Y-%m-%d')
            # Assume market open time (9:30 AM EST) for date-only signals
            dt = dt.replace(hour=9, minute=30)
        
        # Convert to EST
        dt_est = convert_to_est(dt)
        
        if show_time and ' ' in timestamp_str:
            # Show full timestamp with timezone
            return dt_est.strftime('%Y-%m-%d %I:%M:%S %p EST')
        else:
            # Show date only
            return dt_est.strftime('%Y-%m-%d EST')
            
    except (ValueError, TypeError) as e:
        print(f"⚠️ Error formatting timestamp '{timestamp_str}': {e}")
        return timestamp_str

def calculate_time_ago_est(timestamp_str: str) -> str:
    """Calculate how long ago a signal occurred in EST-friendly format"""
    if not timestamp_str:
        return "Unknown"
    
    try:
        # Parse the timestamp
        if ' ' in timestamp_str:
            dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        else:
            dt = datetime.strptime(timestamp_str, '%Y-%m-%d')
            dt = dt.replace(hour=9, minute=30)  # Assume market open
        
        # Convert both to EST for comparison
        dt_est = convert_to_est(dt)
        now_est = datetime.now(EST)
        
        # Calculate difference
        time_diff = now_est - dt_est
        
        if time_diff.days > 0:
            return f"{time_diff.days} day{'s' if time_diff.days != 1 else ''} ago"
        else:
            hours = time_diff.seconds // 3600
            minutes = (time_diff.seconds % 3600) // 60
            
            if hours > 0:
                return f"{hours}h {minutes}m ago"
            elif minutes > 0:
                return f"{minutes}m ago"
            else:
                return "Just now"
                
    except (ValueError, TypeError) as e:
        print(f"⚠️ Error calculating time ago for '{timestamp_str}': {e}")
        return "Unknown"

def load_ticker_config() -> Dict:
    """Load ticker configuration from JSON file"""
    try:
        if os.path.exists(TICKERS_CONFIG_FILE):
            with open(TICKERS_CONFIG_FILE, 'r') as f:
                return json.load(f)
        else:
            # Create default config if file doesn't exist
            default_config = {
                "tickers": ["AAPL", "TSLA", "NVDA", "SPY", "QQQ"],
                "timeframes": ["1d", "1h"],
                "settings": {
                    "max_tickers": 50,
                    "allowed_timeframes": ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"],
                    "default_timeframes": ["1d", "1h"]
                }
            }
            save_ticker_config(default_config)
            return default_config
    except Exception as e:
        print(f"❌ Error loading ticker config: {e}")
        # Return minimal fallback config
        return {
            "tickers": ["AAPL", "TSLA"],
            "timeframes": ["1d"],
            "settings": {
                "max_tickers": 50,
                "allowed_timeframes": ["1d", "1h"],
                "default_timeframes": ["1d"]
            }
        }

def save_ticker_config(config: Dict):
    """Save ticker configuration to JSON file"""
    try:
        temp_file = TICKERS_CONFIG_FILE + '.tmp'
        with open(temp_file, 'w') as f:
            json.dump(config, f, indent=4, sort_keys=True)
        
        # Atomic move
        import shutil
        shutil.move(temp_file, TICKERS_CONFIG_FILE)
        print(f"💾 Ticker configuration saved successfully")
    except Exception as e:
        print(f"❌ Error saving ticker config: {e}")

# Load initial ticker configuration
ticker_config = load_ticker_config()
TICKERS = ticker_config.get('tickers', ['AAPL', 'TSLA'])
TIMEFRAMES = ticker_config.get('timeframes', ['1d'])

# Legacy environment variable support (fallback)
if not TICKERS:
    TICKERS_STR = os.getenv('TICKERS', 'AAPL,TSLA,NVDA,SPY,QQQ')
    TICKERS = [ticker.strip().upper() for ticker in TICKERS_STR.split(',') if ticker.strip()]

if not TIMEFRAMES:
    TIMEFRAMES_STR = os.getenv('TIMEFRAMES', '1d')
    TIMEFRAMES = [tf.strip() for tf in TIMEFRAMES_STR.split(',') if tf.strip()]

# Advanced per-ticker timeframes (overrides TIMEFRAMES if set)
TICKER_TIMEFRAMES_STR = os.getenv('TICKER_TIMEFRAMES', '')
TICKER_TIMEFRAMES = {}

if TICKER_TIMEFRAMES_STR:
    # Parse format like "AAPL:1d,TSLA:1h,BTC-USD:15m"
    for item in TICKER_TIMEFRAMES_STR.split(','):
        if ':' in item:
            ticker, timeframe = item.split(':', 1)
            TICKER_TIMEFRAMES[ticker.strip().upper()] = timeframe.strip()

# Build the final ticker-timeframe combinations
def build_ticker_combinations():
    """Build ticker-timeframe combinations from current config"""
    global TICKER_TF_COMBINATIONS
    TICKER_TF_COMBINATIONS = []
    
    if TICKER_TIMEFRAMES:
        # Use per-ticker timeframes
        for ticker, timeframe in TICKER_TIMEFRAMES.items():
            TICKER_TF_COMBINATIONS.append((ticker, timeframe))
        print(f"📊 Using per-ticker timeframes: {TICKER_TIMEFRAMES}")
    else:
        # Use simple multi-timeframe (all tickers on all timeframes)
        for ticker in TICKERS:
            for timeframe in TIMEFRAMES:
                TICKER_TF_COMBINATIONS.append((ticker, timeframe))
        print(f"📊 Using multi-timeframe: {len(TICKERS)} tickers × {len(TIMEFRAMES)} timeframes = {len(TICKER_TF_COMBINATIONS)} combinations")

# Initial build
build_ticker_combinations()

MAX_SIGNAL_AGE_DAYS = int(os.getenv('MAX_SIGNAL_AGE_DAYS', '1'))
ONLY_STRONG_SIGNALS = os.getenv('ONLY_STRONG_SIGNALS', 'false').lower() == 'true'

print(f"📊 Loaded configuration:")
print(f"   Ticker-Timeframe Combinations: {len(TICKER_TF_COMBINATIONS)}")
for ticker, tf in TICKER_TF_COMBINATIONS:
    print(f"   • {ticker} ({tf})")
print(f"   Max signal age: {MAX_SIGNAL_AGE_DAYS} days")
print(f"   Strong signals only: {ONLY_STRONG_SIGNALS}")

# Global timer tracking for bot commands
loop_start_time = None
checks_completed = 0
bot_start_time = None
last_successful_check = None
health_stats = {
    'total_signals_found': 0,
    'total_notifications_sent': 0,
    'failed_checks': 0,
    'api_errors': 0,
    'discord_errors': 0
}

class SignalNotifier:
    def __init__(self, bot):
        self.bot = bot
        self.last_notifications = self.load_last_notifications()
        
    def load_last_notifications(self) -> Dict:
        """Load the last notification timestamps from file with cleanup"""
        try:
            if os.path.exists(LAST_NOTIFICATION_FILE):
                with open(LAST_NOTIFICATION_FILE, 'r') as f:
                    data = json.load(f)
                
                # Clean up old entries (older than 7 days) to prevent infinite growth
                current_time = datetime.now()
                cleaned_data = {}
                cleaned_count = 0
                
                for key, timestamp_str in data.items():
                    try:
                        # Try to parse as ISO format first (new format)
                        if 'T' in timestamp_str:
                            timestamp = datetime.fromisoformat(timestamp_str)
                        else:
                            # Handle old format (date only) - assume it's from today
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d')
                        
                        # Keep entries that are less than 7 days old
                        if (current_time - timestamp).days < 7:
                            cleaned_data[key] = timestamp_str
                        else:
                            cleaned_count += 1
                    except (ValueError, TypeError):
                        # Remove malformed entries
                        cleaned_count += 1
                        continue
                
                if cleaned_count > 0:
                    print(f"🧹 Cleaned up {cleaned_count} old notification entries")
                    # Save the cleaned data back to file
                    self._save_notifications_atomic(cleaned_data)
                
                return cleaned_data
        except Exception as e:
            print(f"⚠️ Error loading last notifications: {e}")
        return {}
    
    def _save_notifications_atomic(self, data: Dict):
        """Save notifications with atomic write to prevent corruption"""
        temp_file = LAST_NOTIFICATION_FILE + '.tmp'
        try:
            # Write to temporary file first
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2, sort_keys=True)
            
            # Atomic move (rename) - this is atomic on most filesystems
            import shutil
            shutil.move(temp_file, LAST_NOTIFICATION_FILE)
            
        except Exception as e:
            print(f"❌ Error saving notifications atomically: {e}")
            # Clean up temp file if it exists
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
    
    def save_last_notifications(self):
        """Save the last notification timestamps to file with atomic write"""
        try:
            self._save_notifications_atomic(self.last_notifications)
        except Exception as e:
            print(f"❌ Error saving last notifications: {e}")
    
    def cleanup_old_notifications(self):
        """Manually trigger cleanup of old notifications (can be called periodically)"""
        current_time = datetime.now()
        cleaned_data = {}
        cleaned_count = 0
        
        for key, timestamp_str in self.last_notifications.items():
            try:
                if 'T' in timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str)
                else:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d')
                
                # Keep entries that are less than 7 days old
                if (current_time - timestamp).days < 7:
                    cleaned_data[key] = timestamp_str
                else:
                    cleaned_count += 1
            except (ValueError, TypeError):
                cleaned_count += 1
                continue
        
        if cleaned_count > 0:
            print(f"🧹 Cleaned up {cleaned_count} old notification entries from memory")
            self.last_notifications = cleaned_data
            self.save_last_notifications()
        
        return cleaned_count
    
    def fetch_signal_timeline(self, ticker: str, timeframe: str = '1d') -> Optional[List[Dict]]:
        """Fetch signal timeline data from your web API"""
        try:
            print(f"🔍 Fetching signals for {ticker} ({timeframe})...")
            
            # Set period based on timeframe for optimal data coverage
            if timeframe == '1d':
                period = '1y'  # 1 year for daily data
            elif timeframe == '1h':
                period = '1mo'  # 1 month for hourly data
            elif timeframe in ['15m', '30m', '5m']:
                period = '1wk'  # 1 week for intraday timeframes (faster + more relevant)
            elif timeframe in ['4h', '2h']:
                period = '3mo'  # 3 months for medium timeframes
            else:
                period = '1mo'  # Default fallback (1 month)
            
            # Call your existing API endpoint with interval parameter (not timeframe)
            # Also add period parameter for better data retrieval
            params = {
                'ticker': ticker,
                'interval': timeframe,  # Fixed: API expects 'interval', not 'timeframe'
                'period': period  # Dynamic period based on timeframe
            }
            response = requests.get(f"{API_BASE_URL}/api/analyzer-b", params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Received data for {ticker} ({timeframe}) with {period} period")
                
                # Process the data the same way your dashboard does
                signals = self.create_signal_timeline_from_data(data, timeframe)
                print(f"✅ Found {len(signals)} signals for {ticker} ({timeframe})")
                return signals
                
            else:
                print(f"❌ API returned status {response.status_code} for {ticker} ({timeframe})")
                return []
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching data for {ticker} ({timeframe}): {e}")
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing JSON response for {ticker} ({timeframe}): {e}")
        
        return None
    
    def create_signal_timeline_from_data(self, data: Dict, timeframe: str) -> List[Dict]:
        """Create signal timeline using pre-calculated signals from API response"""
        print(f"🔍 Using pre-calculated signals from API for {timeframe}")
        
        all_signals = []
        current_date = datetime.now()
        
        def calculate_days_since(signal_date: str) -> int:
            """Calculate days since a signal date"""
            if not signal_date:
                return 999
            try:
                # Handle both date formats
                if ' ' in signal_date:
                    parsed_date = datetime.strptime(signal_date, '%Y-%m-%d %H:%M:%S')
                else:
                    parsed_date = datetime.strptime(signal_date, '%Y-%m-%d')
                return (current_date - parsed_date).days
            except (ValueError, TypeError) as e:
                print(f"⚠️ Date parsing error for '{signal_date}': {e}")
                return 999
        
        # 1. Wave Trend Signals (main signals section)
        signals_section = data.get('signals', {})
        
        # Buy signals
        buy_signals = signals_section.get('buy', [])
        for signal_date in buy_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'WT Buy Signal',
                    'system': 'Wave Trend',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#00ff0a'
                })
        
        # Gold Buy signals
        gold_buy_signals = signals_section.get('goldBuy', [])
        for signal_date in gold_buy_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'WT Gold Buy Signal',
                    'system': 'Wave Trend',
                    'strength': 'Very Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#FFD700'
                })
        
        # Sell signals
        sell_signals = signals_section.get('sell', [])
        for signal_date in sell_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'WT Sell Signal',
                    'system': 'Wave Trend',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#ff1100'
                })
        
        # Cross signals (these are objects with date, isRed, value)
        cross_signals = signals_section.get('cross', [])
        for cross_signal in cross_signals:
            if isinstance(cross_signal, dict) and 'date' in cross_signal:
                signal_date = cross_signal['date']
                is_red = cross_signal.get('isRed', False)
                value = cross_signal.get('value', 0)
                
                days_since = calculate_days_since(signal_date)
                signal_type = 'WT Bearish Cross' if is_red else 'WT Bullish Cross'
                color = '#ff6600' if is_red else '#00ff88'
                
                all_signals.append({
                    'date': signal_date,
                    'type': signal_type,
                    'system': 'Wave Trend',
                    'strength': 'Moderate',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': color,
                    'value': value
                })
        
        # 2. RSI3M3+ Signals
        rsi3m3_section = data.get('rsi3m3', {})
        rsi3m3_signals = rsi3m3_section.get('signals', {})
        
        # RSI3M3 Buy signals
        rsi3m3_buy_signals = rsi3m3_signals.get('buy', [])
        for signal_date in rsi3m3_buy_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'RSI3M3 Bullish Entry',
                    'system': 'RSI3M3+',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#00ff0a'
                })
        
        # RSI3M3 Sell signals
        rsi3m3_sell_signals = rsi3m3_signals.get('sell', [])
        for signal_date in rsi3m3_sell_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'RSI3M3 Bearish Entry',
                    'system': 'RSI3M3+',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#ff1100'
                })
        
        # 3. Divergence Signals
        divergences_section = data.get('divergences', {})
        
        # Bullish divergences
        bullish_div_signals = divergences_section.get('bullish', [])
        for signal_date in bullish_div_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Bullish Divergence',
                    'system': 'Divergence',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#32CD32'
                })
        
        # Bearish divergences
        bearish_div_signals = divergences_section.get('bearish', [])
        for signal_date in bearish_div_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Bearish Divergence',
                    'system': 'Divergence',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#FF6347'
                })
        
        # Hidden divergences
        hidden_bullish_div_signals = divergences_section.get('hiddenBullish', [])
        for signal_date in hidden_bullish_div_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Hidden Bullish Divergence',
                    'system': 'Divergence',
                    'strength': 'Moderate',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#90EE90'
                })
        
        hidden_bearish_div_signals = divergences_section.get('hiddenBearish', [])
        for signal_date in hidden_bearish_div_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Hidden Bearish Divergence',
                    'system': 'Divergence',
                    'strength': 'Moderate',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#FFA07A'
                })
        
        # Money Flow divergences
        mf_bullish_div_signals = divergences_section.get('mfBullish', [])
        for signal_date in mf_bullish_div_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Bullish MF Divergence',
                    'system': 'Money Flow',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#32CD32'
                })
        
        mf_bearish_div_signals = divergences_section.get('mfBearish', [])
        for signal_date in mf_bearish_div_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Bearish MF Divergence',
                    'system': 'Money Flow',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#FF6347'
                })
        
        # 4. Pattern Signals
        patterns_section = data.get('patterns', {})
        
        # Fast Money signals
        fast_money_buy_signals = patterns_section.get('fastMoneyBuy', [])
        for signal_date in fast_money_buy_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Fast Money Buy',
                    'system': 'Patterns',
                    'strength': 'Very Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#00ff88'
                })
        
        fast_money_sell_signals = patterns_section.get('fastMoneySell', [])
        for signal_date in fast_money_sell_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Fast Money Sell',
                    'system': 'Patterns',
                    'strength': 'Very Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#ff0066'
                })
        
        # RSI Trend Break signals
        rsi_trend_break_buy_signals = patterns_section.get('rsiTrendBreakBuy', [])
        for signal_date in rsi_trend_break_buy_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'RSI Trend Break Buy',
                    'system': 'Patterns',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#00ff0a'
                })
        
        rsi_trend_break_sell_signals = patterns_section.get('rsiTrendBreakSell', [])
        for signal_date in rsi_trend_break_sell_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'RSI Trend Break Sell',
                    'system': 'Patterns',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#ff1100'
                })
        
        # Zero Line Reject signals
        zero_line_buy_signals = patterns_section.get('zeroLineRejectBuy', [])
        for signal_date in zero_line_buy_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Zero Line Reject Buy',
                    'system': 'Patterns',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#00ff0a'
                })
        
        zero_line_sell_signals = patterns_section.get('zeroLineRejectSell', [])
        for signal_date in zero_line_sell_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Zero Line Reject Sell',
                    'system': 'Patterns',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#ff1100'
                })
        
        # 5. Trend Exhaustion Signals
        trend_exhaust_section = data.get('trendExhaust', {})
        trend_exhaust_signals = trend_exhaust_section.get('signals', {})
        
        # Bear/Bull Cross signals
        bear_cross_signals = trend_exhaust_signals.get('bearCross', [])
        for signal_date in bear_cross_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Bear Cross Signal',
                    'system': 'Exhaustion',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#ff4444'
                })
        
        bull_cross_signals = trend_exhaust_signals.get('bullCross', [])
        for signal_date in bull_cross_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Bull Cross Signal',
                    'system': 'Exhaustion',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#44ff44'
                })
        
        # Reversal signals
        oversold_signals = trend_exhaust_signals.get('osReversal', [])
        for signal_date in oversold_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Oversold Reversal',
                    'system': 'Exhaustion',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#44ff44'
                })
        
        overbought_signals = trend_exhaust_signals.get('obReversal', [])
        for signal_date in overbought_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Overbought Reversal',
                    'system': 'Exhaustion',
                    'strength': 'Strong',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#ff4444'
                })
        
        # Additional exhaustion signals
        oversold_extreme_signals = trend_exhaust_signals.get('oversold', [])
        for signal_date in oversold_extreme_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Extreme Oversold',
                    'system': 'Exhaustion',
                    'strength': 'Moderate',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#66ff66'
                })
        
        overbought_extreme_signals = trend_exhaust_signals.get('overbought', [])
        for signal_date in overbought_extreme_signals:
            if signal_date:
                days_since = calculate_days_since(signal_date)
                all_signals.append({
                    'date': signal_date,
                    'type': 'Extreme Overbought',
                    'system': 'Exhaustion',
                    'strength': 'Moderate',
                    'daysSince': days_since,
                    'timeframe': timeframe,
                    'color': '#ff6666'
                })
        
        # Sort all signals by date (most recent first) with enhanced datetime handling
        def get_signal_datetime(signal):
            """Enhanced sorting function to handle both date-only and full timestamps"""
            try:
                date_str = signal.get('date', '')
                if not date_str:
                    return datetime.min
                
                if ' ' in date_str:
                    # Full timestamp (e.g., "2025-01-27 14:30:00")
                    return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                else:
                    # Date only (e.g., "2025-01-27") - assume end of day for better sorting
                    base_date = datetime.strptime(date_str, '%Y-%m-%d')
                    return base_date.replace(hour=23, minute=59, second=59)
            except (ValueError, TypeError):
                return datetime.min
        
        all_signals.sort(key=get_signal_datetime, reverse=True)
        
        # Create summary by system
        system_counts = {}
        for signal in all_signals:
            system = signal['system']
            system_counts[system] = system_counts.get(system, 0) + 1
        
        print(f"🎯 Total API-provided signals found: {len(all_signals)}")
        if system_counts:
            print(f"Signal breakdown by system:")
            for system, count in system_counts.items():
                print(f"  - {system}: {count}")
        
        return all_signals
    
    def check_for_new_signals(self, ticker: str, timeframe: str = '1d') -> List[Dict]:
        """Check for new signals using comprehensive detection with timeframe-specific filtering"""
        try:
            print(f"🔍 Checking for new signals: {ticker} ({timeframe})")
            
            # Fetch signal timeline data
            signals = self.fetch_signal_timeline(ticker, timeframe)
            if not signals:
                print(f"⚠️ No signals found for {ticker} ({timeframe})")
                return []
            
            # Filter for recent signals based on timeframe
            recent_signals = []
            current_datetime = datetime.now()
            
            # Set time window based on timeframe
            if timeframe == '1h':
                max_hours_ago = 4  # Only last 4 hours for hourly data
                print(f"🕐 Filtering for signals within last {max_hours_ago} hours")
            else:
                max_days_ago = 7  # Last 7 days for daily data
                print(f"📅 Filtering for signals within last {max_days_ago} days")
            
            for signal in signals:
                signal_date = signal.get('date', '')
                if not signal_date:
                    continue
                
                try:
                    # Parse signal timestamp
                    if ' ' in signal_date:
                        # Full timestamp (1h data)
                        parsed_signal_time = datetime.strptime(signal_date, '%Y-%m-%d %H:%M:%S')
                    else:
                        # Date only (1d data) - assume market open time
                        parsed_signal_time = datetime.strptime(signal_date, '%Y-%m-%d')
                    
                    # Calculate time difference
                    time_diff = current_datetime - parsed_signal_time
                    
                    # Apply timeframe-specific filtering
                    if timeframe == '1h':
                        # For 1h timeframe: only signals within last 4 hours
                        if time_diff.total_seconds() <= (max_hours_ago * 3600):
                            recent_signals.append(signal)
                    else:
                        # For 1d timeframe: only signals within last 7 days
                        if time_diff.days <= max_days_ago:
                            recent_signals.append(signal)
                            
                except ValueError as e:
                    print(f"⚠️ Error parsing signal date '{signal_date}': {e}")
                    continue
            
            print(f"✅ Found {len(recent_signals)} recent signals for {ticker} ({timeframe})")
            return recent_signals
            
        except Exception as e:
            print(f"❌ Error checking for new signals: {e}")
            return []
    
    def should_notify(self, signal: Dict, ticker: str, timeframe: str) -> bool:
        """Enhanced signal filtering for notifications with duplicate prevention"""
        if not signal:
            return False
        
        # Create unique notification key
        signal_key = f"{ticker}_{timeframe}_{signal.get('type', '')}_{signal.get('date', '')}"
        
        # Check if we've already notified about this signal
        if signal_key in self.last_notifications:
            last_notified = self.last_notifications[signal_key]
            try:
                last_notified_time = datetime.fromisoformat(last_notified)
                # Don't notify again if we've notified within the last 24 hours
                if (datetime.now() - last_notified_time).total_seconds() < 86400:  # 24 hours
                    return False
            except (ValueError, TypeError):
                # If there's an issue parsing the date, remove the old entry and proceed
                del self.last_notifications[signal_key]
        
        # Check if signal is recent enough based on timeframe
        signal_date = signal.get('date', '')
        if not signal_date:
            return False
        
        try:
            current_datetime = datetime.now()
            
            # Parse signal timestamp
            if ' ' in signal_date:
                # Full timestamp (1h data)
                parsed_signal_time = datetime.strptime(signal_date, '%Y-%m-%d %H:%M:%S')
            else:
                # Date only (1d data)
                parsed_signal_time = datetime.strptime(signal_date, '%Y-%m-%d')
            
            # Calculate time difference
            time_diff = current_datetime - parsed_signal_time
            
            # Apply timeframe-specific filtering
            if timeframe == '1h':
                # For 1h timeframe: only signals within last 4 hours
                if time_diff.total_seconds() > (4 * 3600):  # 4 hours in seconds
                    return False
            else:
                # For 1d timeframe: only signals within last 3 days
                if time_diff.days > 3:
                    return False
                    
        except ValueError:
            # If we can't parse the date, fall back to daysSince
            days_since = signal.get('daysSince')
            if days_since is None or not isinstance(days_since, (int, float)):
                return False
            
            if timeframe == '1h':
                # For hourly, be very strict - only today's signals
                if days_since > 0:
                    return False
            else:
                # For daily, allow up to 3 days
                if days_since > 3:
                    return False
        
        # Filter by signal strength and type
        strength = signal.get('strength', '').lower()
        signal_type = signal.get('type', '').lower()
        system = signal.get('system', '').lower()
        
        # High priority signals that should always notify
        high_priority_signals = [
            'gold buy', 'wt gold buy signal', 'volume explosion',
            'price breakout', 'weekly surge', 'exhaustion'
        ]
        
        # Strong signals that should notify
        strong_signals = [
            'buy signal', 'wt buy signal', 'bullish', 'oversold reversal',
            'volume breakout'
        ]
        
        # Check for high priority signals
        if any(priority in signal_type for priority in high_priority_signals):
            return True
        
        # Check for strong signals with good strength
        if any(strong in signal_type for strong in strong_signals):
            if strength in ['strong', 'very strong']:
                return True
        
        # RSI3M3+ bullish entries are always important
        if 'rsi3m3' in system and 'bullish' in signal_type:
            return True
        
        # RSI3M3+ bearish entries are also always important
        if 'rsi3m3' in system and 'bearish' in signal_type:
            return True
        
        # Money flow divergences with strong strength
        if 'money flow' in system and strength == 'strong':
            return True
        
        return False
    
    def format_signal_for_discord(self, signal: Dict, ticker: str, timeframe: str = '1d') -> str:
        """Format a signal for Discord notification with EST timestamps"""
        # Get emoji based on signal type
        emoji = {
            # Wave Trend Signals
            'WT Buy Signal': '📈',
            'WT Gold Buy Signal': '⭐',
            'WT Sell Signal': '📉',
            'WT Bullish Cross': '🟢',
            'WT Bearish Cross': '🔴',
            
            # RSI3M3+ Signals (FIXED MAPPING)
            'RSI3M3 Bullish Entry': '🟢',
            'RSI3M3 Bearish Entry': '🔴',
            
            # Divergence Signals
            'Bullish Divergence': '📈',
            'Bearish Divergence': '📉',
            'Hidden Bullish Divergence': '🔼',
            'Hidden Bearish Divergence': '🔽',
            'Bullish MF Divergence': '💚',
            'Bearish MF Divergence': '❤️',
            
            # Pattern Signals
            'Fast Money Buy': '💰',
            'Fast Money Sell': '💸',
            'RSI Trend Break Buy': '⬆️',
            'RSI Trend Break Sell': '⬇️',
            'Zero Line Reject Buy': '🚀',
            'Zero Line Reject Sell': '📉',
            
            # Trend Exhaustion Signals
            'Bear Cross Signal': '🐻',
            'Bull Cross Signal': '🐂',
            'Oversold Reversal': '🔄',
            'Overbought Reversal': '🔄',
            'Extreme Oversold': '💚',
            'Extreme Overbought': '❤️',
            
            # Legacy mappings (for backward compatibility)
            'RSI3M3 Bull': '🟢',
            'RSI3M3 Bear': '🔴',
            'Exhaustion Oversold': '💚',
            'Exhaustion Overbought': '❤️',
            'Price Breakout': '⬆️',
            'Price Breakdown': '⬇️'
        }.get(signal.get('type', ''), '🔔')
        
        # Get strength indicator
        strength_indicator = {
            'Very Strong': '🔥🔥🔥',
            'Strong': '🔥🔥',
            'Moderate': '🔥',
            'Weak': '💧'
        }.get(signal.get('strength', ''), '')
        
        # Get signal date and format timing in EST
        signal_date = signal.get('date', '')
        
        # Calculate EST-based timing
        timing_est = calculate_time_ago_est(signal_date)
        
        # Format timestamp in EST
        if ' ' in signal_date:
            # Full timestamp available (e.g., "2025-05-27 09:30:00")
            timestamp_display = format_est_timestamp(signal_date, show_time=True)
            time_info = "🕐 **EST Time:** "
        else:
            # Only date available (e.g., "2025-05-27")
            timestamp_display = format_est_timestamp(signal_date, show_time=False)
            time_info = "📅 **EST Date:** "
        
        # Add special indicator for very recent signals
        if timing_est == "Just now":
            timing_est = "Just now ⚡"
        elif "ago" in timing_est and ("m ago" in timing_est or "h ago" in timing_est):
            timing_est = f"{timing_est} ⚡"
        
        return f"""
{emoji} **{ticker}** - {signal.get('type', 'Unknown')} {strength_indicator}
📊 **System:** {signal.get('system', 'Unknown')}
⏰ **Timeframe:** {timeframe}
🕐 **Timing:** {timing_est}
{time_info}{timestamp_display}
        """.strip()

    async def send_signal_notification(self, signal: Dict, ticker: str, timeframe: str):
        """Send a signal notification to Discord"""
        try:
            channel = self.bot.get_channel(CHANNEL_ID)
            if not channel:
                print(f"❌ Could not find channel with ID {CHANNEL_ID}")
                return
            
            # Format the signal message
            message = self.format_signal_for_discord(signal, ticker, timeframe)
            
            # Determine embed color based on signal type
            signal_type = signal.get('type', '').lower()
            if 'gold buy' in signal_type:
                color = 0xFFD700  # Gold
            elif 'buy' in signal_type or 'bullish' in signal_type:
                color = 0x00ff00  # Green
            elif 'sell' in signal_type or 'bearish' in signal_type:
                color = 0xff0000  # Red
            elif 'exhaustion' in signal_type:
                color = 0xff6600  # Orange
            else:
                color = 0x0099ff  # Blue
            
            # Create Discord embed
            embed = discord.Embed(
                title=f"🚨 Signal Alert: {ticker} ({timeframe})",
                description=message,
                color=color,
                timestamp=datetime.now(EST)
            )
            
            # Add system and strength as fields
            embed.add_field(
                name="System", 
                value=signal.get('system', 'Unknown'), 
                inline=True
            )
            embed.add_field(
                name="Strength", 
                value=signal.get('strength', 'Unknown'), 
                inline=True
            )
            
            await channel.send(embed=embed)
            print(f"📤 Sent notification: {ticker} ({timeframe}) - {signal.get('type', 'Unknown')}")
            
            # Record this notification to prevent duplicates
            signal_key = f"{ticker}_{timeframe}_{signal.get('type', '')}_{signal.get('date', '')}"
            self.last_notifications[signal_key] = datetime.now().isoformat()
            self.save_last_notifications()
            
        except Exception as e:
            print(f"❌ Error sending notification: {e}")

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for Railway health checks"""
    
    def do_GET(self):
        """Handle GET requests for health check"""
        try:
            if self.path == '/health':
                # Create health status
                health_data = {
                    "status": "healthy" if signal_check_loop.is_running() else "unhealthy",
                    "uptime_seconds": int((datetime.now() - bot_start_time).total_seconds()) if bot_start_time else 0,
                    "checks_completed": checks_completed,
                    "last_check": last_successful_check.isoformat() if last_successful_check else None,
                    "total_signals_found": health_stats.get('total_signals_found', 0),
                    "total_notifications_sent": health_stats.get('total_notifications_sent', 0),
                    "failed_checks": health_stats.get('failed_checks', 0),
                    "api_errors": health_stats.get('api_errors', 0),
                    "discord_errors": health_stats.get('discord_errors', 0),
                    "bot_ready": bot.is_ready() if 'bot' in globals() else False,
                    "loop_running": signal_check_loop.is_running(),
                    "environment": os.getenv('RAILWAY_ENVIRONMENT', 'local'),
                    "service": os.getenv('RAILWAY_SERVICE_NAME', 'discord-bot'),
                    "version": "1.0.0"
                }
                
                # Set response
                self.send_response(200 if health_data["status"] == "healthy" else 503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(health_data, indent=2).encode())
                
            elif self.path == '/':
                # Basic root endpoint
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Discord Signal Bot - Health Check Available at /health')
                
            else:
                # 404 for other paths
                self.send_response(404)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Not Found')
                
        except Exception as e:
            # Error response
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(f'Health check error: {str(e)}'.encode())
    
    def log_message(self, format, *args):
        """Suppress default HTTP server logging to reduce noise"""
        if os.getenv('RAILWAY_ENVIRONMENT'):
            # Only log health checks in Railway environment for debugging
            return
        else:
            # Log locally for development
            super().log_message(format, *args)

def start_health_server():
    """Start the health check HTTP server in a separate thread"""
    try:
        port = int(os.getenv('PORT', '8080'))  # Railway sets PORT automatically
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        
        print(f"🏥 Health check server starting on port {port}")
        print(f"🌐 Health endpoint: http://0.0.0.0:{port}/health")
        
        # Start server in a separate thread so it doesn't block the bot
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        
        return server
    except Exception as e:
        print(f"⚠️ Failed to start health check server: {e}")
        print("📝 Bot will continue without health endpoint")
        return None

# Discord Bot Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    global loop_start_time, bot_start_time
    bot_start_time = datetime.now(EST)
    print(f'🤖 {bot.user} has connected to Discord!')
    print(f"🚀 Bot started at: {bot_start_time.strftime('%Y-%m-%d %I:%M:%S %p EST')}")
    print(f"📊 Monitoring {len(TICKER_TF_COMBINATIONS)} ticker-timeframe combinations")
    print(f"⏰ Signal check interval: {CHECK_INTERVAL} seconds ({CHECK_INTERVAL/60:.1f} minutes)")
    print(f"🌐 API endpoint: {API_BASE_URL}")
    print(f"📡 Discord channel: {CHANNEL_ID}")
    
    # Railway deployment detection
    if os.getenv('RAILWAY_ENVIRONMENT'):
        print(f"🚂 Running on Railway deployment: {os.getenv('RAILWAY_ENVIRONMENT')}")
        print(f"🔧 Railway service: {os.getenv('RAILWAY_SERVICE_NAME', 'discord-bot')}")
    
    if not signal_check_loop.is_running():
        loop_start_time = datetime.now(EST)
        signal_check_loop.start()
        print(f"✅ Signal monitoring loop started at: {loop_start_time.strftime('%Y-%m-%d %I:%M:%S %p EST')}")
    else:
        print("⚠️ Signal monitoring loop was already running")

@tasks.loop(seconds=CHECK_INTERVAL)
async def signal_check_loop():
    """Enhanced signal monitoring loop with comprehensive detection and health tracking"""
    if not bot.is_ready():
        return
    
    global loop_start_time, checks_completed, last_successful_check, health_stats
    
    try:
        cycle_start = datetime.now(EST)
        loop_start_time = cycle_start
        checks_completed += 1
        total_signals = 0
        notified_signals = 0
        
        print(f"\n🔄 Starting signal check cycle #{checks_completed}")
        print(f"🕐 Cycle start time: {cycle_start.strftime('%Y-%m-%d %I:%M:%S %p EST')}")
        
        # Railway health logging
        if os.getenv('RAILWAY_ENVIRONMENT'):
            print(f"🚂 Railway check #{checks_completed} - Memory usage available")
        
        # Create notifier instance
        notifier = SignalNotifier(bot)
        
        # Periodic cleanup of old notifications (every 10 cycles)
        if checks_completed % 10 == 0:
            cleaned_count = notifier.cleanup_old_notifications()
            if cleaned_count > 0:
                print(f"🧹 Periodic cleanup: removed {cleaned_count} old notification entries")
        
        # Check each ticker across all timeframes
        api_errors = 0
        discord_errors = 0
        
        for ticker in TICKERS:
            for timeframe in TIMEFRAMES:
                try:
                    print(f"\n📊 Checking {ticker} ({timeframe})...")
                    
                    # Get recent signals using comprehensive detection
                    recent_signals = notifier.check_for_new_signals(ticker, timeframe)
                    total_signals += len(recent_signals)
                    
                    if recent_signals:
                        print(f"✅ Found {len(recent_signals)} recent signals for {ticker} ({timeframe})")
                        
                        # Filter signals that should trigger notifications
                        notify_signals = [s for s in recent_signals if notifier.should_notify(s, ticker, timeframe)]
                        
                        if notify_signals:
                            print(f"🚨 {len(notify_signals)} signals meet notification criteria")
                            notified_signals += len(notify_signals)
                            
                            # Send notifications for qualifying signals
                            for signal in notify_signals:
                                try:
                                    await notifier.send_signal_notification(signal, ticker, timeframe)
                                    await asyncio.sleep(1)  # Rate limiting
                                    health_stats['total_notifications_sent'] += 1
                                except Exception as e:
                                    print(f"❌ Discord error sending notification: {e}")
                                    discord_errors += 1
                                    health_stats['discord_errors'] += 1
                        else:
                            print(f"🔕 No signals meet notification criteria for {ticker} ({timeframe})")
                    else:
                        print(f"ℹ️ No recent signals for {ticker} ({timeframe})")
                    
                    # Brief pause between tickers
                    await asyncio.sleep(0.5)
                    
                except requests.exceptions.RequestException as e:
                    print(f"❌ API error checking {ticker} ({timeframe}): {e}")
                    api_errors += 1
                    health_stats['api_errors'] += 1
                    continue
                except Exception as e:
                    print(f"❌ Unexpected error checking {ticker} ({timeframe}): {e}")
                    continue
        
        # Update health stats
        health_stats['total_signals_found'] += total_signals
        last_successful_check = cycle_start
        
        # Calculate next check time and update bot activity
        cycle_end = datetime.now(EST)
        cycle_duration = (cycle_end - cycle_start).total_seconds()
        next_check = cycle_start + timedelta(seconds=CHECK_INTERVAL)
        time_until_next = (next_check - cycle_end).total_seconds()
        
        # Update bot presence with enhanced status
        if time_until_next > 0:
            hours = int(time_until_next // 3600)
            minutes = int((time_until_next % 3600) // 60)
            seconds = int(time_until_next % 60)
            
            if hours > 0:
                status_text = f"Next check in {hours}h {minutes}m"
            elif minutes > 0:
                status_text = f"Next check in {minutes}m {seconds}s"
            else:
                status_text = f"Next check in {seconds}s"
            
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=status_text
                )
            )
        
        # Enhanced summary logging
        print(f"\n📋 Cycle #{checks_completed} completed successfully!")
        print(f"⏱️ Duration: {cycle_duration:.1f} seconds")
        print(f"📊 Total signals found: {total_signals}")
        print(f"🚨 Notifications sent: {notified_signals}")
        print(f"❌ API errors: {api_errors}")
        print(f"❌ Discord errors: {discord_errors}")
        print(f"⏰ Next check: {next_check.strftime('%I:%M:%S %p EST')}")
        
        # Railway-specific logging
        if os.getenv('RAILWAY_ENVIRONMENT'):
            uptime = cycle_end - bot_start_time if bot_start_time else timedelta(0)
            print(f"🚂 Railway uptime: {uptime}")
            print(f"🔧 Railway health: ✅ Loop running normally")
                
    except Exception as e:
        print(f"❌ Critical error in signal check loop: {e}")
        health_stats['failed_checks'] += 1
        
        # Try to notify about the error
        try:
            channel = bot.get_channel(CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title="⚠️ Bot Health Alert",
                    description=f"Signal check cycle #{checks_completed} failed",
                    color=0xff0000,
                    timestamp=datetime.now(EST)
                )
                embed.add_field(name="Error", value=str(e)[:1000], inline=False)
                embed.add_field(name="Cycle", value=f"#{checks_completed}", inline=True)
                embed.add_field(name="Time", value=datetime.now(EST).strftime('%I:%M:%S %p EST'), inline=True)
                await channel.send(embed=embed)
        except:
            pass  # Don't let notification errors crash the loop
        
        await asyncio.sleep(60)  # Wait before retrying

@bot.command(name='signals')
async def get_signals(ctx, ticker: str = "AAPL", timeframe: str = "1d"):
    """Get current signal timeline for a ticker and timeframe
    
    Usage:
    !signals                    - Get AAPL 1d signals  
    !signals TSLA              - Get TSLA 1d signals
    !signals AAPL 1h           - Get AAPL 1h signals
    !signals BTC-USD 1h        - Get BTC-USD 1h signals
    """
    # Validate timeframe
    valid_timeframes = ['1d', '1h', '4h', '15m', '5m']
    if timeframe not in valid_timeframes:
        await ctx.send(f"❌ Invalid timeframe '{timeframe}'. Valid options: {', '.join(valid_timeframes)}")
        return
    
    # Send typing indicator for longer operations
    async with ctx.typing():
        notifier = SignalNotifier(bot)
        signals = notifier.fetch_signal_timeline(ticker.upper(), timeframe)
        
        if not signals:
            await ctx.send(f"❌ No signals found for {ticker.upper()} ({timeframe})")
            return
        
        # Enhanced sorting to ensure most recent signals first
        def get_signal_datetime(signal):
            """Enhanced sorting function to handle both date-only and full timestamps"""
            try:
                date_str = signal.get('date', '')
                if not date_str:
                    return datetime.min
                
                if ' ' in date_str:
                    # Full timestamp (e.g., "2025-01-27 14:30:00")
                    return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                else:
                    # Date only (e.g., "2025-01-27") - assume end of day for better sorting
                    base_date = datetime.strptime(date_str, '%Y-%m-%d')
                    return base_date.replace(hour=23, minute=59, second=59)
            except (ValueError, TypeError):
                return datetime.min
        
        # Sort signals by datetime (most recent first)
        signals.sort(key=get_signal_datetime, reverse=True)
        
        # Show most recent 5 signals
        recent_signals = signals[:5]
        
        embed = discord.Embed(
            title=f"🚨 Latest Signals for {ticker.upper()} ({timeframe})",
            description="📅 **Showing most recent alerts first**",
            color=0x0099ff,
            timestamp=datetime.now(EST)
        )
        
        # Add summary information with enhanced details
        total_signals = len(signals)
        showing_count = len(recent_signals)
        
        # Count signals by recency
        now = datetime.now()
        today_signals = 0
        week_signals = 0
        
        for signal in signals:
            try:
                signal_date = signal.get('date', '')
                if ' ' in signal_date:
                    parsed_date = datetime.strptime(signal_date, '%Y-%m-%d %H:%M:%S')
                else:
                    parsed_date = datetime.strptime(signal_date, '%Y-%m-%d')
                
                days_diff = (now - parsed_date).days
                if days_diff == 0:
                    today_signals += 1
                if days_diff <= 7:
                    week_signals += 1
            except:
                continue
        
        embed.add_field(
            name="📊 Signal Summary", 
            value=f"**Total Found:** {total_signals} signals\n"
                  f"**Today:** {today_signals} signals\n"
                  f"**This Week:** {week_signals} signals\n"
                  f"**Showing:** {showing_count} most recent", 
            inline=False
        )
        
        # Add individual signals with enhanced timing info
        for i, signal in enumerate(recent_signals, 1):
            # Calculate EST-based timing with enhanced display
            signal_date = signal.get('date', '')
            timing_est = calculate_time_ago_est(signal_date)
            
            # Enhanced timing display with urgency indicators
            if timing_est == "Just now":
                timing_display = "⚡ Just now"
            elif "m ago" in timing_est and int(timing_est.split('m')[0].split()[-1]) <= 60:
                # Less than 1 hour
                timing_display = f"⚡ {timing_est}"
            elif "h ago" in timing_est and int(timing_est.split('h')[0].split()[-1]) <= 4:
                # Less than 4 hours
                timing_display = f"🔥 {timing_est}"
            elif "day" in timing_est and "1 day" in timing_est:
                # Yesterday
                timing_display = f"📅 {timing_est}"
            else:
                # Older signals
                timing_display = f"📆 {timing_est}"
            
            # Format timestamp display in EST
            if ' ' in signal_date:
                # Full timestamp with time (common for 1h data)
                date_display = f"🕐 {format_est_timestamp(signal_date, show_time=True)}"
            else:
                # Date only (common for 1d data)
                date_display = f"📅 {format_est_timestamp(signal_date, show_time=False)}"
            
            # Add strength indicator with enhanced emojis
            strength = signal.get('strength', '')
            signal_type = signal.get('type', 'Unknown')
            
            if 'Gold' in signal_type:
                strength_emoji = '⭐🔥🔥🔥'
            elif strength == 'Very Strong':
                strength_emoji = '🔥🔥🔥'
            elif strength == 'Strong':
                strength_emoji = '🔥🔥'
            elif strength == 'Moderate':
                strength_emoji = '🔥'
            else:
                strength_emoji = '💧'
            
            # Enhanced signal type emoji
            type_emoji = '🟢' if any(word in signal_type.lower() for word in ['buy', 'bullish']) else '🔴' if any(word in signal_type.lower() for word in ['sell', 'bearish']) else '🟡'
            
            embed.add_field(
                name=f"{type_emoji} #{i} {signal_type} {strength_emoji}",
                value=f"**System:** {signal.get('system', 'Unknown')}\n"
                      f"**Strength:** {strength}\n"
                      f"**When:** {timing_display}\n"
                      f"{date_display}",
                inline=True
            )
        
        # Add navigation footer
        if total_signals > showing_count:
            embed.set_footer(text=f"💡 Showing {showing_count} of {total_signals} signals • Use !signals {ticker.upper()} <timeframe> for other timeframes")
        else:
            embed.set_footer(text=f"💡 All {total_signals} signals displayed • Use !signals {ticker.upper()} <timeframe> for other timeframes")
        
    await ctx.send(embed=embed)

@bot.command(name='watch')
async def add_ticker(ctx, ticker: str):
    """Add a ticker to the watch list (placeholder - you can implement persistent storage)"""
    await ctx.send(f"✅ Added {ticker.upper()} to watch list!")

@bot.command(name='timer')
async def show_timer(ctx):
    """Show time until next signal check"""
    if not signal_check_loop.is_running():
        await ctx.send("❌ Signal monitoring is not running")
        return
    
    now = datetime.now()
    
    if loop_start_time:
        # Calculate when the next iteration should happen
        elapsed = (now - loop_start_time).total_seconds()
        cycles_completed = int(elapsed // CHECK_INTERVAL)
        next_cycle_time = loop_start_time + timedelta(seconds=(cycles_completed + 1) * CHECK_INTERVAL)
        time_until_next = next_cycle_time - now
        
        if time_until_next.total_seconds() <= 0:
            time_until_next = timedelta(seconds=CHECK_INTERVAL)
            next_cycle_time = now + time_until_next
        
        minutes, seconds = divmod(int(time_until_next.total_seconds()), 60)
        hours, minutes = divmod(minutes, 60)
        
        embed = discord.Embed(
            title="⏰ Signal Check Timer",
            color=0x00ff88,
            timestamp=datetime.now(EST)
        )
        
        if hours > 0:
            time_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            time_str = f"{minutes}m {seconds}s"
        else:
            time_str = f"{seconds}s"
        
        embed.add_field(name="⏳ Time Until Next Check", value=f"`{time_str}`", inline=True)
        embed.add_field(name="🕐 Next Check At (EST)", value=f"`{next_cycle_time.astimezone(EST).strftime('%I:%M:%S %p')}`", inline=True)
        embed.add_field(name="🔄 Check Interval", value=f"`{CHECK_INTERVAL} seconds`", inline=True)
        
        # Progress bar
        progress = 1 - (time_until_next.total_seconds() / CHECK_INTERVAL)
        bar_length = 20
        filled = int(progress * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)
        embed.add_field(name="📊 Progress", value=f"`{bar}` {progress*100:.1f}%", inline=False)
        
        embed.set_footer(text="💡 Use !status for full bot information")
        
    else:
        embed = discord.Embed(
            title="⏰ Signal Check Timer",
            description="Timer information not available yet",
            color=0xff0000
        )
    
    await ctx.send(embed=embed)

@bot.command(name='status')
async def bot_status(ctx):
    """Check bot status"""
    embed = discord.Embed(
        title="🤖 Signal Bot Status",
        color=0x00ff00 if signal_check_loop.is_running() else 0xff0000
    )
    
    embed.add_field(name="Loop Status", value="✅ Running" if signal_check_loop.is_running() else "❌ Stopped", inline=True)
    embed.add_field(name="Check Interval", value=f"`{CHECK_INTERVAL} seconds`", inline=True)
    embed.add_field(name="API URL", value=f"`{API_BASE_URL}`", inline=True)
    
    # Add timing information
    if signal_check_loop.is_running() and loop_start_time:
        now = datetime.now()
        elapsed = (now - loop_start_time).total_seconds()
        cycles_completed = int(elapsed // CHECK_INTERVAL)
        next_cycle_time = loop_start_time + timedelta(seconds=(cycles_completed + 1) * CHECK_INTERVAL)
        time_until_next = next_cycle_time - now
        
        if time_until_next.total_seconds() <= 0:
            time_until_next = timedelta(seconds=CHECK_INTERVAL)
            next_cycle_time = now + time_until_next
        
        minutes, seconds = divmod(int(time_until_next.total_seconds()), 60)
        time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
        
        embed.add_field(name="⏰ Next Check", value=f"`{time_str}`", inline=True)
        embed.add_field(name="🕐 Next Check Time", value=f"`{next_cycle_time.strftime('%H:%M:%S')}`", inline=True)
        embed.add_field(name="🔄 Checks Completed", value=f"`{cycles_completed}`", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='test')
async def test_connection(ctx):
    """Test API connection"""
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=10)
        if response.status_code == 200:
            await ctx.send("✅ API connection successful!")
        else:
            await ctx.send(f"❌ API returned status {response.status_code}")
    except Exception as e:
        await ctx.send(f"❌ API connection failed: {str(e)}")

@bot.command(name='config')
async def show_config(ctx):
    """Show current bot configuration"""
    embed = discord.Embed(
        title="⚙️ Bot Configuration",
        color=0x00ff88,
        timestamp=datetime.now(EST)
    )
    
    # Show ticker-timeframe combinations
    tf_summary = []
    for ticker, timeframe in TICKER_TF_COMBINATIONS:
        tf_summary.append(f"{ticker}({timeframe})")
    
    embed.add_field(
        name="📊 Ticker-Timeframe Combinations", 
        value=f"```{', '.join(tf_summary[:10])}{'...' if len(tf_summary) > 10 else ''}```", 
        inline=False
    )
    
    embed.add_field(name="🔢 Total Combinations", value=f"`{len(TICKER_TF_COMBINATIONS)}`", inline=True)
    embed.add_field(name="🔄 Check Interval", value=f"`{CHECK_INTERVAL} seconds`", inline=True)
    embed.add_field(name="📅 Max Signal Age", value=f"`{MAX_SIGNAL_AGE_DAYS} days`", inline=True)
    embed.add_field(name="💪 Strong Signals Only", value=f"`{ONLY_STRONG_SIGNALS}`", inline=True)
    embed.add_field(name="🌐 API URL", value=f"`{API_BASE_URL}`", inline=True)
    
    if TICKER_TIMEFRAMES:
        embed.add_field(name="⚙️ Configuration Mode", value="`Per-Ticker Timeframes`", inline=True)
    else:
        embed.add_field(name="⚙️ Configuration Mode", value="`Multi-Timeframe`", inline=True)
    
    embed.set_footer(text="💡 Configuration is loaded from .env file")
    
    await ctx.send(embed=embed)

@bot.command(name='notifications')
async def notification_stats(ctx):
    """Show notification statistics and cleanup status"""
    notifier = SignalNotifier(bot)
    
    # Get current stats
    total_entries = len(notifier.last_notifications)
    current_time = datetime.now()
    
    # Analyze entry ages
    recent_entries = 0
    old_entries = 0
    malformed_entries = 0
    
    for key, timestamp_str in notifier.last_notifications.items():
        try:
            if 'T' in timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str)
            else:
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d')
            
            age_days = (current_time - timestamp).days
            if age_days < 1:
                recent_entries += 1
            elif age_days >= 7:
                old_entries += 1
        except (ValueError, TypeError):
            malformed_entries += 1
    
    embed = discord.Embed(
        title="📊 Notification Statistics",
        color=0x00ff88,
        timestamp=datetime.now(EST)
    )
    
    embed.add_field(name="📝 Total Entries", value=f"`{total_entries}`", inline=True)
    embed.add_field(name="🆕 Recent (< 1 day)", value=f"`{recent_entries}`", inline=True)
    embed.add_field(name="🗑️ Old (≥ 7 days)", value=f"`{old_entries}`", inline=True)
    embed.add_field(name="❌ Malformed", value=f"`{malformed_entries}`", inline=True)
    embed.add_field(name="📁 File Size", value=f"`{os.path.getsize(LAST_NOTIFICATION_FILE) if os.path.exists(LAST_NOTIFICATION_FILE) else 0} bytes`", inline=True)
    
    # Show cleanup recommendation
    if old_entries > 0 or malformed_entries > 0:
        embed.add_field(
            name="💡 Recommendation", 
            value=f"Run `!cleanup` to remove {old_entries + malformed_entries} old/malformed entries", 
            inline=False
        )
    else:
        embed.add_field(name="✅ Status", value="Notification storage is clean", inline=False)
    
    embed.set_footer(text="💡 Automatic cleanup runs every 10 signal check cycles")
    
    await ctx.send(embed=embed)

@bot.command(name='cleanup')
async def manual_cleanup(ctx):
    """Manually trigger cleanup of old notification entries"""
    notifier = SignalNotifier(bot)
    
    # Get stats before cleanup
    before_count = len(notifier.last_notifications)
    
    # Perform cleanup
    cleaned_count = notifier.cleanup_old_notifications()
    
    # Get stats after cleanup
    after_count = len(notifier.last_notifications)
    
    embed = discord.Embed(
        title="🧹 Notification Cleanup Complete",
        color=0x00ff00,
        timestamp=datetime.now(EST)
    )
    
    embed.add_field(name="📊 Before", value=f"`{before_count} entries`", inline=True)
    embed.add_field(name="📊 After", value=f"`{after_count} entries`", inline=True)
    embed.add_field(name="🗑️ Removed", value=f"`{cleaned_count} entries`", inline=True)
    
    if cleaned_count > 0:
        embed.add_field(
            name="✅ Result", 
            value=f"Successfully cleaned up {cleaned_count} old notification entries", 
            inline=False
        )
    else:
        embed.add_field(name="ℹ️ Result", value="No old entries found to clean up", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='clear')
async def clear_channel(ctx, limit = None):
    """Clear messages from the current channel (max 100 at a time due to Discord limits)
    
    Usage:
    !clear        - Delete last 10 messages
    !clear 50     - Delete last 50 messages  
    !clear all    - Delete as many messages as possible (in batches)
    
    Note: Discord only allows bulk deletion of messages newer than 14 days
    """
    
    # Check permissions
    if not ctx.channel.permissions_for(ctx.author).manage_messages:
        await ctx.send("❌ You need 'Manage Messages' permission to use this command")
        return
    
    # Check bot permissions
    if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
        await ctx.send("❌ I need 'Manage Messages' permission to delete messages")
        return
    
    try:
        # Handle special case for "all"
        if limit is not None and str(limit).lower() == 'all':
            confirm_msg = await ctx.send(
                "⚠️ **WARNING**: This will delete ALL messages in this channel!\n"
                "React with ✅ to confirm or ❌ to cancel\n"
                "⏰ You have 30 seconds to decide..."
            )
            
            await confirm_msg.add_reaction('✅')
            await confirm_msg.add_reaction('❌')
            
            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ['✅', '❌'] and reaction.message.id == confirm_msg.id
            
            try:
                reaction, user = await bot.wait_for('reaction_add', timeout=30.0, check=check)
                
                if str(reaction.emoji) == '❌':
                    await confirm_msg.edit(content="❌ Channel clear cancelled")
                    return
                elif str(reaction.emoji) == '✅':
                    await confirm_msg.delete()
                    
                    # Delete messages in batches
                    total_deleted = 0
                    status_msg = await ctx.send("🗑️ Starting bulk deletion...")
                    
                    while True:
                        try:
                            # Get messages (Discord limit is 100 per call)
                            messages = []
                            async for message in ctx.channel.history(limit=100):
                                # Skip the status message we just sent
                                if message.id != status_msg.id:
                                    messages.append(message)
                            
                            if not messages:
                                break
                            
                            # Bulk delete (only works for messages < 14 days old)
                            try:
                                await ctx.channel.delete_messages(messages)
                                total_deleted += len(messages)
                                await status_msg.edit(content=f"🗑️ Deleted {total_deleted} messages...")
                                
                                # If we got less than 100 messages, we're done
                                if len(messages) < 100:
                                    break
                                    
                            except discord.HTTPException as e:
                                # Some messages might be too old for bulk delete
                                # Try deleting them individually
                                individual_deleted = 0
                                for message in messages:
                                    try:
                                        await message.delete()
                                        individual_deleted += 1
                                        total_deleted += 1
                                        
                                        # Rate limiting
                                        if individual_deleted % 5 == 0:
                                            await asyncio.sleep(1)
                                            await status_msg.edit(content=f"🗑️ Deleted {total_deleted} messages (individual deletion mode)...")
                                            
                                    except discord.NotFound:
                                        # Message already deleted
                                        continue
                                    except discord.Forbidden:
                                        # Can't delete this message
                                        continue
                                
                                # If no messages were deleted individually, we're probably done
                                if individual_deleted == 0:
                                    break
                            
                            # Small delay between batches
                            await asyncio.sleep(1)
                            
                        except discord.Forbidden:
                            await status_msg.edit(content="❌ Permission denied - cannot delete messages")
                            return
                        except Exception as e:
                            await status_msg.edit(content=f"❌ Error during deletion: {str(e)}")
                            return
                    
                    # Final status
                    await status_msg.edit(content=f"✅ **Deletion Complete!**\n📊 Total messages deleted: **{total_deleted}**\n🆕 Channel is now fresh and clean!")
                    
            except asyncio.TimeoutError:
                await confirm_msg.edit(content="⏰ Confirmation timed out - channel clear cancelled")
                return
        
        else:
            # Normal deletion with specified limit
            if limit is None:
                limit = 10
            else:
                # Try to convert to integer
                try:
                    limit = int(limit)
                except (ValueError, TypeError):
                    await ctx.send("❌ Invalid limit. Use a number (1-100) or 'all'")
                    return
                    
            if limit > 100:
                await ctx.send("❌ Maximum limit is 100 messages per command (use `!clear all` for bulk deletion)")
                return
            elif limit < 1:
                await ctx.send("❌ Limit must be at least 1")
                return
            
            # Add 1 to include the command message itself
            deleted = await ctx.channel.purge(limit=limit + 1)
            
            # Send confirmation (this will be the only message left)
            confirmation = await ctx.send(f"✅ Deleted {len(deleted)} messages")
            
            # Auto-delete confirmation after 5 seconds
            await asyncio.sleep(5)
            try:
                await confirmation.delete()
            except discord.NotFound:
                pass
                
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to delete messages in this channel")
    except discord.HTTPException as e:
        await ctx.send(f"❌ Error deleting messages: {str(e)}")
    except Exception as e:
        await ctx.send(f"❌ Unexpected error: {str(e)}")

@bot.command(name='addticker')
async def add_ticker_command(ctx, ticker: str):
    """Add a ticker to the monitoring list"""
    global TICKERS, TICKER_TF_COMBINATIONS
    try:
        ticker = ticker.upper().strip()
        
        # Load current config
        config = load_ticker_config()
        current_tickers = config.get('tickers', [])
        max_tickers = config.get('settings', {}).get('max_tickers', 50)
        
        # Validation
        if not ticker:
            await ctx.send("❌ Please provide a valid ticker symbol")
            return
            
        if ticker in current_tickers:
            await ctx.send(f"⚠️ **{ticker}** is already being monitored")
            return
            
        if len(current_tickers) >= max_tickers:
            await ctx.send(f"❌ Maximum ticker limit reached ({max_tickers}). Remove a ticker first.")
            return
            
        # Basic ticker validation (alphanumeric, dash, dot)
        import re
        if not re.match(r'^[A-Z0-9.-]+$', ticker):
            await ctx.send(f"❌ Invalid ticker format: **{ticker}**\nTickers should contain only letters, numbers, dots, and dashes.")
            return
            
        # Add ticker
        current_tickers.append(ticker)
        config['tickers'] = sorted(current_tickers)  # Keep sorted
        save_ticker_config(config)
        
        # Update global variables and rebuild combinations
        TICKERS = config['tickers']
        build_ticker_combinations()
        
        # Create success embed
        embed = discord.Embed(
            title="✅ Ticker Added Successfully!",
            description=f"**{ticker}** has been added to the monitoring list",
            color=0x00ff00
        )
        embed.add_field(
            name="📊 Current Status", 
            value=f"Monitoring **{len(TICKERS)}** tickers across **{len(TIMEFRAMES)}** timeframes\n"
                  f"Total combinations: **{len(TICKER_TF_COMBINATIONS)}**",
            inline=False
        )
        embed.add_field(
            name="🔄 Next Check", 
            value="The new ticker will be included in the next signal check cycle",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error adding ticker: {str(e)}")

@bot.command(name='removeticker')
async def remove_ticker_command(ctx, ticker: str):
    """Remove a ticker from the monitoring list"""
    global TICKERS, TICKER_TF_COMBINATIONS
    try:
        ticker = ticker.upper().strip()
        
        # Load current config
        config = load_ticker_config()
        current_tickers = config.get('tickers', [])
        
        if not ticker:
            await ctx.send("❌ Please provide a valid ticker symbol")
            return
            
        if ticker not in current_tickers:
            await ctx.send(f"⚠️ **{ticker}** is not in the monitoring list")
            return
            
        if len(current_tickers) <= 1:
            await ctx.send("❌ Cannot remove the last ticker. At least one ticker must be monitored.")
            return
            
        # Remove ticker
        current_tickers.remove(ticker)
        config['tickers'] = current_tickers
        save_ticker_config(config)
        
        # Update global variables and rebuild combinations
        TICKERS = config['tickers']
        build_ticker_combinations()
        
        # Create success embed
        embed = discord.Embed(
            title="🗑️ Ticker Removed Successfully!",
            description=f"**{ticker}** has been removed from the monitoring list",
            color=0xff9900
        )
        embed.add_field(
            name="📊 Current Status", 
            value=f"Monitoring **{len(TICKERS)}** tickers across **{len(TIMEFRAMES)}** timeframes\n"
                  f"Total combinations: **{len(TICKER_TF_COMBINATIONS)}**",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error removing ticker: {str(e)}")

@bot.command(name='listtickers')
async def list_tickers_command(ctx):
    """List all currently monitored tickers"""
    try:
        config = load_ticker_config()
        tickers = config.get('tickers', [])
        timeframes = config.get('timeframes', ['1d'])
        max_tickers = config.get('settings', {}).get('max_tickers', 50)
        
        # Create embed
        embed = discord.Embed(
            title="📊 Current Ticker Configuration",
            color=0x0099ff
        )
        
        # Tickers field
        if tickers:
            ticker_text = ", ".join(f"`{ticker}`" for ticker in tickers)
            # Split long ticker lists
            if len(ticker_text) > 1000:
                ticker_chunks = []
                current_chunk = ""
                for ticker in tickers:
                    ticker_part = f"`{ticker}`, "
                    if len(current_chunk + ticker_part) > 1000:
                        ticker_chunks.append(current_chunk.rstrip(", "))
                        current_chunk = ticker_part
                    else:
                        current_chunk += ticker_part
                if current_chunk:
                    ticker_chunks.append(current_chunk.rstrip(", "))
                
                for i, chunk in enumerate(ticker_chunks):
                    field_name = "📈 Monitored Tickers" if i == 0 else f"📈 Monitored Tickers (continued {i+1})"
                    embed.add_field(name=field_name, value=chunk, inline=False)
            else:
                embed.add_field(name="📈 Monitored Tickers", value=ticker_text, inline=False)
        else:
            embed.add_field(name="📈 Monitored Tickers", value="*None configured*", inline=False)
            
        # Timeframes field
        timeframe_text = ", ".join(f"`{tf}`" for tf in timeframes)
        embed.add_field(name="⏱️ Timeframes", value=timeframe_text, inline=True)
        
        # Statistics
        embed.add_field(
            name="📊 Statistics",
            value=f"**Tickers**: {len(tickers)}/{max_tickers}\n"
                  f"**Timeframes**: {len(timeframes)}\n"
                  f"**Total Combinations**: {len(TICKER_TF_COMBINATIONS)}",
            inline=True
        )
        
        # Commands help
        embed.add_field(
            name="🛠️ Management Commands",
            value="`!addticker SYMBOL` - Add ticker\n"
                  "`!removeticker SYMBOL` - Remove ticker\n"
                  "`!timeframes` - Manage timeframes",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error listing tickers: {str(e)}")

@bot.command(name='timeframes')
async def timeframes_command(ctx, action: str = None, timeframe: str = None):
    """Manage timeframes: !timeframes list|add|remove [timeframe]"""
    global TIMEFRAMES, TICKER_TF_COMBINATIONS
    try:
        config = load_ticker_config()
        current_timeframes = config.get('timeframes', ['1d'])
        allowed_timeframes = config.get('settings', {}).get('allowed_timeframes', ['1d', '1h'])
        
        if not action:
            action = 'list'
            
        action = action.lower()
        
        if action == 'list':
            embed = discord.Embed(
                title="⏱️ Timeframe Configuration",
                color=0x0099ff
            )
            
            # Current timeframes
            tf_text = ", ".join(f"`{tf}`" for tf in current_timeframes)
            embed.add_field(name="📊 Active Timeframes", value=tf_text, inline=False)
            
            # Available timeframes
            available_text = ", ".join(f"`{tf}`" for tf in allowed_timeframes)
            embed.add_field(name="✅ Available Timeframes", value=available_text, inline=False)
            
            # Statistics
            embed.add_field(
                name="📈 Impact",
                value=f"**Tickers**: {len(TICKERS)}\n"
                      f"**Timeframes**: {len(current_timeframes)}\n"
                      f"**Total Combinations**: {len(TICKER_TF_COMBINATIONS)}",
                inline=False
            )
            
            embed.add_field(
                name="🛠️ Commands",
                value="`!timeframes add 1h` - Add timeframe\n"
                      "`!timeframes remove 1h` - Remove timeframe",
                inline=False
            )
            
            await ctx.send(embed=embed)
            
        elif action == 'add':
            if not timeframe:
                await ctx.send("❌ Please specify a timeframe to add\nExample: `!timeframes add 1h`")
                return
                
            timeframe = timeframe.lower()
            
            if timeframe not in allowed_timeframes:
                await ctx.send(f"❌ **{timeframe}** is not a supported timeframe\n"
                              f"Available: {', '.join(allowed_timeframes)}")
                return
                
            if timeframe in current_timeframes:
                await ctx.send(f"⚠️ **{timeframe}** is already active")
                return
                
            # Add timeframe
            current_timeframes.append(timeframe)
            config['timeframes'] = current_timeframes
            save_ticker_config(config)
            
            # Update globals
            TIMEFRAMES = current_timeframes
            build_ticker_combinations()
            
            embed = discord.Embed(
                title="✅ Timeframe Added!",
                description=f"**{timeframe}** has been added to active timeframes",
                color=0x00ff00
            )
            embed.add_field(
                name="📊 New Status",
                value=f"Total combinations: **{len(TICKER_TF_COMBINATIONS)}**\n"
                      f"({len(TICKERS)} tickers × {len(TIMEFRAMES)} timeframes)",
                inline=False
            )
            
            await ctx.send(embed=embed)
            
        elif action == 'remove':
            if not timeframe:
                await ctx.send("❌ Please specify a timeframe to remove\nExample: `!timeframes remove 1h`")
                return
                
            timeframe = timeframe.lower()
            
            if timeframe not in current_timeframes:
                await ctx.send(f"⚠️ **{timeframe}** is not currently active")
                return
                
            if len(current_timeframes) <= 1:
                await ctx.send("❌ Cannot remove the last timeframe. At least one must be active.")
                return
                
            # Remove timeframe
            current_timeframes.remove(timeframe)
            config['timeframes'] = current_timeframes
            save_ticker_config(config)
            
            # Update globals
            TIMEFRAMES = current_timeframes
            build_ticker_combinations()
            
            embed = discord.Embed(
                title="🗑️ Timeframe Removed!",
                description=f"**{timeframe}** has been removed from active timeframes",
                color=0xff9900
            )
            embed.add_field(
                name="📊 New Status",
                value=f"Total combinations: **{len(TICKER_TF_COMBINATIONS)}**\n"
                      f"({len(TICKERS)} tickers × {len(TIMEFRAMES)} timeframes)",
                inline=False
            )
            
            await ctx.send(embed=embed)
            
        else:
            await ctx.send("❌ Invalid action. Use: `!timeframes list|add|remove [timeframe]`")
            
    except Exception as e:
        await ctx.send(f"❌ Error managing timeframes: {str(e)}")

@bot.command(name='health')
async def health_check(ctx):
    """Comprehensive bot health check for monitoring Railway deployment"""
    try:
        now = datetime.now(EST)
        
        # Calculate uptime
        uptime = now - bot_start_time if bot_start_time else timedelta(0)
        uptime_str = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds%3600)//60}m"
        
        # Calculate time since last check
        time_since_last = now - last_successful_check if last_successful_check else None
        
        # Determine health status
        is_healthy = True
        health_issues = []
        
        if not signal_check_loop.is_running():
            is_healthy = False
            health_issues.append("Signal loop not running")
            
        if time_since_last and time_since_last.total_seconds() > (CHECK_INTERVAL * 2):
            is_healthy = False
            health_issues.append(f"Last check was {time_since_last.total_seconds()//60:.0f}m ago")
            
        if health_stats['failed_checks'] > (checks_completed * 0.1):  # More than 10% failure rate
            is_healthy = False
            health_issues.append("High failure rate detected")
        
        # Create health embed
        embed = discord.Embed(
            title="🏥 Bot Health Status",
            description="🚂 **Railway Deployment Monitor**",
            color=0x00ff00 if is_healthy else 0xff0000,
            timestamp=now
        )
        
        # Basic status
        embed.add_field(
            name="🤖 Bot Status", 
            value=f"**Status:** {'🟢 Healthy' if is_healthy else '🔴 Issues Detected'}\n"
                  f"**Uptime:** {uptime_str}\n"
                  f"**Started:** {bot_start_time.strftime('%m/%d %I:%M %p EST') if bot_start_time else 'Unknown'}",
            inline=True
        )
        
        # Loop status
        loop_status = "🟢 Running" if signal_check_loop.is_running() else "🔴 Stopped"
        last_check_str = last_successful_check.strftime('%I:%M:%S %p EST') if last_successful_check else "Never"
        
        embed.add_field(
            name="⏰ Signal Loop", 
            value=f"**Status:** {loop_status}\n"
                  f"**Cycles:** {checks_completed}\n"
                  f"**Last Check:** {last_check_str}",
            inline=True
        )
        
        # Railway info
        railway_env = os.getenv('RAILWAY_ENVIRONMENT', 'Local')
        railway_service = os.getenv('RAILWAY_SERVICE_NAME', 'discord-bot')
        
        embed.add_field(
            name="🚂 Railway Info", 
            value=f"**Environment:** {railway_env}\n"
                  f"**Service:** {railway_service}\n"
                  f"**Region:** {os.getenv('RAILWAY_REGION', 'Unknown')}",
            inline=True
        )
        
        # Performance stats
        success_rate = ((checks_completed - health_stats['failed_checks']) / max(checks_completed, 1)) * 100
        
        embed.add_field(
            name="📊 Performance", 
            value=f"**Success Rate:** {success_rate:.1f}%\n"
                  f"**Signals Found:** {health_stats['total_signals_found']}\n"
                  f"**Notifications:** {health_stats['total_notifications_sent']}",
            inline=True
        )
        
        # Error tracking
        embed.add_field(
            name="❌ Error Count", 
            value=f"**Failed Checks:** {health_stats['failed_checks']}\n"
                  f"**API Errors:** {health_stats['api_errors']}\n"
                  f"**Discord Errors:** {health_stats['discord_errors']}",
            inline=True
        )
        
        # Next check info
        if signal_check_loop.is_running() and loop_start_time:
            elapsed = (now - loop_start_time).total_seconds()
            cycles_completed_since_start = int(elapsed // CHECK_INTERVAL)
            next_cycle_time = loop_start_time + timedelta(seconds=(cycles_completed_since_start + 1) * CHECK_INTERVAL)
            time_until_next = next_cycle_time - now
            
            if time_until_next.total_seconds() <= 0:
                time_until_next = timedelta(seconds=CHECK_INTERVAL)
                next_cycle_time = now + time_until_next
            
            minutes, seconds = divmod(int(time_until_next.total_seconds()), 60)
            time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
            
            embed.add_field(
                name="⏳ Next Check", 
                value=f"**In:** {time_str}\n"
                      f"**At:** {next_cycle_time.strftime('%I:%M:%S %p EST')}\n"
                      f"**Interval:** {CHECK_INTERVAL}s",
                inline=True
            )
        
        # Health issues (if any)
        if health_issues:
            embed.add_field(
                name="⚠️ Issues Detected", 
                value="\n".join([f"• {issue}" for issue in health_issues]),
                inline=False
            )
        
        # Configuration summary
        embed.add_field(
            name="⚙️ Configuration", 
            value=f"**Tickers:** {len(TICKERS)}\n"
                  f"**Timeframes:** {len(TIMEFRAMES)}\n"
                  f"**Combinations:** {len(TICKER_TF_COMBINATIONS)}",
            inline=True
        )
        
        # Set footer
        embed.set_footer(text="💡 Use !status for detailed bot information • !timer for next check countdown")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error generating health report: {str(e)}")

@bot.command(name='uptime')
async def uptime_command(ctx):
    """Show bot uptime and Railway deployment info"""
    try:
        now = datetime.now(EST)
        
        if not bot_start_time:
            await ctx.send("⚠️ Bot start time not available")
            return
            
        uptime = now - bot_start_time
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        embed = discord.Embed(
            title="⏰ Bot Uptime",
            color=0x00ff88,
            timestamp=now
        )
        
        # Uptime display
        uptime_parts = []
        if days > 0:
            uptime_parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            uptime_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            uptime_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if seconds > 0 or not uptime_parts:
            uptime_parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
        
        uptime_str = ", ".join(uptime_parts)
        
        embed.add_field(
            name="🕐 Current Uptime",
            value=f"`{uptime_str}`",
            inline=False
        )
        
        embed.add_field(
            name="🚀 Started At",
            value=f"`{bot_start_time.strftime('%Y-%m-%d %I:%M:%S %p EST')}`",
            inline=True
        )
        
        embed.add_field(
            name="📅 Current Time",
            value=f"`{now.strftime('%Y-%m-%d %I:%M:%S %p EST')}`",
            inline=True
        )
        
        # Railway info
        if os.getenv('RAILWAY_ENVIRONMENT'):
            embed.add_field(
                name="🚂 Railway Deployment",
                value=f"**Environment:** {os.getenv('RAILWAY_ENVIRONMENT')}\n"
                      f"**Service:** {os.getenv('RAILWAY_SERVICE_NAME', 'discord-bot')}\n"
                      f"**Running:** ✅ Active",
                inline=False
            )
        
        # Loop status
        loop_status = "✅ Running" if signal_check_loop.is_running() else "❌ Stopped"
        embed.add_field(
            name="🔄 Monitoring Status",
            value=f"**Signal Loop:** {loop_status}\n"
                  f"**Check Cycles:** {checks_completed}\n"
                  f"**Last Check:** {last_successful_check.strftime('%I:%M:%S %p EST') if last_successful_check else 'Never'}",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error showing uptime: {str(e)}")

if __name__ == "__main__":
    import asyncio
    import sys
    
    # Fix for Windows event loop issue
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    if not DISCORD_TOKEN:
        print("❌ Please set DISCORD_TOKEN environment variable")
        print("💡 Copy .env.example to .env and fill in your values")
        exit(1)
    
    if not CHANNEL_ID:
        print("❌ Please set DISCORD_CHANNEL_ID environment variable")
        print("💡 Copy .env.example to .env and fill in your values")
        exit(1)
    
    print("🚀 Starting Discord Signal Bot...")
    print(f"📡 Monitoring API: {API_BASE_URL}")
    print(f"💬 Channel ID: {CHANNEL_ID}")
    print(f"⏰ Check interval: {CHECK_INTERVAL} seconds")
    
    # Start health check server for Railway monitoring
    health_server = start_health_server()
    
    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        print("❌ Invalid Discord token")
    except Exception as e:
        print(f"❌ Error starting bot: {e}") 