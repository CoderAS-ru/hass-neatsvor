"""MQTT message router for Neatsvor."""

import asyncio
import logging
from typing import List, Any, Callable, Dict
from custom_components.neatsvor.liboshome.mqtt.handlers.map_handler import MapMessageHandler
from custom_components.neatsvor.liboshome.mqtt.handlers.state_handler import StateMessageHandler
from custom_components.neatsvor.liboshome.mqtt.handlers.dp_handler import DpMessageHandler

_LOGGER = logging.getLogger(__name__)


class MqttMessageRouter:
    """Router for MQTT messages to appropriate handlers."""

    def __init__(self, client_id: str, mac: str):
        """Initialize router."""
        self.client_id = client_id
        self.mac = mac

        # Initialize ALL handlers
        self._handlers: Dict[str, Any] = {
            'MAP_': MapMessageHandler(mac),
            'MAP_UNZIP_': MapMessageHandler(mac),
            'STATE_': StateMessageHandler(mac),
            'DP_DEV_': DpMessageHandler(mac),
            'DEVICE_ON_LINE_': self._handle_device_online,
            'DP_APP_': self._handle_dp_app,
        }

        # Lists for callbacks
        self._map_callbacks: List[Callable] = []
        self._state_callbacks: List[Callable] = []
        self._dp_callbacks: List[Callable] = []

    async def on_mqtt_message(self, msg) -> None:
        """Single handler for MQTT client."""
        topic = msg.topic
        payload = msg.payload

        # Convert topic to string
        topic_str = str(topic)

        # Log all incoming messages for debugging
        _LOGGER.debug("RX Topic: %s, Length: %s", topic_str, len(payload))

        # Find appropriate handler by topic prefix
        for prefix, handler in self._handlers.items():
            if topic_str.startswith(prefix):
                try:
                    # Handle callable handlers (for DEVICE_ON_LINE_, DP_APP_)
                    if callable(handler):
                        await handler(payload)  # Pass only payload
                    else:
                        # Handler is a class instance with parse method
                        parsed_data = await handler.parse(payload)
                        if prefix in ['MAP_', 'MAP_UNZIP_']:
                            await self._notify_map_callbacks(parsed_data)
                        elif prefix == 'STATE_':
                            await self._notify_state_callbacks(parsed_data)
                        elif prefix == 'DP_DEV_':
                            await self._notify_dp_callbacks(parsed_data)
                    return
                except Exception as e:
                    _LOGGER.error("Error in handler %s: %s", prefix, e)
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
                    loop = asyncio.get_event_loop()
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
                    loop = asyncio.get_event_loop()
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
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, callback, dp_data)
            except Exception as e:
                _LOGGER.error("Error in dp callback: %s", e)

    async def _handle_dp_app(self, payload):
        """Handler for DP_APP_ topics (command confirmations)."""
        try:
            # Try to parse as JSON if it's a string
            if isinstance(payload, bytes):
                payload = payload.decode('utf-8')
            
            _LOGGER.debug("DP_APP_ command confirmation received: %s", payload[:200] if len(payload) > 200 else payload)
            
            # Notify DP callbacks if needed
            if self._dp_callbacks:
                # Try to parse as list of DPs
                import json
                try:
                    data = json.loads(payload)
                    if isinstance(data, list):
                        await self._notify_dp_callbacks(data)
                    elif isinstance(data, dict) and 'dps' in data:
                        await self._notify_dp_callbacks(data['dps'])
                except json.JSONDecodeError:
                    _LOGGER.debug("DP_APP_ payload not JSON: %s", payload[:100])
                    
        except Exception as e:
            _LOGGER.error("Error handling DP_APP_ message: %s", e)
            
    async def _handle_device_online(self, payload):
        """Handler for DEVICE_ON_LINE_ topics."""
        try:
            if isinstance(payload, bytes):
                payload = payload.decode('utf-8')
            
            _LOGGER.info("Device online status update: %s", payload[:100] if len(payload) > 100 else payload)
            
            # Parse online status
            import json
            try:
                data = json.loads(payload)
                is_online = data.get('online', False) if isinstance(data, dict) else False
                _LOGGER.info("Device online: %s", is_online)
            except json.JSONDecodeError:
                # Maybe just plain text
                is_online = payload.lower() in ['true', '1', 'online']
                _LOGGER.info("Device online (text): %s", is_online)
                
        except Exception as e:
            _LOGGER.error("Error handling DEVICE_ON_LINE_ message: %s", e)

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