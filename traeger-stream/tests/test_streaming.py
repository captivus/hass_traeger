"""Tests for streaming functionality."""

import pytest
from datetime import datetime, timedelta
import pandas as pd
from unittest.mock import MagicMock, AsyncMock

from streaming import StreamBuffer, DataStream
from traeger_client import TraegerClient
from traeger_client.models import GrillStatus, ProbeData, GrillState, GrillCommand


class TestStreamBuffer:
    """Test StreamBuffer class."""
    
    def test_buffer_creation(self):
        """Test creating a stream buffer."""
        buffer = StreamBuffer(max_duration=timedelta(hours=1))
        assert buffer.max_duration == timedelta(hours=1)
        assert len(buffer.data) == 0
    
    def test_add_data(self, mock_grill_status):
        """Test adding data to buffer."""
        buffer = StreamBuffer()
        
        # Add data
        buffer.add(mock_grill_status)
        
        # Verify
        assert len(buffer.data) == 1
        timestamp, status = buffer.data[0]
        assert isinstance(timestamp, datetime)
        assert status == mock_grill_status
    
    def test_buffer_expiration(self, mock_grill_status):
        """Test old data removal."""
        buffer = StreamBuffer(max_duration=timedelta(seconds=1))
        
        # Add old data
        old_time = datetime.now() - timedelta(seconds=2)
        buffer.data.append((old_time, mock_grill_status))
        
        # Add new data
        buffer.add(mock_grill_status)
        
        # Verify old data removed
        assert len(buffer.data) == 1
        assert buffer.data[0][0] > old_time
    
    def test_get_latest(self, mock_grill_status):
        """Test getting latest status for a grill."""
        buffer = StreamBuffer()
        
        # Add multiple statuses
        status1 = GrillStatus(thing_name="GRILL1", friendly_name="Grill 1")
        status2 = GrillStatus(thing_name="GRILL2", friendly_name="Grill 2")
        status3 = GrillStatus(thing_name="GRILL1", friendly_name="Grill 1 Updated")
        
        buffer.add(status1)
        buffer.add(status2)
        buffer.add(status3)
        
        # Test getting latest
        latest = buffer.get_latest("GRILL1")
        assert latest.friendly_name == "Grill 1 Updated"
        
        latest2 = buffer.get_latest("GRILL2")
        assert latest2.friendly_name == "Grill 2"
        
        # Test non-existent grill
        assert buffer.get_latest("GRILL3") is None
    
    def test_get_dataframe(self):
        """Test converting buffer to DataFrame."""
        buffer = StreamBuffer()
        
        # Add data with probes
        now = datetime.now()
        status1 = GrillStatus(
            thing_name="GRILL1",
            friendly_name="Test Grill",
            connected=True,
            state=GrillState.SMOKING,
            grill_temperature=225,
            grill_set_temperature=225,
            ambient_temperature=72,
            fan_speed=3,
            probes=[
                ProbeData(
                    id="p1",
                    name="Probe 1",
                    temperature=165,
                    target_temperature=203
                )
            ]
        )
        
        buffer.add(status1)
        
        # Get DataFrame
        df = buffer.get_dataframe("GRILL1")
        
        # Verify DataFrame structure
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert "timestamp" in df.columns
        assert "grill_temp" in df.columns
        assert "grill_set" in df.columns
        assert "probe_0_temp" in df.columns
        assert "probe_0_target" in df.columns
        
        # Verify values
        row = df.iloc[0]
        assert row["grill_temp"] == 225
        assert row["grill_set"] == 225
        assert row["ambient"] == 72
        assert row["fan_speed"] == 3
        assert row["state"] == "SMOKING"
        assert row["probe_0_temp"] == 165
        assert row["probe_0_target"] == 203
    
    def test_get_dataframe_empty(self):
        """Test getting DataFrame when buffer is empty."""
        buffer = StreamBuffer()
        df = buffer.get_dataframe("GRILL1")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
    
    def test_clear_buffer(self):
        """Test clearing the buffer."""
        buffer = StreamBuffer()
        buffer.add(GrillStatus(thing_name="GRILL1", friendly_name="Test"))
        
        assert len(buffer.data) == 1
        buffer.clear()
        assert len(buffer.data) == 0


class TestDataStream:
    """Test DataStream class."""
    
    @pytest.fixture
    def mock_client(self):
        """Create mock TraegerClient."""
        client = MagicMock(spec=TraegerClient)
        client.add_status_callback = MagicMock()
        client.list_grills = MagicMock(return_value=[
            {"thing_name": "GRILL1", "friendly_name": "Test Grill"}
        ])
        client.send_command = AsyncMock()
        return client
    
    def test_stream_creation(self, mock_client):
        """Test creating a data stream."""
        stream = DataStream(mock_client)
        
        assert stream.client == mock_client
        assert isinstance(stream.buffer, StreamBuffer)
        assert stream._running is False
        
        # Verify client callback registered
        mock_client.add_status_callback.assert_called_once()
    
    def test_status_update_handling(self, mock_client, mock_grill_status):
        """Test handling status updates from client."""
        stream = DataStream(mock_client)
        
        # Get the callback that was registered
        callback = mock_client.add_status_callback.call_args[0][0]
        
        # Add our own callback
        test_callback = MagicMock()
        stream.add_callback(test_callback)
        
        # Simulate status update
        callback(mock_grill_status)
        
        # Verify buffer updated
        latest = stream.buffer.get_latest("TEST_GRILL_001")
        assert latest == mock_grill_status
        
        # Verify our callback called
        test_callback.assert_called_once_with(mock_grill_status)
    
    def test_callback_management(self, mock_client):
        """Test adding and removing callbacks."""
        stream = DataStream(mock_client)
        
        callback1 = MagicMock()
        callback2 = MagicMock()
        
        # Add callbacks
        stream.add_callback(callback1)
        stream.add_callback(callback2)
        assert len(stream._callbacks) == 2
        
        # Remove callback
        stream.remove_callback(callback1)
        assert len(stream._callbacks) == 1
        assert callback2 in stream._callbacks
    
    def test_callback_error_handling(self, mock_client, mock_grill_status):
        """Test error handling in callbacks."""
        stream = DataStream(mock_client)
        
        # Get the registered callback
        callback = mock_client.add_status_callback.call_args[0][0]
        
        # Add callback that raises exception
        bad_callback = MagicMock(side_effect=Exception("Test error"))
        good_callback = MagicMock()
        
        stream.add_callback(bad_callback)
        stream.add_callback(good_callback)
        
        # Simulate status update - should not crash
        callback(mock_grill_status)
        
        # Verify good callback still called despite error
        good_callback.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_streaming(self, mock_client):
        """Test starting the stream."""
        stream = DataStream(mock_client)
        
        # Run start briefly then stop
        async def run_briefly():
            await stream.start()
        
        # Start in background
        import asyncio
        task = asyncio.create_task(run_briefly())
        
        # Let it run briefly
        await asyncio.sleep(0.1)
        
        # Stop it
        stream.stop()
        
        # Wait for task to complete
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            task.cancel()
        
        # Verify initial status requests sent
        assert mock_client.send_command.called
        command_arg = mock_client.send_command.call_args[0][0]
        assert isinstance(command_arg, GrillCommand)
        assert command_arg.command == "90"  # Update status command
    
    def test_get_buffer(self, mock_client):
        """Test getting the buffer."""
        stream = DataStream(mock_client)
        buffer = stream.get_buffer()
        assert isinstance(buffer, StreamBuffer)
        assert buffer == stream.buffer