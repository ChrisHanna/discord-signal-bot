#!/usr/bin/env python3
"""
Discord Signal Notifier
Fetches signal timeline data from your local web API and sends Discord notifications.
"""

import requests
import json
import time
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import pytz
import threading
import asyncio
import aiohttp
import sys
import traceback
import atexit
from dateutil import parser
import logging
import asyncpg
import numpy as np

# Import database functionality
from database import init_database, check_duplicate, record_notification, get_stats, cleanup_old, record_detected_signal, get_priority_analytics, get_signal_utilization, add_ticker_to_database, remove_ticker_from_database, get_database_tickers, save_vip_tickers_to_database, get_vip_tickers_from_database, save_priority_settings_to_database, update_daily_analytics, get_best_performing_signals, get_signal_performance_summary, cleanup_old_analytics, record_signal_performance
from priority_manager import should_send_notification, get_priority_display, calculate_signal_priority, rank_signals_by_priority, priority_manager

# Import smart scheduler
from smart_scheduler import SmartScheduler, create_smart_scheduler

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:5000')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '1600'))  # Default ~26 minutes (kept for compatibility)
USE_SMART_SCHEDULER = os.getenv('USE_SMART_SCHEDULER', 'true').lower() == 'true'  # Enable smart scheduling
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))

# ✅ REMOVED: JSON file paths and configuration loading functions
# Now using PostgreSQL database as single source of truth

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

# ✅ NEW: Database-based configuration management
class DatabaseConfig:
    """Manage configuration using PostgreSQL database as single source of truth"""
    
    def __init__(self):
        self.tickers = []
        self.timeframes = ['1d', '1h']  # Default timeframes
        self.max_tickers = 50
        self.allowed_timeframes = ['15m', '30m', '1h', '3h', '6h', '1d', '2d', '3d', '1wk']
        
    async def load_from_database(self):
        """Load configuration from PostgreSQL database"""
        try:
            print("🔄 Loading configuration from PostgreSQL database...")
            
            # Load tickers from database
            self.tickers = await get_database_tickers()
            
            if not self.tickers:
                # Initialize with default popular tickers if database is empty
                default_tickers = ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA']
                print(f"📊 Initializing database with default tickers: {default_tickers}")
                
                for ticker in default_tickers:
                    await add_ticker_to_database(ticker)
                    
                self.tickers = default_tickers
            
            print(f"✅ Loaded {len(self.tickers)} tickers from database: {', '.join(self.tickers[:10])}{'...' if len(self.tickers) > 10 else ''}")
            return True
            
        except Exception as e:
            print(f"❌ Error loading configuration from database: {e}")
            # Fallback to environment variables if database fails
            self.load_from_environment()
            return False
    
    def load_from_environment(self):
        """Fallback: Load configuration from environment variables"""
        print("⚠️ Falling back to environment variable configuration")
        
        # Load tickers from environment
        tickers_str = os.getenv('TICKERS', 'AAPL,TSLA,NVDA,SPY,QQQ')
        self.tickers = [ticker.strip().upper() for ticker in tickers_str.split(',') if ticker.strip()]
        
        # Load timeframes from environment
        timeframes_str = os.getenv('TIMEFRAMES', '1d,1h')
        self.timeframes = [tf.strip() for tf in timeframes_str.split(',') if tf.strip()]
        
        print(f"📊 Loaded from environment: {len(self.tickers)} tickers, {len(self.timeframes)} timeframes")
    
    async def add_ticker(self, ticker: str) -> bool:
        """Add ticker to database and update local config"""
        try:
            ticker = ticker.upper().strip()
            
            if ticker in self.tickers:
                return False  # Already exists
                
            if len(self.tickers) >= self.max_tickers:
                return False  # Max limit reached
                
            # Add to database
            success = await add_ticker_to_database(ticker)
            if success:
                self.tickers.append(ticker)
                self.tickers.sort()  # Keep sorted
                return True
            return False
            
        except Exception as e:
            print(f"❌ Error adding ticker {ticker}: {e}")
            return False
    
    async def remove_ticker(self, ticker: str) -> bool:
        """Remove ticker from database and update local config"""
        try:
            ticker = ticker.upper().strip()
            
            if ticker not in self.tickers:
                return False  # Not found
                
            if len(self.tickers) <= 1:
                return False  # Cannot remove last ticker
                
            # Remove from database
            success = await remove_ticker_from_database(ticker)
            if success:
                self.tickers.remove(ticker)
                return True
            return False
            
        except Exception as e:
            print(f"❌ Error removing ticker {ticker}: {e}")
            return False
    
    def get_ticker_combinations(self) -> List[tuple]:
        """Get all ticker-timeframe combinations"""
        combinations = []
        for ticker in self.tickers:
            for timeframe in self.timeframes:
                combinations.append((ticker, timeframe))
        return combinations

# Initialize database config
config = DatabaseConfig()

# Legacy support - will be populated after database load
TICKERS = []
TIMEFRAMES = ['1d', '1h']
TICKER_TF_COMBINATIONS = []

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
    global TICKER_TF_COMBINATIONS, TICKERS, TIMEFRAMES
    
    # Update global variables from config
    TICKERS = config.tickers.copy()
    TIMEFRAMES = config.timeframes.copy()
    
    TICKER_TF_COMBINATIONS = []
    
    if TICKER_TIMEFRAMES:
        # Use per-ticker timeframes
        for ticker, timeframe in TICKER_TIMEFRAMES.items():
            TICKER_TF_COMBINATIONS.append((ticker, timeframe))
        print(f"📊 Using per-ticker timeframes: {TICKER_TIMEFRAMES}")
    else:
        # Use simple multi-timeframe (all tickers on all timeframes)
        TICKER_TF_COMBINATIONS = config.get_ticker_combinations()
        print(f"📊 Using multi-timeframe: {len(TICKERS)} tickers × {len(TIMEFRAMES)} timeframes = {len(TICKER_TF_COMBINATIONS)} combinations")

# Will be built after database initialization
MAX_SIGNAL_AGE_DAYS = int(os.getenv('MAX_SIGNAL_AGE_DAYS', '1'))
ONLY_STRONG_SIGNALS = os.getenv('ONLY_STRONG_SIGNALS', 'false').lower() == 'true'

# Global timer tracking for bot commands
loop_start_time = None
checks_completed = 0
bot_start_time = None
last_successful_check = None
smart_scheduler = None  # Smart scheduler instance
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
        # No longer need to load JSON notifications - database handles this
        self.stats = {
            'signals_sent': 0,
            'api_calls': 0,
            'errors': 0
        }
    
    def fetch_signal_timeline(self, ticker: str, timeframe: str = '1d') -> Optional[List[Dict]]:
        """Fetch signal timeline data from your web API"""
        try:
            print(f"🔍 Fetching signals for {ticker} ({timeframe})...")
            
            # Set period based on timeframe for optimal data coverage
            if timeframe == '1d':
                period = '1y'  # 1 year for daily data
            elif timeframe == '1h':
                period = '1mo'  # 1 month for hourly data
            elif timeframe in ['15m', '30m']:
                period = '1wk'  # 1 week for intraday timeframes (faster + more relevant)
            elif timeframe in ['3h', '6h']:
                period = '3mo'  # 3 months for medium hourly timeframes
            elif timeframe in ['2d', '3d']:
                period = '1y'  # 1 year for multi-day timeframes
            elif timeframe == '1wk':
                period = '5y'  # 5 years for weekly data
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
                
                # 🆕 NEW: Auto-update performance for previous signals using API data
                asyncio.create_task(self.auto_update_signal_performance(ticker, timeframe, data))
                
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
    
    async def auto_update_signal_performance(self, ticker: str, timeframe: str, api_data: Dict):
        """Auto-update performance for previous signals using API pricing data"""
        try:
            from database import record_signal_performance
            import asyncpg
            import os
            
            # Get DATABASE_URL for direct connection
            DATABASE_URL = os.getenv('DATABASE_URL')
            if not DATABASE_URL:
                print(f"⚠️ No DATABASE_URL set for performance tracking")
                return
            
            # Use direct connection instead of pool (which may not be initialized)
            conn = await asyncpg.connect(DATABASE_URL)
            
            try:
                # Get signals from last 7 days that need performance updates
                pending_signals = await conn.fetch('''
                    SELECT sn.ticker, sn.timeframe, sn.signal_type, sn.signal_date, sn.notified_at
                    FROM signal_notifications sn
                    LEFT JOIN signal_performance sp ON (
                        sn.ticker = sp.ticker AND 
                        sn.timeframe = sp.timeframe AND 
                        sn.signal_type = sp.signal_type AND 
                        sn.signal_date = sp.signal_date
                    )
                    WHERE sn.ticker = $1 
                      AND sn.timeframe = $2
                      AND sn.notified_at >= NOW() - INTERVAL '7 days'
                      AND sp.id IS NULL  -- No performance data yet
                    ORDER BY sn.signal_date DESC
                    LIMIT 5  -- Process max 5 signals per API call to avoid overload
                ''', ticker, timeframe)
                
                if not pending_signals:
                    # print(f"✅ No pending performance updates for {ticker} {timeframe}")
                    return  # No pending signals to update
                
                print(f"🔄 Auto-updating performance for {len(pending_signals)} {ticker} signals...")
                
                # Extract pricing data from API response
                pricing_data = self.extract_pricing_data_from_api(api_data)
                
                if not pricing_data:
                    print(f"⚠️ No pricing data available in API response for {ticker}")
                    return
                
                # Update performance for each pending signal
                for signal in pending_signals:
                    try:
                        signal_datetime = signal['signal_date']
                        signal_type = signal['signal_type']
                        
                        # Calculate performance using API pricing data
                        performance = self.calculate_performance_from_pricing(
                            signal_datetime, pricing_data, timeframe
                        )
                        
                        if performance and performance.get('price_at_signal'):
                            await record_signal_performance(
                                ticker=ticker,
                                timeframe=timeframe,
                                signal_type=signal_type,
                                signal_date=signal_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                                price_at_signal=performance['price_at_signal'],
                                price_after_1h=performance.get('price_after_1h'),
                                price_after_4h=performance.get('price_after_4h'),
                                price_after_1d=performance.get('price_after_1d'),
                                price_after_3d=performance.get('price_after_3d')
                            )
                            
                            print(f"✅ Updated performance for {signal_type} signal from {signal_datetime.strftime('%Y-%m-%d %H:%M')}")
                        else:
                            print(f"⚠️ Could not calculate performance for {signal_type} signal from {signal_datetime.strftime('%Y-%m-%d %H:%M')}")
                        
                    except Exception as e:
                        print(f"⚠️ Error updating performance for signal {signal['signal_type']}: {e}")
                        continue
                        
            finally:
                await conn.close()
                
        except Exception as e:
            print(f"❌ Error in auto_update_signal_performance: {e}")
    
    def extract_pricing_data_from_api(self, api_data: Dict) -> Optional[List[Dict]]:
        """Extract OHLCV pricing data from API response"""
        try:
            # 🎯 PRIMARY: OHLC data (confirmed structure from API testing)
            if 'ohlc' in api_data and isinstance(api_data['ohlc'], list):
                ohlc_data = api_data['ohlc']
                if len(ohlc_data) > 0 and isinstance(ohlc_data[0], dict):
                    print(f"✅ Found OHLC data: {len(ohlc_data)} data points")
                    return ohlc_data
            
            # 🎯 SECONDARY: Separate arrays (also confirmed in API response)
            dates = api_data.get('dates', [])
            close_prices = api_data.get('close', [])
            open_prices = api_data.get('open', [])
            high_prices = api_data.get('high', [])
            low_prices = api_data.get('low', [])
            volumes = api_data.get('volume', [])
            
            if dates and close_prices and len(dates) == len(close_prices):
                print(f"✅ Found separate arrays: {len(dates)} data points")
                # Reconstruct OHLC format from separate arrays
                combined_data = []
                for i in range(len(dates)):
                    data_point = {
                        'date': dates[i],
                        'timestamp': dates[i],
                        't': dates[i],
                        'close': close_prices[i],
                        'c': close_prices[i],
                        'price': close_prices[i]  # Fallback price field
                    }
                    
                    # Add OHLV if available
                    if i < len(open_prices) and open_prices[i] is not None:
                        data_point['open'] = open_prices[i]
                        data_point['o'] = open_prices[i]
                    if i < len(high_prices) and high_prices[i] is not None:
                        data_point['high'] = high_prices[i]
                        data_point['h'] = high_prices[i]
                    if i < len(low_prices) and low_prices[i] is not None:
                        data_point['low'] = low_prices[i]
                        data_point['l'] = low_prices[i]
                    if i < len(volumes) and volumes[i] is not None:
                        data_point['volume'] = volumes[i]
                        data_point['v'] = volumes[i]
                    
                    combined_data.append(data_point)
                
                return combined_data
            
            # 🎯 FALLBACK: Other potential structures
            # Option 3: Direct price data in main response
            if 'prices' in api_data:
                return api_data['prices']
            
            # Option 4: Historical data section
            if 'historical' in api_data:
                return api_data['historical']
            
            # Option 5: Data array with timestamps and prices
            if 'data' in api_data and isinstance(api_data['data'], list):
                return api_data['data']
            
            # Option 6: Check if API data contains timestamp/price pairs
            if isinstance(api_data, dict):
                for key in ['chart_data', 'price_data', 'candles', 'bars']:
                    if key in api_data:
                        return api_data[key]
            
            print(f"⚠️ No pricing data found. API data keys: {list(api_data.keys())}")
            return None
            
        except Exception as e:
            print(f"⚠️ Error extracting pricing data: {e}")
            return None
    
    def calculate_performance_from_pricing(self, signal_datetime: datetime, pricing_data: List[Dict], timeframe: str) -> Optional[Dict]:
        """Calculate signal performance using pricing data"""
        try:
            if not pricing_data:
                return None
            
            # Find the price closest to signal time
            signal_price = self.find_closest_price(signal_datetime, pricing_data)
            if not signal_price:
                return None
            
            # Calculate target times for performance measurement
            # Updated to use 1h, 3h, 6h, 1d timeframes
            target_1h = signal_datetime + timedelta(hours=1)
            target_3h = signal_datetime + timedelta(hours=3)
            target_6h = signal_datetime + timedelta(hours=6)
            target_1d = signal_datetime + timedelta(days=1)
            
            # Find prices at target times
            performance = {
                'price_at_signal': signal_price,
                'price_after_1h': self.find_closest_price(target_1h, pricing_data),
                'price_after_3h': self.find_closest_price(target_3h, pricing_data),
                'price_after_6h': self.find_closest_price(target_6h, pricing_data),
                'price_after_1d': self.find_closest_price(target_1d, pricing_data)
            }
            
            return performance
            
        except Exception as e:
            print(f"⚠️ Error calculating performance: {e}")
            return None
    
    def find_closest_price(self, target_datetime: datetime, pricing_data: List[Dict]) -> Optional[float]:
        """Find the price closest to target datetime"""
        try:
            if not pricing_data:
                return None
            
            closest_price = None
            closest_diff = float('inf')
            
            for data_point in pricing_data:
                if not isinstance(data_point, dict):
                    continue
                    
                # Handle different timestamp formats in API data
                timestamp = None
                price = None
                
                # 🎯 PRIMARY: OHLC format from API (confirmed structure)
                if 't' in data_point and 'c' in data_point:
                    timestamp = data_point['t']  # Date in format "2025-05-28"
                    price = data_point['c']      # Close price
                
                # 🎯 SECONDARY: Alternative OHLC formats
                elif 'date' in data_point and 'close' in data_point:
                    timestamp = data_point['date']
                    price = data_point['close']
                elif 'timestamp' in data_point and 'price' in data_point:
                    timestamp = data_point['timestamp']
                    price = data_point['price']
                elif 'time' in data_point and 'value' in data_point:
                    timestamp = data_point['time']
                    price = data_point['value']
                elif 'datetime' in data_point and 'close' in data_point:
                    timestamp = data_point['datetime']
                    price = data_point['close']
                
                if timestamp and price is not None:
                    try:
                        # Parse timestamp from API format
                        if isinstance(timestamp, str):
                            if 'T' in timestamp:
                                # ISO format: "2025-05-28T09:30:00Z"
                                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            elif ' ' in timestamp:
                                # Full datetime: "2025-05-28 09:30:00"
                                dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                            else:
                                # Date only: "2025-05-28" (common in API response)
                                dt = datetime.strptime(timestamp, '%Y-%m-%d')
                                # For daily data, assume market close time (4 PM EST)
                                dt = dt.replace(hour=16, minute=0, second=0)
                        elif isinstance(timestamp, (int, float)):
                            # Unix timestamp
                            dt = datetime.fromtimestamp(timestamp)
                        else:
                            continue
                        
                        # Calculate time difference
                        diff = abs((target_datetime - dt).total_seconds())
                        
                        if diff < closest_diff:
                            closest_diff = diff
                            closest_price = float(price)
                            
                    except (ValueError, TypeError) as e:
                        continue
            
            # 🎯 ENHANCED: More generous time tolerance for daily data
            # Daily data: 24 hours tolerance (signals can be from any time of day)
            # Hourly data: 2 hours tolerance (more precision needed)
            max_tolerance = 86400  # 24 hours in seconds (for daily data)
            
            if closest_diff < max_tolerance and closest_price is not None:
                hours_diff = closest_diff / 3600
                print(f"🎯 Found price ${closest_price:.2f} within {hours_diff:.1f}h of target time")
                return closest_price
            else:
                print(f"⚠️ No price found within tolerance. Closest was {closest_diff/3600:.1f}h away")
            
            return None
            
        except Exception as e:
            print(f"⚠️ Error finding closest price: {e}")
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
                max_hours_ago = 2  #  STRICT: Only last 2 hours maximum
                print(f"🕐 Filtering for signals within last {max_hours_ago} hours")
            else:
                max_hours_ago = 2  #  STRICT: Only last 2 hours maximum
                print(f"📅 Filtering for signals within last {max_hours_ago} hours")
            
            for signal in signals:
                signal_date_str = signal.get('date', '')
                if not signal_date_str:
                    continue
                
                try:
                    # Handle different date formats
                    if ' ' in signal_date_str:
                        signal_datetime = datetime.strptime(signal_date_str, '%Y-%m-%d %H:%M:%S')
                    else:
                        signal_datetime = datetime.strptime(signal_date_str, '%Y-%m-%d')
                        # For daily signals, set time to market close (4 PM EST)
                        signal_datetime = signal_datetime.replace(hour=16)
                    
                    # Calculate age of signal
                    time_diff = current_datetime - signal_datetime
                    
                    if timeframe == '1h':
                        is_recent = time_diff.total_seconds() <= (max_hours_ago * 3600)
                    else:
                        is_recent = time_diff.total_seconds() <= (max_hours_ago * 3600)
                    
                    if is_recent:
                        signal['age_hours'] = time_diff.total_seconds() / 3600
                        recent_signals.append(signal)
                        
                        # Enhanced debug info
                        age_str = f"{time_diff.total_seconds()/3600:.1f}h"
                        print(f"   ✅ {signal.get('type', 'Unknown')} ({signal.get('strength', 'Unknown')}) - {age_str} ago")
                    
                except Exception as e:
                    print(f"⚠️ Error parsing signal date '{signal_date_str}': {e}")
                    continue
            
            print(f"📊 Found {len(recent_signals)} recent signals out of {len(signals)} total")
            return recent_signals
            
        except Exception as e:
            print(f"❌ Error checking for new signals: {e}")
            return []

    async def should_notify(self, signal: Dict, ticker: str, timeframe: str) -> bool:
        """Enhanced signal filtering with priority-based notification system, comprehensive tracking, and ML-based filtering"""
        if not signal:
            return False
        
        # Check if we've already sent this notification using the database
        signal_date = signal.get('date', '')
        signal_type = signal.get('type', '')
        strength = signal.get('strength', 'Unknown')
        system = signal.get('system', 'Unknown')
        
        if not signal_date or not signal_type:
            return False
        
        # Calculate priority score first
        should_send, priority_score = should_send_notification(signal, ticker, timeframe)
        
        # 🤖 NEW: Get ML prediction for filtering
        ml_prediction = None
        ml_should_send = True  # Default to True if ML fails
        
        try:
            from advanced_analytics import advanced_analytics
            
            # Create signal features for ML prediction
            signal_features = {
                'ticker': ticker,
                'timeframe': timeframe,
                'signal_type': signal_type,
                'strength': strength,
                'system': system,
                'signal_date': signal_date
            }
            
            # Get ML prediction
            ml_result = await advanced_analytics.predict_single_signal(signal_features)
            if ml_result and 'prediction' in ml_result:
                ml_prediction = ml_result['prediction']
                
                # ML filtering logic
                success_prob = ml_prediction['success_probability']
                risk_level = ml_prediction.get('risk_level', 'medium')
                confidence = ml_prediction.get('confidence', 'medium')
                
                # Don't send high-risk signals with low success probability
                if risk_level == 'high' and success_prob < 0.4:
                    # ml_should_send = False  # COMMENTED OUT FOR TESTING
                    print(f"🤖 ML Filter: Blocking high-risk signal {ticker} {signal_type} - {success_prob*100:.1f}% success, {risk_level} risk")
                
                # Boost high-confidence, high-success signals
                elif success_prob >= 0.7 and confidence == 'high':
                    ml_should_send = True
                    print(f"🤖 ML Boost: Promoting high-confidence signal {ticker} {signal_type} - {success_prob*100:.1f}% success")
                
        except Exception as e:
            print(f"⚠️ ML filtering failed for {ticker}: {e}")
            # Continue with regular filtering if ML fails
        
        # Check for duplicate in database
        is_duplicate = await check_duplicate(ticker, timeframe, signal_type, signal_date)
        
        # Determine skip reason and whether to send
        skip_reason = None
        will_send = False
        
        if is_duplicate:
            skip_reason = "duplicate_notification"
        elif not should_send:
            skip_reason = f"priority_below_threshold_{priority_score.priority_level.name.lower()}"
        elif not ml_should_send:
            skip_reason = "ml_filter_rejected_high_risk"
        else:
            will_send = True
        
        # Record EVERY signal we detect in the database for analytics
        await record_detected_signal(
            ticker=ticker,
            timeframe=timeframe, 
            signal_type=signal_type,
            signal_date=signal_date,
            strength=strength,
            system=system,
            priority_score=priority_score.total_score,
            priority_level=priority_score.priority_level.name,
            was_sent=will_send,
            skip_reason=skip_reason,
            signal_data={
                'base_score': priority_score.base_score,
                'strength_bonus': priority_score.strength_bonus,
                'system_bonus': priority_score.system_bonus,
                'ticker_bonus': priority_score.ticker_bonus,
                'timeframe_bonus': priority_score.timeframe_bonus,
                'urgency_bonus': priority_score.urgency_bonus,
                'pattern_bonus': priority_score.pattern_bonus,
                'is_vip_ticker': ticker in priority_manager.VIP_TICKERS,
                'is_vip_timeframe': timeframe in priority_manager.VIP_TIMEFRAMES,
                # 🤖 NEW: Store ML prediction data
                'ml_success_probability': ml_prediction['success_probability'] if ml_prediction else None,
                'ml_confidence': ml_prediction.get('confidence') if ml_prediction else None,
                'ml_risk_level': ml_prediction.get('risk_level') if ml_prediction else None,
                'ml_sample_size': ml_prediction.get('sample_size') if ml_prediction else None
            }
        )
        
        if will_send:
            ml_info = f" | ML: {ml_prediction['success_probability']*100:.1f}%" if ml_prediction else ""
            print(f"🎯 Priority notification: {ticker} {signal_type} - Priority: {priority_score.priority_level.name} (Score: {priority_score.total_score}){ml_info}")
        else:
            ml_info = f" | ML: {ml_prediction['success_probability']*100:.1f}%" if ml_prediction else ""
            print(f"⏸️ Skipped signal: {ticker} {signal_type} - Priority: {priority_score.priority_level.name} (Score: {priority_score.total_score}){ml_info} - Reason: {skip_reason}")
        
        return will_send
    
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
        """Send a signal notification to Discord with priority information"""
        try:
            channel = self.bot.get_channel(CHANNEL_ID)
            if not channel:
                print(f"❌ Channel {CHANNEL_ID} not found")
                return
            
            # Calculate priority score for display
            priority_score = calculate_signal_priority(signal, ticker, timeframe)
            priority_display = get_priority_display(priority_score)
            
            # Capture current price for this signal
            current_price = None
            try:
                # Fetch current data to get the latest price
                signal_timeline = self.fetch_signal_timeline(ticker, timeframe)
                if signal_timeline:
                    # Get the most recent price from the timeline
                    recent_data = signal_timeline[-1] if signal_timeline else None
                    if recent_data and 'price' in recent_data:
                        current_price = float(recent_data['price'])
                        print(f"📊 Captured current price for {ticker}: ${current_price:.4f}")
                    else:
                        print(f"⚠️ Could not extract current price from API data for {ticker}")
                else:
                    print(f"⚠️ No signal timeline data available for {ticker}")
            except Exception as e:
                print(f"⚠️ Error capturing current price for {ticker}: {e}")
                # Continue without price - we'll backfill later
            
            # Format the signal message
            message = self.format_signal_for_discord(signal, ticker, timeframe)
            
            # Add priority information to message
            message += f"\n{priority_display}"
            
            # Determine embed color based on priority level
            priority_colors = {
                'CRITICAL': 0xFF0000,  # Red
                'HIGH': 0xFF6600,      # Orange  
                'MEDIUM': 0x0099FF,    # Blue
                'LOW': 0x00FF00,       # Green
                'MINIMAL': 0x808080    # Gray
            }
            
            color = priority_colors.get(priority_score.priority_level.name, 0x0099ff)
            
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
            embed.add_field(
                name="Priority Score",
                value=f"{priority_score.total_score} ({priority_score.priority_level.name})",
                inline=True
            )
            
            # Add current price if captured
            if current_price:
                embed.add_field(
                    name="Price at Signal",
                    value=f"${current_price:.4f}",
                    inline=True
                )
            
            # Send message and get the message object
            
            #  NEW: Add ML Prediction scores 
            # TODO: Get actual ML prediction
            embed.add_field(
                name=" ML Success Rate",
                value="Checking...",
                inline=True
            )
            embed.add_field(
                name=" ML Confidence",
                value="Checking...",
                inline=True
            )
            embed.add_field(
                name=" Risk Level",
                value="Checking...",
                inline=True
            )
            discord_message = await channel.send(embed=embed)
            print(f"📤 Sent priority notification: {ticker} ({timeframe}) - {signal.get('type', 'Unknown')} [Priority: {priority_score.priority_level.name}]")
            
            # Record this notification in the database with enhanced priority tracking and current price
            success = await record_notification(
                ticker=ticker,
                timeframe=timeframe,
                signal_type=signal.get('type', ''),
                signal_date=signal.get('date', ''),
                strength=signal.get('strength'),
                system=signal.get('system'),
                discord_message_id=discord_message.id,
                priority_score=priority_score.total_score,
                priority_level=priority_score.priority_level.name,
                was_vip_ticker=ticker in priority_manager.VIP_TICKERS,
                was_vip_timeframe=timeframe in priority_manager.VIP_TIMEFRAMES,
                urgency_bonus=priority_score.urgency_bonus,
                pattern_bonus=priority_score.pattern_bonus,
                price_at_signal=current_price
            )
            
            if success:
                self.stats['signals_sent'] += 1
                print(f"💾 Recorded notification in database with price: ${current_price:.4f}" if current_price else "💾 Recorded notification in database (price capture failed)")
            else:
                print(f"⚠️ Failed to record notification in database")
            
        except Exception as e:
            print(f"❌ Error sending notification: {e}")
            self.stats['errors'] += 1

    async def cleanup_old_notifications(self, days: int = 30) -> int:
        """Clean up old notifications using database cleanup function"""
        try:
            from database import cleanup_old
            cleaned_count = await cleanup_old(days)
            return cleaned_count
        except Exception as e:
            print(f"❌ Error cleaning up notifications: {e}")
            return 0

