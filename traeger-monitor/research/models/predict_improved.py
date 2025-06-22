#!/usr/bin/env python3
"""Improved temperature prediction for Traeger monitor with better accuracy."""
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
import logging

try:
    import xgboost as xgb
    import numpy as np
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "traeger.db"
MODEL_CACHE = {}
DATA_CACHE = {}

def get_cook_data(cook_id: str, probe_channel: str):
    """Get temperature data for a cook/probe from last 12 hours."""
    cutoff = (datetime.now() - timedelta(hours=12)).isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("""
            SELECT timestamp, payload FROM raw_messages 
            WHERE timestamp > ? ORDER BY timestamp""", (cutoff,))
        
        times, temps, targets, grill_temps = [], [], [], []
        for timestamp, payload in rows:
            status = json.loads(payload).get('status', {})
            if status.get('cook_id') != cook_id: continue
            
            t = datetime.fromisoformat(timestamp)
            grill_temp = status.get('grill', 0)
            
            # Check legacy probe format
            if probe_channel == 'legacy' and status.get('probe_con') == 1:
                temp = status.get('probe')
                target = status.get('probe_set')
                if temp is not None and target is not None and target > 0:
                    times.append(t)
                    temps.append(temp)
                    targets.append(target)
                    grill_temps.append(grill_temp)
                continue
            
            # Find probe in acc array
            for acc in status.get('acc', []):
                if acc.get('channel') == probe_channel and acc.get('con') == 1:
                    if acc['type'] == 'probe':
                        temp = acc.get('probe', {}).get('get_temp')
                        target = acc.get('probe', {}).get('set_temp')
                    elif acc['type'] == 'btprobe':
                        temp = acc.get('btprobe', {}).get('get_temp')
                        target = acc.get('btprobe', {}).get('set_temp')
                    else:
                        continue
                    
                    if temp is not None and target is not None and target > 0:
                        times.append(t)
                        temps.append(temp)
                        targets.append(target)
                        grill_temps.append(grill_temp)
    
    DATA_CACHE[(cook_id, probe_channel)] = (times, temps, targets, grill_temps)
    return times, temps, targets, grill_temps

def calculate_rate(times, temps, window_minutes=10):
    """Calculate temperature rate with proper handling of stalls."""
    if len(temps) < 2:
        return 0.0
    
    # Find data points within window
    recent_time = times[-1] - timedelta(minutes=window_minutes)
    recent_indices = [i for i, t in enumerate(times) if t > recent_time]
    
    if len(recent_indices) < 2:
        recent_indices = list(range(max(0, len(times)-5), len(times)))
    
    if len(recent_indices) < 2:
        return 0.0
    
    # Calculate rate using linear regression for stability
    x = [(times[i] - times[recent_indices[0]]).total_seconds() / 60 for i in recent_indices]
    y = [temps[i] for i in recent_indices]
    
    if max(x) - min(x) == 0:
        return 0.0
    
    # Simple linear regression
    n = len(x)
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(x[i] * y[i] for i in range(n))
    sum_x2 = sum(x[i] ** 2 for i in range(n))
    
    denominator = n * sum_x2 - sum_x ** 2
    if abs(denominator) < 1e-6:
        return 0.0
    
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return slope

def linear_prediction_improved(times, temps, current_temp, target_temp):
    """Improved linear prediction with better rate calculation."""
    if len(temps) < 2 or current_temp >= target_temp:
        return 0, "Already at target"
    
    # For early predictions, use adaptive window sizing
    elapsed_minutes = (times[-1] - times[0]).total_seconds() / 60
    
    if elapsed_minutes < 10:
        # Very early - use all available data
        rate = calculate_rate(times, temps, elapsed_minutes)
    else:
        # Try different window sizes
        rate_5min = calculate_rate(times, temps, 5)
        rate_10min = calculate_rate(times, temps, 10)
        rate_15min = calculate_rate(times, temps, 15)
        
        # For early predictions, weight longer windows more
        if elapsed_minutes < 20:
            rate = 0.2 * rate_5min + 0.3 * rate_10min + 0.5 * rate_15min
        else:
            # Normal weighting for later predictions
            rate = 0.5 * rate_5min + 0.3 * rate_10min + 0.2 * rate_15min
    
    # Handle stalls - if rate is too low, check longer history
    if rate < 0.5:  # Less than 0.5°F/min
        rate_30min = calculate_rate(times, temps, min(30, elapsed_minutes))
        if rate_30min > rate:
            rate = rate_30min
    
    if rate <= 0.1:  # Effectively no rise
        return None, "Temperature stalled"
    
    # For early predictions, apply a conservative factor
    if elapsed_minutes < 20:
        # Assume rate will improve as grill heats up
        rate = rate * 1.2
    
    minutes = (target_temp - current_temp) / rate
    
    # Apply bounds based on elapsed time
    if elapsed_minutes < 15:
        # Early predictions need wider bounds
        minutes = max(20, min(180, minutes))
    else:
        minutes = max(5, min(300, minutes))
    
    return round(minutes), f"Linear (rate: {rate:.1f}F/min)"

