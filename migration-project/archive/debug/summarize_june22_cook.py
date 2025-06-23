import sqlite3
import json
from datetime import datetime

# Summarize today's cook data
conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = conn.cursor()

# Get all messages for the real cook
cursor.execute("""
    SELECT timestamp, json_extract(payload, '$.status') as status
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = 'E8EB1B4C15021750610370'
    ORDER BY timestamp ASC
""")

messages = cursor.fetchall()
print(f"=== JUNE 22 COOK SUMMARY ===")
print(f"Cook ID: E8EB1B4C15021750610370")
print(f"Total messages: {len(messages)}")

if messages:
    # Parse first and last message
    first_ts, first_status = messages[0]
    last_ts, last_status = messages[-1]
    
    first_data = json.loads(first_status) if first_status else {}
    last_data = json.loads(last_status) if last_status else {}
    
    # Calculate duration
    start_time = datetime.fromisoformat(first_ts.replace('Z', '+00:00'))
    end_time = datetime.fromisoformat(last_ts.replace('Z', '+00:00'))
    duration = end_time - start_time
    
    print(f"\nTiming:")
    print(f"  Started: {first_ts} ({start_time.strftime('%I:%M %p')} UTC)")
    print(f"  Ended: {last_ts} ({end_time.strftime('%I:%M %p')} UTC)")
    print(f"  Duration: {duration}")
    
    # Get temperature data
    print(f"\nTemperature Range:")
    cursor.execute("""
        SELECT 
            MIN(json_extract(payload, '$.status.grill')) as min_temp,
            MAX(json_extract(payload, '$.status.grill')) as max_temp,
            AVG(json_extract(payload, '$.status.grill')) as avg_temp
        FROM raw_messages 
        WHERE json_extract(payload, '$.status.cook_id') = 'E8EB1B4C15021750610370'
        AND json_extract(payload, '$.status.grill') IS NOT NULL
    """)
    min_temp, max_temp, avg_temp = cursor.fetchone()
    print(f"  Grill: {min_temp}°F - {max_temp}°F (avg: {avg_temp:.1f}°F)")
    
    # Get probe data if available
    cursor.execute("""
        SELECT 
            MIN(json_extract(payload, '$.status.probe')) as min_probe,
            MAX(json_extract(payload, '$.status.probe')) as max_probe
        FROM raw_messages 
        WHERE json_extract(payload, '$.status.cook_id') = 'E8EB1B4C15021750610370'
        AND json_extract(payload, '$.status.probe') IS NOT NULL
        AND json_extract(payload, '$.status.probe') > 0
    """)
    min_probe, max_probe = cursor.fetchone()
    if min_probe and max_probe:
        print(f"  Probe: {min_probe}°F - {max_probe}°F")
    
    # Get set temperatures
    cursor.execute("""
        SELECT DISTINCT json_extract(payload, '$.status.set') as set_temp
        FROM raw_messages 
        WHERE json_extract(payload, '$.status.cook_id') = 'E8EB1B4C15021750610370'
        AND json_extract(payload, '$.status.set') IS NOT NULL
        ORDER BY set_temp
    """)
    set_temps = [row[0] for row in cursor.fetchall()]
    if set_temps:
        print(f"\nSet temperatures used: {', '.join(map(str, set_temps))}°F")

# Now check why it might not be showing in the UI
print("\n=== CHECKING UI VISIBILITY ===")

# The UI queries by timestamp, let's see what the most recent message is
cursor.execute("""
    SELECT timestamp, json_extract(payload, '$.status.cook_id') as cook_id
    FROM raw_messages 
    ORDER BY timestamp DESC 
    LIMIT 5
""")
print("\nMost recent messages in DB:")
for row in cursor.fetchall():
    print(f"  {row[0]} - Cook: {row[1] or '[No cook ID]'}")

# Check if there are any messages after the cook ended
cursor.execute("""
    SELECT COUNT(*) 
    FROM raw_messages 
    WHERE timestamp > '2025-06-22 19:15:26'
""")
newer_count = cursor.fetchone()[0]
print(f"\nMessages after cook ended: {newer_count}")

conn.close()