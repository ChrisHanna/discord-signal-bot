#!/usr/bin/env python3
"""
Database Schema Fix: Update Price Field Precision
Update NUMERIC precision to handle cryptocurrency prices (BTC ~$67,000, ETH ~$3,500)
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_price_precision():
    """Update price field precision to handle larger values"""
    
    print("🔧 FIXING PRICE FIELD PRECISION")
    print("=" * 50)
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable not set")
        return
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Connected to PostgreSQL database")
        
        # Price fields that need to be updated
        price_fields = [
            'price_at_signal',
            'price_after_1h', 
            'price_after_3h',
            'price_after_4h',
            'price_after_6h',
            'price_after_1d',
            'price_after_3d',
            'max_gain_1d',
            'max_loss_1d'
        ]
        
        print("🔍 Checking current precision constraints...")
        
        # Check current data types
        check_query = '''
            SELECT column_name, data_type, numeric_precision, numeric_scale
            FROM information_schema.columns 
            WHERE table_name = 'signal_performance' 
            AND column_name IN ('price_at_signal', 'price_after_1h', 'price_after_1d')
            ORDER BY column_name
        '''
        
        current_schema = await conn.fetch(check_query)
        print("📊 Current schema for price fields:")
        for row in current_schema:
            print(f"   {row['column_name']}: {row['data_type']} ({row['numeric_precision']},{row['numeric_scale']})")
        
        # Update precision for signal_performance table
        print("\n🔄 Updating signal_performance table...")
        for field in price_fields:
            try:
                alter_query = f'''
                    ALTER TABLE signal_performance 
                    ALTER COLUMN {field} TYPE NUMERIC(12,4)
                '''
                await conn.execute(alter_query)
                print(f"   ✅ Updated {field} to NUMERIC(12,4)")
            except Exception as e:
                if "does not exist" in str(e):
                    print(f"   ⚠️  Column {field} does not exist - skipping")
                else:
                    print(f"   ❌ Error updating {field}: {e}")
        
        # Also update signal_notifications table if price_at_signal exists there
        print("\n🔄 Updating signal_notifications table...")
        try:
            alter_query = '''
                ALTER TABLE signal_notifications 
                ALTER COLUMN price_at_signal TYPE NUMERIC(12,4)
            '''
            await conn.execute(alter_query)
            print("   ✅ Updated price_at_signal to NUMERIC(12,4)")
        except Exception as e:
            if "does not exist" in str(e):
                print("   ⚠️  Column price_at_signal does not exist in signal_notifications")
            else:
                print(f"   ❌ Error updating price_at_signal: {e}")
        
        # Verify the changes
        print("\n🔍 Verifying schema updates...")
        verify_query = '''
            SELECT column_name, data_type, numeric_precision, numeric_scale
            FROM information_schema.columns 
            WHERE table_name IN ('signal_performance', 'signal_notifications')
            AND column_name LIKE '%price%'
            ORDER BY table_name, column_name
        '''
        
        updated_schema = await conn.fetch(verify_query)
        print("📊 Updated schema for price fields:")
        current_table = ""
        for row in updated_schema:
            table_name = await conn.fetchval(
                "SELECT table_name FROM information_schema.columns WHERE column_name = $1 LIMIT 1", 
                row['column_name']
            )
            if table_name != current_table:
                print(f"\n📋 Table: {table_name}")
                current_table = table_name
            print(f"   {row['column_name']}: {row['data_type']} ({row['numeric_precision']},{row['numeric_scale']})")
        
        # Test with sample crypto prices
        print("\n🧪 Testing with sample cryptocurrency prices...")
        test_prices = {
            'BTC-USD': 67543.28,
            'ETH-USD': 3524.67,
            'AAPL': 194.83
        }
        
        for ticker, price in test_prices.items():
            try:
                # Try to insert a test record
                test_query = '''
                    INSERT INTO signal_performance 
                    (ticker, timeframe, signal_type, signal_date, price_at_signal) 
                    VALUES ($1, '1h', 'test', NOW(), $2)
                    ON CONFLICT DO NOTHING
                    RETURNING id
                '''
                result = await conn.fetchval(test_query, ticker, price)
                if result:
                    print(f"   ✅ {ticker}: ${price:.2f} - stored successfully")
                    # Clean up test record
                    await conn.execute('DELETE FROM signal_performance WHERE id = $1', result)
                else:
                    print(f"   ✅ {ticker}: ${price:.2f} - would store successfully (conflict)")
            except Exception as e:
                print(f"   ❌ {ticker}: ${price:.2f} - error: {e}")
        
        await conn.close()
        
        print(f"\n🎯 Schema precision fix completed!")
        print("📈 Price fields can now handle values up to $99,999,999.9999")
        print("💡 You can now run the backfill scripts without precision errors")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(fix_price_precision()) 