def extract_features(times, temps, targets, grill_temps):
    """Extract features for XGBoost with better engineering."""
    if len(temps) < 2:
        return None
    
    features = []
    start_time = times[0]
    
    for i in range(1, len(temps)):
        # Basic features
        minutes_elapsed = (times[i] - start_time).total_seconds() / 60
        probe_temp = temps[i]
        temp_to_target = targets[i] - probe_temp
        grill_temp = grill_temps[i]
        
        # Rate features
        rate_1 = temps[i] - temps[i-1] if i > 0 else 0
        rate_5 = calculate_rate(times[:i+1], temps[:i+1], 5)
        rate_10 = calculate_rate(times[:i+1], temps[:i+1], 10)
        
        # Stall detection
        recent_5 = temps[max(0, i-5):i+1]
        temp_variance = np.var(recent_5) if len(recent_5) > 1 else 0
        
        # Grill relationship
        grill_to_probe = grill_temp - probe_temp
        
        # Progress features
        start_temp = temps[0]
        progress_ratio = (probe_temp - start_temp) / (targets[i] - start_temp) if targets[i] > start_temp else 0
        
        features.append([
            probe_temp,
            minutes_elapsed,
            temp_to_target,
            grill_temp,
            grill_to_probe,
            rate_1,
            rate_5,
            rate_10,
            temp_variance,
            progress_ratio
        ])
    
    return features

def train_xgboost_improved(times, temps, targets, grill_temps):
    """Train XGBoost with better features."""
    if not XGBOOST_AVAILABLE or len(temps) < 20:
        return None
    
    features = extract_features(times, temps, targets, grill_temps)
    if not features:
        return None
    
    # Build training data
    X, y = [], []
    
    for i in range(len(features) - 1):
        # Find actual time to target
        for j in range(i + 1, len(temps)):
            if temps[j] >= targets[i]:
                time_to_target = (times[j] - times[i]).total_seconds() / 60
                if 0 < time_to_target < 180:
                    X.append(features[i])
                    y.append(time_to_target)
                break
    
    if len(X) < 10:
        return None
    
    # Train with better parameters
    model = xgb.XGBRegressor(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        gamma=0.1,
        random_state=42
    )
    
    model.fit(np.array(X), np.array(y))
    return model

def xgboost_prediction_improved(model, times, temps, targets, grill_temps):
    """Make prediction using improved XGBoost model."""
    if not model or not times:
        return None, "No model available"
    
    features = extract_features(times, temps, targets, grill_temps)
    if not features:
        return None, "Cannot extract features"
    
    # Use last feature set
    X_pred = np.array([features[-1]])
    minutes_to_target = model.predict(X_pred)[0]
    
    # Apply bounds and sanity checks
    current_temp = temps[-1]
    target_temp = targets[-1]
    
    # Minimum time based on temperature difference and max reasonable rate
    min_time = (target_temp - current_temp) / 3.0  # Max 3°F/min
    minutes_to_target = max(min_time, minutes_to_target)
    
    return round(max(5, min(180, minutes_to_target))), "XGBoost"

def predict_improved(cook_id: str, probe_channel: str):
    """Improved prediction function with better accuracy."""
    times, temps, targets, grill_temps = get_cook_data(cook_id, probe_channel)
    
    if not times:
        return {'error': 'No data for this cook/probe', 'cook_id': cook_id, 'probe_channel': probe_channel}
    
    current_temp = temps[-1]
    target_temp = targets[-1]
    
    # Skip if target is 0 or already reached
    if target_temp <= 0:
        return {'error': 'No target temperature set', 'current_temp': current_temp}
    
    if current_temp >= target_temp:
        return {'minutes_to_target': 0, 'message': 'Target reached', 'method': 'complete',
                'current_temp': current_temp, 'target_temp': target_temp}
    
    # Try XGBoost if we have enough data
    cache_key = (cook_id, probe_channel)
    if len(temps) >= 20:
        if cache_key not in MODEL_CACHE or len(temps) % 10 == 0:
            logger.info(f"Training model for {cook_id}/{probe_channel}")
            MODEL_CACHE[cache_key] = train_xgboost_improved(times, temps, targets, grill_temps)
        
        if cache_key in MODEL_CACHE:
            minutes, message = xgboost_prediction_improved(MODEL_CACHE[cache_key], times, temps, targets, grill_temps)
            if minutes is not None:
                return {'minutes_to_target': minutes, 'message': message, 'method': 'xgboost',
                        'current_temp': current_temp, 'target_temp': target_temp, 'data_points': len(temps)}
    
    # Fall back to improved linear
    minutes, message = linear_prediction_improved(times, temps, current_temp, target_temp)
    return {'minutes_to_target': minutes, 'message': message, 'method': 'linear',
            'current_temp': current_temp, 'target_temp': target_temp, 'data_points': len(temps)}

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python predict_improved.py <cook_id> <probe_channel>")
        sys.exit(1)
    
    result = predict_improved(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2))