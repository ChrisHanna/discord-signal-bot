#!/usr/bin/env python3
"""
Fix unsupported VIP timeframes in priority_config table
This script removes the unsupported '4h' timeframe and replaces it with supported alternatives
"""
import asyncio
import os
from dotenv import load_dotenv
from database import db_manager

# Load environment variables from .env file
load_dotenv()

async def fix_unsupported_vip_timeframes():
    try:
        # Check if DATABASE_URL is loaded
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            print("❌ DATABASE_URL not found in environment variables")
            return False
        
        print(f"✅ DATABASE_URL found")
        print("🔧 Fixing unsupported VIP timeframes in priority_config table...")
        print()
        
        await db_manager.initialize()
        async with db_manager.pool.acquire() as conn:
            # Supported timeframes by your API
            supported_timeframes = ['15m', '30m', '1h', '3h', '6h', '1d', '2d', '3d', '1wk']
            
            # Get all configs with VIP timeframes
            configs = await conn.fetch('''
                SELECT config_name, vip_timeframes, is_active
                FROM priority_config 
                WHERE vip_timeframes IS NOT NULL
            ''')
            
            print("📊 Current VIP timeframes in database:")
            print("-" * 50)
            
            fixes_needed = []
            
            for config in configs:
                config_name = config['config_name']
                vip_timeframes = config['vip_timeframes'] or []
                is_active = config['is_active']
                
                print(f"**{config_name}** ({'✅ Active' if is_active else '❌ Inactive'})")
                print(f"  Current VIP timeframes: {vip_timeframes}")
                
                # Find unsupported timeframes
                unsupported = [tf for tf in vip_timeframes if tf not in supported_timeframes]
                
                if unsupported:
                    print(f"  ⚠️ Unsupported timeframes found: {unsupported}")
                    
                    # Remove unsupported timeframes
                    new_vip_timeframes = [tf for tf in vip_timeframes if tf in supported_timeframes]
                    
                    # Add replacement timeframes if needed
                    if '4h' in unsupported:
                        # Replace 4h with 3h and 6h (closest supported alternatives)
                        if '3h' not in new_vip_timeframes:
                            new_vip_timeframes.append('3h')
                        if '6h' not in new_vip_timeframes:
                            new_vip_timeframes.append('6h')
                        print(f"  💡 Replacing 4h with 3h and 6h")
                    
                    fixes_needed.append({
                        'config_name': config_name,
                        'old_timeframes': vip_timeframes,
                        'new_timeframes': new_vip_timeframes,
                        'removed': unsupported
                    })
                    
                    print(f"  ✅ Proposed new timeframes: {new_vip_timeframes}")
                else:
                    print(f"  ✅ All timeframes are supported")
                
                print()
            
            if not fixes_needed:
                print("🎉 No fixes needed! All VIP timeframes are already supported.")
                return True
            
            # Ask for confirmation
            print("🔧 Fixes to be applied:")
            print("=" * 60)
            for fix in fixes_needed:
                print(f"Config: {fix['config_name']}")
                print(f"  Remove: {fix['removed']}")
                print(f"  Old: {fix['old_timeframes']}")
                print(f"  New: {fix['new_timeframes']}")
                print()
            
            # Apply fixes automatically
            print("⚡ Applying fixes...")
            
            for fix in fixes_needed:
                await conn.execute('''
                    UPDATE priority_config 
                    SET vip_timeframes = $1, updated_at = NOW()
                    WHERE config_name = $2
                ''', fix['new_timeframes'], fix['config_name'])
                
                print(f"✅ Fixed {fix['config_name']}: {fix['old_timeframes']} → {fix['new_timeframes']}")
            
            print()
            print("🎉 All fixes applied successfully!")
            print("💡 Your VIP timeframes now only use API-supported timeframes")
            
            # Show final state
            print("\n📊 Updated VIP timeframes:")
            print("-" * 40)
            updated_configs = await conn.fetch('''
                SELECT config_name, vip_timeframes, is_active
                FROM priority_config 
                WHERE vip_timeframes IS NOT NULL
                ORDER BY config_name
            ''')
            
            for config in updated_configs:
                status = "✅ Active" if config['is_active'] else "❌ Inactive"
                print(f"{config['config_name']} ({status}): {config['vip_timeframes']}")
            
            return True
            
    except Exception as e:
        print(f"❌ Error fixing VIP timeframes: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if hasattr(db_manager, 'pool') and db_manager.pool:
            await db_manager.pool.close()

if __name__ == "__main__":
    print("🚀 VIP Timeframes Fix Script")
    print("=" * 40)
    success = asyncio.run(fix_unsupported_vip_timeframes())
    
    if success:
        print("\n✅ Script completed successfully!")
        print("💡 You can now use Discord commands to manage VIP timeframes:")
        print("   !viptimeframes list")
        print("   !viptimeframes add 3h")
        print("   !viptimeframes remove 6h")
    else:
        print("\n❌ Script failed. Please check the errors above.") 