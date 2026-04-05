[![GitHub Release][releases-shield]][releases]
[![GitHub License][license-shield]][license]
[![hacs][hacs-badge]][hacs-url]

# Neatsvor Integration for Home Assistant

Интеграция для управления пылесосами Neatsvor (и другими под брендом Black Vision) в Home Assistant.

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

1. Перейдите в **Настройки → Устройства и сервисы → Добавить интеграцию**
2. Найдите "Neatsvor"
3. Введите email и пароль от аккаунта в приложении
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
