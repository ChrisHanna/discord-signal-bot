#!/usr/bin/env python3
"""
Database Migration Script for Discord Signal Bot
Safely migrates existing databases to the enhanced priority system.
"""

import asyncio
import asyncpg
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

class DatabaseMigration:
    def __init__(self):
        self.pool = None
        self.database_url = None
        
    async def migrate_database(self):
        """Run database migration process"""
        print("🔄 Starting Database Migration")
        print("=" * 50)
        
        try:
            # Load environment variables
            await self.load_environment()
            
            # Connect to database
            await self.connect_database()
            
            # Check current schema
            await self.analyze_current_schema()
            
            # Run migrations
            await self.run_migrations()
            
            # Validate migration
            await self.validate_migration()
            
            print("\n✅ Migration completed successfully!")
            print("🎉 Your database is now upgraded to the enhanced priority system!")
            
        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
            return False
        finally:
            if self.pool:
                await self.pool.close()
        
        return True
    
    async def load_environment(self):
        """Load environment variables"""
        print("📁 Loading environment configuration...")
        
        if os.path.exists('.env'):
            load_dotenv()
            print("✅ Loaded .env file")
        
        self.database_url = os.getenv('DATABASE_URL')
        if not self.database_url:
            raise ValueError("DATABASE_URL not configured")
        
        print("✅ Environment configuration loaded")
    
    async def connect_database(self):
        """Connect to PostgreSQL database"""
        print("🔌 Connecting to PostgreSQL database...")
        
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=3,
                server_settings={
                    'application_name': 'discord-signal-bot-migration',
                    'timezone': 'EST'
                }
            )
            
            async with self.pool.acquire() as conn:
                version = await conn.fetchval('SELECT version()')
                print(f"✅ Connected to: {version[:50]}...")
                
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            raise
    
    async def analyze_current_schema(self):
        """Analyze current database schema"""
        print("🔍 Analyzing current database schema...")
        
        async with self.pool.acquire() as conn:
            # Check which tables exist
            tables = await conn.fetch('''
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public'
            ''')
            
            existing_tables = [table['table_name'] for table in tables]
            print(f"📊 Found existing tables: {', '.join(existing_tables)}")
            
            # Check signal_notifications structure
            if 'signal_notifications' in existing_tables:
                columns = await conn.fetch('''
                    SELECT column_name, data_type FROM information_schema.columns 
                    WHERE table_name = 'signal_notifications'
                ''')
                existing_columns = [col['column_name'] for col in columns]
                
                if 'priority_score' not in existing_columns:
                    print("🔄 signal_notifications table needs priority columns")
                else:
                    print("✅ signal_notifications table already has priority columns")
            
            # Check for new tables
            new_tables = ['signals_detected', 'priority_config', 'signal_performance', 'signal_analytics']
            missing_tables = [table for table in new_tables if table not in existing_tables]
            
            if missing_tables:
                print(f"🆕 New tables to create: {', '.join(missing_tables)}")
            else:
                print("✅ All enhanced tables already exist")
    
    async def run_migrations(self):
        """Run database migrations"""
        print("🚀 Running database migrations...")
        
        async with self.pool.acquire() as conn:
            # Migration 1: Add priority columns to signal_notifications
            await self.migrate_signal_notifications(conn)
            
            # Migration 2: Create signals_detected table
            await self.create_signals_detected_table(conn)
            
            # Migration 3: Create priority_config table
            await self.create_priority_config_table(conn)
            
            # Migration 4: Create signal_performance table
            await self.create_signal_performance_table(conn)
            
            # Migration 5: Create signal_analytics table
            await self.create_signal_analytics_table(conn)
            
            # Migration 6: Update user_preferences table
            await self.migrate_user_preferences(conn)
            
            # Migration 7: Create new indexes
            await self.create_new_indexes(conn)
    
    async def migrate_signal_notifications(self, conn):
        """Add priority columns to signal_notifications table"""
        print("🔄 Migrating signal_notifications table...")
        
        # Check if priority_score column exists
        columns = await conn.fetch('''
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'signal_notifications'
        ''')
        existing_columns = [col['column_name'] for col in columns]
        
        if 'priority_score' not in existing_columns:
            await conn.execute('''
                ALTER TABLE signal_notifications 
                ADD COLUMN priority_score INTEGER DEFAULT 0,
                ADD COLUMN priority_level VARCHAR(10),
                ADD COLUMN was_vip_ticker BOOLEAN DEFAULT FALSE,
                ADD COLUMN was_vip_timeframe BOOLEAN DEFAULT FALSE,
                ADD COLUMN urgency_bonus INTEGER DEFAULT 0,
                ADD COLUMN pattern_bonus INTEGER DEFAULT 0
            ''')
            print("✅ Added priority columns to signal_notifications")
        else:
            print("✅ signal_notifications already has priority columns")
    
    async def create_signals_detected_table(self, conn):
        """Create signals_detected table if it doesn't exist"""
        print("🔄 Creating signals_detected table...")
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS signals_detected (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(10) NOT NULL,
                timeframe VARCHAR(5) NOT NULL,
                signal_type VARCHAR(50) NOT NULL,
                signal_date TIMESTAMPTZ NOT NULL,
                detected_at TIMESTAMPTZ DEFAULT NOW(),
                strength VARCHAR(20),
                system VARCHAR(50),
                priority_score INTEGER NOT NULL,
                priority_level VARCHAR(10) NOT NULL,
                was_sent BOOLEAN DEFAULT FALSE,
                skip_reason VARCHAR(100),
                signal_data JSONB,
                CONSTRAINT unique_detected_signal UNIQUE(ticker, timeframe, signal_type, signal_date)
            )
        ''')
        print("✅ Created signals_detected table")
    
    async def create_priority_config_table(self, conn):
        """Create priority_config table"""
        print("🔄 Creating priority_config table...")
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS priority_config (
                id SERIAL PRIMARY KEY,
                config_name VARCHAR(50) UNIQUE NOT NULL,
                min_priority_level VARCHAR(10) NOT NULL,
                critical_threshold INTEGER NOT NULL,
                high_threshold INTEGER NOT NULL,
                medium_threshold INTEGER NOT NULL,
                low_threshold INTEGER NOT NULL,
                vip_tickers TEXT[],
                vip_timeframes TEXT[],
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')
        
        # Insert default configuration
        await conn.execute('''
            INSERT INTO priority_config 
            (config_name, min_priority_level, critical_threshold, high_threshold,
             medium_threshold, low_threshold, vip_tickers, vip_timeframes)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (config_name) DO NOTHING
        ''', 'default', 'MEDIUM', 90, 70, 50, 30, 
             ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA'], ['1d', '4h'])
        
        print("✅ Created priority_config table with default configuration")
    
    async def create_signal_performance_table(self, conn):
        """Create signal_performance table"""
        print("🔄 Creating signal_performance table...")
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS signal_performance (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(10) NOT NULL,
                timeframe VARCHAR(5) NOT NULL,
                signal_type VARCHAR(50) NOT NULL,
                signal_date TIMESTAMPTZ NOT NULL,
                performance_date TIMESTAMPTZ NOT NULL,
                price_at_signal DECIMAL(10,2),
                price_after_1h DECIMAL(10,2),
                price_after_4h DECIMAL(10,2),
                price_after_1d DECIMAL(10,2),
                price_after_3d DECIMAL(10,2),
                max_gain_1d DECIMAL(5,2),
                max_loss_1d DECIMAL(5,2),
                success_1h BOOLEAN,
                success_4h BOOLEAN,
                success_1d BOOLEAN,
                success_3d BOOLEAN,
                CONSTRAINT unique_performance UNIQUE(ticker, timeframe, signal_type, signal_date)
            )
        ''')
        print("✅ Created signal_performance table")
    
    async def create_signal_analytics_table(self, conn):
        """Create signal_analytics table"""
        print("🔄 Creating signal_analytics table...")
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS signal_analytics (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                ticker VARCHAR(10) NOT NULL,
                timeframe VARCHAR(5) NOT NULL,
                system VARCHAR(50) NOT NULL,
                total_signals INTEGER DEFAULT 0,
                sent_signals INTEGER DEFAULT 0,
                skipped_signals INTEGER DEFAULT 0,
                avg_priority_score DECIMAL(5,1),
                priority_distribution JSONB,
                success_rate_1h DECIMAL(5,2),
                success_rate_1d DECIMAL(5,2),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT unique_analytics UNIQUE(date, ticker, timeframe, system)
            )
        ''')
        print("✅ Created signal_analytics table")
    
    async def migrate_user_preferences(self, conn):
        """Update user_preferences table with new columns"""
        print("🔄 Migrating user_preferences table...")
        
        # Check if new columns exist
        columns = await conn.fetch('''
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'user_preferences'
        ''')
        existing_columns = [col['column_name'] for col in columns]
        
        if 'min_priority_level' not in existing_columns:
            await conn.execute('''
                ALTER TABLE user_preferences 
                ADD COLUMN min_priority_level VARCHAR(10) DEFAULT 'MEDIUM',
                ADD COLUMN custom_vip_tickers TEXT[],
                ADD COLUMN custom_vip_timeframes TEXT[],
                ADD COLUMN priority_boost_multiplier DECIMAL(3,1) DEFAULT 1.0
            ''')
            print("✅ Added priority columns to user_preferences")
        else:
            print("✅ user_preferences already has priority columns")
    
    async def create_new_indexes(self, conn):
        """Create new performance indexes"""
        print("🔄 Creating performance indexes...")
        
        indexes = [
            ("idx_priority_score", "signal_notifications", "priority_score DESC"),
            ("idx_detected_signals_date", "signals_detected", "detected_at DESC"),
            ("idx_detected_priority", "signals_detected", "priority_score DESC, was_sent"),
            ("idx_detected_ticker_system", "signals_detected", "ticker, system, detected_at DESC"),
            ("idx_performance_ticker_date", "signal_performance", "ticker, signal_date DESC"),
            ("idx_analytics_date", "signal_analytics", "date DESC, ticker, system"),
        ]
        
        for index_name, table_name, columns in indexes:
            try:
                await conn.execute(f'''
                    CREATE INDEX IF NOT EXISTS {index_name} 
                    ON {table_name}({columns})
                ''')
                print(f"✅ Created index: {index_name}")
            except Exception as e:
                print(f"⚠️  Warning: Could not create index {index_name}: {e}")
    
    async def validate_migration(self):
        """Validate the migration results"""
        print("🔍 Validating migration...")
        
        async with self.pool.acquire() as conn:
            # Check all tables exist
            required_tables = [
                'tickers', 'signal_notifications', 'signals_detected',
                'priority_config', 'signal_performance', 'signal_analytics',
                'user_preferences'
            ]
            
            for table in required_tables:
                count = await conn.fetchval(f'''
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_name = '{table}'
                ''')
                if count == 0:
                    raise Exception(f"Table {table} is missing after migration")
                print(f"✅ Validated table: {table}")
            
            # Check priority_score column exists
            columns = await conn.fetch('''
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'signal_notifications'
            ''')
            column_names = [col['column_name'] for col in columns]
            
            if 'priority_score' not in column_names:
                raise Exception("priority_score column missing from signal_notifications")
            
            print("✅ All priority columns validated")
            
            # Check default configuration exists
            config_count = await conn.fetchval('''
                SELECT COUNT(*) FROM priority_config WHERE config_name = 'default'
            ''')
            if config_count == 0:
                raise Exception("Default priority configuration missing")
            
            print("✅ Priority configuration validated")

async def main():
    """Main migration function"""
    print("🔄 Discord Signal Bot Database Migration")
    print("=========================================\n")
    
    # Check if we're in the right directory
    if not os.path.exists('database.py'):
        print("❌ Error: Please run this script from the discord-bot directory")
        print("💡 Usage: cd discord-bot && python migrate_database.py")
        return False
    
    # Warning message
    print("⚠️  IMPORTANT: This script will modify your database schema.")
    print("📋 It's recommended to backup your database before proceeding.\n")
    
    response = input("🔄 Do you want to proceed with the migration? (y/N): ").strip().lower()
    if response not in ['y', 'yes']:
        print("❌ Migration cancelled by user")
        return False
    
    # Run migration
    migration = DatabaseMigration()
    success = await migration.migrate_database()
    
    if success:
        print("\n🎉 Migration Complete!")
        print("=" * 50)
        print("Your database has been successfully upgraded!")
        print()
        print("📋 What's New:")
        print("✅ Enhanced priority tracking")
        print("✅ Complete signal analytics")
        print("✅ Performance monitoring")
        print("✅ Advanced configuration management")
        print()
        print("📋 Next Steps:")
        print("1. Run: python signal_notifier.py")
        print("2. Test new commands:")
        print("   • !analytics")
        print("   • !utilization")
        print("   • !signalreport")
        print()
        print("📖 See ENHANCED_PRIORITY_SYSTEM.md for full documentation")
        
    return success

if __name__ == "__main__":
    try:
        import asyncio
        
        # Check Python version
        if sys.version_info < (3, 7):
            print("❌ Error: Python 3.7 or higher is required")
            sys.exit(1)
        
        # Check required modules
        try:
            import asyncpg
            import dotenv
        except ImportError as e:
            print(f"❌ Error: Missing required module: {e}")
            print("💡 Install with: pip install asyncpg python-dotenv")
            sys.exit(1)
        
        # Run migration
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n⏹️  Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 