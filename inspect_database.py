#!/usr/bin/env python3
"""
Database Schema Inspector
Check what tables and columns actually exist in the PostgreSQL database
"""

import asyncio
import asyncpg
import os
from datetime import datetime
import json

async def inspect_database():
    """Inspect the database schema and current data"""
    
    print("🔍 PostgreSQL Database Inspector")
    print("=" * 50)
    
    # Database connection
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable not set")
        return
    
    try:
        # Connect to database
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Connected to PostgreSQL database")
        
        # 1. List all tables
        print("\n📋 **TABLES IN DATABASE:**")
        tables = await conn.fetch("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        
        for table in tables:
            print(f"  • {table['tablename']}")
        
        # 2. Check signal_performance table
        print("\n🎯 **SIGNAL_PERFORMANCE TABLE:**")
        try:
            columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'signal_performance'
                ORDER BY ordinal_position
            """)
            
            if columns:
                print("  Columns:")
                for col in columns:
                    nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                    default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""
                    print(f"    • {col['column_name']} ({col['data_type']}) {nullable}{default}")
                
                # Check current data
                count = await conn.fetchval("SELECT COUNT(*) FROM signal_performance")
                print(f"  📊 Current records: {count}")
                
                if count > 0:
                    sample = await conn.fetch("SELECT * FROM signal_performance ORDER BY performance_date DESC LIMIT 3")
                    print("  📄 Sample records:")
                    for i, record in enumerate(sample, 1):
                        print(f"    {i}. {dict(record)}")
            else:
                print("  ❌ Table does not exist or no columns found")
                
        except Exception as e:
            print(f"  ❌ Error checking signal_performance: {e}")
        
        # 3. Check signal_analytics table
        print("\n📈 **SIGNAL_ANALYTICS TABLE:**")
        try:
            columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'signal_analytics'
                ORDER BY ordinal_position
            """)
            
            if columns:
                print("  Columns:")
                for col in columns:
                    nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                    default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""
                    print(f"    • {col['column_name']} ({col['data_type']}) {nullable}{default}")
                
                # Check current data
                count = await conn.fetchval("SELECT COUNT(*) FROM signal_analytics")
                print(f"  📊 Current records: {count}")
                
                if count > 0:
                    sample = await conn.fetch("SELECT * FROM signal_analytics ORDER BY date DESC LIMIT 3")
                    print("  📄 Sample records:")
                    for i, record in enumerate(sample, 1):
                        print(f"    {i}. {dict(record)}")
                        
                # Check success rate data specifically
                success_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM signal_analytics 
                    WHERE success_rate_1h IS NOT NULL OR success_rate_1d IS NOT NULL
                """)
                print(f"  🎯 Records with success rates: {success_count}")
                
            else:
                print("  ❌ Table does not exist or no columns found")
                
        except Exception as e:
            print(f"  ❌ Error checking signal_analytics: {e}")
        
        # 4. Check signal_notifications table
        print("\n📢 **SIGNAL_NOTIFICATIONS TABLE:**")
        try:
            count = await conn.fetchval("SELECT COUNT(*) FROM signal_notifications")
            print(f"  📊 Current records: {count}")
            
            if count > 0:
                recent = await conn.fetch("""
                    SELECT ticker, timeframe, signal_type, signal_date, notified_at 
                    FROM signal_notifications 
                    ORDER BY notified_at DESC 
                    LIMIT 5
                """)
                print("  📄 Recent signals:")
                for i, record in enumerate(recent, 1):
                    print(f"    {i}. {record['ticker']} {record['timeframe']} {record['signal_type']} on {record['signal_date']}")
                    
        except Exception as e:
            print(f"  ❌ Error checking signal_notifications: {e}")
        
        # 5. Check for any performance data gaps
        print("\n🔍 **PERFORMANCE DATA ANALYSIS:**")
        try:
            # Check signals that should have performance data but don't
            missing_performance = await conn.fetch("""
                SELECT sn.ticker, sn.timeframe, sn.signal_type, sn.signal_date, sn.notified_at
                FROM signal_notifications sn
                LEFT JOIN signal_performance sp ON (
                    sn.ticker = sp.ticker AND 
                    sn.timeframe = sp.timeframe AND 
                    sn.signal_type = sp.signal_type AND 
                    sn.signal_date = sp.signal_date
                )
                WHERE sn.notified_at >= NOW() - INTERVAL '7 days'
                  AND sp.id IS NULL
                ORDER BY sn.notified_at DESC
                LIMIT 10
            """)
            
            if missing_performance:
                print(f"  ⚠️ Signals missing performance data: {len(missing_performance)}")
                for record in missing_performance[:5]:
                    print(f"    • {record['ticker']} {record['signal_type']} from {record['signal_date']}")
            else:
                print("  ✅ All recent signals have performance data")
                
        except Exception as e:
            print(f"  ❌ Error checking performance gaps: {e}")
        
        # 6. Show database connection info (without sensitive details)
        print("\n🔗 **DATABASE CONNECTION:**")
        db_info = await conn.fetchrow("SELECT version()")
        print(f"  PostgreSQL Version: {db_info['version']}")
        
        # Close connection
        await conn.close()
        print("\n✅ Database inspection complete!")
        
    except Exception as e:
        print(f"❌ Database connection error: {e}")

if __name__ == "__main__":
    asyncio.run(inspect_database()) 