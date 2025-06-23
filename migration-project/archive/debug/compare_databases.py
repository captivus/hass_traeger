import sqlite3
import json
from datetime import datetime
import pytz

# Set up timezone
central_tz = pytz.timezone('US/Central')
utc_tz = pytz.UTC

# Get date range for June 22, 2025 in Central time
start_central = central_tz.localize(datetime(2025, 6, 22, 0, 0, 0))
end_central = central_tz.localize(datetime(2025, 6, 22, 23, 59, 59))

# Convert to UTC for database query
start_utc = start_central.astimezone(utc_tz).isoformat()
end_utc = end_central.astimezone(utc_tz).isoformat()

print(f"Comparing data for June 22, 2025")
print(f"Central time range: {start_central} to {end_central}")
print(f"UTC time range: {start_utc} to {end_utc}")
print("="*80)

# Query legacy database
print("\n=== LEGACY DATABASE (traeger-stream/data/traeger_data.db) ===")
legacy_conn = sqlite3.connect('/workspaces/hass_traeger/traeger-stream/data/traeger_data.db')
legacy_cursor = legacy_conn.cursor()

# Get table structure
legacy_cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='raw_messages'")
print(f"Table structure: {legacy_cursor.fetchone()}")

# Count records for today
legacy_query = '''
SELECT COUNT(*) as count
FROM raw_messages 
WHERE timestamp >= ? AND timestamp <= ?
'''
legacy_cursor.execute(legacy_query, (start_utc, end_utc))
legacy_count = legacy_cursor.fetchone()[0]
print(f"\nTotal records for June 22: {legacy_count}")

# Get sample records
legacy_cursor.execute('''
SELECT id, state_index, timestamp, channel, event_type, payload 
FROM raw_messages 
WHERE timestamp >= ? AND timestamp <= ?
ORDER BY timestamp
LIMIT 5
''', (start_utc, end_utc))

print("\nSample records:")
for row in legacy_cursor.fetchall():
    print(f"  ID: {row[0]}, StateIdx: {row[1]}, Time: {row[2][:19]}, Chan: {row[3]}, Event: {row[4]}")

# Get unique cook IDs from legacy
legacy_cursor.execute('''
SELECT DISTINCT json_extract(payload, '$.status.cook_id') as cook_id
FROM raw_messages 
WHERE timestamp >= ? AND timestamp <= ?
AND json_extract(payload, '$.status.cook_id') IS NOT NULL
''', (start_utc, end_utc))
legacy_cook_ids = [row[0] for row in legacy_cursor.fetchall()]
print(f"\nUnique cook IDs: {legacy_cook_ids}")

legacy_conn.close()

# Query migrated database
print("\n\n=== MIGRATED DATABASE (traeger-monitor/data/traeger.db) ===")
migrated_conn = sqlite3.connect('/workspaces/hass_traeger/traeger-monitor/data/traeger.db')
migrated_cursor = migrated_conn.cursor()

# Get table structure
migrated_cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='raw_messages'")
print(f"Table structure: {migrated_cursor.fetchone()}")

# Count records for today
migrated_cursor.execute(legacy_query, (start_utc, end_utc))
migrated_count = migrated_cursor.fetchone()[0]
print(f"\nTotal records for June 22: {migrated_count}")

# Get sample records
migrated_cursor.execute('''
SELECT timestamp, payload 
FROM raw_messages 
WHERE timestamp >= ? AND timestamp <= ?
ORDER BY timestamp
LIMIT 5
''', (start_utc, end_utc))

print("\nSample records:")
for row in migrated_cursor.fetchall():
    payload = json.loads(row[1])
    status = payload.get('status', {})
    print(f"  Time: {row[0][:19]}, Cook: {status.get('cook_id', 'N/A')}, Grill: {status.get('grill', 'N/A')}°F")

# Get unique cook IDs from migrated
migrated_cursor.execute('''
SELECT timestamp, payload 
FROM raw_messages 
WHERE timestamp >= ? AND timestamp <= ?
''', (start_utc, end_utc))

migrated_cook_ids = set()
for row in migrated_cursor.fetchall():
    payload = json.loads(row[1])
    cook_id = payload.get('status', {}).get('cook_id')
    if cook_id:
        migrated_cook_ids.add(cook_id)

print(f"\nUnique cook IDs: {list(migrated_cook_ids)}")

migrated_conn.close()

# Compare results
print("\n\n=== COMPARISON ===")
print(f"Legacy records: {legacy_count}")
print(f"Migrated records: {migrated_count}")
print(f"Difference: {legacy_count - migrated_count} records")

print(f"\nLegacy cook IDs: {legacy_cook_ids}")
print(f"Migrated cook IDs: {list(migrated_cook_ids)}")

if set(legacy_cook_ids) == migrated_cook_ids:
    print("\n✓ Cook IDs match between databases")
else:
    print("\n✗ Cook IDs differ between databases")
    print(f"  Only in legacy: {set(legacy_cook_ids) - migrated_cook_ids}")
    print(f"  Only in migrated: {migrated_cook_ids - set(legacy_cook_ids)}")