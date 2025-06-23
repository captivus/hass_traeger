import sqlite3
from datetime import datetime

# Check what happened to June 22 data
legacy_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-stream/data/traeger_data.db")
new_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")

print("=== JUNE 22 MIGRATION DEBUG ===\n")

# Get June 22 messages from legacy
legacy_cursor = legacy_conn.cursor()
legacy_cursor.execute("""
    SELECT COUNT(*), MIN(state_index), MAX(state_index)
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
""")
count, min_idx, max_idx = legacy_cursor.fetchone()
print(f"Legacy June 22: {count} messages, state_index range: {min_idx} to {max_idx}")

# Check if these state_indexes exist in new DB
new_cursor = new_conn.cursor()
new_cursor.execute("""
    SELECT COUNT(*)
    FROM raw_messages 
    WHERE state_index >= ? AND state_index <= ?
""", (min_idx, max_idx))
overlap_count = new_cursor.fetchone()[0]
print(f"New DB has {overlap_count} messages in that state_index range")

# Check timestamps
new_cursor.execute("""
    SELECT COUNT(*)
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
""")
new_june22 = new_cursor.fetchone()[0]
print(f"New DB June 22 messages: {new_june22}")

# Sample the cook IDs
legacy_cursor.execute("""
    SELECT DISTINCT json_extract(payload, '$.status.cook_id')
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
""")
legacy_cooks = [row[0] for row in legacy_cursor.fetchall()]
print(f"\nLegacy June 22 cook IDs: {legacy_cooks}")

new_cursor.execute("""
    SELECT DISTINCT json_extract(payload, '$.status.cook_id')
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
""")
new_cooks = [row[0] for row in new_cursor.fetchall()]
print(f"New DB June 22 cook IDs: {new_cooks}")

legacy_conn.close()
new_conn.close()