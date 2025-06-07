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
import warnings
warnings.filterwarnings('ignore')

load_dotenv()

class AdvancedAnalytics:
    def __init__(self):
        self.db_url = os.getenv('DATABASE_URL')
        self.correlation_cache = {}
        self.ml_models = {}
        
    async def get_correlation_analysis(self, days: int = 30) -> Dict:
        """Analyze correlations between different signals and their success rates"""
        try:
            conn = await asyncpg.connect(self.db_url)
            since_date = datetime.now() - timedelta(days=days)
            
            # Get comprehensive signal data
            signals_data = await conn.fetch('''
                SELECT 
                    sp.ticker,
                    sp.timeframe,
                    sp.signal_type,
                    sp.signal_date,
                    sp.price_at_signal,
                    sp.price_after_1h,
                    sp.price_after_6h,
                    sp.price_after_1d,
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
                    EXTRACT(hour FROM sp.signal_date) as signal_hour,
                    EXTRACT(dow FROM sp.signal_date) as signal_dow,
                    (sp.price_after_1d - sp.price_at_signal) / sp.price_at_signal * 100 as return_1d
                FROM signal_performance sp
                WHERE sp.performance_date >= $1
                  AND sp.price_at_signal IS NOT NULL 
                  AND sp.price_after_1d IS NOT NULL
                  AND sp.price_after_6h IS NOT NULL
                ORDER BY sp.signal_date DESC
            ''', since_date)
            
            await conn.close()
            
            if not signals_data:
                return {"error": "No signal data available for correlation analysis"}
            
            # Convert to DataFrame for analysis
            df = pd.DataFrame([dict(row) for row in signals_data])
            
            # Analyze signal combination patterns
            correlation_results = await self.analyze_signal_combinations(df)
            
            # Analyze temporal patterns
            temporal_patterns = await self.analyze_temporal_patterns(df)
            
            # Analyze ticker relationships
            ticker_correlations = await self.analyze_ticker_correlations(df)
            
            return {
                "signal_combinations": correlation_results,
                "temporal_patterns": temporal_patterns,
                "ticker_correlations": ticker_correlations,
                "total_signals_analyzed": len(df),
                "analysis_period": f"{days} days"
            }
            
        except Exception as e:
            return {"error": f"Correlation analysis failed: {e}"}
    
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
                "ticker_success_correlation": {},
                "cross_ticker_patterns": []
            }
            
            # Calculate success rates by ticker
            ticker_success = df.groupby('ticker').agg({
                'success_1d': ['mean', 'count'],
                'return_1d': 'mean'
            }).round(3)
            
            # Find tickers with significant data
            significant_tickers = []
            for ticker in ticker_success.index:
                if ticker_success.loc[ticker, ('success_1d', 'count')] >= 10:
                    significant_tickers.append({
                        "ticker": ticker,
                        "success_rate": float(ticker_success.loc[ticker, ('success_1d', 'mean')] * 100),
                        "avg_return": float(ticker_success.loc[ticker, ('return_1d', 'mean')]),
                        "signal_count": int(ticker_success.loc[ticker, ('success_1d', 'count')])
                    })
            
            results["ticker_success_correlation"] = sorted(
                significant_tickers, key=lambda x: x["success_rate"], reverse=True
            )
            
            return results
            
        except Exception as e:
            return {"error": f"Ticker correlation analysis failed: {e}"}
    
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
            
            # Create feature matrix
            features = [
                'ticker_encoded', 'timeframe_encoded', 'signal_type_encoded',
                'signal_hour', 'signal_dow', 'signal_day', 'signal_direction_encoded'
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

# Global instance
advanced_analytics = AdvancedAnalytics() 