import sqlite3
from datetime import datetime

# Connect to both databases
legacy_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-stream/data/traeger_data.db")
new_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")

legacy_cursor = legacy_conn.cursor()
new_cursor = new_conn.cursor()

print("=== DETAILED OVERLAP ANALYSIS ===\n")

# Get messages in overlap period
overlap_start = "2025-05-30 16:22:04"
overlap_end = "2025-06-22 20:34:10"

print(f"Analyzing overlap period: {overlap_start} to {overlap_end}\n")

# Count messages in overlap period for each DB
legacy_cursor.execute("""
    SELECT COUNT(*) FROM raw_messages 
    WHERE timestamp >= ? AND timestamp <= ?
""", (overlap_start, overlap_end))
legacy_overlap_count = legacy_cursor.fetchone()[0]

new_cursor.execute("""
    SELECT COUNT(*) FROM raw_messages 
    WHERE timestamp >= ? AND timestamp <= ?
""", (overlap_start, overlap_end))
new_overlap_count = new_cursor.fetchone()[0]

print(f"Legacy messages in overlap period: {legacy_overlap_count}")
print(f"New messages in overlap period: {new_overlap_count}")

# Get unique messages from legacy that need to be migrated
legacy_cursor.execute("""
    SELECT COUNT(*) FROM raw_messages 
    WHERE timestamp < ?
""", (overlap_start,))
legacy_before_overlap = legacy_cursor.fetchone()[0]

print(f"\nLegacy messages BEFORE overlap (need migration): {legacy_before_overlap}")

# Analyze duplicate handling strategy
print("\n=== DUPLICATE HANDLING STRATEGY ===")
print("\nAnalyzing messages with duplicate state_index values...")

# Get a sample duplicate state_index
legacy_cursor.execute("""
    SELECT timestamp, state_index, LENGTH(payload) as payload_len 
    FROM raw_messages 
    WHERE state_index = 1859679
""")
legacy_dup = legacy_cursor.fetchone()

new_cursor.execute("""
    SELECT timestamp, state_index, LENGTH(payload) as payload_len 
    FROM raw_messages 
    WHERE state_index = 1859679
""")
new_dup = new_cursor.fetchone()

if legacy_dup and new_dup:
    print(f"\nExample duplicate (state_index: 1859679):")
    print(f"  Legacy: timestamp={legacy_dup[0]}, payload_len={legacy_dup[2]}")
    print(f"  New:    timestamp={new_dup[0]}, payload_len={new_dup[2]}")

# Check if there are any legacy messages after the new DB's last message
new_cursor.execute("SELECT MAX(timestamp) FROM raw_messages")
new_max_time = new_cursor.fetchone()[0]

legacy_cursor.execute("""
    SELECT COUNT(*) FROM raw_messages 
    WHERE timestamp > ?
""", (new_max_time,))
legacy_after_new = legacy_cursor.fetchone()[0]

print(f"\nLegacy messages AFTER new DB's last message: {legacy_after_new}")

# Summary
print("\n=== MIGRATION SUMMARY ===")
print(f"1. Messages to migrate from BEFORE overlap: {legacy_before_overlap}")
print(f"2. Messages to migrate from AFTER new DB ends: {legacy_after_new}")
print(f"3. Duplicate messages to skip: 672")
print(f"4. Total unique messages after migration: ~{legacy_before_overlap + new_overlap_count + legacy_after_new}")

legacy_conn.close()
new_conn.close()