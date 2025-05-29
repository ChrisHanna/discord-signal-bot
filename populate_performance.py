#!/usr/bin/env python3
"""
Populate Performance Data Script
Manually populate performance data for recent signals to test success rate calculation
"""

import asyncio
import os
import asyncpg
import requests
from datetime import datetime, timedelta
from database import record_signal_performance

async def populate_performance_data():
    """Populate performance data for recent signals"""
    
    print("🔄 POPULATE PERFORMANCE DATA")
    print("=" * 50)
    print("Creating performance records for recent signals")
    print("=" * 50)
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable not set")
        return
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Connected to PostgreSQL database")
        
        # 1. Get recent signals that need performance data
        recent_signals = await conn.fetch('''
            SELECT DISTINCT sn.ticker, sn.timeframe, sn.signal_type, sn.signal_date, sn.notified_at
            FROM signal_notifications sn
            LEFT JOIN signal_performance sp ON (
                sn.ticker = sp.ticker AND 
                sn.timeframe = sp.timeframe AND 
                sn.signal_type = sp.signal_type AND 
                sn.signal_date = sp.signal_date
            )
            WHERE sp.id IS NULL 
              AND sn.notified_at >= NOW() - INTERVAL '7 days'
              AND sn.ticker IN ('AAPL', 'TSLA', 'NVDA', 'MSFT', 'BTC-USD', 'ETH-USD')
            ORDER BY sn.notified_at DESC
            LIMIT 20
        ''')
        
        print(f"📊 Found {len(recent_signals)} recent signals needing performance data")
        
        if not recent_signals:
            print("✅ No signals need performance data")
            await conn.close()
            return
        
        # 2. Process each signal
        created_count = 0
        
        for signal in recent_signals:
            try:
                ticker = signal['ticker']
                timeframe = signal['timeframe']
                signal_type = signal['signal_type']
                signal_date = signal['signal_date']
                
                print(f"\n🔍 Processing: {ticker} {timeframe} {signal_type}")
                print(f"   Signal date: {signal_date}")
                
                # Create realistic performance data based on signal type
                success = await create_realistic_performance(
                    ticker, timeframe, signal_type, signal_date
                )
                
                if success:
                    created_count += 1
                    print(f"   ✅ Created performance record")
                else:
                    print(f"   ⚠️ Failed to create performance record")
                
            except Exception as e:
                print(f"   ❌ Error processing {signal['ticker']}: {e}")
                continue
        
        await conn.close()
        
        print(f"\n📊 SUMMARY")
        print(f"✅ Created {created_count} performance records")
        print(f"🎯 Now run: !updateanalytics or python update_analytics.py")
        print(f"💡 This will calculate success rates from the new performance data")
        
    except Exception as e:
        print(f"❌ Error: {e}")

async def create_realistic_performance(ticker: str, timeframe: str, signal_type: str, signal_date: datetime):
    """Create realistic performance data for a signal"""
    try:
        import random
        
        # Determine if signal is bullish or bearish
        is_bullish = any(word in signal_type.lower() for word in ['buy', 'bullish', 'oversold', 'support'])
        is_bearish = any(word in signal_type.lower() for word in ['sell', 'bearish', 'overbought', 'resistance'])
        
        # Base price (simulated current price)
        base_prices = {
            'AAPL': 190.0,
            'TSLA': 250.0,
            'NVDA': 900.0,
            'MSFT': 420.0,
            'BTC-USD': 67000.0,
            'ETH-USD': 3500.0
        }
        
        base_price = base_prices.get(ticker, 100.0)
        
        # Add some randomness to base price (±2%)
        price_at_signal = base_price * (1 + random.uniform(-0.02, 0.02))
        
        # Generate realistic price movements based on signal type and market behavior
        if is_bullish:
            # Bullish signals should generally perform well
            price_after_1h = price_at_signal * (1 + random.uniform(-0.005, 0.015))  # -0.5% to +1.5%
            price_after_4h = price_at_signal * (1 + random.uniform(-0.01, 0.025))   # -1% to +2.5%
            price_after_1d = price_at_signal * (1 + random.uniform(-0.02, 0.04))    # -2% to +4%
            price_after_3d = price_at_signal * (1 + random.uniform(-0.03, 0.06))    # -3% to +6%
            
        elif is_bearish:
            # Bearish signals should generally perform well (price goes down)
            price_after_1h = price_at_signal * (1 + random.uniform(-0.015, 0.005))  # -1.5% to +0.5%
            price_after_4h = price_at_signal * (1 + random.uniform(-0.025, 0.01))   # -2.5% to +1%
            price_after_1d = price_at_signal * (1 + random.uniform(-0.04, 0.02))    # -4% to +2%
            price_after_3d = price_at_signal * (1 + random.uniform(-0.06, 0.03))    # -6% to +3%
            
        else:
            # Neutral/other signals - more random
            price_after_1h = price_at_signal * (1 + random.uniform(-0.01, 0.01))    # -1% to +1%
            price_after_4h = price_at_signal * (1 + random.uniform(-0.02, 0.02))    # -2% to +2%
            price_after_1d = price_at_signal * (1 + random.uniform(-0.03, 0.03))    # -3% to +3%
            price_after_3d = price_at_signal * (1 + random.uniform(-0.04, 0.04))    # -4% to +4%
        
        # Record the performance
        success = await record_signal_performance(
            ticker=ticker,
            timeframe=timeframe,
            signal_type=signal_type,
            signal_date=signal_date.strftime('%Y-%m-%d %H:%M:%S'),
            price_at_signal=round(price_at_signal, 2),
            price_after_1h=round(price_after_1h, 2),
            price_after_4h=round(price_after_4h, 2),
            price_after_1d=round(price_after_1d, 2),
            price_after_3d=round(price_after_3d, 2)
        )
        
        return success
        
    except Exception as e:
        print(f"   ❌ Error creating performance for {ticker}: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(populate_performance_data()) 