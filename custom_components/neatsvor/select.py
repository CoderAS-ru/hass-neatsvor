"""Select platform for Neatsvor."""

import asyncio
import logging
from typing import List, Optional, Dict, Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    get_localized_fan_speed,
    get_localized_water_level,
    get_localized_clean_mode,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neatsvor select entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    hass.async_create_task(
        _async_setup_selects_later(coordinator, async_add_entities)
    )


async def _async_setup_selects_later(coordinator, async_add_entities):
    """Create selects after DP Manager initialization."""
    _LOGGER.debug("SELECT: Starting select creation")
    
    for i in range(30):
        if coordinator.vacuum and coordinator.vacuum.is_initialized:
            _LOGGER.debug("Vacuum ready after %s seconds", i + 1)
            break
        await asyncio.sleep(1)
    else:
        _LOGGER.error("Vacuum not initialized after 30 seconds")
        return

    for i in range(30):
        if coordinator.vacuum.dp_manager and len(coordinator.vacuum.dp_manager) > 0:
            _LOGGER.debug("DP Manager ready after %s seconds", i + 1)
            break
        await asyncio.sleep(1)
    else:
        _LOGGER.error("DP Manager not initialized")
        return

    dp_manager = coordinator.vacuum.dp_manager
    all_codes = dp_manager.get_all_codes()
    _LOGGER.debug("Available DP codes: %s", all_codes)

    new_entities = []

    # Water level (DP 10)
    water_dp = dp_manager.get_by_code('water_tank')
    if water_dp and water_dp.enum:
        options = [v for k, v in water_dp.enum.items() if k != 0]
        if options:
            new_entities.append(NeatsvorEnumSelect(
                coordinator,
                dp_id=10,
                translation_key="water_level",
                icon="mdi:water",
                options=options,
                value_map={v: k for k, v in water_dp.enum.items()},
                localize_func=get_localized_water_level,
            ))
            _LOGGER.info("Added water level: %s", options)

    # Fan speed (DP 9)
    fan_dp = dp_manager.get_by_code('fan')
    if fan_dp and fan_dp.enum:
        options = [v for k, v in fan_dp.enum.items() if k != 0]
        if options:
            new_entities.append(NeatsvorEnumSelect(
                coordinator,
                dp_id=9,
                translation_key="fan_speed",
                icon="mdi:fan",
                options=options,
                value_map={v: k for k, v in fan_dp.enum.items()},
                localize_func=get_localized_fan_speed,
            ))
            _LOGGER.info("Added fan speed: %s", options)

    # Clean mode (DP 15)
    mode_dp = dp_manager.get_by_code('clean_mode')
    if mode_dp and mode_dp.enum:
        # Оригинальные опции: ['sweep', 'mop', 'sweepMop']
        raw_options = list(mode_dp.enum.values())
        # Опции для отображения: ['sweep', 'mop', 'sweep_mop']
        display_options = []
        for opt in raw_options:
            if opt == "sweepMop":
                display_options.append("sweep_mop")
            else:
                display_options.append(opt)
        
        # value_map: нормализованное значение -> DP ID (число)
        value_map = {}
        for dp_id, raw_value in mode_dp.enum.items():
            normalized = "sweep_mop" if raw_value == "sweepMop" else raw_value
            value_map[normalized] = dp_id
        
        _LOGGER.debug("Clean mode - raw: %s, display: %s, map: %s", 
                      raw_options, display_options, value_map)
        
        new_entities.append(NeatsvorEnumSelect(
            coordinator,
            dp_id=15,
            translation_key="clean_mode",
            icon="mdi:broom",
            options=display_options,
            value_map=value_map,
            localize_func=get_localized_clean_mode,
        ))
        _LOGGER.info("Added clean mode: %s", display_options)

    # Room selection
    room_clean_dp = dp_manager.get_by_code('room_clean')
    if room_clean_dp:
        new_entities.append(NeatsvorRoomSelect(coordinator))
        _LOGGER.info("Added room selection")

        # Cloud map selection
    if hasattr(coordinator.vacuum, 'cloud_maps'):
        new_entities.append(NeatsvorCloudMapSelect(coordinator))
        _LOGGER.info("Added cloud map selection")

    # Clean history selection
    if hasattr(coordinator.vacuum, 'clean_history'):
        new_entities.append(NeatsvorCleanHistorySelect(coordinator))
        _LOGGER.info("Added clean history selection")

    if new_entities:
        async_add_entities(new_entities)
        _LOGGER.info("Added %s selects", len(new_entities))
    else:
        _LOGGER.warning("No selects added")


