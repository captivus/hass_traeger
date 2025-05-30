#!/usr/bin/env python3
"""Script to clean up duplicate records and migrate database schema."""

import sqlite3
import json
import shutil
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backup_database(db_path: Path) -> Path:
    """Create a backup of the database."""
    backup_path = db_path.parent / f"{db_path.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    logger.info(f"Created backup at: {backup_path}")
    return backup_path


def analyze_duplicates(db_path: Path):
    """Analyze duplicate records in the database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        # Get all messages with parsed state_index
        cursor = conn.execute("""
            SELECT 
                id,
                timestamp,
                topic,
                payload,
                json_extract(payload, '$.stateIndex') as state_index
            FROM raw_messages
            WHERE json_valid(payload)
            ORDER BY timestamp ASC
        """)
        
        messages = cursor.fetchall()
        logger.info(f"Total messages: {len(messages)}")
        
        # Group by topic and state_index
        duplicates = {}
        for msg in messages:
            if msg['state_index'] is not None:
                key = (msg['topic'], msg['state_index'])
                if key not in duplicates:
                    duplicates[key] = []
                duplicates[key].append(dict(msg))
        
        # Find actual duplicates
        duplicate_count = 0
        duplicate_ids = []
        for key, msgs in duplicates.items():
            if len(msgs) > 1:
                duplicate_count += len(msgs) - 1
                # Keep the first (oldest) message, mark others for deletion
                for msg in msgs[1:]:
                    duplicate_ids.append(msg['id'])
        
        logger.info(f"Found {duplicate_count} duplicate messages to remove")
        logger.info(f"Unique (topic, state_index) combinations: {len(duplicates)}")
        
        return duplicate_ids
        
    finally:
        conn.close()


def migrate_schema(db_path: Path, create_index: bool = False):
    """Add state_index column and optionally create unique constraint."""
    conn = sqlite3.connect(db_path)
    
    try:
        # Check if state_index column already exists
        cursor = conn.execute("PRAGMA table_info(raw_messages)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'state_index' not in columns:
            logger.info("Adding state_index column...")
            
            # Add the new column
            conn.execute("ALTER TABLE raw_messages ADD COLUMN state_index INTEGER")
            
            # Populate state_index from JSON payload
            conn.execute("""
                UPDATE raw_messages 
                SET state_index = json_extract(payload, '$.stateIndex')
                WHERE json_valid(payload)
            """)
            
            conn.commit()
            logger.info("state_index column added and populated")
        else:
            logger.info("state_index column already exists")
            
        if create_index:
            # Check if unique index already exists
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name='idx_raw_messages_topic_state_index'
            """)
            if not cursor.fetchone():
                # Create unique index to prevent future duplicates
                conn.execute("""
                    CREATE UNIQUE INDEX idx_raw_messages_topic_state_index 
                    ON raw_messages(topic, state_index)
                    WHERE state_index IS NOT NULL
                """)
                conn.commit()
                logger.info("Unique index created")
            else:
                logger.info("Unique index already exists")
            
    finally:
        conn.close()


def remove_duplicates(db_path: Path, duplicate_ids: list):
    """Remove duplicate records from the database."""
    if not duplicate_ids:
        logger.info("No duplicates to remove")
        return
        
    conn = sqlite3.connect(db_path)
    
    try:
        # Delete duplicates in batches
        batch_size = 100
        for i in range(0, len(duplicate_ids), batch_size):
            batch = duplicate_ids[i:i + batch_size]
            placeholders = ','.join('?' * len(batch))
            conn.execute(f"DELETE FROM raw_messages WHERE id IN ({placeholders})", batch)
        
        conn.commit()
        logger.info(f"Removed {len(duplicate_ids)} duplicate records")
        
    finally:
        conn.close()


def verify_cleanup(db_path: Path):
    """Verify the cleanup was successful."""
    conn = sqlite3.connect(db_path)
    
    try:
        # Check for remaining duplicates
        cursor = conn.execute("""
            SELECT 
                topic,
                state_index,
                COUNT(*) as count
            FROM raw_messages
            WHERE state_index IS NOT NULL
            GROUP BY topic, state_index
            HAVING count > 1
        """)
        
        remaining_duplicates = cursor.fetchall()
        if remaining_duplicates:
            logger.warning(f"Found {len(remaining_duplicates)} remaining duplicate combinations")
            for row in remaining_duplicates:
                logger.warning(f"  Topic: {row[0]}, StateIndex: {row[1]}, Count: {row[2]}")
        else:
            logger.info("No duplicates found - cleanup successful!")
            
        # Get final statistics
        cursor = conn.execute("SELECT COUNT(*) FROM raw_messages")
        total_count = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(DISTINCT state_index) FROM raw_messages WHERE state_index IS NOT NULL")
        unique_count = cursor.fetchone()[0]
        
        logger.info(f"Final statistics: {total_count} total messages, {unique_count} unique state indexes")
        
    finally:
        conn.close()


def main():
    """Main cleanup process."""
    db_path = Path("./data/traeger_data.db")
    
    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        return
    
    logger.info("Starting duplicate cleanup process...")
    
    # Step 1: Create backup
    backup_path = backup_database(db_path)
    
    try:
        # Step 2: Analyze duplicates
        duplicate_ids = analyze_duplicates(db_path)
        
        # Step 3: Migrate schema (without unique index yet)
        migrate_schema(db_path, create_index=False)
        
        # Step 4: Remove duplicates
        remove_duplicates(db_path, duplicate_ids)
        
        # Step 5: Create unique index after duplicates are removed
        migrate_schema(db_path, create_index=True)
        
        # Step 6: Verify cleanup
        verify_cleanup(db_path)
        
        logger.info("Cleanup completed successfully!")
        logger.info(f"Backup preserved at: {backup_path}")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        logger.error("Database backup is preserved for recovery")
        raise


if __name__ == "__main__":
    main()