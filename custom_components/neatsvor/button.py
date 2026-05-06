"""Button platform for Neatsvor cloud maps."""

import logging
from typing import Optional, Dict, Any

from homeassistant.components.button import ButtonEntity
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
    """Set up Neatsvor buttons."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        NeatsvorRefreshCloudMapsButton(coordinator),
        NeatsvorSetReferenceMapButton(coordinator),
        NeatsvorRestoreReferenceMapButton(coordinator),
        NeatsvorDownloadMapButton(coordinator),
        NeatsvorDeleteCloudMapButton(coordinator),
        NeatsvorSaveCurrentMapButton(coordinator),
        NeatsvorUseSelectedMapButton(coordinator),
        NeatsvorRefreshCleanHistoryButton(coordinator),
    ]

    async_add_entities(entities)
    _LOGGER.info("Added %d cloud map buttons", len(entities))


class NeatsvorRefreshCloudMapsButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_refresh_cloud_maps"
    _attr_translation_key = "refresh_cloud_maps"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        """Press the button."""
        _LOGGER.info("Refreshing cloud maps list")
        if hasattr(self.coordinator, 'cloud_maps_sensor'):
            await self.coordinator.cloud_maps_sensor.async_update()
            self.hass.bus.async_fire("persistent_notification", {
                "message": "Cloud maps list refreshed",
                "title": "Neatsvor Cloud Maps"
            })
        else:
            _LOGGER.error("No cloud_maps_sensor in coordinator")


class NeatsvorSetReferenceMapButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_set_reference_map"
    _attr_translation_key = "set_reference_map"
    _attr_icon = "mdi:map-marker-star"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        """Handle button press."""
        if not hasattr(self.coordinator, 'cloud_maps_sensor'):
            _LOGGER.error("No cloud maps sensor available")
            return

        sensor = self.coordinator.cloud_maps_sensor
        if not sensor.selected_map_id:
            _LOGGER.warning("No map selected")
            self.hass.bus.async_fire("persistent_notification", {
                "message": "Please select a cloud map first",
                "title": "Neatsvor Reference Map"
            })
            return

        # Save the selected map as the reference
        sensor.set_reference_map(sensor.selected_map_id)

        # Send notification
        self.hass.bus.async_fire("persistent_notification", {
            "message": "Map set as reference",
            "title": "Neatsvor Reference Map"
        })


class NeatsvorRestoreReferenceMapButton(CoordinatorEntity, ButtonEntity):
    """Button to restore the reference map from the device."""
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_restore_reference_map"
    _attr_translation_key = "restore_reference_map"
    _attr_icon = "mdi:restore"

    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        """Press the button to restore the reference map from the device."""
        if not hasattr(self.coordinator, 'vacuum') or not self.coordinator.vacuum:
            _LOGGER.error("No vacuum instance")
            return

        _LOGGER.info("Restoring reference map from device")

        try:
            success = await self.coordinator.vacuum.load_reference_map()

            if success:
                _LOGGER.info("Reference map restored successfully")
                self.hass.bus.async_fire("persistent_notification", {
                    "message": "Reference map restored from device",
                    "title": "Neatsvor Cloud Maps"
                })

                if hasattr(self.coordinator.vacuum, 'request_map'):
                    await self.coordinator.vacuum.request_map()
            else:
                _LOGGER.error("Failed to restore reference map")
                self.hass.bus.async_fire("persistent_notification", {
                    "message": "Failed to restore reference map from device",
                    "title": "Neatsvor Cloud Maps"
                })

        except Exception as e:
            _LOGGER.error("Error restoring reference map: %s", e)
            self.hass.bus.async_fire("persistent_notification", {
                "message": f"Error: {e}",
                "title": "Neatsvor Cloud Maps"
            })


class NeatsvorDownloadMapButton(CoordinatorEntity, ButtonEntity):
    """Button to download the selected cloud map."""
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_download_map"
    _attr_translation_key = "download_map"
    _attr_icon = "mdi:download"

    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        """Press the button."""
        if not hasattr(self.coordinator, 'cloud_maps_sensor'):
            _LOGGER.error("No cloud_maps_sensor in coordinator")
            return

        selected_id = self.coordinator.cloud_maps_sensor.selected_map_id
        if not selected_id:
            _LOGGER.warning("No map selected to download")
            self.hass.bus.async_fire("persistent_notification", {
                "message": "Please select a map first",
                "title": "Neatsvor Cloud Maps"
            })
            return

        _LOGGER.info("Downloading map %d", selected_id)
        self.hass.bus.async_fire("persistent_notification", {
            "message": f"Downloading map {selected_id}...",
            "title": "Neatsvor Cloud Maps"
        })

        if self.coordinator.vacuum and hasattr(self.coordinator.vacuum, 'cloud_maps'):
            try:
                maps = await self.coordinator.vacuum.cloud_maps.get_map_list(
                    self.coordinator.vacuum.info.device_id, 20
                )
                target_map = next((m for m in maps if m.device_map_id == selected_id), None)

                if target_map:
                    result = await self.coordinator.vacuum.cloud_maps.download_map(target_map)
                    if result:
                        if hasattr(self.coordinator.cloud_maps_sensor, 'update_map_info'):
                            await self.coordinator.cloud_maps_sensor.update_map_info(selected_id, result)
                        _LOGGER.info("Map %d downloaded successfully", selected_id)
                        self.hass.bus.async_fire("persistent_notification", {
                            "message": f"Map downloaded successfully",
                            "title": "Neatsvor Cloud Maps"
                        })
                else:
                    _LOGGER.warning("Map %d not found in API", selected_id)
                    self.hass.bus.async_fire("persistent_notification", {
                        "message": f"Map {selected_id} not found in API",
                        "title": "Neatsvor Cloud Maps"
                    })
            except Exception as e:
                _LOGGER.error("Error downloading map: %s", e)
                self.hass.bus.async_fire("persistent_notification", {
                    "message": f"Error downloading map: {e}",
                    "title": "Neatsvor Cloud Maps"
                })


class NeatsvorDeleteCloudMapButton(CoordinatorEntity, ButtonEntity):
    """Button to delete the selected cloud map."""
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_delete_cloud_map"
    _attr_translation_key = "delete_cloud_map"
    _attr_icon = "mdi:delete"
    
    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        """Press the button."""
        if not hasattr(self.coordinator, 'cloud_maps_sensor'):
            _LOGGER.error("No cloud_maps_sensor in coordinator")
            return

        selected_id = self.coordinator.cloud_maps_sensor.selected_map_id
        if not selected_id:
            _LOGGER.warning("No map selected to delete")
            self.hass.bus.async_fire("persistent_notification", {
                "message": "Please select a map first",
                "title": "Neatsvor Cloud Maps"
            })
            return

        _LOGGER.info("Deleting map %d", selected_id)

        selected_map = self.coordinator.cloud_maps_sensor.get_map_by_id(selected_id)
        map_name = selected_map['name'] if selected_map else f"ID {selected_id}"

        self.hass.bus.async_fire("persistent_notification", {
            "message": f"Delete map '{map_name}'? (stub implementation - would delete from cloud)",
            "title": "Neatsvor Cloud Maps"
        })

        if hasattr(self.coordinator.cloud_maps_sensor, '_maps'):
            self.coordinator.cloud_maps_sensor._maps = [
                m for m in self.coordinator.cloud_maps_sensor._maps
                if m['id'] != selected_id
            ]
            self.coordinator.cloud_maps_sensor.async_write_ha_state()

            if hasattr(self.coordinator, 'cloud_map_select'):
                await self.coordinator.cloud_map_select.async_update()


class NeatsvorSaveCurrentMapButton(CoordinatorEntity, ButtonEntity):
    """Button to save the current map to the cloud."""
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_save_current_map"
    _attr_translation_key = "save_current_map"
    _attr_icon = "mdi:cloud-upload"
    
    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        """Press the button."""
        _LOGGER.info("Saving current map to cloud")

        if not hasattr(self.coordinator, 'vacuum') or not self.coordinator.vacuum:
            _LOGGER.error("No vacuum instance")
            self.hass.bus.async_fire("persistent_notification", {
                "message": "Vacuum not available",
                "title": "Neatsvor"
            })
            return

        success = await self.coordinator.vacuum.save_current_map_to_cloud()

        if success:
            _LOGGER.info("Map save command sent successfully")
        else:
            _LOGGER.error("Failed to send save command")


class NeatsvorUseSelectedMapButton(CoordinatorEntity, ButtonEntity):
    """Button to use the selected cloud map as the current map."""
    _attr_has_entity_name = True
    _attr_unique_id = "neatsvor_use_selected_map"
    _attr_translation_key = "use_selected_map"
    _attr_icon = "mdi:map-check"
    
    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        """Press the button."""
        _LOGGER.info("Use selected map button pressed")
        if hasattr(self.coordinator, 'cloud_maps_sensor'):
            await self.coordinator.cloud_maps_sensor.use_selected_cloud_map()
        else:
            _LOGGER.error("No cloud_maps_sensor in coordinator")
            
class NeatsvorRefreshCleanHistoryButton(CoordinatorEntity, ButtonEntity):
    """Button to force load clean history maps."""
    _attr_has_entity_name = True
    _attr_unique_id = "s700_refresh_clean_history"  # ← именно такой ID!
    _attr_translation_key = "refresh_clean_history"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Force loading clean history...")
        
        try:
            # Используем существующий сервис
            await self.hass.services.async_call(
                "neatsvor",
                "force_load_history",
                {},
                blocking=False
            )
            
            # Уведомление пользователя
            self.hass.bus.async_fire("persistent_notification", {
                "message": "Loading clean history maps... This may take a few minutes.",
                "title": "Neatsvor Clean History"
            })
            
            # Обновляем select, чтобы он показал новые записи
            if hasattr(self.coordinator, 'clean_history_select'):
                await self.coordinator.clean_history_select.async_update()
                
        except Exception as e:
            _LOGGER.error("Error loading history: %s", e)
            self.hass.bus.async_fire("persistent_notification", {
                "message": f"Error loading history: {e}",
                "title": "Neatsvor Error"
            })