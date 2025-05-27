#!/usr/bin/env python3
"""
Test script to examine the exact API response structure
"""

import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:5000')

def test_api_response(ticker='AAPL', timeframe='1d'):
    """Test API response and show exact structure"""
    print(f"🔍 Testing API response for {ticker} ({timeframe})")
    print(f"📡 API URL: {API_BASE_URL}/api/analyzer-b")
    
    try:
        # Call the API
        params = {
            'ticker': ticker,
            'timeframe': timeframe
        }
        response = requests.get(f"{API_BASE_URL}/api/analyzer-b", params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API call successful!")
            print(f"📊 Response status code: {response.status_code}")
            
            # Show top-level keys
            print(f"\n📋 Top-level keys in response:")
            top_level_keys = list(data.keys())
            for key in sorted(top_level_keys):
                print(f"  - {key}")
            
            # Show signals section in detail
            if 'signals' in data:
                signals = data['signals']
                print(f"\n🎯 Signals section:")
                print(f"  Keys: {list(signals.keys())}")
                for signal_type, signal_data in signals.items():
                    if isinstance(signal_data, list):
                        print(f"  - {signal_type}: {len(signal_data)} signals")
                        if signal_data:
                            print(f"    Latest: {signal_data[-3:] if len(signal_data) >= 3 else signal_data}")
                    else:
                        print(f"  - {signal_type}: {type(signal_data)} ({len(signal_data) if hasattr(signal_data, '__len__') else 'N/A'})")
            
            # Show RSI3M3 section in detail
            if 'rsi3m3' in data:
                rsi3m3 = data['rsi3m3']
                print(f"\n📈 RSI3M3 section:")
                print(f"  Keys: {list(rsi3m3.keys())}")
                if 'signals' in rsi3m3:
                    rsi_signals = rsi3m3['signals']
                    print(f"  RSI3M3 Signals:")
                    for signal_type, signal_data in rsi_signals.items():
                        if isinstance(signal_data, list):
                            print(f"    - {signal_type}: {len(signal_data)} signals")
                            if signal_data:
                                print(f"      Latest: {signal_data[-3:] if len(signal_data) >= 3 else signal_data}")
            
            # Show divergences section in detail
            if 'divergences' in data:
                divergences = data['divergences']
                print(f"\n↗️ Divergences section:")
                print(f"  Keys: {list(divergences.keys())}")
                for div_type, div_data in divergences.items():
                    if isinstance(div_data, list):
                        print(f"  - {div_type}: {len(div_data)} signals")
                        if div_data:
                            print(f"    Latest: {div_data[-3:] if len(div_data) >= 3 else div_data}")
            
            # Show patterns section in detail
            if 'patterns' in data:
                patterns = data['patterns']
                print(f"\n🔄 Patterns section:")
                print(f"  Keys: {list(patterns.keys())}")
                for pattern_type, pattern_data in patterns.items():
                    if isinstance(pattern_data, list):
                        print(f"  - {pattern_type}: {len(pattern_data)} signals")
                        if pattern_data:
                            print(f"    Latest: {pattern_data[-3:] if len(pattern_data) >= 3 else pattern_data}")
            
            # Show trend exhaust section in detail
            if 'trendExhaust' in data:
                trend_exhaust = data['trendExhaust']
                print(f"\n🔥 TrendExhaust section:")
                print(f"  Keys: {list(trend_exhaust.keys())}")
                if 'signals' in trend_exhaust:
                    te_signals = trend_exhaust['signals']
                    print(f"  TrendExhaust Signals:")
                    for signal_type, signal_data in te_signals.items():
                        if isinstance(signal_data, list):
                            print(f"    - {signal_type}: {len(signal_data)} signals")
                            if signal_data:
                                print(f"      Latest: {signal_data[-3:] if len(signal_data) >= 3 else signal_data}")
            
            # Show summary section if available
            if 'summary' in data:
                summary = data['summary']
                print(f"\n📊 Summary section:")
                signal_counts = {k: v for k, v in summary.items() if 'Signal' in k}
                for key, count in signal_counts.items():
                    print(f"  - {key}: {count}")
            
            # Count total signals across all sections
            total_signals = 0
            signal_sources = []
            
            if 'signals' in data:
                for signal_type, signal_data in data['signals'].items():
                    if isinstance(signal_data, list):
                        total_signals += len(signal_data)
                        if signal_data:
                            signal_sources.append(f"main.{signal_type}({len(signal_data)})")
            
            if 'rsi3m3' in data and 'signals' in data['rsi3m3']:
                for signal_type, signal_data in data['rsi3m3']['signals'].items():
                    if isinstance(signal_data, list):
                        total_signals += len(signal_data)
                        if signal_data:
                            signal_sources.append(f"rsi3m3.{signal_type}({len(signal_data)})")
            
            if 'divergences' in data:
                for div_type, div_data in data['divergences'].items():
                    if isinstance(div_data, list):
                        total_signals += len(div_data)
                        if div_data:
                            signal_sources.append(f"divergences.{div_type}({len(div_data)})")
            
            if 'patterns' in data:
                for pattern_type, pattern_data in data['patterns'].items():
                    if isinstance(pattern_data, list):
                        total_signals += len(pattern_data)
                        if pattern_data:
                            signal_sources.append(f"patterns.{pattern_type}({len(pattern_data)})")
            
            if 'trendExhaust' in data and 'signals' in data['trendExhaust']:
                for signal_type, signal_data in data['trendExhaust']['signals'].items():
                    if isinstance(signal_data, list):
                        total_signals += len(signal_data)
                        if signal_data:
                            signal_sources.append(f"trendExhaust.{signal_type}({len(signal_data)})")
            
            print(f"\n🎯 TOTAL SIGNALS FOUND: {total_signals}")
            print(f"📍 Signal sources: {', '.join(signal_sources)}")
            
            # Save full response to file for detailed inspection
            output_file = f"api_response_{ticker}_{timeframe}.json"
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            print(f"\n💾 Full response saved to: {output_file}")
            
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

if __name__ == "__main__":
    print("🧪 API Response Structure Test")
    print("=" * 50)
    
    # Test multiple tickers and timeframes
    test_cases = [
        ('AAPL', '1d'),
        ('TSLA', '1d'),
        ('AAPL', '1h'),
    ]
    
    for ticker, timeframe in test_cases:
        print(f"\n{'='*20} {ticker} ({timeframe}) {'='*20}")
        data = test_api_response(ticker, timeframe)
        print("-" * 60)
    
    print("\n✅ API structure analysis complete!")
    print("📁 Check the generated JSON files for full response details.") 