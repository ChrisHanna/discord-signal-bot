#!/usr/bin/env python3
"""
Test script to verify 1h timeframe filtering shows only recent signals (last 4 hours)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from signal_notifier import SignalNotifier
from datetime import datetime, timedelta
import json

class MockBot:
    def get_channel(self, channel_id):
        return None

def test_1h_filtering():
    """Test that 1h timeframe only shows signals from last 4 hours"""
    print("🧪 Testing 1h timeframe filtering (last 4 hours only)")
    print("=" * 60)
    
    # Create notifier
    notifier = SignalNotifier(MockBot())
    
    # Test tickers
    tickers = ['AAPL', 'TSLA']
    
    for ticker in tickers:
        print(f"\n📊 Testing {ticker} (1h)")
        print("-" * 40)
        
        # Get signals for 1h timeframe
        signals = notifier.check_for_new_signals(ticker, '1h')
        
        if not signals:
            print(f"❌ No recent signals found for {ticker} (1h)")
            continue
        
        print(f"✅ Found {len(signals)} recent signals for {ticker} (1h)")
        
        # Check each signal's timestamp
        current_time = datetime.now()
        valid_signals = 0
        
        for i, signal in enumerate(signals[:5]):  # Show first 5 signals
            signal_date = signal.get('date', '')
            signal_type = signal.get('type', 'Unknown')
            
            if signal_date:
                try:
                    if ' ' in signal_date:
                        # Full timestamp
                        signal_time = datetime.strptime(signal_date, '%Y-%m-%d %H:%M:%S')
                        time_diff = current_time - signal_time
                        hours_ago = time_diff.total_seconds() / 3600
                        
                        if hours_ago <= 4:
                            valid_signals += 1
                            print(f"  ✅ {signal_type} - {signal_date} ({hours_ago:.1f}h ago)")
                        else:
                            print(f"  ❌ {signal_type} - {signal_date} ({hours_ago:.1f}h ago) - TOO OLD!")
                    else:
                        # Date only - check if it's today
                        signal_time = datetime.strptime(signal_date, '%Y-%m-%d')
                        if signal_time.date() == current_time.date():
                            valid_signals += 1
                            print(f"  ✅ {signal_type} - {signal_date} (Today)")
                        else:
                            days_ago = (current_time.date() - signal_time.date()).days
                            print(f"  ❌ {signal_type} - {signal_date} ({days_ago} days ago) - TOO OLD!")
                            
                except ValueError as e:
                    print(f"  ⚠️ Error parsing date '{signal_date}': {e}")
            else:
                print(f"  ⚠️ No date found for signal: {signal_type}")
        
        print(f"\n📈 Summary for {ticker} (1h):")
        print(f"   Total signals found: {len(signals)}")
        print(f"   Valid signals (≤4h): {valid_signals}")
        
        # Test notification filtering
        notify_count = 0
        for signal in signals:
            if notifier.should_notify(signal, ticker, '1h'):
                notify_count += 1
        
        print(f"   Notification-worthy: {notify_count}")

def test_comparison_with_1d():
    """Compare 1h vs 1d filtering to show the difference"""
    print("\n\n🔄 Comparison: 1h vs 1d filtering")
    print("=" * 60)
    
    notifier = SignalNotifier(MockBot())
    ticker = 'AAPL'
    
    # Get 1h signals
    signals_1h = notifier.check_for_new_signals(ticker, '1h')
    
    # Get 1d signals  
    signals_1d = notifier.check_for_new_signals(ticker, '1d')
    
    print(f"📊 {ticker} Signal Count Comparison:")
    print(f"   1h timeframe (last 4 hours): {len(signals_1h)} signals")
    print(f"   1d timeframe (last 7 days):  {len(signals_1d)} signals")
    
    if signals_1h:
        print(f"\n🕐 Recent 1h signals:")
        for signal in signals_1h[:3]:
            date = signal.get('date', 'No date')
            signal_type = signal.get('type', 'Unknown')
            print(f"   • {signal_type} - {date}")
    
    if signals_1d:
        print(f"\n📅 Recent 1d signals:")
        for signal in signals_1d[:3]:
            date = signal.get('date', 'No date')
            signal_type = signal.get('type', 'Unknown')
            print(f"   • {signal_type} - {date}")

if __name__ == "__main__":
    print("🚀 Starting 1h Timeframe Filtering Test")
    print("Testing that 1h signals only show last 4 hours...")
    print()
    
    test_1h_filtering()
    test_comparison_with_1d()
    
    print("\n" + "=" * 60)
    print("✅ 1h Filtering Test Complete!")
    print("The bot should now only show signals from the last 4 hours for 1h timeframe.") 