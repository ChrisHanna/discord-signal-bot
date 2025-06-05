#!/usr/bin/env python3
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def check_performance_data():
    """Check if performance data was successfully recorded"""
    try:
        DATABASE_URL = os.getenv('DATABASE_URL')
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Check total performance records
        total_count = await conn.fetchval('SELECT COUNT(*) FROM signal_performance')
        print(f"📊 Total performance records: {total_count}")
        
        # Check sample of records with more detail
        print(f"\n🔍 Detailed sample analysis:")
        sample_records = await conn.fetch('''
            SELECT ticker, timeframe, signal_type, signal_date, 
                   price_at_signal, price_after_1h, price_after_1d,
                   CASE WHEN price_after_1h > price_at_signal THEN 'SUCCESS' ELSE 'FAIL' END as result_1h,
                   CASE WHEN price_after_1d > price_at_signal THEN 'SUCCESS' ELSE 'FAIL' END as result_1d,
                   ROUND(((price_after_1h - price_at_signal) / price_at_signal * 100)::numeric, 2) as gain_1h_pct,
                   ROUND(((price_after_1d - price_at_signal) / price_at_signal * 100)::numeric, 2) as gain_1d_pct
            FROM signal_performance 
            WHERE price_at_signal IS NOT NULL 
              AND price_after_1h IS NOT NULL 
              AND price_after_1d IS NOT NULL
            ORDER BY id DESC 
            LIMIT 10
        ''')
        
        for record in sample_records:
            print(f"   {record['ticker']} ({record['timeframe']}) - {record['signal_type']}")
            print(f"   Signal: ${record['price_at_signal']:.2f}")
            print(f"   1h: ${record['price_after_1h']:.2f} ({record['gain_1h_pct']}%) - {record['result_1h']}")
            print(f"   1d: ${record['price_after_1d']:.2f} ({record['gain_1d_pct']}%) - {record['result_1d']}")
            print()
        
        # Analyze by signal type
        print(f"🎯 Success rates by signal type:")
        signal_analysis = await conn.fetch('''
            SELECT 
                signal_type,
                COUNT(*) as total_signals,
                COUNT(CASE WHEN price_after_1h > price_at_signal THEN 1 END) as profitable_1h,
                COUNT(CASE WHEN price_after_1d > price_at_signal THEN 1 END) as profitable_1d,
                ROUND(AVG((price_after_1h - price_at_signal) / price_at_signal * 100)::numeric, 2) as avg_gain_1h,
                ROUND(AVG((price_after_1d - price_at_signal) / price_at_signal * 100)::numeric, 2) as avg_gain_1d
            FROM signal_performance 
            WHERE price_at_signal IS NOT NULL 
              AND price_after_1h IS NOT NULL 
              AND price_after_1d IS NOT NULL
            GROUP BY signal_type
            ORDER BY total_signals DESC
            LIMIT 10
        ''')
        
        for row in signal_analysis:
            success_1h = (row['profitable_1h'] / row['total_signals']) * 100 if row['total_signals'] > 0 else 0
            success_1d = (row['profitable_1d'] / row['total_signals']) * 100 if row['total_signals'] > 0 else 0
            print(f"   {row['signal_type']}: {row['total_signals']} signals")
            print(f"     1h: {success_1h:.1f}% success, {row['avg_gain_1h']}% avg gain")
            print(f"     1d: {success_1d:.1f}% success, {row['avg_gain_1d']}% avg gain")
        
        # Check for bullish vs bearish signals
        print(f"\n📈 Bullish vs Bearish signal analysis:")
        bullish_bearish = await conn.fetch('''
            SELECT 
                CASE 
                    WHEN signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%long%' THEN 'BULLISH'
                    WHEN signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%short%' THEN 'BEARISH'
                    ELSE 'NEUTRAL'
                END as signal_direction,
                COUNT(*) as total_signals,
                COUNT(CASE WHEN price_after_1h > price_at_signal THEN 1 END) as profitable_1h,
                COUNT(CASE WHEN price_after_1d > price_at_signal THEN 1 END) as profitable_1d,
                ROUND(AVG((price_after_1h - price_at_signal) / price_at_signal * 100)::numeric, 2) as avg_gain_1h,
                ROUND(AVG((price_after_1d - price_at_signal) / price_at_signal * 100)::numeric, 2) as avg_gain_1d
            FROM signal_performance 
            WHERE price_at_signal IS NOT NULL 
              AND price_after_1h IS NOT NULL 
              AND price_after_1d IS NOT NULL
            GROUP BY signal_direction
            ORDER BY total_signals DESC
        ''')
        
        for row in bullish_bearish:
            success_1h = (row['profitable_1h'] / row['total_signals']) * 100 if row['total_signals'] > 0 else 0
            success_1d = (row['profitable_1d'] / row['total_signals']) * 100 if row['total_signals'] > 0 else 0
            print(f"   {row['signal_direction']}: {row['total_signals']} signals")
            print(f"     1h: {success_1h:.1f}% success, {row['avg_gain_1h']}% avg gain")
            print(f"     1d: {success_1d:.1f}% success, {row['avg_gain_1d']}% avg gain")
        
        # Check with minimum percentage gain threshold
        print(f"\n💰 Success rates with minimum gain thresholds:")
        thresholds = [0.5, 1.0, 2.0]  # 0.5%, 1%, 2% minimum gains
        
        for threshold in thresholds:
            threshold_data = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_signals,
                    COUNT(CASE WHEN (price_after_1h - price_at_signal) / price_at_signal * 100 >= $1 THEN 1 END) as profitable_1h,
                    COUNT(CASE WHEN (price_after_1d - price_at_signal) / price_at_signal * 100 >= $1 THEN 1 END) as profitable_1d
                FROM signal_performance 
                WHERE price_at_signal IS NOT NULL 
                  AND price_after_1h IS NOT NULL 
                  AND price_after_1d IS NOT NULL
            ''', threshold)
            
            if threshold_data['total_signals'] > 0:
                success_1h = (threshold_data['profitable_1h'] / threshold_data['total_signals']) * 100
                success_1d = (threshold_data['profitable_1d'] / threshold_data['total_signals']) * 100
                print(f"   {threshold}%+ gain: 1h: {success_1h:.1f}%, 1d: {success_1d:.1f}%")
        
        # Check corrected success rates accounting for signal direction
        print(f"\n🔧 CORRECTED Success Analysis (accounting for signal direction):")
        corrected_analysis = await conn.fetch('''
            SELECT 
                signal_type,
                CASE 
                    WHEN signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%' THEN 'BULLISH'
                    WHEN signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%' THEN 'BEARISH'
                    ELSE 'NEUTRAL'
                END as signal_direction,
                COUNT(*) as total_signals,
                -- For BULLISH signals: success = price increase
                -- For BEARISH signals: success = price decrease  
                COUNT(CASE 
                    WHEN (signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%')
                         AND price_after_1h > price_at_signal THEN 1
                    WHEN (signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%')
                         AND price_after_1h < price_at_signal THEN 1
                END) as correct_1h,
                COUNT(CASE 
                    WHEN (signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%')
                         AND price_after_1d > price_at_signal THEN 1
                    WHEN (signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%')
                         AND price_after_1d < price_at_signal THEN 1
                END) as correct_1d,
                ROUND(AVG((price_after_1h - price_at_signal) / price_at_signal * 100)::numeric, 2) as avg_gain_1h,
                ROUND(AVG((price_after_1d - price_at_signal) / price_at_signal * 100)::numeric, 2) as avg_gain_1d
            FROM signal_performance 
            WHERE price_at_signal IS NOT NULL 
              AND price_after_1h IS NOT NULL 
              AND price_after_1d IS NOT NULL
              AND price_after_1h != price_at_signal  -- Exclude 0% changes
              AND price_after_1d != price_at_signal  -- Exclude 0% changes
            GROUP BY signal_type, signal_direction
            ORDER BY total_signals DESC
            LIMIT 15
        ''')
        
        print(f"   Signal Type (Direction) | Count | 1h Success | 1d Success | Avg 1h | Avg 1d")
        print(f"   " + "-" * 80)
        for row in corrected_analysis:
            if row['total_signals'] > 0:
                success_1h = (row['correct_1h'] / row['total_signals']) * 100 if row['correct_1h'] else 0
                success_1d = (row['correct_1d'] / row['total_signals']) * 100 if row['correct_1d'] else 0
                print(f"   {row['signal_type'][:25]} ({row['signal_direction'][:3]}) | {row['total_signals']:3d} | {success_1h:6.1f}% | {success_1d:6.1f}% | {row['avg_gain_1h']:6.2f}% | {row['avg_gain_1d']:6.2f}%")
        
        # Overall corrected success rates
        print(f"\n📊 OVERALL CORRECTED Success Rates:")
        overall_corrected = await conn.fetchrow('''
            SELECT 
                COUNT(*) as total_signals,
                COUNT(CASE 
                    WHEN (signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%')
                         AND price_after_1h > price_at_signal THEN 1
                    WHEN (signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%')
                         AND price_after_1h < price_at_signal THEN 1
                END) as correct_1h,
                COUNT(CASE 
                    WHEN (signal_type ILIKE '%bullish%' OR signal_type ILIKE '%buy%' OR signal_type ILIKE '%oversold%' OR signal_type ILIKE '%entry%')
                         AND price_after_1d > price_at_signal THEN 1
                    WHEN (signal_type ILIKE '%bearish%' OR signal_type ILIKE '%sell%' OR signal_type ILIKE '%overbought%')
                         AND price_after_1d < price_at_signal THEN 1
                END) as correct_1d
            FROM signal_performance 
            WHERE price_at_signal IS NOT NULL 
              AND price_after_1h IS NOT NULL 
              AND price_after_1d IS NOT NULL
              AND price_after_1h != price_at_signal  -- Exclude 0% changes
              AND price_after_1d != price_at_signal  -- Exclude 0% changes
        ''')
        
        if overall_corrected['total_signals'] > 0:
            overall_success_1h = (overall_corrected['correct_1h'] / overall_corrected['total_signals']) * 100
            overall_success_1d = (overall_corrected['correct_1d'] / overall_corrected['total_signals']) * 100
            print(f"   Total signals analyzed: {overall_corrected['total_signals']}")
            print(f"   1-hour success rate: {overall_success_1h:.1f}%")
            print(f"   1-day success rate: {overall_success_1d:.1f}%")
        
        await conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error checking performance data: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(check_performance_data()) 