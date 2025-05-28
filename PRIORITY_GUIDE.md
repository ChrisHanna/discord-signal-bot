# 🎯 Priority Alert System Guide

The Discord Signal Bot now includes an advanced **Priority Management System** that intelligently filters and ranks trading signals based on importance, helping you focus on the most critical alerts.

## 🚀 **How Priority Scoring Works**

Every signal receives a **priority score** based on multiple factors:

### 📊 **Scoring Components**

| Component | Points | Description |
|-----------|--------|-------------|
| **Base Score** | 10 | Every signal starts with 10 points |
| **Strength Bonus** | 0-25 | Very Strong (25), Strong (20), Medium (10), Weak (5) |
| **System Bonus** | 5-20 | Wave Trend (20), RSI3M3+ (18), Divergence (16), etc. |
| **VIP Ticker Bonus** | 0-15 | Major tickers like SPY, AAPL, TSLA get 15 bonus points |
| **VIP Timeframe Bonus** | 0-10 | Important timeframes like 1d, 4h get 10 bonus points |
| **Urgency Bonus** | 4-20 | Recent signals get more points (Just now: 20, 1h ago: 16, etc.) |
| **Pattern Bonus** | 0-30 | Critical patterns like "Gold Buy" get up to 30 bonus points |

### 🏆 **Priority Levels**

Based on the total score, signals are classified into 5 priority levels:

| Priority | Score Range | Emoji | Description |
|----------|-------------|-------|-------------|
| **CRITICAL** | 90+ | 🚨🔥 | Must-see alerts, immediate action required |
| **HIGH** | 70-89 | ⚠️🔥 | Very important signals, high attention |
| **MEDIUM** | 50-69 | 📊⭐ | Standard importance, regular monitoring |
| **LOW** | 30-49 | 📢💙 | Less critical, nice to know |
| **MINIMAL** | <30 | 📝💚 | Low importance, informational only |

## ⚙️ **Configuration Options**

### Environment Variables (`.env` file):

```env
# Minimum priority level to send notifications
MIN_PRIORITY_LEVEL=MEDIUM

# Priority thresholds (adjust these to fine-tune sensitivity)
PRIORITY_CRITICAL_THRESHOLD=90
PRIORITY_HIGH_THRESHOLD=70
PRIORITY_MEDIUM_THRESHOLD=50
PRIORITY_LOW_THRESHOLD=30

# VIP assets get priority treatment
VIP_TICKERS=SPY,QQQ,AAPL,TSLA,NVDA,MSFT,GOOGL,AMZN,META,BTC-USD,ETH-USD
VIP_TIMEFRAMES=1d,4h

# Advanced settings
ONLY_CRITICAL_ALERTS=false
SUPPRESS_WEAK_SIGNALS=true
MAX_ALERTS_PER_HOUR=10
```

## 🎮 **Discord Commands**

### `!priority` - Priority Management
```bash
# Show current priority settings
!priority

# Set minimum priority level
!priority level CRITICAL
!priority level HIGH
!priority level MEDIUM
!priority level LOW
!priority level MINIMAL

# Manage VIP tickers
!priority vip add AMZN
!priority vip remove COIN

# Test priority scoring for a ticker
!priority test AAPL
```

### `!prioritystats` - View Priority Statistics
Shows priority thresholds, scoring system details, and recent activity.

## 🎯 **Usage Examples**

### Example 1: Only Critical Alerts
```env
MIN_PRIORITY_LEVEL=CRITICAL
```
- Only signals scoring 90+ points will be sent
- Perfect for high-noise environments
- Ensures you only see the most important signals

### Example 2: Balanced Approach
```env
MIN_PRIORITY_LEVEL=MEDIUM
VIP_TICKERS=SPY,QQQ,AAPL,TSLA,NVDA
```
- Receives medium and higher priority signals (50+ points)
- VIP tickers get preferential treatment
- Good balance between coverage and noise reduction

### Example 3: Complete Coverage
```env
MIN_PRIORITY_LEVEL=LOW
SUPPRESS_WEAK_SIGNALS=false
```
- Receives most signals except minimal priority
- Good for comprehensive market monitoring
- Higher notification volume

## 📈 **Signal Examples by Priority**

### 🚨 **CRITICAL Priority (90+ points)**
- SPY WT Gold Buy Signal (Very Strong) - Recent
- AAPL Zero Line Reject Buy (Strong) - Just happened
- QQQ Extreme Oversold signal (Strong) - VIP ticker

### ⚠️ **HIGH Priority (70-89 points)**
- TSLA Fast Money Buy (Strong) - VIP ticker
- NVDA Bullish Divergence (Strong) - Within 1 hour
- MSFT RSI3M3+ entry (Very Strong) - Recent

