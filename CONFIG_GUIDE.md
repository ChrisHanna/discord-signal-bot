# 🛠️ Discord Bot Configuration Guide

Your Discord bot is now fully configurable! Here's how to customize it for your trading style.

## ⚙️ Configuration File (`.env`)

All settings are controlled through the `.env` file in the `discord-bot` folder.

### 📊 **Ticker Configuration**
```bash
# Comma-separated list (no spaces around commas work too)
TICKERS=AAPL,TSLA,NVDA,SPY,QQQ

# Crypto examples:
TICKERS=BTC-USD,ETH-USD,DOGE-USD

# Mix of stocks and ETFs:
TICKERS=AAPL,SPY,QQQ,MSFT,GOOGL,IWM,DIA
```

### ⏰ **Timeframe Options**
```bash
TIMEFRAME=1d   # Daily (default, most reliable)
TIMEFRAME=1h   # Hourly (if your API supports it)
TIMEFRAME=4h   # 4-hour (if your API supports it) 
TIMEFRAME=1w   # Weekly (if your API supports it)
```

### 🔔 **Notification Frequency**
```bash
CHECK_INTERVAL=300   # 5 minutes (very active)
CHECK_INTERVAL=900   # 15 minutes (active)
CHECK_INTERVAL=1800  # 30 minutes (moderate)
CHECK_INTERVAL=3600  # 1 hour (relaxed)
```

### 🎯 **Signal Filtering**
```bash
# Only notify about fresh signals
MAX_SIGNAL_AGE_DAYS=1  # Signals from today only
MAX_SIGNAL_AGE_DAYS=3  # Signals from last 3 days
MAX_SIGNAL_AGE_DAYS=7  # Signals from last week

# Signal strength filtering
ONLY_STRONG_SIGNALS=false  # All signals (default)
ONLY_STRONG_SIGNALS=true   # Only Strong/Very Strong signals
```

## 🎮 **Preset Configurations**

### 📈 Day Trading Setup
```bash
TICKERS=SPY,QQQ,TSLA,NVDA,AAPL
TIMEFRAME=1h
CHECK_INTERVAL=300
MAX_SIGNAL_AGE_DAYS=1
ONLY_STRONG_SIGNALS=true
```

### 📊 Swing Trading Setup  
```bash
TICKERS=AAPL,MSFT,GOOGL,AMZN,TSLA,NVDA,SPY,QQQ
TIMEFRAME=1d
CHECK_INTERVAL=1800
MAX_SIGNAL_AGE_DAYS=2
ONLY_STRONG_SIGNALS=false
```

### 🪙 Crypto Focus
```bash
TICKERS=BTC-USD,ETH-USD,ADA-USD,DOGE-USD
TIMEFRAME=1h
CHECK_INTERVAL=600
MAX_SIGNAL_AGE_DAYS=1
ONLY_STRONG_SIGNALS=true
```

### 📈 Index/ETF Monitoring
```bash
TICKERS=SPY,QQQ,IWM,DIA,VTI,VXUS
TIMEFRAME=1d
CHECK_INTERVAL=3600
MAX_SIGNAL_AGE_DAYS=3
ONLY_STRONG_SIGNALS=false
```

## 🎯 **Discord Commands**

Once your bot is running, use these commands in your Discord channel:

- `!config` - Show current configuration
- `!status` - Check bot status  
- `!signals AAPL` - Get recent signals for a ticker
- `!test` - Test API connection

## 🔄 **Applying Changes**

After editing your `.env` file:

1. **Stop the bot** (Ctrl+C)
2. **Restart it** (`python signal_notifier.py`)
3. The new configuration will be loaded automatically

## 💡 **Pro Tips**

### 🎯 **Start Small**
Begin with 3-5 tickers you know well:
```bash
TICKERS=AAPL,SPY,TSLA
```

### ⏱️ **Balance Frequency**
- **Too frequent** = Spam and API rate limits
- **Too infrequent** = Missing timely signals
- **Sweet spot**: 15-30 minutes for most users

### 🎛️ **Gradual Filtering**
Start with all signals, then add filters:
```bash
# Week 1: See everything
ONLY_STRONG_SIGNALS=false
MAX_SIGNAL_AGE_DAYS=3

# Week 2: Focus on strong signals  
ONLY_STRONG_SIGNALS=true
MAX_SIGNAL_AGE_DAYS=2

# Week 3: Only today's strong signals
ONLY_STRONG_SIGNALS=true
MAX_SIGNAL_AGE_DAYS=1
```

### 📱 **Multiple Bots**
Create different bots for different strategies:
- **Bot 1**: Day trading (1h, frequent checks)
- **Bot 2**: Swing trading (1d, less frequent)
- **Bot 3**: Crypto-only (24/7 monitoring)

## 🆘 **Troubleshooting**

### ❌ No Signals?
- Check if your tickers are valid
- Verify API is running (`!test` command)
- Try relaxing filters temporarily

### 🔄 Too Many Notifications?
- Increase `CHECK_INTERVAL`
- Set `ONLY_STRONG_SIGNALS=true`
- Reduce `MAX_SIGNAL_AGE_DAYS`

### 📊 Wrong Timeframe?
- Make sure your API supports the timeframe
- Start with `1d` (most reliable)
- Check API logs for errors

Happy Trading! 🚀 