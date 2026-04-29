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
    DEFAULT_PHONE_CODE,
    APP_CONFIGS, 
    DEFAULT_APP,
    MQTT_PORT,
    MQTT_USERNAME,
    MQTT_PASSWORD,
    DEFAULT_TIMEOUT,
    DEFAULT_COMMAND_DELAY,
    DEFAULT_RETRY_COUNT,
    CONF_PHONE_CODE,
)
from .data_center_manager import get_data_center_manager
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

        # Prepare app list for dropdown
        app_options = {
            code: config["name"] 
            for code, config in APP_CONFIGS.items()
        }

        if user_input is not None:
            try:
                phone_code = user_input.get(CONF_PHONE_CODE, DEFAULT_PHONE_CODE)
                # Remove leading + if present
                phone_code = phone_code.lstrip('+')
                app_type = user_input.get("app_type", DEFAULT_APP)
                
                # Get data center configuration by phone code
                manager = get_data_center_manager(self.hass)
                data_center = await self.hass.async_add_executor_job(
                    manager.get_data_center_by_phone_code, phone_code, self.hass.config.language
                )
                
                if not data_center:
                    _LOGGER.error("No data center found for phone code %s", phone_code)
                    errors["base"] = "no_data_center"
                    return self.async_show_form(
                        step_id="user",
                        data_schema=vol.Schema({
                            vol.Required("app_type", default=DEFAULT_APP): vol.In(app_options),
                            vol.Required(CONF_PHONE_CODE, default=DEFAULT_PHONE_CODE): str,
                            vol.Required(CONF_EMAIL): str,
                            vol.Required(CONF_PASSWORD): str,
                        }),
                        errors=errors,
                    )
                
                app_config = APP_CONFIGS[app_type]

                # Create configuration
                rest_config = RestConfig(
                    base_url=data_center["rest_url"],
                    app_key=app_config["app_key"],
                    app_secret=app_config["app_secret"],
                    package_name=app_config["package_name"],
                    source=app_config["source"],
                    reg_id="",
                    country=data_center.get("country_code", "unknown"),
                    user_agent="okhttp/4.9.1"
                )

                mqtt_config = MQTTConfig(
                    host=data_center["mqtt_host"],
                    port=data_center.get("mqtt_port", MQTT_PORT),
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
                _LOGGER.info("Connecting with app %s, data center %s...", 
                            app_config["name"], data_center["country_name"])
                vacuum = NeatsvorVacuum(config, app_type=app_type)
                await vacuum.initialize()

                # Get device information
                device_mac = vacuum.info.mac if vacuum.info else ""
                device_id = vacuum.info.device_id if vacuum.info else ""

                # Set unique ID
                await self.async_set_unique_id(device_mac)
                self._abort_if_unique_id_configured()

                await vacuum.disconnect()

                # Save configuration
                return self.async_create_entry(
                    title="Neatsvor Vacuum",
                    data={
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_PHONE_CODE: phone_code,
                        "app_type": app_type,
                        "device_mac": device_mac,
                        "device_id": device_id,
                        "rest_url": data_center["rest_url"],
                        "mqtt_host": data_center["mqtt_host"],
                        "mqtt_port": data_center.get("mqtt_port", MQTT_PORT),
                        "country_code": data_center.get("country_code", ""),
                        "country_name": data_center.get("country_name", ""),
                    },
                )

            except Exception as err:
                _LOGGER.error("Connection error: %s", err)
                errors["base"] = "invalid_auth"

        # Simple form with app, phone code, email and password
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("app_type", default=DEFAULT_APP): vol.In(app_options),
                    vol.Required(CONF_PHONE_CODE, default=DEFAULT_PHONE_CODE): str,
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "example_code": "+7 или 7 или 86 или 1",
            }
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
        # Prepare app list for dropdown
        app_options = {
            code: config["name"] 
            for code, config in APP_CONFIGS.items()
        }
        current_app = self.config_entry.data.get("app_type", DEFAULT_APP)
        current_phone_code = self.config_entry.data.get(CONF_PHONE_CODE, DEFAULT_PHONE_CODE)

        if user_input is not None:
            new_phone_code = user_input.get(CONF_PHONE_CODE, current_phone_code)
            new_phone_code = new_phone_code.lstrip('+')
            new_app_type = user_input.get("app_type", current_app)
            
            # Get new data center configuration
            manager = get_data_center_manager(self.hass)
            data_center = await self.hass.async_add_executor_job(
                manager.get_data_center_by_phone_code, new_phone_code, self.hass.config.language
            )
            
            # Update configuration
            new_data = dict(self.config_entry.data)
            new_data[CONF_PHONE_CODE] = new_phone_code
            new_data["app_type"] = new_app_type
            
            if data_center:
                new_data["rest_url"] = data_center["rest_url"]
                new_data["mqtt_host"] = data_center["mqtt_host"]
                new_data["mqtt_port"] = data_center.get("mqtt_port", MQTT_PORT)
                new_data["country_code"] = data_center.get("country_code", "")
                new_data["country_name"] = data_center.get("country_name", "")
            
            # Remove old region key if exists
            new_data.pop("region", None)

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
                    vol.Required("app_type", default=current_app): vol.In(app_options),
                    vol.Required(CONF_PHONE_CODE, default=current_phone_code): str,
                }
            ),
            description_placeholders={
                "device_name": "Neatsvor Vacuum",
                "device_mac": self.config_entry.data.get("device_mac", "Unknown"),
                "email": self.config_entry.data.get(CONF_EMAIL, ""),
            }
        )