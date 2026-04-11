"""Device state management for Neatsvor."""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

_LOGGER = logging.getLogger(__name__)


class DeviceState:
    """Device state container."""

    def __init__(self):
        self.status = None
        self.battery = None
        self.clean_area = None
        self.clean_time = None
        self.charging = None
        self.clean_start_time = None
        self.sensors = NeatsvorSensors()
        self.last_update = None
        self.dp_values: Dict[int, Any] = {}  # Raw DP values

    def update(self, key, value):
        """Update a state attribute."""
        setattr(self, key, value)
        self.last_update = datetime.now()

    def update_dp(self, dp_id: int, value: Any):
        """Update a specific DP value."""
        self.dp_values[dp_id] = value
        self.last_update = datetime.now()

    def __repr__(self):
        return f"<DeviceState battery={self.battery}>"


@dataclass
class NeatsvorSensors:
    """All device sensors (dynamic, from DP schema)."""

    # Core sensors (common to all models)
    battery: Optional[int] = None
    charging: Optional[bool] = None
    online: Optional[bool] = None
    clean_time_min: Optional[int] = None
    clean_area_m2: Optional[float] = None
    status_code: Optional[int] = None  # Raw code from DP 5
    status_text: Optional[str] = None  # Text representation
    mode: Optional[int] = None
    malfunction_code: Optional[int] = None
    malfunction_text: Optional[str] = None

    # Model-specific sensors (filled from DP)
    fan_speed: Optional[str] = None  # quiet, normal, strong, max
    fan_speed_code: Optional[int] = None  # 0-4
    water_level: Optional[str] = None  # low, middle, high
    water_level_code: Optional[int] = None  # 0-3
    clean_mode: Optional[str] = None  # sweep, mop, sweepMop

    # Storage for all DP values in text form
    dp_text: Dict[int, str] = field(default_factory=dict)

    # REST sensors
    software_version: str = "Unknown"
    proto_version: Optional[str] = None
    mac_address: Optional[str] = None
    device_pid: Optional[str] = None
    device_model: Optional[str] = None

    # Consumables (from REST)
    consumables: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Cleaning statistics (from REST)
    total_cleanings: int = 0
    total_clean_time_hours: float = 0
    total_clean_area_m2: float = 0

    # Last cleaning
    last_clean_time: Optional[datetime] = None
    last_clean_duration_min: int = 0
    last_clean_area_m2: float = 0
    last_clean_finished: bool = False

    def update_from_dp(self, dp_id: int, value: Any, dp_manager):
        """
        Update state based on received DP.
        Uses DPManager for transformation.
        """
        self.dp_text[dp_id] = str(value)

        # Get DP definition
        dp_def = dp_manager.get_by_id(dp_id)
        if not dp_def:
            return

        code = dp_def.code
        _LOGGER.debug("Processing DP %s (%s) = %s (type: %s)", dp_id, code, value, type(value).__name__)

        # Process specific DPs
        if code == 'battery_percentage':
            self.battery = int(value) if value is not None else None
        elif code == 'clean_time':
            mult = getattr(dp_def, 'multiple', 60)
            if value is not None:
                try:
                    num_value = int(value)
                    self.clean_time_min = num_value // mult
                except (ValueError, TypeError) as e:
                    _LOGGER.error("Error parsing clean_time: %s", e)
                    self.clean_time_min = None
            else:
                self.clean_time_min = None
        elif code == 'clean_area':
            mult = getattr(dp_def, 'multiple', 10)
            if value is not None:
                try:
                    num_value = int(value)
                    self.clean_area_m2 = num_value / mult
                except (ValueError, TypeError) as e:
                    _LOGGER.error("Error parsing clean_area: %s", e)
                    self.clean_area_m2 = None
            else:
                self.clean_area_m2 = None
        elif code == 'status':
            self.status_code = int(value) if value is not None else None
            if dp_def.enum and value in dp_def.enum:
                self.status_text = dp_def.enum[value]
        elif code == 'fan':
            self.fan_speed_code = int(value) if value is not None else None
            if dp_def.enum and value in dp_def.enum:
                self.fan_speed = dp_def.enum[value]
        elif code == 'water_tank':
            self.water_level_code = int(value) if value is not None else None
            if dp_def.enum and value in dp_def.enum:
                self.water_level = dp_def.enum[value]
        elif code == 'clean_mode':
            self.clean_mode = dp_def.get_enum_text(value) if dp_def.enum else str(value)
        elif code == 'malfunction':
            self.malfunction_code = int(value) if value is not None else None
            if dp_def.enum and value in dp_def.enum:
                self.malfunction_text = dp_def.enum[value]
            else:
                self.malfunction_text = None
        elif code == 'switch_charge':
            self.charging = (value == 2) if value is not None else None

    def update_consumables(self, consume_data: list, total_work_hours: float = 0):
        """Update consumables from REST API."""
        self.consumables.clear()
        _LOGGER.debug("Updating consumables with %s items, total_hours=%s", len(consume_data), total_work_hours)

        for item in consume_data:
            consume_id = item.get("consumeId")
            if not consume_id:
                continue

            limit_seconds = item.get("totalTime", 0)
            limit_hours = limit_seconds / 3600 if limit_seconds else 0

            remaining_percent = 100
            remaining_hours = 0

            if limit_hours > 0 and total_work_hours is not None:
                remaining_hours = max(0, limit_hours - total_work_hours)
                remaining_percent = (remaining_hours / limit_hours) * 100

            # Determine consumable type by name
            name = item.get("consumeName", "").lower()
            
            # Map Russian/English names to standard keys
            if "hepa" in name or "фильтр" in name or "filter" in name:
                cons_type = "filter"
            elif "side" in name or "боков" in name or ("щетка" in name and "боков" not in name and "турбо" not in name):
                cons_type = "side_brush"
            elif "main" in name or "roller" in name or "турбо" in name:
                cons_type = "main_brush"
            else:
                cons_type = f"consume_{consume_id}"

            self.consumables[cons_type] = {
                "id": consume_id,
                "name": item.get("consumeName", "Unknown"),
                "remaining_percent": round(remaining_percent, 1),
                "remaining_hours": round(remaining_hours, 1),
                "limit_hours": round(limit_hours, 1),
                "original_id": cons_type
            }
            _LOGGER.debug("Added %s: %s%% (%s/%s hours)", cons_type, remaining_percent, remaining_hours, limit_hours)

    def get_consumable(self, cons_type: str) -> Optional[Dict]:
        """Get consumable by type."""
        return self.consumables.get(cons_type)