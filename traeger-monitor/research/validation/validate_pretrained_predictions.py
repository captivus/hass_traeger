#!/usr/bin/env python3
"""Validate pre-trained model predictions against historical data."""
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
import logging
import numpy as np
import pickle

try:
    import xgboost as xgb
except ImportError:
    print("Error: xgboost not installed. Run: pip install xgboost")
    exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
HISTORICAL_DB = Path(__file__).parent.parent / "traeger-stream" / "data" / "traeger_data.db"
MODEL_DIR = Path(__file__).parent / "models"

# Load models directly
PRETRAINED_MODELS = {}
for probe_type in ['wired', 'bluetooth', 'legacy']:
    model_path = MODEL_DIR / f"{probe_type}_model.pkl"
    if model_path.exists():
        with open(model_path, 'rb') as f:
            PRETRAINED_MODELS[probe_type] = pickle.load(f)
            logger.info(f"Loaded {probe_type} model")

def get_probe_type(probe_channel: str) -> str:
    """Determine probe type from channel name."""
    if probe_channel == 'legacy':
        return 'legacy'
    elif probe_channel.startswith('BT'):
        return 'bluetooth' 
    else:
        return 'wired'

def get_historical_cook_data(cook_id: str, probe_channel: str):
    """Get cook data from historical database."""
    with sqlite3.connect(HISTORICAL_DB) as conn:
        rows = conn.execute("""
            SELECT timestamp, payload FROM raw_messages 
            WHERE payload LIKE ? ORDER BY timestamp
        """, (f'%"cook_id":"{cook_id}"%',))
        
        times, temps, targets, grill_temps = [], [], [], []
        for timestamp, payload in rows:
            try:
                status = json.loads(payload).get('status', {})
                if status.get('cook_id') != cook_id: continue
                
                t = datetime.fromisoformat(timestamp.replace(' ', 'T'))
                grill_temp = status.get('grill', 0)
                
                # Check legacy probe format
                if probe_channel == 'legacy' and status.get('probe_con') == 1:
                    temp = status.get('probe')
                    target = status.get('probe_set')
                    if temp and target and target > 0:
                        times.append(t)
                        temps.append(temp)
                        targets.append(target)
                        grill_temps.append(grill_temp)
                    continue
                
                # Check acc array probes
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
                        
                        if temp and target and target > 0:
                            times.append(t)
                            temps.append(temp)
                            targets.append(target) 
                            grill_temps.append(grill_temp)
            except json.JSONDecodeError:
                continue
    
    return times, temps, targets, grill_temps

def calculate_rate(times, temps, window_minutes=10):
    """Calculate temperature rate."""
    if len(temps) < 2:
        return 0.0
    
    recent_time = times[-1] - timedelta(minutes=window_minutes)
    recent_indices = [i for i, t in enumerate(times) if t > recent_time]
    
    if len(recent_indices) < 2:
        recent_indices = list(range(max(0, len(times)-5), len(times)))
    
    if len(recent_indices) < 2:
        return 0.0
    
    # Linear regression
    x = [(times[i] - times[recent_indices[0]]).total_seconds() / 60 for i in recent_indices]
    y = [temps[i] for i in recent_indices]
    
    if max(x) - min(x) == 0:
        return 0.0
    
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

def extract_features_single(times, temps, targets, grill_temps, idx):
    """Extract features for a single prediction point."""
    if idx < 1 or idx >= len(temps):
        return None
    
    start_time = times[0]
    
    # Basic features
    minutes_elapsed = (times[idx] - start_time).total_seconds() / 60
    probe_temp = temps[idx]
    temp_to_target = targets[idx] - probe_temp
    grill_temp = grill_temps[idx]
    
    # Rate features
    rate_1 = temps[idx] - temps[idx-1] if idx > 0 else 0
    rate_5 = calculate_rate(times[:idx+1], temps[:idx+1], 5)
    rate_10 = calculate_rate(times[:idx+1], temps[:idx+1], 10)
    
    # Stall detection
    recent_5 = temps[max(0, idx-4):idx+1]
    temp_variance = np.var(recent_5) if len(recent_5) > 1 else 0
    
    # Grill relationship
    grill_to_probe = grill_temp - probe_temp
    
    # Progress
    start_temp = temps[0]
    progress_ratio = (probe_temp - start_temp) / (targets[idx] - start_temp) if targets[idx] > start_temp else 0
    
    return [
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
    ]

