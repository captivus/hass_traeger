"""Data persistence module for storing Traeger grill data."""
import asyncio
import sqlite3
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import logging

logger = logging.getLogger(__name__)


class DataStorage:
    """Handles persistent storage of grill data in SQLite."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize the data storage.
        
        Args:
            db_path: Path to SQLite database file. Defaults to ./data/traeger_data.db
        """
        self.db_path = db_path or Path("./data/traeger_data.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()
        self._seen_state_indexes: Set[tuple] = set()  # Cache of (topic, state_index) pairs
        self._init_db()
        self._load_existing_state_indexes()
    
    def _init_db(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            # Create main table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    state_index INTEGER
                )
            """)
            
            # Create indexes for better query performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_messages_timestamp ON raw_messages(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_messages_topic ON raw_messages(topic)")
            
            # Create unique index to prevent duplicates
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_messages_topic_state_index 
                ON raw_messages(topic, state_index)
                WHERE state_index IS NOT NULL
            """)
            
            # Check if state_index column exists (for backwards compatibility)
            cursor = conn.execute("PRAGMA table_info(raw_messages)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'state_index' not in columns:
                logger.info("Migrating database schema - adding state_index column")
                # Add state_index column to existing tables
                conn.execute("ALTER TABLE raw_messages ADD COLUMN state_index INTEGER")
                
                # Populate state_index from existing data
                conn.execute("""
                    UPDATE raw_messages 
                    SET state_index = json_extract(payload, '$.stateIndex')
                    WHERE json_valid(payload) AND state_index IS NULL
                """)
                logger.info("state_index column added and populated")
            
            conn.commit()
    
    def _load_existing_state_indexes(self):
        """Load existing state indexes into memory cache."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT topic, state_index FROM raw_messages WHERE state_index IS NOT NULL"
            )
            for row in cursor:
                self._seen_state_indexes.add((row[0], row[1]))
            logger.info(f"Loaded {len(self._seen_state_indexes)} existing state indexes into cache")
    
    async def save_raw_message(self, topic: str, payload: str) -> None:
        """Save a raw MQTT message.
        
        Args:
            topic: MQTT topic
            payload: Raw message payload
        """
        async with self._lock:
            await asyncio.to_thread(self._save_raw_message_sync, topic, payload)
    
    def _save_raw_message_sync(self, topic: str, payload: str) -> None:
        """Synchronous method to save raw message with deduplication."""
        with self._sync_lock:  # Thread-safe lock for MQTT callback
            conn = None
            try:
                # Extract state_index from payload
                state_index = None
                try:
                    payload_json = json.loads(payload)
                    state_index = payload_json.get('stateIndex')
                except (json.JSONDecodeError, KeyError):
                    logger.warning(f"Could not extract stateIndex from payload")
                
                if state_index is not None:
                    # Check in-memory cache first (very fast)
                    cache_key = (topic, state_index)
                    if cache_key in self._seen_state_indexes:
                        logger.debug(f"Message with stateIndex {state_index} already in cache, skipping")
                        return
                    
                    # Add to cache immediately to prevent concurrent duplicates
                    self._seen_state_indexes.add(cache_key)
                
                conn = sqlite3.connect(self.db_path)
                
                if state_index is not None:
                    # Double-check in database (in case of cache miss)
                    existing = conn.execute(
                        "SELECT id FROM raw_messages WHERE topic = ? AND state_index = ?",
                        (topic, state_index)
                    ).fetchone()
                    
                    if existing:
                        logger.debug(f"Message with stateIndex {state_index} already in DB, skipping")
                        conn.close()
                        return
                    
                    # Insert new message with state_index
                    cursor = conn.execute(
                        """
                        INSERT INTO raw_messages (topic, payload, state_index, timestamp) 
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                        (topic, payload, state_index)
                    )
                    logger.info(f"Saved message with stateIndex {state_index}. Row ID: {cursor.lastrowid}")
                else:
                    # For messages without stateIndex, insert normally
                    cursor = conn.execute(
                        "INSERT INTO raw_messages (topic, payload) VALUES (?, ?)",
                        (topic, payload)
                    )
                    logger.info(f"Saved message without stateIndex. Row ID: {cursor.lastrowid}")
                
                conn.commit()
                
            except sqlite3.IntegrityError as e:
                # This is expected for duplicate state_index values
                logger.debug(f"Duplicate message ignored: {e}")
                # Remove from cache if insert failed
                if state_index is not None:
                    self._seen_state_indexes.discard((topic, state_index))
            except Exception as e:
                logger.error(f"Failed to save message to DB: {e}")
                # Remove from cache if insert failed
                if state_index is not None:
                    self._seen_state_indexes.discard((topic, state_index))
                raise
            finally:
                if conn:
                    conn.close()
    
    async def get_raw_messages(
        self,
        limit: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        topic: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get raw messages from the database.
        
        Args:
            limit: Maximum number of records to return
            start_time: Optional start time for filtering
            end_time: Optional end time for filtering
            topic: Optional topic filter
            
        Returns:
            List of raw message records
        """
        async with self._lock:
            return await asyncio.to_thread(self._get_raw_messages_sync, limit, start_time, end_time, topic)
    
    def _get_raw_messages_sync(
        self,
        limit: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        topic: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Synchronous method to get raw messages."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            query = "SELECT * FROM raw_messages WHERE 1=1"
            params = []
            
            if topic:
                query += " AND topic = ?"
                params.append(topic)
            
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time.isoformat())
            
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time.isoformat())
                
            query += " ORDER BY timestamp DESC"
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            print(f"DEBUG Storage: Executing query: {query}")
            print(f"DEBUG Storage: With params: {params}")
            cursor = conn.execute(query, params)
            results = [dict(row) for row in cursor.fetchall()]
            print(f"DEBUG Storage: Query returned {len(results)} records")
            logger.info(f"Storage query returned {len(results)} records. Query: {query}, Params: {params}")
            return results
    
    async def export_to_csv(
        self,
        output_path: Path,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> int:
        """Export raw messages to CSV file.
        
        Args:
            output_path: Directory to save CSV files
            start_time: Optional start time for filtering
            end_time: Optional end time for filtering
            
        Returns:
            Number of records exported
        """
        import csv
        
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Export raw messages
        raw_messages = await self.get_raw_messages(start_time=start_time, end_time=end_time)
        raw_csv_path = output_path / "raw_messages.csv"
        
        if raw_messages:
            with open(raw_csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=raw_messages[0].keys())
                writer.writeheader()
                writer.writerows(raw_messages)
        
        return len(raw_messages)
    
    async def get_latest_message(self, topic: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get the latest message, optionally filtered by topic.
        
        Args:
            topic: Optional topic filter
            
        Returns:
            Latest message record or None
        """
        messages = await self.get_raw_messages(limit=1, topic=topic)
        return messages[0] if messages else None