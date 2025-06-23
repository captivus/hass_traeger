import sqlite3

# Connect to both databases
legacy_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-stream/data/traeger_data.db")
new_conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")

legacy_cursor = legacy_conn.cursor()
new_cursor = new_conn.cursor()

print("=== DUPLICATE BREAKDOWN ANALYSIS ===\n")

# Get existing state_indexes in new database
new_cursor.execute("SELECT state_index FROM raw_messages WHERE state_index IS NOT NULL")
existing_state_indexes = set(row[0] for row in new_cursor.fetchall())

# Get existing timestamp+topic combinations
new_cursor.execute("SELECT timestamp, topic FROM raw_messages")
existing_timestamp_topics = set((row[0], row[1]) for row in new_cursor.fetchall())

# Get ALL messages from legacy DB
legacy_cursor.execute("""
    SELECT id, timestamp, topic, payload, state_index 
    FROM raw_messages 
    ORDER BY timestamp ASC
""")

state_index_dups = 0
timestamp_topic_dups = 0
both_dups = 0

for msg in legacy_cursor.fetchall():
    msg_id, timestamp, topic, payload, state_index = msg
    
    state_dup = state_index and state_index in existing_state_indexes
    time_dup = (timestamp, topic) in existing_timestamp_topics
    
    if state_dup and time_dup:
        both_dups += 1
    elif state_dup:
        state_index_dups += 1
    elif time_dup:
        timestamp_topic_dups += 1

print(f"Duplicates by state_index only: {state_index_dups}")
print(f"Duplicates by timestamp+topic only: {timestamp_topic_dups}")
print(f"Duplicates by BOTH criteria: {both_dups}")
print(f"Total duplicates: {state_index_dups + timestamp_topic_dups + both_dups}")

legacy_conn.close()
new_conn.close()