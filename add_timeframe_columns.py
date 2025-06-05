#!/usr/bin/env python3
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def add_timeframe_columns():
    """Add missing 3h and 6h timeframe columns to signal_performance table"""
    try:
        DATABASE_URL = os.getenv('DATABASE_URL')
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Add missing columns
        await conn.execute('''
            ALTER TABLE signal_performance 
            ADD COLUMN IF NOT EXISTS price_after_3h NUMERIC,
            ADD COLUMN IF NOT EXISTS price_after_6h NUMERIC,
            ADD COLUMN IF NOT EXISTS success_3h BOOLEAN,
            ADD COLUMN IF NOT EXISTS success_6h BOOLEAN
        ''')
        
        print("✅ Added 3h and 6h timeframe columns to signal_performance table")
        
        # Check updated structure
        columns = await conn.fetch('''
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'signal_performance'
            ORDER BY ordinal_position
        ''')
        
        print("\n📊 Updated signal_performance table structure:")
        for col in columns:
            print(f"   {col['column_name']}: {col['data_type']}")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(add_timeframe_columns()) 