"""Cloud map manager for Neatsvor."""

import logging
import json
import aiofiles
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from custom_components.neatsvor.liboshome.map.map_decoder import MapDecoder
from custom_components.neatsvor.liboshome.map.map_renderer import MapRenderer
from .map_cache import get_map_cache

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
    """Manager for cloud maps with lazy loading and on-demand PNG generation."""

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
        self._processing_tasks: Dict[int, asyncio.Task] = {}

    async def get_map_list(self, device_id: int, limit: int = 10) -> List[CloudMapInfo]:
        """Get list of cloud maps from API (lazy loading - no metadata processing)."""
        try:
            maps_data = await self.rest.get_map_list(device_id, 0, limit)
            _LOGGER.info("Got %s maps from API for device %s", len(maps_data), device_id)

            cloud_maps = []
            for map_data in maps_data:
                # Extract date from map name
                clean_date = self._extract_date(map_data.get('name', ''))
                
                # Convert estimatedArea from cm² to m²
                estimated_area_cm2 = int(map_data.get('estimated_area_cm2', 0))
                area_m2 = estimated_area_cm2 / 10000

                # Create map info with minimal data (no metadata loading)
                map_info = CloudMapInfo(
                    device_map_id=map_data['device_map_id'],
                    map_id=map_data['map_id'],
                    name=map_data.get('name', ''),
                    area_m2=area_m2,
                    clean_date=clean_date,
                    app_map_url=map_data.get('app_map_url', ''),
                    app_map_md5=map_data.get('app_map_md5', ''),
                    dev_map_url=map_data.get('dev_map_url', ''),
                    dev_map_md5=map_data.get('dev_map_md5', ''),
                )
                
                # Check if PNG already exists (fast check)
                png_path = self._get_png_path(map_info)
                if png_path.exists():
                    map_info.png_path = str(png_path)
                    map_info.png_url = f"/local/neatsvor/maps/cloud/png/{png_path.name}"
                    
                    # Try to load cached metadata
                    await self._load_cached_metadata(map_info)
                
                cloud_maps.append(map_info)

            self._maps_cache = cloud_maps
            _LOGGER.info("Created %s map entries (metadata lazy-loaded)", len(cloud_maps))

            return cloud_maps

        except Exception as e:
            _LOGGER.error("Error getting cloud maps: %s", e, exc_info=True)
            return []

    def _extract_date(self, name: str) -> Optional[datetime]:
        """Extract date from map name."""
        import re
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', name)
        if date_match:
            try:
                return datetime.fromisoformat(date_match.group(1))
            except:
                pass
        return None

    async def _load_cached_metadata(self, map_info: CloudMapInfo):
        """Load metadata from cache or JSON file if exists."""
        cache = get_map_cache()
        cache_key = f"cloud_meta_{map_info.device_map_id}"
        
        # Check memory cache first
        cached_meta = cache.get_metadata(cache_key)
        if cached_meta:
            map_info.room_count = cached_meta.get('room_count', 0)
            map_info.rooms = cached_meta.get('rooms', [])
            map_info.width = cached_meta.get('width', 0)
            map_info.height = cached_meta.get('height', 0)
            return
        
        # Try to load from JSON file
        json_path = self._get_json_path(map_info)
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
                    
                    # Save to memory cache
                    cache.set_metadata(cache_key, {
                        'room_count': map_info.room_count,
                        'rooms': map_info.rooms,
                        'width': map_info.width,
                        'height': map_info.height,
                    })
                    _LOGGER.debug("Loaded metadata from JSON for map %s", map_info.device_map_id)
            except Exception as e:
                _LOGGER.debug("Could not load metadata JSON: %s", e)

    async def ensure_png_exists(self, map_info: CloudMapInfo) -> Optional[str]:
        """
        Ensure PNG exists for selected map.
        Returns PNG path immediately if exists, or generates in background.
        """
        png_path = self._get_png_path(map_info)
        
        # If PNG already exists - return path immediately
        if png_path.exists():
            # Load metadata if not yet loaded
            if not map_info.rooms:
                await self._load_cached_metadata(map_info)
            return str(png_path)
        
        # If PNG is already being processed - wait for it
        if map_info.device_map_id in self._processing_tasks:
            task = self._processing_tasks[map_info.device_map_id]
            if not task.done():
                _LOGGER.debug("PNG already being generated for map %s, waiting...", map_info.device_map_id)
                await task
                return str(png_path) if png_path.exists() else None
        
        # Start background generation
        _LOGGER.info("Starting PNG generation for map %s", map_info.device_map_id)
        task = asyncio.create_task(self._generate_png_background(map_info))
        self._processing_tasks[map_info.device_map_id] = task
        
        # Return None immediately - camera will show loading state
        return None

    async def _generate_png_background(self, map_info: CloudMapInfo):
        """Generate PNG in background."""
        try:
            bv_path = self._get_bv_path(map_info)
            
            # Check if BV exists
            if not bv_path.exists():
                _LOGGER.info("BV not found, downloading map %s", map_info.device_map_id)
                result = await self.download_map(map_info)
                if result and result.get('png_path'):
                    _LOGGER.info("PNG generated for map %s", map_info.device_map_id)
                return
            
            # BV exists, generate PNG
            _LOGGER.info("Generating PNG from existing BV for map %s", map_info.device_map_id)
            map_data = await self._decode_bv_file(bv_path)
            if map_data:
                await self._render_png(map_data, map_info)
                
                # Extract and save metadata
                rooms_info = self._extract_rooms_info(map_data)
                room_count = len(rooms_info)
                await self._save_metadata(map_info, map_data, rooms_info, room_count)
                
                # Update map_info
                map_info.room_count = room_count
                map_info.rooms = rooms_info
                map_info.width = map_data.get('width', 0)
                map_info.height = map_data.get('height', 0)
                
                _LOGGER.info("PNG and metadata generated for map %s", map_info.device_map_id)
                
        except Exception as e:
            _LOGGER.error("Error generating PNG for map %s: %s", map_info.device_map_id, e)
        finally:
            # Cleanup processing task
            self._processing_tasks.pop(map_info.device_map_id, None)

    async def download_map(self, map_info: CloudMapInfo) -> Optional[Dict[str, Any]]:
        """Download and process a cloud map (full download)."""
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

            # Save metadata to JSON
            json_path = await self._save_metadata(map_info, map_data, rooms_info, room_count)

            # Render PNG
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
        room_names = map_data.get('room_names', [])
        
        if room_names:
            for room in room_names:
                room_id = room.get('id')
                room_name = room.get('name')
                rooms.append({
                    'id': room_id,
                    'name': room_name if room_name else f"Room {room_id}"
                })
        else:
            # Fallback to rooms dict
            rooms_dict = map_data.get('rooms', {})
            for room_id in rooms_dict.keys():
                rooms.append({
                    'id': room_id,
                    'name': f"Room {room_id}"
                })

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
        json_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(json_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(metadata, indent=2, ensure_ascii=False))

        _LOGGER.info("Saved metadata with %s rooms: %s", room_count, json_path.name)
        
        # Update cache
        cache = get_map_cache()
        cache.set_metadata(f"cloud_meta_{map_info.device_map_id}", {
            'room_count': room_count,
            'rooms': rooms,
            'width': map_data.get('width'),
            'height': map_data.get('height'),
        })

        return json_path

    async def _render_png(self, map_data: Dict, map_info: CloudMapInfo) -> Optional[Path]:
        """Render map to PNG using MapRenderer."""
        try:
            png_path = self._get_png_path(map_info)
            png_path.parent.mkdir(parents=True, exist_ok=True)

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

    async def get_png_path(self, map_info: CloudMapInfo) -> Optional[Path]:
        """Get PNG path, generating if necessary."""
        png_path = self._get_png_path(map_info)
        if png_path.exists():
            return png_path
        return None
        
    def get_map_by_id(self, device_map_id: int) -> Optional[CloudMapInfo]:
        """Get CloudMapInfo object by device_map_id."""
        for map_info in self._maps_cache:
            if map_info.device_map_id == device_map_id:
                return map_info
        return None