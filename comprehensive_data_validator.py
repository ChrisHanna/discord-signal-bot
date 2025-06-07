#!/usr/bin/env python3
"""
Comprehensive Data Validator for Trading Signal Analysis
Ensures data quality and integrity for ML commands
"""

import asyncio
import asyncpg
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import json
import logging

load_dotenv()

class DataValidator:
    def __init__(self):
        self.db_url = os.getenv('DATABASE_URL')
        self.logger = logging.getLogger(__name__)
        self.validation_results = {}
        
    async def validate_all_data(self, days: int = 30) -> Dict:
        """Comprehensive data validation for ML commands"""
        try:
            validation_report = {
                "timestamp": datetime.now().isoformat(),
                "validation_period_days": days,
                "schema_validation": {},
                "data_quality": {},
                "ml_readiness": {},
                "recommendations": [],
                "overall_score": 0.0
            }
            
            # 1. Database Schema Validation
            schema_results = await self.validate_database_schema()
            validation_report["schema_validation"] = schema_results
            
            # 2. Data Quality Checks
            quality_results = await self.validate_data_quality(days)
            validation_report["data_quality"] = quality_results
            
            # 3. ML Readiness Assessment
            ml_readiness = await self.assess_ml_readiness(days)
            validation_report["ml_readiness"] = ml_readiness
            
            # 4. Generate Recommendations
            recommendations = await self.generate_recommendations(schema_results, quality_results, ml_readiness)
            validation_report["recommendations"] = recommendations
            
            # 5. Calculate Overall Score
            overall_score = self.calculate_overall_score(schema_results, quality_results, ml_readiness)
            validation_report["overall_score"] = overall_score
            
            return validation_report
            
        except Exception as e:
            return {"error": f"Data validation failed: {e}"}
    
    async def validate_database_schema(self) -> Dict:
        """Validate database schema against expected structure"""
        try:
            conn = await asyncpg.connect(self.db_url)
            
            schema_results = {
                "tables_exist": {},
                "required_columns": {},
                "indexes_exist": {},
                "constraints_valid": {},
                "schema_score": 0.0
            }
            
            # Check required tables
            required_tables = [
                'signal_notifications', 'signal_performance', 
                'signal_analytics', 'signals_detected'
            ]
            
            for table in required_tables:
                exists = await self.check_table_exists(conn, table)
                schema_results["tables_exist"][table] = exists
            
            # Check signal_performance table structure
            if schema_results["tables_exist"].get("signal_performance", False):
                required_columns = {
                    'id': 'integer',
                    'ticker': 'character varying',
                    'timeframe': 'character varying',
                    'signal_type': 'character varying',
                    'signal_date': 'timestamp with time zone',
                    'performance_date': 'timestamp with time zone',
                    'price_at_signal': 'numeric',
                    'price_after_1h': 'numeric',
                    'price_after_4h': 'numeric',
                    'price_after_1d': 'numeric',
                    'price_after_3d': 'numeric',
                    'success_1h': 'boolean',
                    'success_4h': 'boolean',
                    'success_1d': 'boolean',
                    'success_3d': 'boolean'
                }
                
                column_validation = await self.validate_table_columns(conn, 'signal_performance', required_columns)
                schema_results["required_columns"]["signal_performance"] = column_validation
            
            # Check essential indexes
            essential_indexes = [
                ('signal_performance', 'idx_performance_ticker_date'),
                ('signal_notifications', 'idx_signal_date'),
                ('signal_notifications', 'idx_ticker_timeframe')
            ]
            
            for table, index in essential_indexes:
                index_exists = await self.check_index_exists(conn, index)
                schema_results["indexes_exist"][f"{table}.{index}"] = index_exists
            
            await conn.close()
            
            # Calculate schema score
            all_tables_exist = all(schema_results["tables_exist"].values())
            all_columns_exist = all(
                col_info.get("exists", False) 
                for col_info in schema_results["required_columns"].get("signal_performance", {}).values()
            )
            most_indexes_exist = sum(schema_results["indexes_exist"].values()) >= len(essential_indexes) * 0.8
            
            schema_score = (
                (1.0 if all_tables_exist else 0.5) * 0.4 +
                (1.0 if all_columns_exist else 0.3) * 0.4 +
                (1.0 if most_indexes_exist else 0.6) * 0.2
            )
            schema_results["schema_score"] = schema_score
            
            return schema_results
            
        except Exception as e:
            return {"error": f"Schema validation failed: {e}"}
    
    async def validate_data_quality(self, days: int = 30) -> Dict:
        """Validate data quality for ML analysis"""
        try:
            conn = await asyncpg.connect(self.db_url)
            since_date = datetime.now() - timedelta(days=days)
            
            quality_results = {
                "completeness": {},
                "consistency": {},
                "accuracy": {},
                "freshness": {},
                "quality_score": 0.0
            }
            
            # Data Completeness Check
            completeness = await self.check_data_completeness(conn, since_date)
            quality_results["completeness"] = completeness
            
            # Data Consistency Check
            consistency = await self.check_data_consistency(conn, since_date)
            quality_results["consistency"] = consistency
            
            # Data Accuracy Check
            accuracy = await self.check_data_accuracy(conn, since_date)
            quality_results["accuracy"] = accuracy
            
            # Data Freshness Check
            freshness = await self.check_data_freshness(conn)
            quality_results["freshness"] = freshness
            
            await conn.close()
            
            # Calculate quality score
            quality_score = (
                completeness.get("score", 0) * 0.3 +
                consistency.get("score", 0) * 0.3 +
                accuracy.get("score", 0) * 0.2 +
                freshness.get("score", 0) * 0.2
            )
            quality_results["quality_score"] = quality_score
            
            return quality_results
            
        except Exception as e:
            return {"error": f"Data quality validation failed: {e}"}
    
    async def assess_ml_readiness(self, days: int = 30) -> Dict:
        """Assess readiness for machine learning analysis"""
        try:
            conn = await asyncpg.connect(self.db_url)
            since_date = datetime.now() - timedelta(days=days)
            
            ml_readiness = {
                "sample_size": {},
                "feature_availability": {},
                "label_quality": {},
                "distribution_balance": {},
                "ml_score": 0.0
            }
            
            # Sample Size Assessment
            sample_size = await self.assess_sample_size(conn, since_date)
            ml_readiness["sample_size"] = sample_size
            
            # Feature Availability
            features = await self.assess_feature_availability(conn, since_date)
            ml_readiness["feature_availability"] = features
            
            # Label Quality
            labels = await self.assess_label_quality(conn, since_date)
            ml_readiness["label_quality"] = labels
            
            # Distribution Balance
            distribution = await self.assess_distribution_balance(conn, since_date)
            ml_readiness["distribution_balance"] = distribution
            
            await conn.close()
            
            # Calculate ML readiness score
            ml_score = (
                sample_size.get("score", 0) * 0.3 +
                features.get("score", 0) * 0.3 +
                labels.get("score", 0) * 0.2 +
                distribution.get("score", 0) * 0.2
            )
            ml_readiness["ml_score"] = ml_score
            
            return ml_readiness
            
        except Exception as e:
            return {"error": f"ML readiness assessment failed: {e}"}
    
    async def check_table_exists(self, conn, table_name: str) -> bool:
        """Check if a table exists"""
        result = await conn.fetchval('''
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = $1
            )
        ''', table_name)
        return result
    
    async def validate_table_columns(self, conn, table_name: str, required_columns: Dict) -> Dict:
        """Validate table columns against requirements"""
        column_info = {}
        
        for column_name, expected_type in required_columns.items():
            result = await conn.fetchrow('''
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = $1 AND column_name = $2
            ''', table_name, column_name)
            
            if result:
                column_info[column_name] = {
                    "exists": True,
                    "type": result['data_type'],
                    "nullable": result['is_nullable'] == 'YES',
                    "type_matches": expected_type.lower() in result['data_type'].lower()
                }
            else:
                column_info[column_name] = {
                    "exists": False,
                    "type": None,
                    "nullable": None,
                    "type_matches": False
                }
        
        return column_info
    
    async def check_index_exists(self, conn, index_name: str) -> bool:
        """Check if an index exists"""
        result = await conn.fetchval('''
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = $1
            )
        ''', index_name)
        return result
    
    async def check_data_completeness(self, conn, since_date: datetime) -> Dict:
        """Check data completeness"""
        try:
            # Check signal_performance table completeness
            perf_stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(price_at_signal) as price_at_signal_count,
                    COUNT(price_after_1h) as price_1h_count,
                    COUNT(price_after_4h) as price_4h_count,
                    COUNT(price_after_1d) as price_1d_count,
                    COUNT(success_1h) as success_1h_count,
                    COUNT(success_1d) as success_1d_count
                FROM signal_performance
                WHERE performance_date >= $1
            ''', since_date)
            
            if perf_stats['total_records'] == 0:
                return {
                    "total_records": 0,
                    "completeness_rates": {},
                    "score": 0.0,
                    "status": "NO_DATA"
                }
            
            completeness_rates = {}
            total = perf_stats['total_records']
            
            for field in ['price_at_signal', 'price_1h', 'price_4h', 'price_1d', 'success_1h', 'success_1d']:
                count = perf_stats[f'{field}_count']
                completeness_rates[field] = round(count / total, 3) if total > 0 else 0
            
            # Calculate completeness score
            avg_completeness = sum(completeness_rates.values()) / len(completeness_rates)
            score = min(avg_completeness * 1.2, 1.0)  # Slight boost for good performance
            
            return {
                "total_records": total,
                "completeness_rates": completeness_rates,
                "score": score,
                "status": "EXCELLENT" if score >= 0.9 else "GOOD" if score >= 0.7 else "POOR"
            }
            
        except Exception as e:
            return {"error": f"Completeness check failed: {e}", "score": 0.0}
    
    async def check_data_consistency(self, conn, since_date: datetime) -> Dict:
        """Check data consistency"""
        try:
            # Check for logical inconsistencies
            inconsistencies = await conn.fetch('''
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(CASE WHEN price_at_signal <= 0 THEN 1 END) as negative_prices,
                    COUNT(CASE WHEN price_after_1d / price_at_signal > 10 THEN 1 END) as extreme_changes,
                    COUNT(CASE WHEN signal_date > performance_date THEN 1 END) as future_signals
                FROM signal_performance
                WHERE performance_date >= $1
                  AND price_at_signal IS NOT NULL
            ''', since_date)
            
            if not inconsistencies or inconsistencies[0]['total_records'] == 0:
                return {"score": 0.0, "status": "NO_DATA"}
            
            stats = inconsistencies[0]
            total = stats['total_records']
            
            inconsistency_rate = (
                stats['negative_prices'] + 
                stats['extreme_changes'] + 
                stats['future_signals']
            ) / max(total, 1)
            
            consistency_score = max(0, 1 - inconsistency_rate * 10)  # Penalty for inconsistencies
            
            return {
                "total_records": total,
                "negative_prices": stats['negative_prices'],
                "extreme_changes": stats['extreme_changes'],
                "future_signals": stats['future_signals'],
                "inconsistency_rate": round(inconsistency_rate, 4),
                "score": consistency_score,
                "status": "EXCELLENT" if consistency_score >= 0.95 else "GOOD" if consistency_score >= 0.8 else "POOR"
            }
            
        except Exception as e:
            return {"error": f"Consistency check failed: {e}", "score": 0.0}
    
    async def check_data_accuracy(self, conn, since_date: datetime) -> Dict:
        """Check data accuracy through validation rules"""
        try:
            # Check success flag accuracy
            accuracy_check = await conn.fetch('''
                SELECT 
                    COUNT(*) as total_with_prices,
                    COUNT(CASE 
                        WHEN success_1d = true AND price_after_1d <= price_at_signal THEN 1 
                    END) as false_positives_1d,
                    COUNT(CASE 
                        WHEN success_1d = false AND price_after_1d > price_at_signal * 1.02 THEN 1 
                    END) as false_negatives_1d
                FROM signal_performance
                WHERE performance_date >= $1
                  AND price_at_signal IS NOT NULL
                  AND price_after_1d IS NOT NULL
                  AND success_1d IS NOT NULL
            ''', since_date)
            
            if not accuracy_check or accuracy_check[0]['total_with_prices'] == 0:
                return {"score": 0.0, "status": "NO_DATA"}
            
            stats = accuracy_check[0]
            total = stats['total_with_prices']
            
            accuracy_issues = stats['false_positives_1d'] + stats['false_negatives_1d']
            accuracy_rate = 1 - (accuracy_issues / max(total, 1))
            
            return {
                "total_validated": total,
                "false_positives": stats['false_positives_1d'],
                "false_negatives": stats['false_negatives_1d'],
                "accuracy_rate": round(accuracy_rate, 4),
                "score": accuracy_rate,
                "status": "EXCELLENT" if accuracy_rate >= 0.95 else "GOOD" if accuracy_rate >= 0.85 else "POOR"
            }
            
        except Exception as e:
            return {"error": f"Accuracy check failed: {e}", "score": 0.0}
    
    async def check_data_freshness(self, conn) -> Dict:
        """Check data freshness"""
        try:
            freshness_stats = await conn.fetchrow('''
                SELECT 
                    MAX(performance_date) as latest_performance,
                    MAX(signal_date) as latest_signal,
                    COUNT(*) as recent_records
                FROM signal_performance
                WHERE performance_date >= NOW() - INTERVAL '7 days'
            ''')
            
            if not freshness_stats['latest_performance']:
                return {"score": 0.0, "status": "NO_DATA"}
            
            # Calculate days since last update
            latest_perf = freshness_stats['latest_performance']
            days_since_update = (datetime.now().replace(tzinfo=latest_perf.tzinfo) - latest_perf).days
            
            # Freshness score based on recency
            if days_since_update <= 1:
                freshness_score = 1.0
            elif days_since_update <= 3:
                freshness_score = 0.8
            elif days_since_update <= 7:
                freshness_score = 0.6
            else:
                freshness_score = 0.3
            
            return {
                "latest_performance_date": latest_perf.isoformat(),
                "latest_signal_date": freshness_stats['latest_signal'].isoformat() if freshness_stats['latest_signal'] else None,
                "days_since_update": days_since_update,
                "recent_records_7d": freshness_stats['recent_records'],
                "score": freshness_score,
                "status": "FRESH" if freshness_score >= 0.8 else "STALE" if freshness_score >= 0.5 else "OUTDATED"
            }
            
        except Exception as e:
            return {"error": f"Freshness check failed: {e}", "score": 0.0}
    
    async def assess_sample_size(self, conn, since_date: datetime) -> Dict:
        """Assess sample size for ML"""
        try:
            sample_stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_samples,
                    COUNT(DISTINCT ticker) as unique_tickers,
                    COUNT(DISTINCT timeframe) as unique_timeframes,
                    COUNT(DISTINCT signal_type) as unique_signal_types
                FROM signal_performance
                WHERE performance_date >= $1
                  AND price_at_signal IS NOT NULL
                  AND price_after_1d IS NOT NULL
                  AND success_1d IS NOT NULL
            ''')
            
            total = sample_stats['total_samples']
            
            # ML sample size scoring
            if total >= 1000:
                sample_score = 1.0
            elif total >= 500:
                sample_score = 0.8
            elif total >= 200:
                sample_score = 0.6
            elif total >= 100:
                sample_score = 0.4
            elif total >= 50:
                sample_score = 0.2
            else:
                sample_score = 0.1
            
            return {
                "total_samples": total,
                "unique_tickers": sample_stats['unique_tickers'],
                "unique_timeframes": sample_stats['unique_timeframes'],
                "unique_signal_types": sample_stats['unique_signal_types'],
                "score": sample_score,
                "status": "EXCELLENT" if sample_score >= 0.8 else "GOOD" if sample_score >= 0.6 else "INSUFFICIENT"
            }
            
        except Exception as e:
            return {"error": f"Sample size assessment failed: {e}", "score": 0.0}
    
    async def assess_feature_availability(self, conn, since_date: datetime) -> Dict:
        """Assess feature availability for ML"""
        try:
            # Check availability of key features
            feature_stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(CASE WHEN ticker IS NOT NULL THEN 1 END) as has_ticker,
                    COUNT(CASE WHEN timeframe IS NOT NULL THEN 1 END) as has_timeframe,
                    COUNT(CASE WHEN signal_type IS NOT NULL THEN 1 END) as has_signal_type,
                    COUNT(CASE WHEN signal_date IS NOT NULL THEN 1 END) as has_signal_date
                FROM signal_performance
                WHERE performance_date >= $1
            ''', since_date)
            
            if feature_stats['total_records'] == 0:
                return {"score": 0.0, "status": "NO_DATA"}
            
            total = feature_stats['total_records']
            essential_features = ['ticker', 'timeframe', 'signal_type', 'signal_date']
            
            feature_completeness = {}
            for feature in essential_features:
                count = feature_stats[f'has_{feature}']
                feature_completeness[feature] = count / total
            
            avg_completeness = sum(feature_completeness.values()) / len(feature_completeness)
            
            return {
                "total_records": total,
                "feature_completeness": feature_completeness,
                "average_completeness": round(avg_completeness, 3),
                "score": avg_completeness,
                "status": "EXCELLENT" if avg_completeness >= 0.95 else "GOOD" if avg_completeness >= 0.8 else "POOR"
            }
            
        except Exception as e:
            return {"error": f"Feature availability assessment failed: {e}", "score": 0.0}
    
    async def assess_label_quality(self, conn, since_date: datetime) -> Dict:
        """Assess quality of success labels"""
        try:
            label_stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(success_1h) as has_success_1h,
                    COUNT(success_1d) as has_success_1d,
                    AVG(CASE WHEN success_1d = true THEN 1.0 ELSE 0.0 END) as success_rate_1d,
                    AVG(CASE WHEN success_1h = true THEN 1.0 ELSE 0.0 END) as success_rate_1h
                FROM signal_performance
                WHERE performance_date >= $1
                  AND price_at_signal IS NOT NULL
                  AND price_after_1d IS NOT NULL
            ''', since_date)
            
            if label_stats['total_records'] == 0:
                return {"score": 0.0, "status": "NO_DATA"}
            
            total = label_stats['total_records']
            label_completeness = label_stats['has_success_1d'] / total
            
            # Check if success rates are reasonable (not too extreme)
            success_rate_1d = label_stats['success_rate_1d'] or 0
            balance_score = 1 - abs(success_rate_1d - 0.5) * 2  # Penalty for extreme imbalance
            
            label_score = (label_completeness * 0.7) + (max(balance_score, 0.2) * 0.3)
            
            return {
                "total_records": total,
                "label_completeness": round(label_completeness, 3),
                "success_rate_1d": round(success_rate_1d, 3),
                "success_rate_1h": round(label_stats['success_rate_1h'] or 0, 3),
                "balance_score": round(balance_score, 3),
                "score": label_score,
                "status": "EXCELLENT" if label_score >= 0.8 else "GOOD" if label_score >= 0.6 else "POOR"
            }
            
        except Exception as e:
            return {"error": f"Label quality assessment failed: {e}", "score": 0.0}
    
    async def assess_distribution_balance(self, conn, since_date: datetime) -> Dict:
        """Assess distribution balance across categories"""
        try:
            # Check distribution across tickers and timeframes
            distribution_stats = await conn.fetch('''
                SELECT 
                    ticker,
                    timeframe,
                    COUNT(*) as count,
                    AVG(CASE WHEN success_1d = true THEN 1.0 ELSE 0.0 END) as success_rate
                FROM signal_performance
                WHERE performance_date >= $1
                  AND success_1d IS NOT NULL
                GROUP BY ticker, timeframe
                ORDER BY count DESC
            ''', since_date)
            
            if not distribution_stats:
                return {"score": 0.0, "status": "NO_DATA"}
            
            total_combinations = len(distribution_stats)
            counts = [stat['count'] for stat in distribution_stats]
            
            # Calculate distribution balance using coefficient of variation
            if len(counts) > 1:
                mean_count = np.mean(counts)
                std_count = np.std(counts)
                cv = std_count / mean_count if mean_count > 0 else 1
                balance_score = max(0, 1 - cv / 2)  # Lower CV = better balance
            else:
                balance_score = 0.5  # Single category isn't ideal
            
            return {
                "total_combinations": total_combinations,
                "sample_distribution": [
                    {
                        "ticker": stat['ticker'],
                        "timeframe": stat['timeframe'],
                        "count": stat['count'],
                        "success_rate": round(stat['success_rate'], 3)
                    }
                    for stat in distribution_stats[:10]  # Top 10
                ],
                "distribution_balance": round(balance_score, 3),
                "score": balance_score,
                "status": "BALANCED" if balance_score >= 0.7 else "MODERATE" if balance_score >= 0.4 else "IMBALANCED"
            }
            
        except Exception as e:
            return {"error": f"Distribution assessment failed: {e}", "score": 0.0}
    
    async def generate_recommendations(self, schema_results: Dict, quality_results: Dict, ml_readiness: Dict) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # Schema recommendations
        if schema_results.get("schema_score", 0) < 0.8:
            recommendations.append("🔧 Database schema issues detected. Ensure all required tables and columns exist.")
        
        # Data quality recommendations
        quality_score = quality_results.get("quality_score", 0)
        if quality_score < 0.7:
            recommendations.append("🧹 Data quality below threshold. Run data cleanup and validation routines.")
        
        completeness = quality_results.get("completeness", {})
        if completeness.get("score", 0) < 0.8:
            recommendations.append("📊 Data completeness issues. Backfill missing price and performance data.")
        
        freshness = quality_results.get("freshness", {})
        if freshness.get("score", 0) < 0.8:
            recommendations.append("🕐 Data freshness issues. Update recent signal performance data.")
        
        # ML readiness recommendations
        sample_size = ml_readiness.get("sample_size", {})
        if sample_size.get("score", 0) < 0.6:
            recommendations.append("📈 Insufficient sample size for reliable ML predictions. Increase data collection period.")
        
        distribution = ml_readiness.get("distribution_balance", {})
        if distribution.get("score", 0) < 0.5:
            recommendations.append("⚖️ Data distribution imbalanced. Consider stratified sampling or balancing techniques.")
        
        # Specific action recommendations
        if not recommendations:
            recommendations.append("✅ Data validation passed! Your system is ready for ML analysis.")
        else:
            recommendations.append("🚀 Run !updateanalytics after implementing fixes to refresh the analysis data.")
        
        return recommendations
    
    def calculate_overall_score(self, schema_results: Dict, quality_results: Dict, ml_readiness: Dict) -> float:
        """Calculate overall data validation score"""
        schema_score = schema_results.get("schema_score", 0)
        quality_score = quality_results.get("quality_score", 0)
        ml_score = ml_readiness.get("ml_score", 0)
        
        # Weighted average
        overall_score = (
            schema_score * 0.2 +      # Schema is foundational but once fixed, stays fixed
            quality_score * 0.5 +     # Data quality is most important
            ml_score * 0.3            # ML readiness determines analysis capability
        )
        
        return round(overall_score, 3)

