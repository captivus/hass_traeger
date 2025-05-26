"""Shared test fixtures and configuration."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from traeger_client.models import GrillStatus, ProbeData, GrillState


@pytest.fixture
def mock_grill_status():
    """Create a mock GrillStatus object."""
    return GrillStatus(
        thing_name="TEST_GRILL_001",
        friendly_name="Test Grill",
        connected=True,
        state=GrillState.SMOKING,
        grill_temperature=225.0,
        grill_set_temperature=225.0,
        ambient_temperature=72.0,
        probes=[
            ProbeData(
                id="probe1",
                name="Probe 1",
                temperature=165.0,
                target_temperature=203.0,
                is_connected=True,
                alarm_fired=False
            )
        ],
        fan_speed=3,
        pellet_level=75,
        cook_timer_seconds=3600,
        last_update=datetime.now()
    )


@pytest.fixture
def mock_raw_status():
    """Create mock raw status data from MQTT."""
    return {
        "thingName": "TEST_GRILL_001",
        "status": {
            "connected": True,
            "system_status": 5,  # SMOKING
            "grill": 225,
            "set": 225,
            "ambient": 72,
            "fan_speed": 3,
            "pellet_level": 75,
            "cook_timer_remaining": 3600,
            "acc": [
                {
                    "type": "probe",
                    "uuid": "probe1",
                    "name": "Probe 1",
                    "temperature": 165,
                    "alarm_set": 203,
                    "connected": True,
                    "alarm_fired": False
                }
            ]
        }
    }


@pytest.fixture
def mock_auth_response():
    """Mock successful authentication response."""
    return {
        "AuthenticationResult": {
            "IdToken": "test_token_123",
            "RefreshToken": "test_refresh_token_456",
            "ExpiresIn": 3600
        }
    }


@pytest.fixture
def mock_user_data():
    """Mock user data response."""
    return {
        "things": [
            {
                "thingName": "TEST_GRILL_001",
                "friendlyName": "Test Grill"
            }
        ]
    }


@pytest.fixture
def mock_mqtt_url_response():
    """Mock MQTT URL response."""
    return {
        "signedUrl": "wss://mqtt.example.com/mqtt?token=test",
        "expirationSeconds": 3600
    }


@pytest.fixture
def mock_aiohttp_session():
    """Create a mock aiohttp session."""
    session = AsyncMock()
    
    # Mock response object
    response = AsyncMock()
    response.status = 200
    response.json = AsyncMock()
    response.text = AsyncMock()
    response.read = AsyncMock()
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    
    # Configure session methods to return context managers
    session.post = MagicMock(return_value=response)
    session.get = MagicMock(return_value=response)
    session.close = AsyncMock()
    
    return session


@pytest.fixture
def mock_mqtt_client():
    """Create a mock MQTT client."""
    client = MagicMock()
    client.connect = MagicMock()
    client.disconnect = MagicMock()
    client.loop_start = MagicMock()
    client.loop_stop = MagicMock()
    client.subscribe = MagicMock()
    client.on_connect = None
    client.on_message = None
    client.on_disconnect = None
    client.ws_set_options = MagicMock()
    client.tls_set_context = MagicMock()
    
    return client