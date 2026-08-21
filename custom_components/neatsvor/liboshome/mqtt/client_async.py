"""
Asynchronous MQTT client using aiomqtt.
Optimized for Windows.
"""

import asyncio
import logging
from typing import List, Callable, Awaitable, Optional

import aiomqtt
import paho.mqtt.client as mqtt  # aiomqtt uses paho under the hood

_LOGGER = logging.getLogger(__name__)


class AsyncMQTTClient:
    """
    Asynchronous MQTT client using aiomqtt.
    Special version for Windows.
    """

    def __init__(self, host: str, port: int, username: str, password: str, client_id: str):
        """Initialize MQTT client."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client_id = client_id

        self._client: Optional[aiomqtt.Client] = None
        self._listening_task: Optional[asyncio.Task] = None
        self._handlers: List[Callable] = []
        self._connected = False
        self._should_run = True

    async def connect(self) -> None:
        """Connect to MQTT broker."""
        _LOGGER.info("Connecting to %s:%s...", self.host, self.port)

        try:
            self._client = aiomqtt.Client(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                identifier=self.client_id,
                keepalive=60
            )

            # Add connection timeout
            await asyncio.wait_for(
                self._client.__aenter__(),
                timeout=10.0
            )

            self._connected = True
            _LOGGER.info("MQTT connected to %s:%s (client_id: %s)", self.host, self.port, self.client_id)

            self._listening_task = asyncio.create_task(self._listen())

        except asyncio.TimeoutError:
            _LOGGER.error("MQTT connection timeout")
            raise
        except Exception as e:
            _LOGGER.error("Error connecting to MQTT: %s", e)
            raise

    async def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        self._should_run = False
        self._connected = False

        # Stop listener
        if self._listening_task and not self._listening_task.done():
            self._listening_task.cancel()
            try:
                await asyncio.wait_for(self._listening_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                pass
            finally:
                self._listening_task = None

        # Close client
        if self._client:
            try:
                # For aiomqtt on Windows, need to close carefully
                await self._client.__aexit__(None, None, None)
            except RuntimeError as e:
                if "Event loop is closed" not in str(e):
                    _LOGGER.debug("Error closing MQTT client: %s", e)
            except Exception as e:
                _LOGGER.debug("Error closing MQTT client: %s", e)
            finally:
                self._client = None

        _LOGGER.info("MQTT client disconnected")

    async def _listen(self) -> None:
        """Listener for incoming messages."""
        _LOGGER.info("MQTT listener started")

        try:
            async for message in self._client.messages:
                if not self._should_run:
                    break

                # Log only important topics for debugging
                topic_str = str(message.topic)
                if topic_str.startswith(("MAP_", "STATE_", "DP_DEV_")):
                    _LOGGER.debug("Received: %s (%s bytes)", message.topic, len(message.payload))

                # Pass message to all handlers
                for handler in self._handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(message)
                        else:
                            handler(message)
                    except Exception as e:
                        _LOGGER.error("Error in MQTT handler: %s", e)

        except asyncio.CancelledError:
            _LOGGER.info("MQTT listener stopped")
        except Exception as e:
            _LOGGER.error("Error in MQTT listener: %s", e)

    async def publish(self, topic: str, payload: bytes, qos: int = 1) -> None:
        """Publish message."""
        if not self._connected or not self._client:
            raise ConnectionError("MQTT not connected")

        try:
            await self._client.publish(topic, payload=payload, qos=qos)
            _LOGGER.debug("Published to %s: %s bytes", topic, len(payload))
        except Exception as e:
            _LOGGER.error("Error publishing to %s: %s", topic, e)
            raise

    async def subscribe(self, topic: str, qos: int = 1) -> None:
        """Subscribe to topic."""
        if not self._connected or not self._client:
            raise ConnectionError("MQTT not connected")

        try:
            await self._client.subscribe(topic, qos=qos)
            _LOGGER.info("Subscribed to %s (QoS %s)", topic, qos)
        except Exception as e:
            _LOGGER.error("Error subscribing to %s: %s", topic, e)
            raise

    def add_handler(self, handler) -> None:
        """Add message handler."""
        if handler not in self._handlers:
            self._handlers.append(handler)
            _LOGGER.debug("Added MQTT handler, total: %s", len(self._handlers))

    def remove_handler(self, handler) -> None:
        """Remove message handler."""
        if handler in self._handlers:
            self._handlers.remove(handler)
            _LOGGER.debug("Removed MQTT handler, remaining: %s", len(self._handlers))

    @property
    def is_connected(self) -> bool:
        """Check connection status."""
        return self._connected