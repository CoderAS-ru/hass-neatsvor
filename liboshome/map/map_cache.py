"""Fast in-memory cache for map data."""
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timedelta

_LOGGER = logging.getLogger(__name__)


class MapCache:
    """Fast in-memory cache for map metadata and images."""

    def __init__(self, ttl_seconds: int = 300):
        self._metadata_cache: Dict[str, tuple[Any, datetime]] = {}
        self._image_cache: Dict[str, tuple[bytes, datetime]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def _is_valid(self, timestamp: datetime) -> bool:
        return datetime.now() - timestamp < self._ttl

    def get_metadata(self, key: str) -> Optional[Any]:
        """Get cached metadata."""
        if key in self._metadata_cache:
            data, timestamp = self._metadata_cache[key]
            if self._is_valid(timestamp):
                return data
            del self._metadata_cache[key]
        return None

    def set_metadata(self, key: str, data: Any):
        """Set metadata in cache."""
        self._metadata_cache[key] = (data, datetime.now())

    def get_image(self, key: str) -> Optional[bytes]:
        """Get cached image bytes."""
        if key in self._image_cache:
            data, timestamp = self._image_cache[key]
            if self._is_valid(timestamp):
                return data
            del self._image_cache[key]
        return None

    def set_image(self, key: str, data: bytes):
        """Set image in cache."""
        self._image_cache[key] = (data, datetime.now())

    def invalidate(self, key: str = None):
        """Invalidate cache."""
        if key:
            self._metadata_cache.pop(key, None)
            self._image_cache.pop(key, None)
        else:
            self._metadata_cache.clear()
            self._image_cache.clear()
            _LOGGER.debug("Full cache cleared")


# Global singleton
_CACHE_INSTANCE: Optional[MapCache] = None

def get_map_cache() -> MapCache:
    """Get global cache instance."""
    global _CACHE_INSTANCE
    if _CACHE_INSTANCE is None:
        _CACHE_INSTANCE = MapCache()
    return _CACHE_INSTANCE