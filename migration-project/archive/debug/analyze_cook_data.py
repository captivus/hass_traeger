import sqlite3
import json
from datetime import datetime
import pytz

# Connect to database
conn = sqlite3.connect('data/traeger.db')
cursor = conn.cursor()

# Set up timezone
central_tz = pytz.timezone('US/Central')
utc_tz = pytz.UTC

# Get date range for June 22, 2025 in Central time
start_central = central_tz.localize(datetime(2025, 6, 22, 0, 0, 0))
end_central = central_tz.localize(datetime(2025, 6, 22, 23, 59, 59))

# Convert to UTC for database query
start_utc = start_central.astimezone(utc_tz).isoformat()
end_utc = end_central.astimezone(utc_tz).isoformat()

# Query all records for today
query = '''
SELECT timestamp, payload 
FROM raw_messages 
WHERE timestamp >= ? AND timestamp <= ?
ORDER BY timestamp
'''

cursor.execute(query, (start_utc, end_utc))
records = cursor.fetchall()

# Analyze each cook
cook_data = {}
for timestamp, payload_str in records:
    payload = json.loads(payload_str)
    status = payload.get('status', {})
    cook_id = status.get('cook_id')
    
    if cook_id:
        if cook_id not in cook_data:
            cook_data[cook_id] = {
                'start_time': timestamp,
                'end_time': timestamp,
                'grill_temps': [],
                'grill_set_temps': [],
                'probe_data': {},
                'record_count': 0
            }
        
        cook = cook_data[cook_id]
        cook['end_time'] = timestamp
        cook['record_count'] += 1
        
        # Grill temps
        if 'grill' in status:
            cook['grill_temps'].append(status['grill'])
        if 'set' in status:
            cook['grill_set_temps'].append(status['set'])
            
        # Legacy probe
        if status.get('probe_con') == 1 and status.get('probe'):
            if 'legacy' not in cook['probe_data']:
                cook['probe_data']['legacy'] = {
                    'temps': [],
                    'targets': []
                }
            cook['probe_data']['legacy']['temps'].append(status['probe'])
            if 'probe_set' in status:
                cook['probe_data']['legacy']['targets'].append(status['probe_set'])
        
        # Modern probes
        for acc in status.get('acc', []):
            if acc.get('con') != 1:
                continue
            channel = acc.get('channel')
            
            if acc['type'] == 'probe':
                probe = acc.get('probe', {})
                if channel not in cook['probe_data']:
                    cook['probe_data'][channel] = {
                        'temps': [],
                        'targets': [],
                        'type': 'wired'
                    }
                if 'get_temp' in probe:
                    cook['probe_data'][channel]['temps'].append(probe['get_temp'])
                if 'set_temp' in probe:
                    cook['probe_data'][channel]['targets'].append(probe['set_temp'])
                    
            elif acc['type'] == 'btprobe':
                probe = acc.get('btprobe', {})
                if channel not in cook['probe_data']:
                    cook['probe_data'][channel] = {
                        'temps': [],
                        'targets': [],
                        'type': 'bluetooth',
                        'battery': []
                    }
                if 'get_temp' in probe:
                    cook['probe_data'][channel]['temps'].append(probe['get_temp'])
                if 'set_temp' in probe:
                    cook['probe_data'][channel]['targets'].append(probe['set_temp'])
                if 'batt' in probe:
                    cook['probe_data'][channel]['battery'].append(probe['batt'])

# Print analysis
for cook_id, data in cook_data.items():
    print(f'\n=== Cook: {cook_id} ===')
    
    # Convert times to Central
    start_dt = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
    start_central = start_dt.astimezone(central_tz)
    end_central = end_dt.astimezone(central_tz)
    duration = end_dt - start_dt
    
    print(f'Start: {start_central.strftime("%Y-%m-%d %H:%M:%S %Z")}')
    print(f'End: {end_central.strftime("%Y-%m-%d %H:%M:%S %Z")}')
    print(f'Duration: {duration}')
    print(f'Total records: {data["record_count"]}')
    
    # Grill temps
    if data['grill_temps']:
        print(f'\nGrill Temperature:')
        print(f'  Range: {min(data["grill_temps"])}°F - {max(data["grill_temps"])}°F')
        if data['grill_set_temps']:
            print(f'  Set points: {list(set(data["grill_set_temps"]))}')
    
    # Probe data
    if data['probe_data']:
        print(f'\nProbes:')
        for channel, probe_info in data['probe_data'].items():
            print(f'  {channel}:')
            if probe_info['temps']:
                print(f'    Temperature range: {min(probe_info["temps"])}°F - {max(probe_info["temps"])}°F')
                print(f'    Final temp: {probe_info["temps"][-1]}°F')
            if probe_info['targets']:
                print(f'    Target temps: {list(set(probe_info["targets"]))}')
            if probe_info.get('type'):
                print(f'    Type: {probe_info["type"]}')
            if probe_info.get('battery'):
                print(f'    Battery levels: {min(probe_info["battery"])}% - {max(probe_info["battery"])}%')

conn.close()