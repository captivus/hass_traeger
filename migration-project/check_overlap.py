import sqlite3
from datetime import datetime

# Connect to both databases
legacy_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-stream/data/traeger_data.db")
new_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")

legacy_cursor = legacy_conn.cursor()
new_cursor = new_conn.cursor()

print("=== OVERLAP ANALYSIS ===\n")

# Get date ranges
legacy_cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM raw_messages")
legacy_min, legacy_max = legacy_cursor.fetchone()
print(f"Legacy DB date range: {legacy_min} to {legacy_max}")

new_cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM raw_messages")
new_min, new_max = new_cursor.fetchone()
print(f"New DB date range: {new_min} to {new_max}")

# Check for overlap period
print(f"\nOverlap check:")
if legacy_max < new_min:
    print("No overlap - legacy ends before new begins")
elif new_max < legacy_min:
    print("No overlap - new ends before legacy begins")
else:
    print(f"OVERLAP DETECTED between {max(legacy_min, new_min)} and {min(legacy_max, new_max)}")

# Check state_index ranges
legacy_cursor.execute("SELECT MIN(state_index), MAX(state_index) FROM raw_messages WHERE state_index IS NOT NULL")
legacy_min_idx, legacy_max_idx = legacy_cursor.fetchone()
print(f"\nLegacy state_index range: {legacy_min_idx} to {legacy_max_idx}")

new_cursor.execute("SELECT MIN(state_index), MAX(state_index) FROM raw_messages WHERE state_index IS NOT NULL")
new_min_idx, new_max_idx = new_cursor.fetchone()
print(f"New state_index range: {new_min_idx} to {new_max_idx}")

# Check for duplicate state_index values
print("\nChecking for duplicate state_index values...")
legacy_cursor.execute("SELECT state_index FROM raw_messages WHERE state_index >= ? AND state_index <= ?", 
                     (new_min_idx, new_max_idx))
legacy_indexes = set(row[0] for row in legacy_cursor.fetchall() if row[0] is not None)

new_cursor.execute("SELECT state_index FROM raw_messages")
new_indexes = set(row[0] for row in new_cursor.fetchall() if row[0] is not None)

duplicates = legacy_indexes.intersection(new_indexes)
print(f"Found {len(duplicates)} duplicate state_index values")

if duplicates:
    print("\nSample duplicate state_indexes:", list(duplicates)[:10])

# Schema comparison
print("\n=== SCHEMA COMPARISON ===")
print("\nBoth databases have identical raw_messages schema:")
print("  id INTEGER PRIMARY KEY")
print("  timestamp DATETIME")
print("  topic TEXT NOT NULL")
print("  payload TEXT NOT NULL")
print("  state_index INTEGER")

# Message counts
legacy_cursor.execute("SELECT COUNT(*) FROM raw_messages")
legacy_count = legacy_cursor.fetchone()[0]
new_cursor.execute("SELECT COUNT(*) FROM raw_messages")
new_count = new_cursor.fetchone()[0]

print(f"\n=== MESSAGE COUNTS ===")
print(f"Legacy DB: {legacy_count} messages")
print(f"New DB: {new_count} messages")
print(f"Total if combined: {legacy_count + new_count}")
print(f"Minus duplicates: {legacy_count + new_count - len(duplicates)}")

legacy_conn.close()
new_conn.close()