#!/usr/bin/env python3
"""
Check Signal Notifications Table Schema
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def check_signal_notifications_schema():
    """Check the schema of signal_notifications table"""
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable not set")
        return
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Get column information
        result = await conn.fetch('''
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'signal_notifications' 
            ORDER BY ordinal_position
        ''')
        
        print("📊 SIGNAL_NOTIFICATIONS TABLE SCHEMA:")
        print("=" * 50)
        
        for row in result:
            nullable = "NULL" if row['is_nullable'] == 'YES' else "NOT NULL"
            default = f" DEFAULT {row['column_default']}" if row['column_default'] else ""
            print(f"   {row['column_name']}: {row['data_type']} {nullable}{default}")
        
        # Check if price_at_signal column exists
        has_price_at_signal = any(row['column_name'] == 'price_at_signal' for row in result)
        
        print("=" * 50)
        if has_price_at_signal:
            print("✅ price_at_signal column EXISTS")
        else:
            print("❌ price_at_signal column MISSING - needs to be added")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_signal_notifications_schema()) 