def start_health_server():
    """Health check server temporarily disabled due to timezone issues"""
    print("🏥 Health check server disabled - will re-enable after timezone fixes")
    return None

# Discord Bot Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    global loop_start_time, bot_start_time, smart_scheduler, config
    bot_start_time = datetime.now(EST)
    print(f'🤖 {bot.user} has connected to Discord!')
    print(f"🚀 Bot started at: {bot_start_time.strftime('%Y-%m-%d %I:%M:%S %p EST')}")
    
    # Initialize database connection
    print("🗄️ Initializing database connection...")
    db_success = await init_database()
    if db_success:
        print("✅ Database connection established successfully")
        
        # ✅ NEW: Load configuration from database
        print("🔄 Loading configuration from database...")
        config_success = await config.load_from_database()
        if config_success:
            print("✅ Configuration loaded from PostgreSQL database")
        else:
            print("⚠️ Using fallback configuration from environment variables")
        
        # Build ticker combinations after loading config
        build_ticker_combinations()
        
        # Display loaded configuration
        print(f"📊 Loaded configuration:")
        print(f"   Ticker-Timeframe Combinations: {len(TICKER_TF_COMBINATIONS)}")
        for ticker, tf in TICKER_TF_COMBINATIONS[:10]:  # Show first 10
            print(f"   • {ticker} ({tf})")
        if len(TICKER_TF_COMBINATIONS) > 10:
            print(f"   ... and {len(TICKER_TF_COMBINATIONS) - 10} more")
        print(f"   Max signal age: {MAX_SIGNAL_AGE_DAYS} days")
        print(f"   Strong signals only: {ONLY_STRONG_SIGNALS}")
        
        # ✅ NEW: Initialize database-backed priority manager
        print("🎯 Initializing priority manager with database...")
        priority_success = await priority_manager.initialize()
        if priority_success:
            print("✅ Priority manager initialized with database configuration")
        else:
            print("⚠️ Priority manager using environment fallback configuration")
    else:
        print("❌ Failed to initialize database - notifications will not work properly")
        # Still load fallback config
        config.load_from_environment()
        priority_manager.db_config.load_from_environment()
        build_ticker_combinations()
    
    print(f"📊 Monitoring {len(TICKER_TF_COMBINATIONS)} ticker-timeframe combinations")
    for ticker, tf in TICKER_TF_COMBINATIONS[:10]:
        print(f"   • {ticker} ({tf})")
    if len(TICKER_TF_COMBINATIONS) > 10:
        print(f"   ... and {len(TICKER_TF_COMBINATIONS) - 10} more")
    
    print(f"🌐 API endpoint: {API_BASE_URL}")
    print(f"📡 Discord channel: {CHANNEL_ID}")
    
    # Railway deployment detection
    if os.getenv('RAILWAY_ENVIRONMENT'):
        print(f"🚂 Running on Railway deployment: {os.getenv('RAILWAY_ENVIRONMENT')}")
        print(f"🔧 Railway service: {os.getenv('RAILWAY_SERVICE_NAME', 'discord-bot')}")
    
    # Initialize scheduler based on configuration
    if USE_SMART_SCHEDULER:
        print("🎯 Initializing Smart Scheduler...")
        print("📅 Smart scheduling aligns signal checks with hourly candle closes")
        
        # Create smart scheduler with custom configuration
        smart_scheduler = create_smart_scheduler(
            signal_check_function=smart_signal_check,
            logger=logging.getLogger(__name__)
        )
        
        # Start the smart scheduler
        smart_scheduler.start()
        loop_start_time = datetime.now(EST)
        print(f"✅ Smart Scheduler started at: {loop_start_time.strftime('%Y-%m-%d %I:%M:%S %p EST')}")
        
    else:
        print("⏰ Using legacy fixed-interval scheduler...")
        print(f"⏰ Signal check interval: {CHECK_INTERVAL} seconds ({CHECK_INTERVAL/60:.1f} minutes)")
        
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
        
        # Periodic cleanup of old notifications (every 10 cycles) - DISABLED
        # if checks_completed % 10 == 0:
        #     cleaned_count = await notifier.cleanup_old_notifications()
        #     if cleaned_count > 0:
        #         print(f"🧹 Periodic cleanup: removed {cleaned_count} old notification entries")
        
        # ✅ NEW: Update daily analytics (every 5 cycles)
        if checks_completed % 5 == 0:
            try:
                analytics_success = await update_daily_analytics()
                if analytics_success:
                    print(f"📊 Updated daily analytics for today")
                else:
                    print(f"⚠️ Failed to update daily analytics")
            except Exception as e:
                print(f"❌ Error updating analytics (non-critical): {e}")
                # Don't let analytics errors break the main signal checking loop
        
        # Check each ticker across all timeframes
        api_errors = 0
        discord_errors = 0
        
        current_hour = cycle_start.hour
        
        for ticker in TICKERS:
            for timeframe in TIMEFRAMES:
                # ⏰ TIMEFRAME-AWARE CHECKING: Only check timeframes at their candle close times
                if timeframe == '3h' and current_hour not in [23, 2, 5, 8, 11, 14, 17, 20]:
                    print(f"⏭️ Skipping {ticker} ({timeframe}) - not a 3h candle close hour")
                    continue
                elif timeframe == '6h' and current_hour not in [2, 8, 14, 20]:
                    print(f"⏭️ Skipping {ticker} ({timeframe}) - not a 6h candle close hour")
                    continue  
                elif timeframe == '1d' and current_hour % 4 != 0:  # Every 4 hours for stocks (16:xx) and crypto (20:xx)
                    print(f"⏭️ Skipping {ticker} ({timeframe}) - not a daily candle close hour (checks at 00, 04, 08, 12, 16, 20)")
                    continue
                # 1h timeframe runs every hour (no skip condition)
                
                try:
                    print(f"\n📊 Checking {ticker} ({timeframe})...")
                    
                    # Get recent signals using comprehensive detection
                    recent_signals = notifier.check_for_new_signals(ticker, timeframe)
                    total_signals += len(recent_signals)
                    
                    if recent_signals:
                        print(f"✅ Found {len(recent_signals)} recent signals for {ticker} ({timeframe})")
                        
                        # Filter signals that should trigger notifications
                        notify_signals = []
                        for signal in recent_signals:
                            should_notify_result = await notifier.should_notify(signal, ticker, timeframe)
                            if should_notify_result:
                                notify_signals.append(signal)
                        
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
    valid_timeframes = ['15m', '30m', '1h', '3h', '6h', '1d', '2d', '3d', '1wk']
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
    if USE_SMART_SCHEDULER and smart_scheduler:
        # Smart scheduler timing
        if not smart_scheduler.is_running():
            await ctx.send("❌ Smart Scheduler is not running")
            return
        
        status_info = smart_scheduler.get_status_info()
        
        embed = discord.Embed(
            title="⏰ Smart Scheduler Timer",
            color=0x00ff88,
            timestamp=datetime.now(EST)
        )
        
        embed.add_field(
            name="⏳ Next Check",
            value=f"`{status_info['time_until_next']}`",
            inline=True
        )
        
        embed.add_field(
            name="🕐 Next Check Time (EST)",
            value=f"`{status_info['next_run_time']}`",
            inline=True
        )
        
        embed.add_field(
            name="📋 Check Reason",
            value=f"`{status_info['next_run_reason']}`",
            inline=True
        )
        
        embed.add_field(
            name="📈 Market Hours",
            value=f"`{'Yes' if status_info['is_market_hours'] else 'No'}`",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Scheduler Type",
            value="`Smart Scheduler`",
            inline=True
        )
        
        embed.add_field(
            name="🔄 Checks Completed",
            value=f"`{checks_completed}`",
            inline=True
        )
        
        # Show upcoming runs
        if status_info['upcoming_runs']:
            upcoming_text = ""
            for i, run in enumerate(status_info['upcoming_runs'][:3], 1):
                priority_icon = "⭐" if run['is_priority'] else "📊"
                market_icon = "📈" if run['is_market_hours'] else "🌙"
                upcoming_text += f"{i}. {run['time']} {priority_icon} {market_icon}\n"
            
            embed.add_field(
                name="📅 Upcoming Checks",
                value=upcoming_text,
                inline=False
            )
        
        embed.set_footer(text="⭐ Priority runs align with hourly candle closes • 📈 Market hours • 🌙 After hours")
        
    else:
        # Legacy scheduler timing
        if not signal_check_loop.is_running():
            await ctx.send("❌ Signal monitoring is not running")
            return

        now = datetime.now(EST)
        
        if loop_start_time:
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
                title="⏰ Legacy Scheduler Timer",
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
            embed.add_field(name="🕐 Next Check At (EST)", value=f"`{next_cycle_time.strftime('%I:%M:%S %p')}`", inline=True)
            embed.add_field(name="🔄 Check Interval", value=f"`{CHECK_INTERVAL} seconds`", inline=True)
            
            # Progress bar
            progress = 1 - (time_until_next.total_seconds() / CHECK_INTERVAL)
            bar_length = 20
            filled = int(progress * bar_length)
            bar = "█" * filled + "░" * (bar_length - filled)
            embed.add_field(name="📊 Progress", value=f"`{bar}`", inline=False)
        else:
            embed = discord.Embed(title="⏰ Timer", description="⚠️ No timing information available", color=0xff0000)
    
    await ctx.send(embed=embed)

@bot.command(name='schedule')
async def show_schedule(ctx):
    """Show smart scheduler configuration and upcoming runs"""
    if not USE_SMART_SCHEDULER or not smart_scheduler:
        await ctx.send("❌ Smart Scheduler is not enabled. Set `USE_SMART_SCHEDULER=true` in .env to enable.")
        return
    
    status_info = smart_scheduler.get_status_info()
    
    embed = discord.Embed(
        title="🎯 Smart Scheduler Configuration",
        description="Signal checks aligned with market candle closes",
        color=0x0099ff,
        timestamp=datetime.now(EST)
    )
    
    # Current status
    embed.add_field(
        name="📊 Current Status",
        value=f"""
**Running:** {'✅ Yes' if status_info['running'] else '❌ No'}
**Current Time:** {status_info['current_time']}
**Market Hours:** {'📈 Yes' if status_info['is_market_hours'] else '🌙 No'}
        """,
        inline=False
    )
    
    # Schedule configuration
    embed.add_field(
        name="⏰ Schedule Configuration",
        value=f"""
**Market Hours:** {smart_scheduler.run_at_minutes} minutes past each hour
**After Hours:** {smart_scheduler.priority_run_minutes} minutes past each hour
**Market Open:** 9:30 AM EST
**Market Close:** 4:00 PM EST
        """,
        inline=False
    )
    
    # Next runs
    if status_info['upcoming_runs']:
        upcoming_text = ""
        for i, run in enumerate(status_info['upcoming_runs'], 1):
            priority_icon = "⭐" if run['is_priority'] else "📊"
            market_icon = "📈" if run['is_market_hours'] else "🌙"
            upcoming_text += f"{i}. **{run['time']}** {priority_icon} {market_icon}\n   _{run['reason']}_\n"
        
        embed.add_field(
            name="📅 Next 3 Scheduled Runs",
            value=upcoming_text,
            inline=False
        )
    
    embed.set_footer(text="⭐ Priority runs (hourly candles) • 📊 Regular runs • 📈 Market hours • 🌙 After hours")
    
    await ctx.send(embed=embed)

@bot.command(name='scheduler')
async def scheduler_control(ctx, action: str = None):
    """Control the smart scheduler
    
    Usage:
    !scheduler - Show scheduler status
    !scheduler start - Start the smart scheduler
    !scheduler stop - Stop the smart scheduler
    !scheduler restart - Restart the smart scheduler
    !scheduler switch - Switch between smart and legacy scheduler
    """
    global smart_scheduler, USE_SMART_SCHEDULER
    
    if action is None:
        # Show status
        embed = discord.Embed(
            title="🎛️ Scheduler Control",
            color=0x0099ff,
            timestamp=datetime.now(EST)
        )
        
        scheduler_type = "Smart Scheduler" if USE_SMART_SCHEDULER else "Legacy Scheduler"
        running_status = "❌ Not Running"
        
        if USE_SMART_SCHEDULER and smart_scheduler:
            running_status = "✅ Running" if smart_scheduler.is_running() else "❌ Stopped"
        elif not USE_SMART_SCHEDULER and signal_check_loop.is_running():
            running_status = "✅ Running"
        
        embed.add_field(
            name="📊 Current Configuration",
            value=f"""
**Type:** {scheduler_type}
**Status:** {running_status}
**Checks Completed:** {checks_completed}
            """,
            inline=False
        )
        
        embed.add_field(
            name="🎮 Available Commands",
            value="""
`!scheduler start` - Start scheduler
`!scheduler stop` - Stop scheduler  
`!scheduler restart` - Restart scheduler
`!scheduler switch` - Switch scheduler type
            """,
            inline=False
        )
        
        await ctx.send(embed=embed)
        return
    
    action = action.lower()
    
    if action == "start":
        if USE_SMART_SCHEDULER:
            if smart_scheduler and smart_scheduler.is_running():
                await ctx.send("⚠️ Smart Scheduler is already running")
            else:
                if not smart_scheduler:
                    smart_scheduler = create_smart_scheduler(smart_signal_check)
                smart_scheduler.start()
                await ctx.send("✅ Smart Scheduler started")
        else:
            if signal_check_loop.is_running():
                await ctx.send("⚠️ Legacy scheduler is already running")
            else:
                signal_check_loop.start()
                await ctx.send("✅ Legacy scheduler started")
    
    elif action == "stop":
        if USE_SMART_SCHEDULER and smart_scheduler:
            smart_scheduler.stop()
            await ctx.send("⏹️ Smart Scheduler stopped")
        elif not USE_SMART_SCHEDULER:
            signal_check_loop.stop()
            await ctx.send("⏹️ Legacy scheduler stopped")
        else:
            await ctx.send("❌ No scheduler to stop")
    
    elif action == "restart":
        if USE_SMART_SCHEDULER and smart_scheduler:
            smart_scheduler.stop()
            await asyncio.sleep(2)
            smart_scheduler.start()
            await ctx.send("🔄 Smart Scheduler restarted")
        elif not USE_SMART_SCHEDULER:
            signal_check_loop.restart()
            await ctx.send("🔄 Legacy scheduler restarted")
        else:
            await ctx.send("❌ No scheduler to restart")
    
    elif action == "switch":
        await ctx.send("🔧 Scheduler switching requires bot restart. Update `USE_SMART_SCHEDULER` in .env and restart the bot.")
    
    else:
        await ctx.send(f"❌ Unknown action '{action}'. Use: start, stop, restart, or switch")

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
        now = datetime.now(EST)  # Use timezone-aware datetime
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
    embed.add_field(name="📈 Total Tickers", value=f"`{len(config.tickers)}`", inline=True)
    embed.add_field(name="⏱️ Total Timeframes", value=f"`{len(config.timeframes)}`", inline=True)
    embed.add_field(name="🔄 Check Interval", value=f"`{CHECK_INTERVAL} seconds`", inline=True)
    embed.add_field(name="📅 Max Signal Age", value=f"`{MAX_SIGNAL_AGE_DAYS} days`", inline=True)
    embed.add_field(name="💪 Strong Signals Only", value=f"`{ONLY_STRONG_SIGNALS}`", inline=True)
    embed.add_field(name="🌐 API URL", value=f"`{API_BASE_URL}`", inline=True)
    
    if TICKER_TIMEFRAMES:
        embed.add_field(name="⚙️ Configuration Mode", value="`Per-Ticker Timeframes`", inline=True)
    else:
        embed.add_field(name="⚙️ Configuration Mode", value="`Multi-Timeframe`", inline=True)
    
    embed.add_field(name="💾 Configuration Source", value="✅ **PostgreSQL Database**\n(Single source of truth)", inline=True)
    
    embed.set_footer(text="💡 Configuration loaded from PostgreSQL database only")
    
    await ctx.send(embed=embed)

