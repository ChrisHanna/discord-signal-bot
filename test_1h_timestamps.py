#!/usr/bin/env python3
"""
Comprehensive test for 1h timeframe data and timestamp handling
"""

import requests
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from signal_notifier import SignalNotifier

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:5000')

class MockBot:
    def __init__(self):
        self.user = None
    
    def get_channel(self, channel_id):
        return None

def test_1h_api_response(ticker='AAPL'):
    """Test 1h API response and examine timestamp format"""
    print(f"🕐 Testing 1h API response for {ticker}")
    print(f"📡 API URL: {API_BASE_URL}/api/analyzer-b")
    
    try:
        # Call the API for 1h timeframe
        params = {
            'ticker': ticker,
            'interval': '1h',
            'period': '3mo'
        }
        response = requests.get(f"{API_BASE_URL}/api/analyzer-b", params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API call successful!")
            
            # Check dates array format for 1h
            dates = data.get('dates', [])
            print(f"\n📅 Dates array (first 10 entries):")
            for i, date in enumerate(dates[:10]):
                print(f"  [{i}] {date}")
            
            if dates:
                first_date = dates[0]
                last_date = dates[-1]
                print(f"\n⏰ Date range:")
                print(f"  First: {first_date}")
                print(f"  Last: {last_date}")
                print(f"  Total periods: {len(dates)}")
                
                # Check if dates include time information
                if ' ' in first_date:
                    print(f"  ✅ Timestamps include time information")
                    try:
                        parsed_first = datetime.strptime(first_date, '%Y-%m-%d %H:%M:%S')
                        parsed_last = datetime.strptime(last_date, '%Y-%m-%d %H:%M:%S')
                        duration = parsed_last - parsed_first
                        print(f"  Duration: {duration}")
                        print(f"  Hours covered: {duration.total_seconds() / 3600:.1f}")
                    except ValueError as e:
                        print(f"  ⚠️ Date parsing error: {e}")
                else:
                    print(f"  ⚠️ Timestamps are date-only (no time info)")
            
            # Examine signals with timestamp details
            print(f"\n🎯 Signal Analysis for 1h timeframe:")
            
            # Main signals
            signals_section = data.get('signals', {})
            for signal_type, signal_data in signals_section.items():
                if isinstance(signal_data, list) and signal_data:
                    print(f"\n  📊 {signal_type} signals ({len(signal_data)}):")
                    for signal in signal_data:
                        if isinstance(signal, dict):
                            # Complex signal (like cross)
                            signal_date = signal.get('date', 'N/A')
                            print(f"    • Date: {signal_date}")
                            if 'value' in signal:
                                print(f"      Value: {signal['value']}")
                            if 'isRed' in signal:
                                print(f"      Direction: {'Bearish' if signal['isRed'] else 'Bullish'}")
                        else:
                            # Simple date string
                            print(f"    • Date: {signal}")
            
            # RSI3M3 signals
            rsi3m3_section = data.get('rsi3m3', {})
            rsi3m3_signals = rsi3m3_section.get('signals', {})
            if rsi3m3_signals:
                print(f"\n  📈 RSI3M3 signals:")
                for signal_type, signal_data in rsi3m3_signals.items():
                    if isinstance(signal_data, list) and signal_data:
                        print(f"    {signal_type}: {signal_data}")
            
            # Patterns
            patterns_section = data.get('patterns', {})
            if patterns_section:
                print(f"\n  🔄 Pattern signals:")
                for pattern_type, pattern_data in patterns_section.items():
                    if isinstance(pattern_data, list) and pattern_data:
                        print(f"    {pattern_type}: {pattern_data}")
            
            return data
            
        else:
            print(f"❌ API returned status {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Error calling API: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON response: {e}")
        return None

def test_1h_signal_processing():
    """Test signal processing specifically for 1h timeframe"""
    print(f"\n🔍 Testing 1h Signal Processing")
    print("=" * 40)
    
    mock_bot = MockBot()
    notifier = SignalNotifier(mock_bot)
    
    # Test multiple tickers for 1h
    test_tickers = ['AAPL', 'TSLA', 'NVDA', 'SPY', 'BTC-USD']
    
    for ticker in test_tickers:
        print(f"\n📊 Testing {ticker} (1h):")
        print("-" * 25)
        
        try:
            # Fetch signals
            signals = notifier.fetch_signal_timeline(ticker, '1h')
            
            if signals:
                print(f"  ✅ Found {len(signals)} total signals")
                
                # Analyze timestamps
                recent_signals = []
                old_signals = []
                today = datetime.now().date()
                
                for signal in signals:
                    signal_date = signal.get('date', '')
                    days_since = signal.get('daysSince', 999)
                    
                    # Check timestamp format
                    timestamp_info = ""
                    if ' ' in signal_date:
                        timestamp_info = " (with time)"
                        try:
                            parsed_date = datetime.strptime(signal_date, '%Y-%m-%d %H:%M:%S')
                            if parsed_date.date() == today:
                                timestamp_info += " TODAY"
                        except:
                            pass
                    else:
                        timestamp_info = " (date only)"
                    
                    if days_since <= 1:  # Recent (today or yesterday)
                        recent_signals.append(signal)
                        print(f"    🔥 {signal['type']} - {signal_date}{timestamp_info}")
                    elif days_since <= 7:  # This week
                        print(f"    📅 {signal['type']} - {signal_date}{timestamp_info}")
                    else:
                        old_signals.append(signal)
                
                print(f"  📈 Recent signals (≤1 day): {len(recent_signals)}")
                print(f"  📊 This week (≤7 days): {len(signals) - len(old_signals)}")
                print(f"  🗃️ Older signals: {len(old_signals)}")
                
                # Test notification logic for 1h
                notify_signals = [s for s in recent_signals if notifier.should_notify(s, ticker, '1h')]
                print(f"  🚨 Would notify: {len(notify_signals)}")
                
                if notify_signals:
                    for signal in notify_signals[:3]:  # Show first 3
                        print(f"    → {signal['type']} ({signal['strength']})")
                
            else:
                print(f"  ❌ No signals found")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")

def test_1h_vs_1d_comparison():
    """Compare 1h vs 1d data for the same ticker"""
    print(f"\n⚖️ 1h vs 1d Comparison")
    print("=" * 25)
    
    mock_bot = MockBot()
    notifier = SignalNotifier(mock_bot)
    
    ticker = 'AAPL'
    
    try:
        # Get 1d signals
        signals_1d = notifier.fetch_signal_timeline(ticker, '1d')
        print(f"📅 {ticker} (1d): {len(signals_1d) if signals_1d else 0} signals")
        
        if signals_1d:
            for signal in signals_1d[:3]:
                print(f"  • {signal['type']} - {signal['date']} ({signal['daysSince']} days ago)")
        
        # Get 1h signals
        signals_1h = notifier.fetch_signal_timeline(ticker, '1h')
        print(f"\n🕐 {ticker} (1h): {len(signals_1h) if signals_1h else 0} signals")
        
        if signals_1h:
            for signal in signals_1h[:3]:
                date_info = signal['date']
                if ' ' in date_info:
                    date_info += " (with time)"
                print(f"  • {signal['type']} - {date_info} ({signal['daysSince']} days ago)")
        
        # Compare signal counts by system
        if signals_1d and signals_1h:
            print(f"\n📊 Signal Comparison by System:")
            
            def count_by_system(signals):
                counts = {}
                for signal in signals:
                    system = signal['system']
                    counts[system] = counts.get(system, 0) + 1
                return counts
            
            counts_1d = count_by_system(signals_1d)
            counts_1h = count_by_system(signals_1h)
            
            all_systems = set(counts_1d.keys()) | set(counts_1h.keys())
            
            for system in sorted(all_systems):
                count_1d = counts_1d.get(system, 0)
                count_1h = counts_1h.get(system, 0)
                print(f"  {system}: 1d={count_1d}, 1h={count_1h}")
                
                if count_1d != count_1h:
                    print(f"    ⚠️ Different signal counts!")
        
    except Exception as e:
        print(f"❌ Error in comparison: {e}")

def test_timestamp_calculation():
    """Test timestamp calculation accuracy for 1h data"""
    print(f"\n⏱️ Timestamp Calculation Test")
    print("=" * 30)
    
    mock_bot = MockBot()
    notifier = SignalNotifier(mock_bot)
    
    # Test with known timestamps
    test_timestamps = [
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  # Now
        (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'),  # 1 hour ago
        (datetime.now() - timedelta(hours=6)).strftime('%Y-%m-%d %H:%M:%S'),  # 6 hours ago
        (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'),   # 1 day ago
        (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d'),            # 2 days ago (date only)
    ]
    
    print("Testing timestamp parsing:")
    
    for timestamp in test_timestamps:
        # Test the calculation function
        current_date = datetime.now()
        
        try:
            if ' ' in timestamp:
                parsed_date = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            else:
                parsed_date = datetime.strptime(timestamp, '%Y-%m-%d')
            
            days_since = (current_date - parsed_date).days
            hours_since = (current_date - parsed_date).total_seconds() / 3600
            
            print(f"  📅 {timestamp}")
            print(f"    Days since: {days_since}")
            print(f"    Hours since: {hours_since:.1f}h")
            print(f"    Would be considered recent (≤1 day): {'YES' if days_since <= 1 else 'NO'}")
            print()
            
        except ValueError as e:
            print(f"  ❌ Error parsing {timestamp}: {e}")

if __name__ == "__main__":
    print("🕐 Comprehensive 1h Timeframe Testing")
    print("=" * 50)
    
    # Test 1: Raw API response analysis
    print("\n" + "="*20 + " RAW API ANALYSIS " + "="*20)
    for ticker in ['AAPL', 'TSLA']:
        data = test_1h_api_response(ticker)
        if data:
            # Save the raw response for inspection
            output_file = f"1h_analysis_{ticker}.json"
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            print(f"📁 Saved to: {output_file}")
        print("-" * 60)
    
    # Test 2: Signal processing
    test_1h_signal_processing()
    
    # Test 3: 1h vs 1d comparison
    test_1h_vs_1d_comparison()
    
    # Test 4: Timestamp calculation accuracy
    test_timestamp_calculation()
    
    print("\n✅ 1h timeframe testing complete!")
    print("📁 Check the generated 1h_analysis_*.json files for detailed inspection.") 