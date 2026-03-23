"""Config flow for VEC Power Monitor integration."""

import voluptuous as vol
import websockets

from homeassistant import config_entries

from .const import DOMAIN

class VecPowerMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VEC Power Monitor."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            host = user_input["host"]
            # Test WebSocket connection
            try:
                uri = f"ws://{host}/ws"
                async with websockets.connect(uri) as websocket:
                    pass  # Just test connection
            except Exception:
                errors["host"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(title="VEC Power Monitor", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("host"): str,
                    vol.Required("voltage", default=120): vol.All(vol.Coerce(int), vol.Range(min=1)),
                }
            ),
            errors=errors,
        )