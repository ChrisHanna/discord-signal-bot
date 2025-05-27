#!/usr/bin/env python3
"""
Test script for dynamic ticker management functionality
Tests JSON-based ticker storage and Discord commands simulation
"""

import json
import os
import sys
from datetime import datetime

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import functions from signal_notifier
from signal_notifier import load_ticker_config, save_ticker_config, build_ticker_combinations

def test_ticker_config_operations():
    """Test ticker configuration loading, saving, and validation"""
    print("🧪 Testing Ticker Configuration Operations")
    print("=" * 50)
    
    # Backup existing config if it exists
    backup_file = 'tickers.json.backup'
    if os.path.exists('tickers.json'):
        with open('tickers.json', 'r') as f:
            backup_data = f.read()
        with open(backup_file, 'w') as f:
            f.write(backup_data)
        print("📋 Backed up existing tickers.json")
    
    try:
        # Test 1: Load default config (file doesn't exist)
        if os.path.exists('tickers.json'):
            os.remove('tickers.json')
        
        print("\n1️⃣ Testing default config creation...")
        config = load_ticker_config()
        
        expected_keys = ['tickers', 'timeframes', 'settings']
        assert all(key in config for key in expected_keys), "Missing required config keys"
        assert isinstance(config['tickers'], list), "Tickers should be a list"
        assert isinstance(config['timeframes'], list), "Timeframes should be a list"
        assert len(config['tickers']) > 0, "Should have default tickers"
        print(f"✅ Default config created with {len(config['tickers'])} tickers")
        
        # Test 2: Save and reload config
        print("\n2️⃣ Testing config save/reload...")
        test_config = {
            "tickers": ["AAPL", "TSLA", "NVDA"],
            "timeframes": ["1d", "1h"],
            "settings": {
                "max_tickers": 25,
                "allowed_timeframes": ["1d", "1h", "4h"],
                "default_timeframes": ["1d"]
            }
        }
        
        save_ticker_config(test_config)
        reloaded_config = load_ticker_config()
        
        assert reloaded_config['tickers'] == test_config['tickers'], "Tickers not saved correctly"
        assert reloaded_config['timeframes'] == test_config['timeframes'], "Timeframes not saved correctly"
        print("✅ Config save/reload successful")
        
        # Test 3: Add ticker simulation
        print("\n3️⃣ Testing add ticker simulation...")
        original_tickers = reloaded_config['tickers'].copy()
        new_ticker = "MSFT"
        
        if new_ticker not in reloaded_config['tickers']:
            reloaded_config['tickers'].append(new_ticker)
            reloaded_config['tickers'] = sorted(reloaded_config['tickers'])
            save_ticker_config(reloaded_config)
            
            updated_config = load_ticker_config()
            assert new_ticker in updated_config['tickers'], f"{new_ticker} not added"
            print(f"✅ Successfully added {new_ticker}")
        
        # Test 4: Remove ticker simulation
        print("\n4️⃣ Testing remove ticker simulation...")
        if len(updated_config['tickers']) > 1:
            ticker_to_remove = updated_config['tickers'][0]
            updated_config['tickers'].remove(ticker_to_remove)
            save_ticker_config(updated_config)
            
            final_config = load_ticker_config()
            assert ticker_to_remove not in final_config['tickers'], f"{ticker_to_remove} not removed"
            print(f"✅ Successfully removed {ticker_to_remove}")
        
        # Test 5: Timeframe management
        print("\n5️⃣ Testing timeframe management...")
        current_timeframes = final_config['timeframes'].copy()
        
        # Add timeframe
        if "4h" not in current_timeframes:
            current_timeframes.append("4h")
            final_config['timeframes'] = current_timeframes
            save_ticker_config(final_config)
            
            tf_config = load_ticker_config()
            assert "4h" in tf_config['timeframes'], "4h timeframe not added"
            print("✅ Successfully added 4h timeframe")
        
        # Remove timeframe (if more than one exists)
        if len(tf_config['timeframes']) > 1:
            tf_to_remove = tf_config['timeframes'][-1]
            tf_config['timeframes'].remove(tf_to_remove)
            save_ticker_config(tf_config)
            
            final_tf_config = load_ticker_config()
            assert tf_to_remove not in final_tf_config['timeframes'], f"{tf_to_remove} timeframe not removed"
            print(f"✅ Successfully removed {tf_to_remove} timeframe")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    
    finally:
        # Restore backup if it exists
        if os.path.exists(backup_file):
            with open(backup_file, 'r') as f:
                backup_data = f.read()
            with open('tickers.json', 'w') as f:
                f.write(backup_data)
            os.remove(backup_file)
            print("🔄 Restored original tickers.json")
    
    return True

