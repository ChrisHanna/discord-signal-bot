#!/usr/bin/env python3
import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import sys
from typing import Dict, List, Optional, Tuple

load_dotenv()

# Fix Windows event loop issue
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class ComprehensiveBackfill:
    def __init__(self):
        self.DATABASE_URL = os.getenv('DATABASE_URL')
        
        # Define all timeframes and their hour equivalents
        self.timeframes = {
            '1h': 1,
            '3h': 3, 
            '4h': 4,
            '6h': 6,
            '1d': 24,
            '3d': 72
        }
        
        # Define interpolation relationships (base timeframes for interpolation)
        self.interpolation_map = {
            '3h': ('1h', '1d'),   # Interpolate between 1h and 1d
            '6h': ('1h', '1d'),   # Interpolate between 1h and 1d  
            '4h': ('1h', '1d'),   # Interpolate between 1h and 1d
            '3d': ('1d', None)    # Extrapolate from 1d (or use existing if available)
        }
    
    async def get_missing_data_summary(self) -> Dict:
        """Get comprehensive summary of missing data across all timeframes"""
        try:
            conn = await asyncpg.connect(self.DATABASE_URL)
            
            summary = {}
            for timeframe in self.timeframes.keys():
                price_col = f'price_after_{timeframe}'
                success_col = f'success_{timeframe}'
                
                stats = await conn.fetchrow(f'''
                    SELECT 
                        COUNT(*) as total_records,
                        COUNT({price_col}) as has_price_data,
                        COUNT({success_col}) as has_success_data,
                        COUNT(CASE WHEN {price_col} IS NULL AND price_at_signal IS NOT NULL THEN 1 END) as missing_price,
                        COUNT(CASE WHEN {success_col} IS NULL AND price_at_signal IS NOT NULL THEN 1 END) as missing_success
                    FROM signal_performance
                    WHERE price_at_signal IS NOT NULL
                ''')
                
                summary[timeframe] = {
                    'total_records': stats['total_records'],
                    'has_price_data': stats['has_price_data'], 
                    'has_success_data': stats['has_success_data'],
                    'missing_price': stats['missing_price'],
                    'missing_success': stats['missing_success'],
                    'price_completeness': (stats['has_price_data'] / max(stats['total_records'], 1)) * 100,
                    'success_completeness': (stats['has_success_data'] / max(stats['total_records'], 1)) * 100
                }
            
            await conn.close()
            return summary
            
        except Exception as e:
            print(f"❌ Error getting data summary: {e}")
            return {}
    
    async def interpolate_price(self, target_hours: int, price_at_signal: float, 
                               price_1h: Optional[float], price_1d: Optional[float], 
                               price_3d: Optional[float] = None) -> Optional[float]:
        """Calculate price at target timeframe using interpolation/extrapolation"""
        try:
            if target_hours == 1 and price_1h is not None:
                return price_1h
            elif target_hours == 24 and price_1d is not None:
                return price_1d
            elif target_hours == 72 and price_3d is not None:
                return price_3d
            
            # For timeframes between 1h and 1d, use linear interpolation
            if target_hours < 24 and price_1h is not None and price_1d is not None:
                # Calculate progress from 1h to 1d
                progress = (target_hours - 1) / (24 - 1)
                return price_1h + (price_1d - price_1h) * progress
            
            # For 3d, extrapolate from 1d if needed
            elif target_hours == 72 and price_1d is not None:
                # Simple extrapolation: assume same rate of change continues
                daily_change = price_1d - price_at_signal
                return price_1d + (daily_change * 2)  # 2 more days of change
            
            return None
            
        except Exception as e:
            print(f"❌ Error interpolating price for {target_hours}h: {e}")
            return None
    
    async def calculate_success_flag(self, signal_type: str, price_at_signal: float, 
                                   price_after: float) -> bool:
        """Calculate success flag based on signal type and price movement"""
        try:
            signal_lower = signal_type.lower()
            
            # Determine signal direction
            is_bullish = any(keyword in signal_lower for keyword in 
                           ['bullish', 'buy', 'oversold', 'entry', 'long', 'support'])
            is_bearish = any(keyword in signal_lower for keyword in 
                           ['bearish', 'sell', 'overbought', 'short', 'resistance'])
            
            if is_bullish:
                return price_after > price_at_signal
            elif is_bearish:
                return price_after < price_at_signal
            else:
                # For neutral/unclear signals, consider any significant movement as success
                return abs((price_after - price_at_signal) / price_at_signal) > 0.01  # 1% movement
                
        except Exception as e:
            print(f"❌ Error calculating success flag: {e}")
            return False
    
    async def calculate_max_gain_loss(self, conn, record_id: int, price_at_signal: float,
                                    price_1h: float, price_1d: float) -> Tuple[Optional[float], Optional[float]]:
        """Calculate max gain and loss within 1 day period"""
        try:
            # For now, use available data points to estimate max gain/loss
            prices = [price_at_signal]
            if price_1h is not None:
                prices.append(price_1h)
            if price_1d is not None:
                prices.append(price_1d)
            
            if len(prices) < 2:
                return None, None
            
            max_price = max(prices)
            min_price = min(prices)
            
            max_gain = ((max_price - price_at_signal) / price_at_signal) * 100
            max_loss = ((min_price - price_at_signal) / price_at_signal) * 100
            
            return max_gain, max_loss
            
        except Exception as e:
            print(f"❌ Error calculating max gain/loss: {e}")
            return None, None
    
    async def backfill_timeframe(self, timeframe: str, limit: Optional[int] = None) -> Dict:
        """Backfill data for a specific timeframe"""
        try:
            conn = await asyncpg.connect(self.DATABASE_URL)
            
            print(f"🔄 Starting backfill for {timeframe} timeframe...")
            
            price_col = f'price_after_{timeframe}'
            success_col = f'success_{timeframe}'
            target_hours = self.timeframes[timeframe]
            
            # Build query to get records needing backfill
            query = f'''
                SELECT 
                    id, ticker, signal_type, signal_date, 
                    price_at_signal, price_after_1h, price_after_1d, price_after_3d,
                    {price_col}, {success_col}
                FROM signal_performance 
                WHERE price_at_signal IS NOT NULL 
                  AND ({price_col} IS NULL OR {success_col} IS NULL)
                ORDER BY signal_date DESC
            '''
            
            if limit:
                query += f' LIMIT {limit}'
            
            records_to_update = await conn.fetch(query)
            
            print(f"📊 Found {len(records_to_update)} records needing {timeframe} backfill")
            
            if len(records_to_update) == 0:
                await conn.close()
                return {"success": True, "message": f"No {timeframe} backfill needed", "updated": 0}
            
            updated_count = 0
            error_count = 0
            
            for i, record in enumerate(records_to_update):
                try:
                    if i % 100 == 0:
                        print(f"📈 Processing {timeframe} record {i+1}/{len(records_to_update)}...")
                    
                    price_at_signal = float(record['price_at_signal'])
                    price_1h = float(record['price_after_1h']) if record['price_after_1h'] else None
                    price_1d = float(record['price_after_1d']) if record['price_after_1d'] else None
                    price_3d = float(record['price_after_3d']) if record['price_after_3d'] else None
                    
                    current_price = record[price_col]
                    current_success = record[success_col]
                    
                    # Calculate missing price data
                    new_price = current_price
                    if current_price is None:
                        new_price = await self.interpolate_price(
                            target_hours, price_at_signal, price_1h, price_1d, price_3d
                        )
                    
                    # Calculate missing success data
                    new_success = current_success
                    if current_success is None and new_price is not None:
                        new_success = await self.calculate_success_flag(
                            record['signal_type'], price_at_signal, new_price
                        )
                    
                    # Update max gain/loss for 1d timeframe if missing
                    max_gain, max_loss = None, None
                    if timeframe == '1d' and price_1h and price_1d:
                        max_gain, max_loss = await self.calculate_max_gain_loss(
                            conn, record['id'], price_at_signal, price_1h, price_1d
                        )
                    
                    # Build update query dynamically
                    update_parts = []
                    params = []
                    param_count = 1
                    
                    if new_price is not None and current_price is None:
                        update_parts.append(f'{price_col} = ${param_count}')
                        params.append(new_price)
                        param_count += 1
                    
                    if new_success is not None and current_success is None:
                        update_parts.append(f'{success_col} = ${param_count}')
                        params.append(new_success)
                        param_count += 1
                    
                    if max_gain is not None:
                        update_parts.append(f'max_gain_1d = COALESCE(max_gain_1d, ${param_count})')
                        params.append(max_gain)
                        param_count += 1
                    
                    if max_loss is not None:
                        update_parts.append(f'max_loss_1d = COALESCE(max_loss_1d, ${param_count})')
                        params.append(max_loss)
                        param_count += 1
                    
                    if update_parts:
                        params.append(record['id'])
                        update_query = f'''
                            UPDATE signal_performance 
                            SET {', '.join(update_parts)}
                            WHERE id = ${param_count}
                        '''
                        
                        await conn.execute(update_query, *params)
                        updated_count += 1
                        
                        if updated_count % 50 == 0:
                            print(f"✅ Updated {updated_count} {timeframe} records so far...")
                    
                except Exception as e:
                    error_count += 1
                    print(f"❌ Error processing {timeframe} record {record['id']}: {e}")
                    continue
            
            await conn.close()
            
            success_rate = (updated_count / len(records_to_update) * 100) if records_to_update else 0
            
            result = {
                "success": True,
                "timeframe": timeframe,
                "message": f"{timeframe} backfill completed",
                "total_processed": len(records_to_update),
                "updated": updated_count,
                "errors": error_count,
                "success_rate": success_rate
            }
            
            print(f"""
🎯 {timeframe.upper()} Backfill Results:
   • Records processed: {len(records_to_update)}
   • Records updated: {updated_count}
   • Errors: {error_count}
   • Success rate: {success_rate:.1f}%
            """)
            
            return result
            
        except Exception as e:
            print(f"❌ {timeframe} backfill failed: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "message": str(e), "updated": 0}
    
    async def run_comprehensive_backfill(self, specific_timeframes: Optional[List[str]] = None,
                                       limit_per_timeframe: Optional[int] = None) -> Dict:
        """Run backfill for all or specific timeframes"""
        try:
            print("🚀 Starting comprehensive performance data backfill...")
            
            # Get initial summary
            initial_summary = await self.get_missing_data_summary()
            
            target_timeframes = specific_timeframes or list(self.timeframes.keys())
            results = {}
            
            total_updated = 0
            total_errors = 0
            
            for timeframe in target_timeframes:
                if timeframe not in self.timeframes:
                    print(f"⚠️ Skipping unknown timeframe: {timeframe}")
                    continue
                
                print(f"\n{'='*50}")
                result = await self.backfill_timeframe(timeframe, limit_per_timeframe)
                results[timeframe] = result
                
                if result["success"]:
                    total_updated += result["updated"]
                    total_errors += result.get("errors", 0)
            
            # Get final summary
            final_summary = await self.get_missing_data_summary()
            
            print(f"\n🎉 COMPREHENSIVE BACKFILL COMPLETED!")
            print(f"   Total records updated: {total_updated}")
            print(f"   Total errors: {total_errors}")
            
            return {
                "success": True,
                "total_updated": total_updated,
                "total_errors": total_errors,
                "timeframe_results": results,
                "initial_summary": initial_summary,
                "final_summary": final_summary
            }
            
        except Exception as e:
            print(f"❌ Comprehensive backfill failed: {e}")
            return {"success": False, "message": str(e)}

# Global instance
backfill_engine = ComprehensiveBackfill()

# Convenience functions for backward compatibility
async def backfill_missing_performance_data():
    """Legacy function - now runs comprehensive backfill"""
    return await backfill_engine.run_comprehensive_backfill(['3h', '6h'])

async def verify_backfill_results():
    """Verify backfill results across all timeframes"""
    summary = await backfill_engine.get_missing_data_summary()
    
    print("\n📊 COMPREHENSIVE DATA STATUS:")
    for timeframe, stats in summary.items():
        print(f"   {timeframe.upper():>3}: {stats['price_completeness']:5.1f}% price, {stats['success_completeness']:5.1f}% success")
    
    return summary

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Comprehensive Performance Data Backfill')
    parser.add_argument('--timeframes', nargs='+', help='Specific timeframes to backfill (e.g., 3h 6h 1d)')
    parser.add_argument('--limit', type=int, help='Limit records per timeframe for testing')
    parser.add_argument('--check', action='store_true', help='Only check status, don\'t run backfill')
    
    args = parser.parse_args()
    
    async def main():
        if args.check:
            summary = await backfill_engine.get_missing_data_summary()
            print("\n📊 DATA COMPLETENESS STATUS:")
            for timeframe, stats in summary.items():
                print(f"   {timeframe:>3}: {stats['has_price_data']:>5}/{stats['total_records']:>5} price ({stats['price_completeness']:5.1f}%), {stats['has_success_data']:>5}/{stats['total_records']:>5} success ({stats['success_completeness']:5.1f}%)")
        else:
            result = await backfill_engine.run_comprehensive_backfill(
                specific_timeframes=args.timeframes,
                limit_per_timeframe=args.limit
            )
            if result["success"]:
                await verify_backfill_results()
    
    asyncio.run(main()) 