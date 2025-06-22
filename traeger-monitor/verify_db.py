#!/usr/bin/env python3
"""Verify database is receiving data."""

import sqlite3
from pathlib import Path
import time

DB_PATH = Path("data/traeger.db")

def verify_database():
    """Check database for recent messages."""
    if not DB_PATH.exists():
        print("✗ Database does not exist yet")
        return
        
    with sqlite3.connect(DB_PATH) as conn:
        # Check total messages
        cursor = conn.execute("SELECT COUNT(*) FROM raw_messages")
        total = cursor.fetchone()[0]
        print(f"Total messages in database: {total}")
        
        # Check recent messages
        cursor = conn.execute("""
            SELECT datetime(timestamp, 'localtime') as local_time, topic, state_index 
            FROM raw_messages 
            ORDER BY timestamp DESC 
            LIMIT 10
        """)
        
        print("\nLast 10 messages:")
        print("-" * 80)
        for row in cursor:
            print(f"{row[0]} | {row[1]} | state_index: {row[2]}")
            
        # Check for duplicates
        cursor = conn.execute("""
            SELECT topic, state_index, COUNT(*) as count 
            FROM raw_messages 
            WHERE state_index IS NOT NULL
            GROUP BY topic, state_index 
            HAVING count > 1
        """)
        
        duplicates = list(cursor)
        if duplicates:
            print(f"\n✗ Found {len(duplicates)} duplicate state_index entries!")
            for dup in duplicates:
                print(f"  {dup[0]} | state_index: {dup[1]} | count: {dup[2]}")
        else:
            print("\n✓ No duplicate messages found")

if __name__ == "__main__":
    verify_database()