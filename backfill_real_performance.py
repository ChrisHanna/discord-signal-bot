#!/usr/bin/env python3
"""
Backfill Real Performance Data Script
Uses REAL historical price data from API to calculate actual signal performance
"""

import asyncio
import os
import asyncpg
import requests
import json
from datetime import datetime, timedelta
from database import record_signal_performance

# API Configuration
API_BASE_URL = os.getenv('API_BASE_URL', 'https://wavetrend-216f065b8ba6.herokuapp.com/')

async def backfill_real_performance():
    """Backfill performance data using real historical price data"""
    
    print("🔄 BACKFILL REAL PERFORMANCE DATA")
    print("=" * 60)
    print("Using REAL historical price data from API")
    print("=" * 60)
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable not set")
        return
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Connected to PostgreSQL database")
        
        # 1. Get all signals from the last 7 days that need performance data
        cutoff_date = datetime.now() - timedelta(days=7)  # Changed to last 7 days
        
        historical_signals = await conn.fetch('''
            SELECT DISTINCT sn.ticker, sn.timeframe, sn.signal_type, sn.signal_date, sn.notified_at
            FROM signal_notifications sn
            LEFT JOIN signal_performance sp ON (
                sn.ticker = sp.ticker AND 
                sn.timeframe = sp.timeframe AND 
                sn.signal_type = sp.signal_type AND 
                sn.signal_date = sp.signal_date
            )
            WHERE sp.id IS NULL 
              AND sn.notified_at >= $1
            ORDER BY sn.notified_at DESC
        ''', cutoff_date)
        
        print(f"📊 Found {len(historical_signals)} signals from last 7 days needing performance data")
        print(f"📅 Processing signals newer than: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if not historical_signals:
            print("✅ No historical signals need performance data")
            await conn.close()
            return
        
        # 2. Group signals by ticker and timeframe for efficient API calls
        grouped_signals = {}
        for signal in historical_signals:
            key = (signal['ticker'], signal['timeframe'])
            if key not in grouped_signals:
                grouped_signals[key] = []
            grouped_signals[key].append(signal)
        
        print(f"🎯 Grouped into {len(grouped_signals)} ticker-timeframe combinations")
        
        total_processed = 0
        total_created = 0
        api_calls_made = 0
        
        # 3. Process each ticker-timeframe group
        for (ticker, timeframe), signals in grouped_signals.items():
            try:
                print(f"\n🔍 Processing {ticker} ({timeframe}): {len(signals)} signals")
                
                # Make API call to get historical price data
                pricing_data = await fetch_real_pricing_data(ticker, timeframe)
                api_calls_made += 1
                
                if not pricing_data:
                    print(f"   ⚠️ No pricing data available for {ticker} ({timeframe})")
                    continue
                
                print(f"   ✅ Retrieved {len(pricing_data)} price data points")
                
                # Process each signal for this ticker/timeframe
                created_count = 0
                for signal in signals:
                    try:
                        signal_date = signal['signal_date']
                        signal_type = signal['signal_type']
                        
                        # Calculate real performance using actual price data
                        performance = calculate_real_performance(signal_date, pricing_data, timeframe)
                        
                        if performance and performance.get('price_at_signal'):
                            # Record real performance data
                            success = await record_signal_performance(
                                ticker=ticker,
                                timeframe=timeframe,
                                signal_type=signal_type,
                                signal_date=signal_date.strftime('%Y-%m-%d %H:%M:%S'),
                                price_at_signal=performance['price_at_signal'],
                                price_after_1h=performance.get('price_after_1h'),
                                price_after_4h=performance.get('price_after_4h'),
                                price_after_1d=performance.get('price_after_1d'),
                                price_after_3d=performance.get('price_after_3d')
                            )
                            
                            if success:
                                created_count += 1
                                total_created += 1
                                print(f"   ✅ {signal_type} from {signal_date.strftime('%m-%d %H:%M')}: Real performance recorded")
                            else:
                                print(f"   ⚠️ Failed to record performance for {signal_type}")
                        else:
                            print(f"   ⚠️ Could not calculate performance for {signal_type} from {signal_date.strftime('%m-%d %H:%M')}")
                        
                        total_processed += 1
                        
                    except Exception as e:
                        print(f"   ❌ Error processing signal {signal['signal_type']}: {e}")
                        continue
                
                print(f"   📊 Created {created_count}/{len(signals)} performance records for {ticker}")
                
                # Rate limiting between API calls
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"   ❌ Error processing {ticker} ({timeframe}): {e}")
                continue
        
        await conn.close()
        
        # 4. Summary
        print(f"\n📊 BACKFILL SUMMARY")
        print("-" * 40)
        print(f"✅ Processed {total_processed} historical signals")
        print(f"✅ Created {total_created} real performance records") 
        print(f"📡 Made {api_calls_made} API calls for real price data")
        print(f"📈 Success rate: {(total_created/max(total_processed,1)*100):.1f}%")
        print(f"\n🎯 Next steps:")
        print(f"   1. Run: python update_analytics.py")
        print(f"   2. Use Discord: !successrates or !performance")
        print(f"   3. All analytics will now use REAL historical performance data! 🎉")
        
    except Exception as e:
        print(f"❌ Error during backfill: {e}")
        import traceback
        traceback.print_exc()

