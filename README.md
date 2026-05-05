# Neatsvor Integration for Home Assistant

[![EN](https://img.shields.io/badge/English-blue)](README.md)
[![RU](https://img.shields.io/badge/Русский-red)](README_ru.md)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![GitHub Release](https://img.shields.io/github/v/release/CoderAS-ru/hass-neatsvor)](https://github.com/CoderAS-ru/hass-neatsvor/releases/latest)
[![GitHub Downloads](https://img.shields.io/github/downloads/CoderAS-ru/hass-neatsvor/total)](https://github.com/CoderAS-ru/hass-neatsvor/releases)
[![License](https://img.shields.io/github/license/CoderAS-ru/hass-neatsvor)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/CoderAS-ru/hass-neatsvor?style=popout&logo=github&logoColor=white)](https://github.com/CoderAS-ru/hass-neatsvor/stargazers)
[![GitHub last commit](https://img.shields.io/github/last-commit/CoderAS-ru/hass-neatsvor?style=popout&logo=github&logoColor=white)](https://github.com/CoderAS-ru/hass-neatsvor/commits/main)

Control your Neatsvor robot vacuum (and other [BlackVision](https://www.blackvision.net/)-based devices using [Libos Home](https://play.google.com/store/apps/details?id=com.blackvision.libos2), [Neatsvor Home](https://play.google.com/store/apps/details?id=com.haibaina.neatsvor), [Joy Life](https://play.google.com/store/apps/details?id=com.blackvision.joylife) apps) in Home Assistant.

<pre>
<img height="400" alt="image 1" src="https://github.com/user-attachments/assets/6419f86e-c2d4-4ad0-9c87-4f2353e58050" /> <img height="400" alt="image 2" src="https://github.com/user-attachments/assets/9ac0f6e0-51f0-4c3e-8b10-6ff4e5e7264c" /> <img height="400" alt="image 3" src="https://github.com/user-attachments/assets/074ffd55-1ffa-4e4f-979d-6359d8c845ec" /> <img height="400" alt="image 4" src="https://github.com/user-attachments/assets/512a0f42-579d-4dc6-a25d-46958b33481d" /> <img height="400" alt="image 5" src="https://github.com/user-attachments/assets/1b3a7ea5-862f-4392-ac62-f80aa16cabd2" />
</pre>

## Features

- 🎮 **Full Control:** Start, pause, stop cleaning, return to dock
- 🗺️ **Live Map:** Display the room map with the robot's real-time position
- 📍 **Zone Cleaning:** Select a zone on the map for cleaning (requires [lovelace-xiaomi-vacuum-map-card](https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card))
- 🧹 **Room Cleaning:** Ability to clean individual rooms by name
- 💧 **Water Level Adjustment** (for mopping models)
- 💨 **Suction Power Adjustment**
- 📊 **Sensors:** Status, battery charge, cleaning time/area
- 🔄 **Consumables:** Display the wear level of the filter and brushes
- 📸 **Cleaning History:** Save and view maps from previous cleanings
- ☁️ **Cloud Maps:** Download and use maps saved in the cloud
- 🌐 **Localization:** Support for Russian and English

### Smart Home with Alice (Yandex)

- 📱 **Voice Control:** Manage and monitor from the "Smart Home with Alice" app (requires [yandex_smart_home](https://github.com/dext0r/yandex_smart_home))
- 🔋 **Battery Status:** Display battery level in the Alice Smart Home app
- 📊 **Sensors in the App:** Access digital sensor values within the Alice Smart Home app

## Installation

### Via HACS (Recommended)

- Add this repository to HACS as a custom repository
- Install the Neatsvor integration
- Restart Home Assistant

### Manual Installation

- Copy the `custom_components/neatsvor` folder to your `config/custom_components/`
- Restart Home Assistant

## Configuration

### Adding the Integration via UI

- Go to **Settings → Devices & Services**
- Click **"+ Add Integration"**
- Find and select "Neatsvor"
- Choose the app where your vacuum is registered:
    - **Libos Home** — for BlackVision devices (default)
    - **Neatsvor Home** — for official Neatsvor vacuums
    - **Joy Life** — for devices controlled via JoyLife
- Enter the **phone code** (country/region) for your account (you can use formats like "+7" or "7")
- Enter your **email** and **password** for the selected app
- Complete the setup

### Account Requirements

- Create an account in the chosen app and pair your device if you haven't already
- Important rule: **One account - one connection**
- For control from multiple devices, use the **"Share Device"** function in the app

### Switching Between Apps

If you have devices in different apps:

- Go to **Settings → Devices & Services → Neatsvor → Configure**
- Change the **"App"** parameter
- The integration will automatically reload with the new settings

> **Note:** Using multiple apps simultaneously requires creating separate integration instances.

## Usage

### Zone Cleaning

To use zone cleaning, you need to install `lovelace-xiaomi-vacuum-map-card`:
```yaml
type: custom:xiaomi-vacuum-map-card
entity: vacuum.neatsvor_vacuum
map_source:
  camera: camera.neatsvor_live_map
calibration_source:
  identity: true
zones:
  service: neatsvor.zone_clean
  service_data:
    entity_id: vacuum.neatsvor_vacuum
    zones: "[[x1, y1, x2, y2, 1]]"
```

### Voice Cleaning of Individual Rooms
1. Go to **Settings → Automations & Scenes → Scripts**
2. Click **"Create Script" → "Create new script" → "Add Action"**
3. In the search field, type **'neatsvor'**
4. Select the action **'Neatsvor: Clean room with preset'**
5. Specify:
   - **Targets → Add target**: Select your robot vacuum
   - **Room name: The exact name of the room (case-sensitive!)**
   - **Toggle 'Use Preset' should be ON!** (This uses your saved settings for that room)
6. Click **'Save'**
7. Enter a name for the script (e.g., Clean Kitchen)
8. Optionally, add a description, area, and icon.

In YAML mode:
```yaml
sequence:
  - action: neatsvor.clean_room_with_preset
    metadata: {}
    data:
      use_preset: true
      room: Kitchen
    target:
      entity_id: vacuum.s700_smart_vacuum
alias: Clean Kitchen
description: Start cleaning the kitchen
```

After creating the script, you need to expose it to Yandex Smart Home via the yandex_smart_home integration configuration.
After this, you can use voice commands in the "Smart Home with Alice" app:
  - _"Alice, turn on the kitchen cleaning"_
  - _"Alice, turn off the living room cleaning"_

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

## Supported Devices
### Neatsvor
  - [S700](https://neatsvor.ru/product/productDetail?spuId=28)

### BlackVision
  - Other BlackVision platform devices

### JoyLife
  - Devices managed via JoyLife

## Troubleshooting
### Authentication Error
- Check your email and password
- Ensure the correct phone code is selected
- Verify the correct app is chosen

### Map Not Displayed
- Make sure the robot has completed at least one cleaning
- Check the MQTT connection in the logs
- Try calling the neatsvor.request_map service

### Zone Cleaning Doesn't Work
- Ensure xiaomi-vacuum-map-card is installed
- Check that the map is displayed correctly
- Make sure the robot is not on the dock

### MQTT Issues
- Ensure outgoing connections to port 8011 are allowed in your network
- Check that a firewall isn't blocking connections to the BlackVision MQTT servers

### Logs
Logs can be viewed at **Settings → System → Logs** → select custom_components.neatsvor.

## Known Limitations
- Zone cleaning requires a map with origin (0,0) — works on most devices
- Map editing (splitting/merging rooms) is not implemented
- Using multiple apps simultaneously requires separate integration instances

## Contributing
If you find a bug or want to suggest an improvement:
1. Create an Issue on GitHub
2. Submit a Pull Request with your changes

## Technical Details
### How the Integration Works
This integration uses **reverse-engineering** of the official mobile app to fully understand the data exchange protocol with the devices.

**Key implementation features:**

- 🔍 **Dynamic DP Schema**: The integration retrieves the current Data Point schema for your specific vacuum model directly from the cloud.
- 📡 **Native MQTT Protocol**: Direct interaction with the device via the MQTT broker, just like the official app.
- 🗺️ **Full Map Support**: Decoding of the proprietary map format.
- 🔄 **Up-to-Date**: When new models or functions are added to the app, the integration automatically supports them (if they use existing DPs).

### Why This Matters
By retrieving the DP schema from the cloud, the integration:
- Supports all vacuum models without needing an update for each one
- Automatically obtains new device capabilities
- Correctly displays all sensors and settings for your specific model

### Legal Information

This integration was created for educational purposes and for the Home Assistant community. The developer is not affiliated with BlackVision or Neatsvor. All trademarks are the property of their respective owners.

> **Note**: This integration does not modify device firmware, bypass security systems, or violate the terms of use of the official applications.

## License
MIT License - free use, modification, and distribution.
