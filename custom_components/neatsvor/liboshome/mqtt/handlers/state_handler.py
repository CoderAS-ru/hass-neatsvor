"""State message handler for MQTT."""

import logging
import gzip
from typing import Dict, Any

_LOGGER = logging.getLogger(__name__)


class StateMessageHandler:
    """Handler for STATE_* topic."""

    def __init__(self, mac: str):
        """Initialize state handler."""
        self.mac = mac

    async def parse(self, payload: bytes) -> Dict[str, Any]:
        """Parse STATE message."""
        if payload == b"\x00" or not payload:
            return {"type": "init", "payload": payload}

        try:
            raw = gzip.decompress(payload)
            proto = self._decode_state_proto(raw)

            nested = proto.get(2, {})
            if not isinstance(nested, dict):
                return {"type": "unknown", "proto": proto}

            result = {
                "type": "state_update",
                "flag": nested.get(1),  # 1=charging, 2=working
                "battery": nested.get(2),
                "raw_proto": proto
            }
            _LOGGER.debug("STATE processed: flag=%s, battery=%s", result['flag'], result['battery'])
            return result

        except Exception as e:
            _LOGGER.error("Error processing STATE: %s", e)
            raise

    def _decode_state_proto(self, data: bytes) -> dict:
        """Decode protobuf STATE messages (copy from dev_state_async.py)."""
        if not data:
            return {}

        result = {}
        i = 0
        length = len(data)

        while i < length:
            try:
                if i >= length:
                    break

                key = data[i]
                field = key >> 3
                wire = key & 0x07
                i += 1

                if wire == 0:  # varint
                    value = 0
                    shift = 0
                    while i < length:
                        b = data[i]
                        i += 1
                        value |= (b & 0x7F) << shift
                        if not b & 0x80:
                            break
                        shift += 7
                    result[field] = value

                elif wire == 2:  # length-delimited
                    if i >= length:
                        break

                    length_byte = data[i]
                    i += 1

                    if i + length_byte > length:
                        break

                    raw = data[i:i + length_byte]
                    i += length_byte

                    result[field] = self._decode_state_proto(raw)

                else:
                    i += 1

            except IndexError:
                _LOGGER.warning("Index out of bounds while decoding protobuf")
                break
            except Exception as e:
                _LOGGER.error("Error decoding protobuf: %s", e)
                break

        return result