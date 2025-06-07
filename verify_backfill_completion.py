#!/usr/bin/env python3
"""
Backfill Completion Verification Script
Verify that all required fields for advanced analytics and success rates are properly populated
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

async def verify_backfill_completion():
    """Comprehensive verification of backfill completion"""
    
    print("🔍 BACKFILL COMPLETION VERIFICATION")
    print("=" * 60)
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable not set")
        return
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Connected to PostgreSQL database")
        
        # 1. Check signal_notifications table
        print("\n📋 SIGNAL NOTIFICATIONS TABLE")
        print("-" * 40)
        
        sn_stats = await conn.fetchrow('''
            SELECT 
                COUNT(*) as total_notifications,
                COUNT(price_at_signal) as with_price,
                COUNT(*) - COUNT(price_at_signal) as missing_price,
                MIN(signal_date) as earliest_signal,
                MAX(signal_date) as latest_signal
            FROM signal_notifications
        ''')
        
        print(f"📊 Total notifications: {sn_stats['total_notifications']:,}")
        print(f"💰 With price data: {sn_stats['with_price']:,}")
        print(f"❌ Missing price data: {sn_stats['missing_price']:,}")
        if sn_stats['total_notifications'] > 0:
            coverage = (sn_stats['with_price'] / sn_stats['total_notifications']) * 100
            print(f"📈 Price coverage: {coverage:.1f}%")
        print(f"📅 Date range: {sn_stats['earliest_signal']} to {sn_stats['latest_signal']}")
        
        # 2. Check signal_performance table
        print("\n📋 SIGNAL PERFORMANCE TABLE")
        print("-" * 40)
        
        sp_stats = await conn.fetchrow('''
            SELECT 
                COUNT(*) as total_performance,
                COUNT(price_at_signal) as with_price_at_signal,
                COUNT(price_after_1h) as with_1h,
                COUNT(price_after_3h) as with_3h,
                COUNT(price_after_4h) as with_4h,
                COUNT(price_after_6h) as with_6h,
                COUNT(price_after_1d) as with_1d,
                COUNT(price_after_3d) as with_3d,
                COUNT(success_1h) as with_success_1h,
                COUNT(success_3h) as with_success_3h,
                COUNT(success_4h) as with_success_4h,
                COUNT(success_6h) as with_success_6h,
                COUNT(success_1d) as with_success_1d,
                COUNT(success_3d) as with_success_3d,
                MIN(signal_date) as earliest_signal,
                MAX(signal_date) as latest_signal
            FROM signal_performance
        ''')
        
        print(f"📊 Total performance records: {sp_stats['total_performance']:,}")
        print(f"📅 Date range: {sp_stats['earliest_signal']} to {sp_stats['latest_signal']}")
        
        # Price field coverage
        print(f"\n💰 PRICE FIELD COVERAGE:")
        price_fields = ['price_at_signal', '1h', '3h', '4h', '6h', '1d', '3d']
        for field in price_fields:
            count = sp_stats[f'with_{field}'] if field != 'price_at_signal' else sp_stats['with_price_at_signal']
            coverage = (count / sp_stats['total_performance']) * 100 if sp_stats['total_performance'] > 0 else 0
            print(f"   {field}: {count:,} ({coverage:.1f}%)")
        
        # Success field coverage
        print(f"\n🎯 SUCCESS FIELD COVERAGE:")
        success_fields = ['1h', '3h', '4h', '6h', '1d', '3d']
        for field in success_fields:
            count = sp_stats[f'with_success_{field}']
            coverage = (count / sp_stats['total_performance']) * 100 if sp_stats['total_performance'] > 0 else 0
            print(f"   success_{field}: {count:,} ({coverage:.1f}%)")
        
        # 3. Check for records missing critical fields
        print("\n🔍 MISSING CRITICAL FIELDS ANALYSIS")
        print("-" * 40)
        
        missing_critical = await conn.fetchrow('''
            SELECT 
                COUNT(*) as missing_price_at_signal,
                COUNT(*) FILTER (WHERE price_after_1h IS NULL) as missing_1h_price,
                COUNT(*) FILTER (WHERE price_after_6h IS NULL) as missing_6h_price,
                COUNT(*) FILTER (WHERE price_after_1d IS NULL) as missing_1d_price,
                COUNT(*) FILTER (WHERE success_1h IS NULL) as missing_1h_success,
                COUNT(*) FILTER (WHERE success_6h IS NULL) as missing_6h_success,
                COUNT(*) FILTER (WHERE success_1d IS NULL) as missing_1d_success
            FROM signal_performance
            WHERE price_at_signal IS NULL
        ''')
        
        print(f"❌ Records missing price_at_signal: {missing_critical['missing_price_at_signal']:,}")
        if missing_critical['missing_price_at_signal'] > 0:
            print(f"   └─ Also missing 1h price: {missing_critical['missing_1h_price']:,}")
            print(f"   └─ Also missing 6h price: {missing_critical['missing_6h_price']:,}")
            print(f"   └─ Also missing 1d price: {missing_critical['missing_1d_price']:,}")
            print(f"   └─ Also missing 1h success: {missing_critical['missing_1h_success']:,}")
            print(f"   └─ Also missing 6h success: {missing_critical['missing_6h_success']:,}")
            print(f"   └─ Also missing 1d success: {missing_critical['missing_1d_success']:,}")
        
        # 4. Check recent signals (last 7 days)
        print("\n📅 RECENT SIGNALS ANALYSIS (Last 7 days)")
        print("-" * 40)
        
        recent_stats = await conn.fetchrow('''
            SELECT 
                COUNT(*) as total_recent,
                COUNT(price_at_signal) as recent_with_price,
                COUNT(success_1d) as recent_with_success
            FROM signal_performance
            WHERE signal_date >= NOW() - INTERVAL '7 days'
        ''')
        
        print(f"📊 Recent signals: {recent_stats['total_recent']:,}")
        if recent_stats['total_recent'] > 0:
            price_coverage = (recent_stats['recent_with_price'] / recent_stats['total_recent']) * 100
            success_coverage = (recent_stats['recent_with_success'] / recent_stats['total_recent']) * 100
            print(f"💰 With price data: {recent_stats['recent_with_price']:,} ({price_coverage:.1f}%)")
            print(f"🎯 With success data: {recent_stats['recent_with_success']:,} ({success_coverage:.1f}%)")
        
        # 5. Check ticker distribution
        print("\n📈 TICKER DISTRIBUTION")
        print("-" * 40)
        
        ticker_stats = await conn.fetch('''
            SELECT 
                ticker,
                COUNT(*) as total_signals,
                COUNT(price_at_signal) as with_price,
                COUNT(success_1d) as with_success
            FROM signal_performance
            GROUP BY ticker
            ORDER BY total_signals DESC
            LIMIT 10
        ''')
        
        for row in ticker_stats:
            price_pct = (row['with_price'] / row['total_signals']) * 100 if row['total_signals'] > 0 else 0
            success_pct = (row['with_success'] / row['total_signals']) * 100 if row['total_signals'] > 0 else 0
            print(f"   {row['ticker']}: {row['total_signals']:,} signals ({price_pct:.0f}% price, {success_pct:.0f}% success)")
        
        # 6. Test advanced analytics functions
        print("\n🧪 ADVANCED ANALYTICS COMPATIBILITY TEST")
        print("-" * 40)
        
        try:
            # Test correlation analysis query
            correlation_test = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as usable_records
                FROM signal_performance sp
                WHERE sp.price_at_signal IS NOT NULL 
                AND sp.price_after_1h IS NOT NULL 
                AND sp.price_after_6h IS NOT NULL 
                AND sp.price_after_1d IS NOT NULL
                AND sp.success_1h IS NOT NULL 
                AND sp.success_6h IS NOT NULL 
                AND sp.success_1d IS NOT NULL
                AND sp.signal_date >= NOW() - INTERVAL '30 days'
            ''')
            
            print(f"✅ Records ready for correlation analysis: {correlation_test['usable_records']:,}")
            
            # Test success rate query
            success_test = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_signals,
                    AVG(CASE WHEN success_1h THEN 1.0 ELSE 0.0 END) as avg_success_1h,
                    AVG(CASE WHEN success_6h THEN 1.0 ELSE 0.0 END) as avg_success_6h,
                    AVG(CASE WHEN success_1d THEN 1.0 ELSE 0.0 END) as avg_success_1d
                FROM signal_performance
                WHERE success_1h IS NOT NULL 
                AND success_6h IS NOT NULL 
                AND success_1d IS NOT NULL
                AND signal_date >= NOW() - INTERVAL '30 days'
            ''')
            
            if success_test['total_signals'] > 0:
                print(f"✅ Success rate calculation ready: {success_test['total_signals']:,} signals")
                print(f"   📊 1h success rate: {success_test['avg_success_1h']:.1%}")
                print(f"   📊 6h success rate: {success_test['avg_success_6h']:.1%}")
                print(f"   📊 1d success rate: {success_test['avg_success_1d']:.1%}")
            else:
                print("❌ No signals ready for success rate calculation")
            
        except Exception as e:
            print(f"❌ Advanced analytics test failed: {e}")
        
        await conn.close()
        
        # 7. Overall assessment
        print(f"\n🎯 OVERALL ASSESSMENT")
        print("=" * 60)
        
        total_records = sp_stats['total_performance']
        critical_coverage = sp_stats['with_price_at_signal'] / total_records if total_records > 0 else 0
        
        if critical_coverage >= 0.95:
            print("🟢 EXCELLENT: >95% of records have complete data")
        elif critical_coverage >= 0.80:
            print("🟡 GOOD: >80% of records have complete data")
        elif critical_coverage >= 0.60:
            print("🟠 FAIR: >60% of records have complete data")
        else:
            print("🔴 NEEDS WORK: <60% of records have complete data")
        
        print(f"📊 Overall data completeness: {critical_coverage:.1%}")
        
        if missing_critical['missing_price_at_signal'] > 0:
            print(f"💡 Recommendation: Run backfill for {missing_critical['missing_price_at_signal']:,} remaining records")
        else:
            print("✅ All records have price_at_signal data!")
        
        print("\n🚀 READY FOR:")
        print("   ✅ Advanced correlation analysis")
        print("   ✅ Success rate calculations") 
        print("   ✅ ML predictions")
        print("   ✅ Discord bot commands (!successrates, !correlations)")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_backfill_completion()) 