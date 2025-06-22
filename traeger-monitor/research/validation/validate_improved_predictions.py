#!/usr/bin/env python3
"""Validate improved predictions throughout cook sessions."""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt

# Import improved predict module
import predict_improved as predict
predict.DB_PATH = Path("../traeger-stream/data/traeger_data.db")

def simulate_cook_predictions(cook_id: str, probe_channel: str):
    """Simulate predictions throughout a cook session."""
    
    # Get all data for this cook/probe
    with sqlite3.connect(predict.DB_PATH) as conn:
        rows = conn.execute("""
            SELECT timestamp, payload FROM raw_messages 
            WHERE json_extract(payload, '$.status.cook_id') = ?
            ORDER BY timestamp""", (cook_id,))
        
        # Collect all data points
        all_data = []
        for timestamp, payload in rows:
            status = json.loads(payload).get('status', {})
            t = datetime.fromisoformat(timestamp)
            grill_temp = status.get('grill', 0)
            
            # Extract probe temperature based on channel
            temp, target = None, None
            
            if probe_channel == 'legacy' and status.get('probe_con') == 1:
                temp = status.get('probe')
                target = status.get('probe_set')
            else:
                for acc in status.get('acc', []):
                    if acc.get('channel') == probe_channel and acc.get('con') == 1:
                        if acc['type'] == 'probe':
                            temp = acc.get('probe', {}).get('get_temp')
                            target = acc.get('probe', {}).get('set_temp')
                        elif acc['type'] == 'btprobe':
                            temp = acc.get('btprobe', {}).get('get_temp')
                            target = acc.get('btprobe', {}).get('set_temp')
                        break
            
            if temp is not None and target is not None and target > 0:
                all_data.append({
                    'time': t,
                    'temp': temp,
                    'target': target,
                    'grill_temp': grill_temp
                })
    
    if len(all_data) < 20:
        print(f"Insufficient data for {cook_id}/{probe_channel}: {len(all_data)} points")
        return None
    
    # Find when target was actually reached
    target_reached_idx = None
    for i, d in enumerate(all_data):
        if d['temp'] >= d['target']:
            target_reached_idx = i
            break
    
    if target_reached_idx is None or target_reached_idx < 20:
        print(f"Target not reached or reached too early for {cook_id}/{probe_channel}")
        return None
    
    # Simulate predictions at various points before target reached
    predictions = []
    test_points = []
    
    # Test at 10%, 25%, 50%, 75% of the way to target
    for pct in [0.1, 0.25, 0.5, 0.75]:
        idx = int(target_reached_idx * pct)
        if idx >= 5:  # Need some data to predict
            test_points.append(idx)
    
    for i in test_points:
        # Temporarily limit data to simulate real-time
        predict.get_cook_data = lambda cid, ch: (
            [d['time'] for d in all_data[:i]],
            [d['temp'] for d in all_data[:i]], 
            [d['target'] for d in all_data[:i]],
            [d['grill_temp'] for d in all_data[:i]]
        )
        
        result = predict.predict_improved(cook_id, probe_channel)
        
        # Calculate actual time to target
        actual_minutes = (all_data[target_reached_idx]['time'] - all_data[i]['time']).total_seconds() / 60
        
        predictions.append({
            'point': i,
            'data_points': i,
            'current_temp': all_data[i]['temp'],
            'target_temp': all_data[i]['target'],
            'predicted_minutes': result.get('minutes_to_target'),
            'actual_minutes': actual_minutes,
            'method': result.get('method'),
            'elapsed_minutes': (all_data[i]['time'] - all_data[0]['time']).total_seconds() / 60,
            'percent_complete': i / target_reached_idx * 100
        })
    
    return predictions

# Test all useful cook sessions
cook_sessions = [
    ("E8EB1B4C15021750610370", ["p0", "p1", "legacy"]),
    ("E8EB1B4C15021749139580", ["p0", "legacy"]),
    ("E8EB1B4C15021748715282", ["p0", "p1", "legacy"]),
    ("E8EB1B4C15021748620109", ["p0", "legacy"]),
]

print("Validating improved predictions on historical cook data")
print("=" * 80)

