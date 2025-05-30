"""Data streaming and buffering for real-time updates."""

import asyncio
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Deque, List, Tuple
import logging
import pandas as pd

from traeger_client import TraegerClient, GrillStatus
from traeger_client.models import GrillCommand

logger = logging.getLogger(__name__)


class StreamBuffer:
    """Circular buffer for time-series data."""
    
    def __init__(self, max_duration: timedelta = timedelta(hours=48)):
        self.max_duration = max_duration
        self.data: Deque[Tuple[datetime, GrillStatus]] = deque()
        self._last_historical_timestamp: Optional[datetime] = None
        
    def add(self, status: GrillStatus):
        """Add new status to buffer."""
        now = datetime.now()
        
        # Skip duplicates
        if not self.is_duplicate(now, status):
            self.data.append((now, status))
            logger.info(f"Added new data point for {status.thing_name} at {now}")
            
            # Keep data sorted by timestamp if we have historical data
            if self._last_historical_timestamp:
                self.data = deque(sorted(self.data, key=lambda x: x[0]))
            
            # Remove old data
            cutoff = now - self.max_duration
            while self.data and self.data[0][0] < cutoff:
                self.data.popleft()
        else:
            logger.debug(f"Skipped duplicate data for {status.thing_name} at {now}")
            
    def get_dataframe(self, thing_name: str) -> pd.DataFrame:
        """Get data as pandas DataFrame for plotting."""
        if not self.data:
            return pd.DataFrame()
            
        records = []
        for timestamp, status in self.data:
            if status.thing_name == thing_name:
                record = {
                    "timestamp": timestamp,
                    "grill_temp": status.grill_temperature,
                    "grill_set": status.set_temperature,
                    "ambient": status.ambient_temperature,
                    "fan_speed": status.fan_speed,
                    "state": status.state.name,
                    "connected": status.connected
                }
                
                # Add probe data
                for i, probe in enumerate(status.probes):
                    record[f"probe_{i}_temp"] = probe.temperature
                    record[f"probe_{i}_target"] = probe.target_temperature
                    
                records.append(record)
                
        return pd.DataFrame(records)
        
    def get_latest(self, thing_name: str) -> Optional[GrillStatus]:
        """Get latest status for a grill."""
        for _, status in reversed(self.data):
            if status.thing_name == thing_name:
                return status
        return None
        
    def clear(self):
        """Clear all data."""
        self.data.clear()
        self._last_historical_timestamp = None
    
    def load_historical_data(self, historical_data: List[Tuple[datetime, GrillStatus]]):
        """Load historical data into buffer.
        
        Args:
            historical_data: List of (timestamp, GrillStatus) tuples sorted by timestamp
        """
        # Clear existing data
        self.data.clear()
        
        # Add historical data
        now = datetime.now()
        cutoff = now - self.max_duration
        
        for timestamp, status in historical_data:
            # Only add data within our time window
            if timestamp >= cutoff:
                self.data.append((timestamp, status))
                self._last_historical_timestamp = timestamp
        
        # Ensure data is sorted by timestamp
        self.data = deque(sorted(self.data, key=lambda x: x[0]))
    
    def is_duplicate(self, timestamp: datetime, status: GrillStatus) -> bool:
        """Check if this data point would be a duplicate.
        
        Returns True if we already have data for this grill at this timestamp.
        """
        # Check for exact duplicates in recent data (within 2 seconds)
        for ts, existing_status in reversed(self.data):
            if existing_status.thing_name == status.thing_name:
                time_diff = abs((timestamp - ts).total_seconds())
                if time_diff < 2:  # Within 2 seconds
                    return True
                break  # Only check the most recent entry for this grill
        
        return False


class DataStream:
    """Manages streaming data from Traeger client."""
    
    def __init__(self, client: TraegerClient):
        self.client = client
        self.buffer = StreamBuffer()
        self._running = False
        self._callbacks = []
        
        # Register callback with client
        self.client.add_status_callback(self._on_status_update)
        
    def _on_status_update(self, status: GrillStatus):
        """Handle status updates from client."""
        self.buffer.add(status)
        
        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(status)
            except Exception as e:
                print(f"Callback error: {e}")
                
    def add_callback(self, callback):
        """Add callback for status updates."""
        self._callbacks.append(callback)
        
    def remove_callback(self, callback):
        """Remove callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
            
    async def start(self):
        """Start streaming."""
        self._running = True
        
        # Request initial status for all grills
        for grill in self.client.list_grills():
            command = GrillCommand.update_status(grill["thing_name"])
            await self.client.send_command(command)
            
        # Give a moment for initial response, then request again to ensure we get data
        await asyncio.sleep(2)
        for grill in self.client.list_grills():
            command = GrillCommand.update_status(grill["thing_name"])
            await self.client.send_command(command)
            
        # Keep connection alive
        while self._running:
            await asyncio.sleep(30)
            
            # Refresh status periodically
            for grill in self.client.list_grills():
                if self._running:
                    command = GrillCommand.update_status(grill["thing_name"])
                    await self.client.send_command(command)
                    
    def stop(self):
        """Stop streaming."""
        self._running = False
        
    def get_buffer(self) -> StreamBuffer:
        """Get the data buffer."""
        return self.buffer