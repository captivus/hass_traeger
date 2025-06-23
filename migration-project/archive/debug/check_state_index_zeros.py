import sqlite3

conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = conn.cursor()

# Check the low state_index values
cursor.execute("""
    SELECT id, timestamp, state_index 
    FROM raw_messages 
    WHERE state_index <= 10
    ORDER BY state_index, timestamp
""")

print("Messages with state_index <= 10:")
for row in cursor.fetchall():
    print(f"  ID: {row[0]}, Time: {row[1]}, StateIdx: {row[2]}")

conn.close()