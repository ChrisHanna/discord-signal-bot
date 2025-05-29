#!/usr/bin/env python3
"""
Update Analytics Script
Calculate success rates from existing performance data and update analytics table
"""

import asyncio
import os
import asyncpg
from datetime import datetime, timedelta

async def update_analytics():
    """Update analytics with success rates from existing performance data"""
    
    print("📊 Analytics Update Script")
    print("=" * 50)
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable not set")
        return
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Connected to PostgreSQL database")
        
        # 1. Check current performance data
        performance_count = await conn.fetchval("SELECT COUNT(*) FROM signal_performance")
        print(f"📊 Total performance records: {performance_count}")
        
        if performance_count == 0:
            print("⚠️ No performance data available to calculate success rates")
            await conn.close()
            return
        
        # 2. Show sample performance data
        sample_perf = await conn.fetch("""
            SELECT ticker, signal_type, success_1h, success_1d, price_at_signal, price_after_1d
            FROM signal_performance 
            ORDER BY performance_date DESC 
            LIMIT 3
        """)
        
        print("\n📄 Sample performance data:")
        for i, record in enumerate(sample_perf, 1):
            price_change = ""
            if record['price_at_signal'] and record['price_after_1d']:
                pct_change = ((record['price_after_1d'] - record['price_at_signal']) / record['price_at_signal']) * 100
                price_change = f" ({pct_change:+.1f}%)"
                
            print(f"  {i}. {record['ticker']} {record['signal_type']}: "
                  f"1h={'✅' if record['success_1h'] else '❌'}, "
                  f"1d={'✅' if record['success_1d'] else '❌'}{price_change}")
        
        # 3. Calculate overall success rates
        success_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_signals,
                COUNT(*) FILTER (WHERE success_1h = true) as success_1h_count,
                COUNT(*) FILTER (WHERE success_1d = true) as success_1d_count,
                ROUND(AVG(CASE WHEN success_1h = true THEN 100.0 ELSE 0.0 END), 2) as success_rate_1h,
                ROUND(AVG(CASE WHEN success_1d = true THEN 100.0 ELSE 0.0 END), 2) as success_rate_1d
            FROM signal_performance
            WHERE success_1h IS NOT NULL OR success_1d IS NOT NULL
        """)
        
        if success_stats:
            print(f"\n🎯 Overall Success Rates:")
            print(f"  Total analyzed signals: {success_stats['total_signals']}")
            print(f"  1-hour success rate: {success_stats['success_rate_1h']}% ({success_stats['success_1h_count']}/{success_stats['total_signals']})")
            print(f"  1-day success rate: {success_stats['success_rate_1d']}% ({success_stats['success_1d_count']}/{success_stats['total_signals']})")
        
        # 4. Update signal_analytics table with success rates
        print(f"\n🔄 Updating signal_analytics table...")
        
        # Get all analytics records that need success rate updates
        analytics_needing_update = await conn.fetch("""
            SELECT DISTINCT date, ticker, timeframe, system 
            FROM signal_analytics 
            WHERE success_rate_1h IS NULL OR success_rate_1d IS NULL
            ORDER BY date DESC
            LIMIT 50
        """)
        
        print(f"📋 Found {len(analytics_needing_update)} analytics records to update")
        
        updated_count = 0
        for record in analytics_needing_update:
            try:
                # Calculate success rates for this specific combination
                success_rates = await conn.fetchrow('''
                    SELECT 
                        ROUND(AVG(CASE WHEN success_1h = true THEN 100.0 ELSE 0.0 END), 2) as success_rate_1h,
                        ROUND(AVG(CASE WHEN success_1d = true THEN 100.0 ELSE 0.0 END), 2) as success_rate_1d,
                        COUNT(*) as performance_count
                    FROM signal_performance sp
                    JOIN signal_notifications sn ON (
                        sp.ticker = sn.ticker AND 
                        sp.timeframe = sn.timeframe AND 
                        sp.signal_type = sn.signal_type AND 
                        sp.signal_date = sn.signal_date
                    )
                    WHERE DATE(sn.notified_at) = $1 
                      AND sp.ticker = $2 
                      AND sp.timeframe = $3
                      AND sn.system = $4
                ''', record['date'], record['ticker'], record['timeframe'], record['system'])
                
                if success_rates and success_rates['performance_count'] > 0:
                    # Update the analytics record
                    await conn.execute('''
                        UPDATE signal_analytics 
                        SET success_rate_1h = $5, success_rate_1d = $6
                        WHERE date = $1 AND ticker = $2 AND timeframe = $3 AND system = $4
                    ''', record['date'], record['ticker'], record['timeframe'], record['system'],
                         success_rates['success_rate_1h'], success_rates['success_rate_1d'])
                    
                    updated_count += 1
                    
                    if updated_count <= 5:  # Show first 5 updates
                        print(f"  ✅ Updated {record['ticker']} {record['timeframe']} {record['system']} "
                              f"({record['date']}): {success_rates['success_rate_1h']}%/{success_rates['success_rate_1d']}%")
                    
            except Exception as e:
                print(f"  ⚠️ Error updating {record['ticker']} {record['timeframe']}: {e}")
                continue
        
        print(f"✅ Updated {updated_count} analytics records with success rates")
        
        # 5. Show updated analytics summary
        updated_analytics = await conn.fetchval("""
            SELECT COUNT(*) FROM signal_analytics 
            WHERE success_rate_1h IS NOT NULL OR success_rate_1d IS NOT NULL
        """)
        
        print(f"\n📈 Analytics Summary:")
        print(f"  Records with success rates: {updated_analytics}")
        print(f"  Records still needing rates: {273 - updated_analytics}")  # From our earlier inspection
        
        # 6. Show best performing signals
        best_performers = await conn.fetch("""
            SELECT ticker, timeframe, system, success_rate_1h, success_rate_1d, total_signals
            FROM signal_analytics 
            WHERE success_rate_1d IS NOT NULL AND total_signals >= 2
            ORDER BY success_rate_1d DESC, total_signals DESC
            LIMIT 5
        """)
        
        if best_performers:
            print(f"\n🏆 Top Performing Signals (1-day success rate):")
            for i, perf in enumerate(best_performers, 1):
                print(f"  {i}. {perf['ticker']} {perf['timeframe']} {perf['system']}: "
                      f"{perf['success_rate_1d']}% success ({perf['total_signals']} signals)")
        
        await conn.close()
        print("\n✅ Analytics update complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(update_analytics()) 