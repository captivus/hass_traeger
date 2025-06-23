#!/usr/bin/env python3
"""
Migration script for Traeger raw messages from legacy to new database.
Handles deduplication and data validation.
"""
import sqlite3
import json
import shutil
from datetime import datetime
import sys

def backup_database(db_path):
    """Create a backup of the database before migration."""
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_path)
    print(f"Created backup: {backup_path}")
    return backup_path

def validate_json_payload(payload):
    """Validate that payload is valid JSON."""
    try:
        json.loads(payload)
        return True
    except:
        return False

def migrate_raw_messages(legacy_db_path, new_db_path, dry_run=True):
    """
    Migrate raw messages from legacy to new database.
    
    Args:
        legacy_db_path: Path to legacy database
        new_db_path: Path to new database
        dry_run: If True, only simulate migration without making changes
    """
    print(f"\n{'DRY RUN' if dry_run else 'ACTUAL'} MIGRATION")
    print("=" * 60)
    
    # Connect to databases
    legacy_conn = sqlite3.connect(legacy_db_path)
    new_conn = sqlite3.connect(new_db_path)
    
    legacy_cursor = legacy_conn.cursor()
    new_cursor = new_conn.cursor()
    
    try:
        # Get existing state_indexes in new database for deduplication
        new_cursor.execute("SELECT state_index FROM raw_messages WHERE state_index IS NOT NULL")
        existing_state_indexes = set(row[0] for row in new_cursor.fetchall())
        
        # Get existing timestamp+topic combinations for secondary deduplication
        new_cursor.execute("SELECT timestamp, topic FROM raw_messages")
        existing_timestamp_topics = set((row[0], row[1]) for row in new_cursor.fetchall())
        
        print(f"Existing records in new DB: {len(existing_state_indexes)} with state_index")
        print(f"Existing timestamp+topic combinations: {len(existing_timestamp_topics)}")
        
        # Get ALL messages from legacy DB (not just before overlap!)
        legacy_cursor.execute("""
            SELECT id, timestamp, topic, payload, state_index 
            FROM raw_messages 
            ORDER BY timestamp ASC
        """)
        
        all_legacy_messages = legacy_cursor.fetchall()
        print(f"\nTotal messages in legacy DB: {len(all_legacy_messages)}")
        
        # Process migration
        migrated_count = 0
        skipped_count = 0
        invalid_json_count = 0
        
        if not dry_run:
            new_conn.execute("BEGIN TRANSACTION")
        
        for msg in all_legacy_messages:
            msg_id, timestamp, topic, payload, state_index = msg
            
            # Validate JSON payload
            if not validate_json_payload(payload):
                print(f"WARNING: Invalid JSON in message ID {msg_id}")
                invalid_json_count += 1
                continue
            
            # Check for duplicates
            if state_index and state_index in existing_state_indexes:
                skipped_count += 1
                continue
            
            if (timestamp, topic) in existing_timestamp_topics:
                skipped_count += 1
                continue
            
            # Migrate the message
            if not dry_run:
                new_cursor.execute("""
                    INSERT INTO raw_messages (timestamp, topic, payload, state_index)
                    VALUES (?, ?, ?, ?)
                """, (timestamp, topic, payload, state_index))
            
            migrated_count += 1
            
            # Add to deduplication sets
            if state_index:
                existing_state_indexes.add(state_index)
            existing_timestamp_topics.add((timestamp, topic))
        
        
        # Commit or rollback
        if not dry_run:
            new_conn.commit()
            print("\nMigration completed successfully!")
        
        # Final statistics
        print(f"\n=== MIGRATION STATISTICS ===")
        print(f"Messages analyzed: {len(all_legacy_messages)}")
        print(f"Messages migrated: {migrated_count}")
        print(f"Messages skipped (duplicates): {skipped_count}")
        print(f"Messages with invalid JSON: {invalid_json_count}")
        
        # Verify final count
        if not dry_run:
            new_cursor.execute("SELECT COUNT(*) FROM raw_messages")
            final_count = new_cursor.fetchone()[0]
            print(f"Final total messages in new DB: {final_count}")
        
    except Exception as e:
        if not dry_run:
            new_conn.rollback()
        print(f"\nERROR: Migration failed - {e}")
        raise
    finally:
        legacy_conn.close()
        new_conn.close()

def main():
    legacy_db = "/workspaces/hass_traeger/traeger-stream/data/traeger_data.db"
    new_db = "/workspaces/hass_traeger/traeger-monitor/data/traeger.db"
    
    # First, do a dry run
    print("Starting dry run to validate migration...")
    migrate_raw_messages(legacy_db, new_db, dry_run=True)
    
    # Ask for confirmation
    print("\n" + "="*60)
    response = input("\nProceed with actual migration? (yes/no): ")
    
    if response.lower() == 'yes':
        # Backup the new database
        backup_path = backup_database(new_db)
        
        # Perform actual migration
        migrate_raw_messages(legacy_db, new_db, dry_run=False)
        
        print(f"\nMigration complete! Backup saved at: {backup_path}")
    else:
        print("Migration cancelled.")

if __name__ == "__main__":
    main()