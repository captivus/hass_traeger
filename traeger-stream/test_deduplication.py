#!/usr/bin/env python3
"""Test script to verify deduplication is working correctly."""

import sqlite3
import time
from datetime import datetime
import sys

def monitor_database(duration=60):
    """Monitor database for duplicates."""
    db_path = "data/traeger_data.db"
    
    print(f"Monitoring database for {duration} seconds...")
    print("Time     | Total | Unique | NULL | Dups | New | Rate/min")
    print("-" * 60)
    
    start_time = time.time()
    prev_stats = get_stats(db_path)
    prev_time = start_time
    
    while time.time() - start_time < duration:
        time.sleep(5)
        curr_stats = get_stats(db_path)
        curr_time = time.time()
        
        # Calculate rate
        time_diff = curr_time - prev_time
        new_msgs = curr_stats['total'] - prev_stats['total']
        rate_per_min = (new_msgs / time_diff) * 60 if time_diff > 0 else 0
        
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"{timestamp} | {curr_stats['total']:5d} | {curr_stats['unique']:6d} | "
              f"{curr_stats['null']:4d} | {curr_stats['dups']:4d} | "
              f"{new_msgs:3d} | {rate_per_min:6.1f}")
        
        # Warnings
        if curr_stats['dups'] > 0:
            print("  ⚠️  DUPLICATES DETECTED!")
            show_duplicate_details(db_path)
        
        if curr_stats['null'] > prev_stats['null']:
            print("  ⚠️  NEW NULL STATE_INDEX ENTRIES!")
        
        prev_stats = curr_stats
        prev_time = curr_time
    
    print("\nFinal statistics:")
    print(f"  Total messages: {curr_stats['total']}")
    print(f"  Unique state indexes: {curr_stats['unique']}")
    print(f"  Duplicates: {curr_stats['dups']}")
    print(f"  NULL state_index: {curr_stats['null']}")

def get_stats(db_path):
    """Get current database statistics."""
    conn = sqlite3.connect(db_path)
    
    # Basic counts
    cursor = conn.execute('''
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT state_index) as unique_states,
            COUNT(CASE WHEN state_index IS NULL THEN 1 END) as null_count
        FROM raw_messages
    ''')
    total, unique, null_count = cursor.fetchone()
    
    # Check for duplicates
    cursor = conn.execute('''
        SELECT COUNT(*) FROM (
            SELECT topic, state_index, COUNT(*) as cnt
            FROM raw_messages
            WHERE state_index IS NOT NULL
            GROUP BY topic, state_index
            HAVING cnt > 1
        )
    ''')
    dup_count = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total': total,
        'unique': unique,
        'null': null_count,
        'dups': dup_count
    }

def show_duplicate_details(db_path):
    """Show details about duplicates."""
    conn = sqlite3.connect(db_path)
    
    cursor = conn.execute('''
        SELECT topic, state_index, COUNT(*) as cnt
        FROM raw_messages
        WHERE state_index IS NOT NULL
        GROUP BY topic, state_index
        HAVING cnt > 1
        LIMIT 5
    ''')
    
    for row in cursor:
        print(f"    - Topic: {row[0][-20:]}, StateIndex: {row[1]}, Count: {row[2]}")
    
    conn.close()

if __name__ == "__main__":
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    monitor_database(duration)