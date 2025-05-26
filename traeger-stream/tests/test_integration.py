"""Integration tests for end-to-end functionality."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import json
import gc

from traeger_client import TraegerClient
from traeger_client.models import GrillStatus, GrillState, GrillCommand
from streaming import DataStream


class TestIntegration:
    """Integration tests for complete flow."""
    
    @pytest.mark.asyncio
    async def test_full_connection_flow(
        self,
        mock_auth_response,
        mock_user_data,
        mock_mqtt_url_response,
        mock_raw_status
    ):
        """Test complete connection and data flow."""
        
        # Setup mocks
        with patch('aiohttp.ClientSession') as mock_session_class:
            # Create responses for each call
            auth_response = AsyncMock()
            auth_response.status = 200
            auth_response.json = AsyncMock(return_value=mock_auth_response)
            auth_response.__aenter__ = AsyncMock(return_value=auth_response)
            auth_response.__aexit__ = AsyncMock(return_value=None)
            
            user_response = AsyncMock()
            user_response.status = 200
            user_response.json = AsyncMock(return_value=mock_user_data)
            user_response.__aenter__ = AsyncMock(return_value=user_response)
            user_response.__aexit__ = AsyncMock(return_value=None)
            
            mqtt_response = AsyncMock()
            mqtt_response.status = 200
            mqtt_response.json = AsyncMock(return_value=mock_mqtt_url_response)
            mqtt_response.__aenter__ = AsyncMock(return_value=mqtt_response)
            mqtt_response.__aexit__ = AsyncMock(return_value=None)
            
            # Create mock session
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session
            
            # Configure session methods
            mock_session.post = MagicMock(side_effect=[auth_response, mqtt_response])
            mock_session.get = MagicMock(return_value=user_response)
            mock_session.close = AsyncMock()
            
            # Mock MQTT client
            with patch('paho.mqtt.client.Client') as mock_mqtt_class:
                mock_mqtt = MagicMock()
                mock_mqtt_class.return_value = mock_mqtt
                
                # Create client
                client = TraegerClient("test@example.com", "password123")
                
                # Set up connection callback
                def simulate_connect(*args, **kwargs):
                    client._on_mqtt_connect(mock_mqtt, None, None, 0)
                
                mock_mqtt.connect.side_effect = simulate_connect
                
                # Connect
                await client.connect()
                
                # Verify authentication
                assert client.token == "test_token_123"
                assert client.refresh_token == "test_refresh_token_456"
                
                # Verify grills discovered
                assert len(client.grills) == 1
                assert client.grills[0]["thingName"] == "TEST_GRILL_001"
                
                # Verify MQTT setup
                assert client.mqtt_client is not None
                mock_mqtt.connect.assert_called_once()
                
                # Simulate MQTT connection
                client._on_mqtt_connect(mock_mqtt, None, None, 0)
                assert client._mqtt_connected is True
                
                # Simulate receiving status
                message = MagicMock()
                message.topic = "prod/thing/update/TEST_GRILL_001"
                message.payload = json.dumps(mock_raw_status)
                
                client._on_mqtt_message(mock_mqtt, None, message)
                
                # Verify status parsed
                status = client.get_status("TEST_GRILL_001")
                assert status is not None
                assert status.grill_temperature == 225
                assert status.state == GrillState.SMOKING
                
                # Cleanup
                await client.disconnect()
                mock_session.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_streaming_integration(self, mock_grill_status):
        """Test integration between client and streaming."""
        
        # Create mock client
        mock_client = MagicMock(spec=TraegerClient)
        mock_client.list_grills = MagicMock(return_value=[
            {"thing_name": "TEST_GRILL_001", "friendly_name": "Test Grill"}
        ])
        mock_client.send_command = AsyncMock()
        mock_client.add_status_callback = MagicMock()
        
        # Create stream
        stream = DataStream(mock_client)
        
        # Get the callback that was registered
        client_callback = mock_client.add_status_callback.call_args[0][0]
        
        # Add test callback
        received_statuses = []
        def test_callback(status):
            received_statuses.append(status)
        
        stream.add_callback(test_callback)
        
        # Simulate multiple status updates
        for i in range(5):
            status = GrillStatus(
                thing_name="TEST_GRILL_001",
                friendly_name="Test Grill",
                grill_temperature=220 + i,
                state=GrillState.SMOKING
            )
            client_callback(status)
            await asyncio.sleep(0.01)
        
        # Verify all updates received
        assert len(received_statuses) == 5
        assert received_statuses[-1].grill_temperature == 224
        
        # Verify buffer has all data
        df = stream.buffer.get_dataframe("TEST_GRILL_001")
        assert len(df) == 5
        assert df["grill_temp"].tolist() == [220, 221, 222, 223, 224]
    
    @pytest.mark.asyncio
    async def test_command_flow(self):
        """Test sending commands through the client."""
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            # Setup mock
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session
            mock_session.post = MagicMock(return_value=mock_response)
            
            # Create client with mocked session
            client = TraegerClient("test@example.com", "password123")
            client.session = mock_session
            client.token = "test_token"
            client.token_expires = 999999999999
            
            # Test various commands
            commands = [
                GrillCommand.set_temperature("GRILL1", 250),
                GrillCommand.set_probe_temperature("GRILL1", 165),
                GrillCommand.shutdown("GRILL1"),
                GrillCommand.update_status("GRILL1")
            ]
            
            for cmd in commands:
                await client.send_command(cmd)
            
            # Verify all commands sent
            assert mock_session.post.call_count == 4
            
            # Check command values
            calls = mock_session.post.call_args_list
            assert calls[0][1]["json"]["command"] == "11,250"  # Set temp
            assert calls[1][1]["json"]["command"] == "14,165"  # Set probe
            assert calls[2][1]["json"]["command"] == "17"      # Shutdown
            assert calls[3][1]["json"]["command"] == "90"      # Update
    
    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """Test error handling and recovery."""
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session
            
            # First attempt fails, second succeeds
            mock_response1 = AsyncMock()
            mock_response1.json = AsyncMock(side_effect=Exception("Network error"))
            mock_response1.__aenter__ = AsyncMock(return_value=mock_response1)
            mock_response1.__aexit__ = AsyncMock(return_value=None)
            
            mock_response2 = AsyncMock()
            mock_response2.json = AsyncMock(return_value={
                "AuthenticationResult": {
                    "IdToken": "recovered_token",
                    "RefreshToken": "recovered_refresh",
                    "ExpiresIn": 3600
                }
            })
            mock_response2.__aenter__ = AsyncMock(return_value=mock_response2)
            mock_response2.__aexit__ = AsyncMock(return_value=None)
            
            mock_session.post = MagicMock(side_effect=[mock_response1, mock_response2])
            
            # Create client
            client = TraegerClient("test@example.com", "password123")
            client.session = mock_session
            
            # First auth attempt should fail
            with pytest.raises(Exception):
                await client._authenticate()
            
            # Second attempt should succeed
            await client._authenticate()
            assert client.token == "recovered_token"
    
    @pytest.mark.asyncio
    async def test_concurrent_updates(self):
        """Test handling concurrent status updates."""
        
        # Create mock client
        mock_client = MagicMock(spec=TraegerClient)
        mock_client.add_status_callback = MagicMock()
        
        # Create stream
        stream = DataStream(mock_client)
        client_callback = mock_client.add_status_callback.call_args[0][0]
        
        # Track updates
        update_count = 0
        
        def count_updates(status):
            nonlocal update_count
            update_count += 1
        
        stream.add_callback(count_updates)
        
        # Simulate rapid concurrent updates
        async def send_updates():
            for i in range(10):
                status = GrillStatus(
                    thing_name=f"GRILL{i % 2}",  # Alternate between 2 grills
                    friendly_name=f"Grill {i % 2}",
                    grill_temperature=200 + i
                )
                client_callback(status)
                
        # Run multiple concurrent update streams
        await asyncio.gather(
            send_updates(),
            send_updates(),
            send_updates()
        )
        
        # Verify all updates processed
        assert update_count == 30  # 3 streams × 10 updates each
        
        # Verify both grills have data
        df0 = stream.buffer.get_dataframe("GRILL0")
        df1 = stream.buffer.get_dataframe("GRILL1")
        assert len(df0) > 0
        assert len(df1) > 0