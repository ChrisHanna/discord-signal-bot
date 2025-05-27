#!/usr/bin/env python3
"""
Test script to verify signal detection is working
Run this to test the signal processing without Discord setup
"""

from signal_notifier import SignalNotifier
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_signal_detection():
    print("🧪 Testing Signal Detection System")
    print("=" * 50)
    
    # Set API URL (default to localhost)
    api_url = os.getenv('API_BASE_URL', 'http://localhost:5000')
    print(f"📡 API URL: {api_url}")
    
    # Test tickers
    test_tickers = ["AAPL", "TSLA", "NVDA", "SPY"]
    
    notifier = SignalNotifier()
    
    for ticker in test_tickers:
        print(f"\n🔍 Testing {ticker}...")
        print("-" * 30)
        
        try:
            signals = notifier.fetch_signal_timeline(ticker)
            
            if signals:
                print(f"✅ Found {len(signals)} signals for {ticker}")
                
                # Show first few signals
                for i, signal in enumerate(signals[:3]):
                    print(f"  {i+1}. {signal.get('system', 'Unknown')} - {signal.get('type', 'Unknown')}")
                    print(f"     📅 {signal.get('date', 'No date')[:10]} ({signal.get('daysSince', '?')} days ago)")
                    print(f"     💪 Strength: {signal.get('strength', 'Unknown')}")
                
                if len(signals) > 3:
                    print(f"  ... and {len(signals) - 3} more signals")
                    
            elif signals == []:
                print(f"ℹ️  No signals found for {ticker} (but API responded)")
            else:
                print(f"❌ Failed to fetch signals for {ticker}")
                
        except Exception as e:
            print(f"❌ Error testing {ticker}: {e}")
    
    print(f"\n🏁 Test completed!")
    print("\n💡 If this works, your Discord bot should work too!")
    print("   Set up your Discord token and channel ID in .env to start notifications")

if __name__ == "__main__":
    test_signal_detection() 