def validate_cook(cook_id, probe_channel):
    """Validate predictions for a single cook/probe."""
    times, temps, targets, grill_temps = get_historical_cook_data(cook_id, probe_channel)
    
    if len(times) < 20:
        return None
    
    probe_type = get_probe_type(probe_channel)
    if probe_type not in PRETRAINED_MODELS:
        return None
    
    model = PRETRAINED_MODELS[probe_type]
    
    predictions = []
    actuals = []
    elapsed_times = []
    progress_pcts = []
    
    # Test at different points (5, 10, 15, 20+ data points)
    test_indices = [5, 10, 15, 20, 30, 40, 50]
    test_indices = [i for i in test_indices if i < len(temps)]
    
    for idx in test_indices:
        features = extract_features_single(times, temps, targets, grill_temps, idx)
        if features is None:
            continue
        
        # Find actual time to target
        actual_time = None
        for j in range(idx + 1, len(temps)):
            if temps[j] >= targets[idx]:
                actual_time = (times[j] - times[idx]).total_seconds() / 60
                break
        
        if actual_time is None or actual_time <= 0 or actual_time > 300:
            continue
        
        # Make prediction
        X_pred = np.array([features])
        predicted_time = model.predict(X_pred)[0]
        
        # Apply bounds
        current_temp = temps[idx]
        target_temp = targets[idx]
        min_time = (target_temp - current_temp) / 3.0  # Max 3°F/min
        predicted_time = max(min_time, predicted_time)
        predicted_time = max(5, min(180, predicted_time))
        
        predictions.append(predicted_time)
        actuals.append(actual_time)
        elapsed_times.append((times[idx] - times[0]).total_seconds() / 60)
        
        # Calculate progress percentage
        start_temp = temps[0]
        progress_pct = (current_temp - start_temp) / (target_temp - start_temp) * 100
        progress_pcts.append(progress_pct)
    
    if not predictions:
        return None
    
    return {
        'cook_id': cook_id,
        'probe_channel': probe_channel,
        'probe_type': probe_type,
        'predictions': predictions,
        'actuals': actuals,
        'elapsed_times': elapsed_times,
        'progress_pcts': progress_pcts,
        'mae': np.mean(np.abs(np.array(predictions) - np.array(actuals)))
    }

def main():
    """Validate pre-trained models on historical data."""
    test_cases = [
        ("E8EB1B4C15021748620109", "legacy"),
        ("E8EB1B4C15021748620109", "p0"),
        ("E8EB1B4C15021750610370", "p1"),
    ]
    
    all_predictions = []
    all_actuals = []
    
    print("\nValidating Pre-trained Model Predictions\n" + "="*50)
    
    for cook_id, probe_channel in test_cases:
        result = validate_cook(cook_id, probe_channel)
        
        if result is None:
            print(f"\n{cook_id} / {probe_channel}: No data or model")
            continue
        
        print(f"\n{cook_id} / {probe_channel} ({result['probe_type']} probe)")
        print(f"  MAE: {result['mae']:.1f} minutes")
        print(f"  Predictions at different stages:")
        
        for i, (elapsed, progress, pred, actual) in enumerate(zip(
            result['elapsed_times'], result['progress_pcts'], 
            result['predictions'], result['actuals'])):
            error = pred - actual
            print(f"    {elapsed:3.0f} min ({progress:3.0f}%): "
                  f"predicted {pred:3.0f} min, actual {actual:3.0f} min "
                  f"(error: {error:+3.0f} min)")
        
        all_predictions.extend(result['predictions'])
        all_actuals.extend(result['actuals'])
    
    if all_predictions:
        overall_mae = np.mean(np.abs(np.array(all_predictions) - np.array(all_actuals)))
        print(f"\n{'='*50}")
        print(f"Overall MAE: {overall_mae:.1f} minutes")
        print(f"Total predictions: {len(all_predictions)}")

if __name__ == "__main__":
    main()