"""Tests for TraegerClient."""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, call
import json

from traeger_client import TraegerClient
from traeger_client.models import GrillStatus, GrillState, GrillCommand


class TestTraegerClient:
    """Test TraegerClient class."""
    
    @pytest.fixture
    def client(self):
        """Create a TraegerClient instance."""
        return TraegerClient("test@example.com", "password123")
    
    @pytest.mark.asyncio
    async def test_authentication(self, client, mock_aiohttp_session, mock_auth_response):
        """Test successful authentication."""
        # Setup mock
        mock_aiohttp_session.post.return_value.json.return_value = mock_auth_response
        client.session = mock_aiohttp_session
        
        # Test
        await client._authenticate()
        
        # Verify
        assert client.token == "test_token_123"
        assert client.refresh_token == "test_refresh_token_456"
        assert client.token_expires > time.time()
        
        # Check API call
        mock_aiohttp_session.post.assert_called_once()
        call_args = mock_aiohttp_session.post.call_args
        assert "cognito-idp.us-west-2.amazonaws.com" in call_args[0][0]
        assert call_args[1]["json"]["AuthFlow"] == "USER_PASSWORD_AUTH"
        assert call_args[1]["json"]["AuthParameters"]["USERNAME"] == "test@example.com"
        assert call_args[1]["json"]["AuthParameters"]["PASSWORD"] == "password123"
    
    @pytest.mark.asyncio
    async def test_authentication_failure(self, client, mock_aiohttp_session):
        """Test authentication failure."""
        # Setup mock
        mock_aiohttp_session.post.return_value.json.return_value = {
            "error": "Invalid credentials"
        }
        client.session = mock_aiohttp_session
        
        # Test
        with pytest.raises(Exception, match="Authentication failed"):
            await client._authenticate()
    
    @pytest.mark.asyncio
    async def test_token_refresh(self, client, mock_aiohttp_session, mock_auth_response):
        """Test token refresh."""
        # Setup initial state
        client.session = mock_aiohttp_session
        client.token = "old_token"
        client.refresh_token = "test_refresh_token"
        client.token_expires = time.time() + 30  # Expires in 30 seconds
        
        # Setup mock
        mock_aiohttp_session.post.return_value.json.return_value = {
            "AuthenticationResult": {
                "IdToken": "new_token_123",
                "ExpiresIn": 3600
            }
        }
        
        # Test
        await client._refresh_auth()
        
        # Verify
        assert client.token == "new_token_123"
        assert client.token_expires > time.time() + 3500
        
        # Check API call
        call_args = mock_aiohttp_session.post.call_args
        assert call_args[1]["json"]["AuthFlow"] == "REFRESH_TOKEN_AUTH"
        assert call_args[1]["json"]["AuthParameters"]["REFRESH_TOKEN"] == "test_refresh_token"
    
    @pytest.mark.asyncio
    async def test_discover_grills(self, client, mock_aiohttp_session, mock_user_data):
        """Test grill discovery."""
        # Setup
        client.session = mock_aiohttp_session
        client.token = "test_token"
        client.token_expires = time.time() + 3600
        
        # Setup mock
        mock_aiohttp_session.get.return_value.json.return_value = mock_user_data
        
        # Test
        await client._discover_grills()
        
        # Verify
        assert len(client.grills) == 1
        assert client.grills[0]["thingName"] == "TEST_GRILL_001"
        assert client.grills[0]["friendlyName"] == "Test Grill"
        
        # Check API call
        mock_aiohttp_session.get.assert_called_once()
        call_args = mock_aiohttp_session.get.call_args
        assert "users/self" in call_args[0][0]
        assert call_args[1]["headers"]["authorization"] == "test_token"
    
    @pytest.mark.asyncio
    async def test_get_mqtt_url(self, client, mock_aiohttp_session, mock_mqtt_url_response):
        """Test getting MQTT URL."""
        # Setup
        client.session = mock_aiohttp_session
        client.token = "test_token"
        client.token_expires = time.time() + 3600
        
        # Setup mock
        mock_aiohttp_session.post.return_value.json.return_value = mock_mqtt_url_response
        
        # Test
        await client._get_mqtt_url()
        
        # Verify
        assert client.mqtt_url == "wss://mqtt.example.com/mqtt?token=test"
        assert client.mqtt_url_expires > time.time()
        
        # Check API call
        call_args = mock_aiohttp_session.post.call_args
        assert "mqtt-connections" in call_args[0][0]
        assert call_args[1]["headers"]["Authorization"] == "test_token"
    
    @pytest.mark.asyncio
    async def test_send_command(self, client, mock_aiohttp_session):
        """Test sending command to grill."""
        # Setup
        client.session = mock_aiohttp_session
        client.token = "test_token"
        client.token_expires = time.time() + 3600
        
        # Setup mock
        mock_aiohttp_session.post.return_value.status = 200
        
        # Test
        command = GrillCommand.set_temperature("TEST_GRILL_001", 225)
        await client.send_command(command)
        
        # Check API call
        call_args = mock_aiohttp_session.post.call_args
        assert "things/TEST_GRILL_001/commands" in call_args[0][0]
        assert call_args[1]["json"]["command"] == "11,225"
        assert call_args[1]["headers"]["Authorization"] == "test_token"
    
    @pytest.mark.asyncio
    async def test_send_command_failure(self, client, mock_aiohttp_session):
        """Test command failure handling."""
        # Setup
        client.session = mock_aiohttp_session
        client.token = "test_token"
        client.token_expires = time.time() + 3600
        
        # Setup mock
        mock_aiohttp_session.post.return_value.status = 400
        mock_aiohttp_session.post.return_value.text.return_value = "Bad request"
        
        # Test
        command = GrillCommand.set_temperature("TEST_GRILL_001", 225)
        with pytest.raises(Exception, match="Command failed: 400"):
            await client.send_command(command)
    
    def test_parse_status(self, client, mock_raw_status):
        """Test parsing raw status data."""
        # Setup
        client.grills = [{"thingName": "TEST_GRILL_001", "friendlyName": "Test Grill"}]
        
        # Test
        status = client._parse_status("TEST_GRILL_001", mock_raw_status)
        
        # Verify
        assert isinstance(status, GrillStatus)
        assert status.thing_name == "TEST_GRILL_001"
        assert status.friendly_name == "Test Grill"
        assert status.connected is True
        assert status.state == GrillState.SMOKING
        assert status.grill_temperature == 225
        assert status.grill_set_temperature == 225
        assert status.ambient_temperature == 72
        assert status.fan_speed == 3
        assert status.pellet_level == 75
        assert len(status.probes) == 1
        assert status.probes[0].temperature == 165
    
    def test_status_callbacks(self, client, mock_grill_status):
        """Test status callback management."""
        # Create mock callback
        callback = MagicMock()
        
        # Add callback
        client.add_status_callback(callback)
        assert callback in client._status_callbacks
        
        # Trigger callback
        client._grill_status["TEST_GRILL_001"] = mock_grill_status
        for cb in client._status_callbacks:
            cb(mock_grill_status)
        
        # Verify callback was called
        callback.assert_called_once_with(mock_grill_status)
        
        # Remove callback
        client.remove_status_callback(callback)
        assert callback not in client._status_callbacks
    
    def test_list_grills(self, client):
        """Test listing grills."""
        # Setup
        client.grills = [
            {"thingName": "GRILL1", "friendlyName": "Backyard Grill"},
            {"thingName": "GRILL2", "friendlyName": "Garage Grill"}
        ]
        
        # Test
        grills = client.list_grills()
        
        # Verify
        assert len(grills) == 2
        assert grills[0]["thing_name"] == "GRILL1"
        assert grills[0]["friendly_name"] == "Backyard Grill"
        assert grills[1]["thing_name"] == "GRILL2"
        assert grills[1]["friendly_name"] == "Garage Grill"
    
    def test_get_status(self, client, mock_grill_status):
        """Test getting status for specific grill."""
        # Setup
        client._grill_status["TEST_GRILL_001"] = mock_grill_status
        
        # Test existing grill
        status = client.get_status("TEST_GRILL_001")
        assert status == mock_grill_status
        
        # Test non-existent grill
        status = client.get_status("UNKNOWN_GRILL")
        assert status is None
    
    def test_get_all_status(self, client, mock_grill_status):
        """Test getting all grill statuses."""
        # Setup
        client._grill_status["TEST_GRILL_001"] = mock_grill_status
        
        # Test
        all_status = client.get_all_status()
        
        # Verify
        assert len(all_status) == 1
        assert "TEST_GRILL_001" in all_status
        assert all_status["TEST_GRILL_001"] == mock_grill_status