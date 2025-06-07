#!/usr/bin/env python3
import asyncio
import asyncpg
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
import json
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, accuracy_score
from sklearn.preprocessing import LabelEncoder, StandardScaler
from scipy import stats
from scipy.stats import chi2_contingency, pearsonr
import warnings
warnings.filterwarnings('ignore')

load_dotenv()

class AdvancedAnalytics:
    def __init__(self):
        self.db_url = os.getenv('DATABASE_URL')
        self.correlation_cache = {}
        self.ml_models = {}
        
    async def get_correlation_analysis(self, days: int = 30) -> Dict:
        """Enhanced correlations with advanced pattern analysis"""
        try:
            conn = await asyncpg.connect(self.db_url)
            since_date = datetime.now() - timedelta(days=days)
            
            # Get comprehensive signal data with enhanced fields
            signals_data = await conn.fetch('''
                SELECT 
                    sp.ticker,
                    sp.timeframe,
                    sp.signal_type,
                    sp.signal_date,
                    sp.price_at_signal,
                    sp.price_after_1h,
                    sp.price_after_3h,
                    sp.price_after_6h,
                    sp.price_after_1d,
                    sp.strength,
                    sp.system,
                    CASE 
                        WHEN sp.signal_type ILIKE '%bullish%' OR sp.signal_type ILIKE '%buy%' OR sp.signal_type ILIKE '%oversold%' OR sp.signal_type ILIKE '%entry%' THEN 'BULLISH'
                        WHEN sp.signal_type ILIKE '%bearish%' OR sp.signal_type ILIKE '%sell%' OR sp.signal_type ILIKE '%overbought%' THEN 'BEARISH'
                        ELSE 'NEUTRAL'
                    END as signal_direction,
                    CASE 
                        WHEN (sp.signal_type ILIKE '%bullish%' OR sp.signal_type ILIKE '%buy%' OR sp.signal_type ILIKE '%oversold%' OR sp.signal_type ILIKE '%entry%')
                             AND sp.price_after_1d > sp.price_at_signal THEN 1
                        WHEN (sp.signal_type ILIKE '%bearish%' OR sp.signal_type ILIKE '%sell%' OR sp.signal_type ILIKE '%overbought%')
                             AND sp.price_after_1d < sp.price_at_signal THEN 1
                        ELSE 0
                    END as success_1d,
                    CASE 
                        WHEN (sp.signal_type ILIKE '%bullish%' OR sp.signal_type ILIKE '%buy%' OR sp.signal_type ILIKE '%oversold%' OR sp.signal_type ILIKE '%entry%')
                             AND sp.price_after_6h > sp.price_at_signal THEN 1
                        WHEN (sp.signal_type ILIKE '%bearish%' OR sp.signal_type ILIKE '%sell%' OR sp.signal_type ILIKE '%overbought%')
                             AND sp.price_after_6h < sp.price_at_signal THEN 1
                        ELSE 0
                    END as success_6h,
                    CASE 
                        WHEN (sp.signal_type ILIKE '%bullish%' OR sp.signal_type ILIKE '%buy%' OR sp.signal_type ILIKE '%oversold%' OR sp.signal_type ILIKE '%entry%')
                             AND sp.price_after_1h > sp.price_at_signal THEN 1
                        WHEN (sp.signal_type ILIKE '%bearish%' OR sp.signal_type ILIKE '%sell%' OR sp.signal_type ILIKE '%overbought%')
                             AND sp.price_after_1h < sp.price_at_signal THEN 1
                        ELSE 0
                    END as success_1h,
                    EXTRACT(hour FROM sp.signal_date) as signal_hour,
                    EXTRACT(dow FROM sp.signal_date) as signal_dow,
                    ABS((sp.price_after_1d - sp.price_at_signal) / sp.price_at_signal * 100) as volatility_1d,
                    (sp.price_after_1d - sp.price_at_signal) / sp.price_at_signal * 100 as return_1d,
                    (sp.price_after_6h - sp.price_at_signal) / sp.price_at_signal * 100 as return_6h,
                    (sp.price_after_1h - sp.price_at_signal) / sp.price_at_signal * 100 as return_1h
                FROM signal_performance sp
                WHERE sp.performance_date >= $1
                  AND sp.price_at_signal IS NOT NULL 
                  AND sp.price_after_1d IS NOT NULL
                  AND sp.price_after_6h IS NOT NULL
                  AND sp.price_after_1h IS NOT NULL
                ORDER BY sp.signal_date DESC
            ''', since_date)
            
            await conn.close()
            
            if not signals_data:
                return {"error": "No signal data available for correlation analysis"}
            
            # Convert to DataFrame for analysis
            df = pd.DataFrame([dict(row) for row in signals_data])
            
            # Enhanced analysis modules
            correlation_results = await self.analyze_signal_combinations(df)
            temporal_patterns = await self.analyze_temporal_patterns(df)
            ticker_correlations = await self.analyze_ticker_correlations(df)
            
            # NEW: Advanced correlation features
            strength_analysis = await self.analyze_strength_correlations(df)
            market_condition_analysis = await self.analyze_market_conditions(df)
            volatility_patterns = await self.analyze_volatility_patterns(df)
            system_performance = await self.analyze_system_correlations(df)
            statistical_significance = await self.analyze_statistical_significance(df)
            
            return {
                "signal_combinations": correlation_results,
                "temporal_patterns": temporal_patterns,
                "ticker_correlations": ticker_correlations,
                "strength_analysis": strength_analysis,
                "market_conditions": market_condition_analysis,
                "volatility_patterns": volatility_patterns,
                "system_performance": system_performance,
                "statistical_significance": statistical_significance,
                "total_signals_analyzed": len(df),
                "analysis_period": f"{days} days",
                "data_quality_score": self.calculate_data_quality_score(df)
            }
            
        except Exception as e:
            return {"error": f"Enhanced correlation analysis failed: {e}"}
    
    async def analyze_signal_combinations(self, df: pd.DataFrame) -> Dict:
        """Find signals that tend to work well together"""
        try:
            results = {
                "high_success_combinations": [],
                "signal_type_correlations": {},
                "timeframe_synergies": {}
            }
            
            # Group by time windows to find concurrent signals
            df['time_window'] = df['signal_date'].dt.floor('1h')
            
            concurrent_signals = df.groupby(['ticker', 'time_window']).agg({
                'signal_type': list,
                'timeframe': list,
                'success_1d': 'mean',
                'success_6h': 'mean',
                'return_1d': 'mean'
            }).reset_index()
            
            # Find combinations with multiple signals
            multi_signal_windows = concurrent_signals[
                concurrent_signals['signal_type'].apply(len) > 1
            ]
            
            if len(multi_signal_windows) > 0:
                for _, row in multi_signal_windows.iterrows():
                    signal_combo = tuple(sorted(set(row['signal_type'])))
                    timeframe_combo = tuple(sorted(set(row['timeframe'])))
                    
                    if len(signal_combo) > 1:  # Only multi-signal combinations
                        combo_key = " + ".join(signal_combo[:2])  # Limit to first 2 for readability
                        
                        if combo_key not in results["signal_type_correlations"]:
                            results["signal_type_correlations"][combo_key] = {
                                "count": 0,
                                "avg_success_1d": 0,
                                "avg_return_1d": 0
                            }
                        
                        results["signal_type_correlations"][combo_key]["count"] += 1
                        results["signal_type_correlations"][combo_key]["avg_success_1d"] += row['success_1d']
                        results["signal_type_correlations"][combo_key]["avg_return_1d"] += row['return_1d']
            
            # Calculate averages and find best combinations
            for combo in results["signal_type_correlations"]:
                count = results["signal_type_correlations"][combo]["count"]
                if count > 0:
                    results["signal_type_correlations"][combo]["avg_success_1d"] /= count
                    results["signal_type_correlations"][combo]["avg_return_1d"] /= count
                    
                    # Add to high success combinations if success rate > 60%
                    if (results["signal_type_correlations"][combo]["avg_success_1d"] > 0.6 and 
                        count >= 3):
                        results["high_success_combinations"].append({
                            "combination": combo,
                            "success_rate": results["signal_type_correlations"][combo]["avg_success_1d"] * 100,
                            "avg_return": results["signal_type_correlations"][combo]["avg_return_1d"],
                            "occurrence_count": count
                        })
            
            # Sort by success rate
            results["high_success_combinations"].sort(
                key=lambda x: x["success_rate"], reverse=True
            )
            
            return results
            
        except Exception as e:
            return {"error": f"Signal combination analysis failed: {e}"}
    
    async def analyze_temporal_patterns(self, df: pd.DataFrame) -> Dict:
        """Analyze time-based patterns in signal success"""
        try:
            results = {
                "best_hours": [],
                "best_days": [],
                "seasonal_patterns": {}
            }
            
            # Analyze success by hour of day
            hourly_success = df.groupby('signal_hour').agg({
                'success_1d': ['mean', 'count'],
                'return_1d': 'mean'
            }).round(3)
            
            for hour in hourly_success.index:
                if hourly_success.loc[hour, ('success_1d', 'count')] >= 5:  # Minimum 5 signals
                    results["best_hours"].append({
                        "hour": int(hour),
                        "success_rate": float(hourly_success.loc[hour, ('success_1d', 'mean')] * 100),
                        "avg_return": float(hourly_success.loc[hour, ('return_1d', 'mean')]),
                        "signal_count": int(hourly_success.loc[hour, ('success_1d', 'count')])
                    })
            
            results["best_hours"].sort(key=lambda x: x["success_rate"], reverse=True)
            
            # Analyze success by day of week
            daily_success = df.groupby('signal_dow').agg({
                'success_1d': ['mean', 'count'],
                'return_1d': 'mean'
            }).round(3)
            
            day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
            
            for dow in daily_success.index:
                if daily_success.loc[dow, ('success_1d', 'count')] >= 5:
                    results["best_days"].append({
                        "day": day_names[int(dow)],
                        "day_number": int(dow),
                        "success_rate": float(daily_success.loc[dow, ('success_1d', 'mean')] * 100),
                        "avg_return": float(daily_success.loc[dow, ('return_1d', 'mean')]),
                        "signal_count": int(daily_success.loc[dow, ('success_1d', 'count')])
                    })
            
            results["best_days"].sort(key=lambda x: x["success_rate"], reverse=True)
            
            return results
            
        except Exception as e:
            return {"error": f"Temporal pattern analysis failed: {e}"}
    
    async def analyze_ticker_correlations(self, df: pd.DataFrame) -> Dict:
        """Analyze relationships between ticker performance"""
        try:
            results = {
                "ticker_success_correlation": [],
                "cross_ticker_patterns": []
            }
            
            # Success rates by ticker
            ticker_performance = df.groupby('ticker').agg({
                'success_1d': ['mean', 'count'],
                'return_1d': 'mean',
                'volatility_1d': 'mean'
            }).round(3)
            
            ticker_success = []
            for ticker in ticker_performance.index:
                if ticker_performance.loc[ticker, ('success_1d', 'count')] >= 3:
                    ticker_success.append({
                        "ticker": ticker,
                        "success_rate": float(ticker_performance.loc[ticker, ('success_1d', 'mean')] * 100),
                        "avg_return": float(ticker_performance.loc[ticker, ('return_1d', 'mean')]),
                        "avg_volatility": float(ticker_performance.loc[ticker, ('volatility_1d', 'mean')]),
                        "signal_count": int(ticker_performance.loc[ticker, ('success_1d', 'count')])
                    })
            
            results["ticker_success_correlation"] = sorted(ticker_success, key=lambda x: x["success_rate"], reverse=True)
            
            return results
            
        except Exception as e:
            return {"error": f"Ticker correlation analysis failed: {e}"}
    
    async def analyze_strength_correlations(self, df: pd.DataFrame) -> Dict:
        """Analyze signal strength correlations with success rates"""
        try:
            results = {
                "strength_correlation": {},
                "optimal_strength_ranges": []
            }
            
            # Only analyze if strength data is available
            if 'strength' in df.columns and df['strength'].notna().sum() > 10:
                # Calculate correlation between strength and success
                strength_corr = df[['strength', 'success_1d']].corr().iloc[0, 1]
                results["strength_correlation"] = {
                    "correlation_coefficient": float(strength_corr) if not pd.isna(strength_corr) else 0,
                    "significance": "High" if abs(strength_corr) > 0.3 else "Medium" if abs(strength_corr) > 0.1 else "Low"
                }
                
                # Find optimal strength ranges
                df['strength_range'] = pd.cut(df['strength'], bins=5, labels=['Very Low', 'Low', 'Medium', 'High', 'Very High'])
                strength_analysis = df.groupby('strength_range').agg({
                    'success_1d': ['mean', 'count'],
                    'return_1d': 'mean'
                }).round(3)
                
                for strength_range in strength_analysis.index:
                    if strength_analysis.loc[strength_range, ('success_1d', 'count')] >= 3:
                        results["optimal_strength_ranges"].append({
                            "range": str(strength_range),
                            "success_rate": float(strength_analysis.loc[strength_range, ('success_1d', 'mean')] * 100),
                            "avg_return": float(strength_analysis.loc[strength_range, ('return_1d', 'mean')]),
                            "count": int(strength_analysis.loc[strength_range, ('success_1d', 'count')])
                        })
                
                results["optimal_strength_ranges"].sort(key=lambda x: x["success_rate"], reverse=True)
            
            return results
            
        except Exception as e:
            return {"error": f"Strength correlation analysis failed: {e}"}
    
    async def analyze_market_conditions(self, df: pd.DataFrame) -> Dict:
        """Analyze performance under different market conditions"""
        try:
            results = {
                "volatility_performance": [],
                "market_regime_analysis": {}
            }
            
            # Volatility-based performance analysis
            df['volatility_category'] = pd.cut(df['volatility_1d'], 
                                               bins=[0, 2, 5, float('inf')], 
                                               labels=['Low', 'Medium', 'High'])
            
            vol_analysis = df.groupby('volatility_category').agg({
                'success_1d': ['mean', 'count'],
                'return_1d': 'mean'
            }).round(3)
            
            for vol_cat in vol_analysis.index:
                if vol_analysis.loc[vol_cat, ('success_1d', 'count')] >= 3:
                    results["volatility_performance"].append({
                        "category": str(vol_cat),
                        "success_rate": float(vol_analysis.loc[vol_cat, ('success_1d', 'mean')] * 100),
                        "avg_return": float(vol_analysis.loc[vol_cat, ('return_1d', 'mean')]),
                        "signal_count": int(vol_analysis.loc[vol_cat, ('success_1d', 'count')])
                    })
            
            results["volatility_performance"].sort(key=lambda x: x["success_rate"], reverse=True)
            
            # Market regime analysis based on overall returns
            avg_return = df['return_1d'].mean()
            market_regime = "Bullish" if avg_return > 1 else "Bearish" if avg_return < -1 else "Neutral"
            
            results["market_regime_analysis"] = {
                "current_regime": market_regime,
                "avg_market_return": float(avg_return),
                "signal_performance_in_regime": float(df['success_1d'].mean() * 100)
            }
            
            return results
            
        except Exception as e:
            return {"error": f"Market conditions analysis failed: {e}"}
    
    async def analyze_volatility_patterns(self, df: pd.DataFrame) -> Dict:
        """Analyze volatility patterns and trends"""
        try:
            results = {
                "trend": "Neutral",
                "volatility_distribution": {},
                "volatility_success_correlation": 0
            }
            
            # Calculate volatility trend
            df_sorted = df.sort_values('signal_date')
            if len(df_sorted) > 10:
                early_vol = df_sorted.head(len(df_sorted)//2)['volatility_1d'].mean()
                late_vol = df_sorted.tail(len(df_sorted)//2)['volatility_1d'].mean()
                
                if late_vol > early_vol * 1.1:
                    results["trend"] = "Increasing"
                elif late_vol < early_vol * 0.9:
                    results["trend"] = "Decreasing"
                else:
                    results["trend"] = "Stable"
            
            # Volatility-success correlation
            vol_success_corr = df[['volatility_1d', 'success_1d']].corr().iloc[0, 1]
            results["volatility_success_correlation"] = float(vol_success_corr) if not pd.isna(vol_success_corr) else 0
            
            # Distribution analysis
            results["volatility_distribution"] = {
                "mean": float(df['volatility_1d'].mean()),
                "median": float(df['volatility_1d'].median()),
                "std": float(df['volatility_1d'].std())
            }
            
            return results
            
        except Exception as e:
            return {"error": f"Volatility patterns analysis failed: {e}"}
    
    async def analyze_system_correlations(self, df: pd.DataFrame) -> Dict:
        """Analyze performance by signal system/source"""
        try:
            results = {
                "system_rankings": [],
                "system_correlations": {}
            }
            
            # Only analyze if system data is available
            if 'system' in df.columns and df['system'].notna().sum() > 5:
                system_performance = df.groupby('system').agg({
                    'success_1d': ['mean', 'count'],
                    'return_1d': 'mean'
                }).round(3)
                
                system_rankings = []
                for system in system_performance.index:
                    if system_performance.loc[system, ('success_1d', 'count')] >= 3:
                        system_rankings.append({
                            "system": str(system),
                            "success_rate": float(system_performance.loc[system, ('success_1d', 'mean')] * 100),
                            "avg_return": float(system_performance.loc[system, ('return_1d', 'mean')]),
                            "signal_count": int(system_performance.loc[system, ('success_1d', 'count')])
                        })
                
                # Rank systems by success rate
                system_rankings.sort(key=lambda x: x["success_rate"], reverse=True)
                for i, system in enumerate(system_rankings):
                    system["rank"] = i + 1
                
                results["system_rankings"] = system_rankings
            
            return results
            
        except Exception as e:
            return {"error": f"System correlation analysis failed: {e}"}
    
    async def analyze_statistical_significance(self, df: pd.DataFrame) -> Dict:
        """Analyze statistical significance of patterns"""
        try:
            results = {
                "overall_confidence": "Medium",
                "sample_size_adequacy": {},
                "pattern_significance": {}
            }
            
            # Sample size analysis
            total_signals = len(df)
            if total_signals >= 100:
                results["overall_confidence"] = "High"
            elif total_signals >= 50:
                results["overall_confidence"] = "Medium"
            else:
                results["overall_confidence"] = "Low"
            
            results["sample_size_adequacy"] = {
                "total_signals": total_signals,
                "confidence_threshold": "100+ signals for high confidence",
                "current_level": results["overall_confidence"]
            }
            
            # Chi-square test for signal type vs success
            if len(df) > 20:
                try:
                    contingency_table = pd.crosstab(df['signal_type'], df['success_1d'])
                    if contingency_table.shape[0] > 1 and contingency_table.shape[1] > 1:
                        chi2, p_value, dof, expected = chi2_contingency(contingency_table)
                        results["pattern_significance"] = {
                            "signal_type_significance": "Significant" if p_value < 0.05 else "Not Significant",
                            "p_value": float(p_value),
                            "chi2_statistic": float(chi2)
                        }
                except Exception:
                    pass
            
            return results
            
        except Exception as e:
            return {"error": f"Statistical significance analysis failed: {e}"}
    
    def calculate_data_quality_score(self, df: pd.DataFrame) -> float:
        """Calculate a data quality score based on completeness and reliability"""
        try:
            # Key field completeness
            key_fields = ['price_at_signal', 'price_after_1h', 'price_after_6h', 'price_after_1d', 
                         'success_1h', 'success_6h', 'success_1d']
            
            completeness_scores = []
            for field in key_fields:
                if field in df.columns:
                    completeness = df[field].notna().sum() / len(df)
                    completeness_scores.append(completeness)
                else:
                    completeness_scores.append(0)
            
            # Overall completeness
            avg_completeness = np.mean(completeness_scores)
            
            # Sample size factor
            sample_size_factor = min(1.0, len(df) / 100)  # Optimal at 100+ signals
            
            # Recency factor (more recent data is better)
            if 'signal_date' in df.columns:
                latest_signal = df['signal_date'].max()
                days_since_latest = (datetime.now() - latest_signal).days
                recency_factor = max(0.5, 1 - (days_since_latest / 30))  # Decay over 30 days
            else:
                recency_factor = 0.8
            
            # Combined quality score
            quality_score = (avg_completeness * 0.5 + sample_size_factor * 0.3 + recency_factor * 0.2)
            
            return min(1.0, quality_score)
            
        except Exception:
            return 0.5  # Default medium quality
    
    async def get_ml_predictions(self, days: int = 90) -> Dict:
        """Use machine learning to predict signal success probability"""
        try:
            conn = await asyncpg.connect(self.db_url)
            since_date = datetime.now() - timedelta(days=days)
            
            # Get comprehensive training data
            training_data = await conn.fetch('''
                SELECT 
                    sp.ticker,
                    sp.timeframe,
                    sp.signal_type,
                    sp.signal_date,
                    sp.price_at_signal,
                    sp.price_after_1h,
                    sp.price_after_6h,
                    sp.price_after_1d,
                    sp.strength,
                    sp.system,
                    EXTRACT(hour FROM sp.signal_date) as signal_hour,
                    EXTRACT(dow FROM sp.signal_date) as signal_dow,
                    EXTRACT(day FROM sp.signal_date) as signal_day,
                    CASE 
                        WHEN sp.signal_type ILIKE '%bullish%' OR sp.signal_type ILIKE '%buy%' OR sp.signal_type ILIKE '%oversold%' OR sp.signal_type ILIKE '%entry%' THEN 1
                        WHEN sp.signal_type ILIKE '%bearish%' OR sp.signal_type ILIKE '%sell%' OR sp.signal_type ILIKE '%overbought%' THEN -1
                        ELSE 0
                    END as signal_direction_encoded,
                    CASE 
                        WHEN (sp.signal_type ILIKE '%bullish%' OR sp.signal_type ILIKE '%buy%' OR sp.signal_type ILIKE '%oversold%' OR sp.signal_type ILIKE '%entry%')
                             AND sp.price_after_1d > sp.price_at_signal THEN 1
                        WHEN (sp.signal_type ILIKE '%bearish%' OR sp.signal_type ILIKE '%sell%' OR sp.signal_type ILIKE '%overbought%')
                             AND sp.price_after_1d < sp.price_at_signal THEN 1
                        ELSE 0
                    END as success_1d
                FROM signal_performance sp
                WHERE sp.performance_date >= $1
                  AND sp.price_at_signal IS NOT NULL 
                  AND sp.price_after_1d IS NOT NULL
                  AND sp.price_after_6h IS NOT NULL
                  AND sp.price_after_1h IS NOT NULL
                ORDER BY sp.signal_date DESC
            ''', since_date)
            
            await conn.close()
            
            if len(training_data) < 50:
                return {"error": "Insufficient data for ML predictions (need at least 50 signals)"}
            
            # Convert to DataFrame
            df = pd.DataFrame([dict(row) for row in training_data])
            
            # Prepare features for ML
            ml_results = await self.train_prediction_models(df)
            
            return ml_results
            
        except Exception as e:
            return {"error": f"ML prediction failed: {e}"}
    
    async def train_prediction_models(self, df: pd.DataFrame) -> Dict:
        """Train machine learning models to predict signal success"""
        try:
            # Encode categorical features
            le_ticker = LabelEncoder()
            le_timeframe = LabelEncoder()
            le_signal_type = LabelEncoder()
            
            df_encoded = df.copy()
            df_encoded['ticker_encoded'] = le_ticker.fit_transform(df['ticker'])
            df_encoded['timeframe_encoded'] = le_timeframe.fit_transform(df['timeframe'])
            df_encoded['signal_type_encoded'] = le_signal_type.fit_transform(df['signal_type'])
            
            # Handle missing strength/system data
            df_encoded['strength'] = df_encoded['strength'].fillna(df_encoded['strength'].median())
            df_encoded['system_encoded'] = 0  # Default for missing system data
            if 'system' in df_encoded.columns and not df_encoded['system'].isna().all():
                le_system = LabelEncoder()
                df_encoded['system_encoded'] = le_system.fit_transform(df_encoded['system'].fillna('unknown'))
            
            # Create enhanced feature matrix
            features = [
                'ticker_encoded', 'timeframe_encoded', 'signal_type_encoded',
                'signal_hour', 'signal_dow', 'signal_day', 'signal_direction_encoded',
                'strength', 'system_encoded'
            ]
            
            X = df_encoded[features]
            y = df_encoded['success_1d']
            
            # Split the data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )
            
            # Train multiple models
            models = {
                'Random Forest': RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10),
                'Gradient Boosting': GradientBoostingClassifier(random_state=42, max_depth=6)
            }
            
            results = {
                "model_performance": {},
                "feature_importance": {},
                "predictions": {},
                "training_stats": {
                    "total_samples": len(df),
                    "training_samples": len(X_train),
                    "test_samples": len(X_test),
                    "positive_class_ratio": y.mean()
                }
            }
            
            for model_name, model in models.items():
                # Train model
                model.fit(X_train, y_train)
                
                # Make predictions
                y_pred = model.predict(X_test)
                y_prob = model.predict_proba(X_test)[:, 1]
                
                # Calculate metrics
                accuracy = accuracy_score(y_test, y_pred)
                cv_scores = cross_val_score(model, X_train, y_train, cv=5)
                
                results["model_performance"][model_name] = {
                    "accuracy": float(accuracy),
                    "cv_mean": float(cv_scores.mean()),
                    "cv_std": float(cv_scores.std())
                }
                
                # Feature importance
                if hasattr(model, 'feature_importances_'):
                    importance = dict(zip(features, model.feature_importances_))
                    results["feature_importance"][model_name] = {
                        k: float(v) for k, v in sorted(importance.items(), 
                                                     key=lambda x: x[1], reverse=True)
                    }
            
            # Generate predictions for recent signals
            recent_predictions = await self.generate_recent_predictions(
                models['Random Forest'], df_encoded, features, le_ticker, le_timeframe, le_signal_type
            )
            results["predictions"] = recent_predictions
            
            return results
            
        except Exception as e:
            return {"error": f"Model training failed: {e}"}
    
    async def generate_recent_predictions(self, model, df_encoded, features, le_ticker, le_timeframe, le_signal_type) -> Dict:
        """Generate predictions for recent signals"""
        try:
            # Get most recent signals (last 7 days)
            recent_cutoff = datetime.now() - timedelta(days=7)
            recent_df = df_encoded[df_encoded['signal_date'] >= recent_cutoff].copy()
            
            if len(recent_df) == 0:
                return {"recent_predictions": []}
            
            # Make predictions
            X_recent = recent_df[features]
            probabilities = model.predict_proba(X_recent)[:, 1]
            predictions = model.predict(X_recent)
            
            # Format results
            prediction_results = []
            for i, (_, row) in enumerate(recent_df.iterrows()):
                prediction_results.append({
                    "ticker": row['ticker'],
                    "signal_type": row['signal_type'],
                    "timeframe": row['timeframe'],
                    "signal_date": row['signal_date'].strftime('%Y-%m-%d %H:%M'),
                    "predicted_success_probability": float(probabilities[i]),
                    "predicted_outcome": "SUCCESS" if predictions[i] == 1 else "FAILURE",
                    "actual_outcome": "SUCCESS" if row['success_1d'] == 1 else "FAILURE",
                    "confidence_level": "HIGH" if abs(probabilities[i] - 0.5) > 0.3 else "MEDIUM" if abs(probabilities[i] - 0.5) > 0.15 else "LOW"
                })
            
            # Sort by probability
            prediction_results.sort(key=lambda x: x["predicted_success_probability"], reverse=True)
            
            return {
                "recent_predictions": prediction_results[:15],  # Top 15 predictions
                "prediction_summary": {
                    "total_recent_signals": len(prediction_results),
                    "high_confidence_predictions": len([p for p in prediction_results if p["confidence_level"] == "HIGH"])
                }
            }
            
        except Exception as e:
            return {"error": f"Recent predictions failed: {e}"}
    
    async def predict_single_signal(self, signal_features: Dict) -> Dict:
        """Predict success probability for a single signal in real-time"""
        try:
            # Quick feature engineering for real-time prediction
            from datetime import datetime, timedelta
            import pandas as pd
            
            conn = await asyncpg.connect(self.db_url)
            
            # Get recent historical data for this ticker/timeframe (last 30 days for speed)
            recent_data = await conn.fetch('''
                SELECT 
                    sp.ticker,
                    sp.timeframe,
                    sp.signal_type,
                    sp.strength,
                    sp.system,
                    CASE 
                        WHEN (sp.signal_type ILIKE '%bullish%' OR sp.signal_type ILIKE '%buy%' OR sp.signal_type ILIKE '%oversold%' OR sp.signal_type ILIKE '%entry%')
                             AND sp.price_after_1d > sp.price_at_signal THEN 1
                        WHEN (sp.signal_type ILIKE '%bearish%' OR sp.signal_type ILIKE '%sell%' OR sp.signal_type ILIKE '%overbought%')
                             AND sp.price_after_1d < sp.price_at_signal THEN 1
                        ELSE 0
                    END as success_1d,
                    EXTRACT(hour FROM sp.signal_date) as signal_hour,
                    EXTRACT(dow FROM sp.signal_date) as signal_dow
                FROM signal_performance sp
                WHERE sp.performance_date >= $1
                  AND sp.price_at_signal IS NOT NULL 
                  AND sp.price_after_1d IS NOT NULL
                ORDER BY sp.signal_date DESC
                LIMIT 500
            ''', datetime.now() - timedelta(days=30))
            
            await conn.close()
            
            if len(recent_data) < 20:
                return {"error": "Insufficient recent data for prediction"}
            
            # Convert to DataFrame
            df = pd.DataFrame([dict(row) for row in recent_data])
            
            # Quick success rate calculation for this specific signal type
            similar_signals = df[
                (df['ticker'] == signal_features['ticker']) & 
                (df['timeframe'] == signal_features['timeframe']) &
                (df['signal_type'] == signal_features['signal_type'])
            ]
            
            # Fallback to broader categories if not enough specific data
            if len(similar_signals) < 5:
                similar_signals = df[
                    (df['ticker'] == signal_features['ticker']) & 
                    (df['timeframe'] == signal_features['timeframe'])
                ]
            
            if len(similar_signals) < 5:
                similar_signals = df[df['signal_type'] == signal_features['signal_type']]
            
            if len(similar_signals) < 5:
                similar_signals = df  # Use all data as last resort
            
            # Calculate success probability
            success_rate = similar_signals['success_1d'].mean()
            
            # Adjust based on signal strength
            strength_multiplier = {
                'Very Strong': 1.2,
                'Strong': 1.1,
                'Moderate': 1.0,
                'Weak': 0.8,
                'Unknown': 0.9
            }.get(signal_features.get('strength', 'Unknown'), 0.9)
            
            adjusted_success_rate = min(success_rate * strength_multiplier, 0.95)  # Cap at 95%
            
            # Determine confidence level based on sample size and consistency
            sample_size = len(similar_signals)
            if sample_size >= 50:
                confidence = "high"
            elif sample_size >= 20:
                confidence = "medium"
            else:
                confidence = "low"
            
            # Determine risk level
            if adjusted_success_rate >= 0.7:
                risk_level = "low"
            elif adjusted_success_rate >= 0.5:
                risk_level = "medium"
            else:
                risk_level = "high"
            
            # Get current market hour for timing analysis
            current_hour = datetime.now().hour
            good_hours = [9, 10, 14, 15]  # Market open and close hours
            timing_bonus = 1.05 if current_hour in good_hours else 1.0
            
            final_probability = min(adjusted_success_rate * timing_bonus, 0.95)
            
            return {
                "prediction": {
                    "success_probability": float(final_probability),
                    "confidence": confidence,
                    "risk_level": risk_level,
                    "sample_size": sample_size,
                    "base_success_rate": float(success_rate),
                    "strength_adjustment": strength_multiplier,
                    "timing_bonus": timing_bonus
                }
            }
            
        except Exception as e:
            return {"error": f"Single signal prediction failed: {e}"}
    
    async def analyze_optimal_timing(self, days: int = 30) -> Dict:
        """Analyze optimal timing for signals based on success rates"""
        try:
            conn = await asyncpg.connect(self.db_url)
            since_date = datetime.now() - timedelta(days=days)
            
            # Get timing data for signals
            timing_data = await conn.fetch('''
                SELECT 
                    EXTRACT(hour FROM sp.signal_date) as signal_hour,
                    EXTRACT(dow FROM sp.signal_date) as signal_dow,
                    CASE 
                        WHEN (sp.signal_type ILIKE '%bullish%' OR sp.signal_type ILIKE '%buy%' OR sp.signal_type ILIKE '%oversold%' OR sp.signal_type ILIKE '%entry%')
                             AND sp.price_after_1d > sp.price_at_signal THEN 1
                        WHEN (sp.signal_type ILIKE '%bearish%' OR sp.signal_type ILIKE '%sell%' OR sp.signal_type ILIKE '%overbought%')
                             AND sp.price_after_1d < sp.price_at_signal THEN 1
                        ELSE 0
                    END as success_1d,
                    sp.ticker,
                    sp.signal_type
                FROM signal_performance sp
                WHERE sp.performance_date >= $1
                  AND sp.price_at_signal IS NOT NULL 
                  AND sp.price_after_1d IS NOT NULL
                ORDER BY sp.signal_date DESC
            ''', since_date)
            
            await conn.close()
            
            if len(timing_data) < 10:
                return {"error": "Insufficient data for timing analysis"}
            
            # Convert to DataFrame
            df = pd.DataFrame([dict(row) for row in timing_data])
            
            # Analyze by hour
            hourly_stats = df.groupby('signal_hour').agg({
                'success_1d': ['mean', 'count']
            }).round(4)
            hourly_stats.columns = ['success_rate', 'signal_count']
            
            # Filter hours with at least 3 signals
            hourly_stats = hourly_stats[hourly_stats['signal_count'] >= 3]
            best_hours = hourly_stats.sort_values('success_rate', ascending=False).head(5)
            
            # Analyze by day of week
            daily_stats = df.groupby('signal_dow').agg({
                'success_1d': ['mean', 'count']
            }).round(4)
            daily_stats.columns = ['success_rate', 'signal_count']
            
            # Filter days with at least 3 signals
            daily_stats = daily_stats[daily_stats['signal_count'] >= 3]
            best_days = daily_stats.sort_values('success_rate', ascending=False)
            
            # Find peak combination times
            combo_stats = df.groupby(['signal_dow', 'signal_hour']).agg({
                'success_1d': ['mean', 'count']
            }).round(4)
            combo_stats.columns = ['success_rate', 'signal_count']
            
            # Filter combinations with at least 2 signals
            combo_stats = combo_stats[combo_stats['signal_count'] >= 2]
            peak_combinations = combo_stats.sort_values('success_rate', ascending=False).head(5)
            
            # Generate insights
            insights = {}
            
            if not hourly_stats.empty:
                insights['best_hour_overall'] = int(hourly_stats.index[0])
                insights['worst_hour_overall'] = int(hourly_stats.sort_values('success_rate').index[0])
            
            if not daily_stats.empty:
                # Weekend vs weekday analysis
                weekend_success = df[df['signal_dow'].isin([0, 6])]['success_1d'].mean()  # Sunday=0, Saturday=6
                weekday_success = df[~df['signal_dow'].isin([0, 6])]['success_1d'].mean()
                insights['weekend_vs_weekday'] = weekend_success > weekday_success
            
            return {
                "best_hours": {
                    str(int(hour)): {
                        'success_rate': float(data['success_rate']),
                        'signal_count': int(data['signal_count'])
                    }
                    for hour, data in best_hours.iterrows()
                },
                "best_days": {
                    str(int(day)): {
                        'success_rate': float(data['success_rate']),
                        'signal_count': int(data['signal_count'])
                    }
                    for day, data in best_days.iterrows()
                },
                "peak_combinations": [
                    {
                        'day': int(combo[0]),
                        'hour': int(combo[1]),
                        'success_rate': float(data['success_rate']),
                        'signal_count': int(data['signal_count'])
                    }
                    for combo, data in peak_combinations.iterrows()
                ],
                "insights": insights,
                "total_signals_analyzed": len(df)
            }
            
        except Exception as e:
            return {"error": f"Timing analysis failed: {e}"}

    async def calculate_signal_quality_score(self, signal_features: Dict) -> Dict:
        """Calculate comprehensive quality score for a signal using multiple ML factors"""
        try:
            # Get basic ML prediction
            ml_result = await self.predict_single_signal(signal_features)
            if "error" in ml_result:
                return ml_result
            
            prediction = ml_result['prediction']
            
            # Quality factors with weights
            factors = {
                'success_probability': prediction['success_probability'],
                'confidence_level': {
                    'high': 0.9,
                    'medium': 0.7,
                    'low': 0.4
                }.get(prediction.get('confidence', 'medium'), 0.7),
                'risk_level': {
                    'low': 0.9,
                    'medium': 0.6,
                    'high': 0.2
                }.get(prediction.get('risk_level', 'medium'), 0.6),
                'sample_size_factor': min(prediction.get('sample_size', 20) / 50, 1.0),  # Cap at 1.0
                'timing_bonus': prediction.get('timing_bonus', 1.0)
            }
            
            # Calculate weighted quality score (0-100)
            weights = {
                'success_probability': 0.4,  # 40% weight
                'confidence_level': 0.25,    # 25% weight
                'risk_level': 0.2,           # 20% weight
                'sample_size_factor': 0.1,   # 10% weight
                'timing_bonus': 0.05         # 5% weight
            }
            
            quality_score = sum(
                factors[factor] * weight 
                for factor, weight in weights.items()
            ) * 100
            
            # Quality grade
            if quality_score >= 85:
                grade = "A+"
                grade_emoji = "🏆"
                recommendation = "EXCELLENT - High priority signal"
            elif quality_score >= 75:
                grade = "A"
                grade_emoji = "🔥"
                recommendation = "VERY GOOD - Send immediately"
            elif quality_score >= 65:
                grade = "B+"
                grade_emoji = "⭐"
                recommendation = "GOOD - Consider sending"
            elif quality_score >= 55:
                grade = "B"
                grade_emoji = "👍"
                recommendation = "AVERAGE - Monitor closely"
            elif quality_score >= 45:
                grade = "C+"
                grade_emoji = "⚠️"
                recommendation = "BELOW AVERAGE - Use caution"
            elif quality_score >= 35:
                grade = "C"
                grade_emoji = "👎"
                recommendation = "POOR - Avoid unless other factors"
            else:
                grade = "D"
                grade_emoji = "🚫"
                recommendation = "VERY POOR - Do not send"
            
            return {
                "quality_score": round(quality_score, 1),
                "grade": grade,
                "grade_emoji": grade_emoji,
                "recommendation": recommendation,
                "factors": factors,
                "prediction_details": prediction
            }
            
        except Exception as e:
            return {"error": f"Quality scoring failed: {e}"}

# Global instance
advanced_analytics = AdvancedAnalytics() 