#!/usr/bin/env python3
"""
Debug Performance Automation
Test why the automated performance tracking isn't working in production
"""

import asyncio
import os
import requests
import json
from datetime import datetime
from signal_notifier import SignalNotifier
from database import db_manager, record_signal_performance
import asyncpg

async def debug_performance_automation():
    """Debug the automated performance tracking system"""
    
    print("🐛 Debug Performance Automation")
    print("=" * 50)
    
    # 1. Test database connection
    print("\n1️⃣ Testing database connection...")
    try:
        DATABASE_URL = os.getenv('DATABASE_URL')
        if not DATABASE_URL:
            print("❌ DATABASE_URL environment variable not set")
            return
            
        # Connect directly to test
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Database connection successful")
        
        # Get some recent signals that should have performance data
        recent_signals = await conn.fetch("""
            SELECT ticker, timeframe, signal_type, signal_date, notified_at
            FROM signal_notifications 
            WHERE notified_at >= NOW() - INTERVAL '24 hours'
            ORDER BY notified_at DESC 
            LIMIT 5
        """)
        
        print(f"📊 Found {len(recent_signals)} recent signals (last 24h)")
        for signal in recent_signals:
            print(f"  • {signal['ticker']} {signal['timeframe']} {signal['signal_type']} at {signal['signal_date']}")
        
        await conn.close()
                
    except Exception as e:
        print(f"❌ Database error: {e}")
        return
    
    # 2. Test API call and data extraction
    print("\n2️⃣ Testing API call and data extraction...")
    try:
        notifier = SignalNotifier(None)  # No bot needed for testing
        
        # Test with a ticker that should have recent signals
        test_ticker = "BTC-USD"  # From the recent signals
        test_timeframe = "1h"
        
        print(f"🔍 Testing API call for {test_ticker} ({test_timeframe})")
        
        # Make API call
        timeline = notifier.fetch_signal_timeline(test_ticker, test_timeframe)
        
        if timeline:
            print(f"✅ API call successful, got {len(timeline)} signals")
        else:
            print("❌ API call failed or returned no data")
            return
            
    except Exception as e:
        print(f"❌ API call error: {e}")
        return
    
    # 3. Test direct API data extraction
    print("\n3️⃣ Testing direct API data extraction...")
    try:
        # Make a direct API call to get raw response
        api_url = "https://wavetrend-216f065b8ba6.herokuapp.com//api/analyzer-b"
        params = {
            'ticker': test_ticker,
            'interval': test_timeframe,
            'period': '1mo'
        }
        
        print(f"📡 Making direct API call: {api_url}")
        print(f"⚙️ Parameters: {params}")
        
        response = requests.get(api_url, params=params, timeout=30)
        
        if response.status_code == 200:
            api_data = response.json()
            print(f"✅ Got API response: {response.status_code}")
            print(f"📦 Response size: {len(response.content)} bytes")
            print(f"🗝️ Main keys: {list(api_data.keys())[:10]}")  # First 10 keys
            
            # Test pricing data extraction
            pricing_data = notifier.extract_pricing_data_from_api(api_data)
            
            if pricing_data:
                print(f"✅ Extracted {len(pricing_data)} price points")
                
                # Show sample price data
                if len(pricing_data) > 0:
                    sample = pricing_data[0]
                    print(f"📄 Sample price data: {sample}")
                    
                    # Test finding a recent price
                    recent_time = datetime.now()
                    found_price = notifier.find_closest_price(recent_time, pricing_data)
                    
                    if found_price:
                        print(f"✅ Found recent price: ${found_price:.2f}")
                    else:
                        print("⚠️ Could not find recent price")
                        
            else:
                print("❌ Could not extract pricing data from API response")
                
                # Debug: Show what we got
                print("🔍 API Response structure:")
                for key, value in api_data.items():
                    if isinstance(value, list):
                        print(f"  {key}: list[{len(value)}] - {type(value[0]) if value else 'empty'}")
                    elif isinstance(value, dict):
                        print(f"  {key}: dict with keys {list(value.keys())[:5]}")
                    else:
                        print(f"  {key}: {type(value)}")
        else:
            print(f"❌ API call failed: {response.status_code}")
            print(f"Response: {response.text[:200]}")
            
    except Exception as e:
        print(f"❌ Direct API test error: {e}")
    
    # 4. Test the auto_update function directly
    print("\n4️⃣ Testing auto_update_signal_performance function...")
    try:
        if 'api_data' in locals():
            print(f"🔄 Running auto_update_signal_performance for {test_ticker}")
            
            # This should be the function that's failing in production
            await notifier.auto_update_signal_performance(test_ticker, test_timeframe, api_data)
            
            print("✅ auto_update_signal_performance completed")
            
            # Check if any new performance data was created
            conn = await asyncpg.connect(DATABASE_URL)
            new_performance = await conn.fetch("""
                SELECT COUNT(*) as count FROM signal_performance 
                WHERE ticker = $1 AND timeframe = $2
                AND performance_date >= NOW() - INTERVAL '5 minutes'
            """, test_ticker, test_timeframe)
            
            if new_performance[0]['count'] > 0:
                print(f"✅ Created {new_performance[0]['count']} new performance records")
            else:
                print("⚠️ No new performance records created")
                
                # Check what signals exist for this ticker
                existing_signals = await conn.fetch("""
                    SELECT signal_type, signal_date 
                    FROM signal_notifications 
                    WHERE ticker = $1 AND timeframe = $2
                    AND notified_at >= NOW() - INTERVAL '7 days'
                """, test_ticker, test_timeframe)
                
                print(f"📊 Found {len(existing_signals)} recent signals for {test_ticker} {test_timeframe}")
                for signal in existing_signals[:3]:
                    print(f"  • {signal['signal_type']} on {signal['signal_date']}")
            
            await conn.close()
                    
    except Exception as e:
        print(f"❌ auto_update test error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Debug complete!")

if __name__ == "__main__":
    asyncio.run(debug_performance_automation()) 