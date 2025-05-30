#!/usr/bin/env python3
"""Check for duplicate state_index values in the database."""

import sqlite3
from datetime import datetime, timedelta, timezone
import json

# Connect to the database
conn = sqlite3.connect('./data/traeger_data.db')
cursor = conn.cursor()

# Get current time and 30 minutes ago
now = datetime.now(timezone.utc)
thirty_minutes_ago = now - timedelta(minutes=30)

print(f'Analyzing data from {thirty_minutes_ago} to {now} UTC')
print('=' * 80)

# Total records in last 30 minutes
cursor.execute('''
    SELECT COUNT(*) 
    FROM raw_messages 
    WHERE timestamp >= ?
''', (thirty_minutes_ago.strftime('%Y-%m-%d %H:%M:%S'),))
total_records = cursor.fetchone()[0]
print(f'Total records in last 30 minutes: {total_records}')

# Get unique state_index count
cursor.execute('''
    SELECT COUNT(DISTINCT state_index)
    FROM raw_messages 
    WHERE timestamp >= ? AND state_index IS NOT NULL
''', (thirty_minutes_ago.strftime('%Y-%m-%d %H:%M:%S'),))
unique_state_indexes = cursor.fetchone()[0]
print(f'Unique state_index values: {unique_state_indexes}')

# Count NULL state_index values
cursor.execute('''
    SELECT COUNT(*)
    FROM raw_messages 
    WHERE timestamp >= ? AND state_index IS NULL
''', (thirty_minutes_ago.strftime('%Y-%m-%d %H:%M:%S'),))
null_state_indexes = cursor.fetchone()[0]
print(f'Records with NULL state_index: {null_state_indexes}')
print(f'Duplicates (excluding NULLs): {total_records - unique_state_indexes - null_state_indexes}')
print()

# Find duplicate state_index values with counts
print('Duplicate state_index values (showing top 10 most duplicated):')
cursor.execute('''
    SELECT 
        state_index,
        COUNT(*) as count,
        MIN(timestamp) as first_seen,
        MAX(timestamp) as last_seen
    FROM raw_messages 
    WHERE timestamp >= ? AND state_index IS NOT NULL
    GROUP BY state_index
    HAVING count > 1
    ORDER BY count DESC
    LIMIT 10
''', (thirty_minutes_ago.strftime('%Y-%m-%d %H:%M:%S'),))

duplicates = cursor.fetchall()
for state_idx, count, first_seen, last_seen in duplicates:
    print(f'  state_index: {state_idx}, count: {count}')
    print(f'    First seen: {first_seen}')
    print(f'    Last seen:  {last_seen}')
    
    # Parse timestamps to calculate time difference
    first_dt = datetime.strptime(first_seen, '%Y-%m-%d %H:%M:%S')
    last_dt = datetime.strptime(last_seen, '%Y-%m-%d %H:%M:%S')
    time_diff = (last_dt - first_dt).total_seconds()
    print(f'    Time span: {time_diff:.1f} seconds')
    print()

# Look at recent examples with full data
print('Recent duplicate examples with payload data:')
cursor.execute('''
    SELECT state_index, timestamp, payload
    FROM raw_messages
    WHERE state_index IN (
        SELECT state_index 
        FROM raw_messages 
        WHERE timestamp >= ? AND state_index IS NOT NULL
        GROUP BY state_index 
        HAVING COUNT(*) > 1
    )
    AND timestamp >= ?
    ORDER BY state_index, timestamp
    LIMIT 20
''', (thirty_minutes_ago.strftime('%Y-%m-%d %H:%M:%S'), thirty_minutes_ago.strftime('%Y-%m-%d %H:%M:%S')))

examples = cursor.fetchall()
current_state_idx = None
for state_idx, ts, payload in examples:
    if state_idx != current_state_idx:
        print(f'\nstate_index {state_idx}:')
        current_state_idx = state_idx
    
    # Parse payload to show key info
    try:
        data = json.loads(payload)
        print(f'  {ts} - grill_temp: {data.get("currentTemperature")}, target: {data.get("desiredTemperature")}')
    except:
        print(f'  {ts} - [unable to parse payload]')

# Check timing patterns
print('\n\nAnalyzing timing between messages...')
cursor.execute('''
    WITH ordered_messages AS (
        SELECT 
            state_index,
            timestamp,
            LAG(timestamp) OVER (ORDER BY timestamp) as prev_timestamp,
            LAG(state_index) OVER (ORDER BY timestamp) as prev_state_index
        FROM raw_messages 
        WHERE timestamp >= ?
    )
    SELECT 
        state_index,
        prev_state_index,
        timestamp,
        prev_timestamp,
        CAST((julianday(timestamp) - julianday(prev_timestamp)) * 86400 AS INTEGER) as seconds_diff
    FROM ordered_messages
    WHERE prev_timestamp IS NOT NULL
    ORDER BY timestamp DESC
    LIMIT 30
''', (thirty_minutes_ago.strftime('%Y-%m-%d %H:%M:%S'),))

timing_data = cursor.fetchall()
print('\nRecent message timing (last 30 messages):')
for state_idx, prev_state_idx, ts, prev_ts, seconds_diff in timing_data:
    if state_idx == prev_state_idx:
        print(f'  DUPLICATE: state_index {state_idx} repeated after {seconds_diff}s')
    else:
        print(f'  Normal: {prev_state_idx} -> {state_idx} after {seconds_diff}s')

conn.close()