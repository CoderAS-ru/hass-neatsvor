"""Decoder for MQTT DP messages."""

import gzip
import logging
from typing import Iterator, Tuple, Any, Optional

import os
import sys

# Настраиваем путь для импорта protobuf
proto_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'protobuf')
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

try:
    from custom_components.neatsvor.liboshome.protobuf import sdk_com_pb2 as bvsdk
except ImportError as e:
    print(f"Error: Failed to import sdk_com_pb2 from {proto_dir}: {e}")
    raise

_LOGGER = logging.getLogger(__name__)


def decode_dp_payload(payload: bytes) -> Iterator[Tuple[int, Any]]:
    """Decode DP payload and yield (dp_id, value) pairs."""
    if not payload:
        return

    _LOGGER.debug("DP payload length: %s", len(payload))

    try:
        # 1. Decompress gzip if needed
        if payload.startswith(b'\x1f\x8b'):  # Gzip magic
            try:
                payload = gzip.decompress(payload)
                _LOGGER.debug("Decompressed gzip")
            except Exception as e:
                _LOGGER.warning("Error decompressing gzip: %s", e)

        # 2. Parse protobuf
        msg = bvsdk.MqttMsg()
        try:
            msg.ParseFromString(payload)
        except Exception as e:
            _LOGGER.warning("Failed to parse protobuf: %s", e)
            yield from _legacy_decode(payload)
            return

        # 3. Check message type
        if msg.header.cmd_type != bvsdk.MqttMsgHeader.CmdType.kDeviceReport:
            _LOGGER.debug("Not DP message, type: %s", msg.header.cmd_type)
            return

        # 4. Extract DPs
        cmd_ids = list(msg.header.cmd_id)
        bodies = list(msg.body)

        if len(cmd_ids) != len(bodies):
            _LOGGER.warning("Mismatch between cmd_id count (%s) and body count (%s)", len(cmd_ids), len(bodies))
            return

        _LOGGER.debug("Decoded: %s DPs, cmd_type: %s", len(cmd_ids), msg.header.cmd_type)

        for i, (dp_id, body_any) in enumerate(zip(cmd_ids, bodies)):
            _LOGGER.debug("DP %s: id=%s, body_type=%s", i, dp_id, type(body_any))
            try:
                body = bvsdk.MqttMsgBody()
                if body_any.Unpack(body):
                    value = _extract_value_from_body(body)
                    if value is not None:  # IMPORTANT: skip None values
                        yield (dp_id, value)
                    else:
                        _LOGGER.debug("DP %s has None value, skipping", dp_id)
                else:
                    _LOGGER.debug("Failed to unpack body for DP %s", dp_id)
            except Exception as e:
                _LOGGER.warning("Error processing DP %s: %s", dp_id, e)

    except Exception as e:
        _LOGGER.error("Critical decoding error: %s", e)


def _extract_value_from_body(body: bvsdk.MqttMsgBody) -> Any:
    """Extract value from body message using HasField for reliability."""
    try:
        # Используем HasField для надежного определения типа
        if body.HasField('int_value'):
            return body.int_value
        elif body.HasField('bool_value'):
            return body.bool_value
        elif body.HasField('string_value'):
            return body.string_value
        elif body.HasField('float_value'):
            return body.float_value
        elif body.HasField('bytes_value'):
            return body.bytes_value
    except Exception as e:
        _LOGGER.debug("Error extracting value with HasField: %s", e)
        
        # Fallback для старых версий protobuf
        try:
            # Проверяем наличие атрибутов через hasattr
            if hasattr(body, 'int_value') and body.int_value != 0:
                return body.int_value
            elif hasattr(body, 'bool_value') and body.bool_value != False:
                return body.bool_value
            elif hasattr(body, 'string_value') and body.string_value != "":
                return body.string_value
            elif hasattr(body, 'float_value') and body.float_value != 0.0:
                return body.float_value
            elif hasattr(body, 'bytes_value') and body.bytes_value != b'':
                return body.bytes_value
        except Exception as e2:
            _LOGGER.debug("Fallback extraction failed: %s", e2)

    return None


def _legacy_decode(payload: bytes) -> Iterator[Tuple[int, Any]]:
    """
    Legacy decoder as fallback (based on current decoder.py).
    Used if protobuf parsing fails.
    """
    if not payload:
        return

    i = 0
    length = len(payload)

    while i < length:
        if i + 4 > length:
            return

        dp_id = payload[i]
        dp_type = payload[i + 1]
        dp_len = payload[i + 3]

        i += 4

        if i + dp_len > length:
            return

        raw = payload[i:i + dp_len]
        i += dp_len

        # Process types
        if dp_type == 1:  # bool
            value = bool(raw[0]) if raw else False
        elif dp_type == 4:  # enum
            value = raw[0] if raw else 0
        elif dp_type == 8:  # numerical
            value = 0
            for b in raw:
                value = (value << 8) | b
        else:
            continue

        yield (dp_id, value)