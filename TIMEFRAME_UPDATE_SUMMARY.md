# Discord Bot Timeframe Support Update

## Overview
Updated the Discord bot to support all timeframes that your API supports: **15m, 30m, 1h, 3h, 6h, 1d, 2d, 3d, 1wk**

## Changes Made

### 1. Updated DatabaseConfig Class (`signal_notifier.py`)
**Before:**
```python
self.allowed_timeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w']
```

**After:**
```python
self.allowed_timeframes = ['15m', '30m', '1h', '3h', '6h', '1d', '2d', '3d', '1wk']
```

### 2. Updated Period Mapping Logic (`signal_notifier.py`)
Enhanced the period mapping to support new timeframes with optimal data coverage:

- `15m, 30m` → `1wk` (1 week for intraday)
- `1h` → `1mo` (1 month for hourly)
- `3h, 6h` → `3mo` (3 months for medium hourly)
- `1d` → `1y` (1 year for daily)
- `2d, 3d` → `1y` (1 year for multi-day)
- `1wk` → `5y` (5 years for weekly)

### 3. Updated Signals Command Validation (`signal_notifier.py`)
**Before:**
```python
valid_timeframes = ['1d', '1h', '4h', '15m', '5m']
```

**After:**
```python
valid_timeframes = ['15m', '30m', '1h', '3h', '6h', '1d', '2d', '3d', '1wk']
```

### 4. Updated Priority Manager (`priority_manager.py`)
Changed default VIP timeframes from unsupported `4h` to supported timeframes:

**Before:**
```python
self.vip_timeframes = set(['1d', '4h'])
env_vip_timeframes = os.getenv('VIP_TIMEFRAMES', '1d,4h')
```

**After:**
```python
self.vip_timeframes = set(['1d', '1h'])
env_vip_timeframes = os.getenv('VIP_TIMEFRAMES', '1d,1h')
```

## Supported Commands

### Timeframe Management
```bash
!timeframes list                    # Show current timeframes
!timeframes add 3h                  # Add 3-hour timeframe
!timeframes add 6h                  # Add 6-hour timeframe
!timeframes add 2d                  # Add 2-day timeframe
!timeframes add 3d                  # Add 3-day timeframe
!timeframes remove 1h               # Remove hourly timeframe
```

### Signal Queries
```bash
!signals AAPL 15m                  # Get 15-minute AAPL signals
!signals TSLA 3h                   # Get 3-hour TSLA signals
!signals SPY 6h                    # Get 6-hour SPY signals
!signals QQQ 2d                    # Get 2-day QQQ signals
!signals NVDA 1wk                  # Get weekly NVDA signals
```

## API Compatibility
All supported timeframes are now compatible with your API endpoints:
- `/api/analyzer-b?ticker=AAPL&interval=3h&period=3mo`
- `/api/analyzer-b?ticker=TSLA&interval=6h&period=3mo`
- `/api/analyzer-b?ticker=SPY&interval=2d&period=1y`

## Testing
Created `test_timeframe_support.py` to verify:
- ✅ All API timeframes are supported
- ✅ Period mapping is correct
- ✅ Priority manager uses valid timeframes
- ✅ Signal commands accept all timeframes

## Database Impact
The bot will now properly store and track signals for all timeframes in the PostgreSQL database:
- `signal_notifications` table supports all timeframes
- `signal_performance` table tracks performance across all timeframes
- `daily_analytics` table aggregates data for all timeframes

## Next Steps
1. Test the new timeframes in your Discord server
2. Add any desired timeframes to your active monitoring list
3. Configure VIP timeframes based on your preferences
4. Monitor signal performance across different timeframes 