#!/usr/bin/env python3
"""
Railway Health Check for Discord Bot
Simple script to verify bot is running properly on Railway
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
import requests

def check_bot_files():
    """Check if essential bot files exist"""
    required_files = [
        'signal_notifier.py',
        'requirements.txt',
        '.env'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    return missing_files

def check_environment_variables():
    """Check if required environment variables are set"""
    required_vars = [
        'DISCORD_TOKEN',
        'DISCORD_CHANNEL_ID',
        'API_BASE_URL'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    return missing_vars

def check_api_connection():
    """Test connection to the trading API"""
    api_url = os.getenv('API_BASE_URL', 'http://localhost:5000')
    
    try:
        response = requests.get(f"{api_url}/", timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"API connection failed: {e}")
        return False

def check_notification_file():
    """Check if notification file exists and is valid"""
    notification_file = 'last_notifications.json'
    
    if not os.path.exists(notification_file):
        return True, "File doesn't exist yet (normal for new deployment)"
    
    try:
        with open(notification_file, 'r') as f:
            data = json.load(f)
        return True, f"File exists with {len(data)} entries"
    except json.JSONDecodeError:
        return False, "File exists but contains invalid JSON"
    except Exception as e:
        return False, f"Error reading file: {e}"

def check_ticker_config():
    """Check ticker configuration"""
    config_file = 'tickers.json'
    
    if not os.path.exists(config_file):
        return True, "Using default configuration"
    
    try:
        with open(config_file, 'r') as f:
            data = json.load(f)
        
        tickers = data.get('tickers', [])
        timeframes = data.get('timeframes', [])
        
        return True, f"{len(tickers)} tickers, {len(timeframes)} timeframes"
    except Exception as e:
        return False, f"Error reading config: {e}"

def main():
    """Run all health checks"""
    print("🏥 Railway Discord Bot Health Check")
    print("=" * 40)
    print(f"🕐 Check time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    if os.getenv('RAILWAY_ENVIRONMENT'):
        print(f"🚂 Railway environment: {os.getenv('RAILWAY_ENVIRONMENT')}")
        print(f"🔧 Railway service: {os.getenv('RAILWAY_SERVICE_NAME', 'discord-bot')}")
    else:
        print("💻 Running locally")
    
    print()
    
    # Check files
    print("📁 Checking essential files...")
    missing_files = check_bot_files()
    if missing_files:
        print(f"❌ Missing files: {', '.join(missing_files)}")
        return False
    else:
        print("✅ All essential files present")
    
    # Check environment variables
    print("\n🔑 Checking environment variables...")
    missing_vars = check_environment_variables()
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        return False
    else:
        print("✅ All required environment variables set")
    
    # Check API connection
    print("\n🌐 Testing API connection...")
    if check_api_connection():
        print("✅ API connection successful")
    else:
        print("⚠️ API connection failed (bot may still work with cached data)")
    
    # Check notification file
    print("\n📊 Checking notification file...")
    notifications_ok, notifications_msg = check_notification_file()
    if notifications_ok:
        print(f"✅ Notifications: {notifications_msg}")
    else:
        print(f"⚠️ Notifications: {notifications_msg}")
    
    # Check ticker config
    print("\n📈 Checking ticker configuration...")
    config_ok, config_msg = check_ticker_config()
    if config_ok:
        print(f"✅ Ticker config: {config_msg}")
    else:
        print(f"❌ Ticker config: {config_msg}")
        return False
    
    print("\n🎉 Health check completed successfully!")
    print("🚀 Bot should be ready to run on Railway")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 