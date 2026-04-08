[![HACS Default][hacs_shield]][hacs]
[![GitHub Latest Release][releases_shield]][latest_release]
[![GitHub All Releases][downloads_total_shield]][releases]
[![GitHub Views][views_shield]][repo]
[![GitHub Visitors][visitors_shield]][repo]

[hacs_shield]: https://img.shields.io/static/v1.svg?label=HACS&message=Default&style=popout&color=green&labelColor=41bdf5&logo=HomeAssistantCommunityStore&logoColor=white
[hacs]: https://hacs.xyz/docs/default_repositories

[releases_shield]: https://img.shields.io/github/release/CoderAS-ru/hass-neatsvor.svg?style=popout
[latest_release]: https://github.com/CoderAS-ru/hass-neatsvor/releases/latest

[downloads_total_shield]: https://img.shields.io/github/downloads/CoderAS-ru/hass-neatsvor/total

[views_shield]: https://img.shields.io/github/search/CoderAS-ru/hass-neatsvor/views?style=popout&label=Views&color=blue
[visitors_shield]: https://img.shields.io/github/search/CoderAS-ru/hass-neatsvor/visitors?style=popout&label=Visitors&color=blue
[repo]: https://github.com/CoderAS-ru/hass-neatsvor


# Neatsvor Integration for Home Assistant

Интеграция для управления пылесосами Neatsvor (и другими под брендом Black Vision) в Home Assistant.

<img width="498" height="987" alt="image" src="https://github.com/user-attachments/assets/6419f86e-c2d4-4ad0-9c87-4f2353e58050" />
<img width="502" height="987" alt="image" src="https://github.com/user-attachments/assets/9ac0f6e0-51f0-4c3e-8b10-6ff4e5e7264c" />
<img width="498" height="1006" alt="image" src="https://github.com/user-attachments/assets/074ffd55-1ffa-4e4f-979d-6359d8c845ec" />
<img width="497" height="1080" alt="image" src="https://github.com/user-attachments/assets/512a0f42-579d-4dc6-a25d-46958b33481d" />
<img width="505" height="1032" alt="image" src="https://github.com/user-attachments/assets/1b3a7ea5-862f-4392-ac62-f80aa16cabd2" />





## Возможности

- 🎮 **Полное управление**: запуск/пауза/остановка уборки, возврат на базу
- 🗺️ **Живая карта**: отображение карты помещения с позицией робота
- 📍 **Зональная уборка**: выбор зоны на карте для уборки (требуется `xiaomi-vacuum-map-card`)
- 🧹 **Уборка комнат**: возможность уборки отдельных комнат
- 💧 **Регулировка подачи воды** (для моделей с режимом влажной уборки)
- 💨 **Регулировка мощности всасывания**
- 📊 **Датчики**: статус, заряд батареи, время/площадь уборки
- 🔄 **Расходники**: отображение износа фильтра и щеток
- 📸 **История уборок**: сохранение карт предыдущих уборок
- ☁️ **Облачные карты**: загрузка и использование сохраненных карт
- 🌐 **Локализация**: поддержка русского и английского языков

## Установка

### Через HACS (рекомендуется)

1. Добавьте репозиторий в HACS как пользовательский репозиторий
2. Установите интеграцию Neatsvor
3. Перезапустите Home Assistant

### Ручная установка

1. Скопируйте папку `custom_components/neatsvor` в `config/custom_components/`
2. Перезапустите Home Assistant

## Настройка

Устройство (робот) должно быть подключено к приложению LibosHome!
1. Перейдите в **Настройки → Устройства и сервисы → Добавить интеграцию**
2. Найдите "Neatsvor"
3. Введите email и пароль от аккаунта в приложении LibosHome
4. Выберите страну/регион (RU, CN, DE)
5. После успешного входа выберите устройство

## Зональная уборка

Для использования зональной уборки необходимо установить [xiaomi-vacuum-map-card](https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card):

```yaml
type: custom:xiaomi-vacuum-map-card
entity: vacuum.neatsvor_vacuum
map_source:
  camera: camera.neatsvor_live_map
calibration_source:
  identity: true  # или используйте калибровку
zones:
  service: neatsvor.zone_clean
  service_data:
    entity_id: vacuum.neatsvor_vacuum
    zones: "[[x1, y1, x2, y2, 1]]"
```

## Сервисы
|Сервис	                        |Описание                            | 
|-------------------------------|------------------------------------|
|neatsvor.zone_clean	          | Зональная уборка                   |
|neatsvor.room_clean	          | Уборка комнаты                     |
|neatsvor.save_reference_map	  | Сохранить текущую карту как эталон |
|neatsvor.restore_reference_map	| Восстановить карту из эталона      |
|neatsvor.save_map_to_cloud	    | Сохранить карту в облако           |

Поддерживаемые устройства
Neatsvor S700

Другие устройства платформы Black Vision/Neatsvor (тестируются)

Известные ограничения
Зональная уборка требует карты с origin (0,0) - работает на большинстве устройств

Редактирование карты (разделение/объединение комнат) не реализовано

## Лицензия
MIT

[releases-shield]: https://img.shields.io/github/v/release/YOUR_USERNAME/hass-neatsvor
[releases]: https://github.com/YOUR_USERNAME/hass-neatsvor/releases
[license-shield]: https://img.shields.io/github/license/YOUR_USERNAME/hass-neatsvor
[license]: https://github.com/YOUR_USERNAME/hass-neatsvor/blob/main/LICENSE
[hacs-badge]: https://img.shields.io/badge/HACS-Default-orange.svg
[hacs-url]: https://github.com/hacs/integration
