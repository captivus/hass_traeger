#!/usr/bin/env python3
"""Validate prediction accuracy on historical cook data."""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt

# Import and configure predict module
import predict
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
                    'target': target
                })
    
    if len(all_data) < 20:
        print(f"Insufficient data for {cook_id}/{probe_channel}: {len(all_data)} points")
        return None
    
    # Simulate predictions at various points
    predictions = []
    
    # Test at 10%, 25%, 50%, 75% through the cook
    test_points = [int(len(all_data) * p) for p in [0.1, 0.25, 0.5, 0.75]]
    
    for i in test_points:
        # Temporarily limit data to simulate real-time
        predict.get_cook_data = lambda cid, ch: (
            [d['time'] for d in all_data[:i]],
            [d['temp'] for d in all_data[:i]], 
            [d['target'] for d in all_data[:i]]
        )
        
        result = predict.predict(cook_id, probe_channel)
        
        # Find actual time to target
        actual_minutes = None
        if result.get('current_temp', 0) < result.get('target_temp', 0):
            for j in range(i, len(all_data)):
                if all_data[j]['temp'] >= all_data[i]['target']:
                    actual_minutes = (all_data[j]['time'] - all_data[i]['time']).total_seconds() / 60
                    break
        
        predictions.append({
            'point': i,
            'data_points': i,
            'current_temp': all_data[i]['temp'],
            'target_temp': all_data[i]['target'],
            'predicted_minutes': result.get('minutes_to_target'),
            'actual_minutes': actual_minutes,
            'method': result.get('method'),
            'elapsed_minutes': (all_data[i]['time'] - all_data[0]['time']).total_seconds() / 60
        })
    
    return predictions

# Test all useful cook sessions
cook_sessions = [
    ("E8EB1B4C15021750610370", ["p0", "p1", "legacy"]),
    ("E8EB1B4C15021749139580", ["p0", "legacy"]),
    ("E8EB1B4C15021748715282", ["p0", "p1", "BT0", "BT1", "legacy"]),
    ("E8EB1B4C15021748620109", ["p0", "legacy"]),
    ("E8EB1B4C15021748231230", ["legacy", "BT0", "BT1"])
]

print("Validating predictions on historical cook data")
print("=" * 80)

all_predictions = []

for cook_id, channels in cook_sessions:
    print(f"\nCook: {cook_id}")
    
    for channel in channels:
        predictions = simulate_cook_predictions(cook_id, channel)
        if predictions:
            print(f"\n  Channel {channel}:")
            
            for p in predictions:
                if p['predicted_minutes'] is not None and p['actual_minutes'] is not None:
                    error = abs(p['predicted_minutes'] - p['actual_minutes'])
                    pct = p['elapsed_minutes'] / (p['elapsed_minutes'] + p['actual_minutes']) * 100
                    
                    print(f"    At {pct:.0f}% done: Predicted {p['predicted_minutes']:.0f} min, "
                          f"Actual {p['actual_minutes']:.0f} min, Error {error:.0f} min ({p['method']})")
                    
                    all_predictions.append({
                        'cook_id': cook_id,
                        'channel': channel,
                        'percent_complete': pct,
                        'predicted': p['predicted_minutes'],
                        'actual': p['actual_minutes'],
                        'error': error,
                        'method': p['method']
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
        print(f"\nLinear predictions: {len(linear_errors)}, MAE: {sum(linear_errors)/len(linear_errors):.1f} min")
    if xgboost_errors:
        print(f"XGBoost predictions: {len(xgboost_errors)}, MAE: {sum(xgboost_errors)/len(xgboost_errors):.1f} min")
    
    # Create scatter plot
    plt.figure(figsize=(10, 6))
    for p in all_predictions:
        color = 'blue' if p['method'] == 'linear' else 'red'
        plt.scatter(p['actual'], p['predicted'], alpha=0.5, color=color)
    
    # Perfect prediction line
    max_val = max(max(p['actual'], p['predicted']) for p in all_predictions)
    plt.plot([0, max_val], [0, max_val], 'k--', label='Perfect prediction')
    
    plt.xlabel('Actual Time to Target (minutes)')
    plt.ylabel('Predicted Time to Target (minutes)')
    plt.title('Prediction Accuracy on Historical Cook Data')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig('prediction_validation.png')
    print("\nValidation plot saved to prediction_validation.png")