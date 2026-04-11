"""
Unified class for controlling Neatsvor vacuum cleaner.
Combines REST, MQTT, DP and maps.
"""

import asyncio
import logging
import gzip
import tempfile
import os
import sys
from typing import Dict, Any, Optional, List, Callable, Awaitable, Tuple
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import aiofiles

from custom_components.neatsvor.liboshome.dp.manager import DPManager
from custom_components.neatsvor.liboshome.device.state import DeviceState
from custom_components.neatsvor.liboshome.mqtt.encoder import NeatsvorEncoder
from custom_components.neatsvor.liboshome.mqtt.command_sender import CommandSender
from custom_components.neatsvor.liboshome.mqtt.message_router import MqttMessageRouter
from custom_components.neatsvor.liboshome.mqtt.client_async import AsyncMQTTClient
from custom_components.neatsvor.liboshome.map.async_visualizer import AsyncMapVisualizer
from custom_components.neatsvor.liboshome.map.cloud_map_manager import CloudMapManager
from custom_components.neatsvor.liboshome.map.clean_history_manager import CleanHistoryManager
from custom_components.neatsvor.liboshome.map.map_decoder import MapDecoder
from custom_components.neatsvor.liboshome.map.map_processor import get_map_processor
from custom_components.neatsvor.liboshome.protobuf import sdk_com_pb2 as bvsdk

_LOGGER = logging.getLogger(__name__)


@dataclass
class VacuumInfo:
    """Device information."""
    device_id: int
    mac: str
    pid: str
    name: str
    client_id: str


