"""Centralized map data processor for Neatsvor."""

import logging
import json
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
import numpy as np

from custom_components.neatsvor.liboshome.map.map_decoder import MapDecoder
from custom_components.neatsvor.liboshome.map.map_renderer import MapRenderer
from custom_components.neatsvor.liboshome.map.async_visualizer import AsyncMapVisualizer

_LOGGER = logging.getLogger(__name__)


@dataclass
class RoomPreset:
    """Preset settings for a room."""
    fan_level: int = 2  # 1-4: quiet, normal, strong, max
    water_level: int = 2  # 1-3: low, middle, high
    clean_times: int = 1
    clean_mode: int = 2  # 0=sweep, 1=mop, 2=sweep_mop 

    def to_dict(self) -> Dict:
        return {
            'fan': self.fan_level,
            'water': self.water_level,
            'times': self.clean_times,
            'mode': self.clean_mode
        }


@dataclass
class RoomInfo:
    """Complete information about a room."""
    id: int
    name: str
    preset: RoomPreset = field(default_factory=RoomPreset)
    area: float = 0.0
    cell_count: int = 0
    coordinates: List[Tuple[int, int]] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'preset': self.preset.to_dict(),
            'area': self.area,
            'cell_count': self.cell_count
        }


@dataclass
class MapMetadata:
    """All metadata extracted from a map."""
    # Basic info
    map_id: Optional[int] = None
    map_type: str = "unknown"  # realtime, cloud, history
    timestamp: datetime = field(default_factory=datetime.now)
    width: int = 0
    height: int = 0
    resolution: int = 0
    area_total: float = 0.0

    # Rooms
    rooms: Dict[int, RoomInfo] = field(default_factory=dict)

    # Positions
    robot_position: Optional[Dict[str, int]] = None
    charger_position: Optional[Dict[str, int]] = None
    robot_angle: Optional[int] = None

    # Paths
    png_path: Optional[str] = None
    json_path: Optional[str] = None
    raw_path: Optional[str] = None

    # Raw protobuf (for advanced access)
    raw_data: Any = None

    @property
    def room_count(self) -> int:
        """Get number of rooms."""
        return len(self.rooms)

    @property
    def room_names(self) -> List[str]:
        """Get list of room names."""
        return [room.name for room in self.rooms.values()]

    @property
    def room_ids(self) -> List[int]:
        """Get list of room IDs."""
        return list(self.rooms.keys())

    @property
    def room_presets(self) -> Dict[int, Dict]:
        """Get presets for all rooms."""
        return {rid: room.preset.to_dict() for rid, room in self.rooms.items()}

    def get_room_by_name(self, name: str) -> Optional[RoomInfo]:
        """Get room by name."""
        for room in self.rooms.values():
            if room.name == name:
                return room
        return None

    def get_room_by_id(self, room_id: int) -> Optional[RoomInfo]:
        """Get room by ID."""
        return self.rooms.get(room_id)

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return {
            'map_id': self.map_id,
            'map_type': self.map_type,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'width': self.width,
            'height': self.height,
            'resolution': self.resolution,
            'area_total': self.area_total,
            'room_count': self.room_count,
            'rooms': [
                {
                    'id': rid,
                    'name': room.name,
                    'preset': room.preset.to_dict(),
                    'area': room.area,
                    'cell_count': room.cell_count
                }
                for rid, room in self.rooms.items()
            ],
            'robot_position': self.robot_position,
            'charger_position': self.charger_position,
            'robot_angle': self.robot_angle,
            'png_path': self.png_path,
            'json_path': self.json_path,
            'raw_path': self.raw_path
        }


