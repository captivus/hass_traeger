import sqlite3
import json

# Check visibility of June 22 data
new_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = new_conn.cursor()

# Get June 22 messages grouped by cook ID
cursor.execute("""
    SELECT 
        json_extract(payload, '$.status.cook_id') as cook_id,
        COUNT(*) as count,
        MIN(timestamp) as first_msg,
        MAX(timestamp) as last_msg
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
    GROUP BY cook_id
    ORDER BY count DESC
""")

print("=== JUNE 22 DATA IN NEW DB ===")
print("\nMessages by Cook ID:")
for row in cursor.fetchall():
    cook_id = row[0] if row[0] else "[NO COOK ID]"
    print(f"  {cook_id}: {row[1]} messages ({row[2]} to {row[3]})")

# Check if there's a visibility issue with the cook_id extraction
cursor.execute("""
    SELECT COUNT(*) 
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
    AND json_extract(payload, '$.status.cook_id') = 'E8EB1B4C15021750610370'
""")
real_cook_count = cursor.fetchone()[0]

cursor.execute("""
    SELECT COUNT(*) 
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
    AND payload LIKE '%E8EB1B4C15021750610370%'
""")
text_search_count = cursor.fetchone()[0]

print(f"\nReal cook E8EB1B4C15021750610370:")
print(f"  Found by JSON extract: {real_cook_count}")
print(f"  Found by text search: {text_search_count}")

# Sample a few messages to see their structure
cursor.execute("""
    SELECT timestamp, topic, substr(payload, 1, 200)
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
    AND json_extract(payload, '$.status.cook_id') = 'E8EB1B4C15021750610370'
    LIMIT 3
""")

print("\nSample messages from real cook:")
for row in cursor.fetchall():
    print(f"  {row[0]} - {row[1]}")
    print(f"    {row[2]}...")

new_conn.close()