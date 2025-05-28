#!/usr/bin/env python3
"""
Complete System Validation for Discord Signal Bot
Tests all components including database, analytics, and Discord functionality
"""

import asyncio
import sys
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def validate_system():
    """Run comprehensive system validation"""
    print("🔍 Discord Signal Bot - Complete System Validation")
    print("=" * 60)
    
    validation_results = {
        'environment': False,
        'database': False,
        'analytics': False,
        'priority_system': False,
        'discord_config': False,
        'smart_scheduler': False
    }
    
    # 1. Environment Variables Check
    print("\n📁 Environment Variables Check")
    print("-" * 30)
    
    required_env_vars = [
        'DISCORD_TOKEN',
        'DISCORD_CHANNEL_ID', 
        'DATABASE_URL',
        'API_BASE_URL'
    ]
    
    missing_vars = []
    for var in required_env_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive data
            if 'TOKEN' in var or 'URL' in var:
                display_value = f"{value[:10]}...{value[-4:]}" if len(value) > 14 else "***"
            else:
                display_value = value
            print(f"  ✅ {var}: {display_value}")
        else:
            print(f"  ❌ {var}: Not set")
            missing_vars.append(var)
    
    if not missing_vars:
        validation_results['environment'] = True
        print("  🎉 All environment variables configured!")
    else:
        print(f"  ⚠️ Missing variables: {', '.join(missing_vars)}")
    
    # 2. Database Connection Test
    print("\n🗄️ Database Connection Test")
    print("-" * 30)
    
    try:
        from database import init_database, get_stats, update_daily_analytics
        
        db_success = await init_database()
        if db_success:
            print("  ✅ Database connection successful")
            
            # Test basic operations
            stats = await get_stats()
            print(f"  ✅ Database queries working")
            print(f"     - Total notifications: {stats.get('total_notifications', 0)}")
            print(f"     - Total detected: {stats.get('total_detected', 0)}")
            
            validation_results['database'] = True
        else:
            print("  ❌ Database connection failed")
            
    except Exception as e:
        print(f"  ❌ Database error: {str(e)[:50]}")
    
    # 3. Analytics System Test
    print("\n📊 Analytics System Test")
    print("-" * 30)
    
    try:
        from database import get_best_performing_signals, get_signal_performance_summary
        
        # Test analytics functions
        best_performers = await get_best_performing_signals(7)
        print("  ✅ Best performers query working")
        
        performance = await get_signal_performance_summary()
        print("  ✅ Performance summary query working")
        
        # Test analytics update
        analytics_success = await update_daily_analytics()
        if analytics_success:
            print("  ✅ Analytics update successful")
        else:
            print("  ⚠️ Analytics update returned false (may be normal if no data)")
        
        validation_results['analytics'] = True
        
    except Exception as e:
        print(f"  ❌ Analytics error: {str(e)[:50]}")
    
    # 4. Priority System Test
    print("\n🎯 Priority System Test")
    print("-" * 30)
    
    try:
        from priority_manager import calculate_signal_priority, priority_manager
        
        # Test signal for priority calculation
        test_signal = {
            'type': 'WT Buy Signal',
            'strength': 'Strong',
            'system': 'Wave Trend',
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        priority_score = calculate_signal_priority(test_signal, 'AAPL', '1d')
        print(f"  ✅ Priority calculation working")
        print(f"     - Test signal score: {priority_score.total_score}")
        print(f"     - Priority level: {priority_score.priority_level.name}")
        print(f"     - VIP tickers: {len(priority_manager.VIP_TICKERS)}")
        
        validation_results['priority_system'] = True
        
    except Exception as e:
        print(f"  ❌ Priority system error: {str(e)[:50]}")
    
    # 5. Discord Configuration Test
    print("\n🤖 Discord Configuration Test")
    print("-" * 30)
    
    try:
        import discord
        
        token = os.getenv('DISCORD_TOKEN')
        channel_id = os.getenv('DISCORD_CHANNEL_ID')
        
        if token and len(token) > 50:
            print("  ✅ Discord token format looks valid")
        else:
            print("  ❌ Discord token missing or invalid format")
        
        if channel_id and channel_id.isdigit():
            print(f"  ✅ Discord channel ID valid: {channel_id}")
            validation_results['discord_config'] = True
        else:
            print("  ❌ Discord channel ID missing or invalid")
        
        print(f"  ℹ️ Discord.py version: {discord.__version__}")
        
    except Exception as e:
        print(f"  ❌ Discord configuration error: {str(e)[:50]}")
    
    # 6. Smart Scheduler Test
    print("\n⏰ Smart Scheduler Test")
    print("-" * 30)
    
    try:
        from smart_scheduler import SmartScheduler, create_smart_scheduler
        
        use_smart = os.getenv('USE_SMART_SCHEDULER', 'false').lower() == 'true'
        print(f"  📋 Smart scheduler enabled: {use_smart}")
        
        if use_smart:
            # Test scheduler creation
            def dummy_check_function(cycle, is_priority, reason):
                pass
            
            scheduler = create_smart_scheduler(dummy_check_function)
            print("  ✅ Smart scheduler creation successful")
            
            status_info = scheduler.get_status_info()
            print(f"     - Current time: {status_info['current_time']}")
            print(f"     - Market hours: {status_info['is_market_hours']}")
            
            validation_results['smart_scheduler'] = True
        else:
            print("  ℹ️ Using legacy scheduler")
            validation_results['smart_scheduler'] = True  # Not required
        
    except Exception as e:
        print(f"  ❌ Smart scheduler error: {str(e)[:50]}")
    
    # 7. File Structure Check
    print("\n📁 File Structure Check")
    print("-" * 30)
    
    required_files = [
        'signal_notifier.py',
        'database.py',
        'priority_manager.py',
        'smart_scheduler.py',
        'requirements.txt',
        '.env'
    ]
    
    for file in required_files:
        if os.path.exists(file):
            print(f"  ✅ {file}")
        else:
            print(f"  ❌ {file} - Missing")
    
    # 8. Configuration Files Check
    print("\n⚙️ Configuration Files Check")
    print("-" * 30)
    
    try:
        # Check if tickers.json exists or can be created
        if os.path.exists('tickers.json'):
            with open('tickers.json', 'r') as f:
                config = json.load(f)
            print(f"  ✅ tickers.json - {len(config.get('tickers', []))} tickers configured")
        else:
            print("  ℹ️ tickers.json - Will be created on first run")
        
        # Check database setup scripts
        if os.path.exists('setup_database.py'):
            print("  ✅ setup_database.py - Available for database initialization")
        
        if os.path.exists('migrate_database.py'):
            print("  ✅ migrate_database.py - Available for database migration")
        
    except Exception as e:
        print(f"  ⚠️ Configuration file error: {str(e)[:50]}")
    
    # 9. System Summary
    print("\n🎯 Validation Summary")
    print("=" * 60)
    
    passed_tests = sum(validation_results.values())
    total_tests = len(validation_results)
    success_rate = (passed_tests / total_tests) * 100
    
    print(f"Tests Passed: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
    print()
    
    for component, status in validation_results.items():
        status_icon = "✅" if status else "❌"
        component_name = component.replace('_', ' ').title()
        print(f"  {status_icon} {component_name}")
    
    print()
    
    if success_rate == 100:
        print("🎉 EXCELLENT! All systems are ready for production!")
        print("✅ Your Discord Signal Bot is fully configured and operational.")
        print()
        print("🚀 Next steps:")
        print("   1. Run: python signal_notifier.py")
        print("   2. Test with: !health command in Discord")
        print("   3. Monitor with: !analytics command")
        
    elif success_rate >= 80:
        print("🟡 GOOD! Most systems are working, minor issues detected.")
        print("⚠️ Address the failed components above before production deployment.")
        
    else:
        print("🔴 ISSUES DETECTED! Several components need attention.")
        print("❌ Please fix the failed components before running the bot.")
        print()
        print("💡 Common fixes:")
        print("   - Set missing environment variables in .env file")
        print("   - Run: python setup_database.py")
        print("   - Verify Discord bot token and permissions")
    
    print()
    print("📚 For detailed help, see README.md or run: python signal_notifier.py")
    print("🔧 For database setup, run: python setup_database.py")
    
    return success_rate >= 80

if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 7):
        print("❌ Python 3.7+ required")
        sys.exit(1)
    
    # Check required modules
    try:
        import discord
        import asyncpg
        import dotenv
    except ImportError as e:
        print(f"❌ Missing required module: {e}")
        print("💡 Run: pip install -r requirements.txt")
        sys.exit(1)
    
    # Run validation
    success = asyncio.run(validate_system())
    sys.exit(0 if success else 1) 