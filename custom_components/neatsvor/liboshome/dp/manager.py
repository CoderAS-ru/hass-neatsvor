"""
DPManager - Central management unit for Data Points.

Combines functionality:
- DPRegistry (storage and search of DP)
- DpMapping (code↔id mapping)
- Value validation
- Formatting for encoder
"""

import logging
from typing import Dict, Any, Optional, List, Tuple, Callable
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)


@dataclass
class DPDefinition:
    """Complete definition of a single Data Point."""

    id: int
    code: str
    type: int  # 0=bool, 1=number, 2=enum, 3=string
    enum: Optional[Dict[int, str]] = None
    scale: int = 1
    multiple: int = 1
    raw_data: Optional[Dict] = None

    @property
    def type_name(self) -> str:
        """Human-readable type name."""
        names = {0: "bool", 1: "number", 2: "enum", 3: "string"}
        return names.get(self.type, f"unknown({self.type})")

    def validate(self, value: Any) -> bool:
        """Validate value against type."""
        if value is None:
            return False

        if self.type == 0:  # bool
            return isinstance(value, (bool, int))
        elif self.type in (1, 2):  # number, enum
            if not isinstance(value, (int, float)):
                return False
            if self.type == 2 and self.enum:
                return int(value) in self.enum
            return True
        elif self.type == 3:  # string
            return isinstance(value, (str, bytes))
        return False

    def format_value(self, value: Any) -> Any:
        """Convert value to required format."""
        if value is None:
            return None

        if self.type == 0:
            return bool(value)
        elif self.type in (1, 2):
            return int(value)
        elif self.type == 3:
            return str(value) if not isinstance(value, bytes) else value.decode('utf-8', errors='ignore')
        return value

    def get_enum_text(self, value: int) -> str:
        """Text representation of enum value."""
        if self.type != 2 or not self.enum:
            return str(value)
        return self.enum.get(int(value), str(value))

    @classmethod
    def from_api_dict(cls, data: Dict) -> 'DPDefinition':
        """Create DPDefinition from raw API response."""
        dp_id = data.get("dpNum")
        if dp_id is None:
            raise ValueError("API data missing dpNum")

        # Convert enum from API format {"stop": 0} → {0: "stop"}
        enum_raw = data.get("dpEnum")
        enum = None
        if enum_raw and isinstance(enum_raw, dict):
            enum = {v: k for k, v in enum_raw.items()}

        # Multiplier for numeric values (clean_time, clean_area)
        multiple = 1
        if data.get("dpNumerical"):
            multiple = data["dpNumerical"].get("multiple", 1)

        return cls(
            id=dp_id,
            code=data.get("dpCode", f"dp_{dp_id}"),
            type=data.get("dataType", 3),
            enum=enum,
            scale=data.get("dpNumerical", {}).get("scale", 1) if data.get("dpNumerical") else 1,
            multiple=multiple,
            raw_data=data
        )


