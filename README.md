# 🤖 Discord Signal Bot with Advanced Analytics

A sophisticated Discord bot that monitors trading signals from your API and provides comprehensive analytics, priority-based notifications, and historical performance tracking.

## ✨ Features

### 📊 Signal Monitoring
- **Real-time signal detection** from multiple trading systems
- **Multi-timeframe support** (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)
- **Intelligent priority scoring** with VIP ticker/timeframe boosts
- **Smart scheduling** aligned with market hours and candle closes
- **Duplicate detection** to prevent notification spam

### 📈 Advanced Analytics
- **Historical performance tracking** with PostgreSQL database
- **Signal utilization analysis** and trend identification
- **Best performer identification** across tickers and systems
- **Priority distribution analytics** for optimization insights
- **Missed opportunity tracking** for threshold tuning

### 🎯 Priority Management
- **Dynamic priority scoring** (10-130+ points scale)
- **VIP ticker and timeframe boosts** for important assets
- **Configurable thresholds** (Critical, High, Medium, Low, Minimal)
- **Pattern and urgency bonuses** for special signal types

### 🏥 Health Monitoring
- **Comprehensive health checks** for all system components
- **Database connection monitoring** with automatic recovery
- **Performance metrics tracking** and error rate monitoring
- **Railway deployment support** with health endpoints

## 🚀 Quick Start

### Prerequisites
- Python 3.7+
- PostgreSQL database
- Discord Bot Token
- Trading API endpoint

### Installation

1. **Clone and setup**
```bash
git clone <repository>
cd discord-bot
pip install -r requirements.txt
```

2. **Environment Configuration**
Copy `.env.example` to `.env` and configure:

```env
# Discord Configuration
DISCORD_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=your_channel_id

# Trading API Configuration
API_BASE_URL=http://localhost:5000
CHECK_INTERVAL=1600

# Smart Scheduler (Recommended)
USE_SMART_SCHEDULER=true

# Database Configuration (PostgreSQL)
DATABASE_URL=postgresql://user:password@host:port/database

# Ticker Configuration
TICKERS=AAPL,TSLA,NVDA,SPY,QQQ
TIMEFRAMES=1d,1h

# Signal Filtering
MAX_SIGNAL_AGE_DAYS=1
ONLY_STRONG_SIGNALS=false
```

3. **Database Setup**
```bash
# Automatic setup (recommended)
python setup_database.py

# Or migrate existing database
python migrate_database.py
```

4. **Run the Bot**
```bash
python signal_notifier.py
```

## 📋 Commands Reference

### 📊 Signal Commands
- `!signals [TICKER] [TIMEFRAME]` - Get latest signals for a ticker
- `!test` - Test API connection
- `!timer` - Show time until next signal check
- `!schedule` - Show smart scheduler information

### 📈 Analytics Commands
- `!analytics [DAYS]` - Signal analytics and trends (default: 7 days)
- `!performance` - Overall historical performance summary
- `!bestperformers [DAYS]` - Top performing signal combinations (default: 30 days)
- `!utilization` - Signal utilization analysis (last 24 hours)
- `!missed [HOURS]` - High-priority signals that were skipped (default: 24 hours)
- `!signalreport` - Comprehensive signal detection and utilization report
- `!updateanalytics [DATE]` - Manually update analytics for specific date
- `!analyticshealth` - Analytics system health check

### ⚙️ Configuration Commands
- `!config` - Show current bot configuration
- `!addticker SYMBOL` - Add ticker to monitoring list
- `!removeticker SYMBOL` - Remove ticker from monitoring list
- `!listtickers` - List all monitored tickers
- `!timeframes [add/remove] [TIMEFRAME]` - Manage timeframes
- `!dbsync` - Check database synchronization status

### 🎯 Priority Management
- `!priority` - Show current priority settings
- `!priority level <LEVEL>` - Set minimum priority level (CRITICAL|HIGH|MEDIUM|LOW|MINIMAL)
- `!priority vip add <TICKER>` - Add ticker to VIP list
- `!priority vip remove <TICKER>` - Remove ticker from VIP list
- `!priority test <TICKER>` - Test priority scoring for a ticker
- `!prioritystats` - Priority distribution statistics

### 🏥 Status & Health Commands
- `!status` - Bot status overview
- `!health` - Comprehensive health check for Railway deployment
- `!uptime` - Bot uptime information
- `!notifications` - Notification statistics from database
- `!scheduler [start/stop/restart]` - Control scheduler

### 🛠️ Utility Commands
- `!cleanup` - Manual database cleanup (removes entries >30 days)
- `!clear [AMOUNT]` - Clear channel messages
- `!help` - Show complete command reference

## 🎯 Priority System

### Scoring Components
- **Base Score:** 10 points
- **Strength Bonus:** 0-25 points (Very Strong: 25, Strong: 15, Moderate: 10, Weak: 5)
- **System Bonus:** 0-20 points (based on system reliability)
- **VIP Ticker Bonus:** 15 points
- **VIP Timeframe Bonus:** 10 points
- **Urgency Bonus:** 0-20 points (based on signal recency)
- **Pattern Bonus:** 0-30 points (special patterns like "Gold" signals)

### Priority Levels
- **🚨 CRITICAL:** 90+ points
- **⚠️ HIGH:** 70-89 points
- **📊 MEDIUM:** 50-69 points
- **📢 LOW:** 30-49 points
- **📝 MINIMAL:** <30 points

## 🗄️ Database Schema

### Core Tables
- **`tickers`** - Monitored ticker symbols
- **`signal_notifications`** - Sent Discord notifications
- **`signals_detected`** - All detected signals (sent + skipped)
- **`signal_analytics`** - Daily aggregated performance metrics
- **`priority_config`** - Priority system configuration
- **`user_preferences`** - User-specific settings

### Analytics Features
- **Daily summaries** with signal counts and priority distributions
- **Historical performance tracking** for tickers and systems
- **Utilization rate monitoring** (sent/detected ratio)
- **Best performer identification** based on utilization and priority
- **Trend analysis** for optimization insights

## 🚂 Railway Deployment

### Environment Variables
Set these in your Railway environment:
```env
RAILWAY_ENVIRONMENT=production
DATABASE_URL=<postgresql_connection_string>
DISCORD_TOKEN=<your_bot_token>
DISCORD_CHANNEL_ID=<your_channel_id>
API_BASE_URL=<your_trading_api_url>
USE_SMART_SCHEDULER=true
```

### Health Monitoring
- Bot includes comprehensive health checks for Railway
- Use `!health` command for detailed system status
- Automatic error recovery and notification
- Performance metrics tracking

## 🔧 Configuration Options

### Smart Scheduler (Recommended)
```env
USE_SMART_SCHEDULER=true
```
- Aligns signal checks with hourly candle closes
- Market hours awareness (9:30 AM - 4:00 PM EST)
- Reduced API calls while maintaining signal accuracy

### Ticker Management
```env
# Simple multi-timeframe (all tickers on all timeframes)
TICKERS=AAPL,TSLA,NVDA,SPY,QQQ
TIMEFRAMES=1d,1h

# Advanced per-ticker timeframes
TICKER_TIMEFRAMES=AAPL:1d,TSLA:1h,BTC-USD:15m
```

### Signal Filtering
```env
MAX_SIGNAL_AGE_DAYS=1          # Only signals from last 1 day
ONLY_STRONG_SIGNALS=false      # Include all signal strengths
```

## 📊 Analytics Dashboard

Access real-time analytics through Discord commands:

1. **Daily Overview:** `!analytics`
2. **Performance Summary:** `!performance`
3. **Top Performers:** `!bestperformers`
4. **Utilization Analysis:** `!utilization`
5. **Missed Opportunities:** `!missed`
6. **Comprehensive Report:** `!signalreport`

## 🚨 Troubleshooting

### Common Issues

**Bot not responding:**
- Check `!health` for system status
- Verify Discord token and channel ID
- Ensure database connection is working

**No signals detected:**
- Test API connection with `!test`
- Check ticker configuration with `!config`
- Verify API endpoint is accessible

**Analytics not updating:**
- Use `!analyticshealth` to check analytics system
- Manually update with `!updateanalytics`
- Check database connection

**Database connection issues:**
- Verify DATABASE_URL environment variable
- Run `python setup_database.py` to initialize
- Check PostgreSQL server status

### Debug Commands
- `!analyticshealth` - Check analytics system health
- `!dbsync` - Verify database synchronization
- `!health` - Comprehensive system health check
- `!test` - Test API connectivity

## 🔐 Security Considerations

- Store sensitive credentials in environment variables
- Use PostgreSQL connection over SSL in production
- Regularly rotate Discord bot token
- Monitor database access logs
- Use Railway's built-in security features

## 📈 Performance Optimization

### Database
- Automatic indexing for query optimization
- Periodic cleanup of old data (configurable)
- Connection pooling for efficient database usage

### API Usage
- Smart scheduling reduces unnecessary API calls
- Rate limiting to prevent API throttling
- Efficient duplicate detection

### Discord
- Rate limiting compliance
- Embed optimization for better UX
- Automatic error recovery

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Test thoroughly with `python test_database.py`
4. Submit a pull request

## 📄 License

[Add your license here]

## 🆘 Support

For issues and questions:
1. Check this README and troubleshooting section
2. Use `!help` command for command reference
3. Run diagnostic commands (`!health`, `!analyticshealth`)
4. Check logs for detailed error information

---

**🎉 Ready to monitor your trading signals with advanced analytics!** 🚀 