#!/usr/bin/env python3
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def check_schema():
    """Check the actual database schema for signal_performance table"""
    try:
        DATABASE_URL = os.getenv('DATABASE_URL')
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Check table structure
        columns = await conn.fetch('''
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'signal_performance'
            ORDER BY ordinal_position
        ''')
        
        print("📊 signal_performance table structure:")
        for col in columns:
            print(f"   {col['column_name']}: {col['data_type']}")
        
        # Check which price columns exist
        price_columns = [col['column_name'] for col in columns if col['column_name'].startswith('price_after_')]
        print(f"\n⏰ Available timeframe columns:")
        for col in price_columns:
            print(f"   {col}")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_schema()) 