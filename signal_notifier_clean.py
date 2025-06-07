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
                max_hours_ago = 4  # Only last 4 hours for hourly data
                print(f"🕐 Filtering for signals within last {max_hours_ago} hours")
            else:
                max_days_ago = 7  # Last 7 days for daily data
                print(f"📅 Filtering for signals within last {max_days_ago} days")
            
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
                        is_recent = time_diff.days <= max_days_ago
                    
                    if is_recent:
                        signal['age_hours'] = time_diff.total_seconds() / 3600
                        recent_signals.append(signal)
                        
                        # Enhanced debug info
                        age_str = f"{time_diff.total_seconds()/3600:.1f}h" if timeframe == '1h' else f"{time_diff.days}d"
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
                    ml_should_send = False
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
        
