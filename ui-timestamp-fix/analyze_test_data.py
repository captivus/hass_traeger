import sqlite3
import json
from datetime import datetime

# Comprehensive analysis of test data in the database
conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = conn.cursor()

print("=== TEST DATA ANALYSIS ===\n")

# 1. Find all test cook records
cursor.execute("""
    SELECT 
        json_extract(payload, '$.status.cook_id') as cook_id,
        COUNT(*) as record_count,
        MIN(timestamp) as first_record,
        MAX(timestamp) as last_record
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') LIKE 'TEST_COOK_%'
    GROUP BY cook_id
    ORDER BY first_record
""")

test_cooks = cursor.fetchall()
total_test_records = sum(row[1] for row in test_cooks)

print(f"TEST COOK SESSIONS FOUND: {len(test_cooks)}")
print(f"TOTAL TEST RECORDS: {total_test_records}")
print("\nBreakdown by cook ID:")
for cook_id, count, first, last in test_cooks:
    duration = datetime.fromisoformat(last.replace('Z', '+00:00')) - datetime.fromisoformat(first.replace('Z', '+00:00'))
    print(f"  {cook_id}: {count} records ({first} to {last}) - Duration: {duration}")

# 2. Check timestamp formats
cursor.execute("""
    SELECT 
        CASE 
            WHEN timestamp LIKE '%T%' THEN 'ISO_FORMAT'
            ELSE 'SPACE_FORMAT'
        END as format_type,
        COUNT(*) as count,
        MIN(timestamp) as earliest,
        MAX(timestamp) as latest
    FROM raw_messages
    GROUP BY format_type
""")

print(f"\n=== TIMESTAMP FORMAT ANALYSIS ===")
for format_type, count, earliest, latest in cursor.fetchall():
    print(f"{format_type}: {count} records")
    print(f"  Range: {earliest} to {latest}")

# 3. Check what percentage of recent data is test data
cursor.execute("""
    SELECT 
        CASE 
            WHEN json_extract(payload, '$.status.cook_id') LIKE 'TEST_COOK_%' THEN 'TEST_DATA'
            WHEN json_extract(payload, '$.status.cook_id') = 'E8EB1B4C15021750610370' THEN 'REAL_COOK_JUNE22'
            WHEN json_extract(payload, '$.status.cook_id') IS NULL THEN 'NO_COOK_ID'
            ELSE 'OTHER_COOK'
        END as data_type,
        COUNT(*) as count
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
    GROUP BY data_type
    ORDER BY count DESC
""")

print(f"\n=== JUNE 22 DATA BREAKDOWN ===")
for data_type, count in cursor.fetchall():
    print(f"  {data_type}: {count} records")

# 4. Check if test data is interfering with API queries
cursor.execute("""
    SELECT 
        timestamp,
        json_extract(payload, '$.status.cook_id') as cook_id,
        json_extract(payload, '$.status.grill') as grill_temp
    FROM raw_messages 
    ORDER BY timestamp DESC 
    LIMIT 20
""")

print(f"\n=== 20 MOST RECENT RECORDS (what API sees) ===")
for i, (ts, cook_id, grill_temp) in enumerate(cursor.fetchall(), 1):
    print(f"  {i:2d}. {ts} - {cook_id or '[No cook ID]'} - Grill: {grill_temp}°F")

# 5. Check when test data was created vs real cook
cursor.execute("""
    SELECT 
        'Real Cook' as source,
        MIN(timestamp) as start_time,
        MAX(timestamp) as end_time,
        COUNT(*) as records
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = 'E8EB1B4C15021750610370'
    
    UNION ALL
    
    SELECT 
        'Test Data' as source,
        MIN(timestamp) as start_time,
        MAX(timestamp) as end_time,
        COUNT(*) as records
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') LIKE 'TEST_COOK_%'
""")

print(f"\n=== TIMING COMPARISON ===")
for source, start, end, count in cursor.fetchall():
    print(f"  {source}: {start} to {end} ({count} records)")

# 6. Sample test data payloads to understand structure
cursor.execute("""
    SELECT timestamp, payload
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') LIKE 'TEST_COOK_%'
    LIMIT 2
""")

print(f"\n=== SAMPLE TEST DATA PAYLOADS ===")
for i, (ts, payload) in enumerate(cursor.fetchall(), 1):
    data = json.loads(payload)
    status = data.get('status', {})
    print(f"\nSample {i} at {ts}:")
    print(f"  Cook ID: {status.get('cook_id')}")
    print(f"  Grill: {status.get('grill')}°F")
    print(f"  Probes: {len(status.get('acc', []))} accessories")
    for j, acc in enumerate(status.get('acc', [])):
        if acc.get('type') in ['probe', 'btprobe']:
            print(f"    {acc.get('type')} {acc.get('channel')}: connected={acc.get('con')}")

conn.close()