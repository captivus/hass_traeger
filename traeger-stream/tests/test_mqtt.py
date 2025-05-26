"""Tests for MQTT functionality."""

import pytest
import json
from unittest.mock import MagicMock, patch, call
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

from traeger_client import TraegerClient
from traeger_client.models import GrillState


class TestMQTT:
    """Test MQTT-related functionality."""
    
    @pytest.fixture
    def client(self):
        """Create a TraegerClient instance."""
        return TraegerClient("test@example.com", "password123")
    
    @pytest.mark.asyncio
    async def test_mqtt_connection(self, client, mock_mqtt_client):
        """Test MQTT connection setup."""
        # Setup
        client.mqtt_url = "wss://mqtt.example.com/mqtt?token=test123"
        client.mqtt_url_expires = 999999999999  # Far future
        client.grills = [{"thingName": "TEST_GRILL_001"}]
        
        with patch('paho.mqtt.client.Client', return_value=mock_mqtt_client):
            # Simulate immediate connection
            def simulate_connect(*args, **kwargs):
                # Trigger the on_connect callback
                client._on_mqtt_connect(mock_mqtt_client, None, None, 0)
            
            mock_mqtt_client.connect.side_effect = simulate_connect
            
            # Test
            await client._connect_mqtt()
            
            # Verify client creation
            assert client.mqtt_client == mock_mqtt_client
            
            # Verify callbacks set
            assert client.mqtt_client.on_connect is not None
            assert client.mqtt_client.on_message is not None
            assert client.mqtt_client.on_disconnect is not None
            
            # Verify TLS setup
            mock_mqtt_client.tls_set_context.assert_called_once()
            
            # Verify WebSocket options
            mock_mqtt_client.ws_set_options.assert_called_once()
            ws_call = mock_mqtt_client.ws_set_options.call_args
            assert "/mqtt?token=test123" in ws_call[1]["path"]
            assert ws_call[1]["headers"]["Host"] == "mqtt.example.com"
            
            # Verify connection
            mock_mqtt_client.connect.assert_called_once_with(
                "mqtt.example.com", 443, keepalive=300
            )
            mock_mqtt_client.loop_start.assert_called_once()
            
            # Verify connected flag
            assert client._mqtt_connected is True
    
    def test_mqtt_on_connect(self, client, mock_mqtt_client):
        """Test MQTT on_connect callback."""
        # Setup
        client.grills = [
            {"thingName": "GRILL1"},
            {"thingName": "GRILL2"}
        ]
        client.mqtt_client = mock_mqtt_client
        
        # Test successful connection
        client._on_mqtt_connect(mock_mqtt_client, None, None, 0)
        
        # Verify
        assert client._mqtt_connected is True
        
        # Verify subscriptions
        expected_calls = [
            call("prod/thing/update/GRILL1"),
            call("prod/thing/update/GRILL2")
        ]
        mock_mqtt_client.subscribe.assert_has_calls(expected_calls)
    
    def test_mqtt_on_disconnect(self, client, mock_mqtt_client):
        """Test MQTT on_disconnect callback."""
        # Setup
        client._mqtt_connected = True
        
        # Test
        client._on_mqtt_disconnect(mock_mqtt_client, None, 1)
        
        # Verify
        assert client._mqtt_connected is False
    
    def test_mqtt_on_message(self, client, mock_raw_status):
        """Test MQTT message handling."""
        # Setup
        client.grills = [{"thingName": "TEST_GRILL_001", "friendlyName": "Test Grill"}]
        callback = MagicMock()
        client.add_status_callback(callback)
        
        # Create mock message
        message = MagicMock()
        message.topic = "prod/thing/update/TEST_GRILL_001"
        message.payload = json.dumps(mock_raw_status)
        
        # Test
        client._on_mqtt_message(None, None, message)
        
        # Verify status parsed and stored
        assert "TEST_GRILL_001" in client._grill_status
        status = client._grill_status["TEST_GRILL_001"]
        assert status.thing_name == "TEST_GRILL_001"
        assert status.state == GrillState.SMOKING
        assert status.grill_temperature == 225
        
        # Verify callback called
        callback.assert_called_once()
        callback_status = callback.call_args[0][0]
        assert callback_status.thing_name == "TEST_GRILL_001"
    
    def test_mqtt_message_parse_error(self, client):
        """Test MQTT message parsing error handling."""
        # Setup
        callback = MagicMock()
        client.add_status_callback(callback)
        
        # Create invalid message
        message = MagicMock()
        message.topic = "prod/thing/update/TEST_GRILL_001"
        message.payload = "invalid json"
        
        # Test - should not raise exception
        client._on_mqtt_message(None, None, message)
        
        # Verify callback not called on error
        callback.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_mqtt_url_refresh(self, client, mock_aiohttp_session, mock_mqtt_url_response):
        """Test MQTT URL refresh when expired."""
        # Setup
        client.session = mock_aiohttp_session
        client.token = "test_token"
        client.token_expires = 999999999999  # Far future
        client.mqtt_url_expires = 0  # Already expired
        
        # Setup mock
        mock_aiohttp_session.post.return_value.json.return_value = mock_mqtt_url_response
        
        # Test
        await client._get_mqtt_url()
        
        # Verify new URL fetched
        assert client.mqtt_url == "wss://mqtt.example.com/mqtt?token=test"
        assert client.mqtt_url_expires > 0
    
    @pytest.mark.asyncio
    async def test_mqtt_connection_timeout(self, client, mock_mqtt_client):
        """Test MQTT connection timeout handling."""
        # Setup
        client.mqtt_url = "wss://mqtt.example.com/mqtt"
        client.mqtt_url_expires = 999999999999
        client._mqtt_connected = False  # Never connects
        
        with patch('paho.mqtt.client.Client', return_value=mock_mqtt_client):
            # Test - should raise timeout exception
            with pytest.raises(Exception, match="MQTT connection timeout"):
                await client._connect_mqtt()
    
    def test_mqtt_websocket_url_parsing(self, client):
        """Test WebSocket URL parsing for MQTT."""
        # Test URL
        test_url = "wss://a1234567890.iot.us-west-2.amazonaws.com/mqtt?X-Amz-Algorithm=AWS4-HMAC-SHA256&param=value"
        
        # Parse like the client does
        parts = urlparse(test_url)
        
        # Verify parsing
        assert parts.scheme == "wss"
        assert parts.netloc == "a1234567890.iot.us-west-2.amazonaws.com"
        assert parts.path == "/mqtt"
        assert "X-Amz-Algorithm" in parts.query
        
        # Verify headers and path construction
        headers = {"Host": parts.netloc}
        path = f"{parts.path}?{parts.query}"
        
        assert headers["Host"] == "a1234567890.iot.us-west-2.amazonaws.com"
        assert path.startswith("/mqtt?X-Amz-Algorithm=")