# Async functions for external use
async def validate_data(days: int = 30) -> Dict:
    """Quick validation function for external use"""
    validator = DataValidator()
    return await validator.validate_all_data(days)

async def quick_health_check() -> Dict:
    """Quick health check for critical issues"""
    validator = DataValidator()
    try:
        conn = await asyncpg.connect(validator.db_url)
        
        # Check basic connectivity and recent data
        recent_count = await conn.fetchval('''
            SELECT COUNT(*) FROM signal_performance 
            WHERE performance_date >= NOW() - INTERVAL '7 days'
        ''')
        
        total_count = await conn.fetchval('SELECT COUNT(*) FROM signal_performance')
        
        await conn.close()
        
        return {
            "status": "healthy" if recent_count > 0 else "warning",
            "recent_records_7d": recent_count,
            "total_records": total_count,
            "recommendation": "System operational" if recent_count > 0 else "Run data backfill process"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "recommendation": "Check database connectivity and configuration"
        }

if __name__ == "__main__":
    async def main():
        print("🔍 COMPREHENSIVE DATA VALIDATION")
        print("=" * 50)
        
        validator = DataValidator()
        results = await validator.validate_all_data(30)
        
        print(f"\n📊 Overall Score: {results.get('overall_score', 0):.1%}")
        print(f"🕐 Validation Time: {results.get('timestamp', 'Unknown')}")
        
        if 'recommendations' in results:
            print(f"\n💡 Recommendations:")
            for rec in results['recommendations']:
                print(f"  • {rec}")
        
        print(f"\n📋 Full Report: {json.dumps(results, indent=2, default=str)}")
    
    asyncio.run(main()) 