"""Neatsvor integration for Home Assistant."""

import logging
import asyncio
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


async def _migrate_old_config(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old configuration (with region) to new format (with phone_code)."""
    # Check if migration is needed
    if CONF_PHONE_CODE in entry.data:
        return False  # Already migrated
    
    if "region" not in entry.data:
        return False  # No old data
    
    old_region = entry.data.get("region")
    
    # Map old region to phone code
    region_to_phone = {
        "ru": "7",
        "cn": "86",
        "de": "49",
        "us": "1",
        "sg": "65",
    }
    
    phone_code = region_to_phone.get(old_region, DEFAULT_PHONE_CODE)
    
    # Get data center info
    manager = get_data_center_manager(hass)
    data_center = await hass.async_add_executor_job(
        manager.get_data_center_by_phone_code, phone_code, hass.config.language
    )
    
    # Create new data
    new_data = dict(entry.data)
    new_data[CONF_PHONE_CODE] = phone_code
    
    if data_center:
        new_data["rest_url"] = data_center["rest_url"]
        new_data["mqtt_host"] = data_center["mqtt_host"]
        new_data["mqtt_port"] = data_center.get("mqtt_port", MQTT_PORT)
        new_data["country_code"] = data_center.get("country_code", "")
        new_data["country_name"] = data_center.get("country_name", "")
    else:
        # Fallback to old COUNTRIES data
        country_data = COUNTRIES.get(old_region, COUNTRIES[DEFAULT_COUNTRY])
        new_data["rest_url"] = country_data["rest_url"]
        new_data["mqtt_host"] = country_data["mqtt_host"]
        new_data["mqtt_port"] = MQTT_PORT
    
    # Remove old key
    new_data.pop("region", None)
    
    # Update entry
    hass.config_entries.async_update_entry(entry, data=new_data)
    _LOGGER.info("Migrated configuration from region '%s' to phone_code '%s'", old_region, phone_code)
    
    return True


def _get_localized_message(hass, key: str, default: str, **kwargs) -> str:
    """Get localized message from translations with named placeholders."""
    language = hass.config.language if hass else "en"
    
    # Simple translation map for notifications with named placeholders
    messages = {
        "en": {
            "cloud_maps_refreshed": "Cloud maps list refreshed",
            "no_map_selected": "Please select a map first",
            "map_set_as_reference": "Map set as reference",
            "reference_map_restored": "Reference map restored from device",
            "reference_map_restore_failed": "Failed to restore reference map from device",
            "downloading_map": "Downloading map {name}...",
            "map_downloaded": "Map downloaded successfully",
            "map_not_found": "Map {name} not found in API",
            "download_error": "Error downloading map: {error}",
            "delete_map": "Delete map '{name}'? (stub implementation - would delete from cloud)",
            "vacuum_not_available": "Vacuum not available",
            "map_save_sent": "Command sent to save current map to cloud",
            "error_saving_map": "Error saving map: {error}",
            "cleaning_room": "Cleaning room: {room}",
            "failed_clean_room": "Failed to clean room {room}: {reason}",
            "map_activated": "Map activated successfully",
            "map_activation_failed": "Failed to activate map",
            "map_auto_restored": "Map auto-restored from reference",
            "no_reference_map": "No reference map has been set. Please set a reference map first.",
            "restored_from_reference": "Restored from reference map '{name}'\n🏠 Rooms: {rooms}\n📏 Area: {area}m²",
            "comparison_title": "Neatsvor Cloud Maps Comparison",
            "no_reference_set": "No reference map has been set.",
            "please_select_map": "Please select a map to compare.",
            "comparison_result": "📊 Comparison: '{selected}' vs Reference '{reference}'\n",
            "differences_found": "\n⚠️ Differences found:\n{diff}",
            "maps_identical": "\n✅ Maps are identical!",
            "cleanup_completed": "Cleanup completed. Kept the last {count} maps.",
            "history_maps_loaded": "Loaded {count} history maps",
            "history_maps_cleaned": "Cleaned up old history maps",
            "all_except_current_cleaned": "Cleaned up all maps except current",
        },
        "ru": {
            "cloud_maps_refreshed": "Список облачных карт обновлен",
            "no_map_selected": "Пожалуйста, сначала выберите карту",
            "map_set_as_reference": "Карта установлена как эталонная",
            "reference_map_restored": "Эталонная карта восстановлена с устройства",
            "reference_map_restore_failed": "Не удалось восстановить эталонную карту с устройства",
            "downloading_map": "Скачивание карты {name}...",
            "map_downloaded": "Карта успешно скачана",
            "map_not_found": "Карта {name} не найдена в API",
            "download_error": "Ошибка скачивания карты: {error}",
            "delete_map": "Удалить карту '{name}'? (заглушка - будет удалено из облака)",
            "vacuum_not_available": "Пылесос недоступен",
            "map_save_sent": "Команда на сохранение карты в облако отправлена",
            "error_saving_map": "Ошибка сохранения карты: {error}",
            "cleaning_room": "Уборка комнаты: {room}",
            "failed_clean_room": "Не удалось убрать комнату {room}: {reason}",
            "map_activated": "Карта успешно активирована",
            "map_activation_failed": "Не удалось активировать карту",
            "map_auto_restored": "Карта автоматически восстановлена из эталона",
            "no_reference_map": "Эталонная карта не установлена. Пожалуйста, сначала установите эталонную карту.",
            "restored_from_reference": "Восстановлено из эталонной карты '{name}'\n🏠 Комнат: {rooms}\n📏 Площадь: {area}м²",
            "comparison_title": "Сравнение облачных карт Neatsvor",
            "no_reference_set": "Эталонная карта не установлена.",
            "please_select_map": "Пожалуйста, выберите карту для сравнения.",
            "comparison_result": "📊 Сравнение: '{selected}' с эталоном '{reference}'\n",
            "differences_found": "\n⚠️ Найдены отличия:\n{diff}",
            "maps_identical": "\n✅ Карты идентичны!",
            "cleanup_completed": "Очистка завершена. Оставлено {count} последних карт.",
            "history_maps_loaded": "Загружено {count} карт истории",
            "history_maps_cleaned": "Очищены старые карты истории",
            "all_except_current_cleaned": "Очищены все карты, кроме текущей",
        }
    }
    
    msg_dict = messages.get(language, messages["en"])
    msg = msg_dict.get(key, default)
    
    # Apply formatting with named placeholders if kwargs provided
    if kwargs:
        try:
            msg = msg.format(**kwargs)
        except (KeyError, IndexError, ValueError) as e:
            _LOGGER.debug("Failed to format message '%s' with kwargs %s: %s", key, kwargs, e)
            # Return raw message with placeholders if formatting fails
    
    return msg


async def _build_config(hass: HomeAssistant, entry: ConfigEntry) -> NeatsvorConfig:
    """Build NeatsvorConfig from entry data."""
    phone_code = entry.data.get(CONF_PHONE_CODE, DEFAULT_PHONE_CODE)
    app_type = entry.data.get("app_type", DEFAULT_APP)
    
    # Try to get data center from stored values first
    rest_url = entry.data.get("rest_url")
    mqtt_host = entry.data.get("mqtt_host")
    mqtt_port = entry.data.get("mqtt_port", MQTT_PORT)
    
    # If not stored, get from data center manager
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
            # Fallback to COUNTRIES using old method (for migration)
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Neatsvor from a config entry."""
    
    # Migrate old configuration if needed
    await _migrate_old_config(hass, entry)

    # Check if this entry is already initialized
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        _LOGGER.warning("Entry %s already initialized, skipping", entry.entry_id)
        return True

    hass.data.setdefault(DOMAIN, {})
    
    # Build config for this entry
    config = await _build_config(hass, entry)
    
    # Create vacuum instance for this entry
    app_type = entry.data.get("app_type", DEFAULT_APP)
    vacuum = NeatsvorVacuum(config, app_type=app_type)
    
    if not vacuum.is_initialized:
        await vacuum.initialize()
    
    vacuum.set_hass(hass)
    
    # Create coordinator
    coordinator = NeatsvorCoordinator(hass, vacuum)
    
    # Create select storage
    from .select_storage import NeatsvorSelectStorage
    coordinator.select_storage = NeatsvorSelectStorage(hass, entry.entry_id)

    # Migrate old data
    old_storage_path = hass.config.path(f"custom_components/neatsvor/select_states_{entry.entry_id}.json")
    await coordinator.select_storage.async_migrate_from_file(Path(old_storage_path))

    # Ensure data is loaded
    await coordinator.select_storage.async_ensure_loaded()
    
    # Store in hass.data
    entry_data = {
        'coordinator': coordinator,
        'vacuum': vacuum,
        'config': config,
    }
    hass.data[DOMAIN][entry.entry_id] = entry_data

    _LOGGER.info("Registering platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start coordinator refresh
    asyncio.create_task(coordinator.async_config_entry_first_refresh())

    # Register services only once globally
    if not hass.data[DOMAIN].get('services_registered'):
        await _async_register_services(hass)
        hass.data[DOMAIN]['services_registered'] = True

    # Register stop handler
    hass.bus.async_listen_once("homeassistant_stop", _async_close_all_vacuums)

    _LOGGER.info("Neatsvor integration initialized for entry %s", entry.entry_id)

    return True


async def _async_register_services(hass: HomeAssistant):
    """Register integration services."""
    from homeassistant.helpers import entity_platform

    async def async_request_all_data(call: ServiceCall) -> None:
        """Request all data as the official app does."""
        _LOGGER.info("Service call: request_all_data")
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                await coordinator.vacuum.request_all_data()
                await coordinator.async_request_refresh()
                _LOGGER.info("Data requested for entry %s", entry_id)

    async def async_request_map(call: ServiceCall) -> None:
        """Request the current map."""
        _LOGGER.info("Service call: request_map")
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                await coordinator.vacuum.request_map()
                await coordinator.async_request_refresh()
                _LOGGER.info("Map requested for entry %s", entry_id)

    async def async_build_map(call: ServiceCall) -> None:
        """Perform a fast map build."""
        _LOGGER.info("Service call: build_map")
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                await coordinator.vacuum.build_map()
                await coordinator.async_request_refresh()
                _LOGGER.info("Map building started for entry %s", entry_id)

    async def async_empty_dust(call: ServiceCall) -> None:
        """Empty the dust bin."""
        _LOGGER.info("Service call: empty_dust")
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                await coordinator.vacuum.empty_dust()
                await coordinator.async_request_refresh()
                _LOGGER.info("Dust bin emptied for entry %s", entry_id)

    async def async_clean_room_with_preset(call: ServiceCall) -> None:
        """Clean a room with its saved preset."""
        room_name = call.data.get("room")
        use_preset = call.data.get("use_preset", True)

        _LOGGER.info("Service call: clean_room_with_preset: %s", room_name)
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                rooms = await coordinator.vacuum.get_available_rooms()
                room_map = {r['name']: r['id'] for r in rooms}

                if room_name in room_map:
                    if use_preset:
                        await coordinator.vacuum.start_room_clean_with_preset([room_map[room_name]])
                    else:
                        await coordinator.vacuum.start_room_clean([room_map[room_name]])

                    await coordinator.async_request_refresh()
                    _LOGGER.info("Room cleaning started for: %s", room_name)
                    
                    # Send localized notification with named placeholder
                    msg = _get_localized_message(
                        hass, "cleaning_room", 
                        "Cleaning room: {room}", 
                        room=room_name
                    )
                    hass.bus.async_fire("persistent_notification", {
                        "message": msg,
                        "title": "Neatsvor"
                    })
                else:
                    msg = _get_localized_message(
                        hass, "failed_clean_room", 
                        "Failed to clean room {room}: room not found", 
                        room=room_name,
                        reason="room not found"
                    )
                    hass.bus.async_fire("persistent_notification", {
                        "message": msg,
                        "title": "Neatsvor Error"
                    })

    async def async_restore_reference_map(call: ServiceCall) -> None:
        """Restore room configuration from the reference map."""
        restore_rooms = call.data.get("room_names", True)
        restore_presets = call.data.get("room_presets", True)

        _LOGGER.info("Service call: restore_reference_map")

        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'cloud_maps_sensor'):
                sensor = coordinator.cloud_maps_sensor
                reference_id = getattr(sensor, '_reference_map_id', None)

                if not reference_id:
                    _LOGGER.warning("No reference map set for entry %s", entry_id)
                    msg = _get_localized_message(
                        hass, "no_reference_map", 
                        "No reference map has been set. Please set a reference map first."
                    )
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
                    "Restored from reference map '{name}'\n🏠 Rooms: {rooms}\n📏 Area: {area}m²",
                    name=reference_map.get('name'),
                    rooms=reference_map.get('room_count'),
                    area=reference_map.get('area')
                )
                hass.bus.async_fire("persistent_notification", {
                    "message": msg,
                    "title": "Neatsvor Cloud Maps"
                })

    async def async_compare_with_reference(call: ServiceCall) -> None:
        """Compare the current map with the reference map."""
        show_details = call.data.get("show_details", False)

        _LOGGER.info("Service call: compare_with_reference")

        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'cloud_maps_sensor'):
                sensor = coordinator.cloud_maps_sensor
                reference_id = getattr(sensor, '_reference_map_id', None)
                selected_id = sensor.selected_map_id

                if not reference_id:
                    _LOGGER.warning("No reference map set for entry %s", entry_id)
                    msg = _get_localized_message(
                        hass, "no_reference_set", 
                        "No reference map has been set."
                    )
                    hass.bus.async_fire("persistent_notification", {
                        "message": msg,
                        "title": "Neatsvor Cloud Maps"
                    })
                    return

                if not selected_id:
                    _LOGGER.warning("No map selected for entry %s", entry_id)
                    msg = _get_localized_message(
                        hass, "please_select_map", 
                        "Please select a map to compare."
                    )
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
                    diff_line = f"🏠 Room count: {reference_map.get('room_count')} vs {selected_map.get('room_count')}"
                    differences.append(diff_line)

                if abs(reference_map.get('area', 0) - selected_map.get('area', 0)) > 1:
                    diff_line = f"📏 Area: {reference_map.get('area')}m² vs {selected_map.get('area')}m²"
                    differences.append(diff_line)

                base_msg = _get_localized_message(
                    hass, "comparison_result",
                    "📊 Comparison: '{selected}' vs Reference '{reference}'\n",
                    selected=selected_map.get('name'),
                    reference=reference_map.get('name')
                )
                
                if differences:
                    diff_text = "\n".join(differences)
                    msg = base_msg + _get_localized_message(
                        hass, "differences_found", 
                        "\n⚠️ Differences found:\n{diff}", 
                        diff=diff_text
                    )
                else:
                    msg = base_msg + _get_localized_message(
                        hass, "maps_identical", 
                        "\n✅ Maps are identical!"
                    )

                if show_details:
                    msg += f"\n\nReference: {reference_map.get('room_count')} rooms, {reference_map.get('area')}m²"
                    msg += f"\nSelected: {selected_map.get('room_count')} rooms, {selected_map.get('area')}m²"

                title = _get_localized_message(
                    hass, "comparison_title", 
                    "Neatsvor Cloud Maps Comparison"
                )
                hass.bus.async_fire("persistent_notification", {
                    "message": msg,
                    "title": title
                })

    async def async_force_update_maps(call: ServiceCall) -> None:
        """Force update all map-related sensors."""
        _LOGGER.info("Service call: force_update_maps")

        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator:
                if hasattr(coordinator, 'cloud_maps_sensor'):
                    await coordinator.cloud_maps_sensor.async_force_update()

                if hasattr(coordinator, 'cloud_map_presets'):
                    await coordinator.cloud_map_presets.async_update()

                if hasattr(coordinator, 'preset_comparison'):
                    await coordinator.preset_comparison.async_update()

                if hasattr(coordinator, 'room_list'):
                    await coordinator.room_list.async_update()

    async def async_cleanup_maps(call: ServiceCall) -> None:
        """Manually clean up old maps and metadata."""
        keep_last = call.data.get("keep_last", 10)
        _LOGGER.info("Service call: cleanup_maps (keep_last=%s)", keep_last)

        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                if hasattr(coordinator.vacuum, 'visualizer'):
                    await coordinator.vacuum.visualizer.cleanup_realtime_maps(keep_last)

                    msg = _get_localized_message(
                        hass, "cleanup_completed", 
                        "Cleanup completed. Kept the last {count} maps.",
                        count=keep_last
                    )
                    hass.bus.async_fire("persistent_notification", {
                        "message": msg,
                        "title": "Neatsvor Map Cleanup"
                    })

    async def async_save_select_states(call: ServiceCall = None) -> None:
        """Save the states of all select entities."""
        storage = hass.data.get(DOMAIN, {}).get('select_states', {})

        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator:
                if hasattr(coordinator, 'room_select') and coordinator.room_select:
                    storage['room_select'] = coordinator.room_select._attr_current_option

                if hasattr(coordinator, 'cloud_map_select') and coordinator.cloud_map_select:
                    storage['cloud_map_select'] = coordinator.cloud_map_select._attr_current_option

        _LOGGER.info("Select states saved: %s", storage)

    async def async_restore_select_states(call: ServiceCall = None) -> None:
        """Restore the states of all select entities."""
        storage = hass.data.get(DOMAIN, {}).get('select_states', {})

        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator:
                if hasattr(coordinator, 'room_select') and 'room_select' in storage:
                    room = storage['room_select']
                    if room and room in coordinator.room_select._attr_options:
                        await coordinator.room_select.async_select_option(room)

                if hasattr(coordinator, 'cloud_map_select') and 'cloud_map_select' in storage:
                    map_option = storage['cloud_map_select']
                    if map_option and map_option in coordinator.cloud_map_select._attr_options:
                        await coordinator.cloud_map_select.async_select_option(map_option)

        _LOGGER.info("Select states restored")

    async def async_set_reference_map(call: ServiceCall) -> None:
        """Set the current map as the reference."""
        _LOGGER.info("Service call: set_reference_map")
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                await coordinator.vacuum.save_reference_map()
                await coordinator.async_request_refresh()
                _LOGGER.info("Reference map saved for entry %s", entry_id)

    async def async_use_cloud_map(call: ServiceCall) -> None:
        """Use a specific cloud map as the current map."""
        map_id = call.data.get("map_id")
        map_url = call.data.get("map_url")
        map_md5 = call.data.get("map_md5")

        _LOGGER.info("Service call: use_cloud_map (map_id=%s)", map_id)
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                success = await coordinator.vacuum.use_cloud_map(map_id, map_url, map_md5)
                if success:
                    _LOGGER.info("Map %s is now current for entry %s", map_id, entry_id)
                    msg = _get_localized_message(
                        hass, "map_activated", 
                        "Map activated successfully"
                    )
                    hass.bus.async_fire("persistent_notification", {
                        "message": msg,
                        "title": "Neatsvor"
                    })

    async def async_use_selected_cloud_map(call: ServiceCall) -> None:
        """Use the selected cloud map as the current map."""
        _LOGGER.info("Service call: use_selected_cloud_map")
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'cloud_maps_sensor'):
                sensor = coordinator.cloud_maps_sensor
                await sensor.use_selected_cloud_map()
            else:
                _LOGGER.error("No cloud_maps_sensor in coordinator for entry %s", entry_id)

    async def async_force_load_history(call: ServiceCall) -> None:
        """Force load all history maps."""
        _LOGGER.info("Service call: force_load_history")

        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
                if hasattr(coordinator.vacuum, 'clean_history'):
                    records = await coordinator.vacuum.clean_history.get_clean_history(
                        coordinator.vacuum.info.device_id, 10
                    )

                    _LOGGER.info("Found %s records", len(records))

                    for i, record in enumerate(records):
                        _LOGGER.info("Loading record %s...", record.record_id)
                        map_data = await coordinator.vacuum.clean_history.load_clean_record_map(record)

                        if map_data:
                            _LOGGER.info("Record %s loaded", record.record_id)
                        else:
                            _LOGGER.error("Failed to load record %s", record.record_id)

                    msg = _get_localized_message(
                        hass, "history_maps_loaded", 
                        "Loaded {count} history maps",
                        count=len(records)
                    )
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

        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'clean_history_sensor'):
                sensor = coordinator.clean_history_sensor
                await sensor.async_cleanup_old_maps()

                msg = _get_localized_message(
                    hass, "history_maps_cleaned", 
                    "Cleaned up old history maps"
                )
                hass.bus.async_fire("persistent_notification", {
                    "message": msg,
                    "title": "Neatsvor Clean History"
                })

    async def async_cleanup_all_except_current(call: ServiceCall) -> None:
        """Clean up all history maps except the current one."""
        _LOGGER.info("Service call: cleanup_all_except_current")

        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'clean_history_sensor'):
                sensor = coordinator.clean_history_sensor
                await sensor.async_cleanup_all_except_current()

                msg = _get_localized_message(
                    hass, "all_except_current_cleaned", 
                    "Cleaned up all maps except current"
                )
                hass.bus.async_fire("persistent_notification", {
                    "message": msg,
                    "title": "Neatsvor Clean History"
                })

    async def async_vacuum_zone_clean(call: ServiceCall) -> None:
        """Alias for vacuum_clean_zone to maintain compatibility with xiaomi-vacuum-map-card."""
        entity_id = call.data.get("entity_id")
        zones = call.data.get("zones", [])

        if not zones:
            zones = call.data.get("zone", [])

        _LOGGER.info("Neatsvor vacuum zone clean alias called: entity=%s, zones=%s", entity_id, zones)

        for entry_id, entry_data in hass.data[DOMAIN].items():
            if entry_id == 'services_registered':
                continue
            coordinator = entry_data.get('coordinator')
            if coordinator and hasattr(coordinator, 'vacuum') and coordinator.vacuum:
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

    # --- ZONE CLEAN SERVICE ---
    hass.services.async_register(DOMAIN, "vacuum_clean_zone", async_vacuum_zone_clean)

    # Subscribe to events
    hass.bus.async_listen("neatsvor_history_map_updated", handle_history_map_updated)
    hass.bus.async_listen("neatsvor_camera_updated", handle_cloud_camera_updated)

    _LOGGER.info("Subscribed to Neatsvor events")

    hass.bus.async_listen_once("homeassistant_stop", async_save_select_states)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and entry.entry_id in hass.data.get(DOMAIN, {}):
        entry_data = hass.data[DOMAIN][entry.entry_id]
        
        # Disconnect vacuum
        if 'vacuum' in entry_data:
            try:
                await entry_data['vacuum'].disconnect()
                _LOGGER.info("Vacuum disconnected for entry %s", entry.entry_id)
            except Exception as e:
                _LOGGER.error("Error disconnecting vacuum for entry %s: %s", entry.entry_id, e)
        
        # Remove entry data
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.info("Entry %s unloaded", entry.entry_id)

    # If no entries left, reset services_registered flag
    entries = [k for k in hass.data.get(DOMAIN, {}) if k != 'services_registered']
    if not entries:
        hass.data[DOMAIN]['services_registered'] = False
        _LOGGER.info("All entries unloaded, services unregistered")

    return unload_ok


async def _async_close_all_vacuums(event):
    """Close all vacuum instances when HA stops."""
    _LOGGER.info("Closing all Neatsvor vacuum instances")
    
    for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
        if entry_id == 'services_registered':
            continue
        if 'vacuum' in entry_data:
            try:
                await entry_data['vacuum'].disconnect()
                _LOGGER.info("Vacuum closed for entry %s", entry_id)
            except Exception as e:
                _LOGGER.error("Error closing vacuum for entry %s: %s", entry_id, e)