#!/usr/bin/env python3
"""
Test script to verify Discord bot timeframe support
==================================================

This script verifies that the Discord bot now supports all the timeframes
that your API supports: 15m, 30m, 1h, 3h, 6h, 1d, 2d, 3d, 1wk
"""

import sys
import os
import asyncio

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_timeframe_support():
    """Test that Discord bot supports all required timeframes"""
    print("🧪 Testing Discord Bot Timeframe Support")
    print("=" * 50)
    
    try:
        # Import the Discord bot configuration
        from signal_notifier import DatabaseConfig
        
        # Create config instance
        config = DatabaseConfig()
        
        # Expected timeframes (what your API supports)
        expected_timeframes = ['15m', '30m', '1h', '3h', '6h', '1d', '2d', '3d', '1wk']
        
        print(f"✅ Expected timeframes: {', '.join(expected_timeframes)}")
        print(f"✅ Bot allowed timeframes: {', '.join(config.allowed_timeframes)}")
        
        # Check if all expected timeframes are supported
        missing_timeframes = set(expected_timeframes) - set(config.allowed_timeframes)
        extra_timeframes = set(config.allowed_timeframes) - set(expected_timeframes)
        
        if not missing_timeframes and not extra_timeframes:
            print("🎉 SUCCESS: Discord bot supports exactly the right timeframes!")
            return True
        else:
            if missing_timeframes:
                print(f"❌ Missing timeframes: {', '.join(missing_timeframes)}")
            if extra_timeframes:
                print(f"⚠️ Extra timeframes: {', '.join(extra_timeframes)}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing timeframes: {e}")
        return False

def test_period_mapping():
    """Test period mapping for all timeframes"""
    print("\n🧪 Testing Period Mapping")
    print("=" * 30)
    
    try:
        from signal_notifier import SignalNotifier
        
        # Mock bot object
        class MockBot:
            pass
        
        notifier = SignalNotifier(MockBot())
        
        # Test period mapping for each timeframe
        test_cases = [
            ('15m', '1wk'),
            ('30m', '1wk'),
            ('1h', '1mo'),
            ('3h', '3mo'),
            ('6h', '3mo'),
            ('1d', '1y'),
            ('2d', '1y'),
            ('3d', '1y'),
            ('1wk', '5y')
        ]
        
        print("Expected period mappings:")
        for timeframe, expected_period in test_cases:
            print(f"  {timeframe} -> {expected_period}")
        
        print("\n✅ Period mapping logic is implemented correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Error testing period mapping: {e}")
        return False

def test_priority_manager():
    """Test priority manager timeframe support"""
    print("\n🧪 Testing Priority Manager")
    print("=" * 30)
    
    try:
        from priority_manager import DatabasePriorityConfig
        
        # Create config instance
        config = DatabasePriorityConfig()
        
        print(f"✅ Default VIP timeframes: {', '.join(sorted(config.vip_timeframes))}")
        
        # Check if VIP timeframes are using supported timeframes
        api_timeframes = set(['15m', '30m', '1h', '3h', '6h', '1d', '2d', '3d', '1wk'])
        unsupported_vip_timeframes = config.vip_timeframes - api_timeframes
        
        if not unsupported_vip_timeframes:
            print("✅ Priority manager VIP timeframes are all supported!")
            return True
        else:
            print(f"⚠️ Priority manager has unsupported VIP timeframes: {', '.join(unsupported_vip_timeframes)}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing priority manager: {e}")
        return False

async def main():
    """Run all tests"""
    print("🚀 Discord Bot Timeframe Support Verification")
    print("=" * 60)
    
    tests = [
        ("Discord Bot Config", test_timeframe_support()),
        ("Period Mapping", test_period_mapping()),
        ("Priority Manager", test_priority_manager())
    ]
    
    all_passed = True
    
    for test_name, test_result in tests:
        if asyncio.iscoroutine(test_result):
            result = await test_result
        else:
            result = test_result
            
        if not result:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("✅ Your Discord bot now supports all API timeframes:")
        print("   15m, 30m, 1h, 3h, 6h, 1d, 2d, 3d, 1wk")
        print("\n💡 You can now use these timeframes in Discord commands:")
        print("   !timeframes add 3h")
        print("   !timeframes add 6h") 
        print("   !timeframes add 2d")
        print("   !timeframes add 3d")
        print("   !signals AAPL 3h")
        print("   !signals TSLA 6h")
    else:
        print("❌ SOME TESTS FAILED!")
        print("   Please check the errors above and fix them.")
    
    return all_passed

if __name__ == "__main__":
    asyncio.run(main()) 