### 📊 **MEDIUM Priority (50-69 points)**
- SPY WT Buy Signal (Medium) - VIP ticker
- AAPL RSI Trend Break (Strong) - Older signal
- Regular ticker with strong signal and good system

### 📢 **LOW Priority (30-49 points)**
- AMD Bullish Cross (Weak) - Non-VIP ticker
- COIN Reversal Signal (Medium) - Older signal
- Lower-tier systems with moderate strength

### 📝 **MINIMAL Priority (<30 points)**
- Unknown ticker, weak signal, old timing
- Poor system reliability, minimal pattern importance

## 🔧 **Customization Tips**

### Increase Sensitivity (More Alerts):
1. Lower `MIN_PRIORITY_LEVEL` to `LOW` or `MINIMAL`
2. Reduce thresholds: `PRIORITY_MEDIUM_THRESHOLD=40`
3. Add more VIP tickers: `VIP_TICKERS=SPY,QQQ,AAPL,TSLA,NVDA,AMD,COIN`

### Decrease Sensitivity (Fewer Alerts):
1. Raise `MIN_PRIORITY_LEVEL` to `HIGH` or `CRITICAL`
2. Increase thresholds: `PRIORITY_CRITICAL_THRESHOLD=100`
3. Limit VIP tickers to only the most important

### Focus on Specific Assets:
```env
VIP_TICKERS=SPY,QQQ
MIN_PRIORITY_LEVEL=MEDIUM
```
This setup prioritizes major index ETFs while filtering out noise from individual stocks.

### Day Trading Setup:
```env
VIP_TIMEFRAMES=15m,1h,4h
MIN_PRIORITY_LEVEL=HIGH
URGENCY_BONUS_MULTIPLIER=2.0
```
Emphasizes shorter timeframes and recent signals for active trading.

## 🧪 **Testing Your Configuration**

### 1. Use the Test Script:
```bash
python test_priority.py
```
This shows how different signals would be scored with your current settings.

### 2. Use Discord Commands:
```bash
!priority test AAPL
!prioritystats
```

### 3. Monitor in Real-Time:
Watch the bot logs to see priority scores for actual signals:
```
🎯 Priority notification: AAPL WT Buy Signal - Priority: HIGH (Score: 78)
⏸️ Skipped low priority: COIN Reversal - Priority: LOW (Score: 34)
```

## 💡 **Best Practices**

### Start Conservative:
1. Begin with `MIN_PRIORITY_LEVEL=MEDIUM`
2. Monitor for a few days
3. Adjust thresholds based on signal volume and quality

### Use VIP Lists Strategically:
- Add your most-watched assets to `VIP_TICKERS`
- Include your preferred timeframes in `VIP_TIMEFRAMES`
- Don't add too many (diminishes the VIP effect)

### Monitor and Adjust:
- Use `!prioritystats` regularly to review activity
- Adjust thresholds if you're getting too many/few alerts
- Test changes with `!priority test` before applying

### Time-Based Adjustments:
- Higher sensitivity during market hours
- Lower sensitivity after-hours and weekends
- Consider creating different configurations for different market conditions

## 🎛️ **Advanced Configuration**

### Custom Priority Patterns:
Edit `priority_manager.py` to add your own signal patterns:
```python
self.SIGNAL_PATTERNS = {
    'Your Custom Pattern': 25,
    'Another Important Signal': 20,
    # ... existing patterns
}
```

### Dynamic VIP Lists:
You can modify VIP tickers through Discord commands:
```bash
!priority vip add AMZN     # Add Amazon to VIP list
!priority vip remove COIN  # Remove Coinbase from VIP list
```

### Multiple Priority Profiles:
Create different `.env` files for different market conditions:
- `.env.trading` - Active trading (high sensitivity)
- `.env.monitoring` - Passive monitoring (medium sensitivity)  
- `.env.critical` - Only critical alerts (low sensitivity)

## 📊 **Monitoring Priority Performance**

### Key Metrics to Track:
1. **Signal Volume**: How many alerts per day/hour
2. **Priority Distribution**: Percentage of each priority level
3. **Hit Rate**: How often high-priority signals lead to good trades
4. **False Positives**: Low-value signals that still get through

### Optimization Process:
1. **Week 1**: Use default settings, collect data
2. **Week 2**: Analyze which signals were most valuable
3. **Week 3**: Adjust thresholds and VIP lists accordingly
4. **Week 4**: Fine-tune based on performance

---

## 🎉 **Getting Started**

1. **Copy the priority configuration** from `.env.example` to your `.env` file
2. **Start with default settings** (`MIN_PRIORITY_LEVEL=MEDIUM`)
3. **Test the system**: Run `python test_priority.py`
4. **Monitor in Discord**: Use `!priority` and `!prioritystats`
5. **Adjust as needed** based on your preferences and signal volume

The priority system ensures you never miss critical signals while filtering out the noise, giving you a professional-grade alert system for your trading strategy! 🚀 