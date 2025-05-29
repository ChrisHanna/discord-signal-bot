#!/usr/bin/env python3
"""
API Pricing Data Inspector
Test script to analyze the response structure from /api/analyzer-b
"""

import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:5000')

def inspect_api_response(ticker: str = "AAPL", timeframe: str = "1d", period: str = "1mo"):
    """Inspect API response structure for pricing data"""
    
    print(f"🔍 Testing API call for {ticker} ({timeframe})")
    print(f"📡 API URL: {API_BASE_URL}/api/analyzer-b")
    print(f"⚙️ Parameters: ticker={ticker}, interval={timeframe}, period={period}")
    print("-" * 60)
    
    try:
        # Make API call
        params = {
            'ticker': ticker,
            'interval': timeframe,
            'period': period
        }
        
        print("📞 Making API call...")
        response = requests.get(f"{API_BASE_URL}/api/analyzer-b", params=params, timeout=30)
        
        print(f"📊 Response Status: {response.status_code}")
        print(f"📦 Response Size: {len(response.content)} bytes")
        
        if response.status_code == 200:
            data = response.json()
            
            # Main structure analysis
            print("\n🗝️ MAIN RESPONSE KEYS:")
            print("-" * 30)
            if isinstance(data, dict):
                for key in data.keys():
                    value = data[key]
                    value_type = type(value).__name__
                    
                    if isinstance(value, list):
                        print(f"  {key}: {value_type} (length: {len(value)})")
                        if len(value) > 0:
                            first_item_type = type(value[0]).__name__
                            print(f"    └─ Items: {first_item_type}")
                            if isinstance(value[0], dict):
                                item_keys = list(value[0].keys())[:5]
                                print(f"    └─ Sample keys: {item_keys}")
                    elif isinstance(value, dict):
                        print(f"  {key}: {value_type} (keys: {len(value)})")
                        sub_keys = list(value.keys())[:5]
                        print(f"    └─ Sub-keys: {sub_keys}")
                    else:
                        print(f"  {key}: {value_type}")
            
            # Look for potential pricing data
            print("\n💰 POTENTIAL PRICING DATA:")
            print("-" * 35)
            
            pricing_candidates = find_pricing_candidates(data)
            
            if pricing_candidates:
                for i, candidate in enumerate(pricing_candidates, 1):
                    print(f"\n{i}. Key: '{candidate['key']}'")
                    print(f"   Count: {candidate['count']} items")
                    print(f"   Sample keys: {candidate['sample_keys']}")
                    
                    # Show sample data
                    sample_data = data[candidate['key']][:2]
                    print(f"   Sample data:")
                    for j, item in enumerate(sample_data):
                        print(f"     [{j}]: {json.dumps(item, indent=6)}")
            else:
                print("   ❌ No obvious pricing data found")
            
            # Full response dump (truncated)
            print("\n📄 FULL RESPONSE SAMPLE:")
            print("-" * 30)
            full_json = json.dumps(data, indent=2)
            if len(full_json) > 2000:
                print(full_json[:2000] + "\n... (truncated)")
            else:
                print(full_json)
            
            # Save full response to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"api_response_{ticker}_{timeframe}_{timestamp}.json"
            
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"\n💾 Full response saved to: {filename}")
            
        else:
            print(f"❌ API Error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection Error: {e}")
    except json.JSONDecodeError as e:
        print(f"❌ JSON Parse Error: {e}")
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")

def find_pricing_candidates(data):
    """Find potential pricing data in the response"""
    candidates = []
    
    if not isinstance(data, dict):
        return candidates
    
    price_indicators = [
        'price', 'close', 'open', 'high', 'low', 'volume', 
        'timestamp', 'date', 'time', 'datetime', 'ohlc', 'candle'
    ]
    
    for key, value in data.items():
        if isinstance(value, list) and len(value) > 0:
            first_item = value[0]
            if isinstance(first_item, dict):
                item_keys = list(first_item.keys())
                item_keys_str = ' '.join(item_keys).lower()
                
                # Check if it looks like pricing data
                if any(indicator in item_keys_str for indicator in price_indicators):
                    candidates.append({
                        'key': key,
                        'count': len(value),
                        'sample_keys': item_keys[:8]  # Show more keys
                    })
    
    return candidates

def test_multiple_scenarios():
    """Test multiple ticker/timeframe combinations"""
    scenarios = [
        ("AAPL", "1d", "1mo"),
        ("AAPL", "1h", "1wk"),
        ("TSLA", "1d", "1mo"),
        ("SPY", "1h", "1wk")
    ]
    
    print("🧪 TESTING MULTIPLE SCENARIOS")
    print("=" * 50)
    
    for ticker, timeframe, period in scenarios:
        print(f"\n📊 Testing: {ticker} {timeframe} (period: {period})")
        try:
            inspect_api_response(ticker, timeframe, period)
            print("\n" + "="*50)
        except Exception as e:
            print(f"❌ Failed: {e}")
            continue

if __name__ == "__main__":
    print("🔬 API Pricing Data Inspector")
    print("=" * 40)
    
    # Test single scenario first
    print("1️⃣ Single Test:")
    inspect_api_response("AAPL", "1d", "1mo")
    
    # Ask if user wants to test multiple
    print("\n" + "="*50)
    test_more = input("🤔 Test multiple scenarios? (y/N): ").lower().strip()
    
    if test_more in ['y', 'yes']:
        test_multiple_scenarios()
    
    print("\n✅ Testing complete!")
    print("💡 Check the generated JSON files for full response data") 