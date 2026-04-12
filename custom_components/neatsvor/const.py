"""Constants for Neatsvor integration."""

import logging
from homeassistant.const import Platform

_LOGGER = logging.getLogger(__name__)

DOMAIN = "neatsvor"

PLATFORMS = [
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CAMERA,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.SWITCH,
]

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_DEVICE_ID = "device_id"

# Country/region configuration
COUNTRIES = {
    "ru": {
        "code": "ru",
        "name": "Russia",
        "phone_code": "7",
        "rest_url": "https://ru.wisdom.blackvision.net",
        "mqtt_host": "ru.mqtt.blackvision.net",
        "region": "ru"
    },
    "cn": {
        "code": "cn",
        "name": "China",
        "phone_code": "86",
        "rest_url": "https://cn.wisdom.blackvision.net",
        "mqtt_host": "cn.mqtt.blackvision.net",
        "region": "cn"
    },
    "de": {
        "code": "de",
        "name": "Germany",
        "phone_code": "49",
        "rest_url": "https://de.wisdom.blackvision.net",
        "mqtt_host": "de.mqtt.blackvision.net",
        "region": "de"
    }
}

DEFAULT_COUNTRY = "ru"

UPDATE_INTERVAL = 60  # seconds

# Control commands
COMMAND_START = "app_start"
COMMAND_PAUSE = "app_pause"
COMMAND_RETURN = "app_charge"
COMMAND_STOP = "app_stop"
COMMAND_FIND = "app_find"
COMMAND_MODE = "set_suction"

# Fan modes
SUCTION_MODE_SILENT = "quiet"
SUCTION_MODE_NORMAL = "normal"
SUCTION_MODE_MAX = "strong"

# Robot status from API
STATUS_STANDBY = "standby"
STATUS_CLEANING = "cleaning"
STATUS_CHARGING = "charging"
STATUS_PAUSED = "paused"
STATUS_GOTO_CHARGE = "goto_charge"
STATUS_CHARGING_COMPLETE = "charging_complete"
STATUS_SLEEP = "sleep"
STATUS_ERROR = "error"

# Status from DP 5
ROBOT_STATUS = {
    0: "idle",
    1: "relocation",
    2: "upgrade",
    3: "building_map",
    4: "paused",
    5: "returning",
    6: "charging",
    7: "charged",
    8: "cleaning",
    9: "zone_cleaning",
    10: "room_cleaning",
    11: "spot_cleaning",
    12: "manual",
    13: "error",
    14: "sleeping",
    15: "dust_collecting",
    50: "washing_mop",
    51: "filling_water",
    52: "drying_mop",
    53: "station_cleaning",
    54: "returning_to_wash",
}

# HA status constants
HA_STATUS_IDLE = "idle"
HA_STATUS_CLEANING = "cleaning"
HA_STATUS_DOCKED = "docked"
HA_STATUS_RETURNING = "returning"
HA_STATUS_PAUSED = "paused"
HA_STATUS_ERROR = "error"
HA_STATUS_CHARGING = "charging"

# Mapping to HA statuses
HA_STATUS_MAP = {
    "idle": "idle",
    "cleaning": "cleaning",
    "room_cleaning": "cleaning",
    "zone_cleaning": "cleaning",
    "spot_cleaning": "cleaning",
    "paused": "paused",
    "returning": "returning",
    "charging": "docked",
    "charged": "docked",
    "error": "error",
    "sleeping": "idle",
}

# Fan speed display mapping (English default)
SUCTION_MAP = {
    "quiet": "Quiet",
    "normal": "Normal",
    "strong": "Strong",
    "max": "Max",
}

# Fan speed display mapping (Russian)
SUCTION_MAP_RU = {
    "quiet": "Тихий",
    "normal": "Обычный",
    "strong": "Сильный",
    "max": "Максимальный",
}

# Water levels (English)
WATER_LEVELS = {
    "low": 1,
    "middle": 2,
    "high": 3
}

WATER_LEVEL_MAP = {
    "low": "Low",
    "middle": "Middle",
    "high": "High"
}

# Water levels (Russian)
WATER_LEVEL_MAP_RU = {
    "low": "Низкий",
    "middle": "Средний",
    "high": "Высокий"
}

# Clean modes (English)
CLEAN_MODE_MAP = {
    "sweep": "Sweep only",
    "mop": "Mop only",
    "sweep_mop": "Sweep and mop"
}

# Clean modes (Russian)
CLEAN_MODE_MAP_RU = {
    "sweep": "Только подмести",
    "mop": "Только мыть",
    "sweep_mop": "Подмести и вымыть"
}

