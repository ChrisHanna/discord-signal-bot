#!/usr/bin/env python3
"""
Fix Old Signals Issue
When new timeframes are added, prevent old signals from being sent as notifications
"""
import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from database import db_manager

# Load environment variables
load_dotenv()

async def analyze_old_signals_issue():
    """Analyze the old signals issue and provide insights"""
    try:
        await db_manager.initialize()
        async with db_manager.pool.acquire() as conn:
            print("🔍 Analyzing Old Signals Issue")
            print("=" * 50)
            
            # 1. Check for recent notifications that might be old signals
            recent_notifications = await conn.fetch('''
                SELECT 
                    ticker, timeframe, signal_type, signal_date, notified_at,
                    (notified_at - signal_date) as delay_between_signal_and_notification
                FROM signal_notifications
                WHERE notified_at >= NOW() - INTERVAL '24 hours'
                ORDER BY (notified_at - signal_date) DESC
                LIMIT 20
            ''')
            
            print(f"📊 Recent notifications (last 24h): {len(recent_notifications)}")
            
            old_signals_sent = []
            for notif in recent_notifications:
                delay = notif['delay_between_signal_and_notification']
                if delay and delay.total_seconds() > 24 * 3600:  # More than 24 hours delay
                    old_signals_sent.append(notif)
                    print(f"⚠️ OLD SIGNAL DETECTED:")
                    print(f"   {notif['ticker']} {notif['timeframe']} {notif['signal_type']}")
                    print(f"   Signal Date: {notif['signal_date']}")
                    print(f"   Sent At: {notif['notified_at']}")
                    print(f"   Delay: {delay}")
                    print()
            
            if not old_signals_sent:
                print("✅ No old signals detected in recent notifications!")
            else:
                print(f"❌ Found {len(old_signals_sent)} old signals that were sent recently")
            
            # 2. Check signals_detected for patterns
            print("\n🔍 Analyzing signals_detected table:")
            print("-" * 40)
            
            signals_by_timeframe = await conn.fetch('''
                SELECT 
                    timeframe,
                    COUNT(*) as total_detected,
                    COUNT(*) FILTER (WHERE was_sent = true) as sent,
                    COUNT(*) FILTER (WHERE skip_reason = 'duplicate_notification') as skipped_duplicate,
                    MIN(detected_at) as first_detected,
                    MAX(detected_at) as last_detected
                FROM signals_detected
                WHERE detected_at >= NOW() - INTERVAL '7 days'
                GROUP BY timeframe
                ORDER BY total_detected DESC
            ''')
            
            for row in signals_by_timeframe:
                print(f"Timeframe {row['timeframe']}:")
                print(f"  Total detected: {row['total_detected']}")
                print(f"  Sent: {row['sent']}")
                print(f"  Skipped (duplicate): {row['skipped_duplicate']}")
                print(f"  First detected: {row['first_detected']}")
                print(f"  Last detected: {row['last_detected']}")
                print()
            
            # 3. Check for signals that should have been duplicates but weren't caught
            potential_missed_duplicates = await conn.fetch('''
                SELECT 
                    sd.ticker, sd.timeframe, sd.signal_type, sd.detected_at,
                    sd.was_sent, sd.skip_reason,
                    sn.notified_at as previous_notification
                FROM signals_detected sd
                LEFT JOIN signal_notifications sn ON (
                    sd.ticker = sn.ticker AND 
                    sd.timeframe = sn.timeframe AND 
                    sd.signal_type = sn.signal_type AND
                    sd.detected_at::date = sn.signal_date::date
                )
                WHERE sd.detected_at >= NOW() - INTERVAL '24 hours'
                    AND sd.was_sent = true
                    AND sn.notified_at IS NOT NULL
                    AND sn.notified_at < sd.detected_at - INTERVAL '1 hour'
                ORDER BY sd.detected_at DESC
                LIMIT 10
            ''')
            
            if potential_missed_duplicates:
                print("⚠️ Potential missed duplicates:")
                for row in potential_missed_duplicates:
                    print(f"   {row['ticker']} {row['timeframe']} {row['signal_type']}")
                    print(f"   Detected: {row['detected_at']}")
                    print(f"   Previous notification: {row['previous_notification']}")
                    print()
            
            return True
            
    except Exception as e:
        print(f"❌ Error analyzing old signals: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if hasattr(db_manager, 'pool') and db_manager.pool:
            await db_manager.pool.close()

async def implement_improved_duplicate_detection():
    """Implement improved duplicate detection to prevent old signals"""
    try:
        await db_manager.initialize()
        async with db_manager.pool.acquire() as conn:
            print("🔧 Implementing Improved Duplicate Detection")
            print("=" * 50)
            
            # 1. Populate signals_detected table with historical notifications
            # This ensures that previously sent signals are tracked in both tables
            print("📝 Backfilling signals_detected with historical notifications...")
            
            backfill_result = await conn.execute('''
                INSERT INTO signals_detected (
                    ticker, timeframe, signal_type, signal_date, strength, 
                    system, priority_score, priority_level, was_sent, 
                    detected_at, skip_reason
                )
                SELECT 
                    sn.ticker, sn.timeframe, sn.signal_type, sn.signal_date, 
                    COALESCE(sn.strength, 'Unknown'),
                    COALESCE(sn.system, 'Legacy'),
                    COALESCE(sn.priority_score, 50),
                    COALESCE(sn.priority_level, 'MEDIUM'),
                    true as was_sent,
                    sn.notified_at as detected_at,
                    null as skip_reason
                FROM signal_notifications sn
                LEFT JOIN signals_detected sd ON (
                    sn.ticker = sd.ticker AND 
                    sn.timeframe = sd.timeframe AND 
                    sn.signal_type = sd.signal_type AND 
                    sn.signal_date = sd.signal_date
                )
                WHERE sd.id IS NULL
                    AND sn.notified_at >= NOW() - INTERVAL '30 days'
                ON CONFLICT (ticker, timeframe, signal_type, signal_date) 
                DO NOTHING
            ''')
            
            print(f"✅ Backfilled {backfill_result.split()[-1] if backfill_result else '0'} historical records")
            
            # 2. Create a view for comprehensive duplicate checking
            print("📊 Creating comprehensive duplicate detection view...")
            
            await conn.execute('''
                CREATE OR REPLACE VIEW comprehensive_signal_history AS
                SELECT DISTINCT
                    ticker, timeframe, signal_type, signal_date::date as signal_day
                FROM (
                    SELECT ticker, timeframe, signal_type, signal_date 
                    FROM signal_notifications
                    UNION ALL
                    SELECT ticker, timeframe, signal_type, signal_date::timestamp 
                    FROM signals_detected 
                    WHERE was_sent = true
                ) combined_signals
            ''')
            
            print("✅ Created comprehensive_signal_history view")
            
            # 3. Show statistics
            stats = await conn.fetchrow('''
                SELECT 
                    (SELECT COUNT(*) FROM signal_notifications) as total_notifications,
                    (SELECT COUNT(*) FROM signals_detected) as total_detected,
                    (SELECT COUNT(*) FROM comprehensive_signal_history) as unique_signals
            ''')
            
            print(f"\n📊 Database Statistics:")
            print(f"  Total notifications: {stats['total_notifications']}")
            print(f"  Total detected signals: {stats['total_detected']}")
            print(f"  Unique signal combinations: {stats['unique_signals']}")
            
            return True
            
    except Exception as e:
        print(f"❌ Error implementing improved duplicate detection: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if hasattr(db_manager, 'pool') and db_manager.pool:
            await db_manager.pool.close()

async def create_enhanced_duplicate_checker():
    """Create an enhanced duplicate checking function"""
    enhanced_checker_code = '''
async def enhanced_check_duplicate(ticker: str, timeframe: str, signal_type: str, signal_date: str) -> bool:
    """Enhanced duplicate checking that prevents old signals from being sent"""
    try:
        async with db_manager.pool.acquire() as conn:
            # Parse signal date
            if ' ' in signal_date:
                parsed_date = datetime.strptime(signal_date, '%Y-%m-%d %H:%M:%S')
            else:
                parsed_date = datetime.strptime(signal_date, '%Y-%m-%d')
            
            # Check both tables for duplicates
            result = await conn.fetchval('''
                SELECT COUNT(*) FROM (
                    SELECT 1 FROM signal_notifications 
                    WHERE ticker = $1 AND timeframe = $2 
                    AND signal_type = $3 AND signal_date::date = $4::date
                    
                    UNION
                    
                    SELECT 1 FROM signals_detected 
                    WHERE ticker = $1 AND timeframe = $2 
                    AND signal_type = $3 AND signal_date::date = $4::date
                    AND was_sent = true
                ) combined
            ''', ticker, timeframe, signal_type, parsed_date)
            
            # Additional time-based filtering for new timeframes
            if result == 0:
                # Check if this signal is too old to be a "new" signal
                signal_age_hours = (datetime.now() - parsed_date).total_seconds() / 3600
                
                # For newly added timeframes, only allow signals from last 24 hours
                if timeframe in ['3h', '6h', '2d', '3d'] and signal_age_hours > 24:
                    print(f"🚫 Blocking old signal: {ticker} {timeframe} {signal_type} from {signal_age_hours:.1f}h ago")
                    return True  # Treat as duplicate to prevent sending
            
            return result > 0
            
    except Exception as e:
        print(f"❌ Error in enhanced duplicate check: {e}")
        return False
'''
    
    # Write the enhanced checker to a file
    with open('discord-bot/enhanced_duplicate_checker.py', 'w') as f:
        f.write('#!/usr/bin/env python3\n')
        f.write('"""\nEnhanced Duplicate Checker\nPrevents old signals from being sent when new timeframes are added\n"""\n')
        f.write('import asyncio\n')
        f.write('from datetime import datetime, timedelta\n')
        f.write('from database import db_manager\n\n')
        f.write(enhanced_checker_code)
    
    print("✅ Created enhanced_duplicate_checker.py")
    print("💡 This enhanced checker can be integrated into signal_notifier.py")

async def main():
    """Main function to analyze and fix the old signals issue"""
    print("🚀 Old Signals Issue Fix Tool")
    print("=" * 40)
    
    # Step 1: Analyze the issue
    print("STEP 1: Analyzing the issue...")
    await analyze_old_signals_issue()
    
    print("\n" + "=" * 50)
    
    # Step 2: Implement improvements
    print("STEP 2: Implementing improvements...")
    await implement_improved_duplicate_detection()
    
    print("\n" + "=" * 50)
    
    # Step 3: Create enhanced checker
    print("STEP 3: Creating enhanced duplicate checker...")
    await create_enhanced_duplicate_checker()
    
    print("\n✅ Old signals issue analysis and fix complete!")
    print("\n💡 Recommendations:")
    print("1. The enhanced duplicate checker prevents old signals")
    print("2. Historical data has been backfilled to signals_detected table")
    print("3. Consider integrating enhanced_duplicate_checker.py into signal_notifier.py")
    print("4. Monitor notifications for the next 24 hours to verify fix")

if __name__ == "__main__":
    asyncio.run(main()) 