#!/usr/bin/env python3
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def check_3h_6h_data():
    """Check if 3h and 6h performance data is populated"""
    try:
        DATABASE_URL = os.getenv('DATABASE_URL')
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Check data availability
        stats = await conn.fetchrow('''
            SELECT 
                COUNT(*) as total_records,
                COUNT(price_after_3h) as records_with_3h,
                COUNT(price_after_6h) as records_with_6h,
                COUNT(CASE WHEN price_after_3h IS NOT NULL THEN 1 END) as non_null_3h,
                COUNT(CASE WHEN price_after_6h IS NOT NULL THEN 1 END) as non_null_6h
            FROM signal_performance
        ''')
        
        print(f"📊 Performance Data Status:")
        print(f"   Total records: {stats['total_records']}")
        print(f"   Records with 3h data: {stats['records_with_3h']}")
        print(f"   Records with 6h data: {stats['records_with_6h']}")
        print(f"   Non-null 3h values: {stats['non_null_3h']}")
        print(f"   Non-null 6h values: {stats['non_null_6h']}")
        
        if stats['non_null_3h'] == 0 or stats['non_null_6h'] == 0:
            print("\n❌ Missing 3h/6h data - backfill needed!")
        else:
            print("\n✅ 3h/6h data looks good!")
            
        await conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_3h_6h_data()) 