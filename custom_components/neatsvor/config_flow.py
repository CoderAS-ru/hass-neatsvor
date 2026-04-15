"""Config flow for Neatsvor integration."""

import logging
from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN, 
    COUNTRIES, 
    DEFAULT_COUNTRY, 
    APP_CONFIGS, 
    DEFAULT_APP,
    MQTT_PORT,
    MQTT_USERNAME,
    MQTT_PASSWORD,
    DEFAULT_TIMEOUT,
    DEFAULT_COMMAND_DELAY,
    DEFAULT_RETRY_COUNT
)
from custom_components.neatsvor.liboshome.config import NeatsvorConfig, RestConfig, MQTTConfig, Credentials, DeviceConfig
from custom_components.neatsvor.liboshome.device.vacuum import NeatsvorVacuum

_LOGGER = logging.getLogger(__name__)


class NeatsvorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Neatsvor."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        # Options for country selection
        country_options = {code: data["name"] for code, data in COUNTRIES.items()}
        
        # Options for app selection
        app_options = {code: config["name"] for code, config in APP_CONFIGS.items()}

        if user_input is not None:
            try:
                region = user_input.get("region", DEFAULT_COUNTRY)
                app_type = user_input.get("app_type", DEFAULT_APP)
                country_data = COUNTRIES[region]
                app_config = APP_CONFIGS[app_type]

                # Create configuration with the selected region and app
                rest_config = RestConfig(
                    base_url=country_data["rest_url"],
                    app_key=app_config["app_key"],
                    app_secret=app_config["app_secret"],
                    package_name=app_config["package_name"],
                    source=app_config["source"],
                    reg_id="",
                    country=region,
                    user_agent="okhttp/4.9.1"
                )

                mqtt_config = MQTTConfig(
                    host=country_data["mqtt_host"],
                    port=MQTT_PORT,
                    username=MQTT_USERNAME,
                    password=MQTT_PASSWORD
                )

                credentials = Credentials(
                    email=user_input[CONF_EMAIL],
                    password=user_input[CONF_PASSWORD]
                )

                device_config = DeviceConfig(
                    default_timeout=DEFAULT_TIMEOUT,
                    command_delay=DEFAULT_COMMAND_DELAY,
                    retry_count=DEFAULT_RETRY_COUNT
                )

                config = NeatsvorConfig(
                    rest=rest_config,
                    mqtt=mqtt_config,
                    credentials=credentials,
                    device=device_config
                )

                # Try to connect
                _LOGGER.info("Connecting to BlackVision (%s) using %s...", region, app_config["name"])
                vacuum = NeatsvorVacuum(config, app_type=app_type)
                await vacuum.initialize()

                # Get device information
                device_mac = vacuum.info.mac if vacuum.info else ""
                device_id = vacuum.info.device_id if vacuum.info else ""

                # Set unique ID
                await self.async_set_unique_id(device_mac)
                self._abort_if_unique_id_configured()

                await vacuum.disconnect()

                # Save the selected region and app in configuration data
                return self.async_create_entry(
                    title="Neatsvor Vacuum",
                    data={
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        "region": region,
                        "app_type": app_type,
                        "device_mac": device_mac,
                        "device_id": device_id,
                    },
                )

            except Exception as err:
                _LOGGER.error("Connection error: %s", err)
                errors["base"] = "invalid_auth"

        # Show form with region and app selection
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("region", default=DEFAULT_COUNTRY): vol.In(country_options),
                    vol.Required("app_type", default=DEFAULT_APP): vol.In(app_options),
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return NeatsvorOptionsFlow(config_entry)


class NeatsvorOptionsFlow(config_entries.OptionsFlow):
    """Handle Neatsvor options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage the options."""
        # Options for country selection
        country_options = {code: data["name"] for code, data in COUNTRIES.items()}
        current_region = self.config_entry.data.get("region", DEFAULT_COUNTRY)
        
        # Options for app selection
        app_options = {code: config["name"] for code, config in APP_CONFIGS.items()}
        current_app = self.config_entry.data.get("app_type", DEFAULT_APP)

        if user_input is not None:
            # Update configuration
            new_data = dict(self.config_entry.data)
            new_data["region"] = user_input.get("region", current_region)
            new_data["app_type"] = user_input.get("app_type", current_app)

            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )

            # Request reload
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)

            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("region", default=current_region): vol.In(country_options),
                    vol.Required("app_type", default=current_app): vol.In(app_options),
                }
            ),
            description_placeholders={
                "device_name": "Neatsvor Vacuum",
                "device_mac": self.config_entry.data.get("device_mac", "Unknown"),
                "email": self.config_entry.data.get(CONF_EMAIL, ""),
            }
        )