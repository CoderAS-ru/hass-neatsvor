"""DP message handler for MQTT."""

import asyncio
import logging
from typing import List, Tuple, Any
from custom_components.neatsvor.liboshome.mqtt.decoder import decode_dp_payload

_LOGGER = logging.getLogger(__name__)


class DpMessageHandler:
    """Handler for DP_DEV_* topic."""

    def __init__(self, mac: str):
        """Initialize DP handler."""
        self.mac = mac

    async def parse(self, payload: bytes) -> List[Tuple[int, Any]]:
        """Parse DP message, return list of (dp_id, value)."""
        _LOGGER.debug("Processing DP, MAC: %s", self.mac)
        try:
            # Decoding involves gzip decompression + protobuf parsing.
            # Run in executor to avoid blocking the HA event loop.
            result = await asyncio.to_thread(_decode_dp_list, payload)
            _LOGGER.info("Successfully decoded DP: %s entries", len(result))
            return result
        except Exception as e:
            _LOGGER.error("Error decoding DP: %s", e)
            raise


def _decode_dp_list(payload: bytes) -> List[Tuple[int, Any]]:
    """Materialize decode_dp_payload generator in a thread."""
    return list(decode_dp_payload(payload))