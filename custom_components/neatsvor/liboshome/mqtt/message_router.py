"""MQTT message router for Neatsvor."""

import asyncio
import logging
from typing import List, Any, Callable, Dict

from custom_components.neatsvor.liboshome.mqtt.handlers.map_handler import MapMessageHandler
from custom_components.neatsvor.liboshome.mqtt.handlers.state_handler import StateMessageHandler
from custom_components.neatsvor.liboshome.mqtt.handlers.dp_handler import DpMessageHandler

_LOGGER = logging.getLogger(__name__)


class DpAppMessageHandler:
    """Handler for DP_APP messages (command confirmations / echoes).

    Интеграция шлёт команды в топик DP_APP_<MAC>, а брокер/устройство
    отвечает в этот же топик короткими (36–59 байт) сообщениями.
    Раньше они никак не логировались — теперь логируем payload целиком,
    чтобы понять, что именно приходит.
    """

    def __init__(self, mac: str):
        self.mac = mac

    async def parse(self, payload: bytes) -> Dict[str, Any]:
        """Parse DP_APP payload — сейчас просто логируем."""
        try:
            hex_payload = payload.hex()
        except Exception:
            hex_payload = repr(payload)

        _LOGGER.debug(
            "DP_APP payload received (len=%d): %s",
            len(payload),
            hex_payload,
        )
        return {"raw": payload, "hex": hex_payload}


class MqttMessageRouter:
    """Router for MQTT messages to appropriate handlers."""

    def __init__(self, client_id: str, mac: str):
        """Initialize router."""
        self.client_id = client_id
        self.mac = mac

        self._handlers = [
            ('MAP_UNZIP_', MapMessageHandler(mac)),
            ('MAP_', MapMessageHandler(mac)),
            ('STATE_', StateMessageHandler(mac)),
            ('DP_DEV_', DpMessageHandler(mac)),
            ('DEVICE_ON_LINE_', None),
            ('DP_APP_', DpAppMessageHandler(mac)),
        ]

        # Lists for callbacks
        self._map_callbacks: List[Callable] = []
        self._state_callbacks: List[Callable] = []
        self._dp_callbacks: List[Callable] = []

    async def on_mqtt_message(self, msg) -> None:
        """Single handler for MQTT client."""
        topic = msg.topic
        payload = msg.payload

        # IMPORTANT: convert topic to string
        topic_str = str(topic)

        # Логируем все входящие сообщения
        _LOGGER.debug("RX Topic: %s, Length: %s", topic_str, len(payload))

        # Дополнительное логирование payload для критичных топиков.
        # Для MAP_* — только первые 64 байта (карта может быть большой).
        # Для DP_APP_ — целиком (он короткий).
        try:
            if topic_str.startswith(('MAP_', 'MAP_UNZIP_')):
                _LOGGER.debug(
                    "RX %s payload first 64 hex: %s",
                    topic_str,
                    payload[:64].hex(),
                )
            elif topic_str.startswith('DP_APP_'):
                _LOGGER.debug(
                    "RX %s payload hex: %s",
                    topic_str,
                    payload.hex(),
                )
        except Exception as log_err:
            _LOGGER.debug("Failed to log payload for %s: %s", topic_str, log_err)

        # Find appropriate handler by topic prefix
        for prefix, handler in self._handlers:
            if not topic_str.startswith(prefix):
                continue

            if handler is None:
                _LOGGER.debug("Topic without handler: %s", topic_str)
                return

            try:
                if prefix in ('MAP_', 'MAP_UNZIP_'):
                    parsed_data = await handler.parse(payload)
                    await self._notify_map_callbacks(parsed_data)

                elif prefix == 'STATE_':
                    parsed_data = await handler.parse(payload)
                    await self._notify_state_callbacks(parsed_data)

                elif prefix == 'DP_DEV_':
                    parsed_data = await handler.parse(payload)
                    await self._notify_dp_callbacks(parsed_data)

                elif prefix == 'DP_APP_':
                    # Ответы/эхо на наши команды. Пока просто логируем.
                    parsed_data = await handler.parse(payload)
                    # Здесь при желании можно вызвать отдельные колбэки,
                    # если понадобится обрабатывать подтверждения.

                else:
                    _LOGGER.debug("Unhandled prefix: %s", prefix)

            except Exception as e:
                _LOGGER.error("Error in handler %s for topic %s: %s", prefix, topic_str, e)

            # Нашли подходящий префикс — дальше не идём
            return

        # If no handler found, just log
        _LOGGER.debug("Topic without handler: %s", topic_str)

    async def _notify_map_callbacks(self, map_data: dict):
        """Notify all subscribers about new map."""
        for callback in self._map_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(map_data)
                else:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, callback, map_data)
            except Exception as e:
                _LOGGER.error("Error in map callback: %s", e)

    async def _notify_state_callbacks(self, state_data: dict):
        """Notify all subscribers about STATE."""
        for callback in self._state_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(state_data)
                else:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, callback, state_data)
            except Exception as e:
                _LOGGER.error("Error in state callback: %s", e)

    async def _notify_dp_callbacks(self, dp_data: list):
        """Notify all subscribers about DP."""
        for callback in self._dp_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(dp_data)
                else:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, callback, dp_data)
            except Exception as e:
                _LOGGER.error("Error in dp callback: %s", e)

    # === Public API for callback registration ===
    def register_map_callback(self, callback: Callable):
        """Register map callback."""
        if callback not in self._map_callbacks:
            self._map_callbacks.append(callback)
            _LOGGER.debug("Registered map callback, total: %s", len(self._map_callbacks))

    def remove_map_callback(self, callback: Callable):
        """Remove map callback."""
        if callback in self._map_callbacks:
            self._map_callbacks.remove(callback)
            _LOGGER.debug("Removed map callback")

    def register_state_callback(self, callback: Callable):
        """Register state callback."""
        if callback not in self._state_callbacks:
            self._state_callbacks.append(callback)
            _LOGGER.debug("Registered state callback, total: %s", len(self._state_callbacks))

    def remove_state_callback(self, callback: Callable):
        """Remove state callback."""
        if callback in self._state_callbacks:
            self._state_callbacks.remove(callback)
            _LOGGER.debug("Removed state callback")

    def register_dp_callback(self, callback: Callable):
        """Register DP callback."""
        if callback not in self._dp_callbacks:
            self._dp_callbacks.append(callback)
            _LOGGER.debug("Registered dp callback, total: %s", len(self._dp_callbacks))

    def remove_dp_callback(self, callback: Callable):
        """Remove DP callback."""
        if callback in self._dp_callbacks:
            self._dp_callbacks.remove(callback)
            _LOGGER.debug("Removed dp callback")

    async def subscribe_to_device_topics(self, mqtt_client) -> None:
        """Subscribe to all device topics via MQTT client."""
        _LOGGER.info("Subscribing to topics for MAC: %s", self.mac)

        # All topics to listen to
        topics = [
            (f"MAP_{self.mac}", 0),
            (f"MAP_UNZIP_{self.mac}", 0),
            (f"STATE_{self.mac}", 1),
            (f"DP_DEV_{self.mac}", 1),
            (f"DP_APP_{self.mac}", 1),
            (f"DEVICE_ON_LINE_{self.mac}", 1),
        ]

        for topic, qos in topics:
            try:
                await mqtt_client.subscribe(topic, qos)
                _LOGGER.debug("Subscribed to: %s, QoS: %s", topic, qos)
            except Exception as e:
                _LOGGER.error("Error subscribing to %s: %s", topic, e)