# Consumables keys
CONSUMABLE_HEPA = "hepa"
CONSUMABLE_SIDE_BRUSH = "side_brush"
CONSUMABLE_MAIN_BRUSH = "main_brush"
CONSUMABLE_FILTER = "filter"

# Yandex Smart Home custom types
CUSTOM_TYPES = {
    "lifetime.filter": "devices.properties.custom.lifetime.filter",
    "lifetime.brush": "devices.properties.custom.lifetime.brush", 
    "lifetime.side_brush": "devices.properties.custom.lifetime.side_brush",
    "area.total": "devices.properties.custom.area.total",
    "area.last": "devices.properties.custom.area.last",
    "time.total": "devices.properties.custom.time.total",
    "time.last": "devices.properties.custom.time.last",
}

# Room cleaning commands
ROOM_CLEAN_DP = 31
ROOM_CLEAN_ATTR_DP = 45

# Supported languages
SUPPORTED_LANGUAGES = ["en", "ru"]
DEFAULT_LANGUAGE = "en"


def get_localized_status(status_key: str, language: str = "en") -> str:
    """Get localized vacuum status string."""
    status_map = {
        "en": {
            "idle": "Idle",
            "cleaning": "Cleaning",
            "returning": "Returning to base",
            "docked": "Docked",
            "paused": "Paused",
            "error": "Error",
            "charging": "Charging",
            "charged": "Charged",
            "relocation": "Relocating",
            "upgrade": "Upgrading",
            "building_map": "Building map",
            "zone_cleaning": "Zone cleaning",
            "room_cleaning": "Room cleaning",
            "spot_cleaning": "Spot cleaning",
            "manual": "Manual control",
            "sleeping": "Sleeping",
            "dust_collecting": "Dust collecting",
            "washing_mop": "Washing mop",
            "filling_water": "Filling water",
            "drying_mop": "Drying mop",
            "station_cleaning": "Station cleaning",
            "returning_to_wash": "Returning to wash",
        },
        "ru": {
            "idle": "Ожидание",
            "cleaning": "Уборка",
            "returning": "Возврат на базу",
            "docked": "На базе",
            "paused": "Приостановлен",
            "error": "Ошибка",
            "charging": "Зарядка",
            "charged": "Заряжен",
            "relocation": "Перемещение",
            "upgrade": "Обновление",
            "building_map": "Построение карты",
            "zone_cleaning": "Зональная уборка",
            "room_cleaning": "Уборка комнаты",
            "spot_cleaning": "Точечная уборка",
            "manual": "Ручное управление",
            "sleeping": "Сон",
            "dust_collecting": "Сбор пыли",
            "washing_mop": "Мойка швабры",
            "filling_water": "Набор воды",
            "drying_mop": "Сушка швабры",
            "station_cleaning": "Очистка станции",
            "returning_to_wash": "Возврат на мойку",
        }
    }
    translations = status_map.get(language, status_map["en"])
    return translations.get(status_key, status_key)


def get_localized_fan_speed(speed_key: str, language: str = "en") -> str:
    """Get localized fan speed string."""
    _LOGGER.debug("get_localized_fan_speed: key=%s, language=%s", speed_key, language)
    if language == "ru":
        result = SUCTION_MAP_RU.get(speed_key, speed_key.capitalize())
    else:
        result = SUCTION_MAP.get(speed_key, speed_key.capitalize())
    _LOGGER.debug("get_localized_fan_speed result: %s", result)
    return result


def get_localized_water_level(level_key: str, language: str = "en") -> str:
    """Get localized water level string."""
    _LOGGER.debug("get_localized_water_level: key=%s, language=%s", level_key, language)
    if language == "ru":
        result = WATER_LEVEL_MAP_RU.get(level_key, level_key.capitalize())
    else:
        result = WATER_LEVEL_MAP.get(level_key, level_key.capitalize())
    _LOGGER.debug("get_localized_water_level result: %s", result)
    return result


def get_localized_clean_mode(mode_key: str, language: str = "en") -> str:
    """Get localized clean mode string."""
    _LOGGER.debug("get_localized_clean_mode: key=%s, language=%s", mode_key, language)
    if language == "ru":
        result = CLEAN_MODE_MAP_RU.get(mode_key, mode_key)
    else:
        result = CLEAN_MODE_MAP.get(mode_key, mode_key)
    _LOGGER.debug("get_localized_clean_mode result: %s", result)
    return result