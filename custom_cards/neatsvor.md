# Neatsvor

This platform can be used to control Neatsvor vacuums connected to Home Assistant using the [Neatsvor integration](https://github.com/CoderAS-ru/hass-neatsvor).

## Available templates

### Zone cleaning (`vacuum_clean_zone`)

Uses 4 coordinates to clean rectangular zones.

**Used service:** `neatsvor.vacuum_clean_zone`
  <details>
  <summary>Example configuration</summary>
    
  **Example configuration:**
  ```yaml
  map_modes:
    - template: vacuum_clean_zone
  ```

  </details>
  <details>
  <summary>Example video</summary>

    https://user-images.githubusercontent.com/6118709/141666913-d95f082d-f5bf-4ab5-a478-ba44effe6f34.mp4

  </details>

## Services

| Service |	Description |
|---------|-------------|
| `neatsvor.zone_clean` |	Start zone cleaning |
| `neatsvor.clean_room_with_preset` |	Start room cleaning using saved presets |
| `neatsvor.set_reference_map` |	Save the current map as a reference |
| `neatsvor.restore_reference_map` |	Restore room configuration from the reference map |
| `neatsvor.save_map_to_cloud` |	Save the current map to the cloud |
| `neatsvor.request_all_data` |	Request all data (like the official app) |
| `neatsvor.build_map` |	Perform a fast map build without cleaning |
| `neatsvor.empty_dust` |	Force empty the dust container |

## Supported entities
For full functionality, your Neatsvor vacuum should provide the following entities in Home Assistant:

| **Entity type**	| **Example ID**	| **Description** |
|-----------------|-----------------|-----------------|
| `vacuum.*`	| vacuum.neatsvor_vacuum	| Main vacuum entity |
| `select.*` | select.neatsvor_fan_speed	| Fan speed control |
| `select.*` | select.neatsvor_water_level	| Water level control (for mopping models) |
| `select.*` | select.neatsvor_clean_mode	| Cleaning mode selection |
| `sensor.*` | sensor.neatsvor_main_brush	| Main brush wear (percent) |
| `sensor.*`	| sensor.neatsvor_side_brush	| Side brush wear (percent) | 
| `sensor.*`	| sensor.neatsvor_hepa_filter	| HEPA filter wear (percent) | 
| `sensor.*	` | sensor.neatsvor_total_cleanings	| Total cleaning count | 
| `sensor.*`	| sensor.neatsvor_cleaning_area	| Total cleaned area (m²) | 
| `sensor.*` | sensor.neatsvor_cleaning_time	| Total cleaning time (minutes) | 

  <details>
  <summary>Example card configuration</summary>
    
  ```yaml
# Below is a complete example of a `neatsvor-vacuum-map-card` configuration for a Neatsvor vacuum. It demonstrates zone cleaning, room selection, cloud maps, and cleaning history.
# IMPORTANT: In this sample, you need to replace all "your_neatsvor*" with the actual names of your entities

type: custom:neatsvor-vacuum-map-card
entity: vacuum.your_neatsvor_smart_vacuum
preset_name: 🗺️ Live map
map_source:
  camera: camera.your_neatsvor_live_map
calibration_source:
  identity: true
refresh_interval: 1
title: Neatsvor Vacuum
zones:
  color: rgba(255, 255, 255, 0.3)
  border_color: rgba(255, 255, 255, 0.8)
  stroke_width: 2
  enable_drag: true
  enable_rotate: true
  enable_remove_last_point: true
  service: neatsvor.vacuum_clean_zone
  service_data:
    entity_id: vacuum.your_neatsvor_smart_vacuum
    zones: "[[x1, y1, x2, y2, 1]]"
icons:
  - icon: mdi:play
    tooltip: Start cleaning
    tap_action:
      action: call-service
      service: vacuum.start
      service_data:
        entity_id: vacuum.your_neatsvor_smart_vacuum
  - icon: mdi:pause
    tooltip: Pause
    tap_action:
      action: call-service
      service: vacuum.pause
      service_data:
        entity_id: vacuum.your_neatsvor_smart_vacuum
  - icon: mdi:stop
    tooltip: Stop
    tap_action:
      action: call-service
      service: vacuum.stop
      service_data:
        entity_id: vacuum.your_neatsvor_smart_vacuum
  - type: menu
    menu_id: fan_speed
    tooltip: Fan speed
    icon: mdi:fan
    entity: select.your_neatsvor_fan_speed
    available_values_attribute: options
    icon_mapping:
      quiet: mdi:fan-speed-1
      Тихий: mdi:fan-speed-1
      normal: mdi:fan-speed-2
      Обычный: mdi:fan-speed-2
      strong: mdi:fan-speed-3
      Сильный: mdi:fan-speed-3
      max: mdi:fan-plus
      Максимальный: mdi:fan-plus
    tap_action:
      action: call-service
      service: select.select_option
      service_data:
        entity_id: select.your_neatsvor_fan_speed
        option: "[[value]]"
  - type: menu
    menu_id: water_box_mode
    tooltip: Water level
    icon: mdi:water
    entity: select.your_neatsvor_water_level
    available_values_attribute: options
    icon_mapping:
      low: mdi:water-minus
      Низкий: mdi:water-minus
      middle: mdi:water
      Средний: mdi:water
      high: mdi:water-plus
      Высокий: mdi:water-plus
    tap_action:
      action: call-service
      service: select.select_option
      service_data:
        entity_id: select.your_neatsvor_water_level
        option: "[[value]]"
  - type: menu
    menu_id: clean_mode
    tooltip: Cleaning mode
    icon: mdi:vacuum
    entity: select.your_neatsvor_clean_mode
    available_values_attribute: options
    icon_mapping:
      sweep: mdi:broom
      Только подмести: mdi:broom
      mop: mdi:spray
      Только мыть: mdi:spray
      sweepMop: mdi:vacuum-outline
      Подмести и вымыть: mdi:vacuum-outline
    tap_action:
      action: call-service
      service: select.select_option
      service_data:
        entity_id: select.your_neatsvor_clean_mode
        option: "[[value]]"
  - icon: mdi:home-import-outline
    tooltip: Return to base
    tap_action:
      action: call-service
      service: vacuum.return_to_base
      service_data:
        entity_id: vacuum.your_neatsvor_smart_vacuum
  - icon: mdi:map-marker-radius
    tooltip: Locate
    tap_action:
      action: call-service
      service: vacuum.locate
      service_data:
        entity_id: vacuum.your_neatsvor_smart_vacuum
  - icon: mdi:map-search
    tooltip: Build map
    tap_action:
      action: call-service
      service: neatsvor.build_map
      service_data:
        entity_id: vacuum.your_neatsvor_smart_vacuum
  - icon: mdi:delete
    tooltip: Empty dust bin
    tap_action:
      action: call-service
      service: neatsvor.empty_dust
      service_data:
        entity_id: vacuum.your_neatsvor_smart_vacuum
tiles:
  - entity: sensor.your_neatsvor_status
    name: Status
  - entity: sensor.your_neatsvor_battery
    name: Battery
    unit: "%"
    icon: mdi:battery
  - entity: sensor.your_neatsvor_last_clean
    name: Last Clean
  - entity: sensor.your_neatsvor_current_clean_time
    name: Clean Time
    unit: min
  - entity: sensor.your_neatsvor_current_clean_area
    name: Clean Area
    unit: m²
additional_presets:
  - preset_name: 🧹 Room cleaning
    entity: vacuum.your_neatsvor_smart_vacuum
    map_source:
      camera: camera.your_neatsvor_live_map
    calibration_source:
      identity: true
    icons:
      - icon: mdi:refresh
        tooltip: Refresh room list
        label: Refresh room list
        tap_action:
          action: call-service
          service: homeassistant.update_entity
          service_data:
            entity_id:
              - select.your_neatsvor_room_select
              - sensor.your_neatsvor
      - icon: mdi:home-circle-outline
        label: All rooms
        tooltip: All rooms
        tap_action:
          action: call-service
          service: vacuum.start
          service_data:
            entity_id: vacuum.your_neatsvor_smart_vacuum
      - type: menu
        menu_id: rooms
        tooltip: Select room
        icon: mdi:floor-plan
        entity: select.your_neatsvor_room_select
        available_values_attribute: options
        icon_mapping:
          Коридор: mdi:wardrobe
          Hallway: mdi:wardrobe
          Гостиная: mdi:sofa
          Living room: mdi:sofa
          Детская: mdi:bed
          Childish: mdi:bed
          Кухня: mdi:fridge
          Kitchen: mdi:fridge
          Спальня: mdi:bed
          Bedroom: mdi:bed
          Ванная: mdi:shower
          Bathroom: mdi:shower
          Туалет: mdi:toilet
          Toilet: mdi:toilet
          Кабинет: mdi:desk
          Office: mdi:desk
        tap_action:
          action: call-service
          service: neatsvor.clean_room_with_preset
          service_data:
            entity_id: vacuum.your_neatsvor_smart_vacuum
            room: "[[value]]"
            use_preset: true
    tiles:
      - entity: sensor.your_neatsvor
        name: Map Status
        icon: mdi:map
        template: >
          {% set rooms = state_attr('select.your_neatsvor_room_select', 'options') %} {%
          if rooms %}
            🗺️ {{ rooms | length }} rooms
          {% else %}
            No map data
          {% endif %}
      - entity: select.your_neatsvor_room_select
        name: Selected Room
        icon: mdi:floor-plan
  - preset_name: ☁️ Cloud maps
    entity: vacuum.your_neatsvor_smart_vacuum
    map_source:
      camera: camera.your_neatsvor_cloud_map
    calibration_source:
      identity: true
    icons:
      - icon: mdi:refresh
        label: Refresh Maps
        tooltip: Refresh Maps
        tap_action:
          action: call-service
          service: button.press
          service_data:
            entity_id: button.your_neatsvor_refresh_cloud_maps
      - type: menu
        menu_id: cloud_maps
        tooltip: Select cloud map
        icon: mdi:map-search
        entity: select.your_neatsvor_cloud_map_select
        available_values_attribute: options
        tap_action:
          action: call-service
          service: select.select_option
          service_data:
            entity_id: select.your_neatsvor_cloud_map_select
            option: "[[value]]"
      - icon: mdi:star-circle
        label: Set as Reference
        tooltip: Set selected map as reference
        tap_action:
          action: call-service
          service: button.press
          service_data:
            entity_id: button.your_neatsvor_set_reference_map
          confirmation:
            text: Set this map as reference for auto-restore?
      - icon: mdi:map-check
        label: Use Map
        tooltip: Use selected cloud map as current map
        tap_action:
          action: call-service
          service: neatsvor.use_selected_cloud_map
          service_data:
            entity_id: vacuum.your_neatsvor_smart_vacuum
          confirmation:
            text: Make selected map the current map?
      - type: toggle
        menu_id: auto_restore
        tooltip: Auto-restore reference map
        icon: mdi:autorenew
        entity: switch.your_neatsvor_auto_restore_reference_map
        tap_action:
          action: call-service
          service: switch.toggle
          service_data:
            entity_id: switch.your_neatsvor_auto_restore_reference_map
    tiles:
      - entity: sensor.your_neatsvor_cloud_maps
        name: Total Maps
        icon: mdi:cloud
        show_name: true
        template: |
          {{ states('sensor.your_neatsvor_cloud_maps') }} maps total
      - entity: select.your_neatsvor_cloud_map_select
        name: Map select
        icon: mdi:map-check
        show_name: true
      - entity: switch.your_neatsvor_auto_restore_reference_map
        name: Auto-restore
        icon: mdi:autorenew
        show_name: true
      - entity: sensor.your_neatsvor_cloud_maps
        name: Reference Map
        icon: mdi:star-circle
        show_name: true
        template: >
          {% set attrs = state_attr('sensor.your_neatsvor_cloud_maps', 'reference') %} {%
          if attrs %}
            {% set map = state_attr('sensor.your_neatsvor_cloud_maps', 'maps') | selectattr('id', 'equalto', attrs) | list %}
            {% if map %}
              {{ map[0].name }}
            {% else %}
              ID: {{ attrs }}
            {% endif %}
          {% else %}
            None set
          {% endif %}
  - preset_name: 📥 Cleaning history
    entity: vacuum.your_neatsvor_smart_vacuum
    map_source:
      camera: camera.your_neatsvor_clean_history_map
    calibration_source:
      identity: true
    icons:
      - icon: mdi:refresh
        label: Refresh History
        tooltip: Refresh History
        tap_action:
          action: call-service
          service: button.press
          service_data:
            entity_id: button.neatsvor_refresh_clean_history
      - type: menu
        menu_id: clean_history
        tooltip: Select history record
        icon: mdi:history
        entity: select.your_neatsvor_clean_history_select
        available_values_attribute: options
        tap_action:
          action: call-service
          service: select.select_option
          service_data:
            entity_id: select.your_neatsvor_clean_history_select
            option: "[[value]]"
    tiles:
      - entity: select.your_neatsvor_clean_history_select
        name: History Record
        icon: mdi:history
        show_name: true
      - entity: sensor.your_neatsvor_last_clean
        name: Last Clean
      - entity: sensor.your_neatsvor_last_clean_duration
        name: Duration
        unit: min
      - entity: sensor.your_neatsvor_last_clean_area
        name: Area
        unit: m²
      - entity: sensor.your_neatsvor_total_cleanings
        name: Total Cleanings
      - entity: sensor.your_neatsvor_total_clean_time
        name: Total Time
        unit: h
      - entity: sensor.your_neatsvor_total_clean_area
        name: Total Area
        unit: m²
  - preset_name: ℹ️ Information
    entity: vacuum.your_neatsvor_smart_vacuum
    map_source:
      camera: camera.your_neatsvor_live_map
    calibration_source:
      identity: true
    icons: []
    tiles:
      - entity: sensor.your_neatsvor_hepa_filter
        name: HEPA Filter
        unit: "%"
      - entity: sensor.your_neatsvor_main_brush
        name: Main Brush
        unit: "%"
        icon: mdi:brush-variant
      - entity: sensor.your_neatsvor_side_brush
        name: Side Brush
        unit: "%"
      - entity: binary_sensor.your_neatsvor_online
        name: Online
        icon: mdi:satellite-uplink
      - entity: binary_sensor.your_neatsvor_charging
        name: Charging
      - entity: binary_sensor.your_neatsvor_dust_bin
        name: Dust Bin
      - entity: binary_sensor.your_neatsvor_mop_attached
        name: Mop Attached
      - entity: sensor.your_neatsvor_software_version
        name: Software Version
      - entity: sensor.your_neatsvor_mac_address
        name: MAC Address
      - entity: sensor.your_neatsvor_device_pid
        name: Device PID
grid_options:
  columns: full
```
  </details>

## Additional configuration
The Neatsvor platform supports tiles for maintenance status, cleaning statistics, and menu icons for fan speed, water level, and cleaning mode. These will appear automatically if the corresponding sensors are available.

For more information about the integration, visit the [Neatsvor integration](https://github.com/CoderAS-ru/hass-neatsvor) repository.