# This module has been adjusted to function without Home Assistant integration.

# Number/Timer platform for Traeger.

async def async_setup_entry(client, entry, async_add_devices):
    """Setup Number/Timer platform."""
    grills = client.get_grills()
    for grill in grills:
        grill_id = grill["thingName"]
        async_add_devices([TraegerNumberEntity(client, grill["thingName"], "cook_timer")])

class TraegerNumberEntity:
    """Traeger Number/Timer Value class."""

    def __init__(self, client, grill_id, devname):
        self.client = client
        self.grill_id = grill_id
        self.devname = devname

    # Timer Properties
    def native_value(self):
        if self.client.get_state_for_device(self.grill_id) is None:
            return 0
        end_time = self.client.get_state_for_device(self.grill_id)[f"{self.devname}_end"]
        start_time = self.client.get_state_for_device(self.grill_id)[f"{self.devname}_start"]
        tot_time = (end_time - start_time) / 60
        return tot_time

    def native_min_value(self):
        return 1

    def native_max_value(self):
        return 1440

    def native_unit_of_measurement(self):
        return "min"

    # Timer Methods
    async def async_set_native_value(self, value : float):
        """Set new Timer Val."""
        await self.client.set_timer_sec(self.grill_id, (round(value)*60))
