import sqlite3
import json
from datetime import datetime

# Deep dive into probe data for today's cook
conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = conn.cursor()

cook_id = "E8EB1B4C15021750610370"

# Get a few sample messages to see the full payload structure
cursor.execute("""
    SELECT timestamp, payload
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = ?
    ORDER BY timestamp ASC
    LIMIT 5
""", (cook_id,))

print("=== SAMPLE PAYLOADS TO UNDERSTAND STRUCTURE ===")
for i, (ts, payload) in enumerate(cursor.fetchall()):
    data = json.loads(payload)
    status = data.get('status', {})
    print(f"\nMessage {i+1} at {ts}:")
    print(f"  Grill: {status.get('grill')}°F (set: {status.get('set')}°F)")
    print(f"  Legacy probe: {status.get('probe')}°F (connected: {status.get('probe_con')})")
    
    # Check for acc array (modern probe format)
    acc = status.get('acc', [])
    if acc:
        print(f"  Accessories ({len(acc)}):")
        for j, accessory in enumerate(acc):
            print(f"    [{j}] Type: {accessory.get('type')}, Channel: {accessory.get('channel')}, Connected: {accessory.get('con')}")
            if accessory.get('type') == 'probe' and accessory.get('probe'):
                p = accessory['probe']
                print(f"        Temp: {p.get('get_temp')}°F, Target: {p.get('set_temp')}°F")
            elif accessory.get('type') == 'btprobe' and accessory.get('btprobe'):
                p = accessory['btprobe']
                print(f"        Temp: {p.get('get_temp')}°F, Target: {p.get('set_temp')}°F, Battery: {p.get('batt')}%")

# Now analyze probe data throughout the cook
print("\n\n=== PROBE DATA ANALYSIS ===")

# Check legacy probe
cursor.execute("""
    SELECT 
        COUNT(*) as msg_count,
        MIN(json_extract(payload, '$.status.probe')) as min_temp,
        MAX(json_extract(payload, '$.status.probe')) as max_temp,
        COUNT(CASE WHEN json_extract(payload, '$.status.probe_con') = 1 THEN 1 END) as connected_count
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = ?
""", (cook_id,))

row = cursor.fetchone()
print(f"\nLegacy Probe:")
print(f"  Messages with data: {row[3]}/{row[0]} connected")
print(f"  Temperature range: {row[1]}°F - {row[2]}°F")

# Check for modern probes in acc array
cursor.execute("""
    SELECT timestamp, json_extract(payload, '$.status.acc') as acc_data
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = ?
    AND json_extract(payload, '$.status.acc') IS NOT NULL
    ORDER BY timestamp ASC
""", (cook_id,))

# Analyze accessory probes
probe_channels = {}
for ts, acc_json in cursor.fetchall():
    if not acc_json:
        continue
    acc_list = json.loads(acc_json)
    for acc in acc_list:
        if acc.get('con') == 1 and acc.get('type') in ['probe', 'btprobe']:
            channel = acc.get('channel', 'unknown')
            if channel not in probe_channels:
                probe_channels[channel] = {
                    'type': acc.get('type'),
                    'count': 0,
                    'temps': [],
                    'first_seen': ts,
                    'last_seen': ts
                }
            probe_channels[channel]['count'] += 1
            probe_channels[channel]['last_seen'] = ts
            
            # Get temperature
            if acc.get('type') == 'probe' and acc.get('probe'):
                temp = acc['probe'].get('get_temp')
            elif acc.get('type') == 'btprobe' and acc.get('btprobe'):
                temp = acc['btprobe'].get('get_temp')
            else:
                temp = None
                
            if temp is not None:
                probe_channels[channel]['temps'].append(temp)

print(f"\nModern Probes Found: {len(probe_channels)}")
for channel, data in sorted(probe_channels.items()):
    print(f"\nChannel {channel} ({data['type']}):")
    print(f"  Messages: {data['count']}")
    print(f"  First seen: {data['first_seen']}")
    print(f"  Last seen: {data['last_seen']}")
    if data['temps']:
        print(f"  Temperature range: {min(data['temps'])}°F - {max(data['temps'])}°F")

# Get a timeline view
print("\n\n=== PROBE TIMELINE ===")
cursor.execute("""
    SELECT 
        timestamp,
        json_extract(payload, '$.status.grill') as grill,
        json_extract(payload, '$.status.probe') as legacy_probe,
        json_extract(payload, '$.status.probe_con') as legacy_con,
        json_extract(payload, '$.status.acc') as acc_data
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = ?
    AND timestamp BETWEEN 
        (SELECT MIN(timestamp) FROM raw_messages WHERE json_extract(payload, '$.status.cook_id') = ?)
        AND
        (SELECT datetime(MIN(timestamp), '+10 minutes') FROM raw_messages WHERE json_extract(payload, '$.status.cook_id') = ?)
    ORDER BY timestamp ASC
""", (cook_id, cook_id, cook_id))

print("\nFirst 10 minutes of cook:")
for ts, grill, legacy_probe, legacy_con, acc_json in cursor.fetchall():
    probes_info = []
    
    # Legacy probe
    if legacy_con == 1 and legacy_probe:
        probes_info.append(f"Legacy:{legacy_probe}°F")
    
    # Modern probes
    if acc_json:
        acc_list = json.loads(acc_json)
        for acc in acc_list:
            if acc.get('con') == 1 and acc.get('type') in ['probe', 'btprobe']:
                channel = acc.get('channel', '?')
                if acc.get('type') == 'probe' and acc.get('probe'):
                    temp = acc['probe'].get('get_temp')
                elif acc.get('type') == 'btprobe' and acc.get('btprobe'):
                    temp = acc['btprobe'].get('get_temp')
                else:
                    temp = None
                if temp:
                    probes_info.append(f"Ch{channel}:{temp}°F")
    
    print(f"{ts}: Grill={grill}°F, Probes=[{', '.join(probes_info)}]")

conn.close()