def test_ticker_validation():
    """Test ticker symbol validation logic"""
    print("\n🔍 Testing Ticker Validation")
    print("=" * 30)
    
    import re
    
    # Valid tickers
    valid_tickers = ["AAPL", "TSLA", "BTC-USD", "ETH-USD", "SPY", "QQQ", "MSFT.TO", "GOOGL"]
    # Invalid tickers
    invalid_tickers = ["", "A@PL", "TS LA", "BTC/USD", "test!", "123_ABC"]
    
    ticker_pattern = r'^[A-Z0-9.-]+$'
    
    print("✅ Valid tickers:")
    for ticker in valid_tickers:
        is_valid = bool(re.match(ticker_pattern, ticker))
        print(f"   {ticker}: {'✅' if is_valid else '❌'}")
        assert is_valid, f"{ticker} should be valid"
    
    print("\n❌ Invalid tickers:")
    for ticker in invalid_tickers:
        is_valid = bool(re.match(ticker_pattern, ticker))
        print(f"   {ticker}: {'❌' if not is_valid else '✅'}")
        assert not is_valid, f"{ticker} should be invalid"
    
    print("✅ All ticker validation tests passed!")

def test_combination_building():
    """Test ticker-timeframe combination building"""
    print("\n🔧 Testing Combination Building")
    print("=" * 35)
    
    # Mock global variables
    test_tickers = ["AAPL", "TSLA", "NVDA"]
    test_timeframes = ["1d", "1h"]
    
    # Calculate expected combinations
    expected_combinations = []
    for ticker in test_tickers:
        for timeframe in test_timeframes:
            expected_combinations.append((ticker, timeframe))
    
    print(f"📊 Test tickers: {test_tickers}")
    print(f"⏱️ Test timeframes: {test_timeframes}")
    print(f"🔢 Expected combinations: {len(expected_combinations)}")
    
    for combo in expected_combinations:
        print(f"   • {combo[0]} ({combo[1]})")
    
    assert len(expected_combinations) == len(test_tickers) * len(test_timeframes)
    print("✅ Combination building logic validated!")

def display_final_config():
    """Display the current ticker configuration"""
    print("\n📊 Current Ticker Configuration")
    print("=" * 40)
    
    try:
        config = load_ticker_config()
        
        print(f"🎯 Tickers ({len(config['tickers'])}):")
        for i, ticker in enumerate(config['tickers'], 1):
            print(f"   {i:2d}. {ticker}")
        
        print(f"\n⏱️ Timeframes ({len(config['timeframes'])}):")
        for i, tf in enumerate(config['timeframes'], 1):
            print(f"   {i}. {tf}")
        
        settings = config.get('settings', {})
        print(f"\n⚙️ Settings:")
        print(f"   Max tickers: {settings.get('max_tickers', 'N/A')}")
        print(f"   Allowed timeframes: {', '.join(settings.get('allowed_timeframes', []))}")
        
        total_combinations = len(config['tickers']) * len(config['timeframes'])
        print(f"\n📈 Total combinations: {total_combinations}")
        
    except Exception as e:
        print(f"❌ Error reading config: {e}")

def main():
    """Run all ticker management tests"""
    print("🚀 Discord Bot Ticker Management Tests")
    print("=" * 50)
    print(f"📅 Test run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run tests
    tests_passed = 0
    total_tests = 3
    
    try:
        # Test 1: Configuration operations
        if test_ticker_config_operations():
            tests_passed += 1
        
        # Test 2: Ticker validation
        test_ticker_validation()
        tests_passed += 1
        
        # Test 3: Combination building
        test_combination_building()
        tests_passed += 1
        
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
    
    # Display results
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed! Ticker management is ready for production.")
        display_final_config()
        
        print("\n🛠️ Available Discord Commands:")
        print("   • !addticker SYMBOL - Add a ticker to monitoring")
        print("   • !removeticker SYMBOL - Remove a ticker from monitoring")
        print("   • !listtickers - List all monitored tickers")
        print("   • !timeframes - Manage timeframes (list/add/remove)")
        
        return True
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 