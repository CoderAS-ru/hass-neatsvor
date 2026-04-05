"""Data update coordinator for Neatsvor."""

import logging
import asyncio
from datetime import timedelta, datetime
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class NeatsvorCoordinator(DataUpdateCoordinator):
    """Coordinator for Neatsvor data updates."""

    def __init__(self, hass: HomeAssistant, vacuum):
        """Initialize with shared vacuum instance."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.vacuum = vacuum
        self._device_id: Optional[int] = None
        self._device_name: str = "Neatsvor Vacuum"
        self.mac_address: Optional[str] = None
        self._initialized = False
        self._rest_failures = 0
        self._max_rest_failures = 3
        self._last_rest_success: Optional[datetime] = None

        # References to cloud map entities
        self.cloud_maps_sensor = None
        self.cloud_map_select = None
        self.cloud_map_image = None

        # References to clean history entities
        self.clean_history_sensor = None
        self.clean_history_select = None
        self.clean_history_camera = None

    async def _async_setup(self):
        """Set up vacuum connection."""
        if not self._initialized:
            try:
                _LOGGER.info("Initializing NeatsvorVacuum...")
                if not self.vacuum.is_initialized:
                    await self.vacuum.initialize()

                # Set hass for visualizer
                self.vacuum.set_hass(self.hass)

                if self.vacuum.info:
                    self._device_id = self.vacuum.info.device_id
                    self.mac_address = self.vacuum.info.mac
                self._initialized = True
                self._rest_failures = 0
                _LOGGER.info("NeatsvorVacuum initialized")
            except Exception as err:
                _LOGGER.error("Initialization error: %s", err)
                raise UpdateFailed(f"Initialization error: {err}") from err

    async def _ensure_rest_connection(self) -> bool:
        """Check and restore REST connection."""
        if not self.vacuum or not self.vacuum.rest:
            _LOGGER.warning("REST client missing")
            return False

        try:
            await self.vacuum.rest.get_devices()
            self._rest_failures = 0
            self._last_rest_success = datetime.now()
            return True
        except Exception as e:
            self._rest_failures += 1
            _LOGGER.warning("REST error (%s/%s): %s", self._rest_failures, self._max_rest_failures, e)

            if self._rest_failures >= self._max_rest_failures:
                _LOGGER.error("REST connection lost, reconnecting...")
                await self._reconnect()

            return False

    async def _reconnect(self):
        """Perform full reconnection."""
        try:
            _LOGGER.info("Reconnecting...")
            await self.vacuum.disconnect()
            await asyncio.sleep(2)
            await self.vacuum.initialize()
            self._rest_failures = 0
            self._last_rest_success = datetime.now()
            _LOGGER.info("Reconnection successful")
        except Exception as e:
            _LOGGER.error("Reconnection error: %s", e)
            self._rest_failures = 0

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from vacuum."""
        try:
            if not self._initialized:
                await self._async_setup()

            rest_ok = await self._ensure_rest_connection()

            sensors = self.vacuum.state.sensors

            data = {
                # MQTT data
                "battery_level": sensors.battery,
                "status_code": sensors.status_code,
                "status_text": self._get_status_text(sensors),
                "online": self.vacuum.is_connected,
                "current_clean_time": sensors.clean_time_min,
                "current_clean_area": sensors.clean_area_m2,
                "fan_speed": sensors.fan_speed,
                "water_level": sensors.water_level,
                "clean_mode": sensors.clean_mode,

                # REST data (will be filled if connection is available)
                "software_version": "Unknown",
                "mac_address": self.mac_address,
                "device_pid": self.vacuum.info.pid if self.vacuum.info else None,
                "consumables": sensors.consumables,
                "statistics": {
                    "total_cleanings": 0,
                    "total_clean_time": 0,
                    "total_clean_area": 0,
                },
                "last_clean": {},
                "device_details": {
                    "device_name": "Neatsvor Vacuum",
                    "mac_address": self.mac_address,
                    "device_id": self.device_id,
                    "p_id": self.vacuum.info.pid if self.vacuum.info else None,
                }
            }

            data["malfunction_code"] = sensors.malfunction_code if hasattr(sensors, 'malfunction_code') else 0

            if rest_ok and self.vacuum and self.vacuum.info:
                # Increase retry attempts for DNS-sensitive requests
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        await self.vacuum.load_consumables()
                        data["consumables"] = sensors.consumables
                        _LOGGER.debug("Consumables after load: %s", sensors.consumables)

                        devices = await self.vacuum.rest.get_devices()
                        for device in devices:
                            if device.get("deviceId") == self.device_id:
                                data["software_version"] = device.get("softwareVersion", "Unknown")
                                data["device_details"].update({
                                    "image_url": device.get("imageUrl"),
                                    "software_version": device.get("softwareVersion", "Unknown"),
                                    "proto_version": device.get("protoVersion"),
                                })
                                break

                        total_stats = await self.vacuum.rest.get_clean_sum(self.vacuum.info.device_id)
                        if total_stats:
                            data["statistics"] = {
                                "total_cleanings": total_stats.get("cleanNums", 0),
                                "total_clean_time": round(total_stats.get("cleanLength", 0) / 3600, 1),
                                "total_clean_area": round(total_stats.get("cleanArea", 0) / 10, 1),
                            }

                        records = await self.vacuum.rest.get_clean_records(self.vacuum.info.device_id, 0, 1)
                        if records:
                            record = records[0]
                            clean_time_str = record.get("cleanTime")
                            clean_time = None
                            if clean_time_str:
                                try:
                                    naive_dt = datetime.strptime(clean_time_str, "%Y-%m-%d %H:%M:%S")
                                    clean_time = dt_util.as_utc(naive_dt)
                                except (ValueError, TypeError) as e:
                                    _LOGGER.warning("Error parsing time: %s", e)

                            data["last_clean"] = {
                                "clean_time": clean_time,
                                "clean_duration": record.get("cleanLength", 0) // 60,
                                "clean_area": record.get("cleanArea", 0) / 10,
                                "finished": record.get("cleanFinishedFlag", False),
                            }

                        # Break on success
                        break

                    except Exception as e:
                        error_str = str(e)
                        if "DNS" in error_str or "Timeout" in error_str or "getaddrinfo" in error_str:
                            if attempt < max_retries - 1:
                                wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                                _LOGGER.warning("DNS/Timeout error, retry %s/%s in %ss: %s", attempt + 1, max_retries, wait_time, error_str)
                                await asyncio.sleep(wait_time)
                                continue
                        # If it's not a DNS error or this is the last attempt, log it
                        if attempt == max_retries - 1:
                            _LOGGER.warning("Error fetching REST data after %s attempts: %s", max_retries, e)
                        else:
                            raise  # Re-raise for retry

            return data

        except Exception as err:
            _LOGGER.error("Update error: %s", err)
            # Return last known data if available
            return self.data or {}

    def _get_status_text(self, sensors) -> str:
        """Get combined status text with error details if needed."""
        if sensors.status_code == 13:  # Malfunction
            error_desc = sensors.malfunction_text or "Unknown error"
            return f"Malfunction: {error_desc}"
        return sensors.status_text or "Unknown"

    @property
    def rest_status(self) -> str:
        """REST connection status."""
        if self._rest_failures == 0 and self._last_rest_success:
            return f"OK (last success: {self._last_rest_success.strftime('%H:%M:%S')})"
        elif self._rest_failures > 0:
            return f"Problems ({self._rest_failures}/{self._max_rest_failures})"
        return "Not checked"

    @property
    def device_id(self) -> Optional[int]:
        """Return device ID."""
        return self._device_id

    @property
    def device_name(self) -> str:
        """Get device name."""
        if self.vacuum and self.vacuum.info and self.vacuum.info.name:
            if self.vacuum.info.name != "Unnamed device":
                return self.vacuum.info.name
        return self._device_name

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information."""
        device_name = "Neatsvor Vacuum"
        if self.vacuum and self.vacuum.info:
            if self.vacuum.info.name and self.vacuum.info.name != "Unnamed device":
                device_name = self.vacuum.info.name

        return {
            "identifiers": {(DOMAIN, str(self._device_id))},
            "name": device_name,
            "manufacturer": "Neatsvor",
            "model": device_name,
        }