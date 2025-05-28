#!/usr/bin/env python3
"""
Priority System Test Script for Discord Signal Bot
Test the priority scoring and filtering system.
"""

import os
import sys
from datetime import datetime, timedelta
from priority_manager import (
    SignalPriorityManager, 
    calculate_signal_priority, 
    should_send_notification,
    rank_signals_by_priority
)

def test_priority_system():
    """Test the priority management system with sample signals"""
    print("🎯 Testing Priority Management System")
    print("=" * 60)
    
    # Load environment variables if available
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("📁 Loaded environment variables from .env file")
    except ImportError:
        print("⚠️  python-dotenv not installed, using default values")
    
    print()
    
    # Create sample signals with different characteristics
    test_signals = [
        # Critical priority signals
        {
            'signal': {
                'type': 'WT Gold Buy Signal',
                'strength': 'Very Strong',
                'system': 'Wave Trend',
                'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            'ticker': 'SPY',
            'timeframe': '1d'
        },
        {
            'signal': {
                'type': 'Zero Line Reject Buy',
                'strength': 'Strong',
                'system': 'Zero Line',
                'date': (datetime.now() - timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
            },
            'ticker': 'AAPL',
            'timeframe': '4h'
        },
        
        # High priority signals
        {
            'signal': {
                'type': 'Fast Money Buy',
                'strength': 'Strong',
                'system': 'Fast Money',
                'date': (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
            },
            'ticker': 'TSLA',
            'timeframe': '1d'
        },
        {
            'signal': {
                'type': 'Bullish Divergence',
                'strength': 'Strong',
                'system': 'Divergence Detection',
                'date': datetime.now().strftime('%Y-%m-%d')
            },
            'ticker': 'NVDA',
            'timeframe': '1d'
        },
        
        # Medium priority signals
        {
            'signal': {
                'type': 'RSI3M3 Bullish Entry',
                'strength': 'Medium',
                'system': 'RSI3M3+',
                'date': (datetime.now() - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')
            },
            'ticker': 'QQQ',
            'timeframe': '1d'
        },
        {
            'signal': {
                'type': 'WT Buy Signal',
                'strength': 'Moderate',
                'system': 'Wave Trend',
                'date': (datetime.now() - timedelta(hours=6)).strftime('%Y-%m-%d %H:%M:%S')
            },
            'ticker': 'MSFT',
            'timeframe': '1h'
        },
        
        # Low priority signals
        {
            'signal': {
                'type': 'Bullish Cross',
                'strength': 'Weak',
                'system': 'Wave Trend',
                'date': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            },
            'ticker': 'AMD',
            'timeframe': '1d'
        },
        {
            'signal': {
                'type': 'Reversal Signal',
                'strength': 'Medium',
                'system': 'Unknown',
                'date': (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
            },
            'ticker': 'COIN',
            'timeframe': '1h'
        }
    ]
    
    print("🧪 Testing Individual Signal Priority Scores")
    print("-" * 60)
    
    scored_signals = []
    
    for i, test_case in enumerate(test_signals, 1):
        signal = test_case['signal']
        ticker = test_case['ticker']
        timeframe = test_case['timeframe']
        
        # Calculate priority score
        priority_score = calculate_signal_priority(signal, ticker, timeframe)
        scored_signals.append((signal, ticker, timeframe, priority_score))
        
        # Check if should notify
        should_notify, _ = should_send_notification(signal, ticker, timeframe)
        
        print(f"\n📊 Test Signal #{i}")
        print(f"   Ticker: {ticker} ({timeframe})")
        print(f"   Signal: {signal['type']}")
        print(f"   Strength: {signal['strength']}")
        print(f"   System: {signal['system']}")
        print(f"   Priority: {priority_score.priority_level.name} (Score: {priority_score.total_score})")
        print(f"   Should Notify: {'✅ YES' if should_notify else '❌ NO'}")
        
        # Show detailed breakdown for first few signals
        if i <= 3:
            print(f"   Score Breakdown:")
            print(f"     • Base: {priority_score.base_score}")
            print(f"     • Strength: +{priority_score.strength_bonus}")
            print(f"     • System: +{priority_score.system_bonus}")
            print(f"     • Ticker: +{priority_score.ticker_bonus}")
            print(f"     • Timeframe: +{priority_score.timeframe_bonus}")
            print(f"     • Urgency: +{priority_score.urgency_bonus}")
            print(f"     • Pattern: +{priority_score.pattern_bonus}")
    
    print("\n" + "=" * 60)
    print("🏆 Ranking Signals by Priority")
    print("-" * 60)
    
    # Rank all signals by priority
    signal_tuples = [(s['signal'], s['ticker'], s['timeframe']) for s in test_signals]
    ranked_signals = rank_signals_by_priority(signal_tuples)
    
    for i, (signal, ticker, timeframe, priority_score) in enumerate(ranked_signals, 1):
        priority_emoji = {
            'CRITICAL': '🚨',
            'HIGH': '⚠️',
            'MEDIUM': '📊',
            'LOW': '📢',
            'MINIMAL': '📝'
        }.get(priority_score.priority_level.name, '❓')
        
        print(f"{i:2d}. {priority_emoji} {ticker} - {signal['type']}")
        print(f"     Priority: {priority_score.priority_level.name} (Score: {priority_score.total_score})")
    
    print("\n" + "=" * 60)
    print("📈 Priority Distribution Summary")
    print("-" * 60)
    
    # Calculate priority distribution
    priority_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'MINIMAL': 0}
    notification_count = 0
    
    for signal, ticker, timeframe, priority_score in ranked_signals:
        priority_counts[priority_score.priority_level.name] += 1
        should_notify, _ = should_send_notification(signal, ticker, timeframe)
        if should_notify:
            notification_count += 1
    
    total_signals = len(ranked_signals)
    
    print(f"Total Signals Tested: {total_signals}")
    print(f"Notifications Sent: {notification_count} ({notification_count/total_signals*100:.1f}%)")
    print()
    
    for level, count in priority_counts.items():
        percentage = count/total_signals*100 if total_signals > 0 else 0
        print(f"{level:8s}: {count:2d} signals ({percentage:4.1f}%)")
    
    print("\n" + "=" * 60)
    print("⚙️ Current Priority Configuration")
    print("-" * 60)
    
    from priority_manager import priority_manager
    
    print(f"Minimum Priority Level: {priority_manager.MIN_PRIORITY_LEVEL}")
    print(f"Critical Threshold: {priority_manager.CRITICAL_THRESHOLD}")
    print(f"High Threshold: {priority_manager.HIGH_THRESHOLD}")
    print(f"Medium Threshold: {priority_manager.MEDIUM_THRESHOLD}")
    print(f"Low Threshold: {priority_manager.LOW_THRESHOLD}")
    print()
    print(f"VIP Tickers: {', '.join(sorted(priority_manager.VIP_TICKERS))}")
    print(f"VIP Timeframes: {', '.join(sorted(priority_manager.VIP_TIMEFRAMES))}")
    
    print("\n✅ Priority system test complete!")
    
    return ranked_signals

def test_configuration_changes():
    """Test how configuration changes affect priority scoring"""
    print("\n🔧 Testing Configuration Changes")
    print("=" * 60)
    
    from priority_manager import priority_manager
    
    # Test signal
    test_signal = {
        'type': 'WT Buy Signal',
        'strength': 'Strong',
        'system': 'Wave Trend',
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    print("Testing with different minimum priority levels:")
    
    original_level = priority_manager.MIN_PRIORITY_LEVEL
    
    for level in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'MINIMAL']:
        priority_manager.MIN_PRIORITY_LEVEL = level
        
        # Test with VIP ticker
        should_notify_vip, score_vip = should_send_notification(test_signal, 'AAPL', '1d')
        
        # Test with regular ticker
        should_notify_reg, score_reg = should_send_notification(test_signal, 'UNKNOWN', '1d')
        
        print(f"\n  {level:8s}: VIP={should_notify_vip} (Score: {score_vip.total_score}), "
              f"Regular={should_notify_reg} (Score: {score_reg.total_score})")
    
    # Restore original setting
    priority_manager.MIN_PRIORITY_LEVEL = original_level
    
    print(f"\nRestored minimum priority level to: {original_level}")

if __name__ == "__main__":
    try:
        # Run main tests
        ranked_signals = test_priority_system()
        
        # Test configuration changes
        test_configuration_changes()
        
        print("\n🎉 All priority tests completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 