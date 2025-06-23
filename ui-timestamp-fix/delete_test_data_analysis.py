import sqlite3
import json

# Analyze what would happen if we delete test data
conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = conn.cursor()

print("=== IMPACT ANALYSIS: DELETING TEST DATA ===\n")

# 1. What exactly would be deleted
cursor.execute("""
    SELECT 
        json_extract(payload, '$.status.cook_id') as cook_id,
        COUNT(*) as records,
        MIN(timestamp) as first_time,
        MAX(timestamp) as last_time
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') LIKE 'TEST_COOK_%'
    GROUP BY cook_id
""")

print("RECORDS TO BE DELETED:")
total_to_delete = 0
for cook_id, count, first, last in cursor.fetchall():
    total_to_delete += count
    print(f"  {cook_id}: {count} records ({first} to {last})")

print(f"\nTOTAL TO DELETE: {total_to_delete} records")

# 2. What would remain as most recent data
cursor.execute("""
    SELECT 
        timestamp,
        json_extract(payload, '$.status.cook_id') as cook_id,
        json_extract(payload, '$.status.grill') as grill_temp
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') NOT LIKE 'TEST_COOK_%'
       OR json_extract(payload, '$.status.cook_id') IS NULL
    ORDER BY timestamp DESC 
    LIMIT 10
""")

print(f"\n10 MOST RECENT RECORDS AFTER DELETION:")
for i, (ts, cook_id, grill_temp) in enumerate(cursor.fetchall(), 1):
    print(f"  {i:2d}. {ts} - {cook_id or '[No cook ID]'} - Grill: {grill_temp}°F")

# 3. Check what the current endpoint would return
cursor.execute("""
    SELECT timestamp, payload 
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') NOT LIKE 'TEST_COOK_%'
       OR json_extract(payload, '$.status.cook_id') IS NULL
    ORDER BY timestamp DESC 
    LIMIT 1
""")

row = cursor.fetchone()
if row:
    ts, payload = row
    data = json.loads(payload)
    status = data.get('status', {})
    print(f"\nNEW /api/current RESPONSE AFTER DELETION:")
    print(f"  Timestamp: {ts}")
    print(f"  Cook ID: {status.get('cook_id', '[None]')}")
    print(f"  Grill: {status.get('grill')}°F")
    print(f"  Grill Set: {status.get('set')}°F")
    print(f"  Probes connected: {len([acc for acc in status.get('acc', []) if acc.get('con') == 1 and acc.get('type') in ['probe', 'btprobe']])}")

# 4. Database size impact
cursor.execute("SELECT COUNT(*) FROM raw_messages")
total_before = cursor.fetchone()[0]
total_after = total_before - total_to_delete

print(f"\nDATABASE SIZE IMPACT:")
print(f"  Before deletion: {total_before:,} records")
print(f"  After deletion: {total_after:,} records")
print(f"  Reduction: {total_to_delete} records ({total_to_delete/total_before*100:.1f}%)")

# 5. Check if any real data has cook_id with TEST in it
cursor.execute("""
    SELECT COUNT(*) 
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') LIKE '%TEST%'
    AND json_extract(payload, '$.status.cook_id') NOT LIKE 'TEST_COOK_%'
""")

other_test_count = cursor.fetchone()[0]
print(f"\nSAFETY CHECK:")
print(f"  Other records with 'TEST' in cook_id: {other_test_count}")

# 6. Generate the DELETE statement
print(f"\nPROPOSED DELETE STATEMENT:")
print(f"DELETE FROM raw_messages")
print(f"WHERE json_extract(payload, '$.status.cook_id') LIKE 'TEST_COOK_%';")

conn.close()