"""Storage handler for Neatsvor select entities."""

import json
import logging
from typing import Dict, Optional, Any
from pathlib import Path
import aiofiles

_LOGGER = logging.getLogger(__name__)


class NeatsvorSelectStorage:
    """Storage for select entity states."""

    def __init__(self, hass, entry_id: str):
        """Initialize storage."""
        self.hass = hass
        self.entry_id = entry_id
        self.data: Dict[str, Any] = {}

        config_dir = Path(hass.config.path("custom_components/neatsvor"))
        config_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path = config_dir / f"select_states_{entry_id}.json"

        self.hass.async_create_task(self._async_load())

    async def _async_load(self) -> None:
        """Load saved states from file asynchronously."""
        try:
            if self.storage_path.exists():
                async with aiofiles.open(self.storage_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    self.data = json.loads(content)
                _LOGGER.debug("Loaded select states from %s", self.storage_path)
            else:
                self.data = {}
                _LOGGER.debug("No existing select states file, starting fresh")
        except Exception as e:
            _LOGGER.error("Error loading select states: %s", e)
            self.data = {}

    async def _async_save(self) -> None:
        """Save states to file asynchronously."""
        try:
            async with aiofiles.open(self.storage_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self.data, indent=2, ensure_ascii=False))
            _LOGGER.debug("Saved select states to %s", self.storage_path)
        except Exception as e:
            _LOGGER.error("Error saving select states: %s", e)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get saved value for key."""
        return self.data.get(key, default)

    async def async_set(self, key: str, value: str) -> None:
        """Set value for key and save asynchronously."""
        old_value = self.data.get(key)
        if old_value != value:
            self.data[key] = value
            await self._async_save()
            _LOGGER.debug("Saved select state: %s = %s (was %s)", key, value, old_value)

    def get_all(self) -> Dict[str, str]:
        """Get all saved values."""
        return self.data.copy()

    async def async_clear(self) -> None:
        """Clear all saved values asynchronously."""
        self.data = {}
        await self._async_save()
        _LOGGER.debug("Cleared all select states")