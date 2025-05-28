# 🗄️ Database Setup Guide

## 🚀 **Quick Setup**

### **For New Users (Fresh Installation):**
```bash
# 1. Navigate to discord-bot directory
cd discord-bot

# 2. Install dependencies
pip install asyncpg python-dotenv

# 3. Set up your .env file with DATABASE_URL
cp .env.example .env
# Edit .env and add your PostgreSQL connection string

# 4. Run the automated setup script
python setup_database.py
```

### **For Existing Users (Migration):**
```bash
# 1. Navigate to discord-bot directory
cd discord-bot

# 2. Backup your database (recommended)
pg_dump your_database_url > backup.sql

# 3. Run the migration script
python migrate_database.py
```

---

## 📋 **Prerequisites**

### **1. PostgreSQL Database**
You need a PostgreSQL database (v12 or higher recommended). Options:

**Cloud Providers:**
- 🚂 [Railway](https://railway.app/) - Easy setup, free tier
- 🐘 [ElephantSQL](https://www.elephantsql.com/) - Managed PostgreSQL
- ☁️ [AWS RDS](https://aws.amazon.com/rds/) - Enterprise grade
- 🌊 [DigitalOcean](https://www.digitalocean.com/products/managed-databases/) - Developer friendly

**Self-Hosted:**
- 🏠 Local PostgreSQL installation
- 🐳 Docker container
- 🛠️ VPS with PostgreSQL

### **2. Python Dependencies**
```bash
pip install asyncpg python-dotenv discord.py
```

### **3. Environment Configuration**
Create `.env` file with your database connection:
```env
DATABASE_URL=postgresql://username:password@hostname:5432/database_name
DISCORD_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=your_channel_id
```

---

## 🛠️ **Setup Scripts**

### **`setup_database.py` - Complete Setup**

**What it does:**
- ✅ Creates all database tables
- ✅ Sets up performance indexes
- ✅ Installs default priority configurations
- ✅ Adds popular ticker symbols
- ✅ Validates the complete setup

**Usage:**
```bash
python setup_database.py
```

**Sample Output:**
```
🚀 Starting Discord Signal Bot Database Setup
============================================================
📁 Loading environment configuration...
✅ Loaded .env file
✅ Environment configuration loaded
🔌 Connecting to PostgreSQL database...
✅ Connected to: PostgreSQL 14.5 on x86_64-pc-linux-gnu...
📊 Creating database tables...
✅ Created tickers table
✅ Created signal_notifications table
✅ Created signals_detected table
✅ Created priority_config table
✅ Created signal_performance table
✅ Created signal_analytics table
✅ Created user_preferences table
⚡ Creating performance indexes...
✅ Created index: idx_signal_date
✅ Created index: idx_detected_priority
...
⚙️ Setting up initial configurations...
✅ Created default priority configuration
✅ Added popular tickers to database
🔍 Validating database setup...
✅ Validated table: tickers
✅ Found 3 priority configurations
✅ Found 11 tickers in database

✅ Database setup completed successfully!
🎉 Your Discord Signal Bot is ready to use!
```

### **`migrate_database.py` - Upgrade Existing Database**

**What it does:**
- 🔄 Adds new columns to existing tables
- 🆕 Creates new tables for enhanced features
- 📊 Preserves all existing data
- ✅ Validates successful migration

**Usage:**
```bash
python migrate_database.py
```

**Sample Output:**
```
🔄 Discord Signal Bot Database Migration
=========================================

⚠️  IMPORTANT: This script will modify your database schema.
📋 It's recommended to backup your database before proceeding.

🔄 Do you want to proceed with the migration? (y/N): y

🔄 Starting Database Migration
==================================================
🔍 Analyzing current database schema...
📊 Found existing tables: signal_notifications, tickers, user_preferences
🔄 signal_notifications table needs priority columns
🆕 New tables to create: signals_detected, priority_config

🚀 Running database migrations...
🔄 Migrating signal_notifications table...
✅ Added priority columns to signal_notifications
🔄 Creating signals_detected table...
✅ Created signals_detected table
...

✅ Migration completed successfully!
🎉 Your database is now upgraded to the enhanced priority system!
```

---

## 📊 **Database Schema**

### **Core Tables:**

#### 1. `signal_notifications` - Sent Notifications
```sql
CREATE TABLE signal_notifications (
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
    pattern_bonus INTEGER DEFAULT 0
);
```

#### 2. `signals_detected` - All Signal Tracking
```sql
CREATE TABLE signals_detected (
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
    signal_data JSONB
);
```

#### 3. `priority_config` - Configuration Management
```sql
CREATE TABLE priority_config (
    id SERIAL PRIMARY KEY,
    config_name VARCHAR(50) UNIQUE NOT NULL,
    min_priority_level VARCHAR(10) NOT NULL,
    critical_threshold INTEGER NOT NULL,
    high_threshold INTEGER NOT NULL,
    medium_threshold INTEGER NOT NULL,
    low_threshold INTEGER NOT NULL,
    vip_tickers TEXT[],
    vip_timeframes TEXT[],
    is_active BOOLEAN DEFAULT TRUE
);
```

### **Performance Tables:**

#### 4. `signal_performance` - Signal Success Tracking
```sql
CREATE TABLE signal_performance (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    signal_date TIMESTAMPTZ NOT NULL,
    price_at_signal DECIMAL(10,2),
    price_after_1h DECIMAL(10,2),
    price_after_1d DECIMAL(10,2),
    success_1h BOOLEAN,
    success_1d BOOLEAN
);
```

#### 5. `signal_analytics` - Daily Analytics
```sql
CREATE TABLE signal_analytics (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    timeframe VARCHAR(5) NOT NULL,
    system VARCHAR(50) NOT NULL,
    total_signals INTEGER DEFAULT 0,
    sent_signals INTEGER DEFAULT 0,
    avg_priority_score DECIMAL(5,1),
    priority_distribution JSONB
);
```

---

## 🔧 **Troubleshooting**

### **Common Issues:**

#### **1. "DATABASE_URL not configured"**
```bash
# Solution: Add DATABASE_URL to your .env file
echo "DATABASE_URL=postgresql://username:password@hostname:5432/database_name" >> .env
```

#### **2. "Database connection failed"**
```bash
# Check your connection string format:
DATABASE_URL=postgresql://user:pass@host:5432/db_name

# Test connection manually:
psql "postgresql://user:pass@host:5432/db_name"
```

#### **3. "Permission denied"**
```bash
# Ensure your database user has necessary permissions:
GRANT CREATE, SELECT, INSERT, UPDATE, DELETE ON DATABASE your_db TO your_user;
GRANT USAGE, CREATE ON SCHEMA public TO your_user;
```

#### **4. "Table already exists" errors**
```bash
# This is normal - the scripts use CREATE TABLE IF NOT EXISTS
# No action needed, the script will continue
```

#### **5. "Module not found" errors**
```bash
# Install missing dependencies:
pip install asyncpg python-dotenv discord.py

# Or install from requirements.txt:
pip install -r requirements.txt
```

### **Manual Database Setup:**

If the automated scripts fail, you can set up manually:

```sql
-- Connect to your PostgreSQL database and run:

-- 1. Create tables (copy from setup_database.py)
CREATE TABLE IF NOT EXISTS tickers (
    symbol VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100),
    exchange VARCHAR(20),
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Create indexes
CREATE INDEX IF NOT EXISTS idx_signal_date ON signal_notifications(signal_date DESC);

-- 3. Insert default configuration
INSERT INTO priority_config 
(config_name, min_priority_level, critical_threshold, high_threshold,
 medium_threshold, low_threshold, vip_tickers, vip_timeframes)
VALUES ('default', 'MEDIUM', 90, 70, 50, 30, 
        ARRAY['SPY', 'QQQ', 'AAPL'], ARRAY['1d', '4h']);
```

---

## 🔍 **Validation**

### **Check Database Setup:**
```bash
# Test database connection
python -c "
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

async def test():
    load_dotenv()
    url = os.getenv('DATABASE_URL')
    conn = await asyncpg.connect(url)
    version = await conn.fetchval('SELECT version()')
    print(f'✅ Connected: {version[:50]}')
    await conn.close()

asyncio.run(test())
"
```

### **Verify Tables:**
```sql
-- Check all tables exist
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- Expected tables:
-- priority_config
-- signal_analytics  
-- signal_notifications
-- signal_performance
-- signals_detected
-- tickers
-- user_preferences
```

### **Test Priority System:**
```bash
# Run the test script
python test_priority.py

# Should output priority scores and recommendations
```

---

## 🚀 **Next Steps**

After successful database setup:

1. **Configure Discord Bot:**
   ```env
   DISCORD_TOKEN=your_bot_token
   DISCORD_CHANNEL_ID=your_channel_id
   ```

2. **Start the Bot:**
   ```bash
   python signal_notifier.py
   ```

3. **Test Commands:**
   ```bash
   !signalreport    # Comprehensive overview
   !analytics       # Signal analytics
   !utilization     # Usage analysis
   !priority        # Priority management
   ```

4. **Monitor Performance:**
   ```bash
   !health          # Bot health
   !missed          # Missed opportunities
   !prioritystats   # Priority statistics
   ```

---

## 📖 **Additional Resources**

- 📋 **ENHANCED_PRIORITY_SYSTEM.md** - Complete system documentation
- 🎯 **PRIORITY_GUIDE.md** - Priority configuration guide
- 🐘 **POSTGRESQL_SETUP.md** - PostgreSQL setup instructions
- 🤖 **README.md** - General bot documentation

---

## 🆘 **Getting Help**

If you encounter issues:

1. **Check the logs** for error messages
2. **Verify your .env configuration**
3. **Test database connectivity** manually
4. **Run validation scripts** to check setup
5. **Review documentation** for configuration options

The database setup is designed to be robust and handle most common scenarios automatically. The scripts include comprehensive error handling and validation to ensure a successful setup.

🎉 **Happy Trading with Enhanced Signal Analytics!** 🚀 