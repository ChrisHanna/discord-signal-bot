#!/usr/bin/env python3
"""
🔧 Fix Success Rate Automation for Discord Bot

This script diagnoses and fixes issues with automatic success rate updates
in the Discord bot's analytics system.
"""

import asyncio
import os
import asyncpg
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

async def diagnose_success_rate_automation():
    """Diagnose why success rates aren't updating automatically"""
    
    print("🔧 Discord Bot Success Rate Automation Diagnostic")
    print("=" * 60)
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable not set")
        return False
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Connected to PostgreSQL database")
        
        # 1. Check signal_performance table
        print("\n1️⃣ Checking signal_performance table...")
        perf_count = await conn.fetchval("SELECT COUNT(*) FROM signal_performance")
        print(f"📊 Total performance records: {perf_count}")
        
        if perf_count == 0:
            print("❌ ISSUE: No performance data available for success rate calculations!")
            print("💡 SOLUTION: Need to populate signal_performance table")
            
            # Check for signal_notifications that could be used for performance calculation
            signal_count = await conn.fetchval("SELECT COUNT(*) FROM signal_notifications WHERE notified_at >= NOW() - INTERVAL '30 days'")
            print(f"📡 Recent signals (30 days): {signal_count}")
            
            if signal_count > 0:
                print("✅ Found recent signals - can backfill performance data")
                
                # Show sample signals that need performance data
                sample_signals = await conn.fetch("""
                    SELECT ticker, timeframe, signal_type, notified_at, signal_date
                    FROM signal_notifications 
                    WHERE notified_at >= NOW() - INTERVAL '7 days'
                    ORDER BY notified_at DESC 
                    LIMIT 5
                """)
                
                print("\n📄 Sample signals needing performance data:")
                for i, signal in enumerate(sample_signals, 1):
                    print(f"  {i}. {signal['ticker']} {signal['timeframe']} {signal['signal_type']} - {signal['notified_at'].strftime('%Y-%m-%d %H:%M')}")
        else:
            print("✅ Performance data exists")
            
            # Check recent performance data
            recent_perf = await conn.fetchval("""
                SELECT COUNT(*) FROM signal_performance 
                WHERE performance_date >= NOW() - INTERVAL '7 days'
            """)
            print(f"📊 Recent performance records (7 days): {recent_perf}")
        
        # 2. Check signal_analytics table
        print("\n2️⃣ Checking signal_analytics table...")
        analytics_count = await conn.fetchval("SELECT COUNT(*) FROM signal_analytics")
        print(f"📈 Total analytics records: {analytics_count}")
        
        # Check analytics with success rates
        analytics_with_success = await conn.fetchval("""
            SELECT COUNT(*) FROM signal_analytics 
            WHERE success_rate_1h IS NOT NULL OR success_rate_1d IS NOT NULL
        """)
        print(f"📊 Analytics with success rates: {analytics_with_success}")
        
        analytics_without_success = analytics_count - analytics_with_success
        if analytics_without_success > 0:
            print(f"⚠️ Analytics missing success rates: {analytics_without_success}")
            
            # Show sample analytics without success rates
            sample_analytics = await conn.fetch("""
                SELECT date, ticker, timeframe, system, total_signals
                FROM signal_analytics 
                WHERE success_rate_1h IS NULL AND success_rate_1d IS NULL
                ORDER BY date DESC 
                LIMIT 5
            """)
            
            print("\n📄 Sample analytics missing success rates:")
            for i, analytics in enumerate(sample_analytics, 1):
                print(f"  {i}. {analytics['date']} - {analytics['ticker']} {analytics['timeframe']} {analytics['system']} ({analytics['total_signals']} signals)")
        
        # 3. Check the auto-update mechanism
        print("\n3️⃣ Checking auto-update mechanism...")
        
        # Test if performance data can be linked to analytics
        linkable_data = await conn.fetchval("""
            SELECT COUNT(*) 
            FROM signal_performance sp
            JOIN signal_notifications sn ON (
                sp.ticker = sn.ticker AND 
                sp.timeframe = sn.timeframe AND 
                sp.signal_type = sn.signal_type AND 
                sp.signal_date = sn.signal_date
            )
            WHERE sn.notified_at >= NOW() - INTERVAL '7 days'
        """)
        print(f"🔗 Performance data linkable to recent signals: {linkable_data}")
        
        if linkable_data == 0:
            print("❌ ISSUE: No performance data can be linked to recent signal notifications!")
            print("💡 SOLUTION: The auto_update_signal_performance function may not be working")
        
        # 4. Test success rate calculation
        print("\n4️⃣ Testing success rate calculation...")
        
        try:
            test_success_rate = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_perf_records,
                    COUNT(*) FILTER (WHERE success_1h = true) as success_1h_count,
                    COUNT(*) FILTER (WHERE success_1d = true) as success_1d_count,
                    ROUND(AVG(CASE WHEN success_1h = true THEN 100.0 ELSE 0.0 END), 2) as calc_success_1h,
                    ROUND(AVG(CASE WHEN success_1d = true THEN 100.0 ELSE 0.0 END), 2) as calc_success_1d
                FROM signal_performance
                WHERE performance_date >= NOW() - INTERVAL '7 days'
            """)
            
            if test_success_rate['total_perf_records'] > 0:
                print(f"✅ Success rate calculation test:")
                print(f"   Total records: {test_success_rate['total_perf_records']}")
                print(f"   1h success rate: {test_success_rate['calc_success_1h']}% ({test_success_rate['success_1h_count']} successes)")
                print(f"   1d success rate: {test_success_rate['calc_success_1d']}% ({test_success_rate['success_1d_count']} successes)")
            else:
                print("❌ No recent performance data to calculate success rates")
        
        except Exception as e:
            print(f"❌ Error calculating success rates: {e}")
        
        # 5. Check auto-update signal performance function
        print("\n5️⃣ Checking auto-update signal performance function...")
        
        # Check if signals have corresponding performance records
        orphaned_signals = await conn.fetchval("""
            SELECT COUNT(*)
            FROM signal_notifications sn
            LEFT JOIN signal_performance sp ON (
                sn.ticker = sp.ticker AND 
                sn.timeframe = sp.timeframe AND 
                sn.signal_type = sp.signal_type AND 
                sn.signal_date = sp.signal_date
            )
            WHERE sn.notified_at >= NOW() - INTERVAL '3 days'
              AND sp.id IS NULL
        """)
        
        print(f"🔍 Recent signals without performance data: {orphaned_signals}")
        
        if orphaned_signals > 0:
            print("❌ ISSUE: Recent signals don't have corresponding performance data!")
            print("💡 SOLUTION: auto_update_signal_performance function may have issues")
            
            # Show sample orphaned signals
            sample_orphaned = await conn.fetch("""
                SELECT sn.ticker, sn.timeframe, sn.signal_type, sn.notified_at
                FROM signal_notifications sn
                LEFT JOIN signal_performance sp ON (
                    sn.ticker = sp.ticker AND 
                    sn.timeframe = sp.timeframe AND 
                    sn.signal_type = sp.signal_type AND 
                    sn.signal_date = sp.signal_date
                )
                WHERE sn.notified_at >= NOW() - INTERVAL '3 days'
                  AND sp.id IS NULL
                ORDER BY sn.notified_at DESC
                LIMIT 5
            """)
            
            print("\n📄 Sample signals missing performance data:")
            for i, signal in enumerate(sample_orphaned, 1):
                print(f"  {i}. {signal['ticker']} {signal['timeframe']} {signal['signal_type']} - {signal['notified_at'].strftime('%Y-%m-%d %H:%M')}")
        
        await conn.close()
        
        # Summary and recommendations
        print("\n" + "=" * 60)
        print("🎯 DIAGNOSIS SUMMARY")
        print("=" * 60)
        
        issues_found = []
        solutions = []
        
        if perf_count == 0:
            issues_found.append("No performance data available")
            solutions.append("Run: python backfill_real_performance.py")
        
        if analytics_without_success > 0:
            issues_found.append(f"{analytics_without_success} analytics missing success rates")
            solutions.append("Run: python update_analytics.py")
        
        if orphaned_signals > 0:
            issues_found.append(f"{orphaned_signals} recent signals missing performance data")
            solutions.append("Fix auto_update_signal_performance function")
        
        if not issues_found:
            print("✅ No major issues found with success rate automation!")
            print("✅ The Discord bot should be calculating success rates automatically")
            print("\n🔧 If success rates still aren't showing, try:")
            print("   1. Restart the Discord bot")
            print("   2. Wait for the next analytics update cycle (every 5 signal checks)")
            print("   3. Manually run: !updateanalytics in Discord")
        else:
            print("❌ Issues found with success rate automation:")
            for i, issue in enumerate(issues_found, 1):
                print(f"   {i}. {issue}")
            
            print("\n💡 Recommended solutions:")
            for i, solution in enumerate(solutions, 1):
                print(f"   {i}. {solution}")
        
        return len(issues_found) == 0
        
    except Exception as e:
        print(f"❌ Error during diagnosis: {e}")
        return False

async def fix_success_rate_automation():
    """Fix the success rate automation issues"""
    
    print("\n🔧 FIXING SUCCESS RATE AUTOMATION")
    print("=" * 60)
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable not set")
        return False
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Fix 1: Update analytics with existing performance data
        print("\n1️⃣ Updating analytics with existing performance data...")
        
        # Get analytics records that need success rate updates
        analytics_to_update = await conn.fetch("""
            SELECT DISTINCT sa.date, sa.ticker, sa.timeframe, sa.system
            FROM signal_analytics sa
            WHERE sa.success_rate_1h IS NULL OR sa.success_rate_1d IS NULL
            ORDER BY sa.date DESC
            LIMIT 50
        """)
        
        updated_count = 0
        for record in analytics_to_update:
            try:
                # Calculate success rates for this combination
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
                        SET success_rate_1h = $5, success_rate_1d = $6,
                            updated_at = NOW()
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
        
        await conn.close()
        
        print("\n✅ Success rate automation fixes completed!")
        print("\n🎯 Next steps:")
        print("   1. The Discord bot should now calculate success rates automatically")
        print("   2. Analytics update every 5 signal check cycles in the bot")
        print("   3. Use !analyticshealth in Discord to check status")
        print("   4. Use !updateanalytics to manually trigger updates")
        
        return True
        
    except Exception as e:
        print(f"❌ Error fixing automation: {e}")
        return False

async def main():
    """Main function to diagnose and fix success rate automation"""
    print("🤖 Discord Bot Success Rate Automation Fixer")
    print("This tool will diagnose and fix issues with automatic success rate updates")
    print()
    
    # Step 1: Diagnose issues
    diagnosis_success = await diagnose_success_rate_automation()
    
    if not diagnosis_success:
        # Step 2: Fix issues
        fix_success = await fix_success_rate_automation()
        
        if fix_success:
            print("\n🎉 SUCCESS! Discord bot success rate automation should now work correctly.")
        else:
            print("\n❌ Some issues remain. Please check the logs above and try manual solutions.")
    else:
        print("\n🎉 No issues found! Your Discord bot success rate automation is working correctly.")
    
    print("\n💡 Additional tools you can use:")
    print("   - python backfill_real_performance.py - Populate historical performance data")
    print("   - python update_analytics.py - Manually update all analytics")
    print("   - !analyticshealth in Discord - Check analytics system health")
    print("   - !updateanalytics in Discord - Manual analytics update")

if __name__ == "__main__":
    asyncio.run(main()) 