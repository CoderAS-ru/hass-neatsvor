"""Binary sensor platform for Neatsvor."""

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neatsvor binary sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        NeatsvorOnlineSensor(coordinator),
        NeatsvorChargingSensor(coordinator),
        NeatsvorDustBinFullSensor(coordinator),
        NeatsvorMopAttachedSensor(coordinator),
    ]

    async_add_entities(entities)
    _LOGGER.info("Created %s binary sensors", len(entities))


class NeatsvorOnlineSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_online"
    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:satellite-uplink"

    @property
    def is_on(self) -> bool:
        """Return true if device is online."""
        if not self.coordinator.data:
            return False
        return bool(self.coordinator.data.get("online", False))

    @property
    def available(self) -> bool:
        """Always available."""
        return True


class NeatsvorChargingSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_charging"
    _attr_translation_key = "charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:battery-charging"

    @property
    def is_on(self) -> bool:
        """Return true if charging."""
        if not self.coordinator or not self.coordinator.data:
            return False

        status_text = self.coordinator.data.get("status_text")
        if not status_text:
            return False

        status_text = status_text.lower()
        charging_states = ["charging", "charge_finished", "docked"]

        return any(state in status_text for state in charging_states)

    @property
    def available(self) -> bool:
        """Return true if data available."""
        return self.coordinator.data is not None


class NeatsvorDustBinFullSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_dust_bin"
    _attr_translation_key = "dust_bin"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:delete-alert"

    @property
    def is_on(self) -> bool:
        """Return true if dust bin is full."""
        if not self.coordinator or not self.coordinator.data:
            return False

        status_code = self.coordinator.data.get("status_code")
        return status_code == 18  # dust_box_full

    @property
    def available(self) -> bool:
        """Return true if data available."""
        return self.coordinator.data is not None


class NeatsvorMopAttachedSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_mop_attached"
    _attr_translation_key = "mop_attached"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:spray"

    @property
    def is_on(self) -> bool:
        """Return true if mop is attached."""
        if not self.coordinator.data:
            return False
        return True  # Default to True

    @property
    def available(self) -> bool:
        """Return true if data available."""
        return self.coordinator.data is not None