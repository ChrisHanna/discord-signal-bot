#!/usr/bin/env python3
"""
PostgreSQL Database Test Script for Discord Signal Bot
Run this to verify your database setup is working correctly.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from database import DatabaseManager, init_database

async def test_database_connection():
    """Test basic database connectivity"""
    print("🧪 Testing PostgreSQL Database Connection...")
    print("=" * 50)
    
    # Check if DATABASE_URL is set
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ ERROR: DATABASE_URL environment variable not found")
        print("   Please set DATABASE_URL in your .env file")
        return False
    
    print(f"🔗 Database URL: {database_url[:20]}...{database_url[-20:] if len(database_url) > 40 else database_url}")
    
    # Test database initialization
    try:
        success = await init_database()
        if success:
            print("✅ Database connection successful!")
            print("✅ Tables created/verified successfully!")
            return True
        else:
            print("❌ Database initialization failed")
            return False
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

async def test_database_operations():
    """Test basic database operations"""
    print("\n🔧 Testing Database Operations...")
    print("=" * 50)
    
    db = DatabaseManager()
    
    try:
        # Initialize database
        await db.initialize()
        
        # Test duplicate checking
        print("📝 Testing duplicate notification checking...")
        is_duplicate = await db.check_duplicate_notification(
            "TEST", "1d", "BUY", "2024-01-01"
        )
        print(f"   Duplicate check result: {is_duplicate}")
        
        # Test recording a notification
        print("📝 Testing notification recording...")
        success = await db.record_notification(
            "TEST", "1d", "BUY", "2024-01-01", "High", "Test System", 123456789
        )
        print(f"   Record notification result: {success}")
        
        # Test checking if it's now a duplicate
        print("📝 Testing duplicate check after recording...")
        is_duplicate_after = await db.check_duplicate_notification(
            "TEST", "1d", "BUY", "2024-01-01"
        )
        print(f"   Duplicate check after recording: {is_duplicate_after}")
        
        # Test getting recent notifications
        print("📝 Testing recent notifications retrieval...")
        recent = await db.get_recent_notifications(24)
        print(f"   Found {len(recent)} recent notifications")
        if recent:
            print("   Most recent:")
            for notification in recent[:3]:
                print(f"     - {notification['ticker']} {notification['signal_type']} at {notification['notified_at']}")
        
        # Test getting statistics
        print("📝 Testing statistics retrieval...")
        stats = await db.get_notification_stats()
        print(f"   Total notifications: {stats.get('total', 0)}")
        print(f"   Last 24 hours: {stats.get('last_24h', 0)}")
        print(f"   Last 7 days: {stats.get('last_7d', 0)}")
        
        # Clean up test data
        print("🧹 Cleaning up test data...")
        async with db.pool.acquire() as conn:
            await conn.execute("DELETE FROM signal_notifications WHERE ticker = 'TEST'")
        
        await db.close()
        print("✅ All database operations successful!")
        return True
        
    except Exception as e:
        print(f"❌ Database operation error: {e}")
        return False

async def test_database_schema():
    """Verify database schema is correct"""
    print("\n🏗️  Testing Database Schema...")
    print("=" * 50)
    
    db = DatabaseManager()
    
    try:
        await db.initialize()
        
        async with db.pool.acquire() as conn:
            # Check if all required tables exist
            tables = await conn.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            
            table_names = [row['table_name'] for row in tables]
            required_tables = ['tickers', 'signal_notifications', 'user_preferences']
            
            print("📋 Checking required tables...")
            for table in required_tables:
                if table in table_names:
                    print(f"   ✅ {table}")
                else:
                    print(f"   ❌ {table} - MISSING!")
            
            # Check indexes
            print("\n📊 Checking indexes...")
            indexes = await conn.fetch("""
                SELECT indexname, tablename 
                FROM pg_indexes 
                WHERE schemaname = 'public'
                AND indexname LIKE 'idx_%'
                ORDER BY tablename, indexname
            """)
            
            for index in indexes:
                print(f"   ✅ {index['indexname']} on {index['tablename']}")
            
            # Check table structures
            print("\n🔍 Checking table structures...")
            for table in required_tables:
                if table in table_names:
                    columns = await conn.fetch(f"""
                        SELECT column_name, data_type, is_nullable
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                        ORDER BY ordinal_position
                    """)
                    
                    print(f"\n   📄 {table} columns:")
                    for col in columns:
                        nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                        print(f"     - {col['column_name']}: {col['data_type']} ({nullable})")
        
        await db.close()
        print("\n✅ Database schema verification complete!")
        return True
        
    except Exception as e:
        print(f"❌ Schema verification error: {e}")
        return False

async def main():
    """Run all database tests"""
    print("🐘 PostgreSQL Database Test Suite")
    print("=" * 50)
    print("This script will test your PostgreSQL setup for the Discord Signal Bot")
    print()
    
    # Load environment variables from .env file if it exists
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("📁 Loaded environment variables from .env file")
    except ImportError:
        print("⚠️  python-dotenv not installed, using system environment variables")
    except Exception as e:
        print(f"⚠️  Could not load .env file: {e}")
    
    print()
    
    # Run tests
    tests = [
        ("Database Connection", test_database_connection),
        ("Database Operations", test_database_operations),
        ("Database Schema", test_database_schema),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
        
        print()
    
    # Summary
    print("🎯 Test Results Summary")
    print("=" * 50)
    
    all_passed = True
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
        if not result:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 All tests passed! Your PostgreSQL setup is ready!")
        print("   You can now run your Discord bot with confidence.")
    else:
        print("⚠️  Some tests failed. Please check the errors above.")
        print("   Refer to POSTGRESQL_SETUP.md for troubleshooting help.")
    
    return all_passed

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1) 