class DPManager:
    """
    Unified manager for working with Data Points.

    Features:
    - Bidirectional ID ↔ Code mapping
    - Value validation before sending
    - Formatting for encoder
    - Caching of frequently used DP
    """

    # Constants for frequently used codes (from APK)
    CODE_SWITCH_CLEAN = 'switch_clean'
    CODE_STATUS = 'status'
    CODE_MODE = 'mode'
    CODE_FAN = 'fan'
    CODE_WATER_TANK = 'water_tank'
    CODE_LOCATE = 'locate'
    CODE_SWITCH_CHARGE = 'switch_charge'
    CODE_CLEAN_MODE = 'clean_mode'
    CODE_CLEAN_TIME = 'clean_time'
    CODE_CLEAN_AREA = 'clean_area'
    CODE_BATTERY_PERCENTAGE = 'battery_percentage'
    CODE_MALFUNCTION = 'malfunction'
    CODE_ROOM_CLEAN = 'room_clean'
    CODE_ROOM_CLEAN_ATTR = 'room_clean_attr'

    def __init__(self):
        self._by_id: Dict[int, DPDefinition] = {}
        self._by_code: Dict[str, DPDefinition] = {}
        self._sensor_mapping: Dict[int, Tuple[str, Callable]] = {}
        self._command_cache: Dict[str, int] = {}  # cache for command -> dp_id

    # ----------------------------------------------------------------------
    # Data loading
    # ----------------------------------------------------------------------

    def load_from_api_list(self, dp_list: List[Dict]) -> int:
        """
        Load DP from list of API responses.

        Args:
            dp_list: List of dictionaries with DP data from REST API

        Returns:
            Number of loaded DP
        """
        count = 0
        for item in dp_list:
            try:
                dp_def = DPDefinition.from_api_dict(item)
                self.add(dp_def)
                count += 1
            except Exception as e:
                _LOGGER.error("Error loading DP: %s, data: %s", e, item)

        _LOGGER.info("DPManager: loaded %s DP", count)
        return count

    def add(self, dp_def: DPDefinition) -> None:
        """Add a single DP definition."""
        self._by_id[dp_def.id] = dp_def
        self._by_code[dp_def.code] = dp_def
        _LOGGER.debug("DP added: %s = %s", dp_def.id, dp_def.code)

    def clear(self) -> None:
        """Clear all data."""
        self._by_id.clear()
        self._by_code.clear()
        self._sensor_mapping.clear()
        self._command_cache.clear()

    # ----------------------------------------------------------------------
    # Search and retrieval
    # ----------------------------------------------------------------------

    def get_by_id(self, dp_id: int) -> Optional[DPDefinition]:
        """Get DP definition by ID."""
        return self._by_id.get(dp_id)

    def get_by_code(self, code: str) -> Optional[DPDefinition]:
        """Get DP definition by code."""
        return self._by_code.get(code)

    def get_id(self, code: str) -> Optional[int]:
        """Get ID by code (main method for commands)."""
        dp = self._by_code.get(code)
        return dp.id if dp else None

    def get_code(self, dp_id: int) -> Optional[str]:
        """Get code by ID."""
        dp = self._by_id.get(dp_id)
        return dp.code if dp else None

    def get_all_ids(self) -> List[int]:
        """Get all IDs."""
        return list(self._by_id.keys())

    def get_all_codes(self) -> List[str]:
        """Get all codes."""
        return list(self._by_code.keys())

    def __contains__(self, item) -> bool:
        """Check presence (by ID or code)."""
        if isinstance(item, int):
            return item in self._by_id
        elif isinstance(item, str):
            return item in self._by_code
        return False

    def __len__(self) -> int:
        return len(self._by_id)

    # ----------------------------------------------------------------------
    # Validation and formatting
    # ----------------------------------------------------------------------

    def validate(self, dp_id: int, value: Any) -> bool:
        """Check if value is valid for given DP."""
        dp = self._by_id.get(dp_id)
        if not dp:
            _LOGGER.warning("DP %s not found", dp_id)
            return False
        return dp.validate(value)

    def validate_by_code(self, code: str, value: Any) -> bool:
        """Check value by DP code."""
        dp = self._by_code.get(code)
        if not dp:
            _LOGGER.warning("DP code '%s' not found", code)
            return False
        return dp.validate(value)

    def format_for_encoder(self, dp_id: int, value: Any) -> Any:
        """
        Format value for sending via encoder.

        Returns:
            Value in format expected by NeatsvorEncoder
        """
        dp = self._by_id.get(dp_id)
        if not dp:
            return value

        if dp.type == 0:  # bool
            return bool(value)
        elif dp.type in (1, 2):  # number, enum
            return int(value)
        elif dp.type == 3:  # string
            if isinstance(value, bytes):
                return value.decode('utf-8', errors='ignore')
            return str(value)
        return value

    # ----------------------------------------------------------------------
    # Sensor mapping (for state updates)
    # ----------------------------------------------------------------------

    def build_sensor_mapping(self) -> Dict[int, Tuple[str, Callable]]:
        """
        Create mapping DP ID → (sensor attribute, transform function).
        """
        mapping = {}

        for dp_id, dp in self._by_id.items():
            code = dp.code

            if code == self.CODE_BATTERY_PERCENTAGE:
                mapping[dp_id] = ("battery", lambda v: int(v) if v is not None else None)

            elif code == self.CODE_CLEAN_TIME:
                mult = dp.multiple
                mapping[dp_id] = ("clean_time_min",
                                 lambda v, m=mult: v // m if v is not None else None)

            elif code == self.CODE_CLEAN_AREA:
                mult = dp.multiple
                mapping[dp_id] = ("clean_area_m2",
                                 lambda v, m=mult: v / m if v is not None else None)

            elif code == self.CODE_STATUS:
                mapping[dp_id] = ("status", lambda v: int(v) if v is not None else None)

            elif code == self.CODE_MODE:
                mapping[dp_id] = ("mode", lambda v: int(v) if v is not None else None)

            elif code == self.CODE_MALFUNCTION:
                mapping[dp_id] = ("malfunction", lambda v: int(v) if v is not None else None)

            elif code == self.CODE_SWITCH_CHARGE:
                mapping[dp_id] = ("charging", lambda v: v == 2 if v is not None else None)

        self._sensor_mapping = mapping
        return mapping

    def process_dp_for_state(self, dp_id: int, value: Any) -> Optional[Tuple[str, Any]]:
        """
        Process incoming DP for state update.

        Returns:
            (attribute_name, transformed_value) or None
        """
        if value is None:
            _LOGGER.debug("Skipping DP %s: value is None", dp_id)
            return None

        if not self._sensor_mapping:
            self.build_sensor_mapping()

        if dp_id in self._sensor_mapping:
            attr_name, transform = self._sensor_mapping[dp_id]
            try:
                transformed = transform(value)
                return (attr_name, transformed)
            except (TypeError, ValueError) as e:
                _LOGGER.error("Error transforming DP %s with value %s: %s", dp_id, value, e)
            except Exception as e:
                _LOGGER.error("Unexpected error transforming DP %s: %s", dp_id, e)

        return None

    # ----------------------------------------------------------------------
    # Export for encoder and other components
    # ----------------------------------------------------------------------

    def to_encoder_schema(self) -> Dict[int, Dict[str, Any]]:
        """
        Convert data to format expected by NeatsvorEncoder.

        Returns:
            {dp_id: {"code": str, "type": int, "enum": dict}}
        """
        schema = {}
        for dp_id, dp in self._by_id.items():
            schema[dp_id] = {
                "code": dp.code,
                "type": dp.type,
                "enum": dp.enum,
                "type_name": dp.type_name
            }
        return schema

    def get_command_dp_id(self, command_name: str) -> Optional[int]:
        """
        Get DP ID for standard command.

        Args:
            command_name: 'start', 'pause', 'stop', 'return_to_base',
                         'fan', 'water', 'locate'
        """
        # Check cache
        if command_name in self._command_cache:
            return self._command_cache[command_name]

        # Command to code mapping
        command_to_code = {
            'start': self.CODE_SWITCH_CLEAN,
            'pause': self.CODE_SWITCH_CLEAN,
            'stop': self.CODE_SWITCH_CLEAN,
            'return_to_base': self.CODE_SWITCH_CHARGE,
            'fan': self.CODE_FAN,
            'water': self.CODE_WATER_TANK,
            'locate': self.CODE_LOCATE,
        }

        code = command_to_code.get(command_name)
        if code:
            dp_id = self.get_id(code)
            if dp_id:
                self._command_cache[command_name] = dp_id
                return dp_id

        return None

    # ----------------------------------------------------------------------
    # Debugging and representation
    # ----------------------------------------------------------------------

    def dump(self) -> str:
        """Return string representation of all DP."""
        lines = [f"DPManager: {len(self)} Data Points"]
        for dp_id in sorted(self._by_id.keys()):
            dp = self._by_id[dp_id]
            enum_info = f", enum={len(dp.enum)} vals" if dp.enum else ""
            lines.append(f"  {dp_id:3d} | {dp.code:20} | {dp.type_name:8} | mult={dp.multiple}{enum_info}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"DPManager({len(self)} DPs)"


# ----------------------------------------------------------------------
# Factory functions for convenience
# ----------------------------------------------------------------------

def create_manager_from_api(dp_list: List[Dict]) -> DPManager:
    """
    Create DPManager from list of API responses.

    Args:
        dp_list: List of dictionaries with DP data from REST API

    Returns:
        Populated DPManager
    """
    manager = DPManager()
    manager.load_from_api_list(dp_list)
    return manager


def create_manager_from_schema(schema: Dict[int, Dict]) -> DPManager:
    """
    Create DPManager from ready schema (for backward compatibility).

    Args:
        schema: Dictionary in format {dp_id: {"code": str, "type": int, ...}}

    Returns:
        Populated DPManager
    """
    manager = DPManager()

    for dp_id, info in schema.items():
        # Convert back to format similar to API
        api_like = {
            "dpNum": dp_id,
            "dpCode": info.get("code", f"dp_{dp_id}"),
            "dataType": info.get("type", 3),
        }

        if info.get("enum"):
            # Reverse enum {0: "stop"} → {"stop": 0}
            reverse_enum = {v: k for k, v in info["enum"].items()}
            api_like["dpEnum"] = reverse_enum

        try:
            dp_def = DPDefinition.from_api_dict(api_like)
            manager.add(dp_def)
        except Exception as e:
            _LOGGER.error("Error creating DP from schema: %s", e)

    _LOGGER.info("DPManager created from schema: %s DPs", len(manager))
    return manager