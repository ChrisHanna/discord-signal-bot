#!/usr/bin/env python3
"""
Simple script to add timeframe-aware checking to signal_notifier.py
This prevents late alerts by only checking timeframes at their candle close times.
"""

import os
import re

def patch_signal_notifier():
    """Add timeframe-aware logic to signal_notifier.py"""
    
    file_path = "signal_notifier.py"
    if not os.path.exists(file_path):
        print(f"❌ {file_path} not found!")
        return False
    
    # Read the current file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if already patched
    if "TIMEFRAME-AWARE CHECKING" in content:
        print("✅ File already patched with timeframe-aware logic!")
        return True
    
    # Find the pattern to replace
    pattern = r'(\s+# Check each ticker across all timeframes\s+api_errors = 0\s+discord_errors = 0\s+)(for ticker in TICKERS:)'
    
    replacement = r'''\1current_hour = cycle_start.hour
        
        \2'''
    
    # Replace the pattern
    content = re.sub(pattern, replacement, content)
    
    # Now add the timeframe filtering logic
    pattern2 = r'(\s+for ticker in TICKERS:\s+for timeframe in TIMEFRAMES:\s+)(try:)'
    
    replacement2 = r'''\1# ⏰ TIMEFRAME-AWARE CHECKING: Only check timeframes at their candle close times
                if timeframe == '3h' and current_hour not in [23, 2, 5, 8, 11, 14, 17, 20]:
                    print(f"⏭️ Skipping {ticker} ({timeframe}) - not a 3h candle close hour")
                    continue
                elif timeframe == '6h' and current_hour not in [2, 8, 14, 20]:
                    print(f"⏭️ Skipping {ticker} ({timeframe}) - not a 6h candle close hour")
                    continue  
                elif timeframe == '1d' and current_hour != 16:  # 4 PM EST market close
                    print(f"⏭️ Skipping {ticker} ({timeframe}) - not daily candle close hour")
                    continue
                # 1h timeframe runs every hour (no skip condition)
                
                \2'''
    
    # Replace the pattern
    new_content = re.sub(pattern2, replacement2, content)
    
    if new_content != content:
        # Create backup
        backup_path = f"{file_path}.backup"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"📋 Created backup: {backup_path}")
        
        # Write the patched file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print("✅ Successfully patched signal_notifier.py with timeframe-aware logic!")
        print("\n🎯 The bot will now:")
        print("   • Check 1h signals every hour")
        print("   • Check 3h signals only at 00:xx, 03:xx, 06:xx, 09:xx, 12:xx, 15:xx, 18:xx, 21:xx")
        print("   • Check 6h signals only at 00:xx, 06:xx, 12:xx, 18:xx")
        print("   • Check daily signals only at 16:xx (4 PM EST market close)")
        print("\n🚀 Restart your bot to apply the changes!")
        return True
    else:
        print("❌ Failed to apply patch - pattern not found")
        return False

if __name__ == "__main__":
    print("🔧 Applying timeframe-aware timing fix...")
    patch_signal_notifier() 
