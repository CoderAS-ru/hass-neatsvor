"""Storage handler for Neatsvor select entities using Home Assistant storage API."""

import json
import logging
from typing import Dict, Optional, Any
from pathlib import Path
from homeassistant.helpers.storage import Store
import aiofiles

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = "neatsvor_select_states"


class NeatsvorSelectStorage:
    """Storage for select entity states using HA storage API."""

    def __init__(self, hass, entry_id: str):
        """Initialize storage."""
        self.hass = hass
        self.entry_id = entry_id
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}")
        self.data: Dict[str, Any] = {}
        self._loaded = False

    async def _async_load(self) -> None:
        """Load saved states from storage."""
        if self._loaded:
            return
        
        try:
            self.data = await self.store.async_load() or {}
            self._loaded = True
            _LOGGER.debug("Loaded select states: %s", self.data)
        except Exception as e:
            _LOGGER.error("Error loading select states: %s", e)
            self.data = {}

    async def _async_save(self) -> None:
        """Save states to storage."""
        try:
            await self.store.async_save(self.data)
            _LOGGER.debug("Saved select states: %s", self.data)
        except Exception as e:
            _LOGGER.error("Error saving select states: %s", e)

    async def async_ensure_loaded(self) -> None:
        """Ensure data is loaded."""
        if not self._loaded:
            await self._async_load()

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get saved value for key (synchronous, assumes loaded)."""
        return self.data.get(key, default)

    async def async_get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get saved value for key asynchronously."""
        await self.async_ensure_loaded()
        return self.data.get(key, default)

    async def async_set(self, key: str, value: str) -> None:
        """Set value for key and save."""
        await self.async_ensure_loaded()
        
        old_value = self.data.get(key)
        if old_value != value:
            self.data[key] = value
            await self._async_save()
            _LOGGER.debug("Saved select state: %s = %s (was %s)", key, value, old_value)

    async def async_set_multiple(self, values: Dict[str, str]) -> None:
        """Set multiple values at once."""
        await self.async_ensure_loaded()
        
        changed = False
        for key, value in values.items():
            if self.data.get(key) != value:
                self.data[key] = value
                changed = True
        
        if changed:
            await self._async_save()
            _LOGGER.debug("Saved multiple select states: %s", values)

    def get_all(self) -> Dict[str, str]:
        """Get all saved values (synchronous, assumes loaded)."""
        return self.data.copy()

    async def async_get_all(self) -> Dict[str, str]:
        """Get all saved values asynchronously."""
        await self.async_ensure_loaded()
        return self.data.copy()

    async def async_clear(self) -> None:
        """Clear all saved values."""
        await self.async_ensure_loaded()
        self.data = {}
        await self._async_save()
        _LOGGER.debug("Cleared all select states")

    async def async_migrate_from_file(self, old_storage_path: Path) -> bool:
        """Migrate data from old file-based storage."""
        if not old_storage_path.exists():
            return False
        
        try:
            async with aiofiles.open(old_storage_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                old_data = json.loads(content)
            
            # Migrate data
            for key, value in old_data.items():
                self.data[key] = value
            
            await self._async_save()
            
            # Delete old file
            old_storage_path.unlink()
            _LOGGER.info("Migrated select states from %s", old_storage_path)
            return True
            
        except Exception as e:
            _LOGGER.error("Error migrating select states: %s", e)
            return False