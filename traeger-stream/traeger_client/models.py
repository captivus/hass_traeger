"""Data models for Traeger grill data."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class GrillState(Enum):
    """Grill operational states."""
    OFFLINE = 0
    IDLE = 1
    STARTUP = 2
    PREHEATING = 3
    IGNITING = 4
    SMOKING = 5
    GRILLING = 6
    COOLING = 7
    SHUTDOWN = 8
    ERROR = 9


class ProbeData(BaseModel):
    """Data from a temperature probe."""
    id: str
    name: str
    temperature: Optional[float] = None
    target_temperature: Optional[float] = None
    is_connected: bool = False
    alarm_fired: bool = False
    battery_level: Optional[int] = None
    ambient_temp: Optional[float] = None
    predicted_time_to_target: Optional[float] = None  # Minutes
    prediction_message: Optional[str] = None  # Explanation when prediction is not possible
    temperature_rate: Optional[float] = None  # °F/minute (1st derivative)
    temperature_acceleration: Optional[float] = None  # °F/minute² (2nd derivative)


class GrillStatus(BaseModel):
    """Complete grill status data."""
    thing_name: str
    friendly_name: str
    connected: bool = False
    state: GrillState = GrillState.OFFLINE
    
    # Temperatures
    grill_temperature: Optional[float] = None
    grill_set_temperature: Optional[float] = None
    ambient_temperature: Optional[float] = None
    
    # Probes
    probes: List[ProbeData] = Field(default_factory=list)
    
    # System info
    fan_speed: Optional[int] = None
    pellet_level: Optional[int] = None
    cook_timer_seconds: Optional[int] = None
    cook_timer_start: Optional[datetime] = None
    
    # Raw data for debugging
    raw_status: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    last_update: datetime = Field(default_factory=datetime.now)
    
    @property
    def cook_time_remaining(self) -> Optional[int]:
        """Calculate remaining cook time in seconds."""
        if self.cook_timer_seconds and self.cook_timer_start:
            elapsed = (datetime.now() - self.cook_timer_start).total_seconds()
            remaining = self.cook_timer_seconds - elapsed
            return max(0, int(remaining))
        return None
    
    @property
    def is_cooking(self) -> bool:
        """Check if grill is actively cooking."""
        return self.state in [
            GrillState.SMOKING,
            GrillState.GRILLING,
            GrillState.PREHEATING,
            GrillState.IGNITING
        ]


class GrillCommand(BaseModel):
    """Commands that can be sent to the grill."""
    thing_name: str
    command: str
    
    @classmethod
    def power_on(cls, thing_name: str) -> "GrillCommand":
        """Create command to power on grill."""
        return cls(thing_name=thing_name, command="17")
    
    @classmethod
    def update_status(cls, thing_name: str) -> "GrillCommand":
        """Create command to request status update."""
        return cls(thing_name=thing_name, command="90")