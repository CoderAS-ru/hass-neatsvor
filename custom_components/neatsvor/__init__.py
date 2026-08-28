"""Neatsvor integration for Home Assistant."""

import logging
import asyncio
from typing import Optional, Union, List
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from pathlib import Path

from .const import (
    DOMAIN, 
    PLATFORMS, 
    COUNTRIES, 
    DEFAULT_COUNTRY,
    DEFAULT_PHONE_CODE,
    CONF_PHONE_CODE,
    APP_CONFIGS, 
    DEFAULT_APP,
    MQTT_PORT,
    MQTT_USERNAME,
    MQTT_PASSWORD,
    DEFAULT_TIMEOUT,
    DEFAULT_COMMAND_DELAY,
    DEFAULT_RETRY_COUNT
)
from .coordinator import NeatsvorCoordinator
from .data_center_manager import get_data_center_manager
from .liboshome.config import NeatsvorConfig, RestConfig, MQTTConfig, Credentials, DeviceConfig
from .liboshome.device.vacuum import NeatsvorVacuum

_LOGGER = logging.getLogger(__name__)


def _normalize_entity_ids(entity_id: Union[str, List[str], None]) -> List[str]:
    """Normalize entity_id to list of strings."""
    if entity_id is None:
        return []
    if isinstance(entity_id, str):
        return [entity_id]
    if isinstance(entity_id, list):
        return entity_id
    return []


