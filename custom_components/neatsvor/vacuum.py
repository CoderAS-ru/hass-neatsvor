"""Neatsvor vacuum platform."""

import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumEntityFeature,
    VacuumActivity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SUCTION_MAP,
    SUCTION_MAP_RU,
    get_localized_status,
    get_localized_fan_speed,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neatsvor vacuum platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NeatsvorVacuum(coordinator)])


class NeatsvorVacuum(CoordinatorEntity, StateVacuumEntity):
    """Neatsvor vacuum entity."""

    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_vacuum"
    _attr_device_info = None  # Will be set in __init__
    _attr_translation_key = "vacuum"  # This will look for entity.vacuum.neatsvor_vacuum.name

    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info

        # Basic features
        self._attr_supported_features = (
            VacuumEntityFeature.START
            | VacuumEntityFeature.PAUSE
            | VacuumEntityFeature.STOP
            | VacuumEntityFeature.RETURN_HOME
            | VacuumEntityFeature.BATTERY
            | VacuumEntityFeature.STATUS
            | VacuumEntityFeature.FAN_SPEED
            | VacuumEntityFeature.LOCATE
            | VacuumEntityFeature.SEND_COMMAND
        )

        # Initialize dynamic features
        self._init_dynamic_features()

    def _init_dynamic_features(self):
        """Initialize dynamic features from DP schema."""
        self._attr_fan_speed_list = ["quiet", "normal", "strong", "max"]

        if not self.coordinator or not self.coordinator.vacuum:
            return

        dp_manager = self.coordinator.vacuum.dp_manager
        if not dp_manager:
            return

        fan_dp = dp_manager.get_by_code('fan')
        if fan_dp and fan_dp.enum:
            speeds = [v for k, v in fan_dp.enum.items() if k != 0]
            if speeds:
                self._attr_fan_speed_list = speeds

    def _get_localized_fan_speed(self, fan_speed: str) -> str:
        """Get localized fan speed display name."""
        language = self.hass.config.language if self.hass else "en"
        if language == "ru":
            return SUCTION_MAP_RU.get(fan_speed, fan_speed.capitalize())
        return SUCTION_MAP.get(fan_speed, fan_speed.capitalize())

    @property
    def activity(self) -> VacuumActivity | None:
        """Return vacuum activity."""
        if not self.coordinator or not self.coordinator.data:
            return None

        status_text = self.coordinator.data.get("status_text")
        if not status_text:
            return VacuumActivity.IDLE

        status_text = status_text.lower()

        activity_map = {
            "cleaning": VacuumActivity.CLEANING,
            "normal_clean": VacuumActivity.CLEANING,
            "room_clean": VacuumActivity.CLEANING,
            "zone_clean": VacuumActivity.CLEANING,
            "spot_clean": VacuumActivity.CLEANING,
            "returning": VacuumActivity.RETURNING,
            "recharge": VacuumActivity.RETURNING,
            "charging": VacuumActivity.DOCKED,
            "charge_finished": VacuumActivity.DOCKED,
            "docked": VacuumActivity.DOCKED,
            "idle": VacuumActivity.IDLE,
            "pause": VacuumActivity.PAUSED,
            "sleep": VacuumActivity.IDLE,
            "error": VacuumActivity.ERROR,
        }

        for key, value in activity_map.items():
            if key in status_text:
                return value

        return VacuumActivity.IDLE

    @property
    def battery_level(self) -> int | None:
        """Return battery level."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("battery_level")

    @property
    def fan_speed(self) -> Optional[str]:
        """Return current fan speed."""
        if not self.coordinator.data:
            return None
        fan_speed = self.coordinator.data.get("fan_speed")
        if fan_speed:
            return self._get_localized_fan_speed(fan_speed)
        return None

    @property
    def entity_picture(self) -> Optional[str]:
        """Return device picture."""
        if not self.coordinator.data:
            return None

        device_details = self.coordinator.data.get("device_details", {})
        image_url = device_details.get("image_url")

        if image_url:
            if "?" in image_url:
                return f"{image_url}&width=256&height=256"
            else:
                return f"{image_url}?width=256&height=256"

        return None

    # ============= Basic commands =============

    async def async_start(self) -> None:
        """Start cleaning."""
        _LOGGER.info("Command: START")
        await self.coordinator.vacuum.start_cleaning()
        await self.coordinator.async_request_refresh()

    async def async_pause(self) -> None:
        """Pause cleaning."""
        _LOGGER.info("Command: PAUSE")
        await self.coordinator.vacuum.pause_cleaning()
        await self.coordinator.async_request_refresh()

    async def async_stop(self, **kwargs: Any) -> None:
        """Stop cleaning."""
        _LOGGER.info("Command: STOP")
        await self.coordinator.vacuum.stop_cleaning()
        await self.coordinator.async_request_refresh()

    async def async_return_to_base(self, **kwargs: Any) -> None:
        """Return to base."""
        _LOGGER.info("Command: RETURN TO BASE")
        await self.coordinator.vacuum.return_to_base()
        await self.coordinator.async_request_refresh()

    async def async_locate(self, **kwargs: Any) -> None:
        """Locate the robot."""
        _LOGGER.info("Command: LOCATE")
        await self.coordinator.vacuum.locate()
        await self.coordinator.async_request_refresh()

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        """Set fan speed."""
        _LOGGER.info("Command: SET FAN SPEED %s", fan_speed)

        # Convert localized name back to internal key if needed
        language = self.hass.config.language if self.hass else "en"
        if language == "ru":
            # Reverse mapping for Russian
            reverse_map = {v: k for k, v in SUCTION_MAP_RU.items()}
            if fan_speed in reverse_map:
                fan_speed = reverse_map[fan_speed]

        dp_manager = self.coordinator.vacuum.dp_manager
        fan_dp = dp_manager.get_by_code('fan')

        if not fan_dp or not fan_dp.enum:
            _LOGGER.error("DP fan not found or has no enum")
            return

        value = None
        for k, v in fan_dp.enum.items():
            if v == fan_speed:
                value = k
                break

        if value is None:
            _LOGGER.error("Invalid fan speed: %s", fan_speed)
            return

        await self.coordinator.vacuum.send_raw_command(9, value)
        await self.coordinator.async_request_refresh()

    # ============= Additional commands =============

    async def async_build_map(self, **kwargs: Any) -> None:
        """Fast map building (DP 28)."""
        _LOGGER.info("Command: BUILD MAP")
        try:
            await self.coordinator.vacuum.build_map()
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Error in build_map: %s", e)

    async def async_empty_dust(self, **kwargs: Any) -> None:
        """Empty dust bin (DP 25)."""
        _LOGGER.info("Command: EMPTY DUST")
        try:
            await self.coordinator.vacuum.empty_dust()
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Error in empty_dust: %s", e)

    async def async_set_volume(self, volume: int, **kwargs: Any) -> None:
        """Set volume (DP 17)."""
        _LOGGER.info("Command: SET VOLUME %s%%", volume)
        try:
            await self.coordinator.vacuum.set_volume(volume)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Error in set_volume: %s", e)

    async def async_clean_room(self, room_name: str, **kwargs: Any) -> None:
        """Clean specific room."""
        _LOGGER.info("Command: CLEAN ROOM '%s'", room_name)
        try:
            rooms = await self.coordinator.vacuum.get_available_rooms()
            room_map = {r['name']: r['id'] for r in rooms}

            if room_name in room_map:
                await self.coordinator.vacuum.start_room_clean([room_map[room_name]])
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Room '%s' not found", room_name)
        except Exception as e:
            _LOGGER.error("Error in clean_room: %s", e)

    async def async_request_all_data(self, **kwargs: Any) -> None:
        """Request all data."""
        _LOGGER.info("Command: REQUEST ALL DATA")
        await self.coordinator.vacuum.request_all_data()
        await self.coordinator.async_request_refresh()

    async def async_request_map(self, **kwargs: Any) -> None:
        """Request map."""
        _LOGGER.info("Command: REQUEST MAP")
        await self.coordinator.vacuum.request_map()
        await self.coordinator.async_request_refresh()

    async def save_reference_map(self) -> bool:
        """Save current map as reference."""
        _LOGGER.info("Saving reference map")
        try:
            success = await self.coordinator.vacuum.save_reference_map()
            return success
        except Exception as e:
            _LOGGER.error("Error: %s", e)
            return False

    async def async_load_reference_map(self, **kwargs: Any) -> None:
        """Load reference map (DP 30)."""
        _LOGGER.info("Command: LOAD REFERENCE MAP")
        try:
            if hasattr(self.coordinator.vacuum, 'load_reference_map'):
                success = await self.coordinator.vacuum.load_reference_map()
                if success:
                    _LOGGER.info("Reference map loaded")
                    await self.async_request_map()
                else:
                    _LOGGER.error("Failed to load reference map")
            else:
                _LOGGER.error("Method load_reference_map not found")

        except Exception as e:
            _LOGGER.error("Error in load_reference_map: %s", e)

    async def save_current_map_to_cloud(self) -> bool:
        """Save current map to cloud."""
        _LOGGER.info("Saving map to cloud")
        try:
            if hasattr(self.coordinator.vacuum, 'save_current_map_to_cloud'):
                success = await self.coordinator.vacuum.save_current_map_to_cloud()
                return success
            else:
                await self.coordinator.vacuum._dp_manager.send(14, None)

                _LOGGER.info("Command to save map to cloud sent (DP 14)")

                self.hass.bus.async_fire("persistent_notification", {
                    "message": "Command sent to save current map to cloud",
                    "title": "Neatsvor"
                })

                async def delayed_refresh():
                    import asyncio
                    await asyncio.sleep(5)
                    if hasattr(self.coordinator, 'cloud_maps_sensor'):
                        await self.coordinator.cloud_maps_sensor.async_update()

                asyncio.create_task(delayed_refresh())

                return True

        except Exception as e:
            _LOGGER.error("Error saving map to cloud: %s", e)
            self.hass.bus.async_fire("persistent_notification", {
                "message": f"Error saving map: {e}",
                "title": "Neatsvor"
            })
            return False

    async def use_cloud_map(self, map_id: int, map_url: str, map_md5: str) -> bool:
        """Use a cloud map as the current map."""
        _LOGGER.info("Using cloud map %s", map_id)
        try:
            success = await self.coordinator.vacuum.use_cloud_map(map_id, map_url, map_md5)
            return success
        except Exception as e:
            _LOGGER.error("Error: %s", e)
            return False

    async def async_compare_with_reference(self, **kwargs: Any) -> Dict[str, Any]:
        """Compare current map with reference."""
        _LOGGER.info("Command: COMPARE WITH REFERENCE")
        try:
            result = await self.coordinator.vacuum.compare_with_reference()
            if result:
                _LOGGER.info("Comparison completed: %s%% differences", result.get('difference_percent', 0))
                return result
            else:
                _LOGGER.error("Failed to compare maps")
                return {}
        except Exception as e:
            _LOGGER.error("Error in compare_with_reference: %s", e)
            return {}

    async def async_send_command(self, command: str, params: dict = None, **kwargs):
        """Send a command to the vacuum."""
        _LOGGER.info("async_send_command: %s, params: %s", command, params)

        if command in ["app_zoned_clean", "zoned_clean"]:
            if params and "zones" in params:
                zones = params["zones"]
                _LOGGER.info("Zone cleaning: %s", zones)

                if len(zones) == 1:
                    zone = zones[0]
                    if len(zone) >= 4:
                        x1, y1, x2, y2 = zone[:4]
                        repeats = zone[4] if len(zone) > 4 else 1

                        await self.coordinator.vacuum.zone_clean(x1, y1, x2, y2, repeats)
                        return True
                else:
                    await self.coordinator.vacuum.multiple_zones_clean(zones)
                    return True
            else:
                _LOGGER.error("No zones parameter")

        elif command == "start":
            await self.async_start()
        elif command == "pause":
            await self.async_pause()
        elif command == "stop":
            await self.async_stop()
        elif command == "return_to_base":
            await self.async_return_to_base()
        else:
            _LOGGER.warning("Unknown command: %s", command)

        return False

    @property
    def state(self) -> Optional[str]:
        """Deprecated method, use activity instead."""
        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data:
            return {}

        data = self.coordinator.data

        attributes = {
            "water_level": data.get("water_level"),
            "clean_mode": data.get("clean_mode"),
            "status_code": data.get("status_code"),
        }

        if hasattr(self.coordinator.vacuum, 'reference_map'):
            ref_map = self.coordinator.vacuum.reference_map
            if ref_map:
                attributes["reference_map_id"] = ref_map.get('map_id')
                attributes["reference_map_name"] = ref_map.get('name')
                attributes["reference_map_date"] = ref_map.get('timestamp')

        consumables = data.get("consumables", {})
        for cons_type, cons_data in consumables.items():
            attributes[f"{cons_type}_remaining"] = cons_data.get("remaining_percent")
            attributes[f"{cons_type}_hours"] = cons_data.get("remaining_hours")

        return attributes