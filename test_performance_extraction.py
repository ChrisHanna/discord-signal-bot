#!/usr/bin/env python3
"""
Test Performance Extraction
Verify that the auto-performance tracking functions work with real API data
"""

import json
import sys
from datetime import datetime, timedelta
from signal_notifier import SignalNotifier
import asyncio
import os

def test_performance_extraction():
    """Test the performance extraction with saved API data"""
    
    print("🧪 Testing Performance Extraction")
    print("=" * 50)
    
    # Load the saved API response
    try:
        with open('api_response_AAPL_1d_20250528_233724.json', 'r') as f:
            api_data = json.load(f)
        print("✅ Loaded saved API response")
    except FileNotFoundError:
        print("❌ API response file not found. Run test_api_pricing.py first.")
        return
    
    # Create SignalNotifier instance
    notifier = SignalNotifier(None)  # No bot needed for testing
    
    # Test 1: Extract pricing data
    print("\n1️⃣ Testing pricing data extraction...")
    pricing_data = notifier.extract_pricing_data_from_api(api_data)
    
    if pricing_data:
        print(f"✅ Extracted {len(pricing_data)} price points")
        print(f"Sample data point: {pricing_data[0]}")
        
        # Show first few prices with dates
        print("\n📊 First 5 price points:")
        for i, point in enumerate(pricing_data[:5]):
            if 't' in point and 'c' in point:
                print(f"  {i+1}. {point['t']}: ${point['c']:.2f}")
            elif 'date' in point and 'close' in point:
                print(f"  {i+1}. {point['date']}: ${point['close']:.2f}")
        
    else:
        print("❌ No pricing data extracted")
        return
    
    # Test 2: Find closest price
    print("\n2️⃣ Testing closest price finding...")
    
    # Create test datetime (using a date from the API response)
    test_signals = [
        datetime(2025, 5, 28, 16, 0, 0),  # Market close on last day
        datetime(2025, 5, 27, 16, 0, 0),  # Previous day
        datetime(2025, 5, 26, 16, 0, 0),  # Weekend (should find closest)
        datetime(2025, 5, 1, 16, 0, 0),   # Earlier in month
    ]
    
    for i, test_datetime in enumerate(test_signals, 1):
        print(f"\n  Test {i}: Signal at {test_datetime.strftime('%Y-%m-%d %H:%M')}")
        
        price = notifier.find_closest_price(test_datetime, pricing_data)
        if price:
            print(f"    ✅ Found price: ${price:.2f}")
        else:
            print(f"    ❌ No price found")
    
    # Test 3: Calculate performance for a sample signal
    print("\n3️⃣ Testing performance calculation...")
    
    # Use a signal from a few days ago
    signal_datetime = datetime(2025, 5, 20, 16, 0, 0)  # Assuming this date exists
    
    performance = notifier.calculate_performance_from_pricing(
        signal_datetime, pricing_data, '1d'
    )
    
    if performance:
        print(f"✅ Performance calculated for signal at {signal_datetime.strftime('%Y-%m-%d %H:%M')}")
        print(f"  Price at signal: ${performance.get('price_at_signal', 0):.2f}")
        print(f"  Price after 1h: ${performance.get('price_after_1h', 0) or 'N/A'}")
        print(f"  Price after 1d: ${performance.get('price_after_1d', 0) or 'N/A'}")
        print(f"  Price after 3d: ${performance.get('price_after_3d', 0) or 'N/A'}")
        
        # Calculate success example
        if performance.get('price_at_signal') and performance.get('price_after_1d'):
            signal_price = performance['price_at_signal']
            price_1d = performance['price_after_1d']
            change_pct = ((price_1d - signal_price) / signal_price) * 100
            
            print(f"\n  📈 1-day change: {change_pct:+.2f}%")
            print(f"  🎯 For a 'Buy' signal, this would be: {'✅ SUCCESS' if change_pct > 0 else '❌ FAILURE'}")
            print(f"  🎯 For a 'Sell' signal, this would be: {'✅ SUCCESS' if change_pct < 0 else '❌ FAILURE'}")
    else:
        print(f"❌ No performance calculated")
    
    # Test 4: Check data coverage
    print("\n4️⃣ Data coverage analysis...")
    
    if pricing_data:
        dates = []
        for point in pricing_data:
            if 't' in point:
                dates.append(point['t'])
            elif 'date' in point:
                dates.append(point['date'])
        
        if dates:
            print(f"  Date range: {min(dates)} to {max(dates)}")
            print(f"  Total days: {len(dates)}")
            
            # Check for gaps
            date_objects = [datetime.strptime(d, '%Y-%m-%d') for d in dates]
            date_objects.sort()
            
            gaps = []
            for i in range(1, len(date_objects)):
                diff = (date_objects[i] - date_objects[i-1]).days
                if diff > 3:  # More than weekend gap
                    gaps.append(f"{date_objects[i-1].strftime('%Y-%m-%d')} to {date_objects[i].strftime('%Y-%m-%d')} ({diff} days)")
            
            if gaps:
                print(f"  ⚠️ Data gaps found:")
                for gap in gaps:
                    print(f"    - {gap}")
            else:
                print(f"  ✅ No significant data gaps")

def test_with_multiple_files():
    """Test with all available API response files"""
    print("\n🔄 Testing with all API response files...")
    
    import glob
    api_files = glob.glob('api_response_*.json')
    
    if not api_files:
        print("❌ No API response files found")
        return
    
    for filename in api_files:
        print(f"\n📄 Testing {filename}...")
        try:
            with open(filename, 'r') as f:
                api_data = json.load(f)
            
            notifier = SignalNotifier(None)
            pricing_data = notifier.extract_pricing_data_from_api(api_data)
            
            if pricing_data:
                print(f"  ✅ {len(pricing_data)} price points extracted")
                
                # Test a price lookup
                if len(pricing_data) > 0:
                    sample_point = pricing_data[-1]  # Last data point
                    if 't' in sample_point:
                        test_date = datetime.strptime(sample_point['t'], '%Y-%m-%d')
                        price = notifier.find_closest_price(test_date, pricing_data)
                        print(f"  💰 Sample price on {sample_point['t']}: ${price:.2f}")
            else:
                print(f"  ❌ No pricing data extracted")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")

if __name__ == "__main__":
    print("🔬 Performance Extraction Test Suite")
    print("=" * 50)
    
    # Test with single file
    test_performance_extraction()
    
    # Test with all files
    test_with_multiple_files()
    
    print("\n✅ Testing complete!")
    print("💡 If all tests pass, the auto-performance tracking should work!") 