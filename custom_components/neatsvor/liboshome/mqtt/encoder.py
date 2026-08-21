"""
Universal command encoder for Neatsvor S700.
Now uses dynamic DP_SCHEMA from REST API.
"""

import gzip
import json
from typing import Union, Dict, Any, Optional, List
from dataclasses import dataclass
import logging

_LOGGER = logging.getLogger(__name__)

import os
import sys

# Add path to protobuf folder
proto_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'protobuf')
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

try:
    from custom_components.neatsvor.liboshome.protobuf import sdk_com_pb2 as bvsdk
    _LOGGER.info("Protobuf modules loaded from: %s", proto_dir)
except ImportError as e:
    _LOGGER.error("Failed to import sdk_com_pb2 from %s: %s", proto_dir, e)
    _LOGGER.error("Please check that sdk_com_pb2.py exists in liboshome/protobuf/")
    raise


@dataclass
class CommandResult:
    """Result of command creation."""
    raw_bytes: bytes
    hex_str: str
    dp_id: int
    value: Any
    size: int


class NeatsvorEncoder:
    """
    Universal command encoder for Neatsvor S700.
    Uses dynamic DP_SCHEMA from REST API.
    """

    def __init__(self, device_mac: str, dp_schema: Dict[int, Dict],
                 login_name: str = "appuser", version: int = 1):
        """
        Args:
            device_mac: Device MAC address (e.g. "AA:BB:CC:DD:EE:FF")
            dp_schema: DP schema from REST API
            login_name: Login name (default "appuser")
            version: Protocol version (usually 1)
        """
        self.device_mac = device_mac
        self.dp_schema = dp_schema
        self.login_name = login_name
        self.version = version
        _LOGGER.debug("Encoder initialized for device %s", device_mac)

    def create_dp_command(self, dp_id: int, value: Union[bool, int, str, bytes, Any]) -> bytes:
        """
        Main method - creates command for any DP.
        """
        # Check DP in dynamic schema
        if dp_id not in self.dp_schema:
            available_dps = list(self.dp_schema.keys())
            raise ValueError(f"DP {dp_id} does not exist. Available DPs: {available_dps}")

        dp_info = self.dp_schema[dp_id]
        dp_type = dp_info.get('type')

        if dp_type is None:
            raise ValueError(f"DP {dp_id} has no type in schema")

        # Validate value (with special handling for DP 14)
        self._validate_value(dp_id, dp_type, value, dp_info.get('enum'))

        try:
            # 1. Create message body (MqttMsgBody) or use ready one
            from google.protobuf import any_pb2
            body_any = any_pb2.Any()

            # If value is already a protobuf message
            if hasattr(value, 'DESCRIPTOR'):
                _LOGGER.debug("Value is protobuf message of type %s", type(value).__name__)
                body_any.Pack(value)
            elif isinstance(value, bytes):
                # If it's already serialized bytes, try to parse as Any
                try:
                    body_any.ParseFromString(value)
                except:
                    # If parsing fails, create new Any with these bytes
                    body_any.value = value
                    body_any.type_url = "type.googleapis.com/sweeper.UseMap"
            else:
                # Normal handling for primitive types
                body = bvsdk.MqttMsgBody()
                if dp_type == 0:  # bool
                    body.bool_value = bool(value)
                elif dp_type in (1, 2):  # int or enum
                    body.int_value = int(value)
                elif dp_type == 3:  # string/raw
                    if isinstance(value, bytes):
                        body.string_value = value.decode('utf-8', errors='ignore')
                    else:
                        body.string_value = str(value)
                else:
                    raise ValueError(f"Unknown DP type {dp_type} for DP {dp_id}")

                body_any.Pack(body)

            # 2. Create header
            header = bvsdk.MqttMsgHeader()
            header.version = self.version
            header.mac_address = self.device_mac
            header.login_name = self.login_name
            header.cmd_id.append(dp_id)
            header.cmd_type = bvsdk.MqttMsgHeader.CmdType.kAppCmd

            # 3. Create main message
            msg = bvsdk.MqttMsg()
            msg.header.CopyFrom(header)
            msg.body.append(body_any)

            # 4. Serialize and compress
            serialized = msg.SerializeToString()
            compressed = gzip.compress(serialized)

            _LOGGER.debug("Created command DP %s, size: %s bytes", dp_id, len(compressed))
            return compressed

        except Exception as e:
            _LOGGER.error("Error creating command DP %s: %s", dp_id, e)
            raise

    def _validate_value(self, dp_id: int, dp_type: int, value: Any, enum_map: Dict = None):
        """Validate value for DP."""
        if dp_type == 0 and not isinstance(value, (bool, int)):
            raise ValueError(f"DP {dp_id} requires bool value, got {type(value)}")

        if dp_type in (1, 2) and not isinstance(value, (int, float)):
            raise ValueError(f"DP {dp_id} requires numeric value, got {type(value)}")

        if dp_type == 2 and enum_map:
            int_val = int(value)
            if int_val not in enum_map:
                valid_values = list(enum_map.items())
                raise ValueError(f"DP {dp_id}: value {value} invalid. "
                               f"Valid values: {valid_values}")

    def create_command_with_result(self, dp_id: int, value: Any) -> CommandResult:
        """
        Create command with additional information.

        Returns:
            CommandResult with raw data and meta information
        """
        raw = self.create_dp_command(dp_id, value)
        return CommandResult(
            raw_bytes=raw,
            hex_str=raw.hex(),
            dp_id=dp_id,
            value=value,
            size=len(raw)
        )

    def decode_response(self, compressed_data: bytes) -> dict:
        """
        Decode response from device.

        Args:
            compressed_data: Compressed data from device

        Returns:
            Dictionary with decoded data or error information
        """
        try:
            # First try to decompress gzip
            if compressed_data.startswith(b'\x1f\x8b'):
                decompressed = gzip.decompress(compressed_data)
            else:
                decompressed = compressed_data

            # Try to parse as protobuf
            try:
                msg = bvsdk.MqttMsg()
                msg.ParseFromString(decompressed)

                result = {
                    'version': msg.header.version,
                    'mac': msg.header.mac_address,
                    'login': msg.header.login_name,
                    'cmd_ids': list(msg.header.cmd_id),
                    'cmd_type': msg.header.cmd_type,
                    'bodies': []
                }

                for body_any in msg.body:
                    try:
                        body = bvsdk.MqttMsgBody()
                        if body_any.Unpack(body):
                            body_data = {}
                            if body.HasField('int_value'):
                                body_data['type'] = 'int'
                                body_data['value'] = body.int_value
                            elif body.HasField('bool_value'):
                                body_data['type'] = 'bool'
                                body_data['value'] = body.bool_value
                            elif body.HasField('string_value'):
                                body_data['type'] = 'string'
                                body_data['value'] = body.string_value
                            else:
                                body_data['type'] = 'unknown'
                                body_data['value'] = 'no value field set'

                            result['bodies'].append(body_data)
                    except Exception as body_error:
                        _LOGGER.debug("Error unpacking body: %s", body_error)
                        result['bodies'].append({'error': str(body_error)})

                return result

            except Exception as parse_error:
                # If parsing as protobuf fails, return raw data
                _LOGGER.debug("Failed to parse as protobuf: %s", parse_error)
                return {
                    'error': 'parse_failed',
                    'message': str(parse_error),
                    'raw_length': len(decompressed),
                    'raw_hex': decompressed.hex()[:100]
                }

        except Exception as e:
            _LOGGER.debug("Error decoding response: %s", e)
            return {
                'error': 'decode_failed',
                'message': str(e),
                'raw_length': len(compressed_data),
                'raw_hex': compressed_data.hex()[:50]
            }

    def get_dp_info(self, dp_id: int) -> Optional[Dict]:
        """
        Get DP information.

        Args:
            dp_id: Data Point ID

        Returns:
            Dictionary with DP information or None if not found
        """
        return self.dp_schema.get(dp_id)

    def get_dp_by_code(self, code: str) -> Optional[Dict]:
        """
        Find DP by code.

        Args:
            code: DP code (e.g. 'switch_clean')

        Returns:
            Dictionary with DP information or None if not found
        """
        for dp_id, info in self.dp_schema.items():
            if info.get('code') == code:
                return {'dp_id': dp_id, **info}
        return None

    @classmethod
    def from_dp_manager(cls, device_mac: str, dp_manager,
                        login_name: str = "appuser", version: int = 1):
        """
        Create encoder from DPManager.

        Args:
            device_mac: Device MAC address
            dp_manager: DPManager instance
            login_name: Login name (default "appuser")
            version: Protocol version (usually 1)

        Returns:
            NeatsvorEncoder
        """
        schema = dp_manager.to_encoder_schema()
        return cls(device_mac, schema, login_name, version)