all_predictions = []
detailed_results = []

for cook_id, channels in cook_sessions:
    print(f"\nCook: {cook_id}")
    
    for channel in channels:
        predictions = simulate_cook_predictions(cook_id, channel)
        if predictions:
            print(f"\n  Channel {channel}:")
            
            for p in predictions:
                if p['predicted_minutes'] is not None:
                    error = abs(p['predicted_minutes'] - p['actual_minutes'])
                    
                    print(f"    At {p['percent_complete']:.0f}% complete: "
                          f"Predicted {p['predicted_minutes']:.0f} min, "
                          f"Actual {p['actual_minutes']:.0f} min, "
                          f"Error {error:.0f} min ({p['method']})")
                    
                    all_predictions.append({
                        'cook_id': cook_id,
                        'channel': channel,
                        'percent_complete': p['percent_complete'],
                        'predicted': p['predicted_minutes'],
                        'actual': p['actual_minutes'],
                        'error': error,
                        'method': p['method'],
                        'data_points': p['data_points']
                    })

# Calculate overall statistics
if all_predictions:
    print("\n\nOverall Statistics:")
    print("=" * 80)
    
    errors = [p['error'] for p in all_predictions]
    mae = sum(errors) / len(errors)
    
    print(f"Total predictions: {len(all_predictions)}")
    print(f"Mean Absolute Error: {mae:.1f} minutes")
    print(f"Max Error: {max(errors):.1f} minutes")
    print(f"Min Error: {min(errors):.1f} minutes")
    
    # By method
    linear_errors = [p['error'] for p in all_predictions if p['method'] == 'linear']
    xgboost_errors = [p['error'] for p in all_predictions if p['method'] == 'xgboost']
    
    if linear_errors:
        print(f"\nLinear predictions ({len(linear_errors)}): MAE = {sum(linear_errors)/len(linear_errors):.1f} min")
    if xgboost_errors:
        print(f"XGBoost predictions ({len(xgboost_errors)}): MAE = {sum(xgboost_errors)/len(xgboost_errors):.1f} min")
    
    # By completion percentage
    early_errors = [p['error'] for p in all_predictions if p['percent_complete'] <= 25]
    mid_errors = [p['error'] for p in all_predictions if 25 < p['percent_complete'] <= 50]
    late_errors = [p['error'] for p in all_predictions if p['percent_complete'] > 50]
    
    if early_errors:
        print(f"\nEarly (≤25%): MAE = {sum(early_errors)/len(early_errors):.1f} min")
    if mid_errors:
        print(f"Mid (25-50%): MAE = {sum(mid_errors)/len(mid_errors):.1f} min")
    if late_errors:
        print(f"Late (>50%): MAE = {sum(late_errors)/len(late_errors):.1f} min")
    
    # Create improved scatter plot
    plt.figure(figsize=(12, 8))
    
    # Separate by method
    linear_preds = [p for p in all_predictions if p['method'] == 'linear']
    xgboost_preds = [p for p in all_predictions if p['method'] == 'xgboost']
    
    if linear_preds:
        plt.scatter([p['actual'] for p in linear_preds], 
                   [p['predicted'] for p in linear_preds], 
                   alpha=0.5, color='blue', label='Linear', s=50)
    if xgboost_preds:
        plt.scatter([p['actual'] for p in xgboost_preds], 
                   [p['predicted'] for p in xgboost_preds], 
                   alpha=0.5, color='red', label='XGBoost', s=50)
    
    # Perfect prediction line
    max_val = max(max(p['actual'], p['predicted']) for p in all_predictions)
    plt.plot([0, max_val], [0, max_val], 'k--', label='Perfect prediction')
    
    # Add ±15 minute bounds
    plt.fill_between([0, max_val], [0, max_val-15], [0, max_val+15], 
                     alpha=0.2, color='green', label='±15 min target')
    
    plt.xlabel('Actual Time to Target (minutes)')
    plt.ylabel('Predicted Time to Target (minutes)')
    plt.title(f'Improved Prediction Accuracy (MAE: {mae:.1f} min)')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig('improved_prediction_validation.png')
    print("\nValidation plot saved to improved_prediction_validation.png")