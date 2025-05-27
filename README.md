# 🤖 Discord Signal Bot

Advanced Discord bot that monitors trading signals and sends real-time notifications to your Discord channel.

## ✨ Features

- 📊 **Multi-timeframe Support**: 1d, 1h, 4h, 2h, 30m, 15m, 5m
- 🎯 **Smart Signal Detection**: Wave Trend, RSI3M3+, Patterns, Exhaustion, Divergences
- 🚫 **Duplicate Prevention**: JSON-based notification tracking
- ⚡ **Real-time Monitoring**: Configurable check intervals
- 💬 **Rich Discord Integration**: Beautiful embeds, reactions, commands
- 🧹 **Auto-cleanup**: Automatic old notification cleanup

## 🚀 Quick Deployment

### **Option 1: Railway.app (Recommended)**

1. **Push to GitHub:**
   ```bash
   git add .
   git commit -m "Deploy Discord Signal Bot"
   git push origin main
   ```

2. **Deploy on Railway:**
   - Go to [railway.app](https://railway.app)
   - Click "Deploy from GitHub repo"
   - Select your repository
   - Add environment variables (see below)
   - Deploy! 🎉

3. **Environment Variables:**
   ```
   DISCORD_TOKEN=your_bot_token
   DISCORD_CHANNEL_ID=your_channel_id
   API_BASE_URL=your_api_url
   CHECK_INTERVAL=1600
   TICKERS=AAPL,TSLA,NVDA,SPY,QQQ
   TIMEFRAMES=1d,1h
   ```

### **Option 2: Render.com (Free)**

1. **Connect GitHub** to Render
2. **Create Web Service** with these settings:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python signal_notifier.py`
3. **Add Environment Variables** from `.env.example`

### **Option 3: DigitalOcean Droplet**

1. **Create Ubuntu Droplet** ($6/month)
2. **SSH into server:**
   ```bash
   ssh root@your_server_ip
   ```
3. **Install dependencies:**
   ```bash
   apt update
   apt install python3 python3-pip git -y
   ```
4. **Clone and setup:**
   ```bash
   git clone your_repo_url
   cd discord-bot
   pip3 install -r requirements.txt
   ```
5. **Create systemd service** for auto-restart:
   ```bash
   sudo nano /etc/systemd/system/discord-bot.service
   ```
   ```ini
   [Unit]
   Description=Discord Signal Bot
   After=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/root/discord-bot
   ExecStart=/usr/bin/python3 signal_notifier.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```
6. **Enable and start:**
   ```bash
   sudo systemctl enable discord-bot.service
   sudo systemctl start discord-bot.service
   ```

## 🎮 Discord Commands

| Command | Description |
|---------|-------------|
| `!signals AAPL 1h` | Get recent signals for ticker/timeframe |
| `!status` | Check bot status and timing |
| `!timer` | Show countdown to next check |
| `!config` | Display bot configuration |
| `!notifications` | Show notification statistics |
| `!cleanup` | Clean old notification entries |
| `!clear all` | Clear all messages in channel |
| `!test` | Test API connection |

## ⚙️ Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Required
DISCORD_TOKEN=your_bot_token_here
DISCORD_CHANNEL_ID=123456789012345678
API_BASE_URL=https://your-api.com

# Optional  
CHECK_INTERVAL=1600                    # Check every ~26 minutes
TICKERS=AAPL,TSLA,NVDA                # Comma-separated tickers
TIMEFRAMES=1d,1h                       # Comma-separated timeframes
MAX_SIGNAL_AGE_DAYS=1                  # Filter signals by age
ONLY_STRONG_SIGNALS=false              # Only notify strong signals
```

## 📊 Supported Timeframes

- **1d** (Daily) - 1 year of data
- **1h** (Hourly) - 1 month of data  
- **4h, 2h** (Medium) - 3 months of data
- **30m, 15m, 5m** (Intraday) - 1 week of data

## 🔧 Development

**Local Setup:**
```bash
git clone your_repo_url
cd discord-bot
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your tokens
python signal_notifier.py
```

**Testing:**
```bash
python test_enhanced_signals.py
python test_json_cleanup.py
python test_1h_timestamps.py
```

## 📈 Performance

- ⚡ **Fast API calls** with optimized periods
- 🧹 **Automatic cleanup** prevents file growth
- 🔒 **Atomic writes** prevent data corruption
- 📊 **Smart filtering** reduces notification spam
- 💾 **Memory efficient** with periodic cleanup

## 🆘 Troubleshooting

**Bot not responding?**
- Check `!status` command
- Verify API_BASE_URL is accessible
- Check Discord token permissions

**No notifications?**
- Run `!notifications` to check stats
- Verify signals meet notification criteria
- Check `!config` for ticker/timeframe setup

**Deployment issues?**
- Ensure all environment variables are set
- Check logs for error messages
- Verify requirements.txt includes all dependencies

## 🎯 Production Ready

✅ **24/7 Monitoring** - Automatic restarts and error handling  
✅ **Duplicate Prevention** - Smart notification tracking  
✅ **Performance Optimized** - Efficient data usage  
✅ **Discord Integrated** - Rich embeds and commands  
✅ **Highly Configurable** - Environment-based settings  

## 📝 License

MIT License - Feel free to modify and distribute!

---

**Made with ❤️ for the trading community** 🚀 