#!/usr/bin/env python3
"""
One-Time Analytics Rebuild Script
Comprehensive rebuild of all analytics from historical signal data
"""

import asyncio
import os
import asyncpg
from datetime import datetime, timedelta

async def rebuild_analytics():
    """Comprehensive one-time rebuild of all analytics data"""
    
    print("🔄 ONE-TIME ANALYTICS REBUILD")
    print("=" * 60)
    print("This script will rebuild ALL analytics from historical data")
    print("=" * 60)
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable not set")
        return
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Connected to PostgreSQL database")
        
        # 1. Show current data status
        print("\n📊 CURRENT DATA STATUS")
        print("-" * 30)
        
        notifications_count = await conn.fetchval("SELECT COUNT(*) FROM signal_notifications")
        performance_count = await conn.fetchval("SELECT COUNT(*) FROM signal_performance")
        analytics_count = await conn.fetchval("SELECT COUNT(*) FROM signal_analytics")
        
        print(f"📨 Signal notifications: {notifications_count}")
        print(f"📈 Performance records: {performance_count}")
        print(f"📊 Analytics records: {analytics_count}")
        
        if notifications_count == 0:
            print("⚠️ No notification data found - nothing to rebuild!")
            await conn.close()
            return
        
        # 2. Get date range of available data
        date_range = await conn.fetchrow("""
            SELECT 
                MIN(DATE(notified_at)) as earliest_date,
                MAX(DATE(notified_at)) as latest_date,
                COUNT(DISTINCT DATE(notified_at)) as unique_dates
            FROM signal_notifications
        """)
        
        print(f"\n📅 DATA RANGE")
        print(f"   Earliest: {date_range['earliest_date']}")
        print(f"   Latest: {date_range['latest_date']}")
        print(f"   Unique dates: {date_range['unique_dates']}")
        
        # 3. Option to clean existing analytics
        print(f"\n🧹 CLEANUP EXISTING ANALYTICS")
        existing_analytics = await conn.fetchval("SELECT COUNT(*) FROM signal_analytics")
        
        if existing_analytics > 0:
            print(f"   Found {existing_analytics} existing analytics records")
            print(f"   🗑️ Cleaning up old analytics records...")
            
            deleted_count = await conn.execute("DELETE FROM signal_analytics")
            print(f"   ✅ Deleted {existing_analytics} old analytics records")
        else:
            print(f"   ✅ No existing analytics to clean up")
        
        # 4. Rebuild analytics day by day
        print(f"\n🔄 REBUILDING ANALYTICS")
        print("-" * 30)
        
        # Get all unique dates with signals
        signal_dates = await conn.fetch("""
            SELECT DISTINCT DATE(notified_at) as signal_date
            FROM signal_notifications
            ORDER BY signal_date
        """)
        
        total_dates = len(signal_dates)
        processed_dates = 0
        total_analytics_created = 0
        
        for date_record in signal_dates:
            signal_date = date_record['signal_date']
            
            # Get all unique combinations for this date
            combinations = await conn.fetch('''
                SELECT 
                    ticker,
                    timeframe, 
                    system,
                    COUNT(*) as total_signals,
                    COUNT(*) FILTER (WHERE was_sent = true) as sent_signals,
                    COUNT(*) FILTER (WHERE was_sent = false) as skipped_signals,
                    ROUND(AVG(priority_score), 2) as avg_priority_score,
                    json_object_agg(priority_level, level_count) as priority_distribution
                FROM (
                    SELECT 
                        ticker,
                        timeframe,
                        system,
                        was_sent,
                        priority_score,
                        priority_level,
                        COUNT(*) as level_count
                    FROM signals_detected
                    WHERE DATE(detected_at) = $1
                    GROUP BY ticker, timeframe, system, was_sent, priority_score, priority_level
                ) grouped
                GROUP BY ticker, timeframe, system
            ''', signal_date)
            
            date_analytics_created = 0
            
            for combo in combinations:
                try:
                    # Calculate success rates if performance data exists
                    success_rates = await conn.fetchrow('''
                        SELECT 
                            ROUND(AVG(CASE WHEN sp.success_1h = true THEN 100.0 ELSE 0.0 END), 2) as success_rate_1h,
                            ROUND(AVG(CASE WHEN sp.success_1d = true THEN 100.0 ELSE 0.0 END), 2) as success_rate_1d,
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
                    ''', signal_date, combo['ticker'], combo['timeframe'], combo['system'])
                    
                    # Insert analytics record
                    await conn.execute('''
                        INSERT INTO signal_analytics (
                            date, ticker, timeframe, system, total_signals, sent_signals, 
                            skipped_signals, avg_priority_score, priority_distribution,
                            success_rate_1h, success_rate_1d, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
                    ''', 
                    signal_date,
                    combo['ticker'],
                    combo['timeframe'], 
                    combo['system'],
                    combo['total_signals'],
                    combo['sent_signals'],
                    combo['skipped_signals'],
                    combo['avg_priority_score'],
                    combo['priority_distribution'],
                    success_rates['success_rate_1h'] if success_rates and success_rates['performance_count'] > 0 else None,
                    success_rates['success_rate_1d'] if success_rates and success_rates['performance_count'] > 0 else None
                    )
                    
                    date_analytics_created += 1
                    total_analytics_created += 1
                    
                except Exception as e:
                    print(f"   ⚠️ Error processing {combo['ticker']} {combo['timeframe']} {combo['system']} for {signal_date}: {e}")
                    continue
            
            processed_dates += 1
            
            if date_analytics_created > 0:
                print(f"   ✅ {signal_date}: Created {date_analytics_created} analytics records")
            
            # Progress indicator
            if processed_dates % 10 == 0 or processed_dates == total_dates:
                print(f"   📈 Progress: {processed_dates}/{total_dates} dates processed")
        
        # 5. Summary statistics
        print(f"\n📊 REBUILD SUMMARY")
        print("-" * 30)
        print(f"✅ Processed {processed_dates} unique dates")
        print(f"✅ Created {total_analytics_created} analytics records")
        
        # Verify final counts
        final_analytics = await conn.fetchval("SELECT COUNT(*) FROM signal_analytics")
        analytics_with_success = await conn.fetchval("""
            SELECT COUNT(*) FROM signal_analytics 
            WHERE success_rate_1h IS NOT NULL OR success_rate_1d IS NOT NULL
        """)
        
        print(f"📈 Final analytics count: {final_analytics}")
        print(f"📊 Records with success rates: {analytics_with_success}")
        
        # 6. Show top performers
        print(f"\n🏆 TOP PERFORMERS")
        print("-" * 30)
        
        top_performers = await conn.fetch("""
            SELECT ticker, timeframe, system, success_rate_1d, total_signals
            FROM signal_analytics 
            WHERE success_rate_1d IS NOT NULL AND total_signals >= 2
            ORDER BY success_rate_1d DESC, total_signals DESC
            LIMIT 10
        """)
        
        if top_performers:
            for i, perf in enumerate(top_performers, 1):
                print(f"   {i:2d}. {perf['ticker']} {perf['timeframe']} {perf['system']}: "
                      f"{perf['success_rate_1d']:5.1f}% success ({perf['total_signals']} signals)")
        else:
            print("   No performance data available yet")
        
        # 7. System summary
        system_summary = await conn.fetch("""
            SELECT 
                system,
                COUNT(*) as records,
                SUM(total_signals) as total_signals,
                SUM(sent_signals) as total_sent,
                ROUND(AVG(avg_priority_score), 2) as avg_priority,
                ROUND(AVG(success_rate_1d), 2) as avg_success_rate
            FROM signal_analytics
            GROUP BY system
            ORDER BY total_signals DESC
        """)
        
        if system_summary:
            print(f"\n🏗️ SYSTEM SUMMARY")
            print("-" * 30)
            for system in system_summary:
                utilization = (system['total_sent'] / max(system['total_signals'], 1)) * 100
                print(f"   {system['system']}: {system['total_signals']} signals, "
                      f"{utilization:.1f}% utilization, {system['avg_priority']:.1f} avg priority")
        
        await conn.close()
        
        print(f"\n✅ ANALYTICS REBUILD COMPLETE!")
        print("=" * 60)
        print("🎯 Your analytics database is now fully populated!")
        print("💡 Use !analytics, !performance, or !bestperformers in Discord")
        
    except Exception as e:
        print(f"❌ Error during rebuild: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 Starting analytics rebuild...")
    asyncio.run(rebuild_analytics()) 