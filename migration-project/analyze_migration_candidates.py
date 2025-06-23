import sqlite3
import json
from datetime import datetime

# Connect to both databases
legacy_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-stream/data/traeger_data.db")
new_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")

print("=== COMPREHENSIVE MIGRATION ANALYSIS ===\n")

# First, get the actual date ranges
legacy_cursor = legacy_conn.cursor()
new_cursor = new_conn.cursor()

# Legacy DB range
legacy_cursor.execute("SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM raw_messages")
legacy_min, legacy_max, legacy_count = legacy_cursor.fetchone()
print(f"Legacy DB: {legacy_count} messages")
print(f"  Range: {legacy_min} to {legacy_max}")

# New DB range
new_cursor.execute("SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM raw_messages")
new_min, new_max, new_count = new_cursor.fetchone()
print(f"\nNew DB: {new_count} messages")
print(f"  Range: {new_min} to {new_max}")

# Get ALL state_indexes from new DB for comparison
print("\n=== BUILDING DEDUPLICATION SETS ===")
new_cursor.execute("SELECT state_index, timestamp, topic FROM raw_messages")
new_state_indexes = set()
new_timestamp_topics = set()

for row in new_cursor.fetchall():
    state_idx, timestamp, topic = row
    if state_idx is not None:
        new_state_indexes.add(state_idx)
    new_timestamp_topics.add((timestamp, topic))

print(f"New DB has {len(new_state_indexes)} unique state_indexes")
print(f"New DB has {len(new_timestamp_topics)} unique timestamp+topic combinations")

# Now analyze what would actually be migrated
print("\n=== ANALYZING MIGRATION CANDIDATES ===")

# Get ALL messages from legacy DB
legacy_cursor.execute("""
    SELECT id, timestamp, topic, state_index, LENGTH(payload) as payload_len
    FROM raw_messages
    ORDER BY timestamp
""")

candidates = []
duplicates_by_state_index = []
duplicates_by_timestamp_topic = []
before_new_db_start = []
after_new_db_end = []

for row in legacy_cursor.fetchall():
    msg_id, timestamp, topic, state_index, payload_len = row
    
    # Check if this would be a duplicate
    is_duplicate = False
    
    if state_index and state_index in new_state_indexes:
        duplicates_by_state_index.append(row)
        is_duplicate = True
    elif (timestamp, topic) in new_timestamp_topics:
        duplicates_by_timestamp_topic.append(row)
        is_duplicate = True
    
    if not is_duplicate:
        candidates.append(row)
        
        # Categorize by time
        if timestamp < new_min:
            before_new_db_start.append(row)
        elif timestamp > new_max:
            after_new_db_end.append(row)

print(f"\nTotal legacy messages analyzed: {legacy_count}")
print(f"Would be skipped (state_index duplicate): {len(duplicates_by_state_index)}")
print(f"Would be skipped (timestamp+topic duplicate): {len(duplicates_by_timestamp_topic)}")
print(f"Total duplicates: {len(duplicates_by_state_index) + len(duplicates_by_timestamp_topic)}")
print(f"\nMigration candidates: {len(candidates)}")
print(f"  - Before new DB start: {len(before_new_db_start)}")
print(f"  - During overlap period: {len(candidates) - len(before_new_db_start) - len(after_new_db_end)}")
print(f"  - After new DB end: {len(after_new_db_end)}")

# Show some examples
if before_new_db_start:
    print(f"\n=== SAMPLE MESSAGES BEFORE NEW DB START ===")
    for row in before_new_db_start[:3]:
        print(f"  ID: {row[0]}, Time: {row[1]}, Topic: {row[2]}, StateIdx: {row[3]}")

# Analyze the overlap period more carefully
print(f"\n=== OVERLAP PERIOD ANALYSIS ===")
overlap_candidates = len(candidates) - len(before_new_db_start) - len(after_new_db_end)
print(f"Messages in overlap period that are NOT duplicates: {overlap_candidates}")
print("This suggests the two systems were capturing different messages!")

# Check cook_ids to understand better
print("\n=== COOK ID ANALYSIS ===")
legacy_cursor.execute("""
    SELECT DISTINCT json_extract(payload, '$.status.cook_id') as cook_id
    FROM raw_messages
    WHERE json_extract(payload, '$.status.cook_id') IS NOT NULL
    AND json_extract(payload, '$.status.cook_id') != ''
""")
legacy_cook_ids = [row[0] for row in legacy_cursor.fetchall()]
print(f"Legacy DB cook IDs: {len(legacy_cook_ids)}")
for cook_id in legacy_cook_ids[:5]:
    print(f"  {cook_id}")

legacy_conn.close()
new_conn.close()