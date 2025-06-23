import sqlite3
import json
from datetime import datetime

# Reproduce the comparison the user saw
new_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = new_conn.cursor()

# Count June 22 messages
cursor.execute("""
    SELECT COUNT(*) 
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
""")
total_june22 = cursor.fetchone()[0]

# Count by cook_id
cursor.execute("""
    SELECT 
        CASE 
            WHEN json_extract(payload, '$.status.cook_id') LIKE 'TEST_COOK_%' THEN 'TEST_COOKS'
            WHEN json_extract(payload, '$.status.cook_id') = 'E8EB1B4C15021750610370' THEN 'REAL_COOK'
            WHEN json_extract(payload, '$.status.cook_id') IS NULL THEN 'NO_COOK_ID'
            ELSE 'OTHER'
        END as cook_type,
        COUNT(*) as count
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
    GROUP BY cook_type
""")

print("=== JUNE 22 MESSAGE BREAKDOWN ===")
print(f"Total messages: {total_june22}")
print("\nBy type:")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]}")

# The user's comparison showed 613 records with cook_id E8EB1B4C15021750610370
# but only 40 TEST records. Let me check if there's a filter being applied
cursor.execute("""
    SELECT COUNT(*)
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
    AND json_extract(payload, '$.status.cook_id') NOT LIKE 'TEST_COOK_%'
    AND json_extract(payload, '$.status.cook_id') IS NOT NULL
""")
non_test_with_cook_id = cursor.fetchone()[0]

print(f"\nNon-test messages with cook_id: {non_test_with_cook_id}")

# Check if the app might be filtering by timestamp format
cursor.execute("""
    SELECT DISTINCT substr(timestamp, 1, 10) as date_part, COUNT(*) as count
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
    GROUP BY date_part
""")
print("\nTimestamp formats:")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} messages")

new_conn.close()