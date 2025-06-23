import sqlite3
import json
from datetime import datetime

legacy_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-stream/data/traeger_data.db")
new_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")

print("=== ANALYZING MESSAGES WITH SAME STATE_INDEX ===\n")

# Get a few examples of matching state_indexes
legacy_cursor = legacy_conn.cursor()
new_cursor = new_conn.cursor()

# Find state_indexes that exist in both databases
legacy_cursor.execute("SELECT DISTINCT state_index FROM raw_messages WHERE state_index IS NOT NULL")
legacy_indexes = set(row[0] for row in legacy_cursor.fetchall())

new_cursor.execute("SELECT DISTINCT state_index FROM raw_messages WHERE state_index IS NOT NULL")
new_indexes = set(row[0] for row in new_cursor.fetchall())

common_indexes = legacy_indexes.intersection(new_indexes)
print(f"Found {len(common_indexes)} state_index values in both databases\n")

# Examine a few in detail
examples = list(common_indexes)[:3]

for state_idx in examples:
    print(f"\n{'='*60}")
    print(f"STATE_INDEX: {state_idx}")
    print(f"{'='*60}")
    
    # Get from legacy
    legacy_cursor.execute("""
        SELECT timestamp, payload
        FROM raw_messages 
        WHERE state_index = ?
    """, (state_idx,))
    legacy_row = legacy_cursor.fetchone()
    
    # Get from new
    new_cursor.execute("""
        SELECT timestamp, payload
        FROM raw_messages 
        WHERE state_index = ?
    """, (state_idx,))
    new_row = new_cursor.fetchone()
    
    if legacy_row and new_row:
        legacy_time = datetime.fromisoformat(legacy_row[0].replace('T', ' '))
        new_time = datetime.fromisoformat(new_row[0].replace('T', ' '))
        time_diff = (new_time - legacy_time).total_seconds()
        
        print(f"\nTiming:")
        print(f"  Legacy timestamp: {legacy_row[0]}")
        print(f"  New timestamp:    {new_row[0]}")
        print(f"  Time difference:  {time_diff} seconds")
        
        # Parse payloads
        legacy_payload = json.loads(legacy_row[1])
        new_payload = json.loads(new_row[1])
        
        # Compare key fields
        legacy_status = legacy_payload.get('status', {})
        new_status = new_payload.get('status', {})
        
        print(f"\nKey Fields:")
        print(f"  Cook ID:     {legacy_status.get('cook_id')}")
        print(f"  Grill Temp:  Legacy={legacy_status.get('grill')}°F, New={new_status.get('grill')}°F")
        print(f"  Grill Time:  Legacy={legacy_status.get('time')}, New={new_status.get('time')}")
        print(f"  Server Status: Legacy={legacy_status.get('server_status')}, New={new_status.get('server_status')}")
        
        # Check if this is truly the same message
        print(f"\nAnalysis:")
        if legacy_status.get('time') == new_status.get('time'):
            print("  ✓ Same grill time - this IS the same state update from the grill")
            print(f"  ✓ Captured by legacy system at: {legacy_row[0]}")
            print(f"  ✓ Captured by new system at:    {new_row[0]}")
            print(f"  → Both systems captured the same grill state update")
        else:
            print("  ✗ Different grill times - these are different states!")

# Now let's check: are there messages with the same stateIndex but different content?
print(f"\n\n{'='*60}")
print("CHECKING FOR CONFLICTING STATE_INDEXES")
print(f"{'='*60}")

for state_idx in examples[:1]:  # Just check one
    legacy_cursor.execute("""
        SELECT json_extract(payload, '$.status.time') as grill_time,
               json_extract(payload, '$.status.grill') as grill_temp
        FROM raw_messages 
        WHERE state_index = ?
    """, (state_idx,))
    legacy_data = legacy_cursor.fetchone()
    
    new_cursor.execute("""
        SELECT json_extract(payload, '$.status.time') as grill_time,
               json_extract(payload, '$.status.grill') as grill_temp
        FROM raw_messages 
        WHERE state_index = ?
    """, (state_idx,))
    new_data = new_cursor.fetchone()
    
    if legacy_data[0] != new_data[0]:
        print(f"\n⚠️  CONFLICT at state_index {state_idx}:")
        print(f"  Legacy grill time: {legacy_data[0]}")
        print(f"  New grill time:    {new_data[0]}")
        print("  These are DIFFERENT states with the same index!")
    else:
        print(f"\n✓ State_index {state_idx} represents the same grill state in both DBs")
        print(f"  Grill time: {legacy_data[0]} (same in both)")
        print(f"  This is a true duplicate - same data captured by both systems")

legacy_conn.close()
new_conn.close()