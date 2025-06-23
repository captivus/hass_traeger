import sqlite3
import json
from datetime import datetime

# Create comprehensive cook summary
conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = conn.cursor()

cook_id = "E8EB1B4C15021750610370"

print("=== JUNE 22 COOK COMPREHENSIVE SUMMARY ===")
print(f"Cook ID: {cook_id}")

# Get timing info
cursor.execute("""
    SELECT MIN(timestamp), MAX(timestamp), COUNT(*)
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = ?
""", (cook_id,))
start_time, end_time, msg_count = cursor.fetchone()

start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
duration = end_dt - start_dt

print(f"\nTIMING:")
print(f"  Started: {start_time} ({start_dt.strftime('%I:%M %p')} UTC)")
print(f"  Ended: {end_time} ({end_dt.strftime('%I:%M %p')} UTC)")
print(f"  Duration: {duration}")
print(f"  Total messages: {msg_count}")

# Grill temperature analysis
cursor.execute("""
    SELECT 
        MIN(json_extract(payload, '$.status.grill')) as min_temp,
        MAX(json_extract(payload, '$.status.grill')) as max_temp,
        AVG(json_extract(payload, '$.status.grill')) as avg_temp
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = ?
    AND json_extract(payload, '$.status.grill') IS NOT NULL
""", (cook_id,))
grill_min, grill_max, grill_avg = cursor.fetchone()

print(f"\nGRILL TEMPERATURE:")
print(f"  Range: {grill_min}°F - {grill_max}°F")
print(f"  Average: {grill_avg:.1f}°F")

# Set temperature changes
cursor.execute("""
    SELECT DISTINCT json_extract(payload, '$.status.set') as set_temp
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = ?
    AND json_extract(payload, '$.status.set') IS NOT NULL
    ORDER BY set_temp
""", (cook_id,))
set_temps = [row[0] for row in cursor.fetchall()]
print(f"  Set points used: {', '.join(map(str, set_temps))}°F")

# PROBE DATA ANALYSIS
print(f"\nPROBE DATA:")

# Legacy probe (appears to mirror p0)
cursor.execute("""
    SELECT 
        COUNT(CASE WHEN json_extract(payload, '$.status.probe_con') = 1 THEN 1 END) as connected,
        MIN(json_extract(payload, '$.status.probe')) as min_temp,
        MAX(json_extract(payload, '$.status.probe')) as max_temp
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = ?
    AND json_extract(payload, '$.status.probe') > 0
""", (cook_id,))
legacy_con, legacy_min, legacy_max = cursor.fetchone()
print(f"\n  Legacy Probe:")
print(f"    Connected messages: {legacy_con}")
print(f"    Temperature range: {legacy_min}°F - {legacy_max}°F")

# Modern probes - detailed analysis
cursor.execute("""
    SELECT timestamp, json_extract(payload, '$.status.acc') as acc_data
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = ?
    AND json_extract(payload, '$.status.acc') IS NOT NULL
    ORDER BY timestamp ASC
""", (cook_id,))

probe_data = {'p0': {'temps': [], 'targets': set()}, 'p1': {'temps': [], 'targets': set()}}

for ts, acc_json in cursor.fetchall():
    if not acc_json:
        continue
    acc_list = json.loads(acc_json)
    for acc in acc_list:
        if acc.get('con') == 1 and acc.get('type') == 'probe' and acc.get('probe'):
            channel = acc.get('channel')
            if channel in probe_data:
                probe = acc['probe']
                temp = probe.get('get_temp')
                target = probe.get('set_temp')
                if temp is not None:
                    probe_data[channel]['temps'].append(temp)
                if target is not None:
                    probe_data[channel]['targets'].add(target)

print(f"\n  Probe p0 (Channel 0):")
if probe_data['p0']['temps']:
    print(f"    Messages with temperature: {len(probe_data['p0']['temps'])}")
    print(f"    Temperature range: {min(probe_data['p0']['temps'])}°F - {max(probe_data['p0']['temps'])}°F")
    print(f"    Target temperatures: {', '.join(map(str, sorted(probe_data['p0']['targets'])))}°F")
    print(f"    Note: This probe's data mirrors the legacy probe")

print(f"\n  Probe p1 (Channel 1):")
if probe_data['p1']['temps']:
    print(f"    Messages with temperature: {len(probe_data['p1']['temps'])}")
    print(f"    Temperature range: {min(probe_data['p1']['temps'])}°F - {max(probe_data['p1']['temps'])}°F")
    print(f"    Target temperatures: {', '.join(map(str, sorted(probe_data['p1']['targets'])))}°F")

# Check when probes stopped reporting
cursor.execute("""
    SELECT 
        MAX(CASE WHEN json_extract(payload, '$.status.probe_con') = 1 THEN timestamp END) as legacy_last,
        MAX(timestamp) as cook_last
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = ?
""", (cook_id,))
legacy_last, cook_last = cursor.fetchone()

print(f"\nPROBE CONNECTIVITY:")
print(f"  Legacy probe last seen: {legacy_last}")
print(f"  Cook ended: {cook_last}")

# Check for probe disconnection
cursor.execute("""
    SELECT timestamp
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = ?
    AND json_extract(payload, '$.status.acc') IS NOT NULL
    ORDER BY timestamp DESC
    LIMIT 1
""", (cook_id,))
last_acc_time = cursor.fetchone()[0]
print(f"  Modern probes last seen: {last_acc_time}")

print("\nNOTE: Both probes were connected throughout most of the cook.")
print("The legacy probe and p0 show identical data (likely the same physical probe).")
print("Probe p1 ran slightly hotter throughout the cook.")

conn.close()