async def _migrate_old_config(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old configuration (with region) to new format (with phone_code)."""
    if CONF_PHONE_CODE in entry.data:
        return False
    
    if "region" not in entry.data:
        return False
    
    old_region = entry.data.get("region")
    region_to_phone = {
        "ru": "7",
        "cn": "86",
        "de": "49",
        "us": "1",
        "sg": "65",
    }
    
    phone_code = region_to_phone.get(old_region, DEFAULT_PHONE_CODE)
    manager = get_data_center_manager(hass)
    data_center = await hass.async_add_executor_job(
        manager.get_data_center_by_phone_code, phone_code, hass.config.language
    )
    
    new_data = dict(entry.data)
    new_data[CONF_PHONE_CODE] = phone_code
    
    if data_center:
        new_data["rest_url"] = data_center["rest_url"]
        new_data["mqtt_host"] = data_center["mqtt_host"]
        new_data["mqtt_port"] = data_center.get("mqtt_port", MQTT_PORT)
        new_data["country_code"] = data_center.get("country_code", "")
        new_data["country_name"] = data_center.get("country_name", "")
    else:
        country_data = COUNTRIES.get(old_region, COUNTRIES[DEFAULT_COUNTRY])
        new_data["rest_url"] = country_data["rest_url"]
        new_data["mqtt_host"] = country_data["mqtt_host"]
        new_data["mqtt_port"] = MQTT_PORT
    
    new_data.pop("region", None)
    hass.config_entries.async_update_entry(entry, data=new_data)
    _LOGGER.info("Migrated configuration from region '%s' to phone_code '%s'", old_region, phone_code)
    return True


async def _build_config(hass: HomeAssistant, entry: ConfigEntry) -> NeatsvorConfig:
    """Build NeatsvorConfig from entry data."""
    phone_code = entry.data.get(CONF_PHONE_CODE, DEFAULT_PHONE_CODE)
    app_type = entry.data.get("app_type", DEFAULT_APP)
    
    rest_url = entry.data.get("rest_url")
    mqtt_host = entry.data.get("mqtt_host")
    mqtt_port = entry.data.get("mqtt_port", MQTT_PORT)
    
    if not rest_url or not mqtt_host:
        manager = get_data_center_manager(hass)
        data_center = await hass.async_add_executor_job(
            manager.get_data_center_by_phone_code, phone_code, hass.config.language
        )
        if data_center:
            rest_url = data_center["rest_url"]
            mqtt_host = data_center["mqtt_host"]
            mqtt_port = data_center.get("mqtt_port", MQTT_PORT)
        else:
            country_map = {"7": "ru", "86": "cn", "49": "de", "1": "us", "65": "sg"}
            region = country_map.get(phone_code, DEFAULT_COUNTRY)
            country_data = COUNTRIES.get(region, COUNTRIES[DEFAULT_COUNTRY])
            rest_url = country_data["rest_url"]
            mqtt_host = country_data["mqtt_host"]
            mqtt_port = MQTT_PORT
    
    app_config = APP_CONFIGS.get(app_type, APP_CONFIGS[DEFAULT_APP])
    
    rest_config = RestConfig(
        base_url=rest_url,
        app_key=app_config["app_key"],
        app_secret=app_config["app_secret"],
        package_name=app_config["package_name"],
        source=app_config["source"],
        reg_id="",
        country=entry.data.get("country_code", "unknown"),
        user_agent="okhttp/4.9.1"
    )

    mqtt_config = MQTTConfig(
        host=mqtt_host,
        port=mqtt_port,
        username=MQTT_USERNAME,
        password=MQTT_PASSWORD
    )

    credentials = Credentials(
        email=entry.data["email"],
        password=entry.data["password"]
    )

    device_config = DeviceConfig(
        default_timeout=DEFAULT_TIMEOUT,
        command_delay=DEFAULT_COMMAND_DELAY,
        retry_count=DEFAULT_RETRY_COUNT
    )

    return NeatsvorConfig(
        rest=rest_config,
        mqtt=mqtt_config,
        credentials=credentials,
        device=device_config
    )


def _get_entry_id_from_entity_id(hass: HomeAssistant, entity_id: str) -> Optional[str]:
    """Find entry_id by entity_id."""
    if not entity_id:
        return None
    
    # Проверяем кэш
    cache = hass.data[DOMAIN].get('_entity_id_cache', {})
    if entity_id in cache:
        return cache[entity_id]
    
    # Используем entity registry для поиска
    from homeassistant.helpers import entity_registry as er
    registry = er.async_get(hass)
    
    entity_entry = registry.async_get(entity_id)
    if entity_entry:
        config_entry_id = entity_entry.config_entry_id
        if config_entry_id and config_entry_id in hass.data[DOMAIN]:
            entry_data = hass.data[DOMAIN].get(config_entry_id)
            if entry_data and 'coordinator' in entry_data:
                cache[entity_id] = config_entry_id
                hass.data[DOMAIN]['_entity_id_cache'] = cache
                _LOGGER.debug("Found entry_id %s for entity_id %s via registry", config_entry_id, entity_id)
                return config_entry_id
    
    # Если только один entry — используем его
    entries = [k for k in hass.data[DOMAIN].keys() 
               if k not in ['services_registered', 'stop_handler_registered', 'service_names', '_entity_id_cache']]
    if len(entries) == 1:
        _LOGGER.info("Only one entry found, using it as fallback: %s", entries[0])
        cache[entity_id] = entries[0]
        hass.data[DOMAIN]['_entity_id_cache'] = cache
        return entries[0]
    
    _LOGGER.warning("No entry found for entity_id: %s", entity_id)
    return None


async def _get_coordinator_by_entity_ids(hass: HomeAssistant, entity_ids: List[str]) -> List[NeatsvorCoordinator]:
    """Get coordinators by entity_ids."""
    coordinators = []
    for entity_id in entity_ids:
        entry_id = _get_entry_id_from_entity_id(hass, entity_id)
        if entry_id:
            entry_data = hass.data[DOMAIN].get(entry_id)
            if entry_data:
                coordinator = entry_data.get('coordinator')
                if coordinator and coordinator not in coordinators:
                    coordinators.append(coordinator)
    return coordinators


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Neatsvor from a config entry."""
    
    await _migrate_old_config(hass, entry)

    if entry.entry_id in hass.data.get(DOMAIN, {}):
        _LOGGER.warning("Entry %s already initialized, skipping", entry.entry_id)
        return True

    hass.data.setdefault(DOMAIN, {})
    
    config = await _build_config(hass, entry)
    app_type = entry.data.get("app_type", DEFAULT_APP)
    vacuum = NeatsvorVacuum(config, app_type=app_type)
    
    if not vacuum.is_initialized:
        await vacuum.initialize()
    
    vacuum.set_hass(hass)
    
    coordinator = NeatsvorCoordinator(hass, vacuum)
    
    from .select_storage import NeatsvorSelectStorage
    coordinator.select_storage = NeatsvorSelectStorage(hass, entry.entry_id)

    old_storage_path = hass.config.path(f"custom_components/neatsvor/select_states_{entry.entry_id}.json")
    await coordinator.select_storage.async_migrate_from_file(Path(old_storage_path))
    await coordinator.select_storage.async_ensure_loaded()
    
    entry_data = {
        'coordinator': coordinator,
        'vacuum': vacuum,
        'config': config,
    }
    hass.data[DOMAIN][entry.entry_id] = entry_data

    await coordinator.async_config_entry_first_refresh()

    _LOGGER.info("Registering platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.data[DOMAIN].get('services_registered'):
        await _async_register_services(hass)
        hass.data[DOMAIN]['services_registered'] = True
        hass.data[DOMAIN]['service_names'] = [
            "request_all_data", "request_map", "build_map", "empty_dust",
            "clean_room_with_preset", "restore_reference_map", "compare_with_reference",
            "force_update_maps", "cleanup_maps", "save_select_states",
            "restore_select_states", "set_reference_map", "use_cloud_map",
            "use_selected_cloud_map", "force_load_history", "cleanup_history_maps",
            "cleanup_all_except_current", "vacuum_clean_zone"
        ]

    if not hass.data[DOMAIN].get('stop_handler_registered'):
        hass.bus.async_listen_once("homeassistant_stop", 
            lambda event: hass.async_create_task(_async_close_all_vacuums(hass)))
        hass.data[DOMAIN]['stop_handler_registered'] = True
        
    _LOGGER.info("Neatsvor integration initialized for entry %s", entry.entry_id)
    return True


async def _async_register_services(hass: HomeAssistant):
    """Register integration services."""

    async def async_request_all_data(call: ServiceCall) -> None:
        """Request all data as the official app does."""
        entity_ids = _normalize_entity_ids(call.data.get("entity_id"))
        _LOGGER.info("Service call: request_all_data for %s", entity_ids)
        
        if entity_ids:
            coordinators = await _get_coordinator_by_entity_ids(hass, entity_ids)
            for coordinator in coordinators:
                if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                    await coordinator.vacuum.request_all_data()
                    await coordinator.async_request_refresh()
            return
        
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id in ['services_registered', 'stop_handler_registered', 'service_names', '_entity_id_cache']:
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                await coordinator.vacuum.request_all_data()
                await coordinator.async_request_refresh()

    async def async_request_map(call: ServiceCall) -> None:
        """Request the current map."""
        entity_ids = _normalize_entity_ids(call.data.get("entity_id"))
        _LOGGER.info("Service call: request_map for %s", entity_ids)
        
        if entity_ids:
            coordinators = await _get_coordinator_by_entity_ids(hass, entity_ids)
            for coordinator in coordinators:
                if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                    await coordinator.vacuum.request_map()
                    await coordinator.async_request_refresh()
            return
        
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id in ['services_registered', 'stop_handler_registered', 'service_names', '_entity_id_cache']:
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                await coordinator.vacuum.request_map()
                await coordinator.async_request_refresh()

    async def async_build_map(call: ServiceCall) -> None:
        """Perform a fast map build."""
        entity_ids = _normalize_entity_ids(call.data.get("entity_id"))
        _LOGGER.info("Service call: build_map for %s", entity_ids)
        
        if entity_ids:
            coordinators = await _get_coordinator_by_entity_ids(hass, entity_ids)
            for coordinator in coordinators:
                if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                    await coordinator.vacuum.build_map()
                    await coordinator.async_request_refresh()
            return
        
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id in ['services_registered', 'stop_handler_registered', 'service_names', '_entity_id_cache']:
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                await coordinator.vacuum.build_map()
                await coordinator.async_request_refresh()

    async def async_empty_dust(call: ServiceCall) -> None:
        """Empty the dust bin."""
        entity_ids = _normalize_entity_ids(call.data.get("entity_id"))
        _LOGGER.info("Service call: empty_dust for %s", entity_ids)
        
        if entity_ids:
            coordinators = await _get_coordinator_by_entity_ids(hass, entity_ids)
            for coordinator in coordinators:
                if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                    await coordinator.vacuum.empty_dust()
                    await coordinator.async_request_refresh()
            return
        
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id in ['services_registered', 'stop_handler_registered', 'service_names', '_entity_id_cache']:
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                await coordinator.vacuum.empty_dust()
                await coordinator.async_request_refresh()

    async def async_clean_room_with_preset(call: ServiceCall) -> None:
        """Clean a room with its saved preset."""
        room_name = call.data.get("room")
        use_preset = call.data.get("use_preset", True)
        entity_ids = _normalize_entity_ids(call.data.get("entity_id"))

        _LOGGER.info("Service call: clean_room_with_preset: %s for %s", room_name, entity_ids)
        
        coordinators = []
        if entity_ids:
            coordinators = await _get_coordinator_by_entity_ids(hass, entity_ids)
        
        if not coordinators:
            for entry_id, entry_data in hass.data[DOMAIN].items():
                if entry_id in ['services_registered', 'stop_handler_registered', 'service_names', '_entity_id_cache']:
                    continue
                coordinator = entry_data.get('coordinator')
                if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                    coordinators.append(coordinator)
                    break
        
        if not coordinators:
            _LOGGER.error("No coordinator found for clean_room_with_preset")
            return
            
        for coordinator in coordinators:
            if hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                rooms = await coordinator.vacuum.get_available_rooms()
                room_map = {r['name']: r['id'] for r in rooms}

                if room_name in room_map:
                    if use_preset:
                        await coordinator.vacuum.start_room_clean_with_preset([room_map[room_name]])
                    else:
                        await coordinator.vacuum.start_room_clean([room_map[room_name]])

                    await coordinator.async_request_refresh()
                    _LOGGER.info("Room cleaning started for: %s", room_name)
                else:
                    _LOGGER.error("Room '%s' not found", room_name)

    async def async_set_reference_map(call: ServiceCall) -> None:
        """Set the current map as the reference."""
        entity_ids = _normalize_entity_ids(call.data.get("entity_id"))
        _LOGGER.info("Service call: set_reference_map for %s", entity_ids)
        
        if entity_ids:
            coordinators = await _get_coordinator_by_entity_ids(hass, entity_ids)
            for coordinator in coordinators:
                if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                    await coordinator.vacuum.save_reference_map()
                    await coordinator.async_request_refresh()
            return
        
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id in ['services_registered', 'stop_handler_registered', 'service_names', '_entity_id_cache']:
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                await coordinator.vacuum.save_reference_map()
                await coordinator.async_request_refresh()

    async def async_use_cloud_map(call: ServiceCall) -> None:
        """Use a specific cloud map as the current map."""
        map_id = call.data.get("map_id")
        map_url = call.data.get("map_url")
        map_md5 = call.data.get("map_md5")
        entity_ids = _normalize_entity_ids(call.data.get("entity_id"))

        _LOGGER.info("Service call: use_cloud_map (map_id=%s) for %s", map_id, entity_ids)
        
        if entity_ids:
            coordinators = await _get_coordinator_by_entity_ids(hass, entity_ids)
            for coordinator in coordinators:
                if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                    await coordinator.vacuum.use_cloud_map(map_id, map_url, map_md5)
                    await coordinator.async_request_refresh()
            return
        
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id in ['services_registered', 'stop_handler_registered', 'service_names', '_entity_id_cache']:
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                await coordinator.vacuum.use_cloud_map(map_id, map_url, map_md5)
                await coordinator.async_request_refresh()

    async def async_use_selected_cloud_map(call: ServiceCall) -> None:
        """Use the selected cloud map as the current map."""
        entity_ids = _normalize_entity_ids(call.data.get("entity_id"))
        _LOGGER.info("Service call: use_selected_cloud_map for %s", entity_ids)

        if entity_ids:
            coordinators = await _get_coordinator_by_entity_ids(hass, entity_ids)
            for coordinator in coordinators:
                if coordinator and hasattr(coordinator, 'cloud_maps_sensor'):
                    await coordinator.cloud_maps_sensor.use_selected_cloud_map()
            return
        
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id in ['services_registered', 'stop_handler_registered', 'service_names', '_entity_id_cache']:
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'cloud_maps_sensor'):
                await coordinator.cloud_maps_sensor.use_selected_cloud_map()

    async def async_vacuum_zone_clean(call: ServiceCall) -> None:
        """Zone cleaning service for xiaomi-vacuum-map-card compatibility."""
        entity_ids = _normalize_entity_ids(call.data.get("entity_id"))
        zones = call.data.get("zones", [])

        if not zones:
            zones = call.data.get("zone", [])

        _LOGGER.info("Service call: vacuum_clean_zone for %s, zones: %s", entity_ids, zones)

        if not entity_ids:
            _LOGGER.error("No entity_id provided")
            return

        coordinators = await _get_coordinator_by_entity_ids(hass, entity_ids)
        if not coordinators:
            _LOGGER.error("Coordinator not found for entity_ids: %s", entity_ids)
            return

        for coordinator in coordinators:
            if not hasattr(coordinator, 'vacuum') or not coordinator.vacuum:
                _LOGGER.error("Vacuum not available for coordinator")
                continue

            vacuum = coordinator.vacuum

            for zone in zones:
                if len(zone) == 4:
                    x1, y1, x2, y2 = zone
                    repeats = 1
                elif len(zone) == 5:
                    x1, y1, x2, y2, repeats = zone
                else:
                    _LOGGER.error("Invalid zone format: %s", zone)
                    continue

                _LOGGER.info("Zone: (%s,%s)-(%s,%s) x%s", x1, y1, x2, y2, repeats)
                await vacuum.zone_clean(x1, y1, x2, y2, repeats)

            await coordinator.async_request_refresh()
            _LOGGER.info("Zone clean commands sent")

    # Register services
    hass.services.async_register(DOMAIN, "request_all_data", async_request_all_data)
    hass.services.async_register(DOMAIN, "request_map", async_request_map)
    hass.services.async_register(DOMAIN, "build_map", async_build_map)
    hass.services.async_register(DOMAIN, "empty_dust", async_empty_dust)
    hass.services.async_register(DOMAIN, "clean_room_with_preset", async_clean_room_with_preset)
    hass.services.async_register(DOMAIN, "set_reference_map", async_set_reference_map)
    hass.services.async_register(DOMAIN, "use_cloud_map", async_use_cloud_map)
    hass.services.async_register(DOMAIN, "use_selected_cloud_map", async_use_selected_cloud_map)
    hass.services.async_register(DOMAIN, "vacuum_clean_zone", async_vacuum_zone_clean)

    _LOGGER.info("All services registered")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and entry.entry_id in hass.data.get(DOMAIN, {}):
        entry_data = hass.data[DOMAIN][entry.entry_id]
        
        if 'vacuum' in entry_data:
            try:
                await entry_data['vacuum'].disconnect()
                _LOGGER.info("Vacuum disconnected for entry %s", entry.entry_id)
            except Exception as e:
                _LOGGER.error("Error disconnecting vacuum: %s", e)
        
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.info("Entry %s unloaded", entry.entry_id)

    entries = [k for k in hass.data.get(DOMAIN, {}) if k not in ['services_registered', 'stop_handler_registered', 'service_names', '_entity_id_cache']]
    if not entries:
        hass.data[DOMAIN]['services_registered'] = False
        service_names = hass.data[DOMAIN].get('service_names', [])
        for service_name in service_names:
            if hass.services.has_service(DOMAIN, service_name):
                hass.services.async_remove(DOMAIN, service_name)
        _LOGGER.info("All entries unloaded, services removed")

    return unload_ok


async def _async_close_all_vacuums(hass):
    """Close all vacuum instances when HA stops."""
    _LOGGER.info("Closing all Neatsvor vacuum instances")
    for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
        if entry_id in ['services_registered', 'stop_handler_registered', 'service_names', '_entity_id_cache']:
            continue
        if 'vacuum' in entry_data:
            try:
                await entry_data['vacuum'].disconnect()
                _LOGGER.info("Vacuum closed for entry %s", entry_id)
            except Exception as e:
                _LOGGER.error("Error closing vacuum: %s", e)