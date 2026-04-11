"""Switch platform for Neatsvor."""

import logging

from homeassistant.components.switch import SwitchEntity
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
    """Set up Neatsvor switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        NeatsvorAutoRestoreSwitch(coordinator),
    ]

    async_add_entities(entities)
    _LOGGER.info("Added %s switches", len(entities))


class NeatsvorAutoRestoreSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_auto_restore"
    _attr_translation_key = "auto_restore"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_icon = "mdi:autorenew"
        self._attr_device_info = coordinator.device_info
        self._attr_is_on = self._load_state()

    def _load_state(self) -> bool:
        """Load saved state from storage."""
        if hasattr(self.coordinator, 'select_storage'):
            saved = self.coordinator.select_storage.get('auto_restore')
            return saved == "on"
        return False

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        self._attr_is_on = True
        self._save_state()
        self.async_write_ha_state()
        _LOGGER.info("Auto-restore reference map ENABLED")

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        self._attr_is_on = False
        self._save_state()
        self.async_write_ha_state()
        _LOGGER.info("Auto-restore reference map DISABLED")

    def _save_state(self):
        """Save state to storage."""
        if hasattr(self.coordinator, 'select_storage'):
            value = "on" if self._attr_is_on else "off"
            self.coordinator.select_storage.async_set('auto_restore', value)