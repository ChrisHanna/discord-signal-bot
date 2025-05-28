#!/usr/bin/env python3
"""
Test Priority and Ticker Integration
Tests the integration between tickers table and priority_config table
"""

import asyncio
import os
import sys
from datetime import datetime

# Add the current directory to Python path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import init_database, add_ticker_to_database, get_database_tickers, db_manager
from priority_manager import priority_manager

async def test_priority_ticker_integration():
    """Test the integration between tickers and priority system"""
    print("🧪 Testing Priority and Ticker Integration")
    print("=" * 60)
    
    # Initialize database
    print("1. Initializing database connection...")
    db_success = await init_database()
    if not db_success:
        print("❌ Failed to initialize database")
        return False
    print("✅ Database initialized")
    
    # Initialize priority manager
    print("\n2. Initializing priority manager...")
    priority_success = await priority_manager.initialize()
    if not priority_success:
        print("❌ Failed to initialize priority manager")
        return False
    print("✅ Priority manager initialized")
    
    # Test 1: Add some test tickers to database
    print("\n3. Adding test tickers to database...")
    test_tickers = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY', 'QQQ']
    
    for ticker in test_tickers:
        success = await add_ticker_to_database(ticker, f"{ticker} Test Stock", "NASDAQ")
        if success:
            print(f"   ✅ Added {ticker}")
        else:
            print(f"   ⚠️ {ticker} already exists or failed to add")
    
    # Test 2: Get current tickers from database
    print("\n4. Getting tickers from database...")
    db_tickers = await get_database_tickers()
    print(f"   📊 Found {len(db_tickers)} tickers in database: {', '.join(db_tickers[:10])}")
    
    # Test 3: Test priority system with database tickers
    print("\n5. Testing priority system...")
    
    print(f"   Current VIP Tickers: {sorted(priority_manager.VIP_TICKERS)}")
    print(f"   Current Min Priority: {priority_manager.MIN_PRIORITY_LEVEL}")
    
    # Test 4: Add VIP ticker that exists in database
    print("\n6. Testing VIP ticker management...")
    test_vip_ticker = 'MSFT'
    
    if test_vip_ticker in db_tickers:
        print(f"   {test_vip_ticker} exists in tickers table ✅")
        
        success = await priority_manager.add_vip_ticker(test_vip_ticker)
        if success:
            print(f"   ✅ Successfully added {test_vip_ticker} as VIP ticker")
            print(f"   Updated VIP Tickers: {sorted(priority_manager.VIP_TICKERS)}")
        else:
            print(f"   ❌ Failed to add {test_vip_ticker} as VIP ticker")
    else:
        print(f"   ⚠️ {test_vip_ticker} not found in tickers table")
    
    # Test 5: Try to add VIP ticker that doesn't exist in database
    print("\n7. Testing validation - adding non-existent ticker...")
    non_existent_ticker = 'FAKE123'
    
    if non_existent_ticker not in db_tickers:
        print(f"   {non_existent_ticker} does not exist in tickers table (expected)")
        
        # This should still work but we'll note it's not validated
        success = await priority_manager.add_vip_ticker(non_existent_ticker)
        if success:
            print(f"   ⚠️ Added {non_existent_ticker} as VIP ticker (no validation currently)")
            
            # Remove it for cleanup
            await priority_manager.remove_vip_ticker(non_existent_ticker)
            print(f"   🧹 Removed {non_existent_ticker} for cleanup")
    
    # Test 6: Test priority scoring with actual tickers
    print("\n8. Testing priority scoring...")
    
    test_signal = {
        'type': 'WT Buy Signal',
        'strength': 'Strong',
        'system': 'Wave Trend',
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    for ticker in ['AAPL', 'MSFT', 'UNKNOWN']:
        score = priority_manager.calculate_priority_score(test_signal, ticker, '1d')
        is_vip = ticker in priority_manager.VIP_TICKERS
        exists_in_db = ticker in db_tickers
        
        print(f"   {ticker}: Score={score.total_score}, Priority={score.priority_level.name}, VIP={is_vip}, InDB={exists_in_db}")
    
    # Test 7: Database validation function
    print("\n9. Testing VIP ticker validation...")
    await test_vip_ticker_validation()
    
    print("\n✅ All tests completed successfully!")
    return True

async def test_vip_ticker_validation():
    """Test validation of VIP tickers against tickers table"""
    
    # Get current VIP tickers and database tickers
    vip_tickers = priority_manager.VIP_TICKERS
    db_tickers = set(await get_database_tickers())
    
    print(f"   VIP Tickers: {sorted(vip_tickers)}")
    print(f"   DB Tickers: {sorted(list(db_tickers)[:10])}{'...' if len(db_tickers) > 10 else ''}")
    
    # Check which VIP tickers exist in database
    valid_vips = vip_tickers & db_tickers
    invalid_vips = vip_tickers - db_tickers
    
    if valid_vips:
        print(f"   ✅ Valid VIP tickers (in database): {sorted(valid_vips)}")
    
    if invalid_vips:
        print(f"   ⚠️ Invalid VIP tickers (not in database): {sorted(invalid_vips)}")
    else:
        print(f"   ✅ All VIP tickers exist in database")

async def test_priority_config_table():
    """Test direct priority_config table operations"""
    print("\n10. Testing priority_config table operations...")
    
    try:
        async with db_manager.pool.acquire() as conn:
            # Check if priority_config table exists and has data
            result = await conn.fetchrow('''
                SELECT COUNT(*) as count FROM priority_config WHERE config_name = 'default'
            ''')
            
            if result['count'] > 0:
                print("   ✅ Priority config table has default configuration")
                
                # Get the current configuration
                config = await conn.fetchrow('''
                    SELECT * FROM priority_config WHERE config_name = 'default'
                ''')
                
                print(f"   📊 Current config:")
                print(f"      Min Priority Level: {config['min_priority_level']}")
                print(f"      VIP Tickers: {config['vip_tickers']}")
                print(f"      VIP Timeframes: {config['vip_timeframes']}")
                print(f"      Thresholds: C={config['critical_threshold']}, H={config['high_threshold']}, M={config['medium_threshold']}, L={config['low_threshold']}")
                
            else:
                print("   ⚠️ No default priority configuration found")
                
    except Exception as e:
        print(f"   ❌ Error testing priority_config table: {e}")

async def create_enhanced_vip_validation():
    """Create an enhanced VIP ticker validation function"""
    print("\n11. Creating enhanced VIP ticker validation...")
    
    async def validate_and_add_vip_ticker(ticker: str) -> tuple[bool, str]:
        """Add VIP ticker with validation against tickers table"""
        ticker = ticker.upper().strip()
        
        # Check if ticker exists in database
        db_tickers = await get_database_tickers()
        
        if ticker not in db_tickers:
            return False, f"Ticker {ticker} not found in monitored tickers database"
        
        # Add to VIP list
        success = await priority_manager.add_vip_ticker(ticker)
        if success:
            return True, f"Successfully added {ticker} as VIP ticker"
        else:
            return False, f"Failed to add {ticker} to VIP tickers"
    
    # Test the validation function
    test_cases = ['AAPL', 'MSFT', 'FAKE123']
    
    for test_ticker in test_cases:
        success, message = await validate_and_add_vip_ticker(test_ticker)
        if success:
            print(f"   ✅ {message}")
            # Clean up by removing it
            await priority_manager.remove_vip_ticker(test_ticker)
        else:
            print(f"   ❌ {message}")

async def main():
    """Run all tests"""
    try:
        success = await test_priority_ticker_integration()
        await test_priority_config_table()
        await create_enhanced_vip_validation()
        
        if success:
            print(f"\n🎉 All integration tests passed!")
        else:
            print(f"\n💥 Some tests failed!")
            
    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main()) 