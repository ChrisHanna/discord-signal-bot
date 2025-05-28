# 🐘 PostgreSQL Setup Guide for Discord Signal Bot

This guide will help you set up PostgreSQL for your Discord Signal Bot with proper database configuration, tables, and monitoring.

## 📋 Prerequisites

- Python 3.8+ with asyncpg library
- PostgreSQL 12+ server
- Discord bot token and channel ID

## 🚀 Quick Setup Options

### Option 1: Local PostgreSQL Development

1. **Install PostgreSQL locally:**
   ```bash
   # Windows (using Chocolatey)
   choco install postgresql
   
   # macOS (using Homebrew)
   brew install postgresql
   
   # Ubuntu/Debian
   sudo apt-get install postgresql postgresql-contrib
   ```

2. **Create database and user:**
   ```sql
   -- Connect as postgres user
   psql -U postgres
   
   -- Create database
   CREATE DATABASE discord_bot_db;
   
   -- Create user with password
   CREATE USER discord_bot WITH PASSWORD 'your_secure_password';
   
   -- Grant privileges
   GRANT ALL PRIVILEGES ON DATABASE discord_bot_db TO discord_bot;
   
   -- Exit psql
   \q
   ```

3. **Set environment variable:**
   ```bash
   DATABASE_URL=postgresql://discord_bot:your_secure_password@localhost:5432/discord_bot_db
   ```

### Option 2: Cloud PostgreSQL (Recommended for Production)

#### Railway PostgreSQL
1. Create a Railway account at https://railway.app
2. Create new project → Add PostgreSQL
3. Copy the provided `DATABASE_URL` from the Variables tab
4. Set as environment variable in your bot deployment

#### Supabase PostgreSQL
1. Create account at https://supabase.com
2. Create new project
3. Go to Settings → Database
4. Copy connection string and set as `DATABASE_URL`

#### Heroku PostgreSQL
1. Add Heroku Postgres addon to your app
2. `DATABASE_URL` will be automatically set

## 🗄️ Database Schema

The bot automatically creates these tables on first run:

### Tables Created Automatically:

```sql
-- Stores ticker symbols and metadata
CREATE TABLE tickers (
    symbol VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100),
    exchange VARCHAR(20),
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tracks all signal notifications sent
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
    CONSTRAINT unique_signal UNIQUE(ticker, timeframe, signal_type, signal_date)
);

-- Stores user preferences and settings
CREATE TABLE user_preferences (
    discord_user_id BIGINT PRIMARY KEY,
    tickers TEXT[],
    min_strength VARCHAR(20) DEFAULT 'Medium',
    notifications_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Performance Indexes:
```sql
-- Optimizes signal date queries
CREATE INDEX idx_signal_date ON signal_notifications(signal_date DESC);

-- Optimizes ticker/timeframe lookups
CREATE INDEX idx_ticker_timeframe ON signal_notifications(ticker, timeframe);

-- Optimizes recent notifications queries
CREATE INDEX idx_notified_at ON signal_notifications(notified_at DESC);
```

## ⚙️ Configuration

1. **Copy environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` file:**
   ```env
   # Required: PostgreSQL connection
   DATABASE_URL=postgresql://username:password@hostname:5432/database_name
   
   # Required: Discord settings
   DISCORD_TOKEN=your_bot_token
   DISCORD_CHANNEL_ID=your_channel_id
   ```

3. **Test database connection:**
   ```bash
   python -c "
   import asyncio
   from database import init_database
   
   async def test():
       success = await init_database()
       print('✅ Database connected!' if success else '❌ Connection failed')
   
   asyncio.run(test())
   "
   ```

## 🔧 Database Management Commands

Your Discord bot includes these database management commands:

### In Discord Chat:
- `!stats` - View notification statistics
- `!cleanup` - Clean up old notification records
- `!health` - Check database connection status

### Manual Database Operations:

```python
# Connect and run manual queries
import asyncio
import asyncpg
import os

async def manual_query():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    
    # Example: View recent notifications
    rows = await conn.fetch("""
        SELECT ticker, signal_type, signal_date, notified_at 
        FROM signal_notifications 
        ORDER BY notified_at DESC 
        LIMIT 10
    """)
    
    for row in rows:
        print(dict(row))
    
    await conn.close()

asyncio.run(manual_query())
```

## 📊 Monitoring & Maintenance

### Database Health Checks
The bot automatically monitors:
- Connection pool status
- Query execution times
- Error rates
- Duplicate prevention effectiveness

### Automatic Cleanup
- Old notifications (default: 30 days) are automatically cleaned up
- Configurable via `DB_CLEANUP_DAYS` environment variable
- Manual cleanup available via `!cleanup` command

### Performance Monitoring
Monitor these PostgreSQL metrics:
- Connection count: `SELECT count(*) FROM pg_stat_activity;`
- Database size: `SELECT pg_size_pretty(pg_database_size('discord_bot_db'));`
- Table sizes: `SELECT schemaname,tablename,pg_size_pretty(pg_total_relation_size(tablename::text)) FROM pg_tables;`

## 🐛 Troubleshooting

### Common Issues:

1. **Connection Refused**
   ```
   ❌ Database initialization failed: connection refused
   ```
   - Check if PostgreSQL is running
   - Verify host/port in DATABASE_URL
   - Check firewall settings

2. **Authentication Failed**
   ```
   ❌ Database initialization failed: authentication failed
   ```
   - Verify username/password in DATABASE_URL
   - Check user permissions in PostgreSQL

3. **Database Not Found**
   ```
   ❌ Database initialization failed: database does not exist
   ```
   - Create the database first: `CREATE DATABASE discord_bot_db;`
   - Verify database name in DATABASE_URL

4. **SSL Required (for cloud databases)**
   ```python
   # Add SSL mode to connection string
   DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require
   ```

### Debug Mode:
Enable detailed database logging:
```env
LOG_LEVEL=DEBUG
```

## 🔒 Security Best Practices

1. **Use strong passwords** for database users
2. **Limit database user permissions** to only required tables
3. **Enable SSL** for remote connections
4. **Regular backups** of your notification data
5. **Monitor connection logs** for suspicious activity
6. **Use environment variables** for sensitive credentials

## 📈 Production Deployment

### Railway (Recommended)
1. Connect GitHub repository to Railway
2. Add PostgreSQL service to your project
3. Set environment variables from Railway dashboard
4. Deploy automatically on git push

### Heroku
1. Add Heroku PostgreSQL addon
2. Configure environment variables
3. Deploy via git or GitHub integration

### Docker
```dockerfile
# Example Dockerfile with PostgreSQL support
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "signal_notifier.py"]
```

## 📚 Additional Resources

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [AsyncPG Documentation](https://magicstack.github.io/asyncpg/)
- [Discord.py Database Integration](https://discordpy.readthedocs.io/)
- [Railway PostgreSQL Guide](https://docs.railway.app/databases/postgresql)

---

🎉 **Congratulations!** Your Discord Signal Bot now has persistent PostgreSQL storage for reliable signal tracking and user preferences! 