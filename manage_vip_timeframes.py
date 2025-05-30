#!/usr/bin/env python3
"""
VIP Timeframes Management Script
Test VIP timeframe management functionality before integrating into Discord bot
"""
import asyncio
import os
import sys
from dotenv import load_dotenv
from database import db_manager

# Load environment variables
load_dotenv()

async def list_vip_timeframes(config_name: str = "default"):
    """List VIP timeframes for a specific configuration"""
    try:
        async with db_manager.pool.acquire() as conn:
            config_row = await conn.fetchrow('''
                SELECT config_name, vip_timeframes, is_active, updated_at
                FROM priority_config 
                WHERE config_name = $1
            ''', config_name)
            
            if config_row:
                vip_timeframes = config_row['vip_timeframes'] or []
                print(f"📊 VIP Timeframes for '{config_row['config_name']}':")
                print(f"   Current VIP Timeframes: {', '.join(vip_timeframes) if vip_timeframes else 'None'}")
                print(f"   Status: {'✅ Active' if config_row['is_active'] else '❌ Inactive'}")
                print(f"   Last Updated: {config_row['updated_at'].strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Check against supported timeframes
                supported_timeframes = ['15m', '30m', '1h', '3h', '6h', '1d', '2d', '3d', '1wk']
                unsupported = [tf for tf in vip_timeframes if tf not in supported_timeframes]
                
                if unsupported:
                    print(f"   ⚠️ Unsupported VIP Timeframes: {', '.join(unsupported)}")
                else:
                    print(f"   ✅ All VIP timeframes are supported")
                
                return True
            else:
                print(f"❌ Configuration '{config_name}' not found")
                return False
                
    except Exception as e:
        print(f"❌ Error listing VIP timeframes: {e}")
        return False

async def add_vip_timeframe(timeframe: str, config_name: str = "default"):
    """Add a timeframe to VIP list"""
    try:
        # Validate timeframe
        supported_timeframes = ['15m', '30m', '1h', '3h', '6h', '1d', '2d', '3d', '1wk']
        if timeframe not in supported_timeframes:
            print(f"❌ '{timeframe}' is not supported by your API")
            print(f"   Supported: {', '.join(supported_timeframes)}")
            return False
        
        async with db_manager.pool.acquire() as conn:
            # Get current VIP timeframes
            config_row = await conn.fetchrow('''
                SELECT vip_timeframes FROM priority_config 
                WHERE config_name = $1
            ''', config_name)
            
            if config_row:
                current_vips = set(config_row['vip_timeframes'] or [])
                if timeframe in current_vips:
                    print(f"⚠️ '{timeframe}' is already a VIP timeframe in '{config_name}' config")
                    return False
                else:
                    # Add the new VIP timeframe
                    current_vips.add(timeframe)
                    await conn.execute('''
                        UPDATE priority_config 
                        SET vip_timeframes = $1, updated_at = NOW()
                        WHERE config_name = $2
                    ''', list(current_vips), config_name)
                    
                    print(f"✅ '{timeframe}' added as VIP timeframe to '{config_name}' config")
                    print(f"   Updated VIP List: {', '.join(sorted(current_vips))}")
                    return True
            else:
                print(f"❌ Configuration '{config_name}' not found")
                return False
                
    except Exception as e:
        print(f"❌ Error adding VIP timeframe: {e}")
        return False

async def remove_vip_timeframe(timeframe: str, config_name: str = "default"):
    """Remove a timeframe from VIP list"""
    try:
        async with db_manager.pool.acquire() as conn:
            config_row = await conn.fetchrow('''
                SELECT vip_timeframes FROM priority_config 
                WHERE config_name = $1
            ''', config_name)
            
            if config_row:
                current_vips = set(config_row['vip_timeframes'] or [])
                if timeframe not in current_vips:
                    print(f"⚠️ '{timeframe}' is not currently a VIP timeframe in '{config_name}' config")
                    return False
                else:
                    # Remove the VIP timeframe
                    current_vips.discard(timeframe)
                    await conn.execute('''
                        UPDATE priority_config 
                        SET vip_timeframes = $1, updated_at = NOW()
                        WHERE config_name = $2
                    ''', list(current_vips), config_name)
                    
                    print(f"✅ '{timeframe}' removed from VIP timeframes in '{config_name}' config")
                    print(f"   Updated VIP List: {', '.join(sorted(current_vips)) if current_vips else 'None'}")
                    return True
            else:
                print(f"❌ Configuration '{config_name}' not found")
                return False
                
    except Exception as e:
        print(f"❌ Error removing VIP timeframe: {e}")
        return False

async def list_all_configs():
    """List all priority configurations"""
    try:
        async with db_manager.pool.acquire() as conn:
            configs = await conn.fetch('''
                SELECT config_name, is_active, min_priority_level, 
                       array_length(vip_tickers, 1) as vip_ticker_count,
                       array_length(vip_timeframes, 1) as vip_timeframe_count,
                       vip_timeframes,
                       updated_at
                FROM priority_config 
                ORDER BY config_name
            ''')
            
            if configs:
                print("🎯 All Priority Configurations:")
                print("=" * 50)
                active_count = 0
                
                for config in configs:
                    status = "✅ Active" if config['is_active'] else "❌ Inactive"
                    if config['is_active']:
                        active_count += 1
                    
                    print(f"**{config['config_name']}** - {status}")
                    print(f"  Min Priority: {config['min_priority_level']}")
                    print(f"  VIP Tickers: {config['vip_ticker_count'] or 0}")
                    print(f"  VIP Timeframes: {config['vip_timeframe_count'] or 0}")
                    print(f"  VIP TFs: {', '.join(config['vip_timeframes']) if config['vip_timeframes'] else 'None'}")
                    print(f"  Updated: {config['updated_at'].strftime('%Y-%m-%d %H:%M')}")
                    print()
                
                if active_count > 1:
                    print(f"⚠️ Warning: {active_count} configurations are active simultaneously.")
                    print("   Bot typically uses 'default' config.")
                
                return True
            else:
                print("❌ No configurations found")
                return False
                
    except Exception as e:
        print(f"❌ Error listing configurations: {e}")
        return False

async def main():
    """Main interactive function"""
    try:
        await db_manager.initialize()
        
        print("🚀 VIP Timeframes Management Tool")
        print("=" * 40)
        
        if len(sys.argv) < 2:
            print("Usage examples:")
            print("  python manage_vip_timeframes.py list")
            print("  python manage_vip_timeframes.py list default")
            print("  python manage_vip_timeframes.py list trading_hours")
            print("  python manage_vip_timeframes.py add 3h")
            print("  python manage_vip_timeframes.py add 6h default")
            print("  python manage_vip_timeframes.py remove 6h")
            print("  python manage_vip_timeframes.py remove 3h trading_hours")
            print("  python manage_vip_timeframes.py configs")
            return
        
        action = sys.argv[1].lower()
        
        if action == 'list':
            config_name = sys.argv[2] if len(sys.argv) > 2 else "default"
            await list_vip_timeframes(config_name)
            
        elif action == 'add':
            if len(sys.argv) < 3:
                print("❌ Please specify a timeframe to add")
                return
            timeframe = sys.argv[2]
            config_name = sys.argv[3] if len(sys.argv) > 3 else "default"
            await add_vip_timeframe(timeframe, config_name)
            
        elif action == 'remove':
            if len(sys.argv) < 3:
                print("❌ Please specify a timeframe to remove")
                return
            timeframe = sys.argv[2]
            config_name = sys.argv[3] if len(sys.argv) > 3 else "default"
            await remove_vip_timeframe(timeframe, config_name)
            
        elif action == 'configs':
            await list_all_configs()
            
        else:
            print(f"❌ Unknown action: {action}")
            print("Valid actions: list, add, remove, configs")
        
    except Exception as e:
        print(f"❌ Error in main: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if hasattr(db_manager, 'pool') and db_manager.pool:
            await db_manager.pool.close()

if __name__ == "__main__":
    asyncio.run(main()) 