async def fetch_real_pricing_data(ticker: str, timeframe: str):
    """Fetch real historical pricing data from API"""
    try:
        # Determine appropriate period based on timeframe for maximum historical coverage
        if timeframe == '1d':
            period = '2y'  # 2 years for daily data
        elif timeframe == '1h':
            period = '3mo'  # 3 months for hourly data (API limit)
        elif timeframe in ['15m', '30m', '5m']:
            period = '1mo'  # 1 month for intraday
        elif timeframe in ['4h', '2h']:
            period = '6mo'  # 6 months for medium timeframes
        else:
            period = '1y'  # Default fallback
        
        params = {
            'ticker': ticker,
            'interval': timeframe,
            'period': period
        }
        
        print(f"   📡 API call: {ticker} {timeframe} period={period}")
        
        response = requests.get(f"{API_BASE_URL}/api/analyzer-b", params=params, timeout=30)
        
        if response.status_code == 200:
            api_data = response.json()
            
            # Extract pricing data using the same method as the bot
            pricing_data = extract_pricing_data_from_api(api_data)
            
            return pricing_data
        else:
            print(f"   ❌ API returned status {response.status_code}")
            return None
            
    except Exception as e:
        print(f"   ❌ Error fetching pricing data: {e}")
        return None

def extract_pricing_data_from_api(api_data: dict):
    """Extract OHLCV pricing data from API response (same as bot logic)"""
    try:
        # 🎯 PRIMARY: OHLC data (confirmed structure from API testing)
        if 'ohlc' in api_data and isinstance(api_data['ohlc'], list):
            ohlc_data = api_data['ohlc']
            if len(ohlc_data) > 0 and isinstance(ohlc_data[0], dict):
                return ohlc_data
        
        # 🎯 SECONDARY: Separate arrays
        dates = api_data.get('dates', [])
        close_prices = api_data.get('close', [])
        open_prices = api_data.get('open', [])
        high_prices = api_data.get('high', [])
        low_prices = api_data.get('low', [])
        volumes = api_data.get('volume', [])
        
        if dates and close_prices and len(dates) == len(close_prices):
            # Reconstruct OHLC format from separate arrays
            combined_data = []
            for i in range(len(dates)):
                data_point = {
                    'date': dates[i],
                    'timestamp': dates[i],
                    't': dates[i],
                    'close': close_prices[i],
                    'c': close_prices[i],
                    'price': close_prices[i]
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
        
        return None
        
    except Exception as e:
        print(f"   ⚠️ Error extracting pricing data: {e}")
        return None

def calculate_real_performance(signal_datetime: datetime, pricing_data: list, timeframe: str):
    """Calculate signal performance using real pricing data"""
    try:
        if not pricing_data:
            return None
        
        # Find the price closest to signal time
        signal_price = find_closest_price(signal_datetime, pricing_data)
        if not signal_price:
            return None
        
        # Calculate target times for performance measurement
        target_1h = signal_datetime + timedelta(hours=1)
        target_4h = signal_datetime + timedelta(hours=4)
        target_1d = signal_datetime + timedelta(days=1)
        target_3d = signal_datetime + timedelta(days=3)
        
        # Find real prices at target times
        performance = {
            'price_at_signal': signal_price,
            'price_after_1h': find_closest_price(target_1h, pricing_data),
            'price_after_4h': find_closest_price(target_4h, pricing_data),
            'price_after_1d': find_closest_price(target_1d, pricing_data),
            'price_after_3d': find_closest_price(target_3d, pricing_data)
        }
        
        return performance
        
    except Exception as e:
        print(f"   ⚠️ Error calculating performance: {e}")
        return None

def find_closest_price(target_datetime: datetime, pricing_data: list):
    """Find the real price closest to target datetime"""
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
            
            # 🎯 PRIMARY: OHLC format from API
            if 't' in data_point and 'c' in data_point:
                timestamp = data_point['t']
                price = data_point['c']
            elif 'date' in data_point and 'close' in data_point:
                timestamp = data_point['date']
                price = data_point['close']
            elif 'timestamp' in data_point and 'price' in data_point:
                timestamp = data_point['timestamp']
                price = data_point['price']
            
            if timestamp and price is not None:
                try:
                    # Parse timestamp from API format
                    if isinstance(timestamp, str):
                        if 'T' in timestamp:
                            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        elif ' ' in timestamp:
                            dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                        else:
                            dt = datetime.strptime(timestamp, '%Y-%m-%d')
                            dt = dt.replace(hour=16, minute=0, second=0)  # Market close
                    elif isinstance(timestamp, (int, float)):
                        dt = datetime.fromtimestamp(timestamp)
                    else:
                        continue
                    
                    # Calculate time difference
                    diff = abs((target_datetime - dt).total_seconds())
                    
                    if diff < closest_diff:
                        closest_diff = diff
                        closest_price = float(price)
                        
                except (ValueError, TypeError):
                    continue
        
        # Enhanced tolerance for real data
        max_tolerance = 86400  # 24 hours
        
        if closest_diff < max_tolerance and closest_price is not None:
            return closest_price
        
        return None
        
    except Exception as e:
        print(f"   ⚠️ Error finding closest price: {e}")
        return None

if __name__ == "__main__":
    print("🚀 Starting real data backfill...")
    asyncio.run(backfill_real_performance()) 