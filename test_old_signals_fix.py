#!/usr/bin/env python3
"""
Test Old Signals Fix
Simple test to verify that old signals are blocked correctly
"""
import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from database import db_manager

# Load environment variables
load_dotenv()

async def test_old_signals_fix():
    """Test that old signals are properly blocked"""
    try:
        await db_manager.initialize()
        
        print("🧪 Testing Old Signals Fix")
        print("=" * 40)
        
        # Test cases with different signal ages
        test_cases = [
            {
                'name': 'Recent signal (30 minutes ago)',
                'signal_date': (datetime.now() - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S'),
                'should_be_blocked': False
            },
            {
                'name': 'Old signal (2 days ago)',
                'signal_date': (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S'),
                'should_be_blocked': True
            },
            {
                'name': 'Very old signal (1 week ago)',
                'signal_date': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S'),
                'should_be_blocked': True
            },
            {
                'name': 'Edge case signal (23 hours ago)',
                'signal_date': (datetime.now() - timedelta(hours=23)).strftime('%Y-%m-%d %H:%M:%S'),
                'should_be_blocked': False
            },
            {
                'name': 'Edge case signal (25 hours ago)',
                'signal_date': (datetime.now() - timedelta(hours=25)).strftime('%Y-%m-%d %H:%M:%S'),
                'should_be_blocked': True
            }
        ]
        
        # Test each case
        all_tests_passed = True
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{i}. {test_case['name']}")
            print(f"   Signal Date: {test_case['signal_date']}")
            
            # Test the duplicate check function
            is_blocked = await db_manager.check_duplicate_notification(
                ticker="TEST",
                timeframe="1h", 
                signal_type="Test Signal",
                signal_date=test_case['signal_date']
            )
            
            expected_result = test_case['should_be_blocked']
            
            if is_blocked == expected_result:
                status = "✅ PASS"
                print(f"   Result: {status} - {'Blocked' if is_blocked else 'Allowed'} (as expected)")
            else:
                status = "❌ FAIL"
                all_tests_passed = False
                print(f"   Result: {status} - {'Blocked' if is_blocked else 'Allowed'} (expected {'Blocked' if expected_result else 'Allowed'})")
        
        print("\n" + "=" * 40)
        if all_tests_passed:
            print("🎉 All tests PASSED! Old signals fix is working correctly.")
            print("✅ Signals older than 24 hours will be blocked")
            print("✅ Recent signals will be allowed through")
        else:
            print("❌ Some tests FAILED! Check the logic.")
        
        return all_tests_passed
        
    except Exception as e:
        print(f"❌ Error testing old signals fix: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if hasattr(db_manager, 'pool') and db_manager.pool:
            await db_manager.pool.close()

async def test_new_timeframe_scenario():
    """Simulate what happens when a new timeframe is added"""
    print("\n🎬 Simulating New Timeframe Addition Scenario")
    print("=" * 50)
    
    print("Scenario: You just added '3h' timeframe to your bot")
    print("The API returns historical 3h signals from the past week...")
    print()
    
    # Simulate historical signals that might be returned
    historical_signals = [
        {'date': (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d %H:%M:%S'), 'type': 'WT Buy Signal'},
        {'date': (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S'), 'type': 'RSI3M3 Bullish Entry'},
        {'date': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'), 'type': 'Bullish Divergence'},
        {'date': (datetime.now() - timedelta(hours=12)).strftime('%Y-%m-%d %H:%M:%S'), 'type': 'Fast Money Buy'},
        {'date': (datetime.now() - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S'), 'type': 'WT Gold Buy Signal'},
    ]
    
    print("Historical signals found:")
    blocked_count = 0
    allowed_count = 0
    
    for i, signal in enumerate(historical_signals, 1):
        signal_datetime = datetime.strptime(signal['date'], '%Y-%m-%d %H:%M:%S')
        age_hours = (datetime.now() - signal_datetime).total_seconds() / 3600
        
        # Test if this signal would be blocked
        is_blocked = await db_manager.check_duplicate_notification(
            ticker="AAPL",
            timeframe="3h",
            signal_type=signal['type'],
            signal_date=signal['date']
        )
        
        if is_blocked:
            status = "🚫 BLOCKED"
            blocked_count += 1
        else:
            status = "✅ ALLOWED"
            allowed_count += 1
        
        print(f"  {i}. {signal['type']} ({age_hours:.1f}h ago) - {status}")
    
    print(f"\nResult: {blocked_count} old signals blocked, {allowed_count} recent signals allowed")
    
    if blocked_count >= 3 and allowed_count <= 2:
        print("🎉 SUCCESS: Old signals are properly blocked!")
        print("💡 Only recent signals (last 24h) would be sent to Discord")
    else:
        print("⚠️ WARNING: Fix may not be working as expected")

async def main():
    """Main test function"""
    print("🚀 Old Signals Fix Test")
    print("Testing the simple date check fix...")
    print()
    
    # Test 1: Basic functionality
    test1_passed = await test_old_signals_fix()
    
    # Test 2: New timeframe scenario
    await test_new_timeframe_scenario()
    
    print("\n" + "=" * 50)
    if test1_passed:
        print("✅ Fix is ready for deployment!")
        print("💡 The bot will now prevent old signals from being sent")
        print("📝 Only signals from the last 24 hours will be allowed")
    else:
        print("❌ Fix needs adjustment before deployment")

if __name__ == "__main__":
    asyncio.run(main()) 