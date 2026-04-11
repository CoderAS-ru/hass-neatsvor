"""Camera platform for Neatsvor."""

import logging
import asyncio
from pathlib import Path
from datetime import datetime

from homeassistant.components.camera import Camera
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
    """Set up Neatsvor cameras."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Live map camera
    entities.append(NeatsvorLiveCamera(coordinator))
    _LOGGER.info("Added live camera")

    # Cloud map camera
    if hasattr(coordinator.vacuum, 'cloud_maps'):
        cloud_camera = NeatsvorCloudMapCamera(coordinator)
        entities.append(cloud_camera)
        coordinator.cloud_map_camera = cloud_camera
        _LOGGER.info("Added cloud map camera")

    # Clean history camera
    entities.append(NeatsvorCleanHistoryCamera(coordinator))
    _LOGGER.info("Added clean history camera")

    async_add_entities(entities)


class NeatsvorLiveCamera(CoordinatorEntity, Camera):
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_live_camera"
    _attr_translation_key = "live_camera"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        Camera.__init__(self)
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:map"
        self._attr_frame_interval = 1.0

        self._last_image = None
        self._last_update = None
        self._map_count = 0
        self._initial_image_loaded = False
        self._image_ready = asyncio.Event()

        if coordinator.vacuum:
            coordinator.vacuum.on_map(self._async_handle_map)
            _LOGGER.debug("Camera subscribed to map updates")

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.info("Live camera added to hass, requesting map...")
        
        # Принудительно запрашиваем карту после добавления в hass
        await self._request_map_with_retry()

    async def _request_map_with_retry(self, retry_count=5):
        """Request map with retry."""
        for attempt in range(retry_count):
            if self.coordinator and self.coordinator.vacuum:
                _LOGGER.info("Requesting map (attempt %s/%s)", attempt + 1, retry_count)
                await self.coordinator.vacuum.request_map()
                
                # Ждём ответа
                try:
                    await asyncio.wait_for(self._image_ready.wait(), timeout=10.0)
                    _LOGGER.info("Map received successfully!")
                    return
                except asyncio.TimeoutError:
                    _LOGGER.warning("Timeout waiting for map, retrying...")
                    self._image_ready.clear()
                    await asyncio.sleep(2)
            else:
                await asyncio.sleep(2)
        
        _LOGGER.error("Failed to get map after %s attempts", retry_count)

    async def _async_handle_map(self, map_data: dict):
        """Handle new map data."""
        try:
            self._map_count += 1
            _LOGGER.debug("Received map #%s: %sx%s", 
                         self._map_count, 
                         map_data.get('width', 0), 
                         map_data.get('height', 0))

            # Рендерим карту
            filename = await self.coordinator.vacuum.visualizer.render_static_map(
                map_data,
                title=f"live_{self._map_count:06d}",
                map_type="realtime"
            )

            if filename and Path(filename).exists():
                import aiofiles
                async with aiofiles.open(filename, 'rb') as f:
                    self._last_image = await f.read()
                    self._initial_image_loaded = True
                    self._image_ready.set()

                self._last_update = datetime.now()
                self.async_write_ha_state()
                _LOGGER.info("Camera updated with map #%s, image size: %s bytes", 
                            self._map_count, len(self._last_image))

            # Периодически чистим старые карты
            if self._map_count % 10 == 0:
                await self.coordinator.vacuum.visualizer.cleanup_realtime_maps(keep_last=10)

        except Exception as e:
            _LOGGER.error("Error processing map: %s", e, exc_info=True)

    async def async_camera_image(self, width=None, height=None):
        """Return camera image."""
        # Если изображения ещё нет, ждём его появления
        if not self._initial_image_loaded:
            try:
                await asyncio.wait_for(self._image_ready.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for initial map image")
                return None
        
        return self._last_image

    @property
    def available(self) -> bool:
        """Return if camera is available."""
        return self._last_image is not None

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        return {
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "map_count": self._map_count,
            "image_size": len(self._last_image) if self._last_image else 0,
            "image_ready": self._initial_image_loaded
        }


class NeatsvorCloudMapCamera(CoordinatorEntity, Camera):
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_cloud_map_camera"
    _attr_translation_key = "cloud_map_camera"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        Camera.__init__(self)
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:cloud-outline"
        self._attr_frame_interval = 0.5
        # Name will be taken from translations via entity_id

        self._current_image = None
        self._current_map_id = None
        self._next_image = None
        self._next_map_id = None
        self._image_timestamp = 0
        self._cloud_maps_ready = False
        self._map_path = None
        self._last_update = datetime.now()

        _LOGGER.debug("CloudMapCamera initialized")

        coordinator.cloud_map_camera = self

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.debug("CloudMapCamera added to hass")

        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

        asyncio.create_task(self._wait_for_cloud_maps())

    async def _wait_for_cloud_maps(self):
        """Wait for cloud_maps_sensor to be available."""
        for i in range(30):
            if hasattr(self.coordinator, 'cloud_maps_sensor') and self.coordinator.cloud_maps_sensor:
                self._cloud_maps_ready = True
                _LOGGER.debug("Cloud maps sensor is now available")
                await self.async_update_image()
                break
            await asyncio.sleep(1)
        else:
            _LOGGER.warning("Cloud maps sensor not available after 30 seconds")

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self._cloud_maps_ready:
            return

        if hasattr(self.coordinator, 'cloud_maps_sensor') and self.coordinator.cloud_maps_sensor:
            sensor = self.coordinator.cloud_maps_sensor
            if sensor and sensor.selected_map_id != self._current_map_id:
                _LOGGER.info("Map changed from %s to %s", self._current_map_id, sensor.selected_map_id)
                self.hass.async_create_task(self.async_update_image())

    @property
    def entity_picture(self) -> str | None:
        """Return URL of image for frontend with cache busting."""
        url = super().entity_picture
        if self._current_image and self._last_update:
            timestamp = int(self._last_update.timestamp())
            if url:
                if '?' in url:
                    return f"{url}&t={timestamp}"
                else:
                    return f"{url}?t={timestamp}"
        return url

    def prefetch_image(self, map_id: int, image_bytes: bytes):
        """Prefetch image for faster switching."""
        self._next_image = image_bytes
        self._next_map_id = map_id
        _LOGGER.debug("Prefetched image for map %s", map_id)

    async def async_update_image(self):
        """Update the camera image."""
        _LOGGER.debug("CloudMapCamera.async_update_image() called")

        if not self._cloud_maps_ready:
            return

        if not hasattr(self.coordinator, 'cloud_maps_sensor') or not self.coordinator.cloud_maps_sensor:
            return

        sensor = self.coordinator.cloud_maps_sensor
        selected_id = sensor.selected_map_id

        if not selected_id:
            _LOGGER.debug("No map selected")
            return

        for m in sensor._maps:
            if m['id'] == selected_id:
                png_path = m.get('png_path')
                if png_path:
                    _LOGGER.info("Loading image for map %s from: %s", selected_id, png_path)
                    await self._async_load_image(png_path, selected_id)
                else:
                    _LOGGER.warning("No PNG path for map %s", selected_id)
                break

    async def _async_load_image(self, png_path: str, map_id: int) -> None:
        """Load image from file."""
        try:
            path = Path(png_path)
            if not path.exists():
                _LOGGER.warning("PNG file not found: %s", png_path)
                return

            import aiofiles
            async with aiofiles.open(path, 'rb') as f:
                image_bytes = await f.read()

                # If this is the current map, update
                sensor = self.coordinator.cloud_maps_sensor
                if sensor and sensor.selected_map_id == map_id:
                    self._current_image = image_bytes
                    self._current_map_id = map_id
                    self._image_timestamp = path.stat().st_mtime
                    self._last_update = datetime.now()
                    _LOGGER.info("Loaded image for camera: %s (%s bytes)", path.name, len(self._current_image))
                else:
                    # Otherwise store in prefetch
                    self.prefetch_image(map_id, image_bytes)
                    _LOGGER.info("Prefetched image for map %s: %s (%s bytes)", map_id, path.name, len(image_bytes))

                self.async_write_ha_state()

        except Exception as e:
            _LOGGER.error("Error loading image for camera: %s", e, exc_info=True)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return camera image with prefetch support."""
        sensor = self.coordinator.cloud_maps_sensor
        if not sensor:
            return None

        selected_id = sensor.selected_map_id
        if not selected_id:
            return None

        # If there's a prefetched image for the current map
        if self._next_map_id == selected_id and self._next_image:
            self._current_image = self._next_image
            self._current_map_id = selected_id
            self._last_update = datetime.now()
            self._next_image = None
            self._next_map_id = None
            self.async_write_ha_state()
            _LOGGER.debug("Used prefetched image for map %s", selected_id)
            return self._current_image

        # If this is the current image
        if self._current_map_id == selected_id and self._current_image:
            return self._current_image

        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self._cloud_maps_ready:
            return False
        if not hasattr(self.coordinator, 'cloud_maps_sensor') or not self.coordinator.cloud_maps_sensor:
            return False
        return self.coordinator.cloud_maps_sensor.selected_map_id is not None

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        return {
            "current_map_id": self._current_map_id,
            "image_size": len(self._current_image) if self._current_image else 0,
            "image_timestamp": self._image_timestamp,
            "cloud_maps_ready": self._cloud_maps_ready,
        }


