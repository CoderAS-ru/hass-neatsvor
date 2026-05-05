# Neatsvor Integration for Home Assistant

[![EN](https://img.shields.io/badge/English-blue)](README.md)
[![RU](https://img.shields.io/badge/Русский-red)](README_ru.md)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![GitHub Release](https://img.shields.io/github/v/release/CoderAS-ru/hass-neatsvor)](https://github.com/CoderAS-ru/hass-neatsvor/releases/latest)
[![GitHub Downloads](https://img.shields.io/github/downloads/CoderAS-ru/hass-neatsvor/total)](https://github.com/CoderAS-ru/hass-neatsvor/releases)
[![License](https://img.shields.io/github/license/CoderAS-ru/hass-neatsvor)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/CoderAS-ru/hass-neatsvor?style=popout&logo=github&logoColor=white)](https://github.com/CoderAS-ru/hass-neatsvor/stargazers)
[![GitHub last commit](https://img.shields.io/github/last-commit/CoderAS-ru/hass-neatsvor?style=popout&logo=github&logoColor=white)](https://github.com/CoderAS-ru/hass-neatsvor/commits/main)

Интеграция для управления пылесосами Neatsvor (и другими на платформе [BlackVision](https://www.blackvision.net/), управляемыми посредством приложений [Libos Home](https://play.google.com/store/apps/details?id=com.blackvision.libos2), [Neatsvor Home](https://play.google.com/store/apps/details?id=com.haibaina.neatsvor), [Joy Life](https://play.google.com/store/apps/details?id=com.blackvision.joylife)) в Home Assistant.

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
- 📱 **Голосовое управление**: управление и контроль из приложения Умный дом с Алисой (требуется [yandex_smart_home](https://github.com/dext0r/yandex_smart_home))
- 🔋 **Заряд батареи**: отображение уровня заряда в приложении Дом с Алисой
- 📊 **Датчики в приложении**: возможность получения значений цифровых датчиков в приложении Умный дом с Алисой

## Установка

### Через HACS (рекомендуется)

1. Добавьте этот репозиторий в HACS как пользовательский репозиторий
2. Установите интеграцию Neatsvor
3. Перезапустите Home Assistant

### Ручная установка

1. Скопируйте папку `custom_components/neatsvor` в `config/custom_components/`
2. Перезапустите Home Assistant

## Настройка

### Добавление интеграции через UI

1. Перейдите в **Настройки → Устройства и сервисы**
2. Нажмите **"+ Добавить интеграцию"**
3. Найдите в списке **"Neatsvor"**
4. Выберите **приложение**, в котором зарегистрирован пылесос:
   - **Libos Home** — для устройств BlackVision (по умолчанию)
   - **Neatsvor Home** — для официальных пылесосов Neatsvor
   - **Joy Life** — для устройств, управляемых через JoyLife
5. Введите телефонный код **страны/региона** указанный для учетной записи в приложении (возможно указание как в формате "+7", так и "7")
6. Введите **email и пароль** от аккаунта в выбранном приложении
7. Завершите установку

### Требования к аккаунту

- При необходимости, создайте аккаунт в выбранном приложении и выполните привязку устройства
- **Важное правило**: "один аккаунт - одно подключение"
- Для управления с нескольких устройств используйте функцию "Поделиться устройством" в приложении

### Переключение между приложениями

Если у вас есть устройства в разных приложениях, вы можете:

1. Перейти в **Настройки → Устройства и сервисы → Neatsvor → Настроить**
2. Изменить параметр **"Приложение"** на нужное
3. Интеграция автоматически перезагрузится с новыми настройками

> **Примечание**: Для использования нескольких приложений одновременно потребуется создать отдельные экземпляры интеграции.

## Использование

### Зональная уборка

Для использования зональной уборки необходимо установить [lovelace-xiaomi-vacuum-map-card](https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card):

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

### Голосовая уборка отдельных комнат

1. Перейдите в **Настройки → Автоматизации и сцены → Скрипты**
2. Нажмите **"Создать скрипт" → "Создать новый скрипт" → "Добавить действие"**
3. В поле поиска введите **'neatsvor'**
4. Выберите действие **'Neatsvor: Убрать комнату с пресетом'**
5. Укажите:
   - **Цели → Добавить цель**: Выберите свой робот-пылесос
   - В поле **Room name**: Укажите название комнаты

   **💡 Важно**: Название комнаты должно **точно совпадать с названием комнаты на карте робота (регистр важен!)**.

   - Выключатель **'Use Preset' должен быть включен!**
6. Нажмите 'Сохранить'.
7. Укажите название скрипта:
   - **Имя**: `Уборка кухни`
8. По желанию, добавьте описание, пространство, ярлык:
   - **Описание**: `Запустить уборку на кухне`

Или в режиме YAML:
```yaml
sequence:
  - action: neatsvor.clean_room_with_preset
    metadata: {}
    data:
      use_preset: true
      room: Кухня
    target:
      entity_id: vacuum.s700_smart_vacuum
alias: Уборка кухни
description: Запустить уборку на кухне
```
После создания сценария, его необходимо экспортировать в Умный дом Яндекса. Через интерфейс интеграции [yandex_smart_home](https://github.com/dext0r/yandex_smart_home) или в YAML:
```yaml
yandex_smart_home:
  filter:
    include_entities:
      - script.uborka_kuhni
      - script.uborka_gostinoy # Скрипт создать аналогично примеру
      - script.uborka_spalni   # Скрипт создать аналогично примеру
```
После этого в приложении "Дом с Алисой" появятся устройства/скрипты, которыми можно управлять голосом:

   - _«Алиса, включи уборку на кухне»_
   - _«Алиса, выключи уборку в гостиной»_

При привязке скриптов к пространствам, они автоматически добавятся в пространства Умного дома Яндекса

ℹ️ Команда «выключи» так же будет работать — скрипт просто выполнится, так как у него нет состояния «вкл/выкл».

## Сервисы

| Сервис | Описание |
|--------|----------|
| `neatsvor.zone_clean` | Зональная уборка |
| `neatsvor.clean_room_with_preset` | Уборка комнаты с использованием предварительных настроек |
| `neatsvor.save_reference_map` | Сохранить текущую карту как эталон |
| `neatsvor.restore_reference_map` | Восстановить карту из эталона |
| `neatsvor.save_map_to_cloud` | Сохранить карту в облако |
| `neatsvor.request_all_data` | Запросить все данные (как официальное приложение) |
| `neatsvor.build_map` | Быстрое построение карты без уборки |
| `neatsvor.empty_dust` | Принудительная очистка контейнера пыли |

## Поддерживаемые устройства
### Neatsvor 
  - [S700](https://neatsvor.ru/product/productDetail?spuId=28)

### BlackVision
  - Другие устройства платформы BlackVision (тестируются)

### JoyLife
  - Устройства под управлением JoyLife (тестируются)

## Устранение неполадок

### Ошибка аутентификации
- Проверьте правильность email и пароля
- Убедитесь, что выбран правильный регион (RU/CN/DE)
- Проверьте, что выбрано правильное приложение

### Не отображается карта
- Убедитесь, что робот завершил хотя бы одну уборку
- Проверьте подключение к MQTT в логах
- Попробуйте вызвать сервис `neatsvor.request_map`

### Зональная уборка не работает
- Убедитесь, что установлена xiaomi-vacuum-map-card
- Проверьте, что карта отображается корректно
- Убедитесь, что робот не на базе

### Проблемы с MQTT
- Проверьте, что в вашей сети разрешены исходящие соединения на порт 8011
- Убедитесь, что брандмауэр не блокирует подключения к MQTT-серверам BlackVision

### Логи
Логи можно посмотреть в **Настройки → Система → Логи** → выбрать `custom_components.neatsvor`

## Известные ограничения
- Зональная уборка требует карты с origin (0,0) - работает на большинстве устройств
- Редактирование карты (разделение/объединение комнат) не реализовано
- Одновременное использование нескольких приложений требует отдельных экземпляров интеграции

## Вклад в развитие
Если вы нашли ошибку или хотите предложить улучшение:
1. Создайте [Issue](https://github.com/CoderAS-ru/hass-neatsvor/issues) на GitHub
2. Отправьте Pull Request с вашими изменениями

## Благодарности
- [Piotr Machowski (PiotrMachowski)](https://github.com/PiotrMachowski) за [xiaomi-vacuum-map-card](https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card)
- [Artem Sorokin (dext0r)](https://github.com/dext0r) за [yandex_smart_home](https://github.com/dext0r/yandex_smart_home)
- Всем тестировщикам и пользователям интеграции

## Технические детали

### Как работает интеграция

Интеграция использует **реверс-инжиниринг** официального мобильного приложения для полного понимания протокола обмена данными с устройствами.

**Ключевые особенности реализации:**

- 🔍 **Динамическая DP-схема** - интеграция получает актуальную Data Point схему для конкретной модели пылесоса непосредственно из облака
- 📡 **Нативный MQTT-протокол** - прямое взаимодействие с устройством через MQTT брокер, аналогично официальному приложению
- 🗺️ **Полная поддержка карт** - декодирование проприетарного формата карт
- 🔄 **Актуальность** - при добавлении новых моделей или функций в приложении, интеграция автоматически их поддерживает (если они используют существующие DP)

### Почему это важно

Благодаря получению DP-схемы из облака, интеграция:
- Поддерживает все модели пылесосов без необходимости обновления
- Автоматически получает новые возможности устройств
- Корректно отображает все датчики и настройки именно используемой модели

### Юридическая информация

Интеграция создана в образовательных целях и для сообщества Home Assistant. Разработчик не связан с компаниями BlackVision или Neatsvor. Все товарные знаки принадлежат их законным владельцам.

**Примечание**: Интеграция не модифицирует прошивку устройств, не обходит системы защиты и не нарушает условия использования официальных приложений.

## Лицензия
MIT License - свободное использование, модификация и распространение

