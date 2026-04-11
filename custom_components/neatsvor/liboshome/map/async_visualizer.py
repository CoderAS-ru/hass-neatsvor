"""
Asynchronous map visualizer.
Saves all maps to structured folders.
"""

import time
import asyncio
from pathlib import Path
import os
import platform
import subprocess
from typing import Dict, Any, Optional
import logging

from .map_renderer import MapRenderer

_LOGGER = logging.getLogger(__name__)


class AsyncMapVisualizer:
    """Asynchronous map visualizer with file-based storage."""

    # Map types and corresponding subfolders
    MAP_TYPES = {
        'realtime': 'realtime',
        'history': 'history',
        'cloud': 'cloud'
    }

    def __init__(self, hass=None, base_dir: Optional[str] = None):
        """
        Initialize visualizer.

        Args:
            hass: Home Assistant instance (optional)
            base_dir: Base directory for maps
        """
        self.hass = hass
        self._counter = 0

        # IMPORTANT: Always use /config/www/neatsvor/maps/ as base folder
        if base_dir is None:
            # Fixed path for all cases
            base_dir = "/config/www/neatsvor/maps"

        self.base_dir = Path(base_dir)
        self._map_renderer = MapRenderer()

        # Create all necessary subdirectories
        self._create_directories()

        _LOGGER.info("Visualizer initialized. Base folder: %s", self.base_dir)

    def _create_directories(self):
        """Create folder structure for maps."""
        for subdir in self.MAP_TYPES.values():
            path = self.base_dir / subdir
            path.mkdir(exist_ok=True, parents=True)
            _LOGGER.debug("Created folder: %s", path)

    def _get_map_path(self, map_type: str, filename: str) -> Path:
        """
        Return full path for saving map.

        Args:
            map_type: Map type ('realtime', 'history', 'cloud')
            filename: File name (without path)

        Returns:
            Path object with full path
        """
        subdir = self.MAP_TYPES.get(map_type, 'other')
        return self.base_dir / subdir / filename

    async def render_static_map(self, map_data: Dict[str, Any],
                               title: str = "map",
                               map_type: str = "cloud") -> Optional[str]:
        """Render static map to file."""
        _LOGGER.info("render_static_map: title=%s, map_type=%s", title, map_type)
        
        try:
            loop = asyncio.get_event_loop()
            
            # Запускаем рендер
            filename = await loop.run_in_executor(
                None,
                self._render_sync,
                map_data,
                title,
                map_type
            )
            
            # Ждём появления файла на диске
            if filename:
                path = Path(filename)
                for _ in range(20):  # Максимум 2 секунды ожидания
                    if path.exists() and path.stat().st_size > 0:
                        _LOGGER.info("File created: %s (%s bytes)", filename, path.stat().st_size)
                        return str(filename)
                    await asyncio.sleep(0.1)
                
                _LOGGER.warning("File not found after render: %s", filename)
                return None
            else:
                return None
                
        except Exception as e:
            _LOGGER.error("Error rendering map: %s", e, exc_info=True)
            return None

    def _render_sync(self, map_data: Dict[str, Any],
                    title: str, map_type: str) -> Path:
        """Synchronous rendering (executed in executor)."""
        # Clean title from invalid characters
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
        safe_title = safe_title[:50]

        # For history maps use title as filename (without timestamp)
        if map_type == "history":
            # Remove possible timestamps from title
            if '_' in safe_title and safe_title.split('_')[0].isdigit() and len(safe_title.split('_')[0]) == 8:
                # This is timestamp like YYYYMMDD, keep as is
                filename = f"{safe_title}.png"
            else:
                filename = f"{safe_title}.png"
        else:
            # For realtime and cloud add timestamp
            timestamp = self._get_timestamp()
            filename = f"{timestamp}_{safe_title}.png"

        # Get full path
        filepath = self._get_map_path(map_type, filename)

        # Create parent directory if it doesn't exist
        filepath.parent.mkdir(exist_ok=True, parents=True)

        # Render map
        self._map_renderer.render_map(
            map_data,
            output_file=str(filepath),
            show_legend=True,
            root_window=None
        )

        self._counter += 1
        return filepath

    async def render_realtime_frame(self, map_data: Dict[str, Any],
                                   robot_pos: Optional[Dict] = None) -> Optional[str]:
        """Render one frame of dynamic map."""
        try:
            if robot_pos:
                _LOGGER.debug("Frame %s: robot x=%s, y=%s", self._counter, robot_pos.get('x'), robot_pos.get('y'))

            filename = await self.render_static_map(
                map_data,
                title=f"realtime_{self._counter:06d}",
                map_type="realtime"
            )

            return filename

        except Exception as e:
            _LOGGER.error("Error rendering frame: %s", e)
            return None

    def _get_timestamp(self) -> str:
        """Return timestamp for filename."""
        from datetime import datetime
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    async def _auto_open_file(self, filepath: Path) -> None:
        """Automatically open file in viewer."""
        if not filepath.exists():
            return

        try:
            system = platform.system()

            if system == "Windows":
                os.startfile(filepath)
            elif system == "Darwin":
                subprocess.run(["open", str(filepath)], check=False)
            else:
                subprocess.run(["xdg-open", str(filepath)], check=False)

            _LOGGER.debug("File opened: %s", filepath)
        except Exception as e:
            _LOGGER.debug("Failed to open file: %s", e)

    def get_stats(self) -> Dict[str, Any]:
        """Return statistics about saved maps."""
        stats = {
            'base_dir': str(self.base_dir),
            'counter': self._counter,
            'directories': {}
        }

        for name, subdir in self.MAP_TYPES.items():
            path = self.base_dir / subdir
            if path.exists():
                files = list(path.glob('*.png'))
                stats['directories'][name] = {
                    'path': str(path),
                    'count': len(files)
                }

        return stats

    async def cleanup_realtime_maps(self, keep_last: int = 10):
        """Clean up old realtime maps and corresponding metadata, keep only last N."""
        try:
            realtime_dir = self.base_dir / "realtime"
            metadata_dir = self.base_dir / "metadata"

            if not realtime_dir.exists():
                return

            # Get all PNG files, sort by modification time
            png_files = sorted(realtime_dir.glob("*.png"), key=os.path.getmtime)
            json_files = sorted(metadata_dir.glob("*.json"), key=os.path.getmtime) if metadata_dir.exists() else []

            # Create mapping of PNG -> JSON
            png_to_json = {}
            for png in png_files:
                stem = png.stem
                possible_jsons = [
                    metadata_dir / f"{stem}.json",
                    metadata_dir / f"{stem.replace('_live', '')}.json",
                    metadata_dir / f"{stem.replace('_realtime', '')}.json",
                    metadata_dir / f"{stem.split('_map_')[0]}_realtime.json" if '_map_' in stem else None,
                ]

                for json_path in possible_jsons:
                    if json_path and json_path.exists():
                        png_to_json[png] = json_path
                        break

            # If there are more files than needed - delete old ones
            if len(png_files) > keep_last:
                files_to_keep = set(png_files[-keep_last:])

                # Delete old PNGs
                for png in png_files[:-keep_last]:
                    png.unlink()
                    _LOGGER.debug("Deleted old map: %s", png.name)

                    # Delete corresponding JSON if exists
                    if png in png_to_json:
                        json_path = png_to_json[png]
                        if json_path.exists():
                            json_path.unlink()
                            _LOGGER.debug("Deleted metadata: %s", json_path.name)

                # Also check JSON files without corresponding PNGs
                if metadata_dir.exists():
                    for json_path in json_files:
                        # Check if there is a corresponding PNG
                        has_png = False
                        for png in files_to_keep:
                            if json_path.stem in png.stem:
                                has_png = True
                                break

                        if not has_png and json_path not in png_to_json.values():
                            # Check file age
                            file_age = time.time() - os.path.getmtime(json_path)
                            if file_age > 3600:  # Older than hour
                                json_path.unlink()
                                _LOGGER.debug("Deleted old metadata without map: %s", json_path.name)

                _LOGGER.info("Real-time cleanup: deleted %s PNGs and corresponding JSON, kept %s", len(png_files[:-keep_last]), keep_last)

            # Additional cleanup of very old files (over 24 hours)
            self._cleanup_old_files(realtime_dir, metadata_dir, max_age_hours=24)

        except Exception as e:
            _LOGGER.error("Error cleaning realtime maps: %s", e)

    def _cleanup_old_files(self, realtime_dir: Path, metadata_dir: Path, max_age_hours: int = 24):
        """Delete files older than max_age_h hours."""
        try:
            import time
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600

            # Clean PNGs
            for png in realtime_dir.glob("*.png"):
                file_age = current_time - os.path.getmtime(png)
                if file_age > max_age_seconds:
                    png.unlink()
                    _LOGGER.debug("Deleted very old map (>%sh): %s", max_age_hours, png.name)

            # Clean JSONs
            if metadata_dir.exists():
                for json_path in metadata_dir.glob("*.json"):
                    file_age = current_time - os.path.getmtime(json_path)
                    if file_age > max_age_seconds:
                        json_path.unlink()
                        _LOGGER.debug("Deleted very old metadata (>%sh): %s", max_age_hours, json_path.name)

        except Exception as e:
            _LOGGER.error("Error cleaning old files: %s", e)