class NeatsvorEnumSelect(CoordinatorEntity, SelectEntity):
    """Universal select for enum DP with saved state and localization."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, dp_id: int, translation_key: str, icon: str,
                 options: List[str], value_map: Dict[str, int],
                 localize_func=None):
        super().__init__(coordinator)
        self._dp_id = dp_id
        self._value_map = value_map
        self._storage_key = f"dp_{dp_id}"
        self._initial_value_sent = False
        self._localize_func = localize_func
        self._raw_options = options  # Сохраняем исходные опции

        self._attr_unique_id = f"neatsvor_{translation_key}"
        self._attr_translation_key = translation_key
        self._attr_device_info = coordinator.device_info
        self._attr_icon = icon
        
        # Временно устанавливаем заглушку
        self._attr_options = ["⏳ Loading..."]
        self._attr_current_option = None
        
        # Сохраняем saved_value для восстановления после локализации
        self._saved_value = self._get_saved_value()
        self._current_value = self._get_current_value()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        
        # Теперь hass доступен, можно локализовать
        language = self.hass.config.language if self.hass else "en"
        _LOGGER.info("Initializing %s with language: %s", self._attr_translation_key, language)
        
        # Локализуем опции
        self._attr_options = self._get_localized_options(self._raw_options)
        
        # Восстанавливаем значение
        if self._saved_value and self._saved_value in self._raw_options:
            self._attr_current_option = self._localize_option(self._saved_value)
            _LOGGER.info("%s: restored saved value '%s' -> '%s'", 
                        self._attr_translation_key, self._saved_value, self._attr_current_option)
        elif self._current_value and self._current_value in self._raw_options:
            self._attr_current_option = self._localize_option(self._current_value)
            _LOGGER.debug("%s: current value '%s' -> '%s'", 
                         self._attr_translation_key, self._current_value, self._attr_current_option)
        else:
            default_options = [opt for opt in self._raw_options if opt != 'none' and opt]
            if default_options:
                self._attr_current_option = self._localize_option(default_options[0])
            else:
                self._attr_current_option = self._localize_option(self._raw_options[0]) if self._raw_options else None
            _LOGGER.info("%s: auto-selected '%s'", self._attr_translation_key, self._attr_current_option)
        
        self.async_write_ha_state()
        
        # Отложенная отправка начального значения
        self.hass.loop.call_later(2, lambda: self.hass.async_create_task(self._delayed_init()))

    def _get_localized_options(self, options: List[str]) -> List[str]:
        """Get localized versions of options."""
        if not self._localize_func:
            return options

        language = self.hass.config.language if self.hass else "en"
        _LOGGER.debug("Getting localized options for %s, language=%s", self._attr_translation_key, language)
        result = [self._localize_func(opt, language) for opt in options]
        _LOGGER.debug("Localized options: %s -> %s", options, result)
        return result

    def _localize_option(self, option: str) -> str:
        """Localize a single option."""
        if not self._localize_func:
            return option

        language = self.hass.config.language if self.hass else "en"
        return self._localize_func(option, language)

    def _get_saved_value(self) -> Optional[str]:
        """Get saved value from storage (internal key, not localized)."""
        if hasattr(self.coordinator, 'select_storage'):
            return self.coordinator.select_storage.get(self._storage_key)
        return None

    def _get_current_value(self) -> Optional[str]:
        """Get current value from coordinator data (internal key, not localized)."""
        if not self.coordinator.data:
            return None

        key_map = {9: "fan_speed", 10: "water_level", 15: "clean_mode"}
        value = self.coordinator.data.get(key_map.get(self._dp_id))

        if value and value in self._value_map:
            return value
        return None

    async def _delayed_init(self):
        """Delayed initialization after hass is ready."""
        try:
            saved_value = self._get_saved_value()
            current = self._get_current_value()

            if saved_value and saved_value != current and not self._initial_value_sent:
                await self._send_initial_value()
            elif not saved_value and not self._initial_value_sent:
                await self._send_initial_value()

        except Exception as e:
            _LOGGER.error("Error in delayed_init for %s: %s", self.entity_id, e)

    async def _send_initial_value(self):
        """Send initial value to device."""
        try:
            # Find the internal key for the current localized option
            internal_value = None
            for opt, val in self._value_map.items():
                if self._localize_option(opt) == self._attr_current_option:
                    internal_value = opt
                    break

            if internal_value and internal_value in self._value_map:
                value = self._value_map[internal_value]
                _LOGGER.info("Setting initial value for %s: %s (%s)", 
                            self._attr_translation_key, internal_value, value)
                await self.coordinator.vacuum.send_raw_command(self._dp_id, value)
                self._initial_value_sent = True
                await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Error setting initial value for %s: %s", self._attr_translation_key, e)

    async def async_select_option(self, option: str) -> None:
        """Select option."""
        # Find the internal key for the selected localized option
        internal_option = None
        for opt, val in self._value_map.items():
            if self._localize_option(opt) == option:
                internal_option = opt
                break

        if internal_option is None or internal_option not in self._value_map:
            _LOGGER.error("Invalid option: %s (available: %s)", 
                         option, [self._localize_option(opt) for opt in self._value_map.keys()])
            return

        value = self._value_map[internal_option]
        _LOGGER.info("Setting DP %s = %s (%s)", self._dp_id, value, internal_option)

        try:
            await self.coordinator.vacuum.send_raw_command(self._dp_id, value)
            self._attr_current_option = option
            self._initial_value_sent = True

            if hasattr(self.coordinator, 'select_storage'):
                await self.coordinator.select_storage.async_set(self._storage_key, internal_option)

            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Error setting option: %s", e)


class NeatsvorRoomSelect(CoordinatorEntity, SelectEntity):
    """Room selection for cleaning with saved state."""

    _attr_has_entity_name = True
    _attr_translation_key = "room_select"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = "neatsvor_room_select"
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:floor-plan"

        self._rooms: List[Dict[str, Any]] = []
        self._room_map: Dict[str, int] = {}
        self._attr_options = ["⏳ Loading..."]
        self._attr_current_option = None
        self.available_rooms = []

        self._saved_room = self._get_saved_value()

        if coordinator.vacuum:
            coordinator.vacuum.on_map(self._handle_map_update)

        asyncio.create_task(self._load_rooms_from_history())

        coordinator.room_select = self

    def _get_saved_value(self) -> Optional[str]:
        """Get saved room from storage."""
        if hasattr(self.coordinator, 'select_storage'):
            return self.coordinator.select_storage.get('last_room')
        return None

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        for i in range(10):
            if self._attr_options and self._attr_options != ["⏳ Loading..."]:
                break
            await asyncio.sleep(1)

        await self._restore_saved_room()

    async def async_update(self):
        """Update entity state."""
        await self._restore_saved_room()

    async def _restore_saved_room(self):
        """Restore saved room if available."""
        if not self._attr_options or self._attr_options == ["⏳ Loading..."] or self._attr_options == ["📭 No rooms available"]:
            return

        valid_options = [opt for opt in self._attr_options if opt not in ["⏳ Loading...", "📭 No rooms available"]]

        if valid_options:
            if self._saved_room and self._saved_room in valid_options:
                self._attr_current_option = self._saved_room
                _LOGGER.info("Restored saved room: %s", self._saved_room)
            elif not self._attr_current_option or self._attr_current_option not in valid_options:
                first_room = valid_options[0]
                self._attr_current_option = first_room
                _LOGGER.info("Auto-selected first room: %s", first_room)

            self.async_write_ha_state()

    async def _load_rooms_from_history(self):
        """Load rooms from history."""
        try:
            for attempt in range(3):
                rooms = await self.coordinator.vacuum.get_available_rooms(timeout=5)
                if rooms:
                    _LOGGER.info("Loaded %s rooms (attempt %s)", len(rooms), attempt + 1)
                    await self._update_rooms(rooms)
                    return
                await asyncio.sleep(2)

            _LOGGER.warning("No rooms found after 3 attempts")
        except Exception as e:
            _LOGGER.error("Error loading rooms from history: %s", e)

    async def _handle_map_update(self, map_data: dict):
        """Handle map update."""
        try:
            rooms = map_data.get('room_names', [])
            if rooms:
                _LOGGER.info("Received %s rooms from map", len(rooms))
                await self._update_rooms(rooms)
        except Exception as e:
            _LOGGER.error("Error processing map: %s", e)

    async def _update_rooms(self, rooms: List[Dict]):
        """Update room list."""
        if not rooms:
            return

        rooms = sorted(rooms, key=lambda x: x['id'])

        self._rooms = rooms
        self._room_map = {room['name']: room['id'] for room in rooms}
        self._attr_options = [room['name'] for room in rooms]
        self.available_rooms = rooms

        await self._restore_saved_room()

        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Start cleaning selected room."""
        if option not in self._room_map:
            _LOGGER.warning("Room '%s' not found in map: %s", option, list(self._room_map.keys()))
            return

        room_id = self._room_map[option]
        _LOGGER.info("Cleaning room: %s (ID: %s)", option, room_id)

        try:
            if hasattr(self.coordinator.vacuum, 'start_room_clean_with_preset'):
                _LOGGER.debug("Using start_room_clean_with_preset for room %s", room_id)
                await self.coordinator.vacuum.start_room_clean_with_preset([room_id])
            else:
                _LOGGER.debug("Using start_room_clean for room %s", room_id)
                await self.coordinator.vacuum.start_room_clean([room_id])

            self._attr_current_option = option

            if hasattr(self.coordinator, 'select_storage'):
                await self.coordinator.select_storage.async_set('last_room', option)
                self._saved_room = option

            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()

            if self.hass:
                self.hass.bus.async_fire("persistent_notification", {
                    "message": f"Cleaning room: {option}",
                    "title": "Neatsvor"
                })

            _LOGGER.info("Room cleaning started successfully for %s", option)

        except Exception as e:
            _LOGGER.error("Error starting cleaning for room %s: %s", option, e, exc_info=True)
            if self.hass:
                self.hass.bus.async_fire("persistent_notification", {
                    "message": f"Failed to clean room {option}: {e}",
                    "title": "Neatsvor Error"
                })

    @property
    def extra_state_attributes(self) -> dict:
        """Additional attributes."""
        return {
            'available_rooms': self._rooms,
            'room_count': len(self._rooms),
            'room_ids': list(self._room_map.values()),
            'room_names': list(self._room_map.keys())
        }


