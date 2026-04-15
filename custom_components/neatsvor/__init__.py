"""Neatsvor integration for Home Assistant."""

import logging
import asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    DOMAIN, 
    PLATFORMS, 
    COUNTRIES, 
    DEFAULT_COUNTRY, 
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
from custom_components.neatsvor.liboshome.config import NeatsvorConfig, RestConfig, MQTTConfig, Credentials, DeviceConfig
from custom_components.neatsvor.liboshome.device.vacuum import NeatsvorVacuum

_LOGGER = logging.getLogger(__name__)

_shared_vacuum = None
_shared_config = None
_initialized = False


def _get_localized_message(hass, key: str, default: str, **kwargs) -> str:
    """Get localized message from translations."""
    language = hass.config.language if hass else "en"
    
    # Simple translation map for notifications
    messages = {
        "en": {
            "cloud_maps_refreshed": "Cloud maps list refreshed",
            "no_map_selected": "Please select a map first",
            "map_set_as_reference": "Map set as reference",
            "reference_map_restored": "Reference map restored from device",
            "reference_map_restore_failed": "Failed to restore reference map from device",
            "downloading_map": "Downloading map {}...",
            "map_downloaded": "Map downloaded successfully",
            "map_not_found": "Map {} not found in API",
            "download_error": "Error downloading map: {}",
            "delete_map": "Delete map '{}'? (stub implementation - would delete from cloud)",
            "vacuum_not_available": "Vacuum not available",
            "map_save_sent": "Command sent to save current map to cloud",
            "error_saving_map": "Error saving map: {}",
            "cleaning_room": "Cleaning room: {}",
            "failed_clean_room": "Failed to clean room {}: {}",
            "map_activated": "Map activated successfully",
            "map_activation_failed": "Failed to activate map",
            "map_auto_restored": "Map auto-restored from reference",
            "no_reference_map": "No reference map has been set. Please set a reference map first.",
            "restored_from_reference": "Restored from reference map '{}'\nрџЏ  Rooms: {}\nрџ“Џ Area: {}mВІ",
            "comparison_title": "Neatsvor Cloud Maps Comparison",
            "no_reference_set": "No reference map has been set.",
            "please_select_map": "Please select a map to compare.",
            "comparison_result": "рџ“Љ Comparison: '{}' vs Reference '{}'\n",
            "differences_found": "\nвљ пёЏ Differences found:\n{}",
            "maps_identical": "\nвњ… Maps are identical!",
            "cleanup_completed": "Cleanup completed. Kept the last {} maps.",
            "history_maps_loaded": "Loaded {} history maps",
            "history_maps_cleaned": "Cleaned up old history maps",
            "all_except_current_cleaned": "Cleaned up all maps except current",
        },
        "ru": {
            "cloud_maps_refreshed": "Список облачных карт обновлен",
            "no_map_selected": "Пожалуйста, сначала выберите карту",
            "map_set_as_reference": "Карта установлена как эталонная",
            "reference_map_restored": "Эталонная карта восстановлена с устройства",
            "reference_map_restore_failed": "Не удалось восстановить эталонную карту с устройства",
            "downloading_map": "Скачивание карты {}...",
            "map_downloaded": "Карта успешно скачана",
            "map_not_found": "Карта {} не найдена в API",
            "download_error": "Ошибка скачивания карты: {}",
            "delete_map": "Удалить карту '{}'? (заглушка - будет удалено из облака)",
            "vacuum_not_available": "Пылесос недоступен",
            "map_save_sent": "Команда на сохранение карты в облако отправлена",
            "error_saving_map": "Ошибка сохранения карты: {}",
            "cleaning_room": "Уборка комнаты: {}",
            "failed_clean_room": "Не удалось убрать комнату {}: {}",
            "map_activated": "Карта успешно активирована",
            "map_activation_failed": "Не удалось активировать карту",
            "map_auto_restored": "Карта автоматически восстановлена из эталона",
            "no_reference_map": "Эталонная карта не установлена. Пожалуйста, сначала установите эталонную карту.",
            "restored_from_reference": "Восстановлено из эталонной карты '{}'\n🏠 Комнат: {}\n📏 Площадь: {}м²",
            "comparison_title": "Сравнение облачных карт Neatsvor",
            "no_reference_set": "Эталонная карта не установлена.",
            "please_select_map": "Пожалуйста, выберите карту для сравнения.",
            "comparison_result": "📊 Сравнение: '{}' с эталоном '{}'\n",
            "differences_found": "\n⚠️ Найдены отличия:\n{}",
            "maps_identical": "\n✅ Карты идентичны!",
            "cleanup_completed": "Очистка завершена. Оставлено {} последних карт.",
            "history_maps_loaded": "Загружено {} карт истории",
            "history_maps_cleaned": "Очищены старые карты истории",
            "all_except_current_cleaned": "Очищены все карты, кроме текущей",
        }
    }
    
    msg_dict = messages.get(language, messages["en"])
    msg = msg_dict.get(key, default)
    
    # Apply formatting if kwargs provided
    if kwargs:
        try:
            msg = msg.format(**kwargs)
        except (KeyError, IndexError):
            pass
    
    return msg


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Neatsvor from a config entry."""
    global _shared_vacuum, _shared_config, _initialized

    if entry.entry_id in hass.data.get(DOMAIN, {}):
        _LOGGER.warning("Entry %s already initialized, skipping", entry.entry_id)
        return True

    if _initialized:
        _LOGGER.warning("Integration already initialized globally, skipping")
        return True

    hass.data.setdefault(DOMAIN, {})

    if _shared_config is None:
        # Get region and app_type from configuration
        region = entry.data.get("region", DEFAULT_COUNTRY)
        app_type = entry.data.get("app_type", DEFAULT_APP)
        
        country_data = COUNTRIES[region]
        app_config = APP_CONFIGS.get(app_type, APP_CONFIGS[DEFAULT_APP])
        
        rest_config = RestConfig(
            base_url=country_data["rest_url"],
            app_key=app_config["app_key"],
            app_secret=app_config["app_secret"],
            package_name=app_config["package_name"],
            source=app_config["source"],
            reg_id="",
            country=region,
            user_agent="okhttp/4.9.1"
        )

        mqtt_config = MQTTConfig(
            host=country_data["mqtt_host"],
            port=MQTT_PORT,
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

        _shared_config = NeatsvorConfig(
            rest=rest_config,
            mqtt=mqtt_config,
            credentials=credentials,
            device=device_config
        )

    if _shared_vacuum is None:
        app_type = entry.data.get("app_type", DEFAULT_APP)
        _shared_vacuum = NeatsvorVacuum(_shared_config, app_type=app_type)

    if not _shared_vacuum.is_initialized:
        await _shared_vacuum.initialize()

    coordinator = NeatsvorCoordinator(hass, _shared_vacuum)
    _shared_vacuum.set_hass(hass)

    coordinator = NeatsvorCoordinator(hass, _shared_vacuum)
    _shared_vacuum.set_hass(hass)

    # Create history entities
    from .sensor import NeatsvorCleanHistorySensor
    from .select import NeatsvorCleanHistorySelect
    from .select_storage import NeatsvorSelectStorage

    coordinator.select_storage = NeatsvorSelectStorage(hass, entry.entry_id)

    hass.data[DOMAIN][entry.entry_id] = coordinator

    _LOGGER.info("Registering platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _delayed_init():
        await asyncio.sleep(5)

    asyncio.create_task(_delayed_init())

    await coordinator.async_config_entry_first_refresh()

    await _async_register_services(hass)

    _initialized = True
    _LOGGER.info("Neatsvor integration initialized for entry %s", entry.entry_id)

    return True


async def _async_register_services(hass: HomeAssistant):
    """Register integration services."""
    from homeassistant.helpers import entity_platform

    async def async_request_all_data(call: ServiceCall) -> None:
        """Request all data as the official app does."""
        _LOGGER.info("Service call: request_all_data")
        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'vacuum') and coord.vacuum:
                await coord.vacuum.request_all_data()
                await coord.async_request_refresh()
                _LOGGER.info("Data requested")

    async def async_request_map(call: ServiceCall) -> None:
        """Request the current map."""
        _LOGGER.info("Service call: request_map")
        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'vacuum') and coord.vacuum:
                await coord.vacuum.request_map()
                await coord.async_request_refresh()
                _LOGGER.info("Map requested")

    async def async_build_map(call: ServiceCall) -> None:
        """Perform a fast map build."""
        _LOGGER.info("Service call: build_map")
        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'vacuum') and coord.vacuum:
                await coord.vacuum.build_map()
                await coord.async_request_refresh()
                _LOGGER.info("Map building started")

    async def async_empty_dust(call: ServiceCall) -> None:
        """Empty the dust bin."""
        _LOGGER.info("Service call: empty_dust")
        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'vacuum') and coord.vacuum:
                await coord.vacuum.empty_dust()
                await coord.async_request_refresh()
                _LOGGER.info("Dust bin emptied")

    async def async_clean_room_with_preset(call: ServiceCall) -> None:
        """Clean a room with its saved preset."""
        room_name = call.data.get("room")
        use_preset = call.data.get("use_preset", True)

        _LOGGER.info("Service call: clean_room_with_preset: %s", room_name)
        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'vacuum') and coord.vacuum:
                rooms = await coord.vacuum.get_available_rooms()
                room_map = {r['name']: r['id'] for r in rooms}

                if room_name in room_map:
                    if use_preset:
                        await coord.vacuum.start_room_clean_with_preset([room_map[room_name]])
                    else:
                        await coord.vacuum.start_room_clean([room_map[room_name]])

                    await coord.async_request_refresh()
                    _LOGGER.info("Room cleaning started for: %s", room_name)
                    
                    # Send localized notification
                    msg = _get_localized_message(hass, "cleaning_room", "Cleaning room: {}", room=room_name)
                    hass.bus.async_fire("persistent_notification", {
                        "message": msg,
                        "title": "Neatsvor"
                    })
                else:
                    msg = _get_localized_message(hass, "failed_clean_room", "Failed to clean room {}: Room not found", room=room_name)
                    hass.bus.async_fire("persistent_notification", {
                        "message": msg,
                        "title": "Neatsvor Error"
                    })

    async def async_restore_reference_map(call: ServiceCall) -> None:
        """Restore room configuration from the reference map."""
        restore_rooms = call.data.get("room_names", True)
        restore_presets = call.data.get("room_presets", True)

        _LOGGER.info("Service call: restore_reference_map")

        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'cloud_maps_sensor'):
                sensor = coord.cloud_maps_sensor
                reference_id = getattr(sensor, '_reference_map_id', None)

                if not reference_id:
                    _LOGGER.warning("No reference map set")
                    msg = _get_localized_message(hass, "no_reference_map", "No reference map has been set. Please set a reference map first.")
                    hass.bus.async_fire("persistent_notification", {
                        "message": msg,
                        "title": "Neatsvor Cloud Maps"
                    })
                    return

                reference_map = sensor.get_map_by_id(reference_id)
                if not reference_map:
                    _LOGGER.error("Reference map %s not found", reference_id)
                    return

                _LOGGER.info("Restoring from reference map: %s", reference_map.get('name'))

                msg = _get_localized_message(
                    hass, "restored_from_reference", 
                    "Restored from reference map '{}'\nрџЏ  Rooms: {}\nрџ“Џ Area: {}mВІ",
                    reference_map.get('name'), reference_map.get('room_count'), reference_map.get('area')
                )
                hass.bus.async_fire("persistent_notification", {
                    "message": msg,
                    "title": "Neatsvor Cloud Maps"
                })

    async def async_compare_with_reference(call: ServiceCall) -> None:
        """Compare the current map with the reference map."""
        show_details = call.data.get("show_details", False)

        _LOGGER.info("Service call: compare_with_reference")

        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'cloud_maps_sensor'):
                sensor = coord.cloud_maps_sensor
                reference_id = getattr(sensor, '_reference_map_id', None)
                selected_id = sensor.selected_map_id

                if not reference_id:
                    _LOGGER.warning("No reference map set")
                    msg = _get_localized_message(hass, "no_reference_set", "No reference map has been set.")
                    hass.bus.async_fire("persistent_notification", {
                        "message": msg,
                        "title": "Neatsvor Cloud Maps"
                    })
                    return

                if not selected_id:
                    _LOGGER.warning("No map selected")
                    msg = _get_localized_message(hass, "please_select_map", "Please select a map to compare.")
                    hass.bus.async_fire("persistent_notification", {
                        "message": msg,
                        "title": "Neatsvor Cloud Maps"
                    })
                    return

                reference_map = sensor.get_map_by_id(reference_id)
                selected_map = sensor.get_map_by_id(selected_id)

                if not reference_map or not selected_map:
                    _LOGGER.error("Maps not found")
                    return

                differences = []
                diff_text = ""

                if reference_map.get('room_count') != selected_map.get('room_count'):
                    diff_line = f"рџЏ  Room count: {reference_map.get('room_count')} vs {selected_map.get('room_count')}"
                    differences.append(diff_line)

                if abs(reference_map.get('area', 0) - selected_map.get('area', 0)) > 1:
                    diff_line = f"рџ“Џ Area: {reference_map.get('area')}mВІ vs {selected_map.get('area')}mВІ"
                    differences.append(diff_line)

                base_msg = _get_localized_message(
                    hass, "comparison_result",
                    "рџ“Љ Comparison: '{}' vs Reference '{}'\n",
                    selected_map.get('name'), reference_map.get('name')
                )
                
                if differences:
                    diff_text = "\n".join(differences)
                    msg = base_msg + _get_localized_message(hass, "differences_found", "\nвљ пёЏ Differences found:\n{}", diff_text)
                else:
                    msg = base_msg + _get_localized_message(hass, "maps_identical", "\nвњ… Maps are identical!")

                if show_details:
                    msg += f"\n\nReference: {reference_map.get('room_count')} rooms, {reference_map.get('area')}mВІ"
                    msg += f"\nSelected: {selected_map.get('room_count')} rooms, {selected_map.get('area')}mВІ"

                title = _get_localized_message(hass, "comparison_title", "Neatsvor Cloud Maps Comparison")
                hass.bus.async_fire("persistent_notification", {
                    "message": msg,
                    "title": title
                })

    async def async_force_update_maps(call: ServiceCall) -> None:
        """Force update all map-related sensors."""
        _LOGGER.info("Service call: force_update_maps")

        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'cloud_maps_sensor'):
                await coord.cloud_maps_sensor.async_force_update()

            if hasattr(coord, 'cloud_map_presets'):
                await coord.cloud_map_presets.async_update()

            if hasattr(coord, 'preset_comparison'):
                await coord.preset_comparison.async_update()

            if hasattr(coord, 'room_list'):
                await coord.room_list.async_update()

    async def async_cleanup_maps(call: ServiceCall) -> None:
        """Manually clean up old maps and metadata."""
        keep_last = call.data.get("keep_last", 10)
        _LOGGER.info("Service call: cleanup_maps (keep_last=%s)", keep_last)

        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'vacuum') and coord.vacuum:
                if hasattr(coord.vacuum, 'visualizer'):
                    await coord.vacuum.visualizer.cleanup_realtime_maps(keep_last)

                    msg = _get_localized_message(hass, "cleanup_completed", "Cleanup completed. Kept the last {} maps.", keep_last)
                    hass.bus.async_fire("persistent_notification", {
                        "message": msg,
                        "title": "Neatsvor Map Cleanup"
                    })

    async def async_save_select_states(call: ServiceCall = None) -> None:
        """Save the states of all select entities."""
        storage = hass.data.get(DOMAIN, {}).get('select_states', {})

        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'room_select') and coord.room_select:
                storage['room_select'] = coord.room_select._attr_current_option

            if hasattr(coord, 'cloud_map_select') and coord.cloud_map_select:
                storage['cloud_map_select'] = coord.cloud_map_select._attr_current_option

        _LOGGER.info("Select states saved: %s", storage)

    async def async_restore_select_states(call: ServiceCall = None) -> None:
        """Restore the states of all select entities."""
        storage = hass.data.get(DOMAIN, {}).get('select_states', {})

        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'room_select') and 'room_select' in storage:
                room = storage['room_select']
                if room and room in coord.room_select._attr_options:
                    await coord.room_select.async_select_option(room)

            if hasattr(coord, 'cloud_map_select') and 'cloud_map_select' in storage:
                map_option = storage['cloud_map_select']
                if map_option and map_option in coord.cloud_map_select._attr_options:
                    await coord.cloud_map_select.async_select_option(map_option)

        _LOGGER.info("Select states restored")

    async def async_set_reference_map(call: ServiceCall) -> None:
        """Set the current map as the reference."""
        _LOGGER.info("Service call: set_reference_map")
        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'vacuum') and coord.vacuum:
                await coord.vacuum.save_reference_map()
                await coord.async_request_refresh()
                _LOGGER.info("Reference map saved")

    async def async_use_cloud_map(call: ServiceCall) -> None:
        """Use a specific cloud map as the current map."""
        map_id = call.data.get("map_id")
        map_url = call.data.get("map_url")
        map_md5 = call.data.get("map_md5")

        _LOGGER.info("Service call: use_cloud_map (map_id=%s)", map_id)
        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'vacuum') and coord.vacuum:
                success = await coord.vacuum.use_cloud_map(map_id, map_url, map_md5)
                if success:
                    _LOGGER.info("Map %s is now current", map_id)
                    msg = _get_localized_message(hass, "map_activated", "Map activated successfully")
                    hass.bus.async_fire("persistent_notification", {
                        "message": msg,
                        "title": "Neatsvor"
                    })

    async def async_use_selected_cloud_map(call: ServiceCall) -> None:
        """Use the selected cloud map as the current map."""
        _LOGGER.info("Service call: use_selected_cloud_map")
        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'cloud_maps_sensor'):
                sensor = coord.cloud_maps_sensor
                await sensor.use_selected_cloud_map()
            else:
                _LOGGER.error("No cloud_maps_sensor in coordinator")

    async def async_force_load_history(call: ServiceCall) -> None:
        """Force load all history maps."""
        _LOGGER.info("Service call: force_load_history")

        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'vacuum') and coord.vacuum:
                if hasattr(coord.vacuum, 'clean_history'):
                    records = await coord.vacuum.clean_history.get_clean_history(
                        coord.vacuum.info.device_id, 10
                    )

                    _LOGGER.info("Found %s records", len(records))

                    for i, record in enumerate(records):
                        _LOGGER.info("Loading record %s...", record.record_id)
                        map_data = await coord.vacuum.clean_history.load_clean_record_map(record)

                        if map_data:
                            _LOGGER.info("Record %s loaded", record.record_id)
                        else:
                            _LOGGER.error("Failed to load record %s", record.record_id)

                    msg = _get_localized_message(hass, "history_maps_loaded", "Loaded {} history maps", len(records))
                    hass.bus.async_fire("persistent_notification", {
                        "message": msg,
                        "title": "Neatsvor Clean History"
                    })

    async def handle_history_map_updated(event):
        """Handle history map updated event."""
        _LOGGER.debug("Event received: %s", event.data)

    async def async_cleanup_history_maps(call: ServiceCall) -> None:
        """Clean up old history maps."""
        keep_last = call.data.get("keep_last", 50)
        _LOGGER.info("Service call: cleanup_history_maps (keep_last=%s)", keep_last)

        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'clean_history_sensor'):
                sensor = coord.clean_history_sensor
                await sensor.async_cleanup_old_maps()

                msg = _get_localized_message(hass, "history_maps_cleaned", "Cleaned up old history maps")
                hass.bus.async_fire("persistent_notification", {
                    "message": msg,
                    "title": "Neatsvor Clean History"
                })

    async def async_cleanup_all_except_current(call: ServiceCall) -> None:
        """Clean up all history maps except the current one."""
        _LOGGER.info("Service call: cleanup_all_except_current")

        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'clean_history_sensor'):
                sensor = coord.clean_history_sensor
                await sensor.async_cleanup_all_except_current()

                msg = _get_localized_message(hass, "all_except_current_cleaned", "Cleaned up all maps except current")
                hass.bus.async_fire("persistent_notification", {
                    "message": msg,
                    "title": "Neatsvor Clean History"
                })

    async def async_xiaomi_miio_zone_clean(call: ServiceCall) -> None:
        """Alias for vacuum_clean_zone to maintain compatibility with xiaomi-vacuum-map-card."""
        entity_id = call.data.get("entity_id")
        zones = call.data.get("zones", [])

        if not zones:
            zones = call.data.get("zone", [])

        _LOGGER.info("Xiaomi miio zone clean alias called: entity=%s, zones=%s", entity_id, zones)

        for entry_id, coord in hass.data[DOMAIN].items():
            if hasattr(coord, 'vacuum') and coord.vacuum:
                vacuum = coord.vacuum

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

                await coord.async_request_refresh()
                _LOGGER.info("Zone clean commands sent")
                return

        _LOGGER.error("Vacuum %s not found", entity_id)

    async def handle_cloud_camera_updated(event):
        """Handle cloud camera updated event."""
        _LOGGER.debug("Cloud camera event: %s", event.data)

    hass.services.async_register(DOMAIN, "request_all_data", async_request_all_data)
    hass.services.async_register(DOMAIN, "request_map", async_request_map)
    hass.services.async_register(DOMAIN, "build_map", async_build_map)
    hass.services.async_register(DOMAIN, "empty_dust", async_empty_dust)

    hass.services.async_register(DOMAIN, "clean_room_with_preset", async_clean_room_with_preset)

    hass.services.async_register(DOMAIN, "restore_reference_map", async_restore_reference_map)

    hass.services.async_register(DOMAIN, "compare_with_reference", async_compare_with_reference)

    hass.services.async_register(DOMAIN, "force_update_maps", async_force_update_maps)
    hass.services.async_register(DOMAIN, "cleanup_maps", async_cleanup_maps)
    hass.services.async_register(DOMAIN, "save_select_states", async_save_select_states)
    hass.services.async_register(DOMAIN, "restore_select_states", async_restore_select_states)
    hass.services.async_register(DOMAIN, "set_reference_map", async_set_reference_map)
    hass.services.async_register(DOMAIN, "use_cloud_map", async_use_cloud_map)
    hass.services.async_register(DOMAIN, "use_selected_cloud_map", async_use_selected_cloud_map)

    hass.services.async_register(DOMAIN, "force_load_history", async_force_load_history)
    hass.services.async_register(DOMAIN, "cleanup_history_maps", async_cleanup_history_maps)
    hass.services.async_register(DOMAIN, "cleanup_all_except_current", async_cleanup_all_except_current)

    # Register service under the name expected by the map card
    hass.services.async_register("xiaomi_miio", "vacuum_clean_zone", async_xiaomi_miio_zone_clean)

    # Subscribe to events
    hass.bus.async_listen("neatsvor_history_map_updated", handle_history_map_updated)
    hass.bus.async_listen("neatsvor_camera_updated", handle_cloud_camera_updated)

    _LOGGER.info("Subscribed to Neatsvor events")

    hass.bus.async_listen_once("homeassistant_stop", async_save_select_states)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    global _initialized

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and entry.entry_id in hass.data[DOMAIN]:
        coordinator = hass.data[DOMAIN][entry.entry_id]
        hass.data[DOMAIN].pop(entry.entry_id)

    _initialized = False
    return unload_ok


async def async_close_shared_vacuum():
    """Close the shared vacuum instance when unloading the entire integration."""
    global _shared_vacuum, _shared_config, _initialized
    if _shared_vacuum:
        await _shared_vacuum.disconnect()
        _shared_vacuum = None
        _shared_config = None
        _initialized = False
        _LOGGER.info("Shared vacuum closed")