class MapProcessor:
    """
    Centralized map processor for all map types.

    Handles:
    - Decoding maps (realtime, cloud, history)
    - Extracting rooms and presets
    - Rendering PNGs
    - Caching metadata
    - Providing unified interface
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize map processor."""
        if storage_dir is None:
            # Default to /config/www/neatsvor/maps
            storage_dir = Path("/config/www/neatsvor/maps")

        self.storage_dir = Path(storage_dir)
        self.renderer = MapRenderer()
        self.visualizer = None  # Don't create AsyncMapVisualizer here, it needs hass

        # Create subdirectories
        self.realtime_dir = self.storage_dir / "realtime"
        self.history_dir = self.storage_dir / "history"
        self.cloud_dir = self.storage_dir / "cloud"
        self.metadata_dir = self.storage_dir / "metadata"

        for dir_path in [self.realtime_dir, self.history_dir,
                        self.cloud_dir, self.metadata_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
            _LOGGER.debug("Created directory: %s", dir_path)

        # Cache for processed maps
        self._cache: Dict[str, MapMetadata] = {}

        _LOGGER.info("MapProcessor initialized with storage: %s", self.storage_dir)

    async def process_realtime_map(self, map_data: Dict[str, Any],
                                   map_id: Optional[int] = None) -> Optional[MapMetadata]:
        """
        Process a realtime map from MQTT.

        Args:
            map_data: Decoded map data from MapDecoder
            map_id: Optional map ID

        Returns:
            MapMetadata with all extracted information or None on error
        """
        _LOGGER.debug("Processing realtime map")

        # Check that map_data is a dictionary
        if not isinstance(map_data, dict):
            _LOGGER.error("map_data is not a dict: %s", type(map_data))
            return None

        try:
            # Extract metadata
            metadata = await self._extract_metadata(map_data, "realtime", map_id)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_realtime"

            # Save PNG
            png_path = await self._save_png(map_data, filename, "realtime")
            if png_path:
                metadata.png_path = str(png_path)

            # Save metadata JSON
            json_path = await self._save_metadata(metadata, filename)
            metadata.json_path = str(json_path)

            # Cache
            cache_key = f"realtime_{metadata.timestamp.timestamp()}"
            self._cache[cache_key] = metadata

            _LOGGER.info("Processed realtime map: %s rooms", metadata.room_count)
            return metadata

        except Exception as e:
            _LOGGER.error("Error processing realtime map: %s", e, exc_info=True)
            return None

    async def process_cloud_map(self, map_data: Dict[str, Any],
                                map_info: Any) -> MapMetadata:
        """
        Process a cloud map.

        Args:
            map_data: Decoded map data from MapDecoder
            map_info: CloudMapInfo object

        Returns:
            MapMetadata with all extracted information
        """
        _LOGGER.debug("Processing cloud map %s", map_info.device_map_id)

        # Extract metadata
        metadata = await self._extract_metadata(map_data, "cloud", map_info.device_map_id)

        # Add cloud-specific info
        metadata.area_total = getattr(map_info, 'area_m2', 0)

        # Generate filename
        safe_name = self._safe_filename(map_info.name)
        filename = f"{map_info.device_map_id}_{safe_name}"

        # Save PNG to public directory
        png_path = self.storage_dir / "cloud" / "png" / f"{filename}.png"
        png_path.parent.mkdir(exist_ok=True)

        await asyncio.to_thread(
            self.renderer.render_map,
            map_data,
            str(png_path),
            show_legend=True
        )
        metadata.png_path = str(png_path)

        # Save metadata JSON
        json_path = await self._save_metadata(metadata, filename)
        metadata.json_path = str(json_path)

        # Cache
        cache_key = f"cloud_{map_info.device_map_id}"
        self._cache[cache_key] = metadata

        _LOGGER.info("Processed cloud map %s: %s rooms", map_info.device_map_id, metadata.room_count)
        return metadata

    async def process_history_map(self, map_data: Dict[str, Any],
                                  record_info: Any) -> MapMetadata:
        """
        Process a history map.

        Args:
            map_data: Decoded map data from MapDecoder
            record_info: CleanRecordInfo object

        Returns:
            MapMetadata with all extracted information
        """
        _LOGGER.debug("Processing history map %s", record_info.record_id)

        # Extract metadata
        metadata = await self._extract_metadata(map_data, "history", record_info.record_id)

        # Generate filename
        clean_time_safe = record_info.clean_time.replace(':', '').replace(' ', '_').replace('-', '')
        filename = f"clean_{record_info.record_id}_{clean_time_safe}"

        # Save PNG
        png_path = await self._save_png(map_data, filename, "history")
        if png_path:
            metadata.png_path = str(png_path)

        # Save metadata JSON
        json_path = await self._save_metadata(metadata, filename)
        metadata.json_path = str(json_path)

        # Cache
        cache_key = f"history_{record_info.record_id}"
        self._cache[cache_key] = metadata

        _LOGGER.info("Processed history map %s: %s rooms", record_info.record_id, metadata.room_count)
        return metadata

    async def _extract_metadata(self, map_data: Dict[str, Any],
                                map_type: str,
                                map_id: Optional[int] = None) -> MapMetadata:
        """
        Extract all metadata from decoded map data.

        This is the core method that extracts:
        - Room names
        - Room presets (from room_attrs)
        - Room areas
        - Positions
        """
        metadata = MapMetadata(
            map_id=map_id,
            map_type=map_type,
            width=map_data.get('width', 0),
            height=map_data.get('height', 0),
            resolution=map_data.get('resolution', 0),
            raw_data=map_data.get('raw')
        )

        # Extract room names
        room_names = map_data.get('room_names', [])
        rooms_dict = map_data.get('rooms', {})

        _LOGGER.debug("Extracting rooms from map_data: %s names, %s room dicts", len(room_names), len(rooms_dict))

        # Try to get room attributes from raw protobuf
        room_attrs = {}
        if metadata.raw_data and hasattr(metadata.raw_data, 'room_info'):
            raw = metadata.raw_data
            _LOGGER.debug("raw.room_info exists: %s", hasattr(raw, 'room_info'))

            if hasattr(raw.room_info, 'room_attrs'):
                _LOGGER.debug("raw.room_info.room_attrs exists, count: %s", len(raw.room_info.room_attrs))
                for attr in raw.room_info.room_attrs:
                    room_attrs[attr.room_id] = RoomPreset(
                        fan_level=attr.fan_level,
                        water_level=attr.tank_level,
                        clean_times=attr.clean_times,
                        clean_mode=attr.clean_mode
                    )
                    _LOGGER.debug("Room %s: fan=%s, water=%s, times=%s", attr.room_id, attr.fan_level, attr.tank_level, attr.clean_times)
            else:
                _LOGGER.debug("raw.room_info.room_attrs not found")
        else:
            _LOGGER.debug("raw_data or room_info not available")

        # Process each room
        for room in room_names:
            room_id = room['id']
            room_name = room['name']

            # Get cell count for area calculation
            cells = rooms_dict.get(room_id, [])
            cell_count = len(cells)

            # Calculate area (each cell is resolution^2 m²)
            # resolution is in mm per pixel, convert to meters
            resolution_m = metadata.resolution / 1000.0 if metadata.resolution else 0.05
            area = cell_count * (resolution_m ** 2)

            # Get preset if available
            preset = room_attrs.get(room_id, RoomPreset())

            metadata.rooms[room_id] = RoomInfo(
                id=room_id,
                name=room_name,
                preset=preset,
                area=area,
                cell_count=cell_count,
                coordinates=cells
            )

            _LOGGER.debug("Room %s: '%s', preset: %s, cells: %s", room_id, room_name, preset.to_dict(), cell_count)

        # Extract positions
        robot_pos = map_data.get('robot_position')
        if robot_pos:
            metadata.robot_position = {
                'x': robot_pos.get('x', 0),
                'y': robot_pos.get('y', 0)
            }
            metadata.robot_angle = robot_pos.get('angle', 0)
            _LOGGER.debug("Robot at (%s, %s), angle: %s", metadata.robot_position['x'], metadata.robot_position['y'], metadata.robot_angle)

        charger_pos = map_data.get('charger_position')
        if charger_pos:
            metadata.charger_position = {
                'x': charger_pos.get('x', 0),
                'y': charger_pos.get('y', 0)
            }
            _LOGGER.debug("Charger at (%s, %s)", metadata.charger_position['x'], metadata.charger_position['y'])

        _LOGGER.info("Extracted %s rooms with presets", len(metadata.rooms))
        return metadata

    async def _save_png(self, map_data: Dict[str, Any],
                        filename: str, map_type: str) -> Optional[Path]:
        """Save PNG using visualizer."""
        try:
            png_path = await self.visualizer.render_static_map(
                map_data,
                title=filename,
                map_type=map_type
            )
            return Path(png_path) if png_path else None
        except Exception as e:
            _LOGGER.error("Error saving PNG: %s", e)
            return None

    async def _save_metadata(self, metadata: MapMetadata,
                            filename: str) -> Optional[Path]:
        """Save metadata to JSON file."""
        try:
            json_path = self.metadata_dir / f"{filename}.json"

            await asyncio.to_thread(
                self._write_json_sync,
                json_path,
                metadata.to_dict()
            )

            _LOGGER.debug("Saved metadata to %s", json_path.name)
            return json_path

        except Exception as e:
            _LOGGER.error("Error saving metadata: %s", e)
            return None

    def _write_json_sync(self, path: Path, data: Dict):
        """Synchronous JSON write (runs in thread)."""
        import json
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _safe_filename(self, name: str) -> str:
        """Convert name to safe filename."""
        import re
        safe = re.sub(r'[<>:"/\\|?*]', '_', name)
        safe = safe.replace(' ', '_')
        if len(safe) > 50:
            safe = safe[:50]
        return safe

    def get_cached_map(self, map_type: str, identifier: Any) -> Optional[MapMetadata]:
        """Get cached map metadata."""
        if map_type == "realtime":
            # For realtime, get the latest
            realtime_maps = [v for k, v in self._cache.items() if k.startswith("realtime_")]
            if realtime_maps:
                return sorted(realtime_maps, key=lambda x: x.timestamp)[-1]
        else:
            cache_key = f"{map_type}_{identifier}"
            return self._cache.get(cache_key)
        return None

    async def load_metadata_from_file(self, json_path: Path) -> Optional[MapMetadata]:
        """Load metadata from JSON file."""
        try:
            data = await asyncio.to_thread(self._load_json_sync, json_path)
            if data:
                metadata = MapMetadata(
                    map_id=data.get('map_id'),
                    map_type=data.get('map_type', 'unknown'),
                    width=data.get('width', 0),
                    height=data.get('height', 0),
                    resolution=data.get('resolution', 0),
                    area_total=data.get('area_total', 0)
                )

                # Restore rooms
                for room_data in data.get('rooms', []):
                    preset = RoomPreset(
                        fan_level=room_data['preset']['fan'],
                        water_level=room_data['preset']['water'],
                        clean_times=room_data['preset']['times'],
                        clean_mode=room_data['preset']['mode']
                    )
                    metadata.rooms[room_data['id']] = RoomInfo(
                        id=room_data['id'],
                        name=room_data['name'],
                        preset=preset,
                        area=room_data.get('area', 0),
                        cell_count=room_data.get('cell_count', 0)
                    )

                # Restore positions
                metadata.robot_position = data.get('robot_position')
                metadata.charger_position = data.get('charger_position')
                metadata.robot_angle = data.get('robot_angle')

                # Restore paths
                metadata.png_path = data.get('png_path')
                metadata.json_path = str(json_path)

                return metadata

        except Exception as e:
            _LOGGER.error("Error loading metadata from %s: %s", json_path, e)

        return None

    def _load_json_sync(self, path: Path) -> Optional[Dict]:
        """Synchronous JSON load (runs in thread)."""
        try:
            import json
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            _LOGGER.error("Error loading JSON: %s", e)
            return None

    def get_public_url(self, metadata: MapMetadata) -> Optional[str]:
        """Get public URL for PNG."""
        if metadata and metadata.png_path:
            png_path = Path(metadata.png_path)
            if png_path.exists():
                # Convert to URL
                relative = png_path.relative_to(Path("/config/www"))
                return f"/local/{relative}"
        return None


# Singleton instance
_processor_instance: Optional[MapProcessor] = None


def get_map_processor() -> MapProcessor:
    """Get or create the global MapProcessor instance."""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = MapProcessor()
    return _processor_instance