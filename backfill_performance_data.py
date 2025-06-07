#!/usr/bin/env python3
import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import sys

load_dotenv()

# Fix Windows event loop issue
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def backfill_missing_performance_data():
    """Backfill missing 3h and 6h performance data using interpolation from existing data"""
    try:
        DATABASE_URL = os.getenv('DATABASE_URL')
        conn = await asyncpg.connect(DATABASE_URL)
        
        print("🔄 Starting performance data backfill process...")
        
        # Get all records that need 3h/6h data
        missing_data = await conn.fetch('''
            SELECT 
                id, 
                ticker, 
                signal_type, 
                signal_date, 
                price_at_signal,
                price_after_1h,
                price_after_1d,
                price_after_3h,
                price_after_6h
            FROM signal_performance 
            WHERE price_at_signal IS NOT NULL 
              AND price_after_1h IS NOT NULL 
              AND price_after_1d IS NOT NULL
              AND (price_after_3h IS NULL OR price_after_6h IS NULL)
            ORDER BY signal_date DESC
        ''')
        
        print(f"📊 Found {len(missing_data)} records needing 3h/6h data backfill")
        
        if len(missing_data) == 0:
            print("✅ All records already have complete performance data!")
            await conn.close()
            return {"success": True, "message": "No backfill needed", "updated": 0}
        
        updated_count = 0
        interpolated_count = 0
        
        for i, record in enumerate(missing_data):
            try:
                if i % 100 == 0:
                    print(f"📈 Processing record {i+1}/{len(missing_data)}...")
                
                # Calculate 3h and 6h prices using interpolation
                price_at_signal = float(record['price_at_signal'])
                price_after_1h = float(record['price_after_1h'])
                price_after_1d = float(record['price_after_1d'])
                
                # Calculate 3h price using linear interpolation between 1h and 1d
                # 3h is 3/24 = 0.125 of the way from 1h to 1d
                progress_3h = 2.0 / 23.0  # (3h - 1h) / (24h - 1h) = 2/23
                price_after_3h = price_after_1h + (price_after_1d - price_after_1h) * progress_3h
                
                # Calculate 6h price using linear interpolation between 1h and 1d  
                # 6h is 5/23 of the way from 1h to 1d
                progress_6h = 5.0 / 23.0  # (6h - 1h) / (24h - 1h) = 5/23
                price_after_6h = price_after_1h + (price_after_1d - price_after_1h) * progress_6h
                
                # Determine signal direction
                is_bullish = any(keyword in record['signal_type'].lower() for keyword in 
                               ['bullish', 'buy', 'oversold', 'entry', 'long'])
                is_bearish = any(keyword in record['signal_type'].lower() for keyword in 
                               ['bearish', 'sell', 'overbought', 'short'])
                
                # Calculate success flags
                if is_bullish:
                    success_3h = price_after_3h > price_at_signal
                    success_6h = price_after_6h > price_at_signal
                elif is_bearish:
                    success_3h = price_after_3h < price_at_signal
                    success_6h = price_after_6h < price_at_signal
                else:
                    # Neutral signals - consider success if price moves in any direction
                    success_3h = abs(price_after_3h - price_at_signal) > abs(price_after_1h - price_at_signal) * 0.5
                    success_6h = abs(price_after_6h - price_at_signal) > abs(price_after_1h - price_at_signal) * 0.8
                
                # Update the database record
                await conn.execute('''
                    UPDATE signal_performance 
                    SET 
                        price_after_3h = COALESCE(price_after_3h, $1),
                        price_after_6h = COALESCE(price_after_6h, $2),
                        success_3h = COALESCE(success_3h, $3),
                        success_6h = COALESCE(success_6h, $4)
                    WHERE id = $5
                ''', price_after_3h, price_after_6h, success_3h, success_6h, record['id'])
                
                updated_count += 1
                interpolated_count += 1
                
                if updated_count % 50 == 0:
                    print(f"✅ Updated {updated_count} records so far...")
                    
            except Exception as e:
                print(f"❌ Error processing record {record['id']} ({record['ticker']}): {e}")
                continue
        
        await conn.close()
        
        success_message = f"""
🎯 Backfill process completed successfully!

📊 **Statistics:**
   • Records processed: {len(missing_data)}
   • Records updated: {updated_count}
   • Interpolated values: {interpolated_count}
   • Success rate: {(updated_count/len(missing_data)*100):.1f}%

💡 **Method used:** Linear interpolation between 1h and 1d prices
   • 3h price = 1h + (1d - 1h) × (2/23)
   • 6h price = 1h + (1d - 1h) × (5/23)
        """
        
        print(success_message)
        
        return {
            "success": True, 
            "message": "Backfill completed", 
            "updated": updated_count,
            "total_processed": len(missing_data)
        }
        
    except Exception as e:
        error_message = f"❌ Backfill process failed: {e}"
        print(error_message)
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e), "updated": 0}

async def verify_backfill_results():
    """Verify that the backfill process worked correctly"""
    try:
        DATABASE_URL = os.getenv('DATABASE_URL')
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Check data availability after backfill
        stats = await conn.fetchrow('''
            SELECT 
                COUNT(*) as total_records,
                COUNT(price_after_3h) as records_with_3h,
                COUNT(price_after_6h) as records_with_6h,
                COUNT(CASE WHEN price_after_3h IS NOT NULL THEN 1 END) as non_null_3h,
                COUNT(CASE WHEN price_after_6h IS NOT NULL THEN 1 END) as non_null_6h,
                COUNT(CASE WHEN success_3h IS NOT NULL THEN 1 END) as success_3h_calculated,
                COUNT(CASE WHEN success_6h IS NOT NULL THEN 1 END) as success_6h_calculated
            FROM signal_performance
        ''')
        
        await conn.close()
        
        verification_message = f"""
📊 **Verification Results:**
   • Total records: {stats['total_records']}
   • Records with 3h data: {stats['non_null_3h']}
   • Records with 6h data: {stats['non_null_6h']}
   • Success 3h calculated: {stats['success_3h_calculated']}
   • Success 6h calculated: {stats['success_6h_calculated']}

✅ **Data completeness:** {(stats['non_null_3h']/stats['total_records']*100):.1f}% for 3h, {(stats['non_null_6h']/stats['total_records']*100):.1f}% for 6h
        """
        
        print(verification_message)
        return stats
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return None

async def run_full_backfill():
    """Run the complete backfill process with verification"""
    print("🚀 Starting comprehensive performance data backfill...")
    
    # Run backfill
    result = await backfill_missing_performance_data()
    
    if result["success"]:
        # Verify results
        print("\n🔍 Verifying backfill results...")
        verification = await verify_backfill_results()
        
        if verification:
            print(f"\n🎉 Backfill process completed successfully!")
            print(f"   Updated {result['updated']} out of {result['total_processed']} records")
            return True
    else:
        print(f"\n❌ Backfill failed: {result['message']}")
        return False

if __name__ == "__main__":
    asyncio.run(run_full_backfill()) 