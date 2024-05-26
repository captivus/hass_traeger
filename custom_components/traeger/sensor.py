# Sensor platform for Traeger interactions without Home Assistant integration.

# The following code has been adjusted to function independently from Home Assistant.

class TraegerBaseSensor:

    def __init__(self, grill_id, friendly_name, value):
        self.grill_id = grill_id
        self.value = value
        self.friendly_name = friendly_name

    @property
    def name(self):
        """Return the name of the sensor"""
        return f"{self.grill_id} {self.friendly_name}"

    @property
    def unique_id(self):
        return f"{self.grill_id}_{self.value}"

    @property
    def state(self):
        raise NotImplementedError

class ValueTemperature(TraegerBaseSensor):
    """Temperature Value class."""

    def __init__(self, grill_id, friendly_name, value, units):
        super().__init__(grill_id, friendly_name, value)
        self.units = units

    @property
    def state(self):
        # Implementation to retrieve temperature
        pass

    @property
    def unit_of_measurement(self):
        return self.units

class PelletSensor(TraegerBaseSensor):
    """Pellet Sensor class."""

    @property
    def state(self):
        # Implementation to retrieve pellet level
        pass

    @property
    def unit_of_measurement(self):
        return "%"

class GrillTimer(TraegerBaseSensor):
    """Timer class."""

    @property
    def state(self):
        # Implementation to retrieve timer value
        pass

    @property
    def unit_of_measurement(self):
        return "sec"

class GrillState(TraegerBaseSensor):
    """Grill State class."""

    @property
    def state(self):
        # Implementation to retrieve grill state
        pass

class HeatingState(TraegerBaseSensor):
    """Heating State class."""

    def __init__(self, grill_id, friendly_name, value, previous_state=None):
        super().__init__(grill_id, friendly_name, value)
        self.previous_state = previous_state

    @property
    def state(self):
        # Implementation to retrieve heating state
        pass

class ProbeState(TraegerBaseSensor):

    def __init__(self, grill_id, sensor_id):
        super().__init__(grill_id, f"Probe State {sensor_id}", f"probe_state_{sensor_id}")
        self.sensor_id = sensor_id

    @property
    def state(self):
        # Implementation to retrieve probe state
        pass
