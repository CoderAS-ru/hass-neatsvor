"""Clean history manager for Neatsvor."""

import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


@dataclass
class CleanRecordInfo:
    """Cleaning record information from history."""
    record_id: int
    clean_time: str
    clean_area_raw: int  # Raw value from API (×10 for m²)
    clean_length: int    # seconds
    record_url: str
    finished: bool

    @property
    def clean_area(self) -> float:
        """Cleaning area in m² (for compatibility with old code)."""
        return self.clean_area_raw * 0.1  # ×0.1 for m²

    @property
    def area_m2(self) -> float:
        """Area in square meters (new property)."""
        return self.clean_area_raw * 0.1

    @property
    def duration_minutes(self) -> int:
        """Cleaning duration in minutes."""
        return self.clean_length // 60

    @property
    def status_icon(self) -> str:
        """Status icon for the cleaning record."""
        return "[OK]" if self.finished else "[STOPPED]"


class CleanHistoryManager:
    """Manager for cleaning history and their maps."""

    def __init__(self, rest_client):
        """Initialize with REST client."""
        self.rest = rest_client
        self.current_record_data: Optional[Dict] = None
        self.current_map_data: Optional[Dict] = None
        self._visualizer = None  # Will be set later

    def set_visualizer(self, visualizer):
        """Set visualizer for saving PNG."""
        self._visualizer = visualizer

    async def get_clean_history(self, device_id: int, limit: int = 20) -> List[CleanRecordInfo]:
        """Get cleaning history (asynchronous)."""
        raw_records = await self.rest.get_clean_records(device_id, 0, limit)

        records = []
        for item in raw_records:
            try:
                record = CleanRecordInfo(
                    record_id=item.get('recordId', 0),
                    clean_time=item.get('cleanTime', 'N/A'),
                    clean_area_raw=item.get('cleanArea', 0),
                    clean_length=item.get('cleanLength', 0),
                    record_url=item.get('recordUrl', ''),
                    finished=item.get('cleanFinishedFlag', False)
                )

                if record.record_id > 0:
                    records.append(record)

            except Exception as e:
                _LOGGER.error("Error parsing cleaning record: %s", e)

        return records

    async def load_clean_record_map(self, record: CleanRecordInfo) -> Optional[Dict]:
        """Load and decode cleaning record map (asynchronous)."""
        _LOGGER.info("load_clean_record_map: record_id=%s, url=%s", record.record_id, record.record_url)

        if not record.record_url:
            _LOGGER.error("No URL for record %s", record.record_id)
            return None

        _LOGGER.info("Downloading data from URL: %s", record.record_url)
        gzip_data = await self.rest.get_clean_record_data(record.record_url)

        if not gzip_data:
            _LOGGER.error("Failed to download map for record %s", record.record_id)
            return None

        _LOGGER.info("Received %s bytes of data", len(gzip_data))

        _LOGGER.info("Decoding map...")
        map_data = await self.rest.decode_clean_map_data(gzip_data)

        if map_data:
            self.current_map_data = map_data

            map_data['clean_info'] = {
                'record_id': record.record_id,
                'clean_time': record.clean_time,
                'clean_area_m2': record.clean_area,
                'clean_length_min': record.duration_minutes,
                'finished': record.finished,
                'record_url': record.record_url
            }

            _LOGGER.info("Cleaning map %s loaded: %sx%s", record.record_id, map_data.get('width', 0), map_data.get('height', 0))
            _LOGGER.info("Rooms in map: %s", len(map_data.get('room_names', [])))

            # Automatically save PNG if visualizer is available
            if self._visualizer:
                _LOGGER.info("Visualizer available, saving PNG...")
                saved_path = await self._save_map_png(record, map_data)
                if saved_path:
                    _LOGGER.info("PNG saved: %s", saved_path)
                else:
                    _LOGGER.error("Failed to save PNG")
            else:
                _LOGGER.warning("Visualizer not set, PNG not saved")

            return map_data
        else:
            _LOGGER.error("Failed to decode map for record %s", record.record_id)
            return None

    async def _save_map_png(self, record: CleanRecordInfo, map_data: Dict) -> Optional[str]:
        """Save map as PNG using visualizer - format: cleanTime_recordId.png"""
        try:
            _LOGGER.info("_save_map_png: record_id=%s", record.record_id)

            if not self._visualizer:
                _LOGGER.error("Visualizer not set")
                return None

            # Clean clean_time from invalid characters
            import re
            clean_time = record.clean_time
            clean_time = clean_time.replace(' ', '_').replace(':', '')
            clean_time = re.sub(r'[^\w\-_]', '', clean_time)

            # Format filename: cleanTime_recordId
            filename = f"{clean_time}_{record.record_id}"
            _LOGGER.info("Filename: %s", filename)

            # Check map_data structure
            _LOGGER.info("map_data keys: %s", map_data.keys())
            _LOGGER.info("Size: %sx%s", map_data.get('width'), map_data.get('height'))

            png_path = await self._visualizer.render_static_map(
                map_data,
                title=filename,
                map_type="history"
            )

            if png_path:
                _LOGGER.info("History map saved: %s", png_path)
                # Check if file exists
                from pathlib import Path
                path = Path(png_path)
                if path.exists():
                    _LOGGER.info("File exists, size: %s bytes", path.stat().st_size)

                    # Check if filename matches our format
                    expected_name = f"{filename}.png"
                    if path.name != expected_name:
                        _LOGGER.warning("Filename mismatch: got %s, expected %s", path.name, expected_name)
                        # If visualizer added timestamp, rename
                        correct_path = path.parent / expected_name
                        if correct_path.exists():
                            correct_path.unlink()
                        path.rename(correct_path)
                        _LOGGER.info("Renamed to: %s", correct_path)
                        return str(correct_path)

                    return png_path
                else:
                    _LOGGER.error("File not found after saving: %s", png_path)
                    return None
            else:
                _LOGGER.error("render_static_map returned None")
                return None

        except Exception as e:
            _LOGGER.error("Error saving PNG: %s", e, exc_info=True)
            return None

    async def visualize_clean_record_map(self, record: CleanRecordInfo) -> Optional[str]:
        """Visualize cleaning record map (for backward compatibility)."""
        map_data = await self.load_clean_record_map(record)

        if not map_data:
            return None

        # If visualizer already saved PNG during load, just return the path
        if hasattr(self, '_last_saved_path') and self._last_saved_path:
            return self._last_saved_path

        return None

    async def process_clean_record_map(self, record: CleanRecordInfo) -> Optional[str]:
        """Process and save cleaning record map."""
        _LOGGER.info("Processing cleaning: %s", record.clean_time)
        _LOGGER.info("Area: %s m², Duration: %s min", record.clean_area, record.duration_minutes)
        _LOGGER.info("Status: %s", 'Finished' if record.finished else 'Interrupted')

        map_data = await self.load_clean_record_map(record)

        if not map_data:
            _LOGGER.error("Failed to load cleaning map")
            return None

        try:
            from custom_components.neatsvor.liboshome.map.async_visualizer import AsyncMapVisualizer

            # Visualizer will use liboshome/maps/history/
            visualizer = AsyncMapVisualizer()

            # Create readable filename
            clean_time_safe = record.clean_time.replace(':', '').replace(' ', '_').replace('-', '')
            filename = f"clean_{record.record_id}_{clean_time_safe}"

            saved_path = await visualizer.render_static_map(
                map_data,
                title=filename,
                map_type="history"
            )

            if saved_path:
                _LOGGER.info("Cleaning map saved: %s", saved_path)
                _LOGGER.info("Map info: %sx%s", map_data.get('width', 0), map_data.get('height', 0))
                _LOGGER.info("Rooms: %s", len(map_data.get('rooms', {})))
                return saved_path
            else:
                _LOGGER.error("Error saving map")
                return None

        except Exception as e:
            _LOGGER.error("Visualization error: %s", e)
            return None