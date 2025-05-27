# �� Discord Signal Bot 🤖📈

Advanced Discord bot that monitors trading signals from your API and sends real-time notifications to your Discord channel.

## ✨ Features

- 🔄 **Real-time Signal Monitoring** - Continuously checks for new trading signals
- 🎯 **Multi-Timeframe Support** - Monitor 1d, 1h, 4h, and more timeframes
- 📊 **Smart Signal Filtering** - Only notifies about recent, strong signals
- 🚫 **Duplicate Prevention** - JSON-based tracking prevents spam notifications
- 📱 **Rich Discord Embeds** - Beautiful, informative signal notifications
- ⏰ **Timestamp Handling** - Full timestamps for 1h data, date-only for 1d
- 🛠️ **Dynamic Ticker Management** - Add/remove tickers without restarting
- 🎛️ **Timeframe Management** - Configure monitoring timeframes dynamically
- 🧹 **Auto-cleanup** - Removes old notifications automatically
- 📈 **Production Ready** - Robust error handling and logging

## 🚀 Quick Start

### 1. Clone and Setup
```bash
git clone https://github.com/ChrisHanna/discord-signal-bot.git
cd discord-signal-bot
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your Discord token and settings
```

### 3. Configure Tickers (JSON)
The bot uses `tickers.json` for dynamic ticker management:
```json
{
    "tickers": ["AAPL", "TSLA", "NVDA", "SPY", "QQQ"],
    "timeframes": ["1d", "1h"],
    "settings": {
        "max_tickers": 50,
        "allowed_timeframes": ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"],
        "default_timeframes": ["1d", "1h"]
    }
}
```

### 4. Run the Bot
```bash
python signal_notifier.py
```

## 🎮 Discord Commands

### 📊 Signal Commands
- `!signals TICKER [TIMEFRAME]` - Get recent signals for a ticker
- `!watch TICKER` - Quick check signals for a ticker (legacy)
- `!test` - Test API connection

### 🎛️ Ticker Management
- `!addticker SYMBOL` - Add a ticker to monitoring list
- `!removeticker SYMBOL` - Remove a ticker from monitoring
- `!listtickers` - List all monitored tickers and configuration

### ⏱️ Timeframe Management
- `!timeframes` - List current timeframe configuration
- `!timeframes add 1h` - Add a timeframe to monitoring
- `!timeframes remove 4h` - Remove a timeframe from monitoring

### 🔧 Bot Management
- `!status` - Show bot status and statistics
- `!config` - Display current configuration
- `!timer` - Show time until next signal check
- `!notifications` - View notification statistics
- `!cleanup` - Manually clean old notifications
- `!clear [NUMBER|all]` - Clear channel messages

## 📋 Configuration

### Environment Variables (.env)
```bash
# Discord Configuration
DISCORD_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=your_channel_id

# API Configuration
API_BASE_URL=https://your-api-url.com
CHECK_INTERVAL=900  # seconds (15 minutes)

# Signal Filtering
MAX_SIGNAL_AGE_DAYS=1
ONLY_STRONG_SIGNALS=false
```

### Ticker Configuration (tickers.json)
The bot automatically creates and manages `tickers.json`:
- **tickers**: Array of ticker symbols to monitor
- **timeframes**: Array of timeframes to check
- **settings**: Configuration limits and allowed values

**Examples:**
```bash
!addticker BTC-USD        # Add Bitcoin
!removeticker NVDA        # Remove NVIDIA
!timeframes add 4h        # Add 4-hour timeframe
!listtickers              # View all configuration
```

## 🔄 How It Works

1. **Signal Detection**: Bot checks your API every 15 minutes for new signals
2. **Smart Filtering**: Only processes recent signals (last 24 hours)
3. **Duplicate Prevention**: JSON tracking prevents repeat notifications
4. **Rich Notifications**: Sends beautiful Discord embeds with signal details
5. **Auto-cleanup**: Removes old notification records (7+ days)

## 📈 Signal Types Supported

- **Wave Trend**: WT Gold/Red Buy/Sell signals
- **RSI3M3+**: Bullish/Bearish entry signals
- **Patterns**: Technical pattern recognition
- **Exhaustion**: Market exhaustion signals