class NeatsvorCloudMapSelect(CoordinatorEntity, SelectEntity):
    """Select for cloud maps with saved state."""

    _attr_has_entity_name = True
    _attr_translation_key = "cloud_map_select"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = "neatsvor_cloud_map_select"
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:map-search"
        self._attr_options = ["⏳ Loading..."]
        self._attr_current_option = None
        self._map_options = {}

        self._saved_map_id = self._get_saved_value()

        _LOGGER.debug("CloudMapSelect initialized")

        coordinator.cloud_map_select = self

    def _get_saved_value(self) -> Optional[int]:
        """Get saved map ID from storage."""
        if hasattr(self.coordinator, 'select_storage'):
            saved = self.coordinator.select_storage.get('last_cloud_map')
            if saved:
                try:
                    return int(saved)
                except:
                    pass
        return None

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.debug("CloudMapSelect added to hass")

        asyncio.create_task(self._wait_for_cloud_maps())

    async def _wait_for_cloud_maps(self):
        """Wait for cloud_maps_sensor to be available."""
        for i in range(30):
            if hasattr(self.coordinator, 'cloud_maps_sensor') and self.coordinator.cloud_maps_sensor:
                _LOGGER.debug("Cloud maps sensor is now available for select")
                await self.async_update()
                break
            await asyncio.sleep(1)
        else:
            _LOGGER.warning("Cloud maps sensor not available after 30 seconds for select")

    async def async_update(self):
        """Update options from sensor."""
        if not self.hass:
            _LOGGER.debug("CloudMapSelect: skipping update - hass not set yet")
            return

        if not hasattr(self.coordinator, 'cloud_maps_sensor') or not self.coordinator.cloud_maps_sensor:
            _LOGGER.debug("CloudMapSelect: cloud_maps_sensor not ready yet")
            return

        sensor = self.coordinator.cloud_maps_sensor

        if not sensor._maps:
            _LOGGER.debug("No maps available in sensor")
            self._attr_options = ["📭 No maps available"]
            self._attr_current_option = None
            self.async_write_ha_state()
            return

        _LOGGER.info("Building select options from %s maps", len(sensor._maps))

        options = []
        self._map_options = {}

        for i, m in enumerate(sensor._maps):
            date_str = "N/A"
            if m.get('date'):
                try:
                    date_str = m['date'][:10]
                except:
                    date_str = "N/A"

            rooms = m.get('room_count', 0)
            area = m.get('area', 0)
            name = m.get('name', 'Unknown')

            option = f"[{date_str}] {area:.1f} m² ({rooms} rooms) - {name}"
            options.append(option)
            self._map_options[option] = m['id']

        self._attr_options = options

        if options:
            if self._saved_map_id:
                found = False
                for option, map_id in self._map_options.items():
                    if map_id == self._saved_map_id:
                        self._attr_current_option = option
                        _LOGGER.info("Restored saved cloud map: %s", option)
                        found = True
                        break

                if not found:
                    _LOGGER.warning("Saved map ID %s not found, selecting first", self._saved_map_id)
                    self._attr_current_option = options[0]
                    self._saved_map_id = self._map_options[options[0]]

                    if hasattr(self.coordinator, 'select_storage'):
                        await self.coordinator.select_storage.async_set('last_cloud_map', str(self._saved_map_id))
            else:
                first_option = options[0]
                first_id = self._map_options[first_option]
                self._attr_current_option = first_option
                self._saved_map_id = first_id
                _LOGGER.info("Auto-selected first cloud map: %s", first_option)

                if hasattr(self.coordinator, 'select_storage'):
                    await self.coordinator.select_storage.async_set('last_cloud_map', str(first_id))

            if sensor.selected_map_id != self._saved_map_id:
                await sensor.select_map(self._saved_map_id)

        self.async_write_ha_state()
        _LOGGER.info("Updated select with %s options", len(options))

    async def async_select_option(self, option: str) -> None:
        """Select map."""
        if option not in self._map_options:
            _LOGGER.error("Option not found. Available: %s", list(self._map_options.keys()))
            return

        map_id = self._map_options[option]
        _LOGGER.info("Selected map ID: %s", map_id)

        if hasattr(self.coordinator, 'cloud_maps_sensor') and self.coordinator.cloud_maps_sensor:
            if await self.coordinator.cloud_maps_sensor.select_map(map_id):
                self._attr_current_option = option
                self._saved_map_id = map_id

                if hasattr(self.coordinator, 'select_storage'):
                    await self.coordinator.select_storage.async_set('last_cloud_map', str(map_id))

                self.async_write_ha_state()
                _LOGGER.info("Map selection successful")
            else:
                _LOGGER.error("Failed to select map ID %s", map_id)
        else:
            _LOGGER.error("No cloud_maps_sensor in coordinator")

    @property
    def extra_state_attributes(self) -> dict:
        """Additional attributes."""
        return {
            'map_options': self._map_options,
            'current_map_id': self._map_options.get(self._attr_current_option) if self._attr_current_option else None,
            'saved_map_id': self._saved_map_id
        }


