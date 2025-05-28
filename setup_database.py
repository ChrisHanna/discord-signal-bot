#!/usr/bin/env python3
"""
Database Setup Script for Discord Signal Bot
Creates all necessary tables, indexes, and initial configurations.
"""

import asyncio
import asyncpg
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import json

class DatabaseSetup:
    def __init__(self):
        self.pool = None
        self.database_url = None
        
    async def setup_database(self):
        """Complete database setup process"""
        print("🚀 Starting Discord Signal Bot Database Setup")
        print("=" * 60)
        
        try:
            # Load environment variables
            await self.load_environment()
            
            # Connect to database
            await self.connect_database()
            
            # Create tables
            await self.create_tables()
            
            # Create indexes
            await self.create_indexes()
            
            # Setup initial configurations
            await self.setup_initial_config()
            
            # Validate setup
            await self.validate_setup()
            
            print("\n✅ Database setup completed successfully!")
            print("🎉 Your Discord Signal Bot is ready to use!")
            
        except Exception as e:
            print(f"\n❌ Setup failed: {e}")
            return False
        finally:
            if self.pool:
                await self.pool.close()
        
        return True
    
    async def load_environment(self):
        """Load and validate environment variables"""
        print("📁 Loading environment configuration...")
        
        # Load .env file if it exists
        if os.path.exists('.env'):
            load_dotenv()
            print("✅ Loaded .env file")
        else:
            print("⚠️  No .env file found - using system environment variables")
        
        # Get database URL
        self.database_url = os.getenv('DATABASE_URL')
        
        if not self.database_url:
            print("\n❌ DATABASE_URL environment variable not found!")
            print("💡 Please set DATABASE_URL in your .env file:")
            print("   DATABASE_URL=postgresql://username:password@hostname:5432/database_name")
            print("\n📖 For more help, see POSTGRESQL_SETUP.md")
            raise ValueError("DATABASE_URL not configured")
        
        # Validate other required variables
        discord_token = os.getenv('DISCORD_TOKEN')
        channel_id = os.getenv('DISCORD_CHANNEL_ID')
        
        if not discord_token:
            print("⚠️  DISCORD_TOKEN not found - you'll need to set this before running the bot")
        
        if not channel_id:
            print("⚠️  DISCORD_CHANNEL_ID not found - you'll need to set this before running the bot")
        
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
                    'application_name': 'discord-signal-bot-setup',
                    'timezone': 'EST'
                }
            )
            
            # Test connection
            async with self.pool.acquire() as conn:
                version = await conn.fetchval('SELECT version()')
                print(f"✅ Connected to: {version[:50]}...")
                
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            print("\n💡 Common issues:")
            print("   • Check your DATABASE_URL format")
            print("   • Ensure PostgreSQL server is running")
            print("   • Verify your credentials and permissions")
            print("   • Check firewall/network connectivity")
            raise
    
    async def create_tables(self):
        """Create all necessary database tables"""
        print("📊 Creating database tables...")
        
        async with self.pool.acquire() as conn:
            # Create tickers table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tickers (
                    symbol VARCHAR(10) PRIMARY KEY,
                    name VARCHAR(100),
                    exchange VARCHAR(20),
                    active BOOLEAN DEFAULT true,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            ''')
            print("✅ Created tickers table")
            
            # Enhanced signal_notifications table with priority tracking
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS signal_notifications (
                    id SERIAL PRIMARY KEY,
                    ticker VARCHAR(10) NOT NULL,
                    timeframe VARCHAR(5) NOT NULL,
                    signal_type VARCHAR(50) NOT NULL,
                    signal_date TIMESTAMPTZ NOT NULL,
                    notified_at TIMESTAMPTZ DEFAULT NOW(),
                    strength VARCHAR(20),
                    system VARCHAR(50),
                    discord_message_id BIGINT,
                    priority_score INTEGER DEFAULT 0,
                    priority_level VARCHAR(10),
                    was_vip_ticker BOOLEAN DEFAULT FALSE,
                    was_vip_timeframe BOOLEAN DEFAULT FALSE,
                    urgency_bonus INTEGER DEFAULT 0,
                    pattern_bonus INTEGER DEFAULT 0,
                    CONSTRAINT unique_signal UNIQUE(ticker, timeframe, signal_type, signal_date)
                )
            ''')
            print("✅ Created signal_notifications table")
            
            # New signals_detected table to track ALL signals
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
            
            # Priority configuration table
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
            print("✅ Created priority_config table")
            
            # Signal performance tracking
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
            
            # Signal analytics summary
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
            
            # Enhanced user_preferences table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    discord_user_id BIGINT PRIMARY KEY,
                    tickers TEXT[],
                    min_strength VARCHAR(20) DEFAULT 'Medium',
                    min_priority_level VARCHAR(10) DEFAULT 'MEDIUM',
                    custom_vip_tickers TEXT[],
                    custom_vip_timeframes TEXT[],
                    notifications_enabled BOOLEAN DEFAULT true,
                    priority_boost_multiplier DECIMAL(3,1) DEFAULT 1.0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            ''')
            print("✅ Created user_preferences table")
    
    async def create_indexes(self):
        """Create performance indexes"""
        print("⚡ Creating performance indexes...")
        
        async with self.pool.acquire() as conn:
            indexes = [
                # Signal notifications indexes
                ("idx_signal_date", "signal_notifications", "signal_date DESC"),
                ("idx_ticker_timeframe", "signal_notifications", "ticker, timeframe"),
                ("idx_notified_at", "signal_notifications", "notified_at DESC"),
                ("idx_priority_score", "signal_notifications", "priority_score DESC"),
                
                # Signals detected indexes
                ("idx_detected_signals_date", "signals_detected", "detected_at DESC"),
                ("idx_detected_priority", "signals_detected", "priority_score DESC, was_sent"),
                ("idx_detected_ticker_system", "signals_detected", "ticker, system, detected_at DESC"),
                
                # Performance tracking indexes
                ("idx_performance_ticker_date", "signal_performance", "ticker, signal_date DESC"),
                
                # Analytics indexes
                ("idx_analytics_date", "signal_analytics", "date DESC, ticker, system"),
                
                # User preferences indexes
                ("idx_user_prefs_updated", "user_preferences", "updated_at DESC")
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
    
    async def setup_initial_config(self):
        """Setup initial priority configurations"""
        print("⚙️ Setting up initial configurations...")
        
        async with self.pool.acquire() as conn:
            # Check if default config already exists
            existing = await conn.fetchval('''
                SELECT COUNT(*) FROM priority_config WHERE config_name = 'default'
            ''')
            
            if existing == 0:
                # Create default priority configuration
                await conn.execute('''
                    INSERT INTO priority_config 
                    (config_name, min_priority_level, critical_threshold, high_threshold,
                     medium_threshold, low_threshold, vip_tickers, vip_timeframes)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ''', 'default', 'MEDIUM', 90, 70, 50, 30, 
                     ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA'], ['1d', '4h'])
                print("✅ Created default priority configuration")
            else:
                print("✅ Default priority configuration already exists")
            
            # Create trading hours configuration
            trading_exists = await conn.fetchval('''
                SELECT COUNT(*) FROM priority_config WHERE config_name = 'trading_hours'
            ''')
            
            if trading_exists == 0:
                await conn.execute('''
                    INSERT INTO priority_config 
                    (config_name, min_priority_level, critical_threshold, high_threshold,
                     medium_threshold, low_threshold, vip_tickers, vip_timeframes)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ''', 'trading_hours', 'HIGH', 95, 75, 55, 35,
                     ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA', 'MSFT'], ['15m', '1h', '4h'])
                print("✅ Created trading_hours priority configuration")
            else:
                print("✅ Trading hours configuration already exists")
            
            # Create after hours configuration
            after_hours_exists = await conn.fetchval('''
                SELECT COUNT(*) FROM priority_config WHERE config_name = 'after_hours'
            ''')
            
            if after_hours_exists == 0:
                await conn.execute('''
                    INSERT INTO priority_config 
                    (config_name, min_priority_level, critical_threshold, high_threshold,
                     medium_threshold, low_threshold, vip_tickers, vip_timeframes)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ''', 'after_hours', 'CRITICAL', 95, 80, 60, 40,
                     ['SPY', 'QQQ'], ['1d'])
                print("✅ Created after_hours priority configuration")
            else:
                print("✅ After hours configuration already exists")
            
            # Add some sample popular tickers
            popular_tickers = [
                ('SPY', 'SPDR S&P 500 ETF', 'NYSE'),
                ('QQQ', 'Invesco QQQ Trust', 'NASDAQ'),
                ('AAPL', 'Apple Inc.', 'NASDAQ'),
                ('TSLA', 'Tesla, Inc.', 'NASDAQ'),
                ('NVDA', 'NVIDIA Corporation', 'NASDAQ'),
                ('MSFT', 'Microsoft Corporation', 'NASDAQ'),
                ('GOOGL', 'Alphabet Inc.', 'NASDAQ'),
                ('AMZN', 'Amazon.com, Inc.', 'NASDAQ'),
                ('META', 'Meta Platforms, Inc.', 'NASDAQ'),
                ('BTC-USD', 'Bitcoin USD', 'CRYPTO'),
                ('ETH-USD', 'Ethereum USD', 'CRYPTO')
            ]
            
            for symbol, name, exchange in popular_tickers:
                try:
                    await conn.execute('''
                        INSERT INTO tickers (symbol, name, exchange)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (symbol) DO NOTHING
                    ''', symbol, name, exchange)
                except Exception as e:
                    print(f"⚠️  Warning: Could not add ticker {symbol}: {e}")
            
            print("✅ Added popular tickers to database")
    
    async def validate_setup(self):
        """Validate the database setup"""
        print("🔍 Validating database setup...")
        
        async with self.pool.acquire() as conn:
            # Check all tables exist
            tables = [
                'tickers', 'signal_notifications', 'signals_detected',
                'priority_config', 'signal_performance', 'signal_analytics',
                'user_preferences'
            ]
            
            for table in tables:
                count = await conn.fetchval(f'''
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_name = '{table}'
                ''')
                if count == 0:
                    raise Exception(f"Table {table} was not created")
                print(f"✅ Validated table: {table}")
            
            # Check priority configurations
            config_count = await conn.fetchval('SELECT COUNT(*) FROM priority_config')
            print(f"✅ Found {config_count} priority configurations")
            
            # Check ticker count
            ticker_count = await conn.fetchval('SELECT COUNT(*) FROM tickers')
            print(f"✅ Found {ticker_count} tickers in database")
            
            # Test priority config retrieval
            default_config = await conn.fetchrow('''
                SELECT * FROM priority_config WHERE config_name = 'default'
            ''')
            if default_config:
                print(f"✅ Default config: min_priority={default_config['min_priority_level']}")
            else:
                raise Exception("Default priority configuration not found")

async def main():
    """Main setup function"""
    print("🤖 Discord Signal Bot Database Setup")
    print("=====================================\n")
    
    # Check if we're in the right directory
    if not os.path.exists('priority_manager.py'):
        print("❌ Error: Please run this script from the discord-bot directory")
        print("💡 Usage: cd discord-bot && python setup_database.py")
        return False
    
    # Check for required files
    required_files = ['database.py', 'priority_manager.py', 'signal_notifier.py']
    missing_files = [f for f in required_files if not os.path.exists(f)]
    
    if missing_files:
        print(f"❌ Error: Missing required files: {', '.join(missing_files)}")
        print("💡 Please ensure you have all bot files in the current directory")
        return False
    
    # Run database setup
    setup = DatabaseSetup()
    success = await setup.setup_database()
    
    if success:
        print("\n🎉 Setup Complete!")
        print("=" * 60)
        print("Your Discord Signal Bot database is now ready!")
        print()
        print("📋 Next Steps:")
        print("1. Ensure your .env file has DISCORD_TOKEN and DISCORD_CHANNEL_ID")
        print("2. Run: python signal_notifier.py")
        print("3. Test with Discord commands:")
        print("   • !signalreport")
        print("   • !priority")
        print("   • !analytics")
        print()
        print("📖 For more information, see:")
        print("   • ENHANCED_PRIORITY_SYSTEM.md")
        print("   • PRIORITY_GUIDE.md")
        print("   • POSTGRESQL_SETUP.md")
        
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
        
        # Run setup
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n⏹️  Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 