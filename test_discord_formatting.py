#!/usr/bin/env python3
"""
Test Discord bot message formatting with timestamps
"""

from signal_notifier import SignalNotifier
import json

class MockBot:
    def __init__(self):
        self.user = None
    
    def get_channel(self, channel_id):
        return None

def test_discord_formatting():
    """Test Discord message formatting with different timestamp formats"""
    print("🔍 Testing Discord Message Formatting")
    print("=" * 50)
    
    mock_bot = MockBot()
    notifier = SignalNotifier(mock_bot)
    
    # Test signals with different timestamp formats
    test_signals = [
        {
            'date': '2025-05-27 09:30:00',  # Full timestamp (1h data)
            'type': 'WT Buy Signal',
            'system': 'Wave Trend',
            'strength': 'Strong',
            'daysSince': 0,
            'timeframe': '1h',
            'color': '#00ff0a'
        },
        {
            'date': '2025-05-26 14:30:00',  # Full timestamp (1h data)
            'type': 'RSI3M3 Bullish Entry',
            'system': 'RSI3M3+',
            'strength': 'Very Strong',
            'daysSince': 1,
            'timeframe': '1h',
            'color': '#00ff0a'
        },
        {
            'date': '2025-05-23',  # Date only (1d data)
            'type': 'Zero Line Reject Sell',
            'system': 'Patterns',
            'strength': 'Strong',
            'daysSince': 4,
            'timeframe': '1d',
            'color': '#ff1100'
        }
    ]
    
    for i, signal in enumerate(test_signals, 1):
        ticker = 'AAPL'
        timeframe = signal['timeframe']
        
        print(f"\n📝 Example {i}: {signal['type']}")
        print("-" * 40)
        
        # Format the signal for Discord
        formatted_message = notifier.format_signal_for_discord(signal, ticker, timeframe)
        print(formatted_message)
        
        # Show what would be sent to Discord
        print(f"\n💬 Discord Notification Preview:")
        print(f"Title: 🚨 Signal Alert: {ticker} ({timeframe})")
        print(f"Description:")
        for line in formatted_message.split('\n'):
            print(f"  {line}")
        
        # Check if this signal would trigger a notification
        should_notify = notifier.should_notify(signal, ticker, timeframe)
        print(f"🔔 Would trigger notification: {'YES' if should_notify else 'NO'}")
        print()

def test_get_signals_formatting():
    """Test the !signals command formatting"""
    print("\n📊 Testing !signals Command Formatting")
    print("=" * 50)
    
    mock_bot = MockBot()
    notifier = SignalNotifier(mock_bot)
    
    # Simulate fetching signals for AAPL
    ticker = 'AAPL'
    print(f"🔍 Testing !signals {ticker} command formatting...")
    
    try:
        # Fetch real signals
        signals = notifier.fetch_signal_timeline(ticker, '1h')
        
        if signals:
            print(f"✅ Found {len(signals)} signals")
            
            # Show how the first 3 signals would be formatted in Discord
            recent_signals = signals[:3]
            
            print(f"\n💬 Discord Embed Fields Preview:")
            print(f"Title: 📊 Recent Signals for {ticker.upper()}")
            
            for i, signal in enumerate(recent_signals, 1):
                days_since = signal.get('daysSince', 0)
                timing = f"{days_since} day{'s' if days_since != 1 else ''} ago"
                
                # Format timestamp display (same logic as updated code)
                signal_date = signal.get('date', '')
                if ' ' in signal_date:
                    # Full timestamp with time
                    date_display = f"🕐 {signal_date}"
                else:
                    # Date only
                    date_display = f"📅 {signal_date}"
                
                field_name = f"{i}. {signal.get('type', 'Unknown')} ({signal.get('system', 'Unknown')})"
                field_value = f"⏰ {timing}\n{date_display}"
                
                print(f"\nField {i}:")
                print(f"  Name: {field_name}")
                print(f"  Value: {field_value}")
        else:
            print("❌ No signals found")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_discord_formatting()
    test_get_signals_formatting()
    print("\n✅ Discord formatting test complete!") 