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
        self._lock = None  # Will be created when needed
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
            
            # Create ML prediction data table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ml_prediction_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,  -- UTC timestamp
                    grill_id TEXT NOT NULL,
                    cook_id TEXT NOT NULL,
                    probe_id TEXT NOT NULL,
                    -- Features
                    probe_temp REAL,
                    probe_target REAL,
                    grill_temp REAL,
                    grill_set REAL,
                    ambient_temp REAL,
                    minutes_elapsed REAL,
                    grill_probe_diff REAL,
                    probe_target_diff REAL,
                    probe_rate REAL,
                    -- Prediction
                    predicted_minutes REAL,
                    prediction_timestamp TEXT,  -- UTC timestamp
                    model_version TEXT,
                    -- Ground truth (updated when target reached)
                    actual_minutes REAL,
                    target_reached_timestamp TEXT  -- UTC timestamp
                )
            """)
            
            # Create indexes for ML table
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ml_prediction_cook ON ml_prediction_data(cook_id, probe_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ml_prediction_timestamp ON ml_prediction_data(timestamp)")
            
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
    
    def _get_lock(self):
        """Get or create the async lock for the current event loop."""
        try:
            # Try to get the current event loop
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running
            return None
            
        # Create new lock if needed or if bound to different loop
        if self._lock is None:
            self._lock = asyncio.Lock()
        else:
            # Check if the lock is bound to the current event loop
            try:
                # Try to access the lock's loop
                lock_loop = self._lock._loop
                if lock_loop is not loop:
                    # Lock is bound to a different event loop, create a new one
                    self._lock = asyncio.Lock()
            except AttributeError:
                # If we can't access the loop, create a new lock to be safe
                self._lock = asyncio.Lock()
        
        return self._lock
    
    async def save_raw_message(self, topic: str, payload: str) -> None:
        """Save a raw MQTT message.
        
        Args:
            topic: MQTT topic
            payload: Raw message payload
        """
        lock = self._get_lock()
        if lock is None:
            # No async context, use sync method directly
            self._save_raw_message_sync(topic, payload)
            return
        async with lock:
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
        lock = self._get_lock()
        if lock is None:
            raise RuntimeError("No event loop available")
        async with lock:
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
    
    async def save_ml_data_point(self, data: Dict[str, Any]) -> None:
        """Save ML feature data point to database.
        
        Args:
            data: Dictionary containing all feature data and predictions
        """
        lock = self._get_lock()
        if lock is None:
            raise RuntimeError("No event loop available")
        async with lock:
            await asyncio.to_thread(self._save_ml_data_point_sync, data)
    
    def _save_ml_data_point_sync(self, data: Dict[str, Any]) -> None:
        """Synchronous method to save ML data point."""
        with self._sync_lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT INTO ml_prediction_data (
                            timestamp, grill_id, cook_id, probe_id,
                            probe_temp, probe_target, grill_temp, grill_set,
                            ambient_temp, minutes_elapsed, grill_probe_diff,
                            probe_target_diff, probe_rate,
                            predicted_minutes, prediction_timestamp, model_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data['timestamp'],
                        data['grill_id'],
                        data['cook_id'],
                        data['probe_id'],
                        data['probe_temp'],
                        data['probe_target'],
                        data['grill_temp'],
                        data['grill_set'],
                        data['ambient_temp'],
                        data.get('minutes_elapsed', 0),
                        data.get('grill_probe_diff', 0),
                        data.get('probe_target_diff', 0),
                        data.get('probe_rate', 0),
                        data.get('predicted_minutes'),
                        data.get('prediction_timestamp'),
                        data.get('model_version', '1.0')
                    ))
                    conn.commit()
            except Exception as e:
                logger.error(f"Failed to save ML data point: {e}")
    
    async def get_ml_data_for_cook(self, cook_id: str, probe_id: str) -> List[Dict[str, Any]]:
        """Get ML data points for a specific cook and probe.
        
        Args:
            cook_id: Cook session ID
            probe_id: Probe identifier
            
        Returns:
            List of ML data points ordered by timestamp
        """
        lock = self._get_lock()
        if lock is None:
            raise RuntimeError("No event loop available")
        async with lock:
            return await asyncio.to_thread(self._get_ml_data_for_cook_sync, cook_id, probe_id)
    
    def _get_ml_data_for_cook_sync(self, cook_id: str, probe_id: str) -> List[Dict[str, Any]]:
        """Synchronous method to get ML data."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM ml_prediction_data
                WHERE cook_id = ? AND probe_id = ?
                ORDER BY timestamp ASC
            """, (cook_id, probe_id))
            return [dict(row) for row in cursor.fetchall()]
    
    async def update_ml_ground_truth(self, cook_id: str, probe_id: str, 
                                   actual_minutes: float, target_reached_timestamp: str) -> None:
        """Update ML predictions with ground truth when target is reached.
        
        Args:
            cook_id: Cook session ID
            probe_id: Probe identifier
            actual_minutes: Actual minutes it took to reach target
            target_reached_timestamp: UTC timestamp when target was reached
        """
        lock = self._get_lock()
        if lock is None:
            raise RuntimeError("No event loop available")
        async with lock:
            await asyncio.to_thread(
                self._update_ml_ground_truth_sync, 
                cook_id, probe_id, actual_minutes, target_reached_timestamp
            )
    
    def _update_ml_ground_truth_sync(self, cook_id: str, probe_id: str,
                                    actual_minutes: float, target_reached_timestamp: str) -> None:
        """Synchronous method to update ground truth."""
        with self._sync_lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    # Update all predictions for this cook/probe with actual time
                    conn.execute("""
                        UPDATE ml_prediction_data
                        SET actual_minutes = ?,
                            target_reached_timestamp = ?
                        WHERE cook_id = ? AND probe_id = ?
                        AND actual_minutes IS NULL
                    """, (actual_minutes, target_reached_timestamp, cook_id, probe_id))
                    
                    updated = conn.total_changes
                    conn.commit()
                    
                    if updated > 0:
                        logger.info(f"Updated {updated} ML predictions with ground truth for cook {cook_id}, probe {probe_id}")
            except Exception as e:
                logger.error(f"Failed to update ML ground truth: {e}")
    
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