"""Data streaming and buffering for real-time updates."""

import asyncio
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Deque, List, Tuple
import pandas as pd

from traeger_client import TraegerClient, GrillStatus
from traeger_client.models import GrillCommand


class StreamBuffer:
    """Circular buffer for time-series data."""
    
    def __init__(self, max_duration: timedelta = timedelta(hours=2)):
        self.max_duration = max_duration
        self.data: Deque[Tuple[datetime, GrillStatus]] = deque()
        
    def add(self, status: GrillStatus):
        """Add new status to buffer."""
        now = datetime.now()
        self.data.append((now, status))
        
        # Remove old data
        cutoff = now - self.max_duration
        while self.data and self.data[0][0] < cutoff:
            self.data.popleft()
            
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
                    "grill_set": status.grill_set_temperature,
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