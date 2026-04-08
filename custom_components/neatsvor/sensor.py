"""Sensor platform for Neatsvor."""

from __future__ import annotations

import logging
import asyncio
from typing import Any, Optional, Dict, List
from pathlib import Path
from datetime import datetime

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime, UnitOfArea
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    get_localized_status,
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
    """Set up Neatsvor sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Battery sensor
    entities.append(NeatsvorBatterySensor(coordinator))

    # ============= MQTT sensors =============
    mqtt_sensors = [
        SensorEntityDescription(
            key="status",
            translation_key="status",
            name="Status",
            icon="mdi:information",
        ),
        SensorEntityDescription(
            key="clean_time",
            translation_key="current_clean_time",
            name="Current Clean Time",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            device_class=SensorDeviceClass.DURATION,
            icon="mdi:timer",
        ),
        SensorEntityDescription(
            key="clean_area",
            translation_key="current_clean_area",
            name="Current Clean Area",
            native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
            device_class=SensorDeviceClass.AREA,
            icon="mdi:floor-plan",
        ),
        SensorEntityDescription(
            key="fan_speed",
            translation_key="fan_speed",
            name="Fan Speed",
            icon="mdi:fan",
        ),
        SensorEntityDescription(
            key="water_level",
            translation_key="water_level",
            name="Water Level",
            icon="mdi:water",
        ),
        SensorEntityDescription(
            key="clean_mode",
            translation_key="clean_mode",
            name="Clean Mode",
            icon="mdi:broom",
        ),
    ]

    for description in mqtt_sensors:
        entities.append(NeatsvorSensor(coordinator, description, "mqtt"))

    # ============= REST sensors =============
    rest_sensors = [
        SensorEntityDescription(
            key="filter",
            translation_key="filter",
            name="HEPA Filter",
            native_unit_of_measurement=PERCENTAGE,
            icon="mdi:air-filter",
        ),
        SensorEntityDescription(
            key="side_brush",
            translation_key="side_brush",
            name="Side Brush",
            native_unit_of_measurement=PERCENTAGE,
            icon="mdi:brush",
        ),
        SensorEntityDescription(
            key="main_brush",
            translation_key="main_brush",
            name="Main Brush",
            native_unit_of_measurement=PERCENTAGE,
            icon="mdi:brush-outline",
        ),
        SensorEntityDescription(
            key="software_version",
            translation_key="software_version",
            name="Software Version",
            icon="mdi:chip",
        ),
        SensorEntityDescription(
            key="mac_address",
            translation_key="mac_address",
            name="MAC Address",
            icon="mdi:network",
        ),
        SensorEntityDescription(
            key="device_pid",
            translation_key="device_pid",
            name="Device PID",
            icon="mdi:identifier",
        ),
        SensorEntityDescription(
            key="total_cleanings",
            translation_key="total_cleanings",
            name="Total Cleanings",
            icon="mdi:counter",
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        SensorEntityDescription(
            key="total_clean_time",
            translation_key="total_clean_time",
            name="Total Clean Time",
            native_unit_of_measurement=UnitOfTime.HOURS,
            icon="mdi:clock-outline",
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        SensorEntityDescription(
            key="total_clean_area",
            translation_key="total_clean_area",
            name="Total Clean Area",
            native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
            icon="mdi:sigma",
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        SensorEntityDescription(
            key="last_clean_time",
            translation_key="last_clean_time",
            name="Last Clean",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:calendar-clock",
        ),
        SensorEntityDescription(
            key="last_clean_duration",
            translation_key="last_clean_duration",
            name="Last Clean Duration",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            icon="mdi:clock-outline",
        ),
        SensorEntityDescription(
            key="last_clean_area",
            translation_key="last_clean_area",
            name="Last Clean Area",
            native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
            icon="mdi:floor-plan",
        ),
    ]

    for description in rest_sensors:
        entities.append(NeatsvorSensor(coordinator, description, "rest"))

    # Malfunction sensor (Ошибка с детализацией)
    entities.append(NeatsvorMalfunctionSensor(coordinator))
    _LOGGER.info("Added malfunction sensor")

    # Cloud maps sensor
    if hasattr(coordinator.vacuum, 'cloud_maps'):
        cloud_maps_sensor = NeatsvorCloudMapsSensor(coordinator)
        entities.append(cloud_maps_sensor)
        coordinator.cloud_maps_sensor = cloud_maps_sensor
        _LOGGER.info("Added cloud maps sensor")

    # Room sensors
    if hasattr(coordinator.vacuum, 'get_available_rooms'):
        entities.append(NeatsvorRoomPresetSensor(coordinator))
        entities.append(NeatsvorRoomListSensor(coordinator))
        _LOGGER.info("Added room sensors")

    # Clean history sensor
    if hasattr(coordinator.vacuum, 'clean_history'):
        clean_history_sensor = NeatsvorCleanHistorySensor(coordinator)
        entities.append(clean_history_sensor)
        coordinator.clean_history_sensor = clean_history_sensor
        _LOGGER.info("Added clean history sensor")

    # Map sensor
    entities.append(NeatsvorMapSensor(coordinator))
    _LOGGER.info("Added map sensor")

    # Preset sensors
    entities.append(NeatsvorCurrentMapPresetSensor(coordinator))
    entities.append(NeatsvorCloudMapPresetSensor(coordinator))
    entities.append(NeatsvorPresetComparisonSensor(coordinator))
    _LOGGER.info("Added preset sensors")
    
    # Maintenance sensor for Yandex Smart Home
    entities.append(NeatsvorMaintenanceSensor(coordinator))
    _LOGGER.info("Added maintenance sensor for Yandex Smart Home")    

    async_add_entities(entities)
    _LOGGER.info("Created %s sensors", len(entities))


class NeatsvorBatterySensor(CoordinatorEntity, SensorEntity):
    """Battery sensor with dynamic icon."""

    _attr_has_entity_name = True
    _attr_translation_key = "battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = "neatsvor_battery"
        self._attr_device_info = coordinator.device_info
        self._cached_value = None

    @property
    def native_value(self) -> int | None:
        """Return battery level with cache."""
        if not self.coordinator.data:
            return self._cached_value

        value = self.coordinator.data.get("battery_level")
        self._cached_value = value
        return value

    @property
    def icon(self) -> str:
        """Return dynamic icon based on charging state and battery level."""
        battery = self.native_value

        if battery is None:
            return "mdi:battery-unknown"

        charging = False
        if self.coordinator.data and self.coordinator.data.get("status_text"):
            status_text = self.coordinator.data.get("status_text", "").lower()
            charging_states = ["charging", "charge_finished", "docked"]
            charging = any(state in status_text for state in charging_states)

        if charging:
            return "mdi:battery-charging"

        if battery >= 90:
            return "mdi:battery"
        elif battery >= 70:
            return "mdi:battery-90"
        elif battery >= 50:
            return "mdi:battery-70"
        elif battery >= 30:
            return "mdi:battery-50"
        elif battery >= 10:
            return "mdi:battery-30"
        elif battery > 0:
            return "mdi:battery-10"
        else:
            return "mdi:battery-outline"

    @property
    def available(self) -> bool:
        """Return if sensor is available."""
        if not self.coordinator.data:
            return False
        return self.native_value is not None


class NeatsvorSensor(CoordinatorEntity, SensorEntity):
    """Universal Neatsvor sensor with localization support."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, description: SensorEntityDescription, source: str):
        """Initialize with universal naming."""
        super().__init__(coordinator)
        self.entity_description = description
        self._source = source

        self._attr_unique_id = f"neatsvor_{description.key}"
        if hasattr(description, 'translation_key'):
            self._attr_translation_key = description.translation_key
        self._attr_device_info = coordinator.device_info

        # Cache for values when coordinator is unavailable
        self._cached_value = None

    def _get_localized_value(self, key: str, value: Any) -> Any:
        """Get localized value for specific keys."""
        if value is None:
            return None

        language = self.hass.config.language if self.hass else "en"

        if key == "status":
            return get_localized_status(value.lower(), language)
        elif key == "fan_speed":
            return get_localized_fan_speed(value, language)
        elif key == "water_level":
            return get_localized_water_level(value, language)
        elif key == "clean_mode":
            return get_localized_clean_mode(value, language)

        return value

    def _get_status_with_error_details(self, status_code: int, error_code: int) -> str:
        """Get status string with error details if applicable."""
        language = self.hass.config.language if self.hass else "en"
        
        # Status mapping
        status_map = {
            0: "idle", 1: "relocation", 2: "upgrading", 3: "building_map",
            4: "paused", 5: "returning", 6: "charging", 7: "charged",
            8: "cleaning", 9: "zone_cleaning", 10: "room_cleaning",
            11: "spot_cleaning", 12: "manual", 13: "error",
            14: "sleeping", 15: "dust_collecting",
            50: "washing_mop", 51: "filling_water", 52: "drying_mop",
            53: "station_cleaning", 54: "returning_to_wash",
        }
        
        status_key = status_map.get(status_code, "unknown")
        
        # If not an error, return localized status
        if status_code != 13:
            return get_localized_status(status_key, language)
        
        # It's an error - add details
        error_map_ru = {
            0: "Нет ошибки",
            1: "Неизвестная ошибка",
            2: "Запутывание колеса",
            3: "Запутывание боковой щетки",
            4: "Запутывание основной щетки",
            5: "Колесо зависло",
            6: "Бампер застрял",
            7: "Ошибка датчика перепада высот",
            8: "Неисправность бака",
            9: "Нет контейнера для пыли",
            10: "Не может найти базу",
            11: "Неисправность камеры",
            12: "Неисправность лидара",
            13: "Лидар застрял",
            14: "Низкий заряд",
            15: "Включите выключатель",
            16: "Неисправность вентилятора",
            17: "Робот застрял",
            18: "Контейнер для пыли полон",
            19: "Зона недоступна",
            20: "Бак чистой воды не установлен",
            21: "Контейнер для пыли не установлен",
            22: "Нет воды в баке",
            23: "Бак грязной воды не установлен",
            24: "Бак грязной воды полон",
            25: "Паллет не установлен",
            26: "Швабра не установлена",
            27: "Запутывание швабры",
            28: "Паллет полон",
            29: "Недостаточно моющего средства",
            50: "Старт на ковре",
            51: "Неисправность батареи",
        }
        
        error_map_en = {
            0: "No error",
            1: "Unknown error",
            2: "Wheel winded",
            3: "Side brush winded",
            4: "Rolling brush winded",
            5: "Wheel suspended",
            6: "Bumper stuck",
            7: "Cliff sensor error",
            8: "Tank malfunction",
            9: "No dust box",
            10: "Cannot find dock",
            11: "Camera malfunction",
            12: "Lidar malfunction",
            13: "Lidar stuck",
            14: "Low power",
            15: "Turn on the switch",
            16: "Fan malfunction",
            17: "Robot trap",
            18: "Dust box full",
            19: "Destination unreachable",
            20: "Clean tank uninstall",
            21: "Dust box uninstall",
            22: "Clean tank lack water",
            23: "Sewage tank uninstall",
            24: "Sewage tank full",
            25: "Pallet uninstall",
            26: "Mop uninstall",
            27: "Mop winded",
            28: "Pallet water full",
            29: "Soap shortage",
            50: "Start on carpet",
            51: "Battery malfunction",
        }
        
        if language == "ru":
            error_text = error_map_ru.get(error_code, f"Неизвестная ошибка ({error_code})")
            return f"Ошибка: {error_text}"
        else:
            error_text = error_map_en.get(error_code, f"Unknown error ({error_code})")
            return f"Error: {error_text}"

    @property
    def native_value(self) -> Optional[Any]:
        """Return sensor value with localization and cache fallback."""
        if not self.coordinator.data:
            if hasattr(self, '_cached_value') and self._cached_value is not None:
                _LOGGER.debug("Using cached value for %s: %s", self.entity_description.key, self._cached_value)
                return self._cached_value
            return None

        data = self.coordinator.data
        key = self.entity_description.key

        value = None
        if self._source == "mqtt":
            if key == "status":
                status_code = data.get("status_code")
                error_code = data.get("malfunction_code", 0)
                # Use enhanced status with error details
                value = self._get_status_with_error_details(status_code, error_code)
            elif key == "clean_time":
                value = data.get("current_clean_time")
            elif key == "clean_area":
                value = data.get("current_clean_area")
            elif key == "fan_speed":
                value = data.get("fan_speed")
                value = self._get_localized_value(key, value)
            elif key == "water_level":
                value = data.get("water_level")
                value = self._get_localized_value(key, value)
            elif key == "clean_mode":
                value = data.get("clean_mode")
                value = self._get_localized_value(key, value)

        elif self._source == "rest":
            consumables = data.get("consumables", {})
            if key in ["filter", "side_brush", "main_brush"]:
                cons = consumables.get(key)
                value = cons.get("remaining_percent") if cons else None

            elif key == "software_version":
                value = data.get("software_version")
            elif key == "mac_address":
                value = data.get("mac_address")
            elif key == "device_pid":
                value = data.get("device_pid")

            stats = data.get("statistics", {})
            if key == "total_cleanings":
                value = stats.get("total_cleanings")
            elif key == "total_clean_time":
                value = stats.get("total_clean_time")
            elif key == "total_clean_area":
                value = stats.get("total_clean_area")

            last = data.get("last_clean", {})
            if key == "last_clean_time":
                value = last.get("clean_time")
            elif key == "last_clean_duration":
                value = last.get("clean_duration")
            elif key == "last_clean_area":
                value = last.get("clean_area")

        # Cache the value
        self._cached_value = value
        return value

    @property
    def available(self) -> bool:
        """Return if sensor is available."""
        if not self.coordinator.data:
            return False
        return self.native_value is not None

    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return additional attributes."""
        if not self.coordinator.data:
            return None

        key = self.entity_description.key

        if key in ["filter", "side_brush", "main_brush"]:
            consumables = self.coordinator.data.get("consumables", {})
            cons = consumables.get(key)
            if cons:
                return {
                    "remaining_hours": cons.get("remaining_hours"),
                    "limit_hours": cons.get("limit_hours"),
                    "consumable_id": cons.get("id"),
                }

        return None
        

class NeatsvorMapSensor(CoordinatorEntity, SensorEntity):
    """Sensor containing all map data as attributes."""

    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = "neatsvor_map_data"
        #self._attr_name = "Map Data"
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:map"
        self._attr_native_value = "0 rooms"

        self._map_image: Optional[bytes] = None
        self._map_path: Optional[str] = None
        self._last_update: Optional[datetime] = None

        self._rooms: List[Dict[str, Any]] = []
        self._room_presets: Dict[int, Dict[str, Any]] = {}

        self._width: int = 0
        self._height: int = 0
        self._resolution: int = 0
        self._robot_position: Optional[Dict[str, int]] = None
        self._charger_position: Optional[Dict[str, int]] = None

        if coordinator.vacuum:
            coordinator.vacuum.on_map(self._async_handle_map)

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator."""
        self.async_write_ha_state()

    async def _async_handle_map(self, map_data: Dict[str, Any]) -> None:
        """Handle new map data."""
        try:
            _LOGGER.debug("Processing map: %sx%s", map_data.get('width', 0), map_data.get('height', 0))

            self._width = map_data.get('width', 0)
            self._height = map_data.get('height', 0)
            self._resolution = map_data.get('resolution', 0)

            self._robot_position = map_data.get('robot_position')
            self._charger_position = map_data.get('charger_position')

            room_names = map_data.get('room_names', [])
            rooms_dict = map_data.get('rooms', {})

            self._rooms = []
            resolution_m = self._resolution / 1000.0 if self._resolution else 0.05

            for room in room_names:
                room_id = room['id']
                cells = rooms_dict.get(room_id, [])
                area = len(cells) * (resolution_m ** 2)

                self._rooms.append({
                    'id': room_id,
                    'name': room['name'],
                    'area': round(area, 2),
                    'cell_count': len(cells)
                })

            self._room_presets = {}
            if 'raw' in map_data and hasattr(map_data['raw'], 'room_info'):
                raw = map_data['raw']
                if hasattr(raw.room_info, 'room_attrs'):
                    for attr in raw.room_info.room_attrs:
                        self._room_presets[attr.room_id] = {
                            'fan': attr.fan_level,
                            'water': attr.tank_level,
                            'times': attr.clean_times,
                            'mode': attr.clean_mode
                        }

            if hasattr(self.coordinator.vacuum, 'visualizer'):
                filename = await self.coordinator.vacuum.visualizer.render_static_map(
                    map_data,
                    title=f"map_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    map_type="realtime"
                )

                if filename and Path(filename).exists():
                    self._map_path = filename
                    import aiofiles
                    async with aiofiles.open(filename, 'rb') as f:
                        self._map_image = await f.read()

            self._last_update = datetime.now()
            self._attr_native_value = f"{len(self._rooms)} rooms"

            _LOGGER.info("Map processed: %s rooms, %s presets", len(self._rooms), len(self._room_presets))

            self.async_write_ha_state()

        except Exception as e:
            _LOGGER.error("Error processing map: %s", e, exc_info=True)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes."""
        attrs = super().extra_state_attributes
        if attrs is None:
            attrs = {}

        rooms_with_presets = []
        for room in self._rooms:
            room_id = room['id']
            preset = self._room_presets.get(room_id, {
                'fan': 2,
                'water': 2,
                'times': 1,
                'mode': 2
            })

            fan_names = {1: "Quiet", 2: "Normal", 3: "Strong", 4: "Max"}
            water_names = {1: "Low", 2: "Middle", 3: "High"}

            rooms_with_presets.append({
                **room,
                'preset': preset,
                'preset_names': {
                    'fan': fan_names.get(preset.get('fan', 2), "Normal"),
                    'water': water_names.get(preset.get('water', 2), "Middle"),
                    'times': preset.get('times', 1)
                }
            })

        attrs.update({
            'width': self._width,
            'height': self._height,
            'resolution': self._resolution,
            'last_update': self._last_update.isoformat() if self._last_update else None,
            'rooms': rooms_with_presets,
            'room_count': len(self._rooms),
            'room_names': [r['name'] for r in self._rooms],
            'room_ids': [r['id'] for r in self._rooms],
            'room_presets': self._room_presets,
            'robot_position': self._robot_position,
            'charger_position': self._charger_position,
            'map_path': self._map_path,
        })

        return attrs

    @property
    def entity_picture(self) -> Optional[str]:
        """Return URL of map image."""
        if self._map_path and Path(self._map_path).exists():
            path = Path(self._map_path)
            if '/config/www/' in str(path):
                return f"/local/{str(path.relative_to('/config/www'))}"
        return None


class NeatsvorCloudMapsSensor(CoordinatorEntity, SensorEntity):
    """Sensor for cloud maps list."""
    _attr_has_entity_name = True
    _attr_translation_key = "cloud_maps"

    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = "neatsvor_cloud_maps"
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:cloud-outline"
        self._attr_native_value = "0"

        self._maps = []
        self.selected_map_id = None
        self._reference_map_id = None
        _LOGGER.debug("CloudMapsSensor initialized")

        coordinator.cloud_maps_sensor = self

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.debug("CloudMapsSensor added to hass")

        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

        await self.async_update()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.hass.async_create_task(self.async_update())

    async def async_force_update(self):
        """Force update of maps and presets."""
        _LOGGER.info("Force updating cloud maps...")
        await self.async_update()

        if hasattr(self.coordinator, 'cloud_map_presets'):
            await self.coordinator.cloud_map_presets.async_update()

        if hasattr(self.coordinator, 'preset_comparison'):
            await self.coordinator.preset_comparison.async_update()

    async def async_update(self):
        """Update maps list."""
        _LOGGER.debug("CloudMapsSensor.async_update() called")

        if not self.coordinator.vacuum:
            _LOGGER.error("Vacuum not initialized")
            return

        if not hasattr(self.coordinator.vacuum, 'cloud_maps'):
            _LOGGER.error("Vacuum has no cloud_maps attribute")
            return

        if not self.coordinator.vacuum.info:
            _LOGGER.error("Vacuum info not available")
            return

        try:
            device_id = self.coordinator.vacuum.info.device_id
            _LOGGER.info("Loading cloud maps for device %s...", device_id)

            maps = await self.coordinator.vacuum.cloud_maps.get_map_list(device_id, 20)

            if maps is None:
                _LOGGER.error("get_map_list returned None")
                return

            if not maps:
                _LOGGER.warning("No cloud maps found (empty list)")
                self._maps = []
                self._attr_native_value = "0"
                self.async_write_ha_state()
                if hasattr(self.coordinator, 'cloud_map_select') and self.coordinator.cloud_map_select:
                    await self.coordinator.cloud_map_select.async_update()
                return

            _LOGGER.info("Received %s maps from API", len(maps))

            self._maps = []
            for i, m in enumerate(maps):
                map_info = {
                    'id': m.device_map_id,
                    'map_id': m.map_id,
                    'name': m.name,
                    'area': round(m.area_m2, 1),
                    'date': m.clean_date.isoformat() if m.clean_date else None,
                    'local_path': m.downloaded_path,
                    'png_path': m.png_path,
                    'png_url': m.png_url,
                    'room_count': m.room_count,
                    'width': m.width,
                    'height': m.height,
                    'dev_map_url': m.dev_map_url,
                    'dev_map_md5': m.dev_map_md5,
                    'json_path': str(self.coordinator.vacuum.cloud_maps._get_json_path(m)) if hasattr(self.coordinator.vacuum.cloud_maps, '_get_json_path') else None,
                }
                self._maps.append(map_info)
                _LOGGER.debug("Map %s: ID=%s, name=%s, rooms=%s, png=%s", i + 1, m.device_map_id, m.name, m.room_count, m.png_url)

            self._attr_native_value = str(len(self._maps))
            _LOGGER.info("Updated %s maps in sensor", len(self._maps))

            if self._maps:
                for map_info in self._maps:
                    if not map_info.get('local_path'):
                        _LOGGER.info("Scheduling background download for map %s", map_info['id'])
                        asyncio.create_task(self._download_map_background(map_info['id']))

            if hasattr(self.coordinator, 'cloud_map_select') and self.coordinator.cloud_map_select:
                _LOGGER.debug("Updating select")
                await self.coordinator.cloud_map_select.async_update()

            if hasattr(self.coordinator, 'cloud_map_image') and self.coordinator.cloud_map_image:
                _LOGGER.debug("Updating image")
                self.coordinator.cloud_map_image.async_write_ha_state()

        except Exception as e:
            _LOGGER.error("Error loading maps: %s", e, exc_info=True)

    async def _prefetch_nearby_maps(self, current_index: int):
        """Prefetch nearby maps for faster switching."""
        if not hasattr(self.coordinator, 'cloud_map_camera'):
            return

        camera = self.coordinator.cloud_map_camera

        # Prefetch the next map
        if current_index > 0:
            prev_map = self._maps[current_index - 1]
            await self._prefetch_single_map(prev_map['id'])

        # Prefetch the previous map
        if current_index < len(self._maps) - 1:
            next_map = self._maps[current_index + 1]
            await self._prefetch_single_map(next_map['id'])

    async def _prefetch_single_map(self, map_id: int):
        """Prefetch a single map."""
        if not hasattr(self.coordinator, 'cloud_map_camera'):
            return

        camera = self.coordinator.cloud_map_camera

        # Find the map
        map_info = None
        for m in self._maps:
            if m['id'] == map_id:
                map_info = m
                break

        if not map_info:
            return

        # If PNG already exists
        if map_info.get('png_path'):
            try:
                import aiofiles
                from pathlib import Path
                png_path = Path(map_info['png_path'])
                if png_path.exists():
                    async with aiofiles.open(png_path, 'rb') as f:
                        png_bytes = await f.read()

                    # Store in camera prefetch
                    camera.prefetch_image(map_id, png_bytes)
                    _LOGGER.debug("Prefetched map %s", map_id)
            except Exception as e:
                _LOGGER.error("Error prefetching map %s: %s", map_id, e)

    async def _download_map_background(self, map_id: int):
        """Download map in background."""
        try:
            map_info = None
            for m in self._maps:
                if m['id'] == map_id:
                    map_info = m
                    break

            if not map_info:
                return

            maps = await self.coordinator.vacuum.cloud_maps.get_map_list(
                self.coordinator.vacuum.info.device_id, 20
            )
            target_map = next((m for m in maps if m.device_map_id == map_id), None)

            if target_map:
                _LOGGER.info("Background downloading map %s", map_id)
                result = await self.coordinator.vacuum.cloud_maps.download_map(target_map)
                if result:
                    await self.update_map_info(map_id, result)
                    _LOGGER.info("Background downloaded map %s", map_id)
        except Exception as e:
            _LOGGER.error("Error background downloading map %s: %s", map_id, e)

    async def select_map(self, map_id: int) -> bool:
        """Select map by ID."""
        _LOGGER.info("select_map(%s) called", map_id)

        for i, m in enumerate(self._maps):
            if m['id'] == map_id:
                self.selected_map_id = map_id
                self.async_write_ha_state()
                _LOGGER.info("Selected map: %s (ID: %s)", m['name'], map_id)

                # Prefetch nearby maps
                asyncio.create_task(self._prefetch_nearby_maps(i))

                if hasattr(self.coordinator, 'cloud_map_camera'):
                    _LOGGER.debug("Updating camera after selection")
                    self.coordinator.cloud_map_camera.async_write_ha_state()

                return True

        _LOGGER.warning("Map ID %s not found in %s", map_id, [m['id'] for m in self._maps])
        return False

    async def use_selected_cloud_map(self) -> bool:
        """Use the currently selected cloud map as the current map on the robot."""
        if not self.selected_map_id:
            _LOGGER.warning("No map selected to use")
            if self.hass:
                self.hass.bus.async_fire("persistent_notification", {
                    "message": "Please select a map first",
                    "title": "Neatsvor"
                })
            return False

        _LOGGER.info("Activating selected map %s on robot", self.selected_map_id)

        for m in self._maps:
            if m['id'] == self.selected_map_id:
                if m.get('app_map_url') and m.get('app_map_md5'):
                    _LOGGER.info("Sending map %s to robot using app URL", self.selected_map_id)
                    success = await self.coordinator.vacuum.use_cloud_map(
                        self.selected_map_id,
                        m['app_map_url'],
                        m['app_map_md5']
                    )
                else:
                    _LOGGER.info("Sending map %s to robot using dev URL (fallback)", self.selected_map_id)
                    success = await self.coordinator.vacuum.use_cloud_map(
                        self.selected_map_id,
                        m['dev_map_url'],
                        m['dev_map_md5']
                    )

                if success:
                    _LOGGER.info("Map %s activated successfully", self.selected_map_id)
                    if self.hass:
                        self.hass.bus.async_fire("persistent_notification", {
                            "message": "Map activated successfully",
                            "title": "Neatsvor"
                        })
                    return True
                else:
                    _LOGGER.error("Failed to activate map %s", self.selected_map_id)
                    if self.hass:
                        self.hass.bus.async_fire("persistent_notification", {
                            "message": "Failed to activate map",
                            "title": "Neatsvor"
                        })
                    return False

        _LOGGER.warning("Selected map ID %s not found in maps list", self.selected_map_id)
        return False

    def set_reference_map(self, map_id: int) -> bool:
        """Set map as reference."""
        for m in self._maps:
            if m['id'] == map_id:
                self._reference_map_id = map_id
                self.async_write_ha_state()
                _LOGGER.info("Reference map set to: %s (ID: %s)", m['name'], map_id)
                return True
        _LOGGER.warning("Map ID %s not found for reference", map_id)
        return False

    async def update_map_info(self, map_id: int, map_data: dict) -> None:
        """Update map information after download."""
        for m in self._maps:
            if m['id'] == map_id:
                m['room_count'] = map_data.get('room_count', 0)
                m['local_path'] = map_data.get('bv_path')
                m['png_path'] = map_data.get('png_path')
                m['png_url'] = map_data.get('png_url')
                m['width'] = map_data.get('width', 0)
                m['height'] = map_data.get('height', 0)
                _LOGGER.info("Updated map %s with %s rooms, PNG at %s", map_id, m['room_count'], m['png_path'])
                break

        self.async_write_ha_state()

        if hasattr(self.coordinator, 'cloud_map_select') and self.coordinator.cloud_map_select:
            await self.coordinator.cloud_map_select.async_update()

        if hasattr(self.coordinator, 'cloud_map_camera') and self.coordinator.cloud_map_camera:
            _LOGGER.debug("Updating camera after map update")
            if hasattr(self.coordinator.cloud_map_camera, 'async_update_image'):
                await self.coordinator.cloud_map_camera.async_update_image()
            else:
                self.coordinator.cloud_map_camera.async_write_ha_state()

    def get_map_by_id(self, map_id: int) -> dict | None:
        """Get map by ID."""
        for m in self._maps:
            if m['id'] == map_id:
                return m
        return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        attrs = {
            'maps': self._maps,
            'selected': self.selected_map_id,
            'total': len(self._maps)
        }

        if self._reference_map_id:
            attrs['reference'] = self._reference_map_id

        if self.selected_map_id:
            selected = self.get_map_by_id(self.selected_map_id)
            if selected:
                attrs['selected_name'] = selected['name']
                attrs['selected_area'] = selected['area']
                attrs['selected_date'] = selected['date']
                attrs['selected_rooms'] = selected['room_count']
                attrs['selected_app_map_url'] = selected.get('app_map_url')
                attrs['selected_app_map_md5'] = selected.get('app_map_md5')
                attrs['selected_dev_map_url'] = selected.get('dev_map_url')
                attrs['selected_dev_map_md5'] = selected.get('dev_map_md5')
                if selected.get('png_url'):
                    attrs['png_url'] = selected['png_url']

        return attrs


class NeatsvorRoomPresetSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing room cleaning presets."""
    _attr_has_entity_name = True
    _attr_translation_key = "room_presets"
    
    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = "neatsvor_room_presets"
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:tune"
        self._attr_native_value = "0 presets"
        self._presets = {}
        self._rooms = []

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        await self._update_presets()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.hass.async_create_task(self._update_presets())

    async def _update_presets(self):
        """Update presets from vacuum."""
        if not self.coordinator.vacuum:
            return

        try:
            if hasattr(self.coordinator.vacuum, '_current_map_metadata'):
                metadata = self.coordinator.vacuum._current_map_metadata
                if metadata and metadata.rooms:
                    self._presets = metadata.room_presets
                    self._rooms = [r.to_dict() for r in metadata.rooms.values()]
                    self._attr_native_value = f"{len(self._presets)} presets"
                    _LOGGER.debug("Loaded %s presets from MapProcessor", len(self._presets))
                    self.async_write_ha_state()
                    return

            if hasattr(self.coordinator.vacuum, '_map_data') and self.coordinator.vacuum._map_data:
                map_data = self.coordinator.vacuum._map_data
                if 'raw' in map_data and hasattr(map_data['raw'], 'room_info'):
                    raw = map_data['raw']
                    if hasattr(raw.room_info, 'room_attrs'):
                        self._presets = {}
                        self._rooms = []

                        room_names = {r['id']: r['name'] for r in map_data.get('room_names', [])}

                        for attr in raw.room_info.room_attrs:
                            room_id = attr.room_id
                            room_name = room_names.get(room_id, f"Room {room_id}")

                            preset = {
                                'fan': attr.fan_level,
                                'water': attr.tank_level,
                                'times': attr.clean_times,
                                'mode': attr.clean_mode
                            }
                            self._presets[room_id] = preset

                            self._rooms.append({
                                'id': room_id,
                                'name': room_name,
                                'preset': preset
                            })

                        self._attr_native_value = f"{len(self._presets)} presets"
                        _LOGGER.info("Loaded %s presets from raw data", len(self._presets))
                        self.async_write_ha_state()

        except Exception as e:
            _LOGGER.error("Error updating room presets: %s", e, exc_info=True)

    @property
    def extra_state_attributes(self) -> dict:
        """Return presets."""
        attrs = {
            'presets': self._presets,
            'rooms': self._rooms,
            'preset_count': len(self._presets)
        }

        formatted = []
        fan_map = {1: "Quiet", 2: "Normal", 3: "Strong", 4: "Max"}
        water_map = {1: "Low", 2: "Middle", 3: "High"}

        for room in self._rooms:
            preset = room.get('preset', {})
            formatted.append({
                'room': room['name'],
                'fan': fan_map.get(preset.get('fan', 2), "Normal"),
                'water': water_map.get(preset.get('water', 2), "Middle"),
                'times': preset.get('times', 1)
            })

        attrs['formatted'] = formatted

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True


class NeatsvorRoomListSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing list of available rooms."""
    _attr_has_entity_name = True
    _attr_translation_key = "room_list"
    
    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = "neatsvor_room_list"
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:format-list-bulleted"
        self._attr_native_value = "0 rooms"
        self._rooms = []

    @property
    def native_value(self) -> str:
        """Return number of rooms."""
        if hasattr(self.coordinator, 'map_entity'):
            return f"{self.coordinator.map_entity.extra_state_attributes.get('room_count', 0)} rooms"
        return "0 rooms"

    @property
    def extra_state_attributes(self) -> dict:
        """Return room list."""
        if hasattr(self.coordinator, 'map_entity'):
            return {
                'rooms': self.coordinator.map_entity.extra_state_attributes.get('rooms', []),
                'room_names': self.coordinator.map_entity.extra_state_attributes.get('room_names', []),
                'room_ids': self.coordinator.map_entity.extra_state_attributes.get('room_ids', []),
                'room_count': self.coordinator.map_entity.extra_state_attributes.get('room_count', 0)
            }
        return {}


class NeatsvorCurrentMapPresetSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing presets from current live map."""
    _attr_has_entity_name = True
    _attr_translation_key = "current_map_presets"
    
    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = "neatsvor_current_map_presets"
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:map"
        self._attr_native_value = "0 presets"
        self._presets = {}
        self._rooms = []
        self._map_time = None

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        await self._update_presets()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.hass.async_create_task(self._update_presets())

    async def _update_presets(self):
        """Update presets from current live map."""
        if not self.coordinator.vacuum:
            return

        try:
            if hasattr(self.coordinator.vacuum, '_current_map_metadata'):
                metadata = self.coordinator.vacuum._current_map_metadata
                if metadata and metadata.rooms:
                    self._presets = metadata.room_presets
                    self._rooms = [r.to_dict() for r in metadata.rooms.values()]
                    self._map_time = metadata.timestamp
                    self._attr_native_value = f"{len(self._presets)} presets"
                    _LOGGER.debug("Current map: %s presets from %s", len(self._presets), self._map_time)
                    self.async_write_ha_state()
                    return

            if hasattr(self.coordinator.vacuum, '_map_data') and self.coordinator.vacuum._map_data:
                map_data = self.coordinator.vacuum._map_data
                if 'raw' in map_data and hasattr(map_data['raw'], 'room_info'):
                    raw = map_data['raw']
                    if hasattr(raw.room_info, 'room_attrs'):
                        self._presets = {}
                        self._rooms = []

                        room_names = {r['id']: r['name'] for r in map_data.get('room_names', [])}

                        for attr in raw.room_info.room_attrs:
                            room_id = attr.room_id
                            room_name = room_names.get(room_id, f"Room {room_id}")

                            preset = {
                                'fan': attr.fan_level,
                                'water': attr.tank_level,
                                'times': attr.clean_times,
                                'mode': attr.clean_mode
                            }
                            self._presets[room_id] = preset

                            self._rooms.append({
                                'id': room_id,
                                'name': room_name,
                                'preset': preset
                            })

                        self._attr_native_value = f"{len(self._presets)} presets"
                        self.async_write_ha_state()

        except Exception as e:
            _LOGGER.error("Error updating current map presets: %s", e)

    @property
    def extra_state_attributes(self) -> dict:
        """Return presets."""
        attrs = {
            'presets': self._presets,
            'rooms': self._rooms,
            'preset_count': len(self._presets),
            'map_time': self._map_time.isoformat() if self._map_time else None
        }

        formatted = []
        fan_map = {1: "Quiet", 2: "Normal", 3: "Strong", 4: "Max"}
        water_map = {1: "Low", 2: "Middle", 3: "High"}

        for room in self._rooms:
            preset = room.get('preset', {})
            formatted.append({
                'room': room['name'],
                'room_id': room['id'],
                'fan': fan_map.get(preset.get('fan', 2), "Normal"),
                'fan_level': preset.get('fan', 2),
                'water': water_map.get(preset.get('water', 2), "Middle"),
                'water_level': preset.get('water', 2),
                'times': preset.get('times', 1)
            })

        attrs['formatted'] = formatted

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True


class NeatsvorCloudMapPresetSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing presets from selected cloud map."""
    _attr_has_entity_name = True
    _attr_translation_key = "cloud_map_presets"
    
    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = "neatsvor_cloud_map_presets"
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:cloud"
        self._attr_native_value = "0 presets"
        self._presets = {}
        self._rooms = []
        self._map_name = None
        self._map_id = None

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        await self._update_presets()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.hass.async_create_task(self._update_presets())

    async def _update_presets(self):
        """Update presets from selected cloud map."""
        if not hasattr(self.coordinator, 'cloud_maps_sensor'):
            return

        try:
            sensor = self.coordinator.cloud_maps_sensor
            selected_id = sensor.selected_map_id if hasattr(sensor, 'selected_map_id') else None

            if not selected_id:
                self._attr_native_value = "No map selected"
                self.async_write_ha_state()
                return

            selected_map = None
            for m in sensor._maps:
                if m['id'] == selected_id:
                    selected_map = m
                    break

            if not selected_map:
                return

            self._map_id = selected_id
            self._map_name = selected_map.get('name')

            json_path = None
            if selected_map.get('json_path'):
                json_path = Path(selected_map['json_path'])
            elif selected_map.get('local_path'):
                bv_path = Path(selected_map['local_path'])
                json_path = bv_path.parent.parent / "json" / f"{bv_path.stem}.json"

            if json_path and json_path.exists():
                try:
                    import json
                    import aiofiles
                    async with aiofiles.open(json_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        metadata = json.loads(content)

                        rooms = metadata.get('rooms', [])
                        self._rooms = rooms
                        self._presets = {}

                        for room in rooms:
                            room_id = room['id']
                            preset = room.get('preset', {})
                            self._presets[room_id] = preset

                        self._attr_native_value = f"{len(self._presets)} presets"
                        _LOGGER.debug("Cloud map '%s': %s presets", self._map_name, len(self._presets))

                except Exception as e:
                    _LOGGER.error("Error loading cloud map presets: %s", e)

            self.async_write_ha_state()

        except Exception as e:
            _LOGGER.error("Error updating cloud map presets: %s", e)

    @property
    def extra_state_attributes(self) -> dict:
        """Return presets."""
        attrs = {
            'presets': self._presets,
            'rooms': self._rooms,
            'preset_count': len(self._presets),
            'map_id': self._map_id,
            'map_name': self._map_name
        }

        formatted = []
        fan_map = {1: "Quiet", 2: "Normal", 3: "Strong", 4: "Max"}
        water_map = {1: "Low", 2: "Middle", 3: "High"}

        for room in self._rooms:
            preset = room.get('preset', {})
            formatted.append({
                'room': room.get('name', f"Room {room.get('id')}"),
                'room_id': room.get('id'),
                'fan': fan_map.get(preset.get('fan', 2), "Normal"),
                'fan_level': preset.get('fan', 2),
                'water': water_map.get(preset.get('water', 2), "Middle"),
                'water_level': preset.get('water', 2),
                'times': preset.get('times', 1)
            })

        attrs['formatted'] = formatted

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True


class NeatsvorPresetComparisonSensor(CoordinatorEntity, SensorEntity):
    """Sensor comparing presets between current and cloud maps."""
    _attr_has_entity_name = True
    _attr_translation_key = "preset_comparison"
    
    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = "neatsvor_preset_comparison"
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:compare"
        self._attr_native_value = "No comparison"
        self._differences = []
        self._current_presets = {}
        self._cloud_presets = {}
        self._current_rooms = []
        self._cloud_rooms = []

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        await self._update_comparison()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.hass.async_create_task(self._update_comparison())

    async def _update_comparison(self):
        """Compare presets between current and cloud maps."""
        self._current_presets = {}
        self._cloud_presets = {}
        self._current_rooms = []
        self._cloud_rooms = []
        self._differences = []

        if hasattr(self.coordinator.vacuum, '_current_map_metadata'):
            metadata = self.coordinator.vacuum._current_map_metadata
            if metadata:
                self._current_presets = metadata.room_presets
                self._current_rooms = [r.to_dict() for r in metadata.rooms.values()]

        if hasattr(self.coordinator, 'cloud_maps_sensor'):
            sensor = self.coordinator.cloud_maps_sensor
            selected_id = sensor.selected_map_id if hasattr(sensor, 'selected_map_id') else None

            if selected_id:
                for m in sensor._maps:
                    if m['id'] == selected_id:
                        json_path = None
                        if m.get('json_path'):
                            json_path = Path(m['json_path'])

                        if json_path and json_path.exists():
                            try:
                                import json
                                import aiofiles
                                async with aiofiles.open(json_path, 'r', encoding='utf-8') as f:
                                    content = await f.read()
                                    metadata = json.loads(content)
                                    self._cloud_rooms = metadata.get('rooms', [])
                                    for room in self._cloud_rooms:
                                        room_id = room['id']
                                        preset = room.get('preset', {})
                                        self._cloud_presets[room_id] = preset
                            except Exception as e:
                                _LOGGER.error("Error loading cloud presets for comparison: %s", e)
                        break

        differences = []

        for room_id, preset in self._current_presets.items():
            if room_id not in self._cloud_presets:
                room_name = next((r['name'] for r in self._current_rooms if r['id'] == room_id), f"Room {room_id}")
                differences.append({
                    'type': 'missing_in_cloud',
                    'room_id': room_id,
                    'room_name': room_name,
                    'preset': preset
                })

        for room_id, preset in self._cloud_presets.items():
            if room_id not in self._current_presets:
                room_name = next((r['name'] for r in self._cloud_rooms if r['id'] == room_id), f"Room {room_id}")
                differences.append({
                    'type': 'missing_in_current',
                    'room_id': room_id,
                    'room_name': room_name,
                    'preset': preset
                })

        common_rooms = set(self._current_presets.keys()) & set(self._cloud_presets.keys())
        for room_id in common_rooms:
            current = self._current_presets[room_id]
            cloud = self._cloud_presets[room_id]

            if current != cloud:
                room_name = next((r['name'] for r in self._current_rooms if r['id'] == room_id), f"Room {room_id}")
                diff = {}
                if current.get('fan') != cloud.get('fan'):
                    diff['fan'] = {'current': current.get('fan'), 'cloud': cloud.get('fan')}
                if current.get('water') != cloud.get('water'):
                    diff['water'] = {'current': current.get('water'), 'cloud': cloud.get('water')}
                if current.get('times') != cloud.get('times'):
                    diff['times'] = {'current': current.get('times'), 'cloud': cloud.get('times')}

                differences.append({
                    'type': 'preset_mismatch',
                    'room_id': room_id,
                    'room_name': room_name,
                    'current': current,
                    'cloud': cloud,
                    'differences': diff
                })

        self._differences = differences

        if differences:
            self._attr_native_value = f"{len(differences)} differences"
        else:
            self._attr_native_value = "Maps match"

        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        """Return comparison results."""
        return {
            'differences': self._differences,
            'current_preset_count': len(self._current_presets),
            'cloud_preset_count': len(self._cloud_presets),
            'current_rooms': self._current_rooms,
            'cloud_rooms': self._cloud_rooms
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True


class NeatsvorCleanHistorySensor(CoordinatorEntity, SensorEntity):
    """Sensor for clean history records - list only, without maps."""
    _attr_has_entity_name = True
    _attr_translation_key = "clean_history"
    
    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = "neatsvor_clean_history"
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:history"
        self._attr_native_value = "0 records"

        self._records = []
        self.selected_record_id = None
        self._loading = False
        self._download_tasks = {}
        self._last_update = datetime.now()
        self._initial_load_done = False

        _LOGGER.debug("CleanHistorySensor initialized")

        coordinator.clean_history_sensor = self

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        await self._load_history()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.hass.async_create_task(self._load_history())

    async def _load_history(self):
        """Load ALL history records - list only, without maps."""
        if self._loading:
            return

        if not self.coordinator or not self.coordinator.vacuum:
            return

        if not hasattr(self.coordinator.vacuum, 'clean_history'):
            _LOGGER.warning("vacuum.clean_history not available")
            return

        self._loading = True
        try:
            device_id = self.coordinator.vacuum.info.device_id
            _LOGGER.info("Loading clean history for device %s...", device_id)

            records = await self.coordinator.vacuum.clean_history.get_clean_history(device_id, 50)

            if records:
                self._records = []
                for record in records:
                    png_path = self._get_cached_png_path(record.record_id, record.clean_time)
                    downloaded = png_path is not None and png_path.exists()

                    self._records.append({
                        'record_id': record.record_id,
                        'clean_time': record.clean_time,
                        'clean_area': round(record.area_m2, 1),
                        'clean_duration': record.duration_minutes,
                        'finished': record.finished,
                        'record_url': record.record_url,
                        'downloaded': downloaded,
                        'png_path': str(png_path) if downloaded else None
                    })

                self._attr_native_value = str(len(self._records))
                _LOGGER.info("Loaded %s history records (%s cached)", len(self._records), sum(1 for r in self._records if r['downloaded']))

                # Auto-load the latest map on first load
                if not self._initial_load_done and self._records:
                    await self._auto_load_latest_map()
                    self._initial_load_done = True

                # Clean up old maps (keep last 50)
                await self._cleanup_old_maps()

                if hasattr(self.coordinator, 'clean_history_select'):
                    await self.coordinator.clean_history_select.async_update()
            else:
                _LOGGER.warning("No history records found")
                self._records = []
                self._attr_native_value = "0 records"

        except Exception as e:
            _LOGGER.error("Error loading history: %s", e, exc_info=True)
        finally:
            self._loading = False
            self.async_write_ha_state()

    async def _auto_load_latest_map(self):
        """Automatically load the latest map on initialization."""
        if not self._records:
            _LOGGER.debug("No records available for auto-load")
            return

        # Take the most recent record (first in the list, as API returns from newest to oldest)
        latest_record = self._records[0]
        latest_id = latest_record['record_id']

        _LOGGER.info("Auto-loading latest map for record %s", latest_id)

        # If map is already downloaded - just select it
        if latest_record.get('downloaded') and latest_record.get('png_path'):
            _LOGGER.info("Latest map already downloaded for record %s", latest_id)
            await self.select_record(latest_id)
            return

        # If not downloaded - start download
        if latest_id not in self._download_tasks or self._download_tasks[latest_id].done():
            _LOGGER.info("Auto-downloading latest map for record %s", latest_id)
            self._download_tasks[latest_id] = asyncio.create_task(
                self._download_record_map(latest_id, auto_select=True)
            )

    def _get_cached_png_path(self, record_id: int, clean_time: str = None):
        """Get path for cached PNG file (format: cleanTime_recordId.png)."""
        from pathlib import Path

        if clean_time:
            import re
            clean_time_clean = clean_time.replace(' ', '_').replace(':', '')
            clean_time_clean = re.sub(r'[^\w\-_]', '', clean_time_clean)
            return Path(f"/config/www/neatsvor/maps/history/{clean_time_clean}_{record_id}.png")

        history_dir = Path("/config/www/neatsvor/maps/history")
        if history_dir.exists():
            for f in history_dir.glob(f"*_{record_id}.png"):
                return f
        return None

    async def select_record(self, record_id: int) -> bool:
        """Select record by ID."""
        _LOGGER.info("Selecting record %s", record_id)

        for i, record in enumerate(self._records):
            if record['record_id'] == record_id:
                self.selected_record_id = record_id
                self.async_write_ha_state()

                # Reset camera
                if hasattr(self.coordinator, 'clean_history_camera') and self.coordinator.clean_history_camera:
                    camera = self.coordinator.clean_history_camera

                    old_record = camera._current_record_id

                    # Clear cache
                    camera._current_image = None
                    camera._current_record_id = record_id
                    camera._last_update = datetime.now()

                    # Force update state
                    camera.async_write_ha_state()

                    # Fire event to update all cards
                    if self.hass:
                        self.hass.bus.async_fire("neatsvor_camera_reset", {
                            "entity_id": camera.entity_id,
                            "record_id": record_id
                        })

                    _LOGGER.debug("Camera reset for record %s (was %s)", record_id, old_record)

                    # Prefetch next and previous records
                    asyncio.create_task(self._prefetch_nearby_records(i))

                from pathlib import Path
                import re
                clean_time = record['clean_time'].replace(' ', '_').replace(':', '')
                clean_time = re.sub(r'[^\w\-_]', '', clean_time)
                png_path = Path(f"/config/www/neatsvor/maps/history/{clean_time}_{record_id}.png")

                if png_path.exists():
                    _LOGGER.info("Found existing PNG for record %s", record_id)
                    record['downloaded'] = True
                    record['png_path'] = str(png_path)
                    self.async_write_ha_state()

                    if hasattr(self.coordinator, 'clean_history_camera') and self.coordinator.clean_history_camera:
                        try:
                            import aiofiles
                            async with aiofiles.open(png_path, 'rb') as f:
                                png_bytes = await f.read()

                            camera = self.coordinator.clean_history_camera
                            camera.update_image(record_id, png_bytes)

                            _LOGGER.info("Camera updated from existing PNG for record %s", record_id)
                        except Exception as e:
                            _LOGGER.error("Error loading existing PNG: %s", e)
                else:
                    if record.get('downloaded'):
                        _LOGGER.info("PNG not found for record %s, resetting downloaded flag", record_id)
                        record['downloaded'] = False
                        record['png_path'] = None
                        self.async_write_ha_state()

                    if not record.get('downloaded'):
                        if record_id not in self._download_tasks or self._download_tasks[record_id].done():
                            _LOGGER.info("Starting download for record %s", record_id)
                            self._download_tasks[record_id] = asyncio.create_task(
                                self._download_record_map(record_id)
                            )

                return True
        return False

    async def _prefetch_nearby_records(self, current_index: int):
        """Prefetch nearby records for faster switching."""
        # Prefetch the next record
        if current_index > 0:
            prev_record = self._records[current_index - 1]
            await self._prefetch_single_record(prev_record['record_id'])

        # Prefetch the previous record
        if current_index < len(self._records) - 1:
            next_record = self._records[current_index + 1]
            await self._prefetch_single_record(next_record['record_id'])

    async def _prefetch_single_record(self, record_id: int):
        """Prefetch a single record."""
        if not hasattr(self.coordinator, 'clean_history_camera'):
            return

        camera = self.coordinator.clean_history_camera

        # Find the record
        record = None
        for r in self._records:
            if r['record_id'] == record_id:
                record = r
                break

        if not record:
            return

        # If PNG already exists
        if record.get('png_path'):
            try:
                import aiofiles
                from pathlib import Path
                png_path = Path(record['png_path'])
                if png_path.exists():
                    async with aiofiles.open(png_path, 'rb') as f:
                        png_bytes = await f.read()

                    # Store in camera prefetch
                    camera.prefetch_image(record_id, png_bytes)
                    _LOGGER.debug("Prefetched record %s", record_id)
            except Exception as e:
                _LOGGER.error("Error prefetching record %s: %s", record_id, e)

    async def _download_record_map(self, record_id: int, auto_select: bool = False):
        """Download map for selected record."""
        try:
            # Check if this request is still relevant (if not auto-select)
            if not auto_select and self.selected_record_id != record_id:
                _LOGGER.info("Skipping download for record %s - user switched to %s", record_id, self.selected_record_id)
                return

            record_info = None
            for r in self._records:
                if r['record_id'] == record_id:
                    record_info = r
                    break

            if not record_info:
                _LOGGER.error("Record %s not found", record_id)
                return

            _LOGGER.info("Downloading map for record %s%s", record_id, " (auto)" if auto_select else "")

            records = await self.coordinator.vacuum.clean_history.get_clean_history(
                self.coordinator.vacuum.info.device_id, 50
            )
            target_record = next((r for r in records if r.record_id == record_id), None)

            if not target_record:
                _LOGGER.error("Record %s not found in API", record_id)
                return

            map_data = await self.coordinator.vacuum.clean_history.load_clean_record_map(target_record)

            if not map_data:
                _LOGGER.error("Failed to load map data")
                return

            saved_path = await self._save_map_png(target_record, map_data)

            if saved_path:
                record_info['downloaded'] = True
                record_info['png_path'] = saved_path
                self.async_write_ha_state()
                _LOGGER.info("Map for record %s saved: %s", record_id, saved_path)

                # For auto-load - automatically select the record
                if auto_select:
                    _LOGGER.info("Auto-selecting record %s after download", record_id)
                    await self.select_record(record_id)

                # Check if still relevant
                elif self.selected_record_id == record_id:
                    if hasattr(self.coordinator, 'clean_history_camera') and self.coordinator.clean_history_camera:
                        try:
                            import aiofiles
                            from pathlib import Path

                            png_path = Path(saved_path)
                            if png_path.exists():
                                async with aiofiles.open(png_path, 'rb') as f:
                                    png_bytes = await f.read()

                                camera = self.coordinator.clean_history_camera
                                camera.update_image(record_id, png_bytes)

                                # Additional forced update
                                camera.async_write_ha_state()

                                _LOGGER.info("Camera updated for record %s", record_id)
                        except Exception as e:
                            _LOGGER.error("Error updating camera: %s", e)
                else:
                    # If not relevant, but may be useful later - save to cache
                    if hasattr(self.coordinator, 'clean_history_camera') and self.coordinator.clean_history_camera:
                        try:
                            import aiofiles
                            from pathlib import Path

                            png_path = Path(saved_path)
                            if png_path.exists():
                                async with aiofiles.open(png_path, 'rb') as f:
                                    png_bytes = await f.read()

                                camera = self.coordinator.clean_history_camera
                                camera.prefetch_image(record_id, png_bytes)
                                _LOGGER.info("Prefetched record %s for later", record_id)
                        except Exception as e:
                            _LOGGER.error("Error prefetching camera: %s", e)
            else:
                _LOGGER.error("Failed to save PNG for record %s", record_id)

        except Exception as e:
            _LOGGER.error("Error downloading map: %s", e, exc_info=True)
        finally:
            if record_id in self._download_tasks:
                del self._download_tasks[record_id]

    async def async_load_and_select(self, record_id: int):
        """Load and select a specific record."""
        _LOGGER.info("Manual load and select for record %s", record_id)

        # Find the record
        record = None
        for r in self._records:
            if r['record_id'] == record_id:
                record = r
                break

        if not record:
            _LOGGER.error("Record %s not found", record_id)
            return False

        # If already downloaded - just select
        if record.get('downloaded') and record.get('png_path'):
            _LOGGER.info("Record %s already downloaded", record_id)
            return await self.select_record(record_id)

        # If not downloaded - start download with auto-select
        if record_id not in self._download_tasks or self._download_tasks[record_id].done():
            _LOGGER.info("Starting download for record %s with auto-select", record_id)
            self._download_tasks[record_id] = asyncio.create_task(
                self._download_record_map(record_id, auto_select=True)
            )
            return True

        return False

    async def _save_map_png(self, record, map_data) -> Optional[str]:
        """Save map as PNG using visualizer."""
        try:
            if not self.coordinator.vacuum.visualizer:
                _LOGGER.error("Visualizer not available")
                return None

            import re
            from pathlib import Path

            clean_time = record.clean_time.replace(' ', '_').replace(':', '')
            clean_time = re.sub(r'[^\w\-_]', '', clean_time)
            filename = f"{clean_time}_{record.record_id}"

            _LOGGER.info("Saving map as: %s.png", filename)

            png_path = await self.coordinator.vacuum.visualizer.render_static_map(
                map_data,
                title=filename,
                map_type="history"
            )

            if png_path:
                path = Path(png_path)
                if path.exists():
                    expected_name = f"{filename}.png"
                    if path.name != expected_name:
                        correct_path = path.parent / expected_name
                        if correct_path.exists():
                            correct_path.unlink()
                        path.rename(correct_path)
                        _LOGGER.info("PNG renamed to: %s", correct_path)
                        return str(correct_path)
                    else:
                        _LOGGER.info("PNG saved correctly: %s", png_path)
                        return png_path
            return None
        except Exception as e:
            _LOGGER.error("Error saving PNG: %s", e)
            return None

    async def async_force_camera_update(self, record_id: int):
        """Force camera update for record."""
        if hasattr(self.coordinator, 'clean_history_camera') and self.coordinator.clean_history_camera:
            camera = self.coordinator.clean_history_camera

            # Find the record
            record = None
            for r in self._records:
                if r['record_id'] == record_id:
                    record = r
                    break

            if record and record.get('png_path'):
                try:
                    import aiofiles
                    png_path = Path(record['png_path'])
                    if png_path.exists():
                        async with aiofiles.open(png_path, 'rb') as f:
                            png_bytes = await f.read()

                        camera.update_image(record_id, png_bytes)
                        _LOGGER.info("Camera force updated for record %s", record_id)
                except Exception as e:
                    _LOGGER.error("Error force updating camera: %s", e)

    async def _cleanup_old_maps(self):
        """Clean up old map files, keep only last 50."""
        try:
            history_dir = Path("/config/www/neatsvor/maps/history")
            if not history_dir.exists():
                return

            # Get all PNG files - FIXED: use asyncio.to_thread
            all_maps = await asyncio.to_thread(lambda: list(history_dir.glob("*.png")))

            # If less than 50 files, do nothing
            if len(all_maps) <= 50:
                return

            # Sort by modification time (newest last) - also needs to_thread
            all_maps = await asyncio.to_thread(lambda: sorted(all_maps, key=lambda x: x.stat().st_mtime, reverse=True))

            # Keep first 50 (newest), delete the rest
            maps_to_delete = all_maps[50:]

            deleted_count = 0
            for map_file in maps_to_delete:
                try:
                    # Extract record_id from filename
                    record_id = None
                    if '_' in map_file.stem:
                        parts = map_file.stem.split('_')
                        if len(parts) >= 2 and parts[-1].isdigit():
                            record_id = int(parts[-1])

                    await asyncio.to_thread(map_file.unlink)
                    deleted_count += 1
                    _LOGGER.debug("Deleted old map: %s", map_file.name)

                    # If the file was associated with a record in the sensor, update status
                    if record_id:
                        for record in self._records:
                            if record['record_id'] == record_id:
                                if record.get('png_path') == str(map_file):
                                    record['downloaded'] = False
                                    record['png_path'] = None
                                    _LOGGER.debug("Updated record %s status (file deleted)", record_id)
                                break

                except Exception as e:
                    _LOGGER.error("Error deleting old map %s: %s", map_file, e)

            if deleted_count > 0:
                self.async_write_ha_state()
                _LOGGER.info("Cleaned up %s old map files, kept last 50", deleted_count)

        except Exception as e:
            _LOGGER.error("Error during map cleanup: %s", e, exc_info=True)

    async def _cleanup_except_current(self):
        """Clean up all maps except the current one."""
        try:
            history_dir = Path("/config/www/neatsvor/maps/history")
            if not history_dir.exists():
                return

            current_id = self.selected_record_id

            # Get all PNG files
            all_maps = list(history_dir.glob("*.png"))

            deleted_count = 0
            for map_file in all_maps:
                # Skip file with current record
                if current_id and f"_{current_id}.png" in map_file.name:
                    continue

                try:
                    # Extract record_id from filename
                    record_id = None
                    if '_' in map_file.stem:
                        parts = map_file.stem.split('_')
                        if len(parts) >= 2 and parts[-1].isdigit():
                            record_id = int(parts[-1])

                    map_file.unlink()
                    deleted_count += 1
                    _LOGGER.debug("Deleted map: %s", map_file.name)

                    # If the file was associated with a record in the sensor, update status
                    if record_id:
                        for record in self._records:
                            if record['record_id'] == record_id:
                                if record.get('png_path') == str(map_file):
                                    record['downloaded'] = False
                                    record['png_path'] = None
                                    _LOGGER.debug("Updated record %s status (file deleted)", record_id)
                                break

                except Exception as e:
                    _LOGGER.error("Error deleting map %s: %s", map_file, e)

            if deleted_count > 0:
                self.async_write_ha_state()
                _LOGGER.info("Cleaned up %s map files, kept current only", deleted_count)

        except Exception as e:
            _LOGGER.error("Error during cleanup: %s", e, exc_info=True)

    async def _cleanup_by_id(self, keep_ids: list[int]):
        """Clean up maps, keeping only specified IDs."""
        try:
            history_dir = Path("/config/www/neatsvor/maps/history")
            if not history_dir.exists():
                return

            # Get all PNG files
            all_maps = list(history_dir.glob("*.png"))

            deleted_count = 0
            for map_file in all_maps:
                # Extract record_id from filename
                record_id = None
                if '_' in map_file.stem:
                    parts = map_file.stem.split('_')
                    if len(parts) >= 2 and parts[-1].isdigit():
                        record_id = int(parts[-1])

                # If ID is not in keep list - delete
                if record_id and record_id not in keep_ids:
                    try:
                        map_file.unlink()
                        deleted_count += 1
                        _LOGGER.debug("Deleted map: %s", map_file.name)

                        # Update record status
                        for record in self._records:
                            if record['record_id'] == record_id:
                                if record.get('png_path') == str(map_file):
                                    record['downloaded'] = False
                                    record['png_path'] = None
                                    _LOGGER.debug("Updated record %s status (file deleted)", record_id)
                                break

                    except Exception as e:
                        _LOGGER.error("Error deleting map %s: %s", map_file, e)

            if deleted_count > 0:
                self.async_write_ha_state()
                _LOGGER.info("Cleaned up %s map files, kept %s records", deleted_count, len(keep_ids))

        except Exception as e:
            _LOGGER.error("Error during cleanup: %s", e, exc_info=True)

    async def async_cleanup_old_maps(self):
        """Public method to cleanup old maps."""
        await self._cleanup_old_maps()

    async def async_cleanup_all_except_current(self):
        """Public method to cleanup all maps except current."""
        await self._cleanup_except_current()

    async def async_cleanup_by_record_ids(self, keep_ids: list[int]):
        """Public method to cleanup maps by record IDs."""
        await self._cleanup_by_id(keep_ids)

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        return {
            'records': self._records,
            'selected_record_id': self.selected_record_id,
            'total_records': len(self._records),
            'downloaded_records': sum(1 for r in self._records if r.get('downloaded')),
            'downloading': list(self._download_tasks.keys()) if self._download_tasks else []
        }


class NeatsvorMalfunctionSensor(CoordinatorEntity, SensorEntity):
    """Sensor for robot malfunctions - shows error details separately."""
    
    _attr_has_entity_name = True
    _attr_translation_key = "malfunction"
    
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = "neatsvor_malfunction"
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:alert-circle"
        
        self._error_map = {
            0: "None",
            1: "Unknown error",
            2: "Wheel winded",
            3: "Side brush winded",
            4: "Rolling brush winded",
            5: "Wheel suspended",
            6: "Bumper stuck",
            7: "Cliff sensor error",
            8: "Tank malfunction",
            9: "No dust box",
            10: "Cannot find dock",
            11: "Camera malfunction",
            12: "Lidar malfunction",
            13: "Lidar stuck",
            14: "Low power",
            15: "Turn on the switch",
            16: "Fan malfunction",
            17: "Robot trap",
            18: "Dust box full",
            19: "Destination unreachable",
            20: "Clean tank uninstall",
            21: "Dust box uninstall",
            22: "Clean tank lack water",
            23: "Sewage tank uninstall",
            24: "Sewage tank full",
            25: "Pallet uninstall",
            26: "Mop uninstall",
            27: "Mop winded",
            28: "Pallet water full",
            29: "Soap shortage",
            50: "Start on carpet",
            51: "Battery malfunction",
        }
        
        self._error_map_ru = {
            0: "Нет",
            1: "Неизвестная ошибка",
            2: "Запутывание колеса",
            3: "Запутывание боковой щетки",
            4: "Запутывание основной щетки",
            5: "Колесо зависло",
            6: "Бампер застрял",
            7: "Ошибка датчика перепада высот",
            8: "Неисправность бака",
            9: "Нет контейнера для пыли",
            10: "Не может найти базу",
            11: "Неисправность камеры",
            12: "Неисправность лидара",
            13: "Лидар застрял",
            14: "Низкий заряд",
            15: "Включите выключатель",
            16: "Неисправность вентилятора",
            17: "Робот застрял",
            18: "Контейнер для пыли полон",
            19: "Зона недоступна",
            20: "Бак чистой воды не установлен",
            21: "Контейнер для пыли не установлен",
            22: "Нет воды в баке",
            23: "Бак грязной воды не установлен",
            24: "Бак грязной воды полон",
            25: "Паллет не установлен",
            26: "Швабра не установлена",
            27: "Запутывание швабры",
            28: "Паллет полон",
            29: "Недостаточно моющего средства",
            50: "Старт на ковре",
            51: "Неисправность батареи",
        }

    @property
    def native_value(self) -> str:
        """Return malfunction description."""
        if not self.coordinator or not self.coordinator.data:
            return "Unknown"
        
        # Добавляем безопасную проверку
        error_code = self.coordinator.data.get("malfunction_code")
        if error_code is None:
            return "Unknown"
        
        language = self.hass.config.language if self.hass else "en"
        
        if language == "ru":
            return self._error_map_ru.get(error_code, f"Неизвестная ошибка ({error_code})")
        return self._error_map.get(error_code, f"Unknown error ({error_code})")

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        if not self.coordinator.data:
            return {}

        error_code = self.coordinator.data.get("malfunction_code", 0)
        return {
            "error_code": error_code,
            "error_description_en": self._error_map.get(error_code, f"Unknown error ({error_code})"),
            "error_description_ru": self._error_map_ru.get(error_code, f"Неизвестная ошибка ({error_code})")
        }

    @property
    def available(self) -> bool:
        """Return if sensor is available."""
        if not self.coordinator.data:
            return False
        return True

        
class NeatsvorMaintenanceSensor(CoordinatorEntity, SensorEntity):
    """Виртуальный сенсор для обслуживания пылесоса."""
    
    _attr_has_entity_name = True
    _attr_translation_key = "maintenance"
    
    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_maintenance"
        self._attr_device_info = coordinator.device_info
        self._attr_icon = "mdi:robot-vacuum"
        self._attr_native_value = "OK"
        
    @property
    def native_value(self):
        """Возвращаем общий статус."""
        if not self.coordinator or not self.coordinator.data:
            return "Unknown"
        
        # Проверяем износ расходников
        consumables = self.coordinator.data.get("consumables", {})
        if not consumables:
            return "OK"
        
        # Если какой-то расходник ниже 15% - Warning
        for key in ["filter", "side_brush", "main_brush"]:
            cons = consumables.get(key)
            if cons and isinstance(cons, dict) and cons.get("remaining_percent", 100) < 15:
                return "Warning"
        
        # Если есть ошибка - Error
        malfunction = self.coordinator.data.get("malfunction_code")
        if malfunction and malfunction > 0:
            return "Error"
            
        return "OK"
    
    @property
    def extra_state_attributes(self):
        """Дополнительные атрибуты для экспорта в УДЯ."""
        if not self.coordinator or not self.coordinator.data:
            return {}
        
        data = self.coordinator.data
        consumables = data.get("consumables", {})
        
        attributes = {}
        
        # Расходники
        for key, name in [("filter", "filter_lifetime"), 
                          ("main_brush", "brush_lifetime"),
                          ("side_brush", "side_brush_lifetime")]:
            cons = consumables.get(key)
            if cons and isinstance(cons, dict):
                attributes[name] = cons.get("remaining_percent", 0)
                attributes[f"{name}_hours"] = cons.get("remaining_hours", 0)
            else:
                attributes[name] = 0
        
        # Статистика
        stats = data.get("statistics", {})
        attributes["total_cleaned_area"] = stats.get("total_clean_area", 0) if stats else 0
        attributes["total_cleaned_time"] = stats.get("total_clean_time", 0) if stats else 0
        attributes["total_cleanings"] = stats.get("total_cleanings", 0) if stats else 0
        
        # Последняя уборка
        last = data.get("last_clean", {})
        if last and last.get("clean_time"):
            attributes["last_clean_date"] = last["clean_time"].isoformat() if last["clean_time"] else None
        attributes["last_clean_area"] = last.get("clean_area", 0) if last else 0
        attributes["last_clean_duration"] = last.get("clean_duration", 0) if last else 0
        
        # Батарея
        attributes["battery_level"] = data.get("battery_level", 0)
        
        return attributes