class NeatsvorCleanHistoryCamera(Camera, CoordinatorEntity):
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_clean_history_camera"
    _attr_translation_key = "clean_history_camera"

    def __init__(self, coordinator):
        super().__init__()
        CoordinatorEntity.__init__(self, coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:history"
        # Name will be taken from translations via entity_id

        self.content_type = "image/png"
        self._current_image = None
        self._current_record_id = None
        self._next_image = None  # Cache for next map
        self._next_record_id = None
        self._last_image_path = None
        self._last_update = datetime.now()

        _LOGGER.debug("CleanHistoryCamera initialized")

        coordinator.clean_history_camera = self

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.info("CleanHistoryCamera added to hass with entity_id: %s", self.entity_id)

    @property
    def entity_picture(self) -> str | None:
        """Return URL of image for frontend with cache busting."""
        url = super().entity_picture

        if self._current_image and self._last_update:
            timestamp = int(self._last_update.timestamp())
            if url:
                if '?' in url:
                    return f"{url}&t={timestamp}"
                else:
                    return f"{url}?t={timestamp}"

        return url

    def prefetch_image(self, record_id: int, image_bytes: bytes):
        """Prefetch image for faster switching."""
        self._next_image = image_bytes
        self._next_record_id = record_id
        _LOGGER.debug("Prefetched image for record %s", record_id)

    def update_image(self, record_id: int, image_bytes: bytes):
        """Called by sensor when new image is available."""
        old_record_id = self._current_record_id
        self._current_record_id = record_id
        self._current_image = image_bytes
        self._last_update = datetime.now()

        # Clear prefetch if it's the same record
        if self._next_record_id == record_id:
            self._next_image = None
            self._next_record_id = None

        self.async_write_ha_state()

        _LOGGER.info("Camera updated for record %s (%s bytes) (was %s)", record_id, len(image_bytes), old_record_id)

    def force_refresh(self):
        """Force refresh camera state."""
        self._current_image = None
        self._current_record_id = None
        self._last_update = datetime.now()
        self.async_write_ha_state()
        _LOGGER.debug("Camera force refreshed")

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return camera image with prefetch support."""
        sensor = self.coordinator.clean_history_sensor
        if not sensor:
            return None

        selected_id = sensor.selected_record_id
        if not selected_id:
            return None

        # If there's a prefetched image for the current record
        if self._next_record_id == selected_id and self._next_image:
            # Swap next and current
            self._current_image = self._next_image
            self._current_record_id = selected_id
            self._last_update = datetime.now()
            self._next_image = None
            self._next_record_id = None
            self.async_write_ha_state()
            _LOGGER.debug("Used prefetched image for record %s", selected_id)
            return self._current_image

        # If this is the current image
        if self._current_record_id == selected_id and self._current_image:
            return self._current_image

        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not hasattr(self.coordinator, 'clean_history_sensor'):
            return False
        sensor = self.coordinator.clean_history_sensor
        return sensor is not None and sensor.selected_record_id is not None