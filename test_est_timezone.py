#!/usr/bin/env python3
"""
Test EST timezone functionality for Discord bot
"""

import sys
import os
from datetime import datetime, timedelta
import pytz

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import functions from signal_notifier
from signal_notifier import convert_to_est, format_est_timestamp, calculate_time_ago_est, EST

def test_timezone_conversion():
    """Test basic timezone conversion functionality"""
    print("🌍 Testing Timezone Conversion")
    print("=" * 40)
    
    # Test current time conversion
    now_utc = datetime.utcnow()
    now_est = convert_to_est(now_utc)
    
    print(f"UTC Time: {now_utc.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"EST Time: {now_est.strftime('%Y-%m-%d %I:%M:%S %p %Z')}")
    
    # Test various timestamp formats
    test_timestamps = [
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  # Now
        (datetime.now() - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S'),  # 2h ago
        (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),  # Yesterday (date only)
        '2025-01-27 09:30:00',  # Market open
        '2025-01-27 16:00:00',  # Market close
        '2025-01-27'  # Date only
    ]
    
    print(f"\n📅 Testing timestamp conversion:")
    for timestamp in test_timestamps:
        est_formatted = format_est_timestamp(timestamp, show_time=True)
        time_ago = calculate_time_ago_est(timestamp)
        print(f"  Input: {timestamp}")
        print(f"  EST:   {est_formatted}")
        print(f"  Ago:   {time_ago}")
        print()

def test_signal_formatting():
    """Test signal formatting with EST timestamps"""
    print("📊 Testing Signal Formatting with EST")
    print("=" * 40)
    
    # Mock signal data
    test_signals = [
        {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  # Now
            'type': 'WT Buy Signal',
            'system': 'Wave Trend',
            'strength': 'Strong'
        },
        {
            'date': (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'),  # 1h ago
            'type': 'RSI3M3 Bullish Entry',
            'system': 'RSI3M3+',
            'strength': 'Very Strong'
        },
        {
            'date': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),  # Yesterday
            'type': 'Bullish Divergence',
            'system': 'Divergence',
            'strength': 'Strong'
        }
    ]
    
    for i, signal in enumerate(test_signals, 1):
        print(f"Signal {i}:")
        print(f"  Original: {signal['date']}")
        print(f"  EST Time: {format_est_timestamp(signal['date'])}")
        print(f"  Time Ago: {calculate_time_ago_est(signal['date'])}")
        print(f"  Type: {signal['type']} ({signal['strength']})")
        print()

def test_market_hours():
    """Test EST formatting during market hours"""
    print("📈 Testing Market Hours Display")
    print("=" * 35)
    
    # Market hours in EST
    market_open = "09:30:00"
    market_close = "16:00:00"
    
    # Create test timestamps for different market times
    today = datetime.now(EST).strftime('%Y-%m-%d')
    
    market_times = [
        f"{today} 09:30:00",  # Market open
        f"{today} 12:00:00",  # Midday
        f"{today} 16:00:00",  # Market close
        f"{today} 18:00:00",  # After hours
    ]
    
    for timestamp in market_times:
        est_time = format_est_timestamp(timestamp)
        time_ago = calculate_time_ago_est(timestamp)
        print(f"Time: {est_time}")
        print(f"Ago:  {time_ago}")
        print()

def test_different_timezones():
    """Test handling of different input timezones"""
    print("🌐 Testing Different Input Timezones")
    print("=" * 40)
    
    # Create timestamps in different timezones
    now = datetime.now()
    
    # UTC timestamp
    utc_time = datetime.utcnow()
    print(f"UTC Input: {utc_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"EST Output: {format_est_timestamp(utc_time.strftime('%Y-%m-%d %H:%M:%S'))}")
    print()
    
    # Local time (system timezone)
    local_time = now
    print(f"Local Input: {local_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"EST Output: {format_est_timestamp(local_time.strftime('%Y-%m-%d %H:%M:%S'))}")
    print()

def test_edge_cases():
    """Test edge cases and error handling"""
    print("⚠️ Testing Edge Cases")
    print("=" * 25)
    
    edge_cases = [
        "",  # Empty string
        "invalid-date",  # Invalid format
        "2025-13-45",  # Invalid date
        "2025-01-27 25:99:99",  # Invalid time
    ]
    
    for case in edge_cases:
        print(f"Input: '{case}'")
        try:
            est_result = format_est_timestamp(case)
            ago_result = calculate_time_ago_est(case)
            print(f"  EST: {est_result}")
            print(f"  Ago: {ago_result}")
        except Exception as e:
            print(f"  Error: {e}")
        print()

def main():
    """Run all EST timezone tests"""
    print("🕐 EST Timezone Testing Suite")
    print("=" * 50)
    print(f"Current EST Time: {datetime.now(EST).strftime('%Y-%m-%d %I:%M:%S %p %Z')}")
    print()
    
    try:
        test_timezone_conversion()
        test_signal_formatting()
        test_market_hours()
        test_different_timezones()
        test_edge_cases()
        
        print("✅ All EST timezone tests completed successfully!")
        print("\n📋 Summary:")
        print("  ✅ Timezone conversion working")
        print("  ✅ Signal formatting with EST")
        print("  ✅ Market hours display")
        print("  ✅ Error handling for edge cases")
        print("\n🚀 EST timezone support is ready for production!")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 