@bot.command(name='tickersync')
async def ticker_sync_command(ctx):
    """Sync bot with database tickers (loads from PostgreSQL)"""
    try:
        embed = discord.Embed(
            title="🔄 Ticker Database Sync",
            description="Reloading ticker configuration from PostgreSQL database",
            color=0xff6600,
            timestamp=datetime.now(EST)
        )
        
        # Show current state
        embed.add_field(
            name="Before Sync",
            value=f"**Tickers:** {len(config.tickers)}\n**Combinations:** {len(TICKER_TF_COMBINATIONS)}",
            inline=True
        )
        
        # Reload from database
        config_success = await config.load_from_database()
        
        if config_success:
            # Rebuild combinations
            build_ticker_combinations()
            
            embed.add_field(
                name="After Sync",
                value=f"**Tickers:** {len(config.tickers)}\n**Combinations:** {len(TICKER_TF_COMBINATIONS)}",
                inline=True
            )
            
            embed.add_field(
                name="✅ Sync Successful",
                value=f"Configuration reloaded from PostgreSQL database\n**Active Tickers:** {', '.join(config.tickers[:5])}{'...' if len(config.tickers) > 5 else ''}",
                inline=False
            )
            embed.color = 0x00ff00
        else:
            embed.add_field(
                name="❌ Sync Failed",
                value="Failed to reload from database, using current configuration",
                inline=False
            )
            embed.color = 0xff0000
        
        embed.set_footer(text="💡 Bot configuration is always loaded from PostgreSQL database")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error syncing tickers: {e}")

@bot.command(name='notifications')
async def notification_stats(ctx):
    """Show notification statistics from database"""
    try:
        # Get database statistics
        stats = await get_stats()
        
        embed = discord.Embed(
            title="📊 Notification Statistics",
            color=0x0099ff,
            timestamp=datetime.now(EST)
        )
        
        embed.add_field(
            name="📨 Total Notifications", 
            value=f"`{stats.get('total_notifications', 0)}`", 
            inline=True
        )
        embed.add_field(
            name="🆕 Last 24 Hours", 
            value=f"`{stats.get('last_24h', 0)}`", 
            inline=True
        )
        
        most_active = stats.get('most_active_ticker')
        if most_active:
            embed.add_field(
                name="📈 Most Active Ticker", 
                value=f"`{most_active['ticker']}` ({most_active['count']} signals)", 
                inline=True
            )
        
        most_common = stats.get('most_common_signal')
        if most_common:
            embed.add_field(
                name="🔔 Most Common Signal", 
                value=f"`{most_common['signal_type'][:30]}...` ({most_common['count']})", 
                inline=True
            )
        
        embed.add_field(
            name="💾 Storage", 
            value="PostgreSQL Database", 
            inline=True
        )
        embed.add_field(
            name="🔧 Duplicate Prevention", 
            value="Database Constraints", 
            inline=True
        )
        
        embed.set_footer(text="💡 Database auto-cleans entries older than 30 days")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error getting notification stats: {e}")

@bot.command(name='cleanup')
async def manual_cleanup(ctx):
    """Manually trigger cleanup of old notification entries from database"""
    try:
        # Perform database cleanup
        cleaned_count = await cleanup_old(days=30)
        
        embed = discord.Embed(
            title="🧹 Database Cleanup Complete",
            color=0x00ff00,
            timestamp=datetime.now(EST)
        )
        
        embed.add_field(name="🗑️ Removed", value=f"`{cleaned_count} entries`", inline=True)
        embed.add_field(name="📅 Older Than", value="`30 days`", inline=True)
        
        if cleaned_count > 0:
            embed.add_field(
                name="✅ Result", 
                value=f"Successfully cleaned up {cleaned_count} old notification entries from database", 
                inline=False
            )
        else:
            embed.add_field(name="ℹ️ Result", value="No old entries found to clean up", inline=False)
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error during cleanup: {e}")

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
    global config
    try:
        ticker = ticker.upper().strip()
        
        # Validation
        if not ticker:
            await ctx.send("❌ Please provide a valid ticker symbol")
            return
            
        if ticker in config.tickers:
            await ctx.send(f"⚠️ **{ticker}** is already being monitored")
            return
            
        if len(config.tickers) >= config.max_tickers:
            await ctx.send(f"❌ Maximum ticker limit reached ({config.max_tickers}). Remove a ticker first.")
            return
            
        # Basic ticker validation (alphanumeric, dash, dot)
        import re
        if not re.match(r'^[A-Z0-9.-]+$', ticker):
            await ctx.send(f"❌ Invalid ticker format: **{ticker}**\nTickers should contain only letters, numbers, dots, and dashes.")
            return
            
        # Add ticker to database
        db_success = await config.add_ticker(ticker)
        
        if db_success:
            # Update global variables and rebuild combinations
            build_ticker_combinations()
            
            # Create success embed
            embed = discord.Embed(
                title="✅ Ticker Added Successfully!",
                description=f"**{ticker}** has been added to the monitoring list",
                color=0x00ff00
            )
            embed.add_field(
                name="📊 Current Status", 
                value=f"Monitoring **{len(config.tickers)}** tickers across **{len(config.timeframes)}** timeframes\n"
                      f"Total combinations: **{len(TICKER_TF_COMBINATIONS)}**\n"
                      f"**Active immediately** - no restart required",
                inline=False
            )
            embed.add_field(
                name="🔄 Next Check", 
                value="The new ticker will be included in the next signal check cycle",
                inline=False
            )
            embed.add_field(
                name="💾 Database Storage",
                value="✅ Ticker saved to PostgreSQL database",
                inline=False
            )
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Failed to add ticker **{ticker}** to database")
        
    except Exception as e:
        await ctx.send(f"❌ Error adding ticker: {str(e)}")

@bot.command(name='removeticker')
async def remove_ticker_command(ctx, ticker: str):
    """Remove a ticker from the monitoring list"""
    global config
    try:
        ticker = ticker.upper().strip()
        
        if not ticker:
            await ctx.send("❌ Please provide a valid ticker symbol")
            return
            
        if ticker not in config.tickers:
            await ctx.send(f"⚠️ **{ticker}** is not in the monitoring list")
            return
            
        if len(config.tickers) <= 1:
            await ctx.send("❌ Cannot remove the last ticker. At least one ticker must be monitored.")
            return
            
        # Remove ticker from database
        db_success = await config.remove_ticker(ticker)
        
        if db_success:
            # Update global variables and rebuild combinations
            build_ticker_combinations()
            
            # Create success embed
            embed = discord.Embed(
                title="🗑️ Ticker Removed Successfully!",
                description=f"**{ticker}** has been removed from the monitoring list",
                color=0xff9900
            )
            embed.add_field(
                name="📊 Current Status", 
                value=f"Monitoring **{len(config.tickers)}** tickers across **{len(config.timeframes)}** timeframes\n"
                      f"Total combinations: **{len(TICKER_TF_COMBINATIONS)}**",
                inline=False
            )
            embed.add_field(
                name="💾 Database Storage",
                value="✅ Ticker removed from PostgreSQL database",
                inline=False
            )
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Failed to remove ticker **{ticker}** from database")
        
    except Exception as e:
        await ctx.send(f"❌ Error removing ticker: {str(e)}")

