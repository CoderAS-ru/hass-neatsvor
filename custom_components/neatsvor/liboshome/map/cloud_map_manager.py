"""Cloud map manager for Neatsvor."""

import logging
import json
import os
import aiofiles
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from custom_components.neatsvor.liboshome.map.map_decoder import MapDecoder
from custom_components.neatsvor.liboshome.map.map_renderer import MapRenderer

_LOGGER = logging.getLogger(__name__)


@dataclass
class CloudMapInfo:
    """Information about a cloud map."""
    device_map_id: int
    map_id: int
    name: str
    area_m2: float
    clean_date: Optional[datetime]
    app_map_url: str
    app_map_md5: str
    dev_map_url: str
    dev_map_md5: str
    downloaded_path: Optional[str] = None
    png_path: Optional[str] = None
    png_url: Optional[str] = None
    room_count: int = 0
    rooms: List[Dict] = None
    width: int = 0
    height: int = 0
    resolution: float = 0.05

    def __post_init__(self):
        if self.rooms is None:
            self.rooms = []


class CloudMapManager:
    """Manager for cloud maps with local caching."""

    def __init__(self, rest_client):
        """Initialize with REST client."""
        self.rest = rest_client
        self.bv_dir = Path("/config/www/neatsvor/maps/cloud/bv")
        self.json_dir = Path("/config/www/neatsvor/maps/cloud/json")
        self.png_dir = Path("/config/www/neatsvor/maps/cloud/png")

        # Create directories if they don't exist
        for dir_path in [self.bv_dir, self.json_dir, self.png_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
            _LOGGER.debug("Created directory: %s", dir_path)

        self.renderer = MapRenderer()
        self._maps_cache: List[CloudMapInfo] = []

    async def get_map_list(self, device_id: int, limit: int = 20) -> List[CloudMapInfo]:
        """Get list of cloud maps from API and merge with local cache."""
        try:
            # Use get_map_list method from async_client.py
            maps_data = await self.rest.get_map_list(device_id, 0, limit)
            _LOGGER.info("Got %s maps from API for device %s", len(maps_data), device_id)

            cloud_maps = []
            for map_data in maps_data:
                # Extract date from map name (format: "S700-2026-01-09")
                clean_date = None
                map_name = map_data.get('name', '')

                # Try to extract date from name
                import re
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', map_name)
                if date_match:
                    try:
                        clean_date = datetime.fromisoformat(date_match.group(1))
                    except:
                        pass

                # Convert estimatedArea from cm² to m²
                estimated_area_cm2 = int(map_data.get('estimated_area_cm2', 0))
                area_m2 = estimated_area_cm2 / 10000

                # Create map info
                map_info = CloudMapInfo(
                    device_map_id=map_data['device_map_id'],
                    map_id=map_data['map_id'],
                    name=map_name,
                    area_m2=area_m2,
                    clean_date=clean_date,
                    app_map_url=map_data.get('app_map_url', ''),
                    app_map_md5=map_data.get('app_map_md5', ''),
                    dev_map_url=map_data.get('dev_map_url', ''),
                    dev_map_md5=map_data.get('dev_map_md5', ''),
                )

                # Check local cache and create metadata if needed
                await self._load_or_create_metadata(map_info)

                cloud_maps.append(map_info)

            self._maps_cache = cloud_maps
            _LOGGER.info("Processed %s maps", len(cloud_maps))

            # Log statistics by rooms
            maps_with_rooms = sum(1 for m in cloud_maps if m.room_count > 0)
            _LOGGER.info("Maps with rooms: %s/%s", maps_with_rooms, len(cloud_maps))

            return cloud_maps

        except Exception as e:
            _LOGGER.error("Error getting cloud maps: %s", e, exc_info=True)
            return []

    async def _load_or_create_metadata(self, map_info: CloudMapInfo):
        """Load metadata from local cache or create if BV exists but JSON doesn't."""
        bv_path = self._get_bv_path(map_info)
        json_path = self._get_json_path(map_info)
        png_path = self._get_png_path(map_info)

        # Check if BV file exists
        if bv_path.exists():
            map_info.downloaded_path = str(bv_path)

            # If JSON exists - load from it
            if json_path.exists():
                try:
                    async with aiofiles.open(json_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        metadata = json.loads(content)
                        map_info.room_count = metadata.get('room_count', 0)
                        map_info.rooms = metadata.get('rooms', [])
                        map_info.width = metadata.get('width', 0)
                        map_info.height = metadata.get('height', 0)
                        map_info.resolution = metadata.get('resolution', 0.05)
                        _LOGGER.debug("Loaded metadata from %s with %s rooms", json_path.name, map_info.room_count)
                except Exception as e:
                    _LOGGER.debug("Could not load metadata: %s", e)

            # If JSON doesn't exist - create it from BV file
            else:
                _LOGGER.info("JSON metadata missing for %s, creating from BV...", map_info.device_map_id)
                try:
                    # Decode BV file
                    map_data = await self._decode_bv_file(bv_path)
                    if map_data:
                        # Extract rooms
                        rooms_info = self._extract_rooms_info(map_data)
                        room_count = len(rooms_info)

                        # Save metadata
                        await self._save_metadata(map_info, map_data, rooms_info, room_count)

                        # Update map_info
                        map_info.room_count = room_count
                        map_info.rooms = rooms_info
                        map_info.width = map_data.get('width', 0)
                        map_info.height = map_data.get('height', 0)

                        _LOGGER.info("Created JSON with %s rooms for map %s", room_count, map_info.device_map_id)
                except Exception as e:
                    _LOGGER.error("Failed to create metadata: %s", e)

        # Check PNG
        if png_path.exists():
            map_info.png_path = str(png_path)
            map_info.png_url = f"/local/neatsvor/maps/cloud/png/{png_path.name}"
            _LOGGER.debug("PNG exists: %s", png_path.name)
        else:
            # If PNG doesn't exist but BV does - generate it
            if bv_path.exists() and not png_path.exists():
                _LOGGER.info("PNG missing for %s, generating...", map_info.device_map_id)
                try:
                    # Use already loaded data or decode again
                    if hasattr(map_info, 'rooms') and map_info.rooms:
                        # Already have rooms, use them
                        map_data = await self._decode_bv_file(bv_path)
                        if map_data:
                            png_path = await self._render_png(map_data, map_info)
                            if png_path:
                                map_info.png_path = str(png_path)
                                map_info.png_url = f"/local/neatsvor/maps/cloud/png/{png_path.name}"
                                _LOGGER.info("Generated PNG: %s", map_info.png_url)
                except Exception as e:
                    _LOGGER.error("Failed to generate PNG: %s", e)

    async def download_map(self, map_info: CloudMapInfo) -> Optional[Dict[str, Any]]:
        """Download and process a cloud map."""
        _LOGGER.info("Downloading map %s: %s", map_info.device_map_id, map_info.name)

        try:
            # Download BV file
            bv_data = await self._download_bv_file(map_info)
            if not bv_data:
                _LOGGER.error("Failed to download BV file")
                return None

            # Save BV file
            bv_path = self._get_bv_path(map_info)
            async with aiofiles.open(bv_path, 'wb') as f:
                await f.write(bv_data)
            _LOGGER.info("Saved BV file: %s", bv_path.name)

            # Decode map data
            map_data = await self._decode_bv_file(bv_path)
            if not map_data:
                _LOGGER.error("Failed to decode map")
                return None

            # Extract room information
            rooms_info = self._extract_rooms_info(map_data)
            room_count = len(rooms_info)
            _LOGGER.info("Found %s rooms in map", room_count)

            # Save metadata to JSON (with rooms)
            json_path = await self._save_metadata(map_info, map_data, rooms_info, room_count)

            # Render PNG directly to public directory
            png_path = await self._render_png(map_data, map_info)

            # Update map info
            map_info.downloaded_path = str(bv_path)
            map_info.room_count = room_count
            map_info.rooms = rooms_info
            map_info.width = map_data.get('width', 0)
            map_info.height = map_data.get('height', 0)
            map_info.resolution = map_data.get('resolution', 0.05)
            if png_path:
                map_info.png_path = str(png_path)
                map_info.png_url = f"/local/neatsvor/maps/cloud/png/{png_path.name}"
                _LOGGER.info("PNG saved to public folder: %s", map_info.png_url)

            return {
                'saved_path': str(png_path) if png_path else None,
                'bv_path': str(bv_path),
                'json_path': str(json_path),
                'png_path': str(png_path) if png_path else None,
                'png_url': map_info.png_url,
                'room_count': room_count,
                'rooms': rooms_info,
                'width': map_data.get('width'),
                'height': map_data.get('height'),
            }

        except Exception as e:
            _LOGGER.error("Error downloading map: %s", e, exc_info=True)
            return None

    def _extract_rooms_info(self, map_data: Dict) -> List[Dict]:
        """Extract room information from decoded map data."""
        rooms = []

        # Log map_data structure for debugging
        _LOGGER.debug("Map data keys: %s", map_data.keys())

        # Try to get room names from the map data
        room_names = map_data.get('room_names', [])
        if room_names:
            _LOGGER.debug("Found room_names: %s", room_names)
            for room in room_names:
                room_id = room.get('id')
                room_name = room.get('name')
                _LOGGER.debug("Processing room: id=%s, name=%s", room_id, room_name)
                rooms.append({
                    'id': room_id,
                    'name': room_name if room_name else f"Room {room_id}"
                })

        # If we have rooms dict but no names, create generic names
        rooms_dict = map_data.get('rooms', {})
        if rooms_dict and not rooms:
            _LOGGER.debug("Found rooms dict with %s entries", len(rooms_dict))
            for room_id in rooms_dict.keys():
                rooms.append({
                    'id': room_id,
                    'name': f"Room {room_id}"
                })

        # Check for segments (alternative format)
        segments = map_data.get('segments', [])
        if segments and not rooms:
            _LOGGER.debug("Found segments: %s", len(segments))
            for segment in segments:
                if segment.get('type') == 'room':
                    rooms.append({
                        'id': segment.get('id'),
                        'name': segment.get('name', f"Room {segment.get('id')}")
                    })

        # Sort by ID
        rooms.sort(key=lambda x: x['id'])

        _LOGGER.info("Extracted %s rooms from map data", len(rooms))
        return rooms

    async def _download_bv_file(self, map_info: CloudMapInfo) -> Optional[bytes]:
        """Download BV file from URL."""
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(map_info.app_map_url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        _LOGGER.debug("Downloaded %s bytes", len(data))
                        return data
                    else:
                        _LOGGER.error("HTTP %s from %s", resp.status, map_info.app_map_url)
                        return None
        except Exception as e:
            _LOGGER.error("Download error: %s", e)
            return None

    async def _decode_bv_file(self, bv_path: Path) -> Optional[Dict[str, Any]]:
        """Decode BV file using MapDecoder."""
        try:
            # Use synchronous decoder in thread pool
            import asyncio
            _LOGGER.debug("Decoding BV file: %s", bv_path)
            map_data = await asyncio.to_thread(
                MapDecoder.decode_app_map,
                str(bv_path)
            )
            _LOGGER.debug("Decoded map: %sx%s", map_data.get('width'), map_data.get('height'))
            return map_data
        except Exception as e:
            _LOGGER.error("Decode error: %s", e)
            return None

    async def _save_metadata(self, map_info: CloudMapInfo, map_data: Dict, rooms: List[Dict], room_count: int) -> Path:
        """Save map metadata to JSON file including room information."""
        metadata = {
            'device_map_id': map_info.device_map_id,
            'map_id': map_info.map_id,
            'name': map_info.name,
            'area_m2': map_info.area_m2,
            'clean_date': map_info.clean_date.isoformat() if map_info.clean_date else None,
            'room_count': room_count,
            'rooms': rooms,
            'width': map_data.get('width'),
            'height': map_data.get('height'),
            'resolution': map_data.get('resolution', 0.05),
            'downloaded_at': datetime.now().isoformat(),
            'app_map_url': map_info.app_map_url,
            'app_map_md5': map_info.app_map_md5,
            'dev_map_url': map_info.dev_map_url,
            'dev_map_md5': map_info.dev_map_md5,
        }

        json_path = self._get_json_path(map_info)

        # Create directory if needed
        json_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(json_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(metadata, indent=2, ensure_ascii=False))

        _LOGGER.info("Saved metadata with %s rooms: %s", room_count, json_path.name)

        # For debugging - show first few rooms
        if rooms:
            sample = rooms[:3]
            _LOGGER.debug("Sample rooms: %s", sample)

        return json_path

    async def _render_png(self, map_data: Dict, map_info: CloudMapInfo) -> Optional[Path]:
        """Render map to PNG using MapRenderer and save directly to public directory."""
        try:
            png_path = self._get_png_path(map_info)

            # Create directory if needed
            png_path.parent.mkdir(parents=True, exist_ok=True)

            # Use synchronous renderer in thread pool
            import asyncio
            await asyncio.to_thread(
                self.renderer.render_map,
                map_data,
                str(png_path),
                show_legend=True
            )

            if png_path.exists():
                _LOGGER.info("Rendered PNG: %s", png_path)
                return png_path
            else:
                _LOGGER.error("PNG file was not created at %s", png_path)
                return None

        except Exception as e:
            _LOGGER.error("Render error: %s", e, exc_info=True)
            return None

    def _get_bv_path(self, map_info: CloudMapInfo) -> Path:
        """Get path for BV file."""
        safe_name = self._safe_filename(map_info.name)
        return self.bv_dir / f"{map_info.device_map_id}_{safe_name}.bv"

    def _get_json_path(self, map_info: CloudMapInfo) -> Path:
        """Get path for JSON metadata."""
        safe_name = self._safe_filename(map_info.name)
        return self.json_dir / f"{map_info.device_map_id}_{safe_name}.json"

    def _get_png_path(self, map_info: CloudMapInfo) -> Path:
        """Get path for PNG image in public directory."""
        safe_name = self._safe_filename(map_info.name)
        return self.png_dir / f"{map_info.device_map_id}_{safe_name}.png"

    def _safe_filename(self, name: str) -> str:
        """Convert map name to safe filename."""
        import re
        safe = re.sub(r'[<>:"/\\|?*]', '_', name)
        safe = safe.replace(' ', '_')
        if len(safe) > 50:
            safe = safe[:50]
        return safe

    def get_png_url(self, map_info: CloudMapInfo) -> Optional[str]:
        """Get public URL for PNG file."""
        return map_info.png_url

    async def get_map_data(self, map_info: CloudMapInfo) -> Optional[Dict]:
        """Get decoded map data, downloading if necessary."""
        bv_path = self._get_bv_path(map_info)

        if not bv_path.exists():
            _LOGGER.info("Map not cached, downloading: %s", map_info.device_map_id)
            result = await self.download_map(map_info)
            if not result:
                return None

        # Decode the map
        try:
            return await self._decode_bv_file(bv_path)
        except Exception as e:
            _LOGGER.error("Error decoding map: %s", e)
            return None

    async def get_png_path(self, map_info: CloudMapInfo) -> Optional[Path]:
        """Get PNG path, generating if necessary."""
        png_path = self._get_png_path(map_info)

        if png_path.exists():
            return png_path

        # Need to generate PNG
        map_data = await self.get_map_data(map_info)
        if map_data:
            return await self._render_png(map_data, map_info)

        return None

    async def get_rooms_info(self, map_info: CloudMapInfo) -> List[Dict]:
        """Get room information for a map."""
        # First check if we already have it in memory
        if map_info.rooms:
            return map_info.rooms

        # Try to load from JSON
        json_path = self._get_json_path(map_info)
        if json_path.exists():
            try:
                async with aiofiles.open(json_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    metadata = json.loads(content)
                    rooms = metadata.get('rooms', [])
                    map_info.rooms = rooms
                    map_info.room_count = len(rooms)
                    _LOGGER.debug("Loaded %s rooms from JSON for map %s", len(rooms), map_info.device_map_id)
                    return rooms
            except Exception as e:
                _LOGGER.error("Error loading rooms from JSON: %s", e)

        # If not, download the map
        _LOGGER.info("Downloading map to get rooms: %s", map_info.device_map_id)
        result = await self.download_map(map_info)
        if result:
            return result.get('rooms', [])

        return []