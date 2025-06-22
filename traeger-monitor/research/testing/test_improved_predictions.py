#!/usr/bin/env python3
"""Test improved predictions on historical data."""
import predict_improved as predict
from pathlib import Path

# Use historical database
predict.DB_PATH = Path("../traeger-stream/data/traeger_data.db")

# Override cutoff for historical data
def get_cook_data_historical(cook_id: str, probe_channel: str):
    cutoff = "2025-01-01"  # Before all historical data
    
    with predict.sqlite3.connect(predict.DB_PATH) as conn:
        rows = conn.execute("""
            SELECT timestamp, payload FROM raw_messages 
            WHERE timestamp > ? ORDER BY timestamp""", (cutoff,))
        
        times, temps, targets, grill_temps = [], [], [], []
        for timestamp, payload in rows:
            status = predict.json.loads(payload).get('status', {})
            if status.get('cook_id') != cook_id: continue
            
            t = predict.datetime.fromisoformat(timestamp)
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
    
    predict.DATA_CACHE[(cook_id, probe_channel)] = (times, temps, targets, grill_temps)
    return times, temps, targets, grill_temps

predict.get_cook_data = get_cook_data_historical

# Test predictions
test_cases = [
    ("E8EB1B4C15021748715282", "p0"),
    ("E8EB1B4C15021748715282", "p1"),
    ("E8EB1B4C15021749139580", "p0"),
    ("E8EB1B4C15021748620109", "p0"),
]

print("Testing improved predictions:")
print("=" * 60)

for cook_id, channel in test_cases:
    print(f"\nCook: {cook_id}, Channel: {channel}")
    result = predict.predict_improved(cook_id, channel)
    print(predict.json.dumps(result, indent=2))