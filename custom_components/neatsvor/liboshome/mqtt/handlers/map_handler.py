"""Map message handler for MQTT."""

import asyncio
import logging
from custom_components.neatsvor.liboshome.map.map_decoder import MapDecoder

_LOGGER = logging.getLogger(__name__)


class MapMessageHandler:
    """Handler for MAP_* and MAP_UNZIP_* topics."""

    def __init__(self, mac: str):
        """Initialize map handler."""
        self.mac = mac
        self.decoder = MapDecoder()

    async def parse(self, payload: bytes) -> dict:
        """Main method: parse payload -> return dict with map."""
        _LOGGER.debug("Processing map, MAC: %s", self.mac)
        try:
            result = await asyncio.to_thread(self.decoder.decode_mqtt_map, payload)
            _LOGGER.info("Successfully decoded map: %sx%s", result.get('width', 0), result.get('height', 0))

            # === DEBUG DUMP ===
            from custom_components.neatsvor.liboshome.map.map_utils import MapDebugDumper
            await asyncio.to_thread(MapDebugDumper.dump, result, "realtime", "live")
            # === /DEBUG DUMP ===

            return result
        except Exception as e:
            _LOGGER.error("Error decoding map: %s", e)
            raise