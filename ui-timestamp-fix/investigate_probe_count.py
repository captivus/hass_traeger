import sqlite3
import json

# Investigate why 3 probes are showing instead of 2
conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = conn.cursor()

cook_id = "E8EB1B4C15021750610370"

print("=== INVESTIGATING PROBE COUNT DISCREPANCY ===\n")

# Get a sample of messages and examine the probe structure
cursor.execute("""
    SELECT timestamp, payload
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = ?
    ORDER BY timestamp ASC
    LIMIT 10
""", (cook_id,))

print("Sample probe configurations throughout cook:")
for i, (ts, payload) in enumerate(cursor.fetchall(), 1):
    data = json.loads(payload)
    status = data.get('status', {})
    
    print(f"\nMessage {i} at {ts}:")
    
    # Check legacy probe
    legacy_probe = status.get('probe')
    legacy_con = status.get('probe_con')
    print(f"  Legacy probe: temp={legacy_probe}, connected={legacy_con}")
    
    # Check acc array
    acc = status.get('acc', [])
    print(f"  Accessories: {len(acc)} total")
    
    probe_count = 0
    for j, accessory in enumerate(acc):
        acc_type = accessory.get('type')
        channel = accessory.get('channel')
        connected = accessory.get('con')
        
        if acc_type in ['probe', 'btprobe']:
            probe_count += 1
            if acc_type == 'probe' and accessory.get('probe'):
                temp = accessory['probe'].get('get_temp')
                target = accessory['probe'].get('set_temp')
                print(f"    [{j}] {acc_type} {channel}: temp={temp}°F, target={target}°F, connected={connected}")
            elif acc_type == 'btprobe' and accessory.get('btprobe'):
                temp = accessory['btprobe'].get('get_temp')
                target = accessory['btprobe'].get('set_temp')
                battery = accessory['btprobe'].get('batt')
                print(f"    [{j}] {acc_type} {channel}: temp={temp}°F, target={target}°F, battery={battery}%, connected={connected}")
        else:
            print(f"    [{j}] {acc_type} {channel}: connected={connected}")
    
    print(f"  Total probe-type accessories: {probe_count}")

# Now check what channels actually have data throughout the cook
print(f"\n=== PROBE CHANNEL ANALYSIS ===")

cursor.execute("""
    SELECT timestamp, json_extract(payload, '$.status.acc') as acc_data
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = ?
    AND json_extract(payload, '$.status.acc') IS NOT NULL
    ORDER BY timestamp ASC
""", (cook_id,))

channel_data = {}
for ts, acc_json in cursor.fetchall():
    if not acc_json:
        continue
    acc_list = json.loads(acc_json)
    for acc in acc_list:
        if acc.get('con') == 1 and acc.get('type') in ['probe', 'btprobe']:
            channel = acc.get('channel', 'unknown')
            acc_type = acc.get('type')
            
            if channel not in channel_data:
                channel_data[channel] = {
                    'type': acc_type,
                    'count': 0,
                    'temps': [],
                    'first_seen': ts
                }
            
            channel_data[channel]['count'] += 1
            channel_data[channel]['last_seen'] = ts
            
            # Get temperature
            if acc_type == 'probe' and acc.get('probe'):
                temp = acc['probe'].get('get_temp')
            elif acc_type == 'btprobe' and acc.get('btprobe'):
                temp = acc['btprobe'].get('get_temp')
            else:
                temp = None
                
            if temp is not None:
                channel_data[channel]['temps'].append(temp)

print(f"\nActive probe channels found: {len(channel_data)}")
for channel, data in sorted(channel_data.items()):
    print(f"\nChannel '{channel}' ({data['type']}):")
    print(f"  Messages: {data['count']}")
    print(f"  Duration: {data['first_seen']} to {data.get('last_seen', 'unknown')}")
    if data['temps']:
        print(f"  Temperature range: {min(data['temps'])}°F - {max(data['temps'])}°F")
        print(f"  Sample temps: {data['temps'][:5]}...")

# Check how the web UI extract_probes function would interpret this
print(f"\n=== WEB UI INTERPRETATION ===")

# Simulate the extract_probes function from server.py
cursor.execute("""
    SELECT payload
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = ?
    ORDER BY timestamp ASC
    LIMIT 5
""", (cook_id,))

for i, (payload,) in enumerate(cursor.fetchall(), 1):
    data = json.loads(payload)
    status = data.get('status', {})
    
    # Simulate extract_probes function
    probes = []
    
    # Check legacy format
    if status.get('probe_con') == 1 and status.get('probe'):
        probes.append({
            'channel': 'legacy', 
            'temp': status['probe'], 
            'target': status.get('probe_set')
        })
    
    # Check acc array for modern probes
    for acc in status.get('acc', []):
        if acc.get('con') != 1: 
            continue
        if acc['type'] == 'probe':
            p = acc.get('probe', {})
            probes.append({
                'channel': acc['channel'], 
                'temp': p.get('get_temp'), 
                'target': p.get('set_temp')
            })
        elif acc['type'] == 'btprobe':
            p = acc.get('btprobe', {})
            probes.append({
                'channel': acc['channel'], 
                'temp': p.get('get_temp'), 
                'target': p.get('set_temp'), 
                'battery': p.get('batt')
            })
    
    print(f"\nMessage {i} would return {len(probes)} probes to UI:")
    for probe in probes:
        print(f"  {probe}")

conn.close()