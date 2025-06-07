#!/usr/bin/env python3
import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import aiohttp
import sys

load_dotenv()

# Fix Windows event loop issue
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def backfill_3h_6h_performance():
    """Backfill 3h and 6h performance data for existing signals"""
    try:
        DATABASE_URL = os.getenv('DATABASE_URL')
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Get all signals that need 3h and 6h data
        signals = await conn.fetch('''
            SELECT id, ticker, signal_date, price_at_signal
            FROM signal_performance 
            WHERE price_at_signal IS NOT NULL 
              AND (price_after_3h IS NULL OR price_after_6h IS NULL)
            ORDER BY signal_date DESC
        ''')
        
        print(f"📊 Found {len(signals)} signals needing 3h/6h backfill")
        
        if len(signals) == 0:
            print("✅ All signals already have 3h/6h data!")
            await conn.close()
            return
        
        updated_count = 0
        error_count = 0
        
        # Use trust_env=False to avoid DNS issues on Windows
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
            for i, signal in enumerate(signals):
                try:
                    if i % 50 == 0:
                        print(f"📈 Processing signal {i+1}/{len(signals)}...")
                    
                    # Calculate target times
                    signal_time = signal['signal_date']
                    time_3h = signal_time + timedelta(hours=3)
                    time_6h = signal_time + timedelta(hours=6)
                    
                    # Get pricing data from API
                    ticker = signal['ticker']
                    price_3h = await fetch_price_data(session, ticker, time_3h)
                    price_6h = await fetch_price_data(session, ticker, time_6h)
                    
                    if price_3h or price_6h:
                        # Update database
                        await conn.execute('''
                            UPDATE signal_performance 
                            SET price_after_3h = COALESCE($1, price_after_3h),
                                price_after_6h = COALESCE($2, price_after_6h)
                            WHERE id = $3
                        ''', price_3h, price_6h, signal['id'])
                        
                        updated_count += 1
                        if updated_count % 25 == 0:
                            print(f"✅ Updated {updated_count} signals so far...")
                    else:
                        print(f"⚠️ No price data found for {ticker} signal {signal['id']}")
                except Exception as e:
                    print(f"❌ Error processing signal {signal['id']} ({ticker}): {e}")
                    error_count += 1
                    continue
        
        await conn.close()
        print(f"\n🎯 Backfill complete! Updated {updated_count} signals with 3h/6h data")
        print(f"📊 Errors encountered: {error_count}")
        print(f"📈 Success rate: {(updated_count/(len(signals)-error_count)*100):.1f}%" if (len(signals)-error_count) > 0 else "N/A")
        
    except Exception as e:
        print(f"❌ Error during backfill: {e}")
        import traceback
        traceback.print_exc()

async def fetch_price_data(session, ticker, target_timestamp):
    """Fetch price data from API for a specific time"""
    try:
        # Use the correct API endpoint format from working scripts
        api_url = "https://wavetrend-216f065b8ba6.herokuapp.com/api/analyzer-b"
        params = {
            'ticker': ticker,
            'interval': '1h',  # Use interval instead of timeframe
            'period': '1mo'    # Get a month of data to find our target time
        }
        
        async with session.get(api_url, params=params, timeout=15) as response:
            if response.status == 200:
                data = await response.json()
                
                # Extract pricing data and find closest price to target time
                pricing_data = extract_pricing_data_from_response(data)
                if pricing_data:
                    closest_price = find_closest_price(target_timestamp, pricing_data)
                    return closest_price
                else:
                    print(f"⚠️ No pricing data found for {ticker}")
                    return None
            else:
                print(f"❌ API error for {ticker}: {response.status}")
                return None
    except Exception as e:
        print(f"❌ Exception for {ticker}: {e}")
        return None

def extract_pricing_data_from_response(api_response):
    """Extract pricing data from API response"""
    try:
        if 'historical_data' in api_response:
            return api_response['historical_data']
        elif 'data' in api_response:
            return api_response['data']
        elif 'prices' in api_response:
            return api_response['prices']
        else:
            return None
    except Exception as e:
        print(f"Error extracting pricing data: {e}")
        return None

def find_closest_price(target_time: datetime, pricing_data: list) -> float:
    """Find the closest price to target time from pricing data"""
    try:
        closest_price = None
        min_diff = float('inf')
        
        for price_point in pricing_data:
            if 'timestamp' in price_point and ('close' in price_point or 'price' in price_point):
                # Parse timestamp
                timestamp_str = price_point['timestamp']
                if 'T' in timestamp_str:
                    price_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                else:
                    price_time = datetime.fromisoformat(timestamp_str)
                
                # Calculate time difference
                diff = abs((price_time - target_time).total_seconds())
                
                if diff < min_diff:
                    min_diff = diff
                    price_value = price_point.get('close', price_point.get('price', 0))
                    closest_price = float(price_value)
        
        # Only return if within 2 hours tolerance
        if min_diff < 7200:  # 2 hours in seconds
            return closest_price
        
        return None
        
    except Exception as e:
        print(f"Error finding closest price: {e}")
        return None

if __name__ == "__main__":
    asyncio.run(backfill_3h_6h_performance()) 