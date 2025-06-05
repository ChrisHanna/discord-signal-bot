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
            LIMIT 100
        ''')
        
        print(f"📊 Found {len(signals)} signals needing 3h/6h backfill")
        
        updated_count = 0
        
        # Use trust_env=False to avoid DNS issues on Windows
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
            for signal in signals:
                try:
                    # Calculate target times
                    signal_time = signal['signal_date']
                    time_3h = signal_time + timedelta(hours=3)
                    time_6h = signal_time + timedelta(hours=6)
                    
                    # Get pricing data from API
                    ticker = signal['ticker']
                    api_url = f"https://wavetrend-216f065b8ba6.herokuapp.com/{ticker}/1h"
                    
                    async with session.get(api_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            # Extract pricing data
                            if 'pricing_data' in data:
                                pricing_data = data['pricing_data']
                                
                                # Find closest prices
                                price_3h = find_closest_price(time_3h, pricing_data)
                                price_6h = find_closest_price(time_6h, pricing_data)
                                
                                if price_3h or price_6h:
                                    # Update database
                                    await conn.execute('''
                                        UPDATE signal_performance 
                                        SET price_after_3h = COALESCE($1, price_after_3h),
                                            price_after_6h = COALESCE($2, price_after_6h)
                                        WHERE id = $3
                                    ''', price_3h, price_6h, signal['id'])
                                    
                                    updated_count += 1
                                    print(f"✅ Updated {ticker} signal {signal['id']} - 3h: {price_3h}, 6h: {price_6h}")
                                
                except Exception as e:
                    print(f"❌ Error processing signal {signal['id']}: {e}")
                    continue
        
        await conn.close()
        print(f"\n🎯 Backfill complete! Updated {updated_count} signals with 3h/6h data")
        
    except Exception as e:
        print(f"❌ Error during backfill: {e}")
        import traceback
        traceback.print_exc()

def find_closest_price(target_time: datetime, pricing_data: list) -> float:
    """Find the closest price to target time from pricing data"""
    try:
        closest_price = None
        min_diff = float('inf')
        
        for price_point in pricing_data:
            if 'timestamp' in price_point and 'close' in price_point:
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
                    closest_price = float(price_point['close'])
        
        # Only return if within 2 hours tolerance
        if min_diff < 7200:  # 2 hours in seconds
            return closest_price
        
        return None
        
    except Exception as e:
        print(f"Error finding closest price: {e}")
        return None

if __name__ == "__main__":
    asyncio.run(backfill_3h_6h_performance()) 