@bot.command(name='listtickers')
async def list_tickers_command(ctx):
    """List all currently monitored tickers"""
    try:
        # Use global config
        tickers = config.tickers
        timeframes = config.timeframes
        max_tickers = config.max_tickers
        
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
        
        embed.add_field(
            name="💾 Data Source",
            value="✅ PostgreSQL Database\n(Single source of truth)",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error listing tickers: {str(e)}")

@bot.command(name='timeframes')
async def timeframes_command(ctx, action: str = None, timeframe: str = None):
    """Manage timeframes: !timeframes list|add|remove [timeframe]"""
    global config
    try:
        current_timeframes = config.timeframes
        allowed_timeframes = config.allowed_timeframes
        
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
                value=f"**Tickers**: {len(config.tickers)}\n"
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
            
            embed.add_field(
                name="💾 Data Source",
                value="✅ PostgreSQL Database",
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
            config.timeframes = current_timeframes
            
            # Update globals
            build_ticker_combinations()
            
            embed = discord.Embed(
                title="✅ Timeframe Added!",
                description=f"**{timeframe}** has been added to active timeframes",
                color=0x00ff00
            )
            embed.add_field(
                name="📊 New Status",
                value=f"Total combinations: **{len(TICKER_TF_COMBINATIONS)}**\n"
                      f"({len(config.tickers)} tickers × {len(config.timeframes)} timeframes)",
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
            config.timeframes = current_timeframes
            
            # Update globals
            build_ticker_combinations()
            
            embed = discord.Embed(
                title="🗑️ Timeframe Removed!",
                description=f"**{timeframe}** has been removed from active timeframes",
                color=0xff9900
            )
            embed.add_field(
                name="📊 New Status",
                value=f"Total combinations: **{len(TICKER_TF_COMBINATIONS)}**\n"
                      f"({len(config.tickers)} tickers × {len(config.timeframes)} timeframes)",
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
        now = datetime.now(EST)  # Use timezone-aware datetime
        
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
        now = datetime.now(EST)  # Use timezone-aware datetime
        
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

@bot.command(name='priority')
async def priority_settings(ctx, action: str = None, sub_action: str = None, ticker: str = None):
    """Manage priority settings for signal notifications
    
    Usage:
    !priority - Show current priority settings
    !priority level <CRITICAL|HIGH|MEDIUM|LOW|MINIMAL> - Set minimum priority level
    !priority vip add <TICKER> - Add ticker to VIP list
    !priority vip remove <TICKER> - Remove ticker from VIP list
    !priority test <TICKER> - Test priority scoring for a ticker
    !priority reload - Reload configuration from database
    """
    from priority_manager import priority_manager
    
    embed = discord.Embed(
        title="🎯 Priority Management",
        color=0x0099ff,
        timestamp=datetime.now(EST)
    )
    
    if action is None:
        # Show current settings
        embed.add_field(
            name="Current Settings",
            value=f"""
**Minimum Priority Level:** {priority_manager.MIN_PRIORITY_LEVEL}
**Critical Threshold:** {priority_manager.CRITICAL_THRESHOLD}
**High Threshold:** {priority_manager.HIGH_THRESHOLD}
**Medium Threshold:** {priority_manager.MEDIUM_THRESHOLD}
**Low Threshold:** {priority_manager.LOW_THRESHOLD}
            """,
            inline=False
        )
        
        embed.add_field(
            name="VIP Tickers",
            value=", ".join(sorted(priority_manager.VIP_TICKERS)) or "None",
            inline=False
        )
        
        embed.add_field(
            name="VIP Timeframes", 
            value=", ".join(sorted(priority_manager.VIP_TIMEFRAMES)) or "None",
            inline=False
        )
        
        embed.add_field(
            name="Available Commands",
            value="""
`!priority level <LEVEL>` - Set minimum priority
`!priority vip add <TICKER>` - Add VIP ticker
`!priority vip remove <TICKER>` - Remove VIP ticker
`!priority test <TICKER>` - Test priority scoring
`!priority reload` - Reload from database
            """,
            inline=False
        )
        
        embed.add_field(
            name="💾 Configuration Source",
            value="✅ **PostgreSQL Database**\n(Single source of truth)",
            inline=False
        )
        
    elif action == "level" and sub_action:
        valid_levels = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'MINIMAL']
        if sub_action.upper() in valid_levels:
            success = await priority_manager.set_min_priority_level(sub_action.upper())
            if success:
                embed.add_field(
                    name="✅ Priority Level Updated",
                    value=f"Minimum priority level set to: **{sub_action.upper()}**\nSaved to PostgreSQL database",
                    inline=False
                )
                embed.color = 0x00ff00
            else:
                embed.add_field(
                    name="❌ Update Failed",
                    value="Failed to save priority level to database",
                    inline=False
                )
                embed.color = 0xff0000
        else:
            embed.add_field(
                name="❌ Invalid Priority Level",
                value=f"Valid levels: {', '.join(valid_levels)}",
                inline=False
            )
    
    elif action == "vip" and sub_action and ticker:
        ticker = ticker.upper()
        
        if sub_action.lower() == "add":
            success = await priority_manager.add_vip_ticker(ticker)
            
            if success:
                embed.add_field(
                    name="✅ VIP Ticker Added",
                    value=f"Added **{ticker}** to VIP tickers list\n**Current VIP Tickers:** {', '.join(sorted(priority_manager.VIP_TICKERS))}",
                    inline=False
                )
                embed.add_field(
                    name="💾 Database Storage",
                    value="✅ VIP tickers saved to PostgreSQL database",
                    inline=False
                )
                embed.color = 0x00ff00
            else:
                embed.add_field(
                    name="❌ Add Failed",
                    value=f"Failed to add **{ticker}** to VIP tickers database",
                    inline=False
                )
                embed.color = 0xff0000
                
        elif sub_action.lower() == "remove":
            if ticker in priority_manager.VIP_TICKERS:
                success = await priority_manager.remove_vip_ticker(ticker)
                
                if success:
                    embed.add_field(
                        name="✅ VIP Ticker Removed", 
                        value=f"Removed **{ticker}** from VIP tickers list\n**Current VIP Tickers:** {', '.join(sorted(priority_manager.VIP_TICKERS))}",
                        inline=False
                    )
                    embed.add_field(
                        name="💾 Database Storage",
                        value="✅ VIP tickers updated in PostgreSQL database",
                        inline=False
                    )
                    embed.color = 0x00ff00
                else:
                    embed.add_field(
                        name="❌ Remove Failed",
                        value=f"Failed to remove **{ticker}** from VIP tickers database",
                        inline=False
                    )
                    embed.color = 0xff0000
            else:
                embed.add_field(
                    name="⚠️ Ticker Not Found",
                    value=f"**{ticker}** is not in the VIP tickers list",
                    inline=False
                )
        else:
            embed.add_field(
                name="❌ Invalid VIP Action",
                value="Use `add` or `remove` with VIP commands",
                inline=False
            )
    
    elif action == "test" and sub_action:
        test_ticker = sub_action.upper()
        # Create a sample signal for testing
        test_signal = {
            'type': 'WT Buy Signal',
            'strength': 'Strong',
            'system': 'Wave Trend',
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        priority_score = calculate_signal_priority(test_signal, test_ticker, '1d')
        
        embed.add_field(
            name=f"🧪 Priority Test: {test_ticker}",
            value=priority_manager.get_debug_breakdown(priority_score),
            inline=False
        )
    
    elif action == "reload":
        success = await priority_manager.reload_from_database()
        if success:
            embed.add_field(
                name="✅ Configuration Reloaded",
                value="Priority configuration reloaded from PostgreSQL database",
                inline=False
            )
            embed.color = 0x00ff00
        else:
            embed.add_field(
                name="❌ Reload Failed",
                value="Failed to reload configuration from database",
                inline=False
            )
            embed.color = 0xff0000
    
    else:
        embed.add_field(
            name="❌ Invalid Command",
            value="""
**Usage Examples:**
`!priority` - Show current settings
`!priority level HIGH` - Set minimum priority to HIGH
`!priority vip add MSFT` - Add MSFT to VIP tickers
`!priority vip remove MSFT` - Remove MSFT from VIP tickers
`!priority test AAPL` - Test priority scoring for AAPL
`!priority reload` - Reload from database
            """,
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='prioritystats')
async def priority_statistics(ctx):
    """Show priority statistics for recent signals"""
    from priority_manager import priority_manager
    
    try:
        # Get recent notifications from database
        recent_notifications = await get_stats()
        
        embed = discord.Embed(
            title="📊 Priority Statistics",
            color=0x0099ff,
            timestamp=datetime.now(EST)
        )
        
        # Show priority distribution if we have notifications
        if recent_notifications and recent_notifications.get('total_notifications', 0) > 0:
            embed.add_field(
                name="Recent Activity",
                value=f"""
**Total Notifications:** {recent_notifications.get('total_notifications', 0)}
**Total Detected:** {recent_notifications.get('total_detected', 0)}
**Last 24 Hours:** {recent_notifications.get('last_24h', 0)}
**Last 7 Days:** {recent_notifications.get('last_7d', 0)}
**Utilization Rate:** {recent_notifications.get('utilization_rate_24h', 0)}%
                """,
                inline=False
            )
            
            # Priority distribution
            priority_dist_raw = recent_notifications.get('priority_distribution', {})
            if priority_dist_raw:
                # Handle both dict and JSON string formats
                if isinstance(priority_dist_raw, str):
                    try:
                        import json
                        priority_dist = json.loads(priority_dist_raw)
                    except json.JSONDecodeError:
                        priority_dist = {}
                else:
                    priority_dist = priority_dist_raw
                    
                if priority_dist:
                    embed.add_field(
                        name="Priority Distribution (24h)",
                        value=f"""
🚨 **Critical:** {priority_dist.get('CRITICAL', 0)}
⚠️ **High:** {priority_dist.get('HIGH', 0)}
📊 **Medium:** {priority_dist.get('MEDIUM', 0)}
📢 **Low:** {priority_dist.get('LOW', 0)}
📝 **Minimal:** {priority_dist.get('MINIMAL', 0)}
                        """,
                        inline=True
                    )
        
        embed.add_field(
            name="Priority Thresholds",
            value=f"""
🚨 **Critical:** {priority_manager.CRITICAL_THRESHOLD}+ points
⚠️ **High:** {priority_manager.HIGH_THRESHOLD}+ points  
📊 **Medium:** {priority_manager.MEDIUM_THRESHOLD}+ points
📢 **Low:** {priority_manager.LOW_THRESHOLD}+ points
📝 **Minimal:** Below {priority_manager.LOW_THRESHOLD} points
            """,
            inline=False
        )
        
        embed.add_field(
            name="Scoring System",
            value="""
**Base Score:** 10 points
**Strength Bonus:** Up to 25 points
**System Bonus:** Up to 20 points
**VIP Ticker Bonus:** 15 points
**VIP Timeframe Bonus:** 10 points
**Urgency Bonus:** Up to 20 points
**Pattern Bonus:** Up to 30 points
            """,
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error getting priority statistics: {e}")

@bot.command(name='analytics')
async def signal_analytics(ctx, days: int = 7):
    """Show comprehensive signal analytics
    
    Usage:
    !analytics - Show 7-day analytics
    !analytics 3 - Show 3-day analytics
    !analytics 14 - Show 14-day analytics
    """
    try:
        if days < 1 or days > 30:
            await ctx.send("❌ Days must be between 1 and 30")
            return
            
        analytics = await get_priority_analytics(days)
        
        if not analytics:
            await ctx.send("❌ No analytics data available")
            return
            
        embed = discord.Embed(
            title=f"📈 Signal Analytics ({days} days)",
            color=0x00ff88,
            timestamp=datetime.now(EST)
        )
        
        # Detection overview
        detection_stats = analytics.get('detection_stats', {})
        if detection_stats:
            total_detected = detection_stats.get('total_detected', 0)
            total_sent = detection_stats.get('total_sent', 0)
            total_skipped = detection_stats.get('total_skipped', 0)
            avg_priority = detection_stats.get('avg_priority_score', 0)
            
            embed.add_field(
                name="🔍 Detection Overview",
                value=f"""
**Total Detected:** {total_detected}
**Notifications Sent:** {total_sent}
**Signals Skipped:** {total_skipped}
**Utilization Rate:** {(total_sent/max(total_detected,1)*100):.1f}%
**Avg Priority Score:** {avg_priority:.1f}
                """,
                inline=False
            )
            
            # Priority breakdown
            embed.add_field(
                name="🏆 Priority Breakdown",
                value=f"""
🚨 **Critical:** {detection_stats.get('critical_count', 0)}
⚠️ **High:** {detection_stats.get('high_count', 0)}
📊 **Medium:** {detection_stats.get('medium_count', 0)}
📢 **Low:** {detection_stats.get('low_count', 0)}
📝 **Minimal:** {detection_stats.get('minimal_count', 0)}
                """,
                inline=True
            )
        
        # Top systems
        system_stats = analytics.get('system_stats', [])
        if system_stats:
            top_systems = system_stats[:5]
            systems_text = ""
            for system in top_systems:
                sent_rate = (system['sent_signals'] / max(system['total_signals'], 1)) * 100
                systems_text += f"**{system['system']}:** {system['total_signals']} detected, {system['sent_signals']} sent ({sent_rate:.1f}%)\n"
            
            embed.add_field(
                name="🏗️ Top Systems",
                value=systems_text[:1000],
                inline=False
            )
        
        # Top skipped signals (missed opportunities)
        top_skipped = analytics.get('top_skipped', [])
        if top_skipped:
            skipped_text = ""
            for signal in top_skipped[:5]:
                skipped_text += f"**{signal['ticker']} {signal['signal_type']}:** Score {signal['priority_score']} ({signal['count']}x)\n"
            
            embed.add_field(
                name="⚠️ Top Missed Opportunities",
                value=skipped_text[:1000],
                inline=False
            )
        
        embed.set_footer(text="💡 Use !utilization for detailed signal usage analysis")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error getting analytics: {e}")

@bot.command(name='utilization')
async def signal_utilization(ctx):
    """Show detailed signal utilization analysis (last 24 hours)"""
    try:
        utilization = await get_signal_utilization()
        
        if not utilization:
            await ctx.send("❌ No utilization data available")
            return
            
        embed = discord.Embed(
            title="🔬 Signal Utilization Analysis (24h)",
            description="Comprehensive breakdown of signal detection and usage",
            color=0xff6600,
            timestamp=datetime.now(EST)
        )
        
        # Signal type utilization
        signal_types = utilization.get('signal_type_stats', [])
        if signal_types:
            top_signals = signal_types[:8]
            signal_text = ""
            for signal in top_signals:
                utilization_rate = (signal['sent'] / max(signal['detected'], 1)) * 100
                signal_text += f"**{signal['signal_type'][:20]}:** {signal['detected']} detected, {signal['sent']} sent ({utilization_rate:.1f}%)\n"
            
            embed.add_field(
                name="📊 Signal Type Utilization",
                value=signal_text[:1000],
                inline=False
            )
        
        # Timeframe utilization  
        timeframes = utilization.get('timeframe_stats', [])
        if timeframes:
            timeframe_text = ""
            for tf in timeframes:
                utilization_rate = (tf['sent'] / max(tf['detected'], 1)) * 100
                timeframe_text += f"**{tf['timeframe']}:** {tf['detected']} detected, {tf['sent']} sent ({utilization_rate:.1f}%)\n"
            
            embed.add_field(
                name="⏱️ Timeframe Performance",
                value=timeframe_text,
                inline=True
            )
        
        # System utilization
        systems = utilization.get('system_utilization', [])
        if systems:
            system_text = ""
            for system in systems[:6]:
                utilization_rate = (system['sent'] / max(system['detected'], 1)) * 100
                system_text += f"**{system['system']}:** {system['detected']} detected, {system['sent']} sent ({utilization_rate:.1f}%)\n"
            
            embed.add_field(
                name="🏗️ System Utilization",
                value=system_text[:1000],
                inline=True
            )
        
        # Missed opportunities
        missed = utilization.get('missed_opportunities', [])
        if missed:
            missed_text = ""
            for opp in missed[:5]:
                missed_text += f"**{opp['ticker']} {opp['signal_type'][:15]}:** Score {opp['priority_score']} - {opp['skip_reason']}\n"
            
            embed.add_field(
                name="💔 High-Priority Missed Opportunities",
                value=missed_text[:1000],
                inline=False
            )
        
        embed.set_footer(text="💡 Use !analytics for historical trends • !missed for recent missed signals")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error getting utilization report: {e}")

@bot.command(name='missed')
async def missed_opportunities(ctx, hours: int = 24):
    """Show high-priority signals that were skipped recently
    
    Usage:
    !missed - Show missed signals from last 24 hours
    !missed 6 - Show missed signals from last 6 hours
    !missed 48 - Show missed signals from last 48 hours
    """
    try:
        if hours < 1 or hours > 168:  # Max 1 week
            await ctx.send("❌ Hours must be between 1 and 168 (1 week)")
            return
            
        # Get utilization data which includes missed opportunities
        utilization = await get_signal_utilization()
        missed = utilization.get('missed_opportunities', [])
        
        if not missed:
            await ctx.send(f"✅ No high-priority signals were skipped in the last {hours} hours!")
            return
            
        embed = discord.Embed(
            title=f"💔 Missed High-Priority Signals ({len(missed)} found)",
            description=f"Signals with priority score ≥60 that were skipped in the last {hours} hours",
            color=0xff3333,
            timestamp=datetime.now(EST)
        )
        
        # Group by skip reason
        skip_reasons = {}
        for signal in missed:
            reason = signal.get('skip_reason', 'unknown')
            if reason not in skip_reasons:
                skip_reasons[reason] = []
            skip_reasons[reason].append(signal)
        
        # Show breakdown by reason
        for reason, signals in skip_reasons.items():
            if len(signals) > 5:
                reason_text = f"**{len(signals)} signals skipped**\n"
                for signal in signals[:3]:
                    reason_text += f"• {signal['ticker']} {signal['signal_type'][:20]} (Score: {signal['priority_score']})\n"
                reason_text += f"• ... and {len(signals)-3} more"
            else:
                reason_text = ""
                for signal in signals:
                    reason_text += f"• **{signal['ticker']}** {signal['signal_type'][:25]} (Score: {signal['priority_score']})\n"
            
            embed.add_field(
                name=f"Reason: {reason.replace('_', ' ').title()}",
                value=reason_text[:1000],
                inline=False
            )
        
        # Add suggestions
        suggestions = ""
        if any('priority_below_threshold' in reason for reason in skip_reasons.keys()):
            suggestions += "• Consider lowering `MIN_PRIORITY_LEVEL` to capture more signals\n"
        if 'duplicate_notification' in skip_reasons:
            suggestions += "• Many duplicates found - this is normal and prevents spam\n"
        
        if suggestions:
            embed.add_field(
                name="💡 Suggestions",
                value=suggestions,
                inline=False
            )
        
        embed.set_footer(text="💡 Use !priority level LOW to receive more signals • !analytics for trends")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error getting missed opportunities: {e}")

@bot.command(name='signalreport')
async def comprehensive_signal_report(ctx):
    """Generate a comprehensive signal detection and utilization report"""
    try:
        # Send typing indicator for longer operation
        async with ctx.typing():
            # Get both analytics and utilization data
            analytics = await get_priority_analytics(7)
            utilization = await get_signal_utilization()
            stats = await get_stats()
            
            embed = discord.Embed(
                title="📋 Comprehensive Signal Report",
                description="Complete analysis of signal detection, priority scoring, and utilization",
                color=0x9932cc,
                timestamp=datetime.now(EST)
            )
            
            # Executive summary
            if stats:
                total_detected = stats.get('total_detected', 0)
                total_sent = stats.get('total_notifications', 0)
                utilization_rate = stats.get('utilization_rate_24h', 0)
                
                embed.add_field(
                    name="📈 Executive Summary",
                    value=f"""
**Overall Performance:** {'✅ Excellent' if utilization_rate > 80 else '⚠️ Needs Attention' if utilization_rate > 50 else '❌ Poor'}
**Detection Rate:** {total_detected} signals/day
**Notification Rate:** {total_sent} alerts/day  
**Utilization Efficiency:** {utilization_rate}%
**Signal Coverage:** {'Comprehensive' if total_detected > 50 else 'Moderate' if total_detected > 20 else 'Limited'}
                    """,
                    inline=False
                )
            
            # Key metrics
            detection_stats = analytics.get('detection_stats', {}) if analytics else {}
            if detection_stats:
                avg_priority = detection_stats.get('avg_priority_score', 0)
                total_detected_7d = detection_stats.get('total_detected', 0)
                total_sent_7d = detection_stats.get('total_sent', 0)
                
                embed.add_field(
                    name="🎯 Key Metrics (7 days)",
                    value=f"""
**Signals Detected:** {total_detected_7d}
**Notifications Sent:** {total_sent_7d}
**Average Priority:** {avg_priority:.1f}
**Signal Quality:** {'High' if avg_priority > 60 else 'Medium' if avg_priority > 40 else 'Low'}
                    """,
                    inline=True
                )
            
            # System performance
            if analytics and analytics.get('system_stats'):
                best_system = analytics['system_stats'][0]
                embed.add_field(
                    name="🏆 Top Performing System",
                    value=f"""
**System:** {best_system['system']}
**Signals:** {best_system['total_signals']}
**Sent:** {best_system['sent_signals']}
**Avg Priority:** {best_system['avg_priority']:.1f}
                    """,
                    inline=True
                )
            
            # Recommendations
            recommendations = []
            
            if utilization_rate < 50:
                recommendations.append("• Consider lowering priority thresholds to catch more signals")
            if avg_priority < 40:
                recommendations.append("• Review VIP ticker and timeframe settings")
            if total_detected < 20:
                recommendations.append("• Add more tickers or timeframes for better coverage")
            if not recommendations:
                recommendations.append("• System is performing well - continue monitoring")
                
            embed.add_field(
                name="💡 Recommendations",
                value="\n".join(recommendations),
                inline=False
            )
            
            embed.set_footer(text="💡 Use !analytics, !utilization, or !missed for detailed analysis")
            
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error generating comprehensive report: {e}")

async def smart_signal_check(cycle_count: int, is_priority: bool, reason: str):
    """Enhanced signal check function for smart scheduler"""
    global loop_start_time, checks_completed, last_successful_check, health_stats
    
    try:
        cycle_start = datetime.now(EST)
        loop_start_time = cycle_start
        checks_completed = cycle_count
        total_signals = 0
        notified_signals = 0
        
        print(f"\n🎯 Smart Signal Check #{cycle_count}")
        print(f"🕐 Check time: {cycle_start.strftime('%Y-%m-%d %I:%M:%S %p EST')}")
        print(f"📋 Reason: {reason}")
        print(f"⭐ Priority run: {'Yes' if is_priority else 'No'}")
        
        # Railway health logging
        if os.getenv('RAILWAY_ENVIRONMENT'):
            print(f"🚂 Railway check #{cycle_count} - Smart scheduler active")
        
        # Create notifier instance
        notifier = SignalNotifier(bot)
        
        # Periodic cleanup of old notifications (every 10 cycles) - DISABLED
        # if cycle_count % 10 == 0:
        #     cleaned_count = await notifier.cleanup_old_notifications()
        #     if cleaned_count > 0:
        #         print(f"🧹 Periodic cleanup: removed {cleaned_count} old notification entries")
        
        # ✅ NEW: Update daily analytics (every 5 cycles)
        if cycle_count % 5 == 0:
            try:
                analytics_success = await update_daily_analytics()
                if analytics_success:
                    print(f"📊 Updated daily analytics for today")
                else:
                    print(f"⚠️ Failed to update daily analytics")
            except Exception as e:
                print(f"❌ Error updating analytics (non-critical): {e}")
                # Don't let analytics errors break the main signal checking loop
        
        # Check each ticker across all timeframes
        api_errors = 0
        discord_errors = 0
        
        current_hour = cycle_start.hour
        
        for ticker in TICKERS:
            for timeframe in TIMEFRAMES:
                # ⏰ TIMEFRAME-AWARE CHECKING: Only check timeframes at their candle close times
                if timeframe == '3h' and current_hour not in [23, 2, 5, 8, 11, 14, 17, 20]:
                    print(f"⏭️ Skipping {ticker} ({timeframe}) - not a 3h candle close hour")
                    continue
                elif timeframe == '6h' and current_hour not in [2, 8, 14, 20]:
                    print(f"⏭️ Skipping {ticker} ({timeframe}) - not a 6h candle close hour")
                    continue  
                elif timeframe == '1d' and current_hour % 4 != 0:  # Every 4 hours for stocks (16:xx) and crypto (20:xx)
                    print(f"⏭️ Skipping {ticker} ({timeframe}) - not a daily candle close hour (checks at 00, 04, 08, 12, 16, 20)")
                    continue
                # 1h timeframe runs every hour (no skip condition)
                
                try:
                    print(f"\n📊 Checking {ticker} ({timeframe})...")
                    
                    # Get recent signals using comprehensive detection
                    recent_signals = notifier.check_for_new_signals(ticker, timeframe)
                    total_signals += len(recent_signals)
                    
                    if recent_signals:
                        print(f"✅ Found {len(recent_signals)} recent signals for {ticker} ({timeframe})")
                        
                        # Filter signals that should trigger notifications
                        notify_signals = []
                        for signal in recent_signals:
                            should_notify_result = await notifier.should_notify(signal, ticker, timeframe)
                            if should_notify_result:
                                notify_signals.append(signal)
                        
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
        
        # Calculate cycle duration and update bot presence
        cycle_end = datetime.now(EST)
        cycle_duration = (cycle_end - cycle_start).total_seconds()
        
        # Get next run info from smart scheduler
        if smart_scheduler:
            next_run_info = smart_scheduler.get_time_until_next_run()
            minutes = int(next_run_info.total_seconds() // 60)
            seconds = int(next_run_info.total_seconds() % 60)
            
            if minutes > 0:
                status_text = f"Next: {minutes}m {seconds}s"
            else:
                status_text = f"Next: {seconds}s"
            
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=status_text
                )
            )
        
        # Enhanced summary logging
        print(f"\n📋 Smart Check #{cycle_count} completed!")
        print(f"⏱️ Duration: {cycle_duration:.1f} seconds")
        print(f"📊 Total signals found: {total_signals}")
        print(f"🚨 Notifications sent: {notified_signals}")
        print(f"❌ API errors: {api_errors}")
        print(f"❌ Discord errors: {discord_errors}")
        
        if smart_scheduler:
            next_runs = smart_scheduler.get_next_run_times(1)
            if next_runs:
                next_run = next_runs[0]
                print(f"⏰ Next check: {next_run.strftime('%I:%M:%S %p EST')} ({smart_scheduler.get_run_reason(next_run)})")
        
        # Railway-specific logging
        if os.getenv('RAILWAY_ENVIRONMENT'):
            uptime = cycle_end - bot_start_time if bot_start_time else timedelta(0)
            print(f"🚂 Railway uptime: {uptime}")
            print(f"🔧 Railway health: ✅ Smart scheduler running normally")
                
    except Exception as e:
        print(f"❌ Critical error in smart signal check: {e}")
        health_stats['failed_checks'] += 1
        
        # Try to notify about the error
        try:
            channel = bot.get_channel(CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title="⚠️ Smart Scheduler Alert",
                    description=f"Smart signal check #{cycle_count} failed",
                    color=0xff0000,
                    timestamp=datetime.now(EST)
                )
                embed.add_field(name="Error", value=str(e)[:1000], inline=False)
                embed.add_field(name="Cycle", value=f"#{cycle_count}", inline=True)
                embed.add_field(name="Reason", value=reason, inline=True)
                embed.add_field(name="Time", value=datetime.now(EST).strftime('%I:%M:%S %p EST'), inline=True)
                await channel.send(embed=embed)
        except:
            pass  # Don't let notification errors crash the scheduler

@bot.command(name='dbsync')
async def database_sync(ctx):
    """Show and sync database stored tickers and VIP settings"""
    try:
        embed = discord.Embed(
            title="🗄️ Database Storage Status",
            description="PostgreSQL stored tickers and VIP settings",
            color=0x9932cc,
            timestamp=datetime.now(EST)
        )
        
        # Get database tickers
        db_tickers = await get_database_tickers()
        embed.add_field(
            name="📊 Database Tickers",
            value=f"**Count:** {len(db_tickers)}\n**Tickers:** {', '.join(db_tickers[:10])}{'...' if len(db_tickers) > 10 else ''}" if db_tickers else "No tickers stored in database",
            inline=False
        )
        
        # Get database VIP tickers
        db_vip_tickers = await get_vip_tickers_from_database()
        embed.add_field(
            name="⭐ Database VIP Tickers",
            value=f"**Count:** {len(db_vip_tickers)}\n**VIP Tickers:** {', '.join(db_vip_tickers)}" if db_vip_tickers else "No VIP tickers stored in database",
            inline=False
        )
        
        # Compare with current memory
        global TICKERS
        from priority_manager import priority_manager
        
        memory_tickers = set(TICKERS)
        memory_vip = set(priority_manager.VIP_TICKERS)
        db_ticker_set = set(db_tickers)
        db_vip_set = set(db_vip_tickers)
        
        # Sync status
        tickers_synced = memory_tickers == db_ticker_set
        vip_synced = memory_vip == db_vip_set
        
        embed.add_field(
            name="🔄 Sync Status",
            value=f"""
**Tickers Synced:** {'✅ Yes' if tickers_synced else '❌ No'}
**VIP Synced:** {'✅ Yes' if vip_synced else '❌ No'}
**Memory Tickers:** {len(memory_tickers)}
**Database Tickers:** {len(db_ticker_set)}
**Memory VIP:** {len(memory_vip)}
**Database VIP:** {len(db_vip_set)}
            """,
            inline=False
        )
        
        if not tickers_synced:
            missing_in_db = memory_tickers - db_ticker_set
            missing_in_memory = db_ticker_set - memory_tickers
            if missing_in_db:
                embed.add_field(
                    name="⚠️ Missing in Database",
                    value=f"Tickers: {', '.join(missing_in_db)}",
                    inline=True
                )
            if missing_in_memory:
                embed.add_field(
                    name="⚠️ Missing in Memory",
                    value=f"Tickers: {', '.join(missing_in_memory)}",
                    inline=True
                )
        
        if not vip_synced:
            missing_vip_in_db = memory_vip - db_vip_set
            missing_vip_in_memory = db_vip_set - memory_vip
            if missing_vip_in_db:
                embed.add_field(
                    name="⚠️ VIP Missing in Database",
                    value=f"VIP Tickers: {', '.join(missing_vip_in_db)}",
                    inline=True
                )
            if missing_vip_in_memory:
                embed.add_field(
                    name="⚠️ VIP Missing in Memory", 
                    value=f"VIP Tickers: {', '.join(missing_vip_in_memory)}",
                    inline=True
                )
        
        embed.add_field(
            name="💡 Commands",
            value="`!addticker SYMBOL` - Add and sync ticker\n`!priority vip add SYMBOL` - Add and sync VIP ticker\n`!dbsync` - Check sync status",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error checking database sync: {e}")

@bot.command(name='bestperformers')
async def best_performing_signals(ctx, days: int = 30):
    """Show historically best performing signals based on analytics data
    
    Usage:
    !bestperformers - Show 30-day best performers
    !bestperformers 7 - Show 7-day best performers
    !bestperformers 60 - Show 60-day best performers
    """
    try:
        if days < 1 or days > 90:
            await ctx.send("❌ Days must be between 1 and 90")
            return
            
        # Send typing indicator for longer operation
        async with ctx.typing():
            best_performers = await get_best_performing_signals(days)
            
            if not best_performers or not best_performers.get('best_performers'):
                await ctx.send(f"❌ No analytics data available for the last {days} days. Analytics are built over time as signals are detected.")
                return
                
            embed = discord.Embed(
                title=f"🏆 Best Performing Signals ({days} days)",
                description="Top signal combinations based on utilization rate and priority",
                color=0xffd700,
                timestamp=datetime.now(EST)
            )
            
            # Top performers
            top_performers = best_performers.get('best_performers', [])[:10]
            if top_performers:
                performers_text = ""
                for i, performer in enumerate(top_performers, 1):
                    performers_text += f"{i}. **{performer['ticker']} {performer['system']} ({performer['timeframe']})**: {performer['utilization_rate']}% utilization, {performer['avg_priority']:.1f} avg priority\n"
                
                embed.add_field(
                    name="🎯 Top Signal Combinations",
                    value=performers_text[:1000],
                    inline=False
                )
            
            # Most active systems
            active_systems = best_performers.get('most_active_systems', [])[:5]
            if active_systems:
                systems_text = ""
                for system in active_systems:
                    systems_text += f"**{system['system']}**: {system['total_signals']} signals, {system['avg_priority']:.1f} avg priority\n"
                
                embed.add_field(
                    name="🏗️ Most Active Systems",
                    value=systems_text,
                    inline=True
                )
            
            # Consistent performers
            consistent = best_performers.get('consistent_performers', [])[:5]
            if consistent:
                consistent_text = ""
                for ticker in consistent:
                    consistent_text += f"**{ticker['ticker']}**: {ticker['avg_priority']:.1f} avg priority, {ticker['total_signals']} signals\n"
                
                embed.add_field(
                    name="⭐ Consistent High-Priority Tickers",
                    value=consistent_text,
                    inline=True
                )
            
            embed.set_footer(text="💡 Analytics are updated every 5 signal check cycles • Use !analytics for detection stats")
            
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error getting best performers: {e}")

@bot.command(name='performance')
async def signal_performance_summary(ctx):
    """Show overall signal performance summary from historical analytics"""
    try:
        # Send typing indicator
        async with ctx.typing():
            performance = await get_signal_performance_summary()
            
            if not performance or not performance.get('overall_stats'):
                await ctx.send("❌ No historical analytics data available yet. Performance data is built over time as signals are detected.")
                return
                
            embed = discord.Embed(
                title="📈 Signal Performance Summary",
                description="Historical performance analysis from analytics database",
                color=0x00ff88,
                timestamp=datetime.now(EST)
            )
            
            # Overall stats
            overall = performance.get('overall_stats', {})
            if overall:
                total_signals = overall.get('total_signals_all_time', 0)
                total_sent = overall.get('total_sent_all_time', 0)
                overall_avg = overall.get('overall_avg_priority', 0)
                utilization_rate = (total_sent / max(total_signals, 1)) * 100
                
                embed.add_field(
                    name="📊 All-Time Performance",
                    value=f"""
**Total Signals Detected:** {total_signals:,}
**Total Notifications Sent:** {total_sent:,}
**Overall Utilization Rate:** {utilization_rate:.1f}%
**Average Priority Score:** {overall_avg:.1f}
**Unique Tickers:** {overall.get('unique_tickers', 0)}
**Signal Systems:** {overall.get('unique_systems', 0)}
                    """,
                    inline=False
                )
                
                # Date range
                earliest = overall.get('earliest_date')
                latest = overall.get('latest_date')
                if earliest and latest:
                    embed.add_field(
                        name="📅 Data Range",
                        value=f"**From:** {earliest}\n**To:** {latest}",
                        inline=True
                    )
            
            # Recent stats (30 days)
            recent = performance.get('recent_stats', {})
            if recent:
                recent_signals = recent.get('signals_30d', 0)
                recent_sent = recent.get('sent_30d', 0)
                recent_utilization = (recent_sent / max(recent_signals, 1)) * 100
                
                embed.add_field(
                    name="📈 Last 30 Days",
                    value=f"""
**Signals:** {recent_signals}
**Sent:** {recent_sent}
**Utilization:** {recent_utilization:.1f}%
**Avg Priority:** {recent.get('avg_priority_30d', 0):.1f}
**Active Days:** {recent.get('active_days_30d', 0)}
                    """,
                    inline=True
                )
            
            # Top system
            top_system = performance.get('top_system', {})
            if top_system:
                embed.add_field(
                    name="🏆 Top System",
                    value=f"""
**System:** {top_system.get('system', 'Unknown')}
**Total Signals:** {top_system.get('total_signals', 0)}
**Avg Priority:** {top_system.get('avg_priority', 0):.1f}
                    """,
                    inline=True
                )
            
            # Top ticker
            top_ticker = performance.get('top_ticker', {})
            if top_ticker:
                embed.add_field(
                    name="⭐ Most Reliable Ticker",
                    value=f"""
**Ticker:** {top_ticker.get('ticker', 'Unknown')}
**Utilization Rate:** {top_ticker.get('utilization_rate', 0)}%
**Avg Priority:** {top_ticker.get('avg_priority', 0):.1f}
**Total Signals:** {top_ticker.get('total_signals', 0)}
                    """,
                    inline=True
                )
            
            embed.set_footer(text="💡 Use !bestperformers for detailed analysis • !analytics for recent trends")
            
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error getting performance summary: {e}")

@bot.command(name='updateanalytics')
async def manual_analytics_update(ctx, date: str = None):
    """Manually update daily analytics for a specific date or today
    
    Usage:
    !updateanalytics - Update analytics for today
    !updateanalytics 2024-01-15 - Update analytics for specific date
    """
    try:
        # Validate date format if provided
        if date:
            try:
                datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                await ctx.send("❌ Invalid date format. Use YYYY-MM-DD (e.g., 2024-01-15)")
                return
        
        # Send typing indicator
        async with ctx.typing():
            success = await update_daily_analytics(date)
            
            if success:
                target_date = date if date else "today"
                embed = discord.Embed(
                    title="✅ Analytics Updated",
                    description=f"Successfully updated daily analytics for {target_date}",
                    color=0x00ff00,
                    timestamp=datetime.now(EST)
                )
                embed.add_field(
                    name="📊 What was updated",
                    value="• Signal detection counts\n• Priority distributions\n• System performance\n• Ticker analytics",
                    inline=False
                )
            else:
                embed = discord.Embed(
                    title="❌ Analytics Update Failed",
                    description="Failed to update daily analytics",
                    color=0xff0000,
                    timestamp=datetime.now(EST)
                )
                embed.add_field(
                    name="💡 Possible reasons",
                    value="• No signals detected for the date\n• Database connection issue\n• Invalid date format",
                    inline=False
                )
            
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error updating analytics: {e}")

@bot.command(name='analyticshealth')
async def analytics_health_check(ctx):
    """Check the health and status of the analytics system"""
    try:
        embed = discord.Embed(
            title="🔬 Analytics System Health Check",
            description="Comprehensive status of the analytics and database system",
            color=0x00ff88,
            timestamp=datetime.now(EST)
        )
        
        # Test database connection and table existence
        try:
            stats = await get_stats()
            db_connection = "✅ Connected"
        except Exception as e:
            db_connection = f"❌ Error: {str(e)[:50]}"
            stats = {}
        
        # Test analytics functions
        analytics_functions = {}
        
        # Test update_daily_analytics
        try:
            await update_daily_analytics()
            analytics_functions['update_daily_analytics'] = "✅ Working"
        except Exception as e:
            analytics_functions['update_daily_analytics'] = f"❌ Error: {str(e)[:30]}"
        
        # Test get_best_performing_signals
        try:
            await get_best_performing_signals(7)
            analytics_functions['best_performers'] = "✅ Working"
        except Exception as e:
            analytics_functions['best_performers'] = f"❌ Error: {str(e)[:30]}"
        
        # Test get_signal_performance_summary
        try:
            await get_signal_performance_summary()
            analytics_functions['performance_summary'] = "✅ Working"
        except Exception as e:
            analytics_functions['performance_summary'] = f"❌ Error: {str(e)[:30]}"
        
        # Database status
        embed.add_field(
            name="🗄️ Database Status",
            value=f"""
**Connection:** {db_connection}
**Total Notifications:** {stats.get('total_notifications', 0)}
**Total Detected:** {stats.get('total_detected', 0)}
**Utilization Rate:** {stats.get('utilization_rate_24h', 0)}%
            """,
            inline=False
        )
        
        # Analytics functions status
        functions_text = ""
        for func, status in analytics_functions.items():
            functions_text += f"**{func}:** {status}\n"
        
        embed.add_field(
            name="📊 Analytics Functions",
            value=functions_text,
            inline=False
        )
        
        # Data freshness check
        current_time = datetime.now(EST)
        if last_successful_check:
            time_since_last = current_time - last_successful_check
            if time_since_last.total_seconds() < 3600:  # Less than 1 hour
                data_freshness = f"✅ Fresh ({time_since_last.total_seconds()//60:.0f}m ago)"
            else:
                data_freshness = f"⚠️ Stale ({time_since_last.total_seconds()//3600:.1f}h ago)"
        else:
            data_freshness = "❌ Unknown"
        
        embed.add_field(
            name="📅 Data Freshness",
            value=f"**Last Signal Check:** {data_freshness}",
            inline=True
        )
        
        # Analytics integration status
        analytics_integration = "✅ Enabled" if checks_completed % 5 == 0 else "✅ Scheduled"
        embed.add_field(
            name="🔄 Analytics Integration",
            value=f"**Auto-Updates:** {analytics_integration}\n**Update Frequency:** Every 5 cycles",
            inline=True
        )
        
        # Overall health score
        working_functions = sum(1 for status in analytics_functions.values() if "✅" in status)
        total_functions = len(analytics_functions)
        health_score = (working_functions / total_functions) * 100
        
        if health_score == 100:
            health_status = "🟢 Excellent"
            embed.color = 0x00ff00
        elif health_score >= 75:
            health_status = "🟡 Good"
            embed.color = 0xffff00
        else:
            health_status = "🔴 Issues Detected"
            embed.color = 0xff0000
        
        embed.add_field(
            name="🏥 Overall Health",
            value=f"**Status:** {health_status}\n**Score:** {health_score:.0f}%\n**Functions Working:** {working_functions}/{total_functions}",
            inline=False
        )
        
        embed.set_footer(text="💡 Use !updateanalytics to manually update • !performance for historical data")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error running analytics health check: {e}")

@bot.command(name='vipsync')
async def vip_sync_command(ctx):
    """Manually sync VIP tickers with database (reload configuration)"""
    try:
        embed = discord.Embed(
            title="🔄 Priority Configuration Sync",
            description="Reloading priority configuration from PostgreSQL database",
            color=0xff6600,
            timestamp=datetime.now(EST)
        )
        
        # Show current state
        embed.add_field(
            name="Before Sync",
            value=f"**VIP Tickers:** {', '.join(sorted(priority_manager.VIP_TICKERS))}\n**Min Priority:** {priority_manager.MIN_PRIORITY_LEVEL}",
            inline=False
        )
        
        # Reload from database
        success = await priority_manager.reload_from_database()
        
        if success:
            embed.add_field(
                name="After Sync",
                value=f"**VIP Tickers:** {', '.join(sorted(priority_manager.VIP_TICKERS))}\n**Min Priority:** {priority_manager.MIN_PRIORITY_LEVEL}",
                inline=False
            )
            
            embed.add_field(
                name="✅ Sync Successful",
                value="Priority configuration reloaded from PostgreSQL database",
                inline=False
            )
            embed.color = 0x00ff00
        else:
            embed.add_field(
                name="❌ Sync Failed",
                value="Failed to reload from database, using current configuration",
                inline=False
            )
            embed.color = 0xff0000
        
        embed.set_footer(text="💡 Priority configuration is always loaded from PostgreSQL database")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error syncing priority configuration: {e}")

@bot.command(name='commands')
async def help_command(ctx):
    """Show all available bot commands organized by category"""
    embed = discord.Embed(
        title="🤖 Discord Signal Bot - Command Reference",
        description="Complete list of available commands organized by category",
        color=0x0099ff,
        timestamp=datetime.now(EST)
    )
    
    # Signal Commands
    embed.add_field(
        name="📊 Signal Commands",
        value="""
`!signals [TICKER] [TIMEFRAME]` - Get latest signals
`!test` - Test API connection
`!timer` - Show time until next check
`!schedule` - Show smart scheduler info
        """,
        inline=False
    )
    
    # Analytics Commands
    embed.add_field(
        name="📈 Analytics Commands",
        value="""
`!analytics [DAYS]` - Signal analytics & trends
`!performance` - Overall performance summary
`!bestperformers [DAYS]` - Top performing signals
`!utilization` - Signal utilization analysis
`!missed [HOURS]` - High-priority missed signals
`!signalreport` - Comprehensive signal report
`!updateanalytics [DATE]` - Manual analytics update
`!analyticshealth` - Analytics system health check
`!successrates [DAYS]` - Signal success rate analysis
`!correlations [DAYS]` - 🔗 Enhanced correlation analysis with ML patterns, market conditions & statistical validation
`!mlpredict [DAYS]` - 🤖 ML-powered success predictions
`!testperformance [TICKER]` - Add sample performance data
`!debugapi [TICKER] [TF]` - Debug API response structure
        """,
        inline=False
    )
    
    # Configuration Commands
    embed.add_field(
        name="⚙️ Configuration Commands",
        value="""
`!config` - Show current configuration
`!addticker SYMBOL` - Add ticker to watchlist
`!removeticker SYMBOL` - Remove ticker from watchlist
`!listtickers` - List all monitored tickers
`!tickersync` - Sync bot with database tickers (loads from PostgreSQL)
`!timeframes [ACTION] [TF]` - Manage timeframes
`!dbsync` - Database synchronization status
        """,
        inline=False
    )
    
    # Priority Commands
    embed.add_field(
        name="🎯 Priority Management",
        value="""
`!priority` - Show priority settings
`!priority level LEVEL` - Set minimum priority
`!priority vip add TICKER` - Add VIP ticker
`!priority vip remove TICKER` - Remove VIP ticker
`!priority test TICKER` - Test priority scoring
`!prioritystats` - Priority statistics
`!vipsync` - Manually sync VIP tickers from database
        """,
        inline=False
    )
    
    # Status & Health Commands
    embed.add_field(
        name="🏥 Status & Health",
        value="""
`!status` - Bot status overview
`!health` - Comprehensive health check
`!uptime` - Bot uptime information
`!notifications` - Notification statistics
`!scheduler [ACTION]` - Control scheduler
        """,
        inline=False
    )
    
    # Utility Commands
    embed.add_field(
        name="🛠️ Utility Commands",
        value="""
`!cleanup` - Manual database cleanup
`!clear [AMOUNT]` - Clear channel messages
`!watch TICKER` - Add ticker (legacy)
`!commands` - Show this help message
        """,
        inline=False
    )
    
    # Footer with important info
    embed.set_footer(text="💡 Use [OPTIONAL] for optional parameters • All commands start with !")
    
    await ctx.send(embed=embed)

# ✅ NEW: Function to sync tickers with database on startup
async def sync_tickers_with_database():
    """Sync ticker list with PostgreSQL database on startup"""
    global TICKERS, ticker_config
    try:
        print("🔄 Syncing ticker list with PostgreSQL database...")
        
        # Get tickers from database
        db_tickers = await get_database_tickers()
        
        if db_tickers:
            print(f"📊 Found {len(db_tickers)} tickers in database: {', '.join(db_tickers[:10])}{'...' if len(db_tickers) > 10 else ''}")
            
            # Update config with database tickers
            ticker_config['tickers'] = sorted(list(set(db_tickers)))  # Remove duplicates and sort
            save_ticker_config(ticker_config)
            
            # Update global TICKERS variable
            TICKERS = ticker_config['tickers']
            
            print(f"✅ Ticker list synchronized: now monitoring {len(TICKERS)} tickers")
            return True
        else:
            print("⚠️ No tickers found in database, using config file tickers")
            
            # If database is empty, populate it with current config tickers
            for ticker in TICKERS:
                await add_ticker_to_database(ticker)
            print(f"📊 Populated database with {len(TICKERS)} tickers from config")
            return True
            
    except Exception as e:
        print(f"❌ Error syncing tickers with database: {e}")
        print("⚠️ Continuing with config file tickers")
        return False

@bot.command(name='validativips')
async def validate_vip_tickers(ctx):
    """Validate VIP tickers against monitored tickers database"""
    try:
        validation = await priority_manager.db_config.validate_vip_tickers()
        
        embed = discord.Embed(
            title="🔍 VIP Ticker Validation",
            description="Checking VIP tickers against monitored tickers database",
            color=0x00ff00 if validation['validation_passed'] else 0xff6600,
            timestamp=datetime.now(EST)
        )
        
        # Validation summary
        embed.add_field(
            name="📊 Summary",
            value=f"""
**Total VIP Tickers:** {validation['total_vips']}
**Total Monitored Tickers:** {validation['total_monitored']}
**Validation Status:** {'✅ Passed' if validation['validation_passed'] else '⚠️ Issues Found'}
            """,
            inline=False
        )
        
        # Valid VIP tickers
        if validation['valid_vips']:
            valid_text = ", ".join(validation['valid_vips'][:10])
            if len(validation['valid_vips']) > 10:
                valid_text += f" ... and {len(validation['valid_vips']) - 10} more"
            
            embed.add_field(
                name="✅ Valid VIP Tickers",
                value=f"`{valid_text}`",
                inline=False
            )
        
        # Invalid VIP tickers (if any)
        if validation['invalid_vips']:
            invalid_text = ", ".join(validation['invalid_vips'])
            embed.add_field(
                name="⚠️ Invalid VIP Tickers",
                value=f"`{invalid_text}`\n*These tickers are not in the monitored tickers database*",
                inline=False
            )
            
            embed.add_field(
                name="💡 Suggested Actions",
                value="• Use `!addticker SYMBOL` to add missing tickers to monitoring\n"
                      "• Use `!cleanupvips` to remove invalid VIP tickers\n"
                      "• Use `!priority vip remove SYMBOL` to manually remove specific VIP tickers",
                inline=False
            )
        
        # Error handling
        if 'error' in validation:
            embed.add_field(
                name="❌ Validation Error",
                value=f"```{validation['error']}```",
                inline=False
            )
        
        embed.set_footer(text="💡 VIP tickers should exist in the monitored tickers database for optimal functionality")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error validating VIP tickers: {e}")

@bot.command(name='cleanupvips')
async def cleanup_vip_tickers(ctx):
    """Clean up VIP tickers that don't exist in monitored tickers database"""
    try:
        # Send typing indicator for longer operation
        async with ctx.typing():
            cleanup_result = await priority_manager.db_config.sync_vip_with_monitored_tickers()
            
        if cleanup_result['cleanup_performed']:
            embed = discord.Embed(
                title="🧹 VIP Ticker Cleanup Complete",
                description="Removed invalid VIP tickers from configuration",
                color=0x00ff00 if cleanup_result['cleanup_success'] else 0xff0000,
                timestamp=datetime.now(EST)
            )
            
            if cleanup_result['invalid_vips']:
                embed.add_field(
                    name="🗑️ Removed VIP Tickers",
                    value=f"`{', '.join(cleanup_result['invalid_vips'])}`",
                    inline=False
                )
            
            embed.add_field(
                name="📊 After Cleanup",
                value=f"""
**Valid VIP Tickers:** {len(cleanup_result['valid_vips'])}
**Remaining VIPs:** {', '.join(cleanup_result['valid_vips']) if cleanup_result['valid_vips'] else 'None'}
**Database Saved:** {'✅ Yes' if cleanup_result['cleanup_success'] else '❌ Failed'}
                """,
                inline=False
            )
            
        else:
            embed = discord.Embed(
                title="✅ No Cleanup Needed",
                description="All VIP tickers are valid and exist in the monitored tickers database",
                color=0x00ff00,
                timestamp=datetime.now(EST)
            )
            
            embed.add_field(
                name="📊 Current Status",
                value=f"""
**Valid VIP Tickers:** {len(cleanup_result['valid_vips'])}
**VIP List:** {', '.join(cleanup_result['valid_vips']) if cleanup_result['valid_vips'] else 'None'}
                """,
                inline=False
            )
        
        embed.set_footer(text="💡 Use !validatevips to check VIP ticker status anytime")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error cleaning up VIP tickers: {e}")

@bot.command(name='vipstatus')
async def vip_ticker_status(ctx):
    """Show detailed status of VIP tickers and their relationship to monitored tickers"""
    try:
        # Get validation data
        validation = await priority_manager.db_config.validate_vip_tickers()
        
        # Get additional data
        db_tickers = await get_database_tickers()
        vip_tickers = priority_manager.VIP_TICKERS
        
        embed = discord.Embed(
            title="⭐ VIP Ticker Status Report",
            description="Comprehensive analysis of VIP ticker configuration",
            color=0x9932cc,
            timestamp=datetime.now(EST)
        )
        
        # Overview
        embed.add_field(
            name="📊 Overview",
            value=f"""
**Total Monitored Tickers:** {len(db_tickers)}
**Total VIP Tickers:** {len(vip_tickers)}
**VIP Coverage:** {(len(vip_tickers)/max(len(db_tickers),1)*100):.1f}%
**Validation Status:** {'✅ All Valid' if validation['validation_passed'] else f'⚠️ {len(validation["invalid_vips"])} Invalid'}
            """,
            inline=False
        )
        
        # VIP ticker details
        if validation['valid_vips']:
            vip_details = []
            for vip in sorted(validation['valid_vips'])[:10]:
                # Check if this ticker is actively monitored
                monitoring_status = "🟢 Monitored" if vip in db_tickers else "🔴 Not Monitored"
                vip_details.append(f"• **{vip}** - {monitoring_status}")
            
            if len(validation['valid_vips']) > 10:
                vip_details.append(f"• ... and {len(validation['valid_vips']) - 10} more")
            
            embed.add_field(
                name="✅ Valid VIP Tickers",
                value="\n".join(vip_details),
                inline=False
            )
        
        # Invalid VIPs (if any)
        if validation['invalid_vips']:
            embed.add_field(
                name="❌ Invalid VIP Tickers",
                value=f"```{', '.join(validation['invalid_vips'])}```\n*Not found in monitored tickers database*",
                inline=False
            )
        
        # Monitoring suggestions
        non_vip_monitored = set(db_tickers) - set(vip_tickers)
        if non_vip_monitored:
            suggestions = sorted(list(non_vip_monitored))[:5]
            embed.add_field(
                name="💡 Potential VIP Candidates",
                value=f"Monitored tickers that could be added as VIP:\n`{', '.join(suggestions)}`{'...' if len(non_vip_monitored) > 5 else ''}",
                inline=False
            )
        
        # Commands
        embed.add_field(
            name="🛠️ Management Commands",
            value="""
`!validatevips` - Validate VIP tickers
`!cleanupvips` - Remove invalid VIP tickers  
`!priority vip add TICKER` - Add VIP ticker
`!priority vip remove TICKER` - Remove VIP ticker
`!addticker TICKER` - Add ticker to monitoring
            """,
            inline=False
        )
        
        embed.set_footer(text="💡 VIP tickers receive priority scoring bonuses in signal detection")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error getting VIP ticker status: {e}")

@bot.command(name='testpriority')
async def test_priority_integration(ctx):
    """Run a quick test of the priority-ticker integration"""
    try:
        embed = discord.Embed(
            title="🧪 Priority Integration Test",
            description="Testing the integration between tickers and priority system",
            color=0xff6600,
            timestamp=datetime.now(EST)
        )
        
        # Send typing indicator
        async with ctx.typing():
            # Test 1: Database connectivity
            try:
                db_tickers = await get_database_tickers()
                db_test = f"✅ Connected ({len(db_tickers)} tickers)"
            except Exception as e:
                db_test = f"❌ Failed: {str(e)[:50]}"
            
            # Test 2: Priority manager initialization
            try:
                await priority_manager.reload_from_database()
                priority_test = f"✅ Loaded ({len(priority_manager.VIP_TICKERS)} VIP tickers)"
            except Exception as e:
                priority_test = f"❌ Failed: {str(e)[:50]}"
            
            # Test 3: VIP validation
            try:
                validation = await priority_manager.db_config.validate_vip_tickers()
                if validation['validation_passed']:
                    validation_test = f"✅ All {validation['total_vips']} VIP tickers valid"
                else:
                    validation_test = f"⚠️ {len(validation['invalid_vips'])} invalid VIP tickers"
            except Exception as e:
                validation_test = f"❌ Failed: {str(e)[:50]}"
            
            # Test 4: Priority scoring
            try:
                test_signal = {
                    'type': 'WT Buy Signal',
                    'strength': 'Strong',
                    'system': 'Wave Trend',
                    'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                # Test with first available ticker
                test_ticker = db_tickers[0] if db_tickers else 'AAPL'
                score = priority_manager.calculate_priority_score(test_signal, test_ticker, '1d')
                scoring_test = f"✅ Score calculated: {score.total_score} ({score.priority_level.name})"
            except Exception as e:
                scoring_test = f"❌ Failed: {str(e)[:50]}"
        
        # Test results
        embed.add_field(
            name="🔍 Test Results",
            value=f"""
**Database Connection:** {db_test}
**Priority Manager:** {priority_test}
**VIP Validation:** {validation_test}
**Priority Scoring:** {scoring_test}
            """,
            inline=False
        )
        
        # Quick stats
        if db_tickers:
            embed.add_field(
                name="📊 Quick Stats",
                value=f"""
**Monitored Tickers:** {len(db_tickers)}
**VIP Tickers:** {len(priority_manager.VIP_TICKERS)}
**VIP Coverage:** {(len(priority_manager.VIP_TICKERS)/max(len(db_tickers),1)*100):.1f}%
**Sample Tickers:** {', '.join(db_tickers[:5])}{'...' if len(db_tickers) > 5 else ''}
                """,
                inline=False
            )
        
        embed.add_field(
            name="💡 Commands",
            value="`!vipstatus` - Detailed VIP analysis\n`!validatevips` - Validate VIP tickers\n`!priority` - Priority settings",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error running priority integration test: {e}")

@bot.command(name='testperformance')
async def test_signal_performance(ctx, ticker: str = "AAPL"):
    """Test signal performance tracking by adding sample data
    
    Usage:
    !testperformance          - Test with AAPL
    !testperformance TSLA     - Test with specific ticker
    """
    try:
        from database import record_signal_performance
        import random
        
        embed = discord.Embed(
            title="🧪 Signal Performance Test",
            description=f"Adding sample performance data for {ticker.upper()}",
            color=0xff6600,
            timestamp=datetime.now(EST)
        )
        
        # Send typing indicator
        async with ctx.typing():
            # Create sample performance data
            sample_signals = [
                {
                    'signal_type': 'WT Buy Signal',
                    'signal_date': '2024-01-15 09:30:00',
                    'price_at_signal': 150.00,
                    'price_after_1h': 151.50,  # +1% (success)
                    'price_after_4h': 152.25,  # +1.5% (success)
                    'price_after_1d': 155.00,  # +3.33% (success)
                },
                {
                    'signal_type': 'WT Sell Signal', 
                    'signal_date': '2024-01-16 14:15:00',
                    'price_at_signal': 155.00,
                    'price_after_1h': 154.20,  # -0.52% (success for sell)
                    'price_after_4h': 153.50,  # -0.97% (success for sell)
                    'price_after_1d': 152.00,  # -1.94% (success for sell)
                },
                {
                    'signal_type': 'RSI3M3 Bullish Entry',
                    'signal_date': '2024-01-17 11:45:00', 
                    'price_at_signal': 152.00,
                    'price_after_1h': 151.75,  # -0.16% (failure)
                    'price_after_4h': 153.10,  # +0.72% (success)
                    'price_after_1d': 154.80,  # +1.84% (success)
                }
            ]
            
            success_count = 0
            total_count = len(sample_signals)
            
            for signal in sample_signals:
                success = await record_signal_performance(
                    ticker=ticker.upper(),
                    timeframe='1d',
                    signal_type=signal['signal_type'],
                    signal_date=signal['signal_date'],
                    price_at_signal=signal['price_at_signal'],
                    price_after_1h=signal['price_after_1h'],
                    price_after_4h=signal['price_after_4h'],
                    price_after_1d=signal['price_after_1d']
                )
                
                if success:
                    success_count += 1
        
        # Show results
        embed.add_field(
            name="📊 Test Results",
            value=f"""
**Signals Added:** {success_count}/{total_count}
**Ticker:** {ticker.upper()}
**Timeframe:** 1d
**Sample Data:** 3 different signal types with realistic price movements
            """,
            inline=False
        )
        
        # Calculate expected success rates
        embed.add_field(
            name="📈 Expected Success Rates",
            value="""
**1h Success Rate:** ~67% (2/3 signals successful)
**1d Success Rate:** ~100% (3/3 signals successful)
            """,
            inline=False
        )
        
        embed.add_field(
            name="🔧 Next Steps",
            value="`!updateanalytics` - Update analytics to see success rates\n`!performance` - View performance summary\n`!bestperformers` - See top performing signals",
            inline=False
        )
        
        if success_count == total_count:
            embed.color = 0x00ff00
            embed.add_field(
                name="✅ Success",
                value="All sample performance data added successfully!",
                inline=False
            )
        else:
            embed.color = 0xff0000
            embed.add_field(
                name="❌ Partial Failure",
                value=f"Only {success_count}/{total_count} records added successfully",
                inline=False
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error testing signal performance: {e}")

@bot.command(name='successrates')
async def show_success_rates(ctx, days: int = 30):
    """Show success rate statistics from signal performance data
    
    Usage:
    !successrates      - Show 30-day success rates
    !successrates 7    - Show 7-day success rates
    !successrates 90   - Show 90-day success rates
    """
    try:
        if days < 1 or days > 365:
            await ctx.send("❌ Days must be between 1 and 365")
            return
            
        embed = discord.Embed(
            title=f"📈 Signal Success Rates ({days} days)",
            description="Success rate analysis with corrected bullish/bearish logic",
            color=0x00ff88,
            timestamp=datetime.now(EST)
        )
        
        # Send typing indicator
        async with ctx.typing():
            from database import db_manager
            
            async with db_manager.pool.acquire() as conn:
                since_date = datetime.now() - timedelta(days=days)
                
                # ✅ CORRECTED Overall success rates with proper signal direction handling
                # Updated to use 1h, 3h, 6h, 1d timeframes
                overall_stats = await conn.fetchrow('''
                    SELECT 
                        COUNT(*) as total_signals,
                        COUNT(CASE 
                            WHEN (signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%')
                                 AND price_after_1h > price_at_signal THEN 1
                            WHEN (signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%')
                                 AND price_after_1h < price_at_signal THEN 1
                        END) as correct_1h,
                        COUNT(CASE 
                            WHEN (signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%')
                                 AND price_after_3h > price_at_signal THEN 1
                            WHEN (signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%')
                                 AND price_after_3h < price_at_signal THEN 1
                        END) as correct_3h,
                        COUNT(CASE 
                            WHEN (signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%')
                                 AND price_after_6h > price_at_signal THEN 1
                            WHEN (signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%')
                                 AND price_after_6h < price_at_signal THEN 1
                        END) as correct_6h,
                        COUNT(CASE 
                            WHEN (signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%')
                                 AND price_after_1d > price_at_signal THEN 1
                            WHEN (signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%')
                                 AND price_after_1d < price_at_signal THEN 1
                        END) as correct_1d
                    FROM signal_performance
                    WHERE performance_date >= $1
                      AND price_at_signal IS NOT NULL 
                      AND price_after_1h IS NOT NULL 
                      AND price_after_1d IS NOT NULL
                      AND price_after_1h != price_at_signal  -- Exclude 0% changes
                      AND price_after_1d != price_at_signal  -- Exclude 0% changes
                ''', since_date)
                
                if overall_stats and overall_stats['total_signals'] > 0:
                    success_1h = (overall_stats['correct_1h'] / overall_stats['total_signals']) * 100 if overall_stats['correct_1h'] else 0
                    success_3h = (overall_stats['correct_3h'] / overall_stats['total_signals']) * 100 if overall_stats['correct_3h'] else 0
                    success_6h = (overall_stats['correct_6h'] / overall_stats['total_signals']) * 100 if overall_stats['correct_6h'] else 0
                    success_1d = (overall_stats['correct_1d'] / overall_stats['total_signals']) * 100 if overall_stats['correct_1d'] else 0
                    
                    embed.add_field(
                        name="📊 Overall Success Rates (CORRECTED)",
                        value=f"""
**Total Signals Analyzed:** {overall_stats['total_signals']}
**1 Hour:** {success_1h:.1f}% ({overall_stats['correct_1h']} correct)
**3 Hours:** {success_3h:.1f}% ({overall_stats['correct_3h']} correct)
**6 Hours:** {success_6h:.1f}% ({overall_stats['correct_6h']} correct)
**1 Day:** {success_1d:.1f}% ({overall_stats['correct_1d']} correct)
                        """,
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="📊 No Performance Data",
                        value=f"No signal performance data found for the last {days} days.\n\nUse `!testperformance` to add sample data.",
                        inline=False
                    )
                    embed.color = 0xff6600
                
                # ✅ CORRECTED Success rates by signal type  
                signal_type_stats = await conn.fetch('''
                    SELECT 
                        signal_type,
                        CASE 
                            WHEN signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%' THEN 'BULLISH'
                            WHEN signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%' THEN 'BEARISH'
                            ELSE 'NEUTRAL'
                        END as signal_direction,
                        COUNT(*) as count,
                        CAST(CAST(COUNT(CASE 
                            WHEN (signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%')
                                 AND price_after_1h > price_at_signal THEN 1
                            WHEN (signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%')
                                 AND price_after_1h < price_at_signal THEN 1
                        END) AS NUMERIC) / CAST(COUNT(*) AS NUMERIC) * 100 AS NUMERIC(5,1)) as success_1h,
                        CAST(CAST(COUNT(CASE 
                            WHEN (signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%')
                                 AND price_after_6h > price_at_signal THEN 1
                            WHEN (signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%')
                                 AND price_after_6h < price_at_signal THEN 1
                        END) AS NUMERIC) / CAST(COUNT(*) AS NUMERIC) * 100 AS NUMERIC(5,1)) as success_6h,
                        CAST(CAST(COUNT(CASE 
                            WHEN (signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%')
                                 AND price_after_1d > price_at_signal THEN 1
                            WHEN (signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%')
                                 AND price_after_1d < price_at_signal THEN 1
                        END) AS NUMERIC) / CAST(COUNT(*) AS NUMERIC) * 100 AS NUMERIC(5,1)) as success_1d
                    FROM signal_performance
                    WHERE performance_date >= $1
                      AND price_at_signal IS NOT NULL 
                      AND price_after_1h IS NOT NULL 
                      AND price_after_1d IS NOT NULL
                      AND price_after_1h != price_at_signal  -- Exclude 0% changes
                      AND price_after_1d != price_at_signal  -- Exclude 0% changes
                    GROUP BY signal_type, signal_direction
                    HAVING COUNT(*) >= 2
                    ORDER BY success_1d DESC NULLS LAST
                    LIMIT 10
                ''', since_date)
                
                if signal_type_stats:
                    signal_text = ""
                    for signal in signal_type_stats:
                        direction_emoji = "🔺" if signal['signal_direction'] == 'BULLISH' else ("🔻" if signal['signal_direction'] == 'BEARISH' else "⚖️")
                        signal_text += f"{direction_emoji} **{signal['signal_type'][:22]}:** 1h={signal['success_1h'] or 0}%, 6h={signal['success_6h'] or 0}%, 1d={signal['success_1d'] or 0}% ({signal['count']} signals)\n"
                    
                    embed.add_field(
                        name="🎯 Success by Signal Type (CORRECTED)",
                        value=signal_text[:1000],
                        inline=False
                    )
                
                # Success rates by ticker (using corrected logic)
                ticker_stats = await conn.fetch('''
                    SELECT 
                        ticker,
                        COUNT(*) as count,
                        CAST(CAST(COUNT(CASE 
                            WHEN (signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%')
                                 AND price_after_1h > price_at_signal THEN 1
                            WHEN (signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%')
                                 AND price_after_1h < price_at_signal THEN 1
                        END) AS NUMERIC) / CAST(COUNT(*) AS NUMERIC) * 100 AS NUMERIC(5,1)) as success_1h,
                        CAST(CAST(COUNT(CASE 
                            WHEN (signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%')
                                 AND price_after_6h > price_at_signal THEN 1
                            WHEN (signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%')
                                 AND price_after_6h < price_at_signal THEN 1
                        END) AS NUMERIC) / CAST(COUNT(*) AS NUMERIC) * 100 AS NUMERIC(5,1)) as success_6h,
                        CAST(CAST(COUNT(CASE 
                            WHEN (signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%')
                                 AND price_after_1d > price_at_signal THEN 1
                            WHEN (signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%')
                                 AND price_after_1d < price_at_signal THEN 1
                        END) AS NUMERIC) / CAST(COUNT(*) AS NUMERIC) * 100 AS NUMERIC(5,1)) as success_1d
                    FROM signal_performance
                    WHERE performance_date >= $1
                      AND price_at_signal IS NOT NULL 
                      AND price_after_1h IS NOT NULL 
                      AND price_after_1d IS NOT NULL
                      AND price_after_1h != price_at_signal  -- Exclude 0% changes
                      AND price_after_1d != price_at_signal  -- Exclude 0% changes
                    GROUP BY ticker
                    HAVING COUNT(*) >= 2
                    ORDER BY success_1d DESC NULLS LAST
                    LIMIT 8
                ''', since_date)
                
                if ticker_stats:
                    ticker_text = ""
                    for ticker in ticker_stats:
                        ticker_text += f"**{ticker['ticker']}:** 1h={ticker['success_1h'] or 0}%, 6h={ticker['success_6h'] or 0}%, 1d={ticker['success_1d'] or 0}% ({ticker['count']} signals)\n"
                    
                    embed.add_field(
                        name="📈 Success by Ticker (CORRECTED)",
                        value=ticker_text,
                        inline=False
                    )
        
        embed.set_footer(text="✅ Using timeframes: 1h, 3h, 6h, 1d | Bullish signals profit from price increases, Bearish signals profit from price decreases")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error getting success rates: {e}")

@bot.command(name='correlations')
async def signal_correlations(ctx, days: int = 30):
    """Analyze correlations between signals and identify patterns that work together
    
    Usage:
    !correlations      - Analyze last 30 days
    !correlations 7    - Analyze last 7 days
    !correlations 90   - Analyze last 90 days
    """
    try:
        if days < 1 or days > 365:
            await ctx.send("❌ Days must be between 1 and 365")
            return
            
        embed = discord.Embed(
            title=f"🔗 Enhanced Signal Correlation Analysis ({days} days)",
            description="Advanced correlation patterns, market conditions & signal intelligence",
            color=0x9932cc,
            timestamp=datetime.now(EST)
        )
        
        # Send typing indicator
        async with ctx.typing():
            from advanced_analytics import advanced_analytics
            
            analysis = await advanced_analytics.get_correlation_analysis(days)
            
            if "error" in analysis:
                embed.add_field(
                    name="❌ Analysis Error",
                    value=analysis["error"],
                    inline=False
                )
                embed.color = 0xff6600
            else:
                # Data Quality Score (NEW)
                quality_score = analysis.get("data_quality_score", 0)
                quality_emoji = "🟢" if quality_score >= 0.8 else "🟡" if quality_score >= 0.6 else "🔴"
                
                # Signal combinations
                combinations = analysis.get("signal_combinations", {})
                high_success = combinations.get("high_success_combinations", [])
                
                if high_success:
                    combo_text = ""
                    for combo in high_success[:4]:  # Top 4 to save space
                        combo_text += f"🎯 **{combo['combination'][:35]}**\n"
                        combo_text += f"   Success: {combo['success_rate']:.1f}% | Return: {combo['avg_return']:.1f}% | Count: {combo['occurrence_count']}\n\n"
                    
                    embed.add_field(
                        name="🚀 High-Success Signal Combinations",
                        value=combo_text[:1000],
                        inline=False
                    )
                
                # NEW: Strength Analysis
                strength_analysis = analysis.get("strength_analysis", {})
                if strength_analysis:
                    strength_corr = strength_analysis.get("strength_correlation", {})
                    optimal_strengths = strength_analysis.get("optimal_strength_ranges", [])
                    
                    if optimal_strengths:
                        strength_text = ""
                        for strength in optimal_strengths[:3]:
                            strength_text += f"💪 **Strength {strength['range']}:** {strength['success_rate']:.1f}% success, {strength['avg_return']:.1f}% return ({strength['count']} signals)\n"
                        
                        embed.add_field(
                            name="💪 Optimal Signal Strengths",
                            value=strength_text,
                            inline=True
                        )
                
                # NEW: Market Conditions Analysis
                market_conditions = analysis.get("market_conditions", {})
                if market_conditions:
                    volatility_performance = market_conditions.get("volatility_performance", [])
                    market_regime = market_conditions.get("market_regime_analysis", {})
                    
                    if volatility_performance:
                        vol_text = ""
                        for vol in volatility_performance[:3]:
                            vol_emoji = "🔥" if vol['category'] == 'High' else "⚡" if vol['category'] == 'Medium' else "🌊"
                            vol_text += f"{vol_emoji} **{vol['category']} Vol:** {vol['success_rate']:.1f}% success, {vol['avg_return']:.1f}% return\n"
                        
                        embed.add_field(
                            name="🌊 Market Volatility Impact",
                            value=vol_text,
                            inline=True
                        )
                
                # Temporal patterns (enhanced)
                temporal = analysis.get("temporal_patterns", {})
                best_hours = temporal.get("best_hours", [])
                best_days = temporal.get("best_days", [])
                
                if best_hours:
                    hours_text = ""
                    for hour_data in best_hours[:4]:
                        time_emoji = "🌅" if 6 <= hour_data['hour'] <= 11 else "☀️" if 12 <= hour_data['hour'] <= 17 else "🌙"
                        hours_text += f"{time_emoji} **{hour_data['hour']:02d}:00** - {hour_data['success_rate']:.1f}% ({hour_data['signal_count']} signals)\n"
                    
                    embed.add_field(
                        name="🕐 Peak Performance Hours",
                        value=hours_text,
                        inline=True
                    )
                
                if best_days:
                    days_text = ""
                    for day_data in best_days[:4]:
                        day_emoji = "📈" if day_data['success_rate'] > 50 else "📊"
                        days_text += f"{day_emoji} **{day_data['day'][:3]}** - {day_data['success_rate']:.1f}% ({day_data['signal_count']} signals)\n"
                    
                    embed.add_field(
                        name="📆 Best Trading Days",
                        value=days_text,
                        inline=True
                    )
                
                # NEW: System Performance Analysis
                system_performance = analysis.get("system_performance", {})
                if system_performance:
                    system_rankings = system_performance.get("system_rankings", [])
                    
                    if system_rankings:
                        system_text = ""
                        for system in system_rankings[:4]:
                            sys_emoji = "🥇" if system['rank'] == 1 else "🥈" if system['rank'] == 2 else "🥉" if system['rank'] == 3 else "🏅"
                            system_text += f"{sys_emoji} **{system['system']}:** {system['success_rate']:.1f}% success ({system['signal_count']} signals)\n"
                        
                        embed.add_field(
                            name="🎯 Top Signal Systems",
                            value=system_text,
                            inline=True
                        )
                
                # Ticker correlations (enhanced)
                ticker_corr = analysis.get("ticker_correlations", {})
                ticker_success = ticker_corr.get("ticker_success_correlation", [])
                
                if ticker_success:
                    ticker_text = ""
                    for ticker_data in ticker_success[:5]:
                        perf_emoji = "🚀" if ticker_data['success_rate'] > 60 else "📈" if ticker_data['success_rate'] > 40 else "📊"
                        ticker_text += f"{perf_emoji} **{ticker_data['ticker']}** - {ticker_data['success_rate']:.1f}% ({ticker_data['signal_count']} signals)\n"
                    
                    embed.add_field(
                        name="🏆 Top Performing Assets",
                        value=ticker_text,
                        inline=True
                    )
                
                # NEW: Statistical Significance & Volatility Patterns
                stats_sig = analysis.get("statistical_significance", {})
                volatility_patterns = analysis.get("volatility_patterns", {})
                
                insights_text = ""
                
                if stats_sig:
                    confidence_level = stats_sig.get("overall_confidence", "Medium")
                    conf_emoji = "🟢" if confidence_level == "High" else "🟡" if confidence_level == "Medium" else "🔴"
                    insights_text += f"{conf_emoji} **Statistical Confidence:** {confidence_level}\n"
                
                if volatility_patterns:
                    vol_trend = volatility_patterns.get("trend", "Neutral")
                    trend_emoji = "📈" if vol_trend == "Increasing" else "📉" if vol_trend == "Decreasing" else "➡️"
                    insights_text += f"{trend_emoji} **Market Volatility Trend:** {vol_trend}\n"
                
                # Analysis summary with enhanced metrics
                summary_text = f"""
**Signals Analyzed:** {analysis.get('total_signals_analyzed', 0):,}
**Analysis Period:** {analysis.get('analysis_period', 'N/A')}
**Data Quality:** {quality_emoji} {quality_score*100:.0f}%"""
                
                if insights_text:
                    summary_text += f"\n\n**Key Insights:**\n{insights_text}"
                
                embed.add_field(
                    name="📊 Analysis Summary",
                    value=summary_text,
                    inline=False
                )
        
        embed.set_footer(text="🔬 Enhanced with ML patterns, volatility analysis & statistical validation | Use longer timeframes for higher confidence")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error analyzing correlations: {e}")

@bot.command(name='mlpredict')
async def ml_predictions(ctx, days: int = 90):
    """Enhanced machine learning predictions for signal success probability
    
    Usage:
    !mlpredict        - Train on 90 days, predict recent signals
    !mlpredict 60     - Train on 60 days (faster training)
    !mlpredict 180    - Train on 180 days (higher accuracy)
    !mlpredict 365    - Train on full year (maximum accuracy)
    """
    try:
        if days < 30 or days > 365:
            await ctx.send("❌ Days must be between 30 and 365 for ML training")
            return
            
        embed = discord.Embed(
            title=f"🤖 Enhanced ML Signal Predictions ({days}-day training)",
            description="Advanced machine learning predictions with risk analysis & ensemble voting",
            color=0x00ff88,
            timestamp=datetime.now(EST)
        )
        
        # Send typing indicator
        async with ctx.typing():
            from advanced_analytics import advanced_analytics
            
            ml_analysis = await advanced_analytics.get_ml_predictions(days)
            
            if "error" in ml_analysis:
                embed.add_field(
                    name="❌ ML Analysis Error",
                    value=ml_analysis["error"],
                    inline=False
                )
                embed.color = 0xff6600
            else:
                # Enhanced Model performance
                performance = ml_analysis.get("model_performance", {})
                if performance:
                    perf_text = ""
                    best_model = None
                    best_score = 0
                    
                    for model_name, metrics in performance.items():
                        accuracy = metrics.get('accuracy', 0)
                        cv_mean = metrics.get('cv_mean', 0)
                        auc = metrics.get('auc_score', accuracy)  # Fallback to accuracy if AUC not available
                        
                        # Determine best model
                        combined_score = (accuracy + cv_mean + auc) / 3
                        if combined_score > best_score:
                            best_score = combined_score
                            best_model = model_name
                        
                        # Model performance display
                        perf_emoji = "🥇" if model_name == best_model else "🥈" if combined_score > 0.6 else "🥉"
                        perf_text += f"{perf_emoji} **{model_name}:**\n"
                        perf_text += f"   Accuracy: {accuracy*100:.1f}% | AUC: {auc*100:.1f}%\n"
                        perf_text += f"   Cross-Val: {cv_mean*100:.1f}% ±{metrics.get('cv_std', 0)*100:.1f}%\n\n"
                    
                    embed.add_field(
                        name="🔬 Model Performance Rankings",
                        value=perf_text,
                        inline=False
                    )
                
                # Enhanced Feature importance with categories
                importance = ml_analysis.get("feature_importance", {})
                if importance and "Random Forest" in importance:
                    imp_text = ""
                    rf_importance = importance["Random Forest"]
                    feature_categories = {
                        'signal_type_encoded': ('🎯', 'Signal Type'),
                        'ticker_encoded': ('📈', 'Asset'),
                        'timeframe_encoded': ('⏱️', 'Timeframe'),
                        'signal_hour': ('🕐', 'Hour of Day'),
                        'signal_dow': ('📅', 'Day of Week'),
                        'signal_direction_encoded': ('📊', 'Signal Direction'),
                        'strength': ('💪', 'Signal Strength'),
                        'system_encoded': ('🔧', 'Signal System'),
                        'volatility_score': ('🌊', 'Volatility'),
                        'momentum_score': ('🚀', 'Momentum'),
                        'market_sentiment': ('😊', 'Market Sentiment'),
                        'signal_frequency': ('📡', 'Signal Frequency'),
                        'historical_success_rate': ('📚', 'Historical Success'),
                        'risk_score': ('⚠️', 'Risk Score')
                    }
                    
                    for feature, imp_val in list(rf_importance.items())[:6]:
                        emoji, display_name = feature_categories.get(feature, ('📊', feature))
                        imp_text += f"{emoji} **{display_name}:** {imp_val:.3f}\n"
                    
                    embed.add_field(
                        name="🎯 Most Predictive Factors",
                        value=imp_text,
                        inline=True
                    )
                
                # Ensemble & Risk Analysis (NEW)
                ensemble = ml_analysis.get("ensemble_predictions", {})
                risk_analysis = ml_analysis.get("risk_analysis", {})
                
                if ensemble or risk_analysis:
                    insights_text = ""
                    
                    if ensemble:
                        ensemble_acc = ensemble.get("ensemble_accuracy", 0)
                        improvement = ensemble.get("improvement_over_best", 0)
                        insights_text += f"🤝 **Ensemble Accuracy:** {ensemble_acc*100:.1f}%\n"
                        if improvement > 0:
                            insights_text += f"📈 **Improvement:** +{improvement*100:.1f}%\n"
                    
                    if risk_analysis:
                        risk_dist = risk_analysis.get("risk_distribution", {})
                        if risk_dist:
                            insights_text += f"⚠️ **High Risk Signals:** {risk_dist.get('high_risk', 0)*100:.0f}%\n"
                            insights_text += f"✅ **Low Risk Signals:** {risk_dist.get('low_risk', 0)*100:.0f}%\n"
                    
                    if insights_text:
                        embed.add_field(
                            name="🧠 ML Insights & Risk Analysis",
                            value=insights_text,
                            inline=True
                        )
                
                # Enhanced Recent predictions with risk levels
                predictions = ml_analysis.get("predictions", {})
                recent_preds = predictions.get("recent_predictions", [])
                
                if recent_preds:
                    pred_text = ""
                    for pred in recent_preds[:10]:  # Top 10 predictions
                        # Enhanced confidence and risk display
                        prob = pred.get('ensemble_success_probability', pred.get('predicted_success_probability', 0))
                        confidence = pred.get('confidence_level', 'MEDIUM')
                        risk_level = pred.get('risk_level', 'MEDIUM')
                        
                        # Smart emoji selection
                        confidence_emoji = "🔥" if confidence == 'HIGH' else "⚡" if confidence == 'MEDIUM' else "💡"
                        risk_emoji = "🟢" if risk_level == 'LOW' else "🟡" if risk_level == 'MEDIUM' else "🔴"
                        outcome_emoji = "✅" if pred['predicted_outcome'] == 'SUCCESS' else "❌"
                        actual_emoji = "✅" if pred['actual_outcome'] == 'SUCCESS' else "❌"
                        
                        pred_text += f"{confidence_emoji}{risk_emoji} **{pred['ticker']}** {pred['timeframe']} - {prob*100:.1f}%\n"
                        pred_text += f"   {outcome_emoji} Predicted | {actual_emoji} Actual | Risk: {risk_level}\n\n"
                    
                    embed.add_field(
                        name="🔮 Recent ML Predictions (🔥=High Conf, 🟢=Low Risk)",
                        value=pred_text[:1000],
                        inline=False
                    )
                
                # Enhanced Training & Prediction stats
                training_stats = ml_analysis.get("training_stats", {})
                pred_summary = predictions.get("prediction_summary", {}) if predictions else {}
                
                stats_text = ""
                if training_stats:
                    stats_text += f"**Training Data:** {training_stats.get('training_samples', 0):,} signals\n"
                    stats_text += f"**Success Rate:** {training_stats.get('positive_class_ratio', 0)*100:.1f}%\n"
                    stats_text += f"**Features Used:** {training_stats.get('feature_count', 9)}\n"
                
                if pred_summary:
                    stats_text += f"**Recent Signals:** {pred_summary.get('total_recent_signals', 0)}\n"
                    stats_text += f"**High Confidence:** {pred_summary.get('high_confidence_predictions', 0)}\n"
                    stats_text += f"**Low Risk:** {pred_summary.get('low_risk_predictions', 0)}"
                
                if stats_text:
                    embed.add_field(
                        name="📊 Training & Prediction Statistics",
                        value=stats_text,
                        inline=True
                    )
                
                # Actionable recommendations (NEW)
                if recent_preds:
                    recommendations = []
                    high_conf_low_risk = [p for p in recent_preds if p.get('confidence_level') == 'HIGH' and p.get('risk_level') == 'LOW']
                    avoid_signals = [p for p in recent_preds if p.get('risk_level') == 'HIGH' and p.get('ensemble_success_probability', 0) < 0.4]
                    
                    if high_conf_low_risk:
                        recommendations.append(f"🎯 **Best Bets:** {len(high_conf_low_risk)} high-confidence, low-risk signals")
                    if avoid_signals:
                        recommendations.append(f"⚠️ **Avoid:** {len(avoid_signals)} high-risk signals")
                    if len(recent_preds) > 0:
                        avg_prob = np.mean([p.get('ensemble_success_probability', 0) for p in recent_preds])
                        recommendations.append(f"📈 **Market Outlook:** {avg_prob*100:.0f}% avg success probability")
                    
                    if recommendations:
                        embed.add_field(
                            name="💡 Actionable Recommendations",
                            value="\n".join(recommendations),
                            inline=False
                        )
        
        embed.set_footer(text="🤖 Enhanced ML with ensemble voting, risk analysis & advanced features | More training data = higher accuracy")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error generating enhanced ML predictions: {e}")

@bot.command(name='debugapi')
async def debug_api_response(ctx, ticker: str = "AAPL", timeframe: str = "1d"):
    """Debug command to inspect API response structure for pricing data
    
    Usage:
    !debugapi            - Debug AAPL 1d response
    !debugapi TSLA 1h    - Debug TSLA 1h response
    """
    try:
        async with ctx.typing():
            notifier = SignalNotifier(bot)
            
            # Make API call
            params = {
                'ticker': ticker.upper(),
                'interval': timeframe,
                'period': '1mo'
            }
            response = requests.get(f"{API_BASE_URL}/api/analyzer-b", params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                embed = discord.Embed(
                    title=f"🔍 API Response Debug: {ticker.upper()} ({timeframe})",
                    description="Analyzing API response structure for pricing data",
                    color=0x9932cc,
                    timestamp=datetime.now(EST)
                )
                
                # Show main keys
                main_keys = list(data.keys()) if isinstance(data, dict) else []
                embed.add_field(
                    name="🗝️ Main Response Keys",
                    value=f"```{', '.join(main_keys[:10])}{'...' if len(main_keys) > 10 else ''}```",
                    inline=False
                )
                
                # Look for potential pricing data
                pricing_candidates = []
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, list) and len(value) > 0:
                            first_item = value[0]
                            if isinstance(first_item, dict):
                                item_keys = list(first_item.keys())
                                # Check if it looks like pricing data
                                price_indicators = ['price', 'close', 'open', 'high', 'low', 'volume', 'timestamp', 'date', 'time']
                                if any(indicator in ' '.join(item_keys).lower() for indicator in price_indicators):
                                    pricing_candidates.append({
                                        'key': key,
                                        'count': len(value),
                                        'sample_keys': item_keys[:5]
                                    })
                
                if pricing_candidates:
                    candidates_text = ""
                    for candidate in pricing_candidates[:3]:
                        candidates_text += f"**{candidate['key']}**: {candidate['count']} items\n"
                        candidates_text += f"  Sample keys: {', '.join(candidate['sample_keys'])}\n\n"
                    
                    embed.add_field(
                        name="💰 Potential Pricing Data",
                        value=candidates_text[:1000],
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="💰 Potential Pricing Data",
                        value="No obvious pricing data arrays found",
                        inline=False
                    )
                
                # Show a sample of the first pricing candidate
                if pricing_candidates:
                    first_candidate = pricing_candidates[0]
                    sample_data = data[first_candidate['key']][:2]  # First 2 items
                    
                    embed.add_field(
                        name=f"📊 Sample from '{first_candidate['key']}'",
                        value=f"```json\n{json.dumps(sample_data, indent=2)[:500]}...```",
                        inline=False
                    )
                
                # Auto-extraction test
                extracted = notifier.extract_pricing_data_from_api(data)
                if extracted:
                    embed.add_field(
                        name="🤖 Auto-Extraction Result",
                        value=f"✅ Found {len(extracted)} data points\nFirst item keys: {list(extracted[0].keys()) if extracted else 'None'}",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="🤖 Auto-Extraction Result",
                        value="❌ No pricing data extracted with current logic",
                        inline=False
                    )
                
            else:
                embed = discord.Embed(
                    title="❌ API Debug Failed",
                    description=f"API returned status {response.status_code}",
                    color=0xff0000
                )
            
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error debugging API response: {e}")

@bot.command(name='debugperformance')
async def debug_performance_tracking(ctx, ticker: str = "AAPL"):
    """Debug command to check if performance tracking is working with real notifications
    
    Usage:
    !debugperformance AAPL - Check AAPL performance tracking
    !debugperformance TSLA - Check TSLA performance tracking
    """
    try:
        embed = discord.Embed(
            title=f"🔍 Performance Tracking Debug: {ticker.upper()}",
            description="Checking connection between notifications and performance data",
            color=0x9932cc,
            timestamp=datetime.now(EST)
        )
        
        async with ctx.typing():
            from database import db_manager
            
            async with db_manager.pool.acquire() as conn:
                # Check recent notifications
                recent_notifications = await conn.fetch('''
                    SELECT ticker, timeframe, signal_type, signal_date, notified_at
                    FROM signal_notifications
                    WHERE ticker = $1 
                      AND notified_at >= NOW() - INTERVAL '7 days'
                    ORDER BY notified_at DESC
                    LIMIT 5
                ''', ticker.upper())
                
                # Check performance data
                performance_data = await conn.fetch('''
                    SELECT ticker, timeframe, signal_type, signal_date, performance_date,
                           success_1h, success_1d, price_at_signal
                    FROM signal_performance
                    WHERE ticker = $1 
                      AND performance_date >= NOW() - INTERVAL '7 days'
                    ORDER BY performance_date DESC
                    LIMIT 5
                ''', ticker.upper())
                
                # Check for pending performance updates
                pending_updates = await conn.fetch('''
                    SELECT sn.ticker, sn.timeframe, sn.signal_type, sn.signal_date, sn.notified_at
                    FROM signal_notifications sn
                    LEFT JOIN signal_performance sp ON (
                        sn.ticker = sp.ticker AND 
                        sn.timeframe = sp.timeframe AND 
                        sn.signal_type = sp.signal_type AND 
                        sn.signal_date = sp.signal_date
                    )
                    WHERE sn.ticker = $1 
                      AND sn.notified_at >= NOW() - INTERVAL '7 days'
                      AND sp.id IS NULL
                    ORDER BY sn.signal_date DESC
                    LIMIT 10
                ''', ticker.upper())
                
                # Display results
                embed.add_field(
                    name="📬 Recent Notifications (7 days)",
                    value=f"**Found:** {len(recent_notifications)} notifications\n" + 
                          (f"**Latest:** {recent_notifications[0]['signal_type']} at {recent_notifications[0]['notified_at'].strftime('%Y-%m-%d %H:%M')}" if recent_notifications else "**Latest:** None"),
                    inline=False
                )
                
                embed.add_field(
                    name="📊 Performance Data (7 days)",
                    value=f"**Found:** {len(performance_data)} performance records\n" +
                          (f"**Latest:** {performance_data[0]['signal_type']} - 1h: {'✅' if performance_data[0]['success_1h'] else '❌'}, 1d: {'✅' if performance_data[0]['success_1d'] else '❌'}" if performance_data else "**Latest:** None"),
                    inline=False
                )
                
                embed.add_field(
                    name="⏳ Pending Performance Updates",
                    value=f"**Count:** {len(pending_updates)} notifications waiting for performance tracking\n" +
                          ("\n".join([f"• {p['signal_type']} from {p['signal_date'].strftime('%Y-%m-%d %H:%M')}" for p in pending_updates[:3]]) if pending_updates else "**Status:** All caught up!"),
                    inline=False
                )
                
                # Determine overall status
                if len(recent_notifications) == 0:
                    status = "🟡 No recent notifications to track"
                    embed.color = 0xffff00
                elif len(performance_data) == 0:
                    status = "🔴 Notifications exist but no performance data"
                    embed.color = 0xff0000
                elif len(pending_updates) > len(performance_data):
                    status = "🟡 Performance tracking is behind"
                    embed.color = 0xffff00
                else:
                    status = "🟢 Performance tracking is working"
                    embed.color = 0x00ff00
                
                embed.add_field(
                    name="🏥 Overall Status",
                    value=status,
                    inline=False
                )
                
                # Show recent notification details
                if recent_notifications:
                    notification_details = ""
                    for i, notif in enumerate(recent_notifications[:3]):
                        has_performance = any(
                            p['signal_type'] == notif['signal_type'] and 
                            p['signal_date'].replace(tzinfo=None) == notif['signal_date'].replace(tzinfo=None)
                            for p in performance_data
                        )
                        status_icon = "✅" if has_performance else "⏳"
                        notification_details += f"{status_icon} {notif['signal_type']} ({notif['timeframe']}) - {notif['notified_at'].strftime('%m/%d %H:%M')}\n"
                    
                    embed.add_field(
                        name="📋 Notification Status",
                        value=notification_details,
                        inline=False
                    )
        
        embed.set_footer(text="💡 Use !testperformance to add sample data • !updateanalytics to process existing signals")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error debugging performance tracking: {e}")

@bot.command(name='debugauto')
async def debug_auto_performance(ctx, ticker: str = "AAPL", timeframe: str = "1d"):
    """Debug the auto_update_signal_performance method step by step
    
    Usage:
    !debugauto AAPL 1d - Debug AAPL daily performance tracking
    !debugauto TSLA 1h - Debug TSLA hourly performance tracking
    """
    try:
        embed = discord.Embed(
            title=f"🔬 Auto Performance Debug: {ticker.upper()} ({timeframe})",
            description="Step-by-step debugging of automatic performance tracking",
            color=0xff6600,
            timestamp=datetime.now(EST)
        )
        
        async with ctx.typing():
            notifier = SignalNotifier(bot)
            debug_info = []
            
            # Step 1: Check DATABASE_URL
            import os
            DATABASE_URL = os.getenv('DATABASE_URL')
            if DATABASE_URL:
                debug_info.append("✅ DATABASE_URL environment variable is set")
            else:
                debug_info.append("❌ DATABASE_URL environment variable is missing")
                embed.add_field(name="🔍 Debug Results", value="\n".join(debug_info), inline=False)
                embed.color = 0xff0000
                await ctx.send(embed=embed)
                return
            
            # Step 2: Test direct database connection
            try:
                import asyncpg
                conn = await asyncpg.connect(DATABASE_URL)
                debug_info.append("✅ Direct database connection successful")
                
                # Step 3: Check for pending signals
                pending_signals = await conn.fetch('''
                    SELECT sn.ticker, sn.timeframe, sn.signal_type, sn.signal_date, sn.notified_at
                    FROM signal_notifications sn
                    LEFT JOIN signal_performance sp ON (
                        sn.ticker = sp.ticker AND 
                        sn.timeframe = sp.timeframe AND 
                        sn.signal_type = sp.signal_type AND 
                        sn.signal_date = sp.signal_date
                    )
                    WHERE sn.ticker = $1 
                      AND sn.timeframe = $2
                      AND sn.notified_at >= NOW() - INTERVAL '7 days'
                      AND sp.id IS NULL
                    ORDER BY sn.signal_date DESC
                    LIMIT 3
                ''', ticker.upper(), timeframe)
                
                debug_info.append(f"✅ Found {len(pending_signals)} pending signals for {ticker} {timeframe}")
                
                if len(pending_signals) == 0:
                    debug_info.append("⚠️ No pending signals to process - this might be why no performance data")
                    await conn.close()
                    embed.add_field(name="🔍 Debug Results", value="\n".join(debug_info), inline=False)
                    embed.color = 0xffff00
                    await ctx.send(embed=embed)
                    return
                
                await conn.close()
                
            except Exception as e:
                debug_info.append(f"❌ Database connection failed: {str(e)[:100]}")
                embed.add_field(name="🔍 Debug Results", value="\n".join(debug_info), inline=False)
                embed.color = 0xff0000
                await ctx.send(embed=embed)
                return
            
            # Step 4: Test API call and data extraction
            try:
                import requests
                params = {
                    'ticker': ticker.upper(),
                    'interval': timeframe,
                    'period': '1mo'
                }
                response = requests.get(f"{API_BASE_URL}/api/analyzer-b", params=params, timeout=30)
                
                if response.status_code == 200:
                    debug_info.append(f"✅ API call successful (status: {response.status_code})")
                    
                    api_data = response.json()
                    pricing_data = notifier.extract_pricing_data_from_api(api_data)
                    
                    if pricing_data:
                        debug_info.append(f"✅ Pricing data extracted: {len(pricing_data)} data points")
                        
                        # Show sample of pricing data
                        if len(pricing_data) > 0:
                            sample = pricing_data[0]
                            sample_keys = list(sample.keys())[:5]
                            debug_info.append(f"📊 Sample data keys: {', '.join(sample_keys)}")
                    else:
                        debug_info.append("❌ Failed to extract pricing data from API response")
                        # Show API response structure
                        api_keys = list(api_data.keys())[:5] if isinstance(api_data, dict) else []
                        debug_info.append(f"🔍 API response keys: {', '.join(api_keys)}")
                        
                else:
                    debug_info.append(f"❌ API call failed (status: {response.status_code})")
                    
            except Exception as e:
                debug_info.append(f"❌ API call error: {str(e)[:100]}")
            
            # Step 5: Test performance calculation
            if 'pricing_data' in locals() and pricing_data and len(pending_signals) > 0:
                try:
                    test_signal = pending_signals[0]
                    signal_datetime = test_signal['signal_date']
                    
                    performance = notifier.calculate_performance_from_pricing(
                        signal_datetime, pricing_data, timeframe
                    )
                    
                    if performance and performance.get('price_at_signal'):
                        debug_info.append("✅ Performance calculation successful")
                        debug_info.append(f"📈 Signal price: ${performance['price_at_signal']:.2f}")
                        debug_info.append(f"📈 1h price: ${performance.get('price_after_1h', 0):.2f}")
                        debug_info.append(f"📈 1d price: ${performance.get('price_after_1d', 0):.2f}")
                    else:
                        debug_info.append("❌ Performance calculation failed")
                        debug_info.append(f"🔍 Signal datetime: {signal_datetime}")
                        
                except Exception as e:
                    debug_info.append(f"❌ Performance calculation error: {str(e)[:100]}")
            
            # Step 6: Test record_signal_performance function
            if 'performance' in locals() and performance and performance.get('price_at_signal'):
                try:
                    from database import record_signal_performance
                    
                    # Try to record the performance
                    success = await record_signal_performance(
                        ticker=ticker.upper(),
                timeframe=timeframe,
                        signal_type=test_signal['signal_type'],
                        signal_date=test_signal['signal_date'].strftime('%Y-%m-%d %H:%M:%S'),
                        price_at_signal=performance['price_at_signal'],
                        price_after_1h=performance.get('price_after_1h'),
                        price_after_4h=performance.get('price_after_4h'),
                        price_after_1d=performance.get('price_after_1d'),
                        price_after_3d=performance.get('price_after_3d')
                    )
                    
                    if success:
                        debug_info.append("✅ Performance record saved successfully")
                    else:
                        debug_info.append("❌ Failed to save performance record")
                        
                except Exception as e:
                    debug_info.append(f"❌ Record performance error: {str(e)[:100]}")
        
        # Format results
        embed.add_field(
            name="🔍 Step-by-Step Debug Results",
            value="\n".join(debug_info[:15]),  # Limit to avoid Discord message limits
            inline=False
        )
        
        # Determine overall status
        if "❌" in "\n".join(debug_info):
            embed.color = 0xff0000
            embed.add_field(name="🚨 Issues Found", value="Check the failed steps above", inline=False)
        else:
            embed.color = 0x00ff00
            embed.add_field(name="✅ All Steps Passed", value="Performance tracking should be working", inline=False)
        
        embed.set_footer(text="💡 This shows exactly where the auto_update_signal_performance method is failing")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error in debug command: {e}")

@bot.command(name='backfill')
async def performance_backfill(ctx, action: str = None, limit: int = 15, days: int = 3):
    """Enhanced backfill for ALL timeframes (1h, 3h, 4h, 6h, 1d, 3d)"""
    if action == "help" or action is None:
        help_text = """
🔄 **ENHANCED BACKFILL SYSTEM** 🔄

**Commands:**
• `!backfill check` - Check data completeness status
• `!backfill run [limit] [days]` - Run comprehensive backfill
• `!backfill quick [limit]` - Quick populate recent signals

**What it does:**
✅ Populates ALL timeframes: 1h, 3h, 4h, 6h, 1d, 3d
✅ Backfills existing records missing 3h/6h data
✅ Uses smart interpolation for accurate data
✅ Calculates success flags for all timeframes

**Examples:**
• `!backfill run` - Standard backfill (15 signals, 3 days)
• `!backfill run 50 7` - Backfill 50 signals from last 7 days
• `!backfill check` - See current data status
        """
        
        embed = discord.Embed(
            title="🔄 Enhanced Backfill System",
            description=help_text,
            color=0x00ff00
        )
        await ctx.send(embed=embed)
        return
    
    if action == "check":
        try:
            conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
            
            # Get comprehensive data status
            status_query = '''
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(price_after_1h) as has_1h,
                    COUNT(price_after_3h) as has_3h,
                    COUNT(price_after_4h) as has_4h,
                    COUNT(price_after_6h) as has_6h,
                    COUNT(price_after_1d) as has_1d,
                    COUNT(price_after_3d) as has_3d,
                    COUNT(success_1h) as success_1h,
                    COUNT(success_3h) as success_3h,
                    COUNT(success_4h) as success_4h,
                    COUNT(success_6h) as success_6h,
                    COUNT(success_1d) as success_1d,
                    COUNT(success_3d) as success_3d
                FROM signal_performance
                WHERE performance_date >= NOW() - INTERVAL '30 days'
            '''
            
            result = await conn.fetchrow(status_query)
            await conn.close()
            
            total = result['total_records']
            if total == 0:
                await ctx.send("📊 No performance records found in the last 30 days")
                return
            
            # Create status embed
            embed = discord.Embed(
                title="📊 Performance Data Status (Last 30 Days)",
                color=0x3498db
            )
            
            # Price data completeness
            price_status = f"""
**Price Data Completeness:**
• 1h: {result['has_1h']}/{total} ({(result['has_1h']/total*100):.1f}%)
• 3h: {result['has_3h']}/{total} ({(result['has_3h']/total*100):.1f}%)
• 4h: {result['has_4h']}/{total} ({(result['has_4h']/total*100):.1f}%)
• 6h: {result['has_6h']}/{total} ({(result['has_6h']/total*100):.1f}%)
• 1d: {result['has_1d']}/{total} ({(result['has_1d']/total*100):.1f}%)
• 3d: {result['has_3d']}/{total} ({(result['has_3d']/total*100):.1f}%)
            """
            
            success_status = f"""
**Success Flag Completeness:**
• 1h: {result['success_1h']}/{total} ({(result['success_1h']/total*100):.1f}%)
• 3h: {result['success_3h']}/{total} ({(result['success_3h']/total*100):.1f}%)
• 4h: {result['success_4h']}/{total} ({(result['success_4h']/total*100):.1f}%)
• 6h: {result['success_6h']}/{total} ({(result['success_6h']/total*100):.1f}%)
• 1d: {result['success_1d']}/{total} ({(result['success_1d']/total*100):.1f}%)
• 3d: {result['success_3d']}/{total} ({(result['success_3d']/total*100):.1f}%)
            """
            
            embed.add_field(name="📈 Price Data", value=price_status, inline=False)
            embed.add_field(name="✅ Success Flags", value=success_status, inline=False)
            
            # Calculate missing data priority
            missing_3h = total - result['has_3h']
            missing_6h = total - result['has_6h']
            
            if missing_3h > 0 or missing_6h > 0:
                embed.add_field(
                    name="🎯 Recommended Action", 
                    value=f"Run `!backfill run` to fill {missing_3h + missing_6h} missing 3h/6h records",
                    inline=False
                )
            else:
                embed.add_field(
                    name="✅ Status", 
                    value="All critical timeframes are populated!",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error checking backfill status: {e}")
    
    elif action in ["run", "quick"]:
        try:
            # Send processing message
            processing_msg = await ctx.send(
                f"🔄 Running enhanced backfill (limit: {limit}, days: {days})..."
            )
            
            # Import and run the enhanced quick populate
            import sys
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            from quick_populate_performance import quick_populate
            result = await quick_populate(limit=limit, days_back=days)
            
            # Update processing message with results
            embed = discord.Embed(
                title="✅ Enhanced Backfill Complete!",
                color=0x00ff00
            )
            
            embed.add_field(
                name="📊 Results Summary",
                value=f"""
• **New Records Created:** {result['created']}
• **Existing Records Backfilled:** {result['backfilled']}
• **Total Improvements:** {result['total']}

✅ All timeframes populated: 1h, 3h, 4h, 6h, 1d, 3d
🎯 Now run `!successrates` to see updated analytics!
                """,
                inline=False
            )
            
            await processing_msg.edit(content="", embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Backfill failed: {str(e)}")
            import traceback
            traceback.print_exc()
            
    else:
        await ctx.send(
            "❓ Unknown action. Use `!backfill help` for usage instructions."
        )

@bot.command(name='besttimes')
async def ml_best_times(ctx, days: int = 30):
    """🕐 ML-powered analysis of best times to send signals
    
    Usage:
    !besttimes        - Analyze last 30 days
    !besttimes 60     - Analyze last 60 days  
    !besttimes 90     - Analyze last 90 days
    """
    try:
        if days < 7 or days > 365:
            await ctx.send("❌ Days must be between 7 and 365")
            return
            
        embed = discord.Embed(
            title=f"🕐 ML-Powered Best Signal Times ({days}-day analysis)",
            description="Discover optimal times for highest signal success rates",
            color=0x00ff88,
            timestamp=datetime.now(EST)
        )
        
        # Send typing indicator
        async with ctx.typing():
            from advanced_analytics import advanced_analytics
            
            timing_analysis = await advanced_analytics.analyze_optimal_timing(days)
            
            if "error" in timing_analysis:
                embed.add_field(
                    name="❌ Analysis Error",
                    value=timing_analysis["error"],
                    inline=False
                )
                embed.color = 0xff6600
            else:
                # Best Hours
                best_hours = timing_analysis.get("best_hours", {})
                if best_hours:
                    hours_text = ""
                    for hour, data in list(best_hours.items())[:5]:
                        success_rate = data['success_rate'] * 100
                        signal_count = data['signal_count']
                        emoji = "🔥" if success_rate >= 60 else "⭐" if success_rate >= 50 else "💡"
                        
                        # Convert to 12-hour format
                        hour_12 = int(hour)
                        am_pm = "AM" if hour_12 < 12 else "PM"
                        if hour_12 == 0:
                            hour_12 = 12
                        elif hour_12 > 12:
                            hour_12 -= 12
                            
                        hours_text += f"{emoji} **{hour_12}:00 {am_pm}:** {success_rate:.1f}% success ({signal_count} signals)\n"
                    
                    embed.add_field(
                        name="⏰ Best Hours for Signals",
                        value=hours_text,
                        inline=False
                    )
                
                # Best Days of Week
                best_days = timing_analysis.get("best_days", {})
                if best_days:
                    days_text = ""
                    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                    
                    for day_num, data in best_days.items():
                        success_rate = data['success_rate'] * 100
                        signal_count = data['signal_count']
                        day_name = day_names[int(day_num)] if int(day_num) < len(day_names) else f"Day {day_num}"
                        
                        emoji = "🔥" if success_rate >= 60 else "⭐" if success_rate >= 50 else "💡"
                        days_text += f"{emoji} **{day_name}:** {success_rate:.1f}% success ({signal_count} signals)\n"
                    
                    embed.add_field(
                        name="📅 Best Days of Week",
                        value=days_text,
                        inline=True
                    )
                
                # Peak Performance Combinations
                peak_combos = timing_analysis.get("peak_combinations", [])
                if peak_combos:
                    combo_text = ""
                    for combo in peak_combos[:3]:
                        day_name = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][combo['day']]
                        hour_12 = combo['hour'] if combo['hour'] <= 12 else combo['hour'] - 12
                        hour_12 = 12 if hour_12 == 0 else hour_12
                        am_pm = "AM" if combo['hour'] < 12 else "PM"
                        
                        combo_text += f"🎯 **{day_name} {hour_12}:00 {am_pm}:** {combo['success_rate']*100:.1f}% success\n"
                    
                    embed.add_field(
                        name="🎯 Peak Performance Times",
                        value=combo_text,
                        inline=True
                    )
                
                # Market Insights
                insights = timing_analysis.get("insights", {})
                if insights:
                    insights_text = ""
                    
                    if insights.get('best_hour_overall'):
                        best_hour = insights['best_hour_overall']
                        hour_12 = best_hour if best_hour <= 12 else best_hour - 12
                        hour_12 = 12 if hour_12 == 0 else hour_12
                        am_pm = "AM" if best_hour < 12 else "PM"
                        insights_text += f"⭐ **Golden Hour:** {hour_12}:00 {am_pm}\n"
                    
                    if insights.get('worst_hour_overall'):
                        worst_hour = insights['worst_hour_overall']
                        hour_12 = worst_hour if worst_hour <= 12 else worst_hour - 12
                        hour_12 = 12 if hour_12 == 0 else hour_12
                        am_pm = "AM" if worst_hour < 12 else "PM"
                        insights_text += f"⚠️ **Avoid Hour:** {hour_12}:00 {am_pm}\n"
                    
                    if insights.get('weekend_vs_weekday'):
                        weekend_better = insights['weekend_vs_weekday']
                        insights_text += f"📊 **{'Weekend' if weekend_better else 'Weekday'} signals perform better**\n"
                    
                    if insights_text:
                        embed.add_field(
                            name="💡 Key Insights",
                            value=insights_text,
                            inline=False
                        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error analyzing optimal times: {e}")

@bot.command(name='signalquality')
async def signal_quality_analysis(ctx, ticker: str = "AAPL", limit: int = 5):
    """🏆 Analyze signal quality using ML scoring system
    
    Usage:
    !signalquality AAPL     - Quality scores for AAPL (last 5 signals)
    !signalquality BTC 10   - Quality scores for BTC (last 10 signals)
    """
    try:
        if limit < 1 or limit > 20:
            await ctx.send("❌ Limit must be between 1 and 20")
            return
            
        embed = discord.Embed(
            title=f"🏆 Signal Quality Analysis: {ticker.upper()}",
            description=f"ML-powered quality scoring for last {limit} signals",
            color=0x00ff88,
            timestamp=datetime.now(EST)
        )
        
        # Send typing indicator
        async with ctx.typing():
            from advanced_analytics import advanced_analytics
            
            # Get recent signals for this ticker from the database
            conn = await init_database_connection()
            if not conn:
                await ctx.send("❌ Database connection failed")
                return
            
            recent_signals = await conn.fetch('''
                SELECT DISTINCT
                    ticker,
                    timeframe,
                    signal_type,
                    signal_date,
                    strength,
                    system
                FROM signal_performance sp
                WHERE ticker = $1
                  AND signal_date >= NOW() - INTERVAL '30 days'
                ORDER BY signal_date DESC
                LIMIT $2
            ''', ticker.upper(), limit)
            
            await conn.close()
            
            if not recent_signals:
                embed.add_field(
                    name="❌ No Recent Signals",
                    value=f"No signals found for {ticker.upper()} in the last 30 days",
                    inline=False
                )
                embed.color = 0xff6600
            else:
                quality_results = []
                
                for signal in recent_signals:
                    signal_features = {
                        'ticker': signal['ticker'],
                        'timeframe': signal['timeframe'],
                        'signal_type': signal['signal_type'],
                        'strength': signal['strength'],
                        'system': signal['system'],
                        'signal_date': str(signal['signal_date'])
                    }
                    
                    quality_result = await advanced_analytics.calculate_signal_quality_score(signal_features)
                    
                    if "error" not in quality_result:
                        quality_results.append({
                            'signal': signal,
                            'quality': quality_result
                        })
                
                if quality_results:
                    # Sort by quality score (highest first)
                    quality_results.sort(key=lambda x: x['quality']['quality_score'], reverse=True)
                    
                    # Display top signals
                    signals_text = ""
                    for i, result in enumerate(quality_results[:limit]):
                        signal = result['signal']
                        quality = result['quality']
                        
                        # Format signal date
                        signal_date = signal['signal_date'].strftime('%m/%d %H:%M')
                        
                        signals_text += f"{quality['grade_emoji']} **{quality['grade']} ({quality['quality_score']})** - "
                        signals_text += f"{signal['signal_type']} ({signal['timeframe']}) - {signal_date}\n"
                        signals_text += f"   *{quality['recommendation']}*\n\n"
                    
                    embed.add_field(
                        name="📊 Recent Signal Grades",
                        value=signals_text,
                        inline=False
                    )
                    
                    # Quality distribution
                    grades = [r['quality']['grade'] for r in quality_results]
                    grade_counts = {}
                    for grade in grades:
                        grade_counts[grade] = grade_counts.get(grade, 0) + 1
                    
                    distribution_text = ""
                    for grade, count in sorted(grade_counts.items(), reverse=True):
                        distribution_text += f"**{grade}:** {count} signals\n"
                    
                    embed.add_field(
                        name="📈 Quality Distribution",
                        value=distribution_text,
                        inline=True
                    )
                    
                    # Average quality score
                    avg_score = sum(r['quality']['quality_score'] for r in quality_results) / len(quality_results)
                    if avg_score >= 75:
                        avg_emoji = "🔥"
                    elif avg_score >= 65:
                        avg_emoji = "⭐"
                    elif avg_score >= 55:
                        avg_emoji = "👍"
                    else:
                        avg_emoji = "⚠️"
                    
                    embed.add_field(
                        name="📊 Average Quality",
                        value=f"{avg_emoji} **{avg_score:.1f}/100**",
                        inline=True
                    )
                    
                else:
                    embed.add_field(
                        name="❌ Analysis Error",
                        value="Could not analyze signal quality",
                        inline=False
                    )
                    embed.color = 0xff6600
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error analyzing signal quality: {e}")

@bot.command(name='datavalidation')
async def data_validation_command(ctx, days: int = 30):
    """Comprehensive data validation for ML commands - !datavalidation [days]"""
    try:
        # Validate days parameter
        if not 7 <= days <= 90:
            await ctx.send("❌ Days must be between 7 and 90")
            return
        
        # Send typing indicator
        async with ctx.typing():
            # Import validation functions
            from comprehensive_data_validator import validate_data
            
            # Run comprehensive validation
            validation_results = await validate_data(days)
            
            if 'error' in validation_results:
                await ctx.send(f"❌ Data validation failed: {validation_results['error']}")
                return
            
            # Create embed
            embed = discord.Embed(
                title="🔍 Comprehensive Data Validation Report",
                description=f"Data quality assessment for ML commands ({days} days analysis)",
                color=0x00ff88 if validation_results.get('overall_score', 0) >= 0.7 else 0xff6b00 if validation_results.get('overall_score', 0) >= 0.5 else 0xff0000,
                timestamp=datetime.now(EST)
            )
            
            # Overall Score
            overall_score = validation_results.get('overall_score', 0)
            score_emoji = "🟢" if overall_score >= 0.8 else "🟡" if overall_score >= 0.6 else "🔴"
            embed.add_field(
                name="📊 Overall Data Quality Score",
                value=f"{score_emoji} **{overall_score:.1%}** ({overall_score:.3f}/1.000)",
                inline=False
            )
            
            # Schema Validation
            schema = validation_results.get('schema_validation', {})
            schema_score = schema.get('schema_score', 0)
            schema_emoji = "✅" if schema_score >= 0.9 else "⚠️" if schema_score >= 0.7 else "❌"
            embed.add_field(
                name="🗄️ Database Schema",
                value=f"{schema_emoji} Score: {schema_score:.1%}\nTables: {len([t for t in schema.get('tables_exist', {}).values() if t])}/4 exist",
                inline=True
            )
            
            # Data Quality
            quality = validation_results.get('data_quality', {})
            quality_score = quality.get('quality_score', 0)
            quality_emoji = "✅" if quality_score >= 0.8 else "⚠️" if quality_score >= 0.6 else "❌"
            
            # Get specific quality metrics
            completeness = quality.get('completeness', {})
            freshness = quality.get('freshness', {})
            
            embed.add_field(
                name="🧹 Data Quality",
                value=f"{quality_emoji} Score: {quality_score:.1%}\nCompleteness: {completeness.get('status', 'Unknown')}\nFreshness: {freshness.get('status', 'Unknown')}",
                inline=True
            )
            
            # ML Readiness
            ml_readiness = validation_results.get('ml_readiness', {})
            ml_score = ml_readiness.get('ml_score', 0)
            ml_emoji = "🤖" if ml_score >= 0.8 else "⚙️" if ml_score >= 0.6 else "🔧"
            
            sample_size = ml_readiness.get('sample_size', {})
            
            embed.add_field(
                name="🤖 ML Readiness",
                value=f"{ml_emoji} Score: {ml_score:.1%}\nSamples: {sample_size.get('total_samples', 0):,}\nStatus: {sample_size.get('status', 'Unknown')}",
                inline=True
            )
            
            # Key Statistics
            if completeness.get('total_records', 0) > 0:
                embed.add_field(
                    name="📈 Key Statistics",
                    value=f"""
**Total Records:** {completeness.get('total_records', 0):,}
**Unique Tickers:** {sample_size.get('unique_tickers', 0)}
**Unique Timeframes:** {sample_size.get('unique_timeframes', 0)}
**Data Completeness:** {completeness.get('score', 0):.1%}
                    """,
                    inline=True
                )
            
            # Freshness Details
            if freshness.get('latest_performance_date'):
                latest_date = freshness.get('latest_performance_date', '')
                days_since = freshness.get('days_since_update', 0)
                embed.add_field(
                    name="🕐 Data Freshness",
                    value=f"""
**Latest Update:** {latest_date[:10]}
**Days Since Update:** {days_since}
**Recent Records (7d):** {freshness.get('recent_records_7d', 0):,}
                    """,
                    inline=True
                )
            
            # Recommendations
            recommendations = validation_results.get('recommendations', [])
            if recommendations:
                rec_text = "\n".join(f"• {rec}" for rec in recommendations[:3])  # Show top 3
                if len(recommendations) > 3:
                    rec_text += f"\n... and {len(recommendations) - 3} more"
                
                embed.add_field(
                    name="💡 Recommendations",
                    value=rec_text,
                    inline=False
                )
            
            # Status Indicators
            status_indicators = []
            if overall_score >= 0.8:
                status_indicators.append("🟢 Ready for ML Analysis")
            elif overall_score >= 0.6:
                status_indicators.append("🟡 Needs Minor Improvements")
            else:
                status_indicators.append("🔴 Requires Data Fixes")
            
            if schema_score >= 0.9:
                status_indicators.append("✅ Schema Valid")
            
            if quality_score >= 0.8:
                status_indicators.append("🧹 Quality Excellent")
            
            embed.add_field(
                name="🎯 Status",
                value=" | ".join(status_indicators),
                inline=False
            )
            
            embed.set_footer(text="🔬 Enhanced with comprehensive validation & ML readiness assessment | Use !correlations, !mlpredict, !successrates for analysis")
            
            await ctx.send(embed=embed)
    
    except Exception as e:
        await ctx.send(f"❌ Error running data validation: {e}")

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
