"""DP message handler for MQTT."""

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
            result = list(decode_dp_payload(payload))
            _LOGGER.info("Successfully decoded DP: %s entries", len(result))
            return result
        except Exception as e:
            _LOGGER.error("Error decoding DP: %s", e)
            raise