## 🚀 Deployment

### Railway (Recommended)
1. Fork this repository
2. Connect to Railway
3. Set environment variables
4. Deploy!

Railway configuration included:
- `railway.json` - Service configuration
- `Procfile` - Process configuration

### Docker
```dockerfile
FROM python:3.9-slim
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["python", "signal_notifier.py"]
```

### Heroku
```bash
heroku create your-signal-bot
heroku config:set DISCORD_TOKEN=your_token
heroku config:set DISCORD_CHANNEL_ID=your_channel_id
git push heroku main
```

## 🛠️ Development

### Test Scripts
- `test_ticker_management.py` - Test ticker management features
- `test_1h_timestamps.py` - Test timestamp handling
- `test_enhanced_signals.py` - Test signal detection
- `test_discord_formatting.py` - Test message formatting
- `test_json_cleanup.py` - Test cleanup functionality

### Run Tests
```bash
python test_ticker_management.py
python test_enhanced_signals.py
```

## 📚 API Requirements

Your API should provide endpoints:
- `/signals/timeline?ticker=AAPL&interval=1d&period=1y`
- Return JSON with signals containing:
  - `system`: Signal system name
  - `date`: Signal date
  - `signal_type`: Type of signal
  - `strength`: Signal strength

## 🔒 Security

- `.env` file excluded from git
- `tickers.json` excluded (user-specific)
- `last_notifications.json` excluded (runtime data)
- Token validation on startup
- Error handling for API failures

## 📊 File Structure

```
discord-signal-bot/
├── signal_notifier.py          # Main bot code
├── tickers.json               # Ticker configuration (auto-created)
├── last_notifications.json    # Notification tracking (auto-created)
├── requirements.txt           # Python dependencies
├── .env.example              # Environment template
├── .gitignore               # Git exclusions
├── Procfile                 # Process configuration
├── railway.json            # Railway deployment config
├── CONFIG_GUIDE.md         # Detailed configuration guide
└── test_*.py              # Test scripts
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## 🆘 Support

- Create an issue for bugs
- Check existing issues for solutions
- Test scripts help diagnose problems
- CONFIG_GUIDE.md for detailed setup

## 🎯 Production Ready

This bot is designed for production use with:
- ✅ Comprehensive error handling
- ✅ Automatic cleanup and maintenance
- ✅ Robust duplicate prevention
- ✅ Dynamic configuration management
- ✅ Rich logging and monitoring
- ✅ Multi-environment deployment support

## Railway Deployment Monitoring

The bot includes comprehensive health monitoring features specifically designed for Railway deployments:

### Health Check Commands

- `!health` - Complete bot health status with Railway info
- `!uptime` - Show bot uptime and deployment details  
- `!status` - Basic bot operational status
- `!timer` - Time until next signal check

### Railway Health Features

- **Automatic Railway Detection**: Detects Railway environment variables
- **Enhanced Logging**: Detailed logs for Railway console monitoring
- **Health Alerts**: Automatic Discord notifications for critical errors
- **Performance Tracking**: Success rates, error counts, uptime stats

### Monitoring Your Railway Deployment

1. **Check Health Status**: Use `!health` to get a comprehensive overview
2. **Monitor Logs**: Check Railway console for detailed logging
3. **Verify Timer**: Use `!timer` to ensure signal checks are running
4. **Track Uptime**: Use `!uptime` to see how long the bot has been running

### Railway Health Check Script

Run the health check script before deployment:

```bash
python railway_health.py
```

This verifies:
- ✅ All required files are present
- ✅ Environment variables are configured  
- ✅ API connection is working
- ✅ Configuration files are valid

### Troubleshooting Railway Issues

If the bot isn't working on Railway:

1. **Check Environment Variables**: Ensure all required vars are set
2. **Verify API Access**: Make sure your API endpoint is accessible
3. **Monitor Health**: Use `!health` command to identify issues
4. **Check Logs**: Review Railway deployment logs for errors
5. **Test Locally**: Run `railway_health.py` to verify configuration 