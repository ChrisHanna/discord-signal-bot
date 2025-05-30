#!/usr/bin/env python3
"""
Examine priority_config table structure and contents
"""
import asyncio
import os
from dotenv import load_dotenv
from database import db_manager

# Load environment variables from .env file
load_dotenv()

async def show_priority_configs():
    try:
        # Check if DATABASE_URL is loaded
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            print("❌ DATABASE_URL not found in environment variables")
            print("💡 Make sure your .env file contains DATABASE_URL")
            return
        
        print(f"✅ DATABASE_URL found: {database_url[:50]}...")
        
        await db_manager.initialize()
        async with db_manager.pool.acquire() as conn:
            # Get table structure
            table_info = await conn.fetch("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'priority_config'
                ORDER BY ordinal_position
            """)
            
            print('\n📋 Priority Config Table Structure:')
            print('=' * 50)
            for col in table_info:
                print(f"  {col['column_name']} ({col['data_type']}) - Nullable: {col['is_nullable']}")
            print()
            
            # Get all configurations
            configs = await conn.fetch('SELECT * FROM priority_config ORDER BY config_name, updated_at DESC')
            
            if configs:
                print('📊 Priority Config Table Contents:')
                print('=' * 60)
                for i, config in enumerate(configs, 1):
                    print(f'{i}. Config Name: "{config["config_name"]}"')
                    print(f'   Active: {config["is_active"]}')
                    print(f'   Min Priority: {config["min_priority_level"]}')
                    print(f'   VIP Tickers: {config["vip_tickers"]}')
                    print(f'   VIP Timeframes: {config["vip_timeframes"]}')
                    print(f'   Updated: {config["updated_at"]}')
                    print(f'   Created: {config["created_at"]}')
                    print(f'   Thresholds: Critical={config["critical_threshold"]}, High={config["high_threshold"]}, Medium={config["medium_threshold"]}, Low={config["low_threshold"]}')
                    print('-' * 40)
                    
                # Show which config is currently being used
                print('\n🎯 Current Active Configuration:')
                active_configs = [c for c in configs if c["is_active"]]
                if active_configs:
                    for config in active_configs:
                        print(f'   Using: "{config["config_name"]}" (Updated: {config["updated_at"]})')
                else:
                    print('   ⚠️ No active configuration found!')
                    
            else:
                print('❌ No priority configs found in database')
                
    except Exception as e:
        print(f'❌ Error examining priority configs: {e}')
        import traceback
        traceback.print_exc()
    finally:
        if hasattr(db_manager, 'pool') and db_manager.pool:
            await db_manager.pool.close()

if __name__ == "__main__":
    asyncio.run(show_priority_configs()) 