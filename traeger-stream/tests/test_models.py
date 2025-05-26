"""Tests for data models."""

import pytest
from datetime import datetime, timedelta

from traeger_client.models import (
    GrillStatus, ProbeData, GrillState, GrillCommand
)


class TestProbeData:
    """Test ProbeData model."""
    
    def test_probe_data_creation(self):
        """Test creating ProbeData with all fields."""
        probe = ProbeData(
            id="probe1",
            name="Main Probe",
            temperature=165.5,
            target_temperature=203.0,
            is_connected=True,
            alarm_fired=False
        )
        
        assert probe.id == "probe1"
        assert probe.name == "Main Probe"
        assert probe.temperature == 165.5
        assert probe.target_temperature == 203.0
        assert probe.is_connected is True
        assert probe.alarm_fired is False
    
    def test_probe_data_optional_fields(self):
        """Test ProbeData with optional fields."""
        probe = ProbeData(
            id="probe2",
            name="Probe 2"
        )
        
        assert probe.temperature is None
        assert probe.target_temperature is None
        assert probe.is_connected is False
        assert probe.alarm_fired is False


class TestGrillStatus:
    """Test GrillStatus model."""
    
    def test_grill_status_creation(self, mock_grill_status):
        """Test creating GrillStatus."""
        assert mock_grill_status.thing_name == "TEST_GRILL_001"
        assert mock_grill_status.friendly_name == "Test Grill"
        assert mock_grill_status.connected is True
        assert mock_grill_status.state == GrillState.SMOKING
        assert mock_grill_status.grill_temperature == 225.0
        assert len(mock_grill_status.probes) == 1
    
    def test_is_cooking_property(self):
        """Test is_cooking property for different states."""
        status = GrillStatus(
            thing_name="test",
            friendly_name="Test"
        )
        
        # Not cooking states
        for state in [GrillState.OFFLINE, GrillState.IDLE, GrillState.COOLING, GrillState.SHUTDOWN]:
            status.state = state
            assert status.is_cooking is False
        
        # Cooking states
        for state in [GrillState.SMOKING, GrillState.GRILLING, GrillState.PREHEATING, GrillState.IGNITING]:
            status.state = state
            assert status.is_cooking is True
    
    def test_cook_time_remaining(self):
        """Test cook_time_remaining calculation."""
        now = datetime.now()
        
        # Test with timer set
        status = GrillStatus(
            thing_name="test",
            friendly_name="Test",
            cook_timer_seconds=3600,  # 1 hour
            cook_timer_start=now - timedelta(minutes=30)  # Started 30 min ago
        )
        
        remaining = status.cook_time_remaining
        assert remaining is not None
        assert 1790 <= remaining <= 1810  # ~30 minutes remaining (with some tolerance)
        
        # Test without timer
        status2 = GrillStatus(
            thing_name="test",
            friendly_name="Test"
        )
        assert status2.cook_time_remaining is None
        
        # Test expired timer
        status3 = GrillStatus(
            thing_name="test",
            friendly_name="Test",
            cook_timer_seconds=3600,
            cook_timer_start=now - timedelta(hours=2)  # Started 2 hours ago
        )
        assert status3.cook_time_remaining == 0


class TestGrillCommand:
    """Test GrillCommand model."""
    
    def test_set_temperature_command(self):
        """Test creating set temperature command."""
        cmd = GrillCommand.set_temperature("grill1", 225)
        assert cmd.thing_name == "grill1"
        assert cmd.command == "11,225"
    
    def test_set_probe_temperature_command(self):
        """Test creating set probe temperature command."""
        cmd = GrillCommand.set_probe_temperature("grill1", 165)
        assert cmd.thing_name == "grill1"
        assert cmd.command == "14,165"
    
    def test_power_on_command(self):
        """Test creating power on command."""
        cmd = GrillCommand.power_on("grill1")
        assert cmd.thing_name == "grill1"
        assert cmd.command == "17"
    
    def test_shutdown_command(self):
        """Test creating shutdown command."""
        cmd = GrillCommand.shutdown("grill1")
        assert cmd.thing_name == "grill1"
        assert cmd.command == "17"
    
    def test_update_status_command(self):
        """Test creating update status command."""
        cmd = GrillCommand.update_status("grill1")
        assert cmd.thing_name == "grill1"
        assert cmd.command == "90"


class TestGrillState:
    """Test GrillState enum."""
    
    def test_grill_states(self):
        """Test all grill states are defined."""
        assert GrillState.OFFLINE.value == 0
        assert GrillState.IDLE.value == 1
        assert GrillState.STARTUP.value == 2
        assert GrillState.PREHEATING.value == 3
        assert GrillState.IGNITING.value == 4
        assert GrillState.SMOKING.value == 5
        assert GrillState.GRILLING.value == 6
        assert GrillState.COOLING.value == 7
        assert GrillState.SHUTDOWN.value == 8
        assert GrillState.ERROR.value == 9
    
    def test_state_name(self):
        """Test state name property."""
        assert GrillState.SMOKING.name == "SMOKING"
        assert GrillState.IDLE.name == "IDLE"