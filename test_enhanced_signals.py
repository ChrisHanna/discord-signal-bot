#!/usr/bin/env python3
"""
Test script for enhanced signal detection using actual API data
"""

import requests
import json
import os
from dotenv import load_dotenv
from signal_notifier import SignalNotifier
import discord

# Load environment variables
load_dotenv()

# Mock Discord bot for testing
class MockBot:
    def __init__(self):
        self.user = None
    
    def get_channel(self, channel_id):
        return None

def test_signal_processing():
    """Test signal processing with actual API data"""
    print("🧪 Testing Enhanced Signal Detection")
    print("=" * 50)
    
    # Create mock bot and notifier
    mock_bot = MockBot()
    notifier = SignalNotifier(mock_bot)
    
    # Test cases
    test_cases = [
        ('AAPL', '1d'),
        ('TSLA', '1d'),
        ('AAPL', '1h'),
    ]
    
    for ticker, timeframe in test_cases:
        print(f"\n🔍 Testing {ticker} ({timeframe})")
        print("-" * 30)
        
        try:
            # Fetch signals using our enhanced detection
            signals = notifier.fetch_signal_timeline(ticker, timeframe)
            
            if signals:
                print(f"✅ Found {len(signals)} total signals")
                
                # Group by system
                by_system = {}
                for signal in signals:
                    system = signal['system']
                    if system not in by_system:
                        by_system[system] = []
                    by_system[system].append(signal)
                
                # Show breakdown
                for system, system_signals in by_system.items():
                    print(f"  📊 {system}: {len(system_signals)} signals")
                    for signal in system_signals[:3]:  # Show first 3
                        days_since = signal.get('daysSince', 0)
                        print(f"    • {signal['type']} - {days_since} days ago ({signal['date']})")
                
                # Test notification filtering
                recent_signals = notifier.check_for_new_signals(ticker, timeframe)
                notify_signals = [s for s in recent_signals if notifier.should_notify(s, ticker, timeframe)]
                
                print(f"  🔔 Recent signals (≤7 days): {len(recent_signals)}")
                print(f"  🚨 Would notify: {len(notify_signals)}")
                
                if notify_signals:
                    print("    Notification-worthy signals:")
                    for signal in notify_signals:
                        print(f"    → {signal['type']} ({signal['strength']}) - {signal['daysSince']} days ago")
                
            else:
                print("❌ No signals found")
                
        except Exception as e:
            print(f"❌ Error testing {ticker} ({timeframe}): {e}")
    
    print(f"\n✅ Enhanced signal detection test complete!")

def test_signal_formatting():
    """Test Discord message formatting"""
    print("\n🎨 Testing Signal Formatting")
    print("=" * 30)
    
    mock_bot = MockBot()
    notifier = SignalNotifier(mock_bot)
    
    # Test signal examples
    test_signals = [
        {
            'date': '2025-05-16',
            'type': 'WT Gold Buy Signal',
            'system': 'Wave Trend',
            'strength': 'Very Strong',
            'daysSince': 0,
            'timeframe': '1d',
            'color': '#FFD700'
        },
        {
            'date': '2025-05-15',
            'type': 'RSI3M3 Bullish Entry',
            'system': 'RSI3M3+',
            'strength': 'Strong',
            'daysSince': 1,
            'timeframe': '1h',
            'color': '#00ff0a'
        },
        {
            'date': '2025-05-10',
            'type': 'Bullish Divergence',
            'system': 'Divergence',
            'strength': 'Strong',
            'daysSince': 6,
            'timeframe': '1d',
            'color': '#32CD32'
        }
    ]
    
    for i, signal in enumerate(test_signals, 1):
        print(f"\n📝 Example {i}:")
        formatted = notifier.format_signal_for_discord(signal, 'AAPL', signal['timeframe'])
        print(formatted)
        
        should_notify = notifier.should_notify(signal, 'AAPL', signal['timeframe'])
        print(f"   🔔 Would notify: {'YES' if should_notify else 'NO'}")

if __name__ == "__main__":
    test_signal_processing()
    test_signal_formatting() 