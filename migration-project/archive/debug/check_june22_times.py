import sqlite3

new_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = new_conn.cursor()

# Get all June 22 records with their cook IDs
cursor.execute("""
    SELECT timestamp, json_extract(payload, '$.status.cook_id') as cook_id
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
    AND json_extract(payload, '$.status.cook_id') = 'E8EB1B4C15021750610370'
    ORDER BY timestamp DESC
    LIMIT 10
""")

print("Real cook data in migrated DB:")
for row in cursor.fetchall():
    print(f"  Time: {row[0]}, Cook: {row[1]}")

# Count by cook ID
cursor.execute("""
    SELECT json_extract(payload, '$.status.cook_id') as cook_id, COUNT(*) as count
    FROM raw_messages 
    WHERE date(timestamp) = '2025-06-22'
    GROUP BY cook_id
""")

print("\nJune 22 message counts by cook ID:")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} messages")

new_conn.close()