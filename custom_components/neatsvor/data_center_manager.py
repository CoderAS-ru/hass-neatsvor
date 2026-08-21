"""Data center manager for Neatsvor integration using country databases."""

import logging
import sqlite3
import os
from typing import Optional, Dict, Any

_LOGGER = logging.getLogger(__name__)


class DataCenterManager:
    """Manager for finding data centers by phone code using country2.db."""

    def __init__(self, hass):
        """Initialize the manager."""
        self.hass = hass
        # Путь к папке с БД в custom_components/neatsvor/db/
        self.db_path = os.path.join(
            hass.config.path("custom_components/neatsvor"), "db"
        )
        _LOGGER.debug("DataCenterManager db_path: %s", self.db_path)
        
    def get_data_center_by_phone_code(self, phone_code: str, language: str = "en") -> Optional[Dict[str, Any]]:
        """
        Get data center configuration by phone code.
        
        Returns dict with:
            - rest_url: REST API URL (base_url from data_center table)
            - mqtt_host: MQTT host
            - mqtt_port: MQTT port (8011)
            - country_code: Country code (cn, de, ru, us, sg)
            - country_name: Localized country name
        """
        # Основной поиск в country2.db
        result = self._get_from_country2_db(phone_code, language)
        if result:
            return result
            
        # Резервный поиск в country.db (только для прямых кодов)
        result = self._get_from_country_db(phone_code, language)
        if result:
            return result
            
        # Резервное отображение
        return self._fallback_by_phone_code(phone_code, language)
    
    def _get_from_country2_db(self, phone_code: str, language: str) -> Optional[Dict[str, Any]]:
        """Query country2.db for data center by phone code."""
        db_file = os.path.join(self.db_path, "country2.db")
        if not os.path.exists(db_file):
            _LOGGER.warning("country2.db not found at %s", db_file)
            return None
            
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            # 1. Находим регион по телефонному коду
            cursor.execute("""
                SELECT id, code, name, phone_code, data_center_id
                FROM region
                WHERE phone_code = ?
                LIMIT 1
            """, (phone_code,))
            
            region_row = cursor.fetchone()
            if not region_row:
                _LOGGER.debug("No region found for phone_code %s", phone_code)
                conn.close()
                return None
                
            region_id, region_code, region_name, region_phone, data_center_id = region_row
            
            # 2. Находим дата-центр
            cursor.execute("""
                SELECT id, code, name, base_url
                FROM data_center
                WHERE id = ?
            """, (data_center_id,))
            
            dc_row = cursor.fetchone()
            if not dc_row:
                _LOGGER.warning("No data center found for id %s", data_center_id)
                conn.close()
                return None
                
            dc_id, dc_code, dc_name, base_url = dc_row
            
            # 3. Получаем MQTT конфигурацию
            mqtt_config = self._get_mqtt_config(dc_code, data_center_id)
            
            # 4. Получаем локализованное имя страны
            country_name_localized = region_name
            try:
                # Пробуем разные варианты языковых таблиц
                lang_variants = [language, language.split('-')[0] if '-' in language else language, "en"]
                for lang in lang_variants:
                    table_name = f"region_language_{lang}"
                    try:
                        cursor.execute(f"""
                            SELECT content
                            FROM {table_name}
                            WHERE region_id = ?
                            LIMIT 1
                        """, (region_id,))
                        lang_row = cursor.fetchone()
                        if lang_row and lang_row[0]:
                            country_name_localized = lang_row[0]
                            break
                    except:
                        continue
            except Exception as e:
                _LOGGER.debug("Could not get localized name: %s", e)
            
            conn.close()
            
            _LOGGER.info("Found data center: phone_code=%s -> %s (%s), rest=%s, mqtt=%s", 
                        phone_code, dc_code, country_name_localized, base_url, mqtt_config.get("mqtt_host"))
            
            return {
                "rest_url": base_url,
                "mqtt_host": mqtt_config.get("mqtt_host"),
                "mqtt_port": mqtt_config.get("mqtt_port", 8011),
                "country_code": dc_code,
                "country_name": country_name_localized,
                "phone_code": phone_code,
            }
            
        except Exception as e:
            _LOGGER.error("Error querying country2.db: %s", e)
            return None
    
    def _get_mqtt_config(self, country_code: str, data_center_id: int = None) -> Dict[str, Any]:
        """Get MQTT configuration by country code."""
        # Маппинг country_code на MQTT host
        mqtt_map = {
            "cn": {"mqtt_host": "cn.mqtt.blackvision.net", "mqtt_port": 8011},
            "de": {"mqtt_host": "de.mqtt.blackvision.net", "mqtt_port": 8011},
            "ru": {"mqtt_host": "ru.mqtt.blackvision.net", "mqtt_port": 8011},
            "us": {"mqtt_host": "us.mqtt.blackvision.net", "mqtt_port": 8011},
            "sg": {"mqtt_host": "sg.mqtt.blackvision.net", "mqtt_port": 8011},
        }
        
        # Пробуем получить из country.db (для CN/DE/RU)
        mqtt_from_db = self._get_mqtt_from_country_db(country_code)
        if mqtt_from_db:
            return mqtt_from_db
            
        # Используем маппинг
        if country_code in mqtt_map:
            return mqtt_map[country_code]
            
        # Дефолтный MQTT
        _LOGGER.warning("No MQTT config for country_code %s, using default", country_code)
        return {"mqtt_host": "ru.mqtt.blackvision.net", "mqtt_port": 8011}
    
    def _get_mqtt_from_country_db(self, country_code: str) -> Optional[Dict[str, Any]]:
        """Get MQTT configuration from country.db by country code."""
        db_file = os.path.join(self.db_path, "country.db")
        if not os.path.exists(db_file):
            return None
            
        # country.db имеет записи только для China, Germany, Russia
        code_to_name = {
            "cn": "China",
            "de": "Germany",
            "ru": "Russia",
        }
        
        name_en = code_to_name.get(country_code)
        if not name_en:
            return None
            
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT mqtt, port
                FROM country
                WHERE name_en = ? AND isTest = 0
                LIMIT 1
            """, (name_en,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                mqtt_host, mqtt_port = row
                return {"mqtt_host": mqtt_host, "mqtt_port": mqtt_port or 8011}
                
        except Exception as e:
            _LOGGER.error("Error getting MQTT from country.db: %s", e)
            
        return None
    
    def _get_from_country_db(self, phone_code: str, language: str) -> Optional[Dict[str, Any]]:
        """Query country.db as fallback for direct phone codes."""
        db_file = os.path.join(self.db_path, "country.db")
        if not os.path.exists(db_file):
            return None
        
        # Маппинг телефонных кодов на страны
        phone_to_country = {
            "7": "Russia",
            "86": "China",
            "49": "Germany",
        }
        
        if phone_code not in phone_to_country:
            return None
            
        country_name = phone_to_country[phone_code]
        
        country_to_code = {
            "Russia": "ru",
            "China": "cn",
            "Germany": "de",
        }
        
        country_code = country_to_code.get(country_name)
        if not country_code:
            return None
            
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT name_en, host, mqtt, port
                FROM country
                WHERE name_en = ? AND isTest = 0
                LIMIT 1
            """, (country_name,))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
                
            name_en, rest_url, mqtt_host, mqtt_port = row
            
            if language == "ru":
                ru_names = {"Russia": "Россия", "China": "Китай", "Germany": "Германия"}
                country_name_localized = ru_names.get(name_en, name_en)
            else:
                country_name_localized = name_en
            
            return {
                "rest_url": rest_url,
                "mqtt_host": mqtt_host,
                "mqtt_port": mqtt_port or 8011,
                "country_code": country_code,
                "country_name": country_name_localized,
                "phone_code": phone_code,
            }
            
        except Exception as e:
            _LOGGER.error("Error querying country.db: %s", e)
            return None
    
    def _fallback_by_phone_code(self, phone_code: str, language: str) -> Optional[Dict[str, Any]]:
        """Static fallback mapping when databases are unavailable."""
        fallback_map = {
            "7": {
                "rest_url": "https://ru.wisdom.blackvision.net",
                "mqtt_host": "ru.mqtt.blackvision.net",
                "country_code": "ru",
                "country_name": "Russia" if language == "en" else "Россия",
            },
            "86": {
                "rest_url": "https://cn.wisdom.blackvision.net",
                "mqtt_host": "cn.mqtt.blackvision.net",
                "country_code": "cn",
                "country_name": "China" if language == "en" else "Китай",
            },
            "49": {
                "rest_url": "https://de.wisdom.blackvision.net",
                "mqtt_host": "de.mqtt.blackvision.net",
                "country_code": "de",
                "country_name": "Germany" if language == "en" else "Германия",
            },
        }
        
        if phone_code in fallback_map:
            result = fallback_map[phone_code].copy()
            result["mqtt_port"] = 8011
            result["phone_code"] = phone_code
            return result
            
        # По умолчанию Россия
        result = fallback_map["7"].copy()
        result["mqtt_port"] = 8011
        result["phone_code"] = phone_code
        return result


# Singleton instance
_MANAGER = None


def get_data_center_manager(hass) -> DataCenterManager:
    """Get or create singleton DataCenterManager instance."""
    global _MANAGER
    if _MANAGER is None or _MANAGER.hass != hass:
        _MANAGER = DataCenterManager(hass)
    return _MANAGER