class NeatsvorVacuum:
    """
    Unified class for controlling Neatsvor vacuum cleaner.

    Example:
        vacuum = NeatsvorVacuum(config)
        await vacuum.initialize()
        await vacuum.start_cleaning()
        status = vacuum.status
        await vacuum.disconnect()
    """

    # DP command constants
    DP_SWITCH_CLEAN = 'switch_clean'
    DP_SWITCH_CHARGE = 'switch_charge'
    DP_LOCATE = 'locate'
    DP_FAN = 'fan'
    DP_WATER_TANK = 'water_tank'
    DP_ROOM_CLEAN = 31  # Fixed ID for room cleaning
    DP_BUILD_MAP = 'build_map'
    DP_VOLUME_SET = 'volume_set'
    DP_DUST_COLLECTION = 'dust_collection'

    # Water level mapping
    WATER_LEVEL_MAP = {1: "low", 2: "middle", 3: "high"}

    def __init__(self, config):
        """
        Initialize vacuum.

        Args:
            config: NeatsvorConfig object with configuration
        """
        self.config = config

        # Clients (initialized in initialize)
        self.rest = None
        self.mqtt = None
        self.router = None
        self._command_sender = None
        self._encoder = None

        # Managers
        self.dp_manager: Optional[DPManager] = None
        self.cloud_maps: Optional[CloudMapManager] = None
        self.clean_history: Optional[CleanHistoryManager] = None
        self.visualizer = None

        # State
        self.state = DeviceState()
        self.state.sensors.battery = None
        self.state.sensors.status = "unknown"
        self.state.sensors.charging = False
        self.state.sensors.clean_time_min = None
        self.state.sensors.clean_area_m2 = None
        self.state.sensors.online = False
        self.state.sensors.water_level = "middle"

        self.info: Optional[VacuumInfo] = None
        self._map_data: Optional[Dict] = None

        self._map_origin_x: int = 0
        self._map_origin_y: int = 0
        self._map_height: int = 200
        self._map_width: int = 200
        
        self._last_map_id = None
        self._last_map_check = None
        self._restore_in_progress = False

        # Callbacks
        self._map_callbacks: List[Callable[[Dict], Awaitable[None]]] = []
        self._state_callbacks: List[Callable[[Dict], Awaitable[None]]] = []
        self._dp_callbacks: List[Callable[[List], Awaitable[None]]] = []

        self._initialized = False
        self._connected = False

    # ------------------------------------------------------------------
    # Initialization and connection
    # ------------------------------------------------------------------

    def set_hass(self, hass):
        """Set Home Assistant instance for visualizer."""
        _LOGGER.info("set_hass called, hass=%s", hass is not None)

        # Save reference to hass
        self.hass = hass

        if self.visualizer is None and hass:
            _LOGGER.info("Creating AsyncMapVisualizer...")

            # IMPORTANT: Explicitly specify base directory for maps
            base_dir = "/config/www/neatsvor/maps"
            self.visualizer = AsyncMapVisualizer(hass=hass, base_dir=base_dir)
            _LOGGER.info("Visualizer created with base path: %s", base_dir)

            # Set visualizer for clean_history
            if hasattr(self, 'clean_history'):
                _LOGGER.info("Setting visualizer for clean_history")
                self.clean_history.set_visualizer(self.visualizer)
                _LOGGER.info("Visualizer set for clean_history")
            else:
                _LOGGER.warning("clean_history not found in vacuum")
        else:
            _LOGGER.info("Visualizer already exists or no hass: %s", self.visualizer is not None)

    async def initialize(self) -> bool:
        """Initialize the vacuum connection."""
        # Prevent re-initialization
        if self._initialized:
            _LOGGER.warning("Vacuum already initialized, skipping")
            return True

        try:
            _LOGGER.debug("=== START INITIALIZATION ===")

            # 1. REST authentication with region from config
            _LOGGER.debug("STEP 1 - Creating REST client")
            from custom_components.neatsvor.liboshome.rest.async_client import NeatsvorRestAsync

            self.rest = NeatsvorRestAsync(
                email=self.config.credentials.email,
                password=self.config.credentials.password,
                region=self.config.rest.country
            )

            _LOGGER.debug("STEP 2 - Entering REST context")
            await self.rest.__aenter__()

            _LOGGER.debug("STEP 3 - Performing login()")
            await self.rest.login()

            _LOGGER.debug("STEP 4 - Performing login_sdk()")
            await self.rest.login_sdk()

            _LOGGER.info("REST authentication successful, client_id=%s", self.rest.client_id)

            # 2. Device information
            _LOGGER.debug("STEP 5 - Getting device list")
            devices = await self.rest.get_devices()
            _LOGGER.debug("Found %s devices", len(devices))

            if not devices:
                raise RuntimeError("No devices found")

            device = devices[0]
            self.info = VacuumInfo(
                device_id=device["deviceId"],
                mac=device["macAddress"],
                pid=device["pId"],
                name=device.get("deviceName", "Unnamed device"),
                client_id=self.rest.client_id
            )
            _LOGGER.info("Device: %s (MAC: %s)", self.info.name, self.info.mac)

            # 3. Load DP schema (CRITICAL)
            _LOGGER.debug("STEP 6 - Loading DP schema")
            dp_list = await self.rest.get_device_dp(self.info.device_id, self.info.pid)
            _LOGGER.debug("Received %s DP items", len(dp_list))

            self.dp_manager = DPManager()
            self.dp_manager.load_from_api_list(dp_list)
            _LOGGER.info("Loaded DP: %s", len(self.dp_manager))

            # 4. Create managers (fast)
            self.cloud_maps = CloudMapManager(self.rest)
            self.clean_history = CleanHistoryManager(self.rest)

            # 5. Device image (background, non-critical)
            try:
                image_url = device.get("imageUrl")
                if image_url:
                    asyncio.create_task(self._cache_device_image(image_url))
            except Exception as e:
                _LOGGER.warning("Failed to cache device image: %s", e)

            # 6. MQTT connection in background
            asyncio.create_task(self._connect_mqtt_async())

            self._initialized = True
            self._connected = True
            _LOGGER.info("Basic initialization complete, DP Manager ready")

            # 7. Request initial data in background
            asyncio.create_task(self._request_initial_data())

            return True

        except Exception as e:
            _LOGGER.error("Initialization error: %s", e)
            await self.disconnect()
            raise

    async def _connect_mqtt_async(self):
        """Connect MQTT in background."""
        try:
            _LOGGER.info("Background MQTT connection...")
            await self._connect_mqtt()
            _LOGGER.info("MQTT connected in background")
        except Exception as e:
            _LOGGER.error("Background MQTT error: %s", e)

    async def _request_initial_data(self):
        """Request initial data in background."""
        try:
            _LOGGER.info("Background data request...")
            # Small delay to allow MQTT to connect
            await asyncio.sleep(2)
            await self.request_all_data()
            _LOGGER.info("Initial data requested")
        except Exception as e:
            _LOGGER.error("Data request error: %s", e)

    async def _connect_mqtt(self) -> None:
        """Internal method for MQTT connection."""
        # MQTT client
        self.mqtt = AsyncMQTTClient(
            host=self.config.mqtt.host,
            port=self.config.mqtt.port,
            username=self.config.mqtt.username,
            password=self.config.mqtt.password,
            client_id=f"APP_{self.info.client_id}"
        )
        await self.mqtt.connect()

        # Message router
        self.router = MqttMessageRouter(
            client_id=f"APP_{self.info.client_id}",
            mac=self.info.mac
        )
        self.mqtt.add_handler(self.router.on_mqtt_message)

        # Register callbacks
        self.router.register_map_callback(self._on_map_data)
        self.router.register_state_callback(self._on_state_data)
        self.router.register_dp_callback(self._on_dp_data)

        # Subscribe to topics
        await self.router.subscribe_to_device_topics(self.mqtt)

        # Create encoder
        self._encoder = NeatsvorEncoder.from_dp_manager(
            device_mac=self.info.mac,
            dp_manager=self.dp_manager,
            login_name='appuser',
            version=1
        )

        # Create command sender
        self._command_sender = CommandSender(
            mqtt_client=self.mqtt,
            mac=self.info.mac,
            command_delay=self.config.device.command_delay
        )

        _LOGGER.info("MQTT connected and configured")

    async def _on_mqtt_disconnect(self):
        """Handle MQTT disconnection and reconnect."""
        _LOGGER.warning("MQTT disconnected, attempting to reconnect...")
        self._connected = False

        for attempt in range(5):
            try:
                # Exponential backoff: 2, 4, 8, 16, 32 seconds
                wait_time = 2 ** attempt
                _LOGGER.info("MQTT reconnect attempt %s/5 in %ss...", attempt + 1, wait_time)
                await asyncio.sleep(wait_time)

                # Try to reconnect
                if self.mqtt:
                    try:
                        await self.mqtt.disconnect()
                    except:
                        pass
                    self.mqtt = None

                await self._connect_mqtt()
                self._connected = True
                _LOGGER.info("MQTT reconnected successfully")

                # Request fresh data after reconnection
                asyncio.create_task(self.request_all_data())
                return

            except Exception as e:
                _LOGGER.error("MQTT reconnect attempt %s failed: %s", attempt + 1, e)

        _LOGGER.error("Failed to reconnect MQTT after 5 attempts")

    async def disconnect(self) -> None:
        """Disconnect all clients."""
        self._connected = False
        self._initialized = False

        # MQTT - disconnect first
        if self.mqtt:
            try:
                await self.mqtt.disconnect()
                _LOGGER.info("MQTT disconnected")
            except Exception as e:
                _LOGGER.error("Error disconnecting MQTT: %s", e)
            finally:
                self.mqtt = None
                self.router = None
                self._command_sender = None
                self._encoder = None

        await asyncio.sleep(0.1)

        # REST
        if self.rest:
            try:
                await self.rest.__aexit__(None, None, None)
                _LOGGER.info("REST session closed")
            except Exception as e:
                _LOGGER.error("Error closing REST: %s", e)
            finally:
                self.rest = None

    # ------------------------------------------------------------------
    # Basic commands
    # ------------------------------------------------------------------

    async def _send_dp_command(self, dp_name: str, value: Any, dp_id: Optional[int] = None) -> bool:
        """
        Universal method for sending DP commands.

        Args:
            dp_name: DP name in manager
            value: Value to send
            dp_id: Direct DP ID (if known)

        Returns:
            True if command was sent successfully
        """
        try:
            if dp_id is None:
                dp_id = self.dp_manager.get_id(dp_name)

            if dp_id:
                command_bytes = self._encoder.create_dp_command(dp_id, value)
                await self._command_sender.publish_command(command_bytes)
                _LOGGER.debug("Command sent: %s=%s", dp_name, value)
                return True
            else:
                _LOGGER.error("DP '%s' not found", dp_name)
                return False

        except Exception as e:
            _LOGGER.error("Error sending command %s: %s", dp_name, e)
            return False

    async def start_cleaning(self) -> bool:
        """Start cleaning."""
        return await self._send_dp_command(self.DP_SWITCH_CLEAN, 2)

    async def pause_cleaning(self) -> bool:
        """Pause cleaning."""
        return await self._send_dp_command(self.DP_SWITCH_CLEAN, 1)

    async def stop_cleaning(self) -> bool:
        """Stop cleaning."""
        return await self._send_dp_command(self.DP_SWITCH_CLEAN, 0)

    async def return_to_base(self) -> bool:
        """Return to base."""
        return await self._send_dp_command(self.DP_SWITCH_CHARGE, 2)

    async def locate(self) -> bool:
        """Locate robot."""
        return await self._send_dp_command(self.DP_LOCATE, True)

    async def set_fan_speed(self, level: int) -> bool:
        """Set fan speed (1-4)."""
        if not 1 <= level <= 4:
            _LOGGER.error("Invalid fan level: %s", level)
            return False
        return await self._send_dp_command(self.DP_FAN, level)

    async def set_water_level(self, level: int) -> bool:
        """Set water level (1-3)."""
        if not 1 <= level <= 3:
            _LOGGER.error("Invalid water level: %s", level)
            return False
        return await self._send_dp_command(self.DP_WATER_TANK, level)

    async def build_map(self) -> bool:
        """Fast map building without cleaning."""
        return await self._send_dp_command(self.DP_BUILD_MAP, True)

    async def set_volume(self, level: int) -> bool:
        """Set voice volume (0-100)."""
        if not 0 <= level <= 100:
            _LOGGER.error("Invalid volume level: %s", level)
            return False
        return await self._send_dp_command(self.DP_VOLUME_SET, level)

    async def empty_dust(self) -> bool:
        """Force empty dust bin."""
        # Try different possible DP names
        dp_names = ['dust_collection', 'empty_dust', 'dust_collection_switch']
        for name in dp_names:
            if self.dp_manager.get_id(name):
                return await self._send_dp_command(name, True)

        _LOGGER.error("DP for dust collection not found")
        return False

    async def start_room_clean(self, room_ids: List[int]) -> bool:
        """Room cleaning."""
        try:
            # Setup protobuf path
            proto_dir = Path(__file__).parent.parent / "protobuf"
            if str(proto_dir) not in sys.path:
                sys.path.insert(0, str(proto_dir))

            import sweeper_any_pb2 as sweeper_any
            from google.protobuf import any_pb2

            room_data = sweeper_any.Rooms()
            room_data.room_ids.extend(room_ids)
            room_data.fan_level = 2
            room_data.water_level = 2
            room_data.mode = 2

            body_any = any_pb2.Any()
            body_any.Pack(room_data, "sweeper.Rooms")

            command_bytes = self._encoder.create_dp_command(
                self.DP_ROOM_CLEAN,
                body_any.SerializeToString()
            )

            await self._command_sender.publish_command(command_bytes)
            _LOGGER.info("Room clean command sent: %s", room_ids)
            return True

        except Exception as e:
            _LOGGER.error("Error in room cleaning: %s", e)
            return False

    async def save_reference_map(self) -> bool:
        """Save current map as reference on the device."""
        _LOGGER.info("Saving reference map")
        try:
            from custom_components.neatsvor.liboshome.protobuf import sweeper_any_pb2
            from google.protobuf import any_pb2

            map_reuse = sweeper_any_pb2.MapReuse()
            map_reuse.map_id = 0  # 0 for current map
            map_reuse.operation = 1  # 1 = save

            # Pack into Any
            body_any = any_pb2.Any()
            body_any.Pack(map_reuse, "type.googleapis.com/sweeper.MapReuse")

            await self.send_raw_command(30, body_any.SerializeToString())

            _LOGGER.info("Reference map save command sent")
            return True

        except Exception as e:
            _LOGGER.error("Error saving reference map: %s", e)
            return False

    async def restore_reference_map(self, map_id: int, map_url: str = "", map_md5: str = "") -> bool:
        """
        Restore reference map using DP 30 (map_reuse).

        Args:
            map_id: Device map ID
            map_url: URL to download map (optional)
            map_md5: MD5 checksum (optional)
        """
        _LOGGER.info("Restoring reference map %s...", map_id)
        try:
            from custom_components.neatsvor.liboshome.protobuf import sweeper_any_pb2
            from google.protobuf import any_pb2

            use_map = sweeper_any_pb2.UseMap()
            use_map.map_id = map_id
            if map_url:
                use_map.url = map_url
            if map_md5:
                use_map.md5 = map_md5

            body_any = any_pb2.Any()
            body_any.Pack(use_map, "type.googleapis.com/sweeper.UseMap")

            command_bytes = self._encoder.create_dp_command(30, body_any.SerializeToString())
            await self._command_sender.publish_command(command_bytes)

            _LOGGER.info("Restore command sent for map %s", map_id)
            return True

        except Exception as e:
            _LOGGER.error("Error restoring reference map: %s", e)
            return False

    async def use_cloud_map(self, map_id: int, map_url: str, map_md5: str) -> bool:
        """
        Use a cloud map as the current map (DP 30).
        """
        _LOGGER.info("Using cloud map %s as current map", map_id)
        try:
            from custom_components.neatsvor.liboshome.protobuf import sweeper_any_pb2
            from google.protobuf import any_pb2
            import base64

            # Create UseMap message exactly as in the original app
            use_map = sweeper_any_pb2.UseMap()
            use_map.map_id = map_id
            use_map.url = map_url
            use_map.md5 = map_md5

            _LOGGER.debug("UseMap: id=%s, url=%s, md5=%s", map_id, map_url, map_md5)

            # Use encoder directly
            command_bytes = self._encoder.create_dp_command(30, use_map)

            _LOGGER.debug("Command bytes length: %s", len(command_bytes))

            # Send directly
            await self._command_sender.publish_command(command_bytes)

            _LOGGER.info("Command to use map %s sent", map_id)

            # Request map update after a short delay
            async def delayed_map_request():
                await asyncio.sleep(2)
                await self.request_map()

            asyncio.create_task(delayed_map_request())

            return True

        except Exception as e:
            _LOGGER.error("Error using cloud map: %s", e)
            import traceback
            traceback.print_exc()
            return False

    async def save_current_map_to_cloud(self) -> bool:
        """Save current map to cloud (DP 14)."""
        _LOGGER.info("Saving map to cloud")
        try:
            # For DP 14 send None (empty message)
            await self.send_raw_command(14, None)

            _LOGGER.info("Command to save map to cloud sent")
            return True

        except Exception as e:
            _LOGGER.error("Error saving map to cloud: %s", e)
            return False

    async def send_raw_command(self, dp_id: int, value) -> bool:
        """Send raw command."""
        try:
            command_bytes = self._encoder.create_dp_command(dp_id, value)
            await self._command_sender.publish_command(command_bytes)
            _LOGGER.info("Raw command sent: DP %s=%s", dp_id, value)
            return True
        except Exception as e:
            _LOGGER.error("Error sending DP %s command: %s", dp_id, e)
            return False

    async def _check_map_changed(self, map_data: Dict):
        """Check if map changed and restore if needed."""
        if self._restore_in_progress:
            return

        # Get current map_id from map data
        current_map_id = None
        if 'raw' in map_data and hasattr(map_data['raw'], 'header'):
            current_map_id = map_data['raw'].header.map_id

        if not current_map_id:
            return

        # If this is the first map - just remember
        if self._last_map_id is None:
            self._last_map_id = current_map_id
            self._last_map_check = datetime.now()
            return

        # Check if map changed
        if current_map_id != self._last_map_id:
            _LOGGER.warning("Map changed from %s to %s", self._last_map_id, current_map_id)

            # Check if auto-restore is enabled
            if hasattr(self, '_auto_restore_enabled') and self._auto_restore_enabled:
                await self._restore_reference_map_if_needed()

            self._last_map_id = current_map_id
            self._last_map_check = datetime.now()

    async def _restore_reference_map_if_needed(self):
        """Restore reference map if available."""
        if not hasattr(self, 'coordinator') or not self.coordinator:
            return

        if not hasattr(self.coordinator, 'cloud_maps_sensor'):
            return

        sensor = self.coordinator.cloud_maps_sensor
        reference_id = getattr(sensor, '_reference_map_id', None)

        if not reference_id:
            _LOGGER.debug("No reference map set, skipping restore")
            return

        _LOGGER.info("Attempting to restore reference map %s", reference_id)

        self._restore_in_progress = True
        try:
            # Find map in sensor
            reference_map = sensor.get_map_by_id(reference_id)
            if not reference_map:
                _LOGGER.error("Reference map %s not found", reference_id)
                return

            # Use existing method for restoration
            if reference_map.get('app_map_url') and reference_map.get('app_map_md5'):
                await self.use_cloud_map(
                    reference_id,
                    reference_map['app_map_url'],
                    reference_map['app_map_md5']
                )
            else:
                await self.use_cloud_map(
                    reference_id,
                    reference_map['dev_map_url'],
                    reference_map['dev_map_md5']
                )

            _LOGGER.info("Reference map %s restored", reference_id)

            # Notify user
            if hasattr(self, 'hass') and self.hass:
                self.hass.bus.async_fire("persistent_notification", {
                    "message": "Map auto-restored from reference",
                    "title": "Neatsvor"
                })

        except Exception as e:
            _LOGGER.error("Error restoring reference map: %s", e)
        finally:
            self._restore_in_progress = False
            
    async def request_map(self, priority=False) -> bool:
        """Request map (DP 4)."""
        if priority:
            _LOGGER.info("High priority map request")
            # Отправляем запрос дважды с интервалом
            result1 = await self.request_data([4])
            await asyncio.sleep(0.5)
            result2 = await self.request_data([4])
            return result1 and result2
        return await self.request_data([4])

    # ------------------------------------------------------------------
    # Data requests
    # ------------------------------------------------------------------

    async def request_data(self, dp_ids: List[int]) -> bool:
        """Request data for specified DPs."""
        try:
            _LOGGER.info("Requesting data for %s DPs", len(dp_ids))

            header = bvsdk.MqttMsgHeader()
            header.version = 1
            header.login_name = self.info.client_id
            header.cmd_id.extend(dp_ids)
            header.cmd_type = bvsdk.MqttMsgHeader.CmdType.kAppRequest

            msg = bvsdk.MqttMsg()
            msg.header.CopyFrom(header)

            serialized = msg.SerializeToString()
            compressed = gzip.compress(serialized)

            await self._command_sender.publish_command(compressed)
            _LOGGER.info("Data request sent")
            return True

        except Exception as e:
            _LOGGER.error("Error requesting data: %s", e)
            return False

    async def request_all_data(self) -> bool:
        """Request all data like the official app."""
        dp_ids = [3, 4, 5, 1, 2, 15, 6, 7, 8, 9, 10, 16, 24, 37, 36, 34, 38, 40, 49, 47, 25, 33, 35]
        _LOGGER.info("Requesting all data: %s", dp_ids)
        return await self.request_data(dp_ids)

    async def request_map(self) -> bool:
        """Request map (DP 4)."""
        return await self.request_data([4])

    # ------------------------------------------------------------------
    # Incoming data handlers
    # ------------------------------------------------------------------

    async def _on_map_data(self, map_data: Dict):
        """Handle map data."""
        try:
            _LOGGER.debug("Received map! Size: %sx%s", map_data.get('width', 0), map_data.get('height', 0))

            # Save to state
            self._map_data = map_data
            self.state._map_data = map_data

            # Check for map change
            await self._check_map_changed(map_data)

            # Visualization
            try:
                robot_pos = map_data.get('robot_position')
                if hasattr(self, 'visualizer') and self.visualizer:
                    if hasattr(self.visualizer, 'base_dir'):
                        _LOGGER.debug("Visualizer base dir: %s", self.visualizer.base_dir)

                    await self.visualizer.render_realtime_frame(map_data, robot_pos=robot_pos)
                else:
                    _LOGGER.debug("Visualizer not initialized")
            except Exception as e:
                _LOGGER.error("Error visualizing map: %s", e)

            # Callbacks
            for i, callback in enumerate(self._map_callbacks):
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(map_data)
                    else:
                        callback(map_data)
                except Exception as e:
                    _LOGGER.error("Error in map callback #%s: %s", i, e)

        except Exception as e:
            _LOGGER.error("Error in _on_map_data: %s", e, exc_info=True)

    async def _on_state_data(self, state_data: Dict):
        """Handle state data."""
        if state_data.get('type') == 'state_update':
            self.state.sensors.status = "charging" if state_data.get('flag') == 1 else "working"
            self.state.sensors.battery = state_data.get('battery')
            _LOGGER.debug("State: %s, battery: %s%%", self.state.sensors.status, self.state.sensors.battery)

        for callback in self._state_callbacks:
            try:
                await callback(state_data)
            except Exception as e:
                _LOGGER.error("Error in state callback: %s", e)

    async def _on_dp_data(self, dp_list: List):
        """Handle DP data using updated state."""
        if not self._connected:
            _LOGGER.debug("MQTT disconnected, skipping DP processing")
            return

        _LOGGER.info("MQTT: Received %s DP updates", len(dp_list))

        for dp_id, value in dp_list:
            # Log received DPs for debugging
            _LOGGER.info("DP %s = %s", dp_id, type(value).__name__)

            # Special attention to DP 32
            if dp_id == 32:
                _LOGGER.warning("DP 32 RECEIVED! Type: %s", type(value))
                if isinstance(value, bytes):
                    _LOGGER.warning("Bytes length: %s", len(value))
                    _LOGGER.warning("First 50 bytes: %s", value[:50].hex())
                    # Try to parse
                    try:
                        from custom_components.neatsvor.liboshome.protobuf import sweeper_com_pb2
                        zone_clean = sweeper_com_pb2.ZoneClean()
                        zone_clean.ParseFromString(value)
                        _LOGGER.warning("Parsed: times=%s", zone_clean.times)
                        for i, zone in enumerate(zone_clean.zones):
                            _LOGGER.warning("Zone %s: number=%s", i, zone.number)
                            for point in zone.points:
                                _LOGGER.warning("point: (%s, %s)", point.x, point.y)
                    except Exception as e:
                        _LOGGER.warning("Failed to parse: %s", e)

            # Log status change
            if dp_id == 5:
                status_map = {
                    0: "idle", 1: "relocation", 2: "upgrade", 3: "building_map",
                    4: "paused", 5: "returning", 6: "charging", 7: "charged",
                    8: "cleaning", 9: "zone_cleaning", 10: "room_cleaning",
                    11: "spot_cleaning", 12: "manual", 13: "error", 14: "sleeping",
                    15: "dust_collecting", 50: "washing_mop", 51: "filling_water",
                    52: "drying_mop", 53: "station_cleaning", 54: "returning_to_wash"
                }
                _LOGGER.info("Robot status: %s (DP5=%s)", status_map.get(value, f"Unknown({value})"), value)

            # Update state
            self.state.sensors.update_from_dp(dp_id, value, self.dp_manager)
            self.state.update_dp(dp_id, value)

            # Process through DP manager
            result = self.dp_manager.process_dp_for_state(dp_id, value)
            if result:
                attr_name, transformed = result
                setattr(self.state.sensors, attr_name, transformed)

        # Notify subscribers
        for callback in self._dp_callbacks:
            try:
                await callback(dp_list)
            except Exception as e:
                _LOGGER.error("Error in dp callback: %s", e)

    # ------------------------------------------------------------------
    # Room operations
    # ------------------------------------------------------------------

    async def get_available_rooms(self, timeout: int = 10) -> list:
        """
        Return list of rooms from the latest received map.
        Waits for map receipt up to timeout seconds.
        """
        # If map already exists - return immediately
        if self._map_data:
            rooms_from_map = self._map_data.get('room_names', [])
            if rooms_from_map:
                _LOGGER.info("Found rooms in current map: %s", len(rooms_from_map))
                return sorted(rooms_from_map, key=lambda x: x['id'])

        # If no map - wait for it
        _LOGGER.debug("Waiting for map to get rooms (up to %s sec)...", timeout)

        for i in range(timeout):
            await asyncio.sleep(1)
            if self._map_data:
                rooms_from_map = self._map_data.get('room_names', [])
                if rooms_from_map:
                    _LOGGER.info("Got rooms after waiting: %s", len(rooms_from_map))
                    return sorted(rooms_from_map, key=lambda x: x['id'])

        _LOGGER.warning("No map received within %s sec, rooms not found", timeout)
        return []

    async def get_room_presets(self) -> Dict[int, Dict]:
        """
        Get room presets from the latest map.
        Returns {room_id: {'fan': 1-4, 'water': 1-3, 'times': 1-3, 'mode': 0-2}}
        """
        if not self._map_data:
            _LOGGER.debug("No map data for presets")
            return {}

        try:
            # Try to get from raw map data
            if 'raw' in self._map_data and hasattr(self._map_data['raw'], 'room_info'):
                raw = self._map_data['raw']
                if hasattr(raw.room_info, 'room_attrs'):
                    presets = {}
                    for attr in raw.room_info.room_attrs:
                        presets[attr.room_id] = {
                            'fan': attr.fan_level,
                            'water': attr.tank_level,
                            'times': attr.clean_times,
                            'mode': attr.clean_mode
                        }
                    _LOGGER.info("Loaded %s presets from map", len(presets))
                    return presets
        except Exception as e:
            _LOGGER.debug("Failed to load presets: %s", e)

        return {}

    async def start_room_clean_with_preset(self, room_ids: List[int]) -> bool:
        """Clean rooms using saved presets from map."""
        try:
            _LOGGER.info("start_room_clean_with_preset called with rooms: %s", room_ids)

            # Get presets from current map (for logging, not for sending)
            presets = await self.get_room_presets()
            _LOGGER.info("Presets loaded: %s", presets)

            # Setup protobuf path
            proto_dir = Path(__file__).parent.parent / "protobuf"
            if str(proto_dir) not in sys.path:
                sys.path.insert(0, str(proto_dir))

            import sweeper_any_pb2 as sweeper_any
            from google.protobuf import any_pb2

            # Create Rooms message
            room_data = sweeper_any.Rooms()
            room_data.room_ids.extend(room_ids)

            # Parameters below are NOT used if map has presets
            # But keep default values
            room_data.fan_level = 2
            room_data.water_level = 2
            room_data.mode = 2

            room_names = [self._get_room_name(room_id) for room_id in room_ids]
            _LOGGER.info("Rooms to clean: %s (IDs: %s)", room_names, room_ids)

            body_any = any_pb2.Any()
            body_any.Pack(room_data, "sweeper.Rooms")

            serialized = body_any.SerializeToString()
            _LOGGER.debug("RoomAttrs serialized size: %s bytes", len(serialized))

            command_bytes = self._encoder.create_dp_command(31, serialized)
            _LOGGER.debug("Command size: %s bytes", len(command_bytes))

            await self._command_sender.publish_command(command_bytes)
            _LOGGER.info("Room cleaning started for %s (presets from map)", room_names)
            return True

        except Exception as e:
            _LOGGER.error("Error in room cleaning with presets: %s", e, exc_info=True)
            return False

    def _get_room_name(self, room_id: int) -> str:
        """Get room name by ID from latest map."""
        if self._map_data:
            rooms = self._map_data.get('room_names', [])
            for room in rooms:
                if room['id'] == room_id:
                    return room['name']
        return f"Room_{room_id}"

    async def zone_clean(self, x1: int, y1: int, x2: int, y2: int, repeats: int = 1) -> bool:
        """Zone cleaning with proper coordinate scaling."""
        _LOGGER.info(f"Raw zone: ({x1},{y1})-({x2},{y2}) x{repeats}")
        
        if not self._map_data:
            _LOGGER.error("No map data available for scaling")
            return False
        
        # 1. Получаем размеры карты
        map_width = self._map_data.get('width', 185)
        map_height = self._map_data.get('height', 173)
        
        # 2. Вычисляем multiple (как в map_renderer.py)
        if map_width < 100 and map_height < 100:
            multiple = 8
        elif map_width < 200 and map_height < 200:
            multiple = 6
        elif map_width >= 300 or map_height >= 300:
            multiple = 2
        else:
            multiple = 4
        
        # 3. Вычисляем высоту легенды
        room_names = self._map_data.get('room_names', [])
        if room_names:
            legend_height = 50 + ((len(room_names) - 1) // 4 + 1) * 40
        else:
            legend_height = 0
        
        _LOGGER.info(f"Map: {map_width}x{map_height}, multiple={multiple}, legend_height={legend_height}")
        
        # 4. Масштабируем обратно к оригинальным координатам
        original_x1 = int(round((x1) / multiple))
        original_x2 = int(round((x2) / multiple))
        original_y1 = int(round((y1 - legend_height) / multiple))
        original_y2 = int(round((y2 - legend_height) / multiple))
        
        # 5. Приводим к правильному порядку
        if original_x1 > original_x2:
            original_x1, original_x2 = original_x2, original_x1
        if original_y1 > original_y2:
            original_y1, original_y2 = original_y2, original_y1
        
        # 6. Проверка границ
        if original_x1 < 0 or original_y1 < 0 or original_x2 > map_width or original_y2 > map_height:
            _LOGGER.error(f"Zone out of bounds! Map: {map_width}x{map_height}, Zone: ({original_x1},{original_y1})-({original_x2},{original_y2})")
            return False
        
        _LOGGER.info(f"Converted zone: ({original_x1},{original_y1})-({original_x2},{original_y2})")
        
        # 7. Отправляем команду с оригинальными координатами
        try:
            from custom_components.neatsvor.liboshome.mqtt.zone_encoder import encode_zone_clean_command
            
            await self._send_dp_command('mode', 3)
            await asyncio.sleep(0.3)
            
            command_bytes = await encode_zone_clean_command(
                self._encoder,
                original_x1, original_y1,
                original_x2, original_y2,
                repeats,
                origin_x=self._map_origin_x,
                origin_y=self._map_origin_y,
                map_height=map_height
            )
            
            await self._command_sender.publish_command(command_bytes)
            _LOGGER.info(f"Zone cleaning command sent with original coords: ({original_x1},{original_y1})-({original_x2},{original_y2})")
            return True
            
        except Exception as e:
            _LOGGER.error(f"Zone cleaning error: {e}", exc_info=True)
            return False

    async def multiple_zones_clean(self, zones: List[Tuple[int, int, int, int, int]]) -> bool:
        """
        Clean multiple zones.

        Args:
            zones: List of zones, each = (x1, y1, x2, y2, repeats)
        """
        _LOGGER.info("Cleaning %s zones", len(zones))

        try:
            from custom_components.neatsvor.liboshome.mqtt.zone_encoder import encode_multiple_zones_command

            command_bytes = await encode_multiple_zones_command(self._encoder, zones)
            await self._command_sender.publish_command(command_bytes)

            _LOGGER.info("Command for %s zones sent", len(zones))
            return True

        except Exception as e:
            _LOGGER.error("Error cleaning multiple zones: %s", e)
            return False

    # ------------------------------------------------------------------
    # Data and statistics
    # ------------------------------------------------------------------

    async def _cache_device_image(self, image_url: str) -> Optional[str]:
        """Download and cache device image."""
        try:
            images_dir = Path(__file__).parent.parent / "images"
            images_dir.mkdir(exist_ok=True, parents=True)

            safe_mac = self.info.mac.replace(':', '_').replace('-', '_')
            image_path = images_dir / f"{safe_mac}.png"

            if image_path.exists():
                _LOGGER.debug("Image already cached: %s", image_path)
                return str(image_path)

            _LOGGER.info("Downloading device image: %s", image_url)
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(image_path, 'wb') as f:
                            await f.write(await resp.read())
                        _LOGGER.info("Image saved: %s", image_path)
                        return str(image_path)
                    else:
                        _LOGGER.warning("Failed to download image: %s", resp.status)
                        return None

        except Exception as e:
            _LOGGER.error("Error caching device image: %s", e)
            return None

    async def load_consumables(self) -> bool:
        """Load consumables information."""
        if not self.rest or not self.info:
            return False

        try:
            total_stats = await self.rest.get_clean_sum(self.info.device_id)
            total_hours = total_stats.get("cleanLength", 0) / 3600 if total_stats else 0
            _LOGGER.debug("Total hours: %s", total_hours)

            consume_data = await self.rest.get_consumables(self.info.device_id)
            _LOGGER.debug("Raw consume data: %s", consume_data)

            if consume_data:
                self.state.sensors.update_consumables(consume_data, total_hours)
                _LOGGER.debug("Loaded consumables: %s", self.state.sensors.consumables)
                return True
        except Exception as e:
            _LOGGER.error("Error loading consumables: %s", e)

        return False

    async def get_cleaning_history(self, limit: int = 20) -> List:
        """Get cleaning history."""
        if not self.clean_history or not self.info:
            return []
        return await self.clean_history.get_clean_history(self.info.device_id, limit)

    async def get_cloud_maps(self, limit: int = 10) -> List:
        """Get list of cloud maps."""
        if not self.cloud_maps or not self.info:
            return []
        return await self.cloud_maps.get_map_list(self.info.device_id, limit)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def status(self) -> Dict[str, Any]:
        """Current device state."""
        return {
            'battery': self.state.sensors.battery,
            'status': self.state.sensors.status or "unknown",
            'charging': self.state.sensors.charging if self.state.sensors.charging is not None else False,
            'clean_time': self.state.sensors.clean_time_min,
            'clean_area': self.state.sensors.clean_area_m2,
            'online': self._connected,
            'consumables': self.state.sensors.consumables,
            'water_level': self.state.sensors.water_level
        }

    @property
    def is_connected(self) -> bool:
        """Whether device is connected."""
        return self._connected

    @property
    def is_initialized(self) -> bool:
        """Whether device is initialized."""
        return self._initialized

    @property
    def name(self) -> str:
        """Device name."""
        return self.info.name if self.info else "Unknown"

    @property
    def mac(self) -> str:
        """MAC address."""
        return self.info.mac if self.info else ""

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_map(self, callback: Callable[[Dict], Awaitable[None]]):
        """Subscribe to map updates."""
        self._map_callbacks.append(callback)
        _LOGGER.debug("Added map callback, total: %s", len(self._map_callbacks))
        return callback

    def on_state(self, callback: Callable[[Dict], Awaitable[None]]):
        """Subscribe to state updates."""
        self._state_callbacks.append(callback)
        return callback

    def on_dp(self, callback: Callable[[List], Awaitable[None]]):
        """Subscribe to DP updates."""
        self._dp_callbacks.append(callback)
        return callback