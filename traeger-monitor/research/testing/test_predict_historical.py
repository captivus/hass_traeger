#!/usr/bin/env python3
"""Test predict.py with historical cook data."""
import sys
import json
from pathlib import Path

# Update DB path to use historical data
import predict
predict.DB_PATH = Path("../traeger-stream/data/traeger_data.db")

# Override the cutoff time for historical data
original_get_cook_data = predict.get_cook_data

def get_cook_data_historical(cook_id: str, probe_channel: str):
    """Get temperature data for a cook/probe from historical data."""
    # Use a much older cutoff for historical data
    cutoff = "2025-01-01"  # Before all our historical data
    
    with predict.sqlite3.connect(predict.DB_PATH) as conn:
        rows = conn.execute("""
            SELECT timestamp, payload FROM raw_messages 
            WHERE timestamp > ? ORDER BY timestamp""", (cutoff,))
        
        times, temps, targets = [], [], []
        for timestamp, payload in rows:
            status = predict.json.loads(payload).get('status', {})
            if status.get('cook_id') != cook_id: continue
            
            t = predict.datetime.fromisoformat(timestamp)
            
            # Check legacy probe format
            if probe_channel == 'legacy' and status.get('probe_con') == 1:
                temp = status.get('probe')
                target = status.get('probe_set')
                if temp is not None and target is not None:
                    times.append(t)
                    temps.append(temp)
                    targets.append(target)
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
                    
                    if temp is not None and target is not None:
                        times.append(t)
                        temps.append(temp)
                        targets.append(target)
    
    predict.DATA_CACHE[(cook_id, probe_channel)] = (times, temps, targets)
    return times, temps, targets

predict.get_cook_data = get_cook_data_historical

# Test with the comprehensive cook session that has all probe types
cook_id = "E8EB1B4C15021748715282"
probe_channels = ["p0", "p1", "BT0", "BT1", "legacy"]

print(f"Testing predictions for cook: {cook_id}")
print("=" * 60)

for channel in probe_channels:
    print(f"\nTesting probe channel: {channel}")
    result = predict.predict(cook_id, channel)
    print(json.dumps(result, indent=2))
    
# Also test with a shorter cook
print("\n\nTesting shorter cook session")
print("=" * 60)
cook_id2 = "E8EB1B4C15021749139580"
result = predict.predict(cook_id2, "p0")
print(f"\nCook {cook_id2}, probe p0:")
print(json.dumps(result, indent=2))