class NeatsvorCleanHistorySelect(CoordinatorEntity, SelectEntity):
    """Select for clean history records."""

    _attr_has_entity_name = True
    _attr_translation_key = "clean_history_select"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = "neatsvor_clean_history_select"
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:history"
        self._attr_options = ["⏳ Loading..."]
        self._attr_current_option = None
        self._record_options = {}  # option -> record_id
        self._record_map = {}  # record_id -> option

        self._saved_record_id = self._get_saved_value()
        _LOGGER.debug("CleanHistorySelect initialized")
        coordinator.clean_history_select = self

    def _get_saved_value(self) -> Optional[int]:
        """Get saved record ID from storage."""
        if hasattr(self.coordinator, 'select_storage'):
            saved = self.coordinator.select_storage.get('last_clean_history')
            if saved:
                try:
                    return int(saved)
                except:
                    pass
        return None

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        await asyncio.sleep(2)
        await self.async_update()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.hass.async_create_task(self.async_update())

async def async_update(self):
    """Update options from sensor."""
    if not self.hass:
        return

    if not hasattr(self.coordinator, 'clean_history_sensor') or not self.coordinator.clean_history_sensor:
        self._attr_options = ["⏳ Waiting for sensor..."]
        self._attr_current_option = None
        self.async_write_ha_state()
        return

    sensor = self.coordinator.clean_history_sensor

    if not hasattr(sensor, '_records'):
        self._attr_options = ["⏳ Initializing..."]
        self._attr_current_option = None
        self.async_write_ha_state()
        return

    if not sensor._records:
        self._attr_options = ["📭 No history records"]
        self._attr_current_option = None
        self.async_write_ha_state()
        return

    _LOGGER.info("Building select options from %s records", len(sensor._records))

    options = []
    self._record_options = {}
    self._record_map = {}

    for record in sensor._records:
        time_str = record['clean_time'][:16] if len(record['clean_time']) > 16 else record['clean_time']
        check = "✓" if record['finished'] else "⚠"
        option = f"[{time_str}] {record['clean_area']}m² ({record['clean_duration']}min) {check}"
        options.append(option)
        self._record_options[option] = record['record_id']
        self._record_map[record['record_id']] = option

    self._attr_options = options

    if options:
        # Restore saved selection if available
        if self._saved_record_id and self._saved_record_id in self._record_map:
            saved_option = self._record_map[self._saved_record_id]
            self._attr_current_option = saved_option
            _LOGGER.info("Restored saved record: %s", saved_option)

            if sensor.selected_record_id != self._saved_record_id:
                sensor.selected_record_id = self._saved_record_id
                sensor.async_write_ha_state()
        else:
            # Автоматически выбираем первую запись, если нет сохранённой
            first_option = options[0]
            first_record_id = self._record_options[first_option]
            self._attr_current_option = first_option
            self._saved_record_id = first_record_id
            _LOGGER.info("Auto-selected first record: %s", first_option)

            # Сохраняем выбор
            if hasattr(self.coordinator, 'select_storage'):
                await self.coordinator.select_storage.async_set('last_clean_history', str(first_record_id))

            # Уведомляем сенсор о выборе (без загрузки карты)
            if sensor.selected_record_id != first_record_id:
                sensor.selected_record_id = first_record_id
                sensor.async_write_ha_state()

    self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Select record - user selected a record."""
        if option not in self._record_options:
            _LOGGER.error("Option not found: %s", option)
            return

        record_id = self._record_options[option]
        _LOGGER.info("Selected record ID: %s", record_id)

        if hasattr(self.coordinator, 'clean_history_sensor') and self.coordinator.clean_history_sensor:
            # Call select_record which will load the map
            if await self.coordinator.clean_history_sensor.select_record(record_id):
                self._attr_current_option = option
                self._saved_record_id = record_id

                # Save selection
                if hasattr(self.coordinator, 'select_storage'):
                    await self.coordinator.select_storage.async_set('last_clean_history', str(record_id))

                self.async_write_ha_state()
                _LOGGER.info("Record selection successful")