[![HACS Default](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/CoderAS-ru/hass-neatsvor)](https://github.com/CoderAS-ru/hass-neatsvor/releases/latest)
[![GitHub Downloads](https://img.shields.io/github/downloads/CoderAS-ru/hass-neatsvor/total)](https://github.com/CoderAS-ru/hass-neatsvor/releases)
[![License](https://img.shields.io/github/license/CoderAS-ru/hass-neatsvor)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/CoderAS-ru/hass-neatsvor?style=popout&logo=github&logoColor=white)](https://github.com/CoderAS-ru/hass-neatsvor/stargazers)
[![GitHub last commit](https://img.shields.io/github/last-commit/CoderAS-ru/hass-neatsvor?style=popout&logo=github&logoColor=white)](https://github.com/CoderAS-ru/hass-neatsvor/commits/main)

# Neatsvor Integration for Home Assistant

Интеграция для управления пылесосами Neatsvor (и другими, на платформе [BlackVision](https://www.blackvision.net/), управляемыми посредством приложения [LibosHome](https://play.google.com/store/apps/details?id=com.blackvision.libos2)) в Home Assistant.

<pre>
<img height="400" alt="image 1" src="https://github.com/user-attachments/assets/6419f86e-c2d4-4ad0-9c87-4f2353e58050" /> <img height="400" alt="image 2" src="https://github.com/user-attachments/assets/9ac0f6e0-51f0-4c3e-8b10-6ff4e5e7264c" /> <img height="400" alt="image 3" src="https://github.com/user-attachments/assets/074ffd55-1ffa-4e4f-979d-6359d8c845ec" /> <img height="400" alt="image 4" src="https://github.com/user-attachments/assets/512a0f42-579d-4dc6-a25d-46958b33481d" /> <img height="400" alt="image 5" src="https://github.com/user-attachments/assets/1b3a7ea5-862f-4392-ac62-f80aa16cabd2" />
</pre>

## Возможности

- 🎮 **Полное управление**: запуск/пауза/остановка уборки, возврат на базу
- 🗺️ **Живая карта**: отображение карты помещения с позицией робота
- 📍 **Зональная уборка**: выбор зоны на карте для уборки (требуется [lovelace-xiaomi-vacuum-map-card](https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card))
- 🧹 **Уборка комнат**: возможность уборки отдельных комнат
- 💧 **Регулировка подачи воды** (для моделей с режимом влажной уборки)
- 💨 **Регулировка мощности всасывания**
- 📊 **Датчики**: статус, заряд батареи, время/площадь уборки
- 🔄 **Расходники**: отображение износа фильтра и щеток
- 📸 **История уборок**: сохранение карт предыдущих уборок
- ☁️ **Облачные карты**: загрузка и использование сохраненных карт
- 🌐 **Локализация**: поддержка русского и английского языков

### Умный дом с Алисой
- 📱 **Голосовое управление**: управление м контроль из приложения Умный дом с Алисой (требуется [yandex_smart_home](https://github.com/dext0r/yandex_smart_home))
- 🔋 **Заряд батареи**: отображение уровня заряда в приложении Дом с Алисой
- 📊 **Датчики в приложении**: Возможность получения значений цифровых датчиков в приложении Умный дом с Алисой


## Установка

### Через HACS (рекомендуется)

1. Добавьте этот репозиторий в HACS как пользовательский репозиторий
2. Установите интеграцию Neatsvor
3. Перезапустите Home Assistant

### Ручная установка

1. Скопируйте папку `custom_components/neatsvor` в `config/custom_components/`
2. Перезапустите Home Assistant

## Настройка

Устройство (робот) должно быть подключено именно к приложению LibosHome!
1. Перейдите в **Настройки → Устройства и сервисы → Добавить интеграцию**
2. Найдите "Neatsvor"
3. Введите email и пароль от аккаунта в приложении LibosHome
4. Выберите страну/регион (RU, CN, DE)
5. После успешного входа выберите устройство

## Зональная уборка

Для использования зональной уборки необходимо установить [lovelace-xiaomi-vacuum-map-card](https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card):

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

## Поддерживаемые устройства
### Neatsvor 
  - [S700](https://neatsvor.ru/product/productDetail?spuId=28)

Другие устройства платформы BlackVision/Neatsvor (тестируются)

## Известные ограничения
<b>Устройство должно быть зарегистрированно и подключено именно в приложении LibosHome!</b>

Интеграция не поддерживает устройства, подключенные к приложениям Neatsvor или JoyLife!

Зональная уборка требует карты с origin (0,0) - работает на большинстве устройств.

Редактирование карты (разделение/объединение комнат) не реализовано.

## Лицензия
MIT
