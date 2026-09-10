"""Image platform for Neatsvor cloud maps."""

import logging
import asyncio
from pathlib import Path
from typing import Optional

from homeassistant.components.image import ImageEntity
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
    """Set up Neatsvor image entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Cloud map image only
    entities.append(NeatsvorCloudMapImage(coordinator))
    _LOGGER.info("Added cloud map image entity")

    async_add_entities(entities)


class NeatsvorCloudMapImage(ImageEntity, CoordinatorEntity):
    """Image entity for selected cloud map."""

    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator.hass)
        CoordinatorEntity.__init__(self, coordinator)
        self._attr_unique_id = "neatsvor_cloud_map_image"
        self._attr_name = "Cloud Map"
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:cloud-outline"
        self._content_type = "image/png"
        self._cached_image = None
        self._current_map_id = None
        self._current_png_url = None
        self._cloud_maps_ready = False
        _LOGGER.debug("CloudMapImage initialized")

        coordinator.cloud_map_image = self

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.debug("CloudMapImage added to hass")

        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

        asyncio.create_task(self._wait_for_cloud_maps())

    async def _wait_for_cloud_maps(self):
        """Wait for cloud_maps_sensor to be available."""
        for i in range(30):
            if hasattr(self.coordinator, 'cloud_maps_sensor') and self.coordinator.cloud_maps_sensor:
                self._cloud_maps_ready = True
                _LOGGER.debug("Cloud maps sensor is now available for image")
                self.async_write_ha_state()
                break
            await asyncio.sleep(1)
        else:
            _LOGGER.warning("Cloud maps sensor not available after 30 seconds for image")

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self._cloud_maps_ready:
            return
        _LOGGER.debug("CloudMapImage received coordinator update")
        self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        """Return image bytes."""
        if not self._cloud_maps_ready:
            _LOGGER.debug("Waiting for cloud maps sensor...")
            return None

        _LOGGER.debug("async_image() called")

        if not hasattr(self.coordinator, 'cloud_maps_sensor') or not self.coordinator.cloud_maps_sensor:
            _LOGGER.error("No cloud_maps_sensor in coordinator")
            return None

        sensor = self.coordinator.cloud_maps_sensor
        selected_id = sensor.selected_map_id

        _LOGGER.debug("Selected map ID: %s", selected_id)
        _LOGGER.debug("Current cached map ID: %s", self._current_map_id)

        if not selected_id:
            _LOGGER.debug("No map selected")
            return None

        if self._current_map_id == selected_id and self._cached_image:
            _LOGGER.debug("Returning cached image for map %s", selected_id)
            return self._cached_image

        _LOGGER.info("Loading image for map ID: %s", selected_id)

        cloud_map = None
        for m in sensor._maps:
            if m['id'] == selected_id:
                cloud_map = m
                break

        if not cloud_map:
            _LOGGER.warning("Map ID %s not found in sensor data", selected_id)
            return None

        _LOGGER.debug("Map data: %s", cloud_map)

        png_path = None
        if cloud_map.get('png_path'):
            png_path = Path(cloud_map['png_path'])
            if png_path.exists():
                _LOGGER.debug("Found PNG at public path: %s", png_path)
            else:
                png_path = None

        if not png_path and cloud_map.get('local_path'):
            bv_path = Path(cloud_map['local_path'])
            png_path = Path("/config/www/neatsvor/maps/cloud/png") / bv_path.name.replace('.bv', '.png')
            if png_path.exists():
                _LOGGER.debug("Found PNG from BV path at public location: %s", png_path)
            else:
                png_path = None

        if png_path and png_path.exists():
            try:
                import aiofiles
                async with aiofiles.open(png_path, 'rb') as f:
                    self._cached_image = await f.read()
                    self._current_map_id = selected_id
                    self._current_png_url = cloud_map.get('png_url')
                    _LOGGER.info("Loaded map image: %s (%s bytes)", png_path.name, len(self._cached_image))
                    self.async_write_ha_state()
                    return self._cached_image
            except Exception as e:
                _LOGGER.error("Error loading image file: %s", e, exc_info=True)
        else:
            _LOGGER.warning("No PNG file found for map %s", selected_id)

        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self._cloud_maps_ready:
            return False
        if not hasattr(self.coordinator, 'cloud_maps_sensor') or not self.coordinator.cloud_maps_sensor:
            return False

        sensor = self.coordinator.cloud_maps_sensor
        if not sensor.selected_map_id:
            return False

        for m in sensor._maps:
            if m['id'] == sensor.selected_map_id:
                return m.get('local_path') is not None or m.get('png_path') is not None
        return False

    @property
    def entity_picture(self) -> str | None:
        """Return URL of image for frontend."""
        if not self._cloud_maps_ready:
            return None

        if not hasattr(self.coordinator, 'cloud_maps_sensor') or not self.coordinator.cloud_maps_sensor:
            return None

        sensor = self.coordinator.cloud_maps_sensor
        if not sensor.selected_map_id:
            return None

        for m in sensor._maps:
            if m['id'] == sensor.selected_map_id:
                if m.get('png_url'):
                    import time
                    return f"{m['png_url']}?v={int(time.time())}"
        return None