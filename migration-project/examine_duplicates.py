import sqlite3
import json

# Connect to both databases
legacy_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-stream/data/traeger_data.db")
new_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")

legacy_cursor = legacy_conn.cursor()
new_cursor = new_conn.cursor()

print("=== EXAMINING DUPLICATE DETECTION LOGIC ===\n")

# First, let's look at what state_index actually represents
print("1. Understanding state_index values:")
print("-" * 50)

# Get some examples from both databases
legacy_cursor.execute("""
    SELECT timestamp, state_index, json_extract(payload, '$.stateIndex') as payload_state_index
    FROM raw_messages 
    WHERE state_index IS NOT NULL
    ORDER BY timestamp
    LIMIT 5
""")
print("\nLegacy DB examples:")
for row in legacy_cursor.fetchall():
    print(f"  Time: {row[0]}, state_index: {row[1]}, payload.stateIndex: {row[2]}")

new_cursor.execute("""
    SELECT timestamp, state_index, json_extract(payload, '$.stateIndex') as payload_state_index
    FROM raw_messages 
    WHERE state_index IS NOT NULL
    ORDER BY timestamp
    LIMIT 5
""")
print("\nNew DB examples:")
for row in new_cursor.fetchall():
    print(f"  Time: {row[0]}, state_index: {row[1]}, payload.stateIndex: {row[2]}")

# Now let's find an actual "duplicate" and compare
print("\n\n2. Examining a 'duplicate' state_index (1859679):")
print("-" * 50)

# Get the messages with this state_index from both DBs
legacy_cursor.execute("""
    SELECT timestamp, topic, state_index, payload
    FROM raw_messages 
    WHERE state_index = 1859679
""")
legacy_msg = legacy_cursor.fetchone()

new_cursor.execute("""
    SELECT timestamp, topic, state_index, payload
    FROM raw_messages 
    WHERE state_index = 1859679
""")
new_msg = new_cursor.fetchone()

if legacy_msg and new_msg:
    print(f"\nLegacy message:")
    print(f"  Timestamp: {legacy_msg[0]}")
    print(f"  Topic: {legacy_msg[1]}")
    print(f"  State Index: {legacy_msg[2]}")
    
    print(f"\nNew message:")
    print(f"  Timestamp: {new_msg[0]}")
    print(f"  Topic: {new_msg[1]}")
    print(f"  State Index: {new_msg[2]}")
    
    # Compare timestamps
    print(f"\n  Timestamps match? {legacy_msg[0] == new_msg[0]}")
    
    # Compare the actual payloads
    legacy_payload = json.loads(legacy_msg[3])
    new_payload = json.loads(new_msg[3])
    
    # Compare key fields
    print(f"\n  Comparing payload contents:")
    legacy_status = legacy_payload.get('status', {})
    new_status = new_payload.get('status', {})
    
    print(f"    Cook ID match? {legacy_status.get('cook_id') == new_status.get('cook_id')}")
    print(f"    Grill temp match? {legacy_status.get('grill') == new_status.get('grill')}")
    print(f"    Time field match? {legacy_status.get('time') == new_status.get('time')}")
    
    # Check if payloads are identical
    payloads_identical = legacy_msg[3] == new_msg[3]
    print(f"\n  Entire payloads identical? {payloads_identical}")
    
    if not payloads_identical:
        print("\n  Payload differences exist!")
        print(f"    Legacy payload length: {len(legacy_msg[3])}")
        print(f"    New payload length: {len(new_msg[3])}")

# Let's check if state_index truly represents unique messages
print("\n\n3. Checking state_index uniqueness within each database:")
print("-" * 50)

legacy_cursor.execute("""
    SELECT state_index, COUNT(*) as count
    FROM raw_messages 
    WHERE state_index IS NOT NULL
    GROUP BY state_index
    HAVING count > 1
    LIMIT 5
""")
legacy_dups = legacy_cursor.fetchall()
print(f"\nLegacy DB duplicate state_indexes: {len(legacy_dups)}")
if legacy_dups:
    print("  Examples:", legacy_dups)

new_cursor.execute("""
    SELECT state_index, COUNT(*) as count
    FROM raw_messages 
    WHERE state_index IS NOT NULL
    GROUP BY state_index
    HAVING count > 1
    LIMIT 5
""")
new_dups = new_cursor.fetchall()
print(f"\nNew DB duplicate state_indexes: {len(new_dups)}")
if new_dups:
    print("  Examples:", new_dups)

# Let's understand what stateIndex represents
print("\n\n4. Understanding stateIndex semantics:")
print("-" * 50)
print("\nstateIndex appears to be a monotonically increasing counter from the grill")
print("that increments with each state update. If two systems captured the same")
print("state update from the grill, they would have the same stateIndex.")
print("\nBUT: The timestamps might differ slightly due to:")
print("- Network latency differences")
print("- Processing time differences")
print("- Clock differences between systems")

legacy_conn.close()
new_conn.close()