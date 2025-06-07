#!/usr/bin/env python3
"""
Database Migration: Add price_at_signal column to signal_notifications table
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def add_price_at_signal_column():
    """Add price_at_signal column to signal_notifications table"""
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable not set")
        return
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Connected to PostgreSQL database")
        
        # Check if column already exists
        existing_column = await conn.fetchval('''
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'signal_notifications' 
              AND column_name = 'price_at_signal'
        ''')
        
        if existing_column:
            print("✅ price_at_signal column already exists")
            await conn.close()
            return
        
        print("🔄 Adding price_at_signal column to signal_notifications table...")
        
        # Add the column
        await conn.execute('''
            ALTER TABLE signal_notifications 
            ADD COLUMN price_at_signal NUMERIC(12,4)
        ''')
        
        print("✅ Successfully added price_at_signal column")
        
        # Verify the column was added
        result = await conn.fetch('''
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'signal_notifications' 
              AND column_name = 'price_at_signal'
        ''')
        
        if result:
            print(f"✅ Verified: {result[0]['column_name']} ({result[0]['data_type']}) added successfully")
        
        # Show some stats
        total_signals = await conn.fetchval('SELECT COUNT(*) FROM signal_notifications')
        print(f"📊 Total signals in table: {total_signals}")
        
        signals_without_price = await conn.fetchval('''
            SELECT COUNT(*) 
            FROM signal_notifications 
            WHERE price_at_signal IS NULL
        ''')
        print(f"📊 Signals without price: {signals_without_price}")
        
        await conn.close()
        print("🎯 Next steps:")
        print("   1. Update signal_notifier.py to capture price when sending signals")
        print("   2. Run backfill to populate historical prices based on timestamps")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(add_price_at_signal_column()) 