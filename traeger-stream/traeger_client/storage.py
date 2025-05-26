"""Data persistence module for storing Traeger grill data."""
import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from contextlib import asynccontextmanager

from .models import GrillState, ProbeData


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
                CREATE TABLE IF NOT EXISTS grill_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    grill_id TEXT NOT NULL,
                    grill_name TEXT,
                    is_connected BOOLEAN,
                    firmware_version TEXT,
                    ambient_temperature REAL,
                    grill_temperature REAL,
                    grill_set_temperature REAL,
                    probe_temperature REAL,
                    probe_set_temperature REAL,
                    probe_alarm_fired BOOLEAN,
                    pellet_level INTEGER,
                    fan_level INTEGER,
                    fan_mode TEXT,
                    fire_state TEXT,
                    smoke_level INTEGER,
                    wifi_signal INTEGER,
                    raw_data TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS probe_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    grill_id TEXT NOT NULL,
                    probe_id TEXT NOT NULL,
                    probe_name TEXT,
                    temperature REAL,
                    target_temperature REAL,
                    is_connected BOOLEAN,
                    alarm_fired BOOLEAN,
                    battery_level INTEGER,
                    ambient_temp REAL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
            """)
            
            # Create indexes for better query performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_grill_states_timestamp ON grill_states(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_grill_states_grill_id ON grill_states(grill_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_probe_data_timestamp ON probe_data(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_probe_data_grill_id ON probe_data(grill_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_messages_timestamp ON raw_messages(timestamp)")
            
            conn.commit()
    
    async def save_grill_state(self, state: GrillState) -> None:
        """Save a grill state to the database.
        
        Args:
            state: The grill state to save
        """
        async with self._lock:
            await asyncio.to_thread(self._save_grill_state_sync, state)
    
    def _save_grill_state_sync(self, state: GrillState) -> None:
        """Synchronous method to save grill state."""
        with sqlite3.connect(self.db_path) as conn:
            # Save main grill state
            conn.execute("""
                INSERT INTO grill_states (
                    grill_id, grill_name, is_connected, firmware_version,
                    ambient_temperature, grill_temperature, grill_set_temperature,
                    probe_temperature, probe_set_temperature, probe_alarm_fired,
                    pellet_level, fan_level, fan_mode, fire_state,
                    smoke_level, wifi_signal, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                state.grill_id,
                state.grill_name,
                state.is_connected,
                state.firmware_version,
                state.ambient_temperature,
                state.grill_temperature,
                state.grill_set_temperature,
                state.probe_temperature,
                state.probe_set_temperature,
                state.probe_alarm_fired,
                state.pellet_level,
                state.fan_level,
                state.fan_mode,
                state.fire_state,
                state.smoke_level,
                state.wifi_signal,
                json.dumps(state.raw_data) if state.raw_data else None
            ))
            
            # Save Bluetooth probe data
            for probe in state.probes:
                conn.execute("""
                    INSERT INTO probe_data (
                        grill_id, probe_id, probe_name, temperature,
                        target_temperature, is_connected, alarm_fired,
                        battery_level, ambient_temp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    state.grill_id,
                    probe.id,
                    probe.name,
                    probe.temperature,
                    probe.target_temperature,
                    probe.is_connected,
                    probe.alarm_fired,
                    probe.battery_level,
                    probe.ambient_temp
                ))
            
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
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO raw_messages (topic, payload) VALUES (?, ?)",
                (topic, payload)
            )
            conn.commit()
    
    async def get_grill_states(
        self,
        grill_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve grill states from the database.
        
        Args:
            grill_id: Optional grill ID to filter by
            start_time: Optional start time for filtering
            end_time: Optional end time for filtering
            limit: Maximum number of records to return
            
        Returns:
            List of grill state records
        """
        async with self._lock:
            return await asyncio.to_thread(
                self._get_grill_states_sync, grill_id, start_time, end_time, limit
            )
    
    def _get_grill_states_sync(
        self,
        grill_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Synchronous method to get grill states."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            query = "SELECT * FROM grill_states WHERE 1=1"
            params = []
            
            if grill_id:
                query += " AND grill_id = ?"
                params.append(grill_id)
            
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
            
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    async def get_probe_data(
        self,
        grill_id: Optional[str] = None,
        probe_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve probe data from the database.
        
        Args:
            grill_id: Optional grill ID to filter by
            probe_id: Optional probe ID to filter by
            start_time: Optional start time for filtering
            end_time: Optional end time for filtering
            limit: Maximum number of records to return
            
        Returns:
            List of probe data records
        """
        async with self._lock:
            return await asyncio.to_thread(
                self._get_probe_data_sync, grill_id, probe_id, start_time, end_time, limit
            )
    
    def _get_probe_data_sync(
        self,
        grill_id: Optional[str] = None,
        probe_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Synchronous method to get probe data."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            query = "SELECT * FROM probe_data WHERE 1=1"
            params = []
            
            if grill_id:
                query += " AND grill_id = ?"
                params.append(grill_id)
            
            if probe_id:
                query += " AND probe_id = ?"
                params.append(probe_id)
            
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
            
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    async def export_to_csv(
        self,
        output_path: Path,
        grill_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Tuple[int, int]:
        """Export data to CSV files.
        
        Args:
            output_path: Directory to save CSV files
            grill_id: Optional grill ID to filter by
            start_time: Optional start time for filtering
            end_time: Optional end time for filtering
            
        Returns:
            Tuple of (grill_records_count, probe_records_count)
        """
        import csv
        
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Export grill states
        grill_states = await self.get_grill_states(grill_id, start_time, end_time)
        grill_csv_path = output_path / "grill_states.csv"
        
        if grill_states:
            with open(grill_csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=grill_states[0].keys())
                writer.writeheader()
                writer.writerows(grill_states)
        
        # Export probe data
        probe_data = await self.get_probe_data(grill_id, None, start_time, end_time)
        probe_csv_path = output_path / "probe_data.csv"
        
        if probe_data:
            with open(probe_csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=probe_data[0].keys())
                writer.writeheader()
                writer.writerows(probe_data)
        
        return len(grill_states), len(probe_data)
    
    async def get_latest_state(self, grill_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest state for a specific grill.
        
        Args:
            grill_id: The grill ID
            
        Returns:
            Latest grill state record or None
        """
        states = await self.get_grill_states(grill_id=grill_id, limit=1)
        return states[0] if states else None