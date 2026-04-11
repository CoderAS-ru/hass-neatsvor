"""Command sender for MQTT."""

import logging
import asyncio
from typing import Union

_LOGGER = logging.getLogger(__name__)


class CommandSender:
    """
    Command sender to DP_APP_{MAC} topic.
    Analog of separate command sending service in APK.
    """

    def __init__(self, mqtt_client, mac: str, command_delay: float = 0.1):
        """Initialize command sender."""
        self.mqtt = mqtt_client
        self.topic_app = f"DP_APP_{mac}"
        self.command_delay = command_delay

    async def publish_command(self, payload: bytes) -> None:
        """Publish command to MQTT."""
        try:
            _LOGGER.debug("Sending to %s, length: %s", self.topic_app, len(payload))
            await self.mqtt.publish(self.topic_app, payload, qos=0)
            _LOGGER.info("Command sent")

            if self.command_delay > 0:
                await asyncio.sleep(self.command_delay)

        except Exception as e:
            _LOGGER.error("Error sending command: %s", e)
            raise