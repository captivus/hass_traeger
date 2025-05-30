"""Data persistence module for storing Traeger grill data."""
import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
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
        self._init_db()
    
    def _init_db(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
            """)
            
            # Create indexes for better query performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_messages_timestamp ON raw_messages(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_messages_topic ON raw_messages(topic)")
            
            conn.commit()
    
    async def save_raw_message(self, topic: str, payload: str) -> None:
        """Save a raw MQTT message.
        
        Args:
            topic: MQTT topic
            payload: Raw message payload
        """
        async with self._lock:
            await asyncio.to_thread(self._save_raw_message_sync, topic, payload)
    
    def _save_raw_message_sync(self, topic: str, payload: str) -> None:
        """Synchronous method to save raw message."""
        import logging
        logger = logging.getLogger(__name__)
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "INSERT INTO raw_messages (topic, payload) VALUES (?, ?)",
                (topic, payload)
            )
            conn.commit()
            logger.info(f"Successfully saved message to DB. Row ID: {cursor.lastrowid}, DB: {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to save message to DB: {e}")
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