class VacuumCommands:
    """
    Helper class for quick commands.
    Automatically finds DP ID by codes.
    """

    def __init__(self, encoder: NeatsvorEncoder):
        """Initialize with encoder."""
        self.encoder = encoder
        self._command_cache = {}  # Cache for frequently used commands

    def _get_dp_id_by_code(self, code: str) -> int:
        """
        Get DP ID by code.

        Args:
            code: DP code

        Returns:
            DP ID

        Raises:
            ValueError: If DP with this code is not found
        """
        # First search in schema
        for dp_id, dp_info in self.encoder.dp_schema.items():
            if dp_info.get('code') == code:
                return dp_id

        # If not found, try partial match
        for dp_id, dp_info in self.encoder.dp_schema.items():
            if code in dp_info.get('code', ''):
                _LOGGER.warning("Exact match for '%s' not found, using '%s'", code, dp_info.get('code'))
                return dp_id

        available_codes = [dp_info.get('code') for dp_info in self.encoder.dp_schema.values()]
        raise ValueError(f"DP with code '{code}' not found in schema. Available codes: {available_codes}")

    def start(self) -> bytes:
        """Start cleaning."""
        dp_id = self._get_dp_id_by_code('switch_clean')
        return self.encoder.create_dp_command(dp_id, 2)

    def pause(self) -> bytes:
        """Pause cleaning."""
        dp_id = self._get_dp_id_by_code('switch_clean')
        return self.encoder.create_dp_command(dp_id, 1)

    def stop(self) -> bytes:
        """Stop cleaning."""
        dp_id = self._get_dp_id_by_code('switch_clean')
        return self.encoder.create_dp_command(dp_id, 0)

    def go_to_dock(self) -> bytes:
        """Return to dock."""
        dp_id = self._get_dp_id_by_code('switch_charge')
        return self.encoder.create_dp_command(dp_id, 2)

    def set_fan_speed(self, level: int) -> bytes:
        """
        Set fan speed.

        Args:
            level: Speed level
                  0: none, 1: quiet, 2: normal, 3: strong, 4: max
        """
        if level not in range(5):
            raise ValueError("Fan level must be 0-4")

        dp_id = self._get_dp_id_by_code('fan')
        return self.encoder.create_dp_command(dp_id, level)

    def set_water_level(self, level: int) -> bytes:
        """
        Set water level.

        Args:
            level: Water level
                  0: none, 1: low, 2: middle, 3: high
        """
        if level not in range(4):
            raise ValueError("Water level must be 0-3")

        dp_id = self._get_dp_id_by_code('water_tank')
        return self.encoder.create_dp_command(dp_id, level)

    def locate(self) -> bytes:
        """Locate robot (makes it beep)."""
        dp_id = self._get_dp_id_by_code('locate')
        return self.encoder.create_dp_command(dp_id, True)

    def send_custom(self, dp_code: str, value: Any) -> bytes:
        """
        Send command by DP code.

        Args:
            dp_code: DP code
            value: Value

        Returns:
            Command bytes
        """
        dp_id = self._get_dp_id_by_code(dp_code)
        return self.encoder.create_dp_command(dp_id, value)