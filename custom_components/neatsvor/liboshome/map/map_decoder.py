"""Map decoder for Neatsvor."""

import gzip
import logging
import numpy as np
from typing import Dict, Any, List, Tuple
import struct
import aiofiles
import asyncio

import os
import sys

_LOGGER = logging.getLogger(__name__)

proto_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'protobuf')
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

try:
    import sweeper_map_pb2
    HAS_PROTOBUF = True
except ImportError as e:
    _LOGGER.error("Error importing protobuf from %s: %s", proto_dir, e)
    HAS_PROTOBUF = False


def _parse_map_data(data: bytes):
    """Helper function for parsing protobuf."""
    map_data = sweeper_map_pb2.MapData()
    map_data.ParseFromString(data)
    return map_data


class MapDecoder:
    """Map decoder for Neatsvor maps."""

    @staticmethod
    async def decode_app_map_async(filepath: str) -> Dict[str, Any]:
        """Asynchronous version of appMap.bv file decoding."""
        if not HAS_PROTOBUF:
            raise ImportError("Protobuf modules not loaded")

        # Read file asynchronously
        async with aiofiles.open(filepath, 'rb') as f:
            compressed = await f.read()

        # Decompress gzip in executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, gzip.decompress, compressed)

        _LOGGER.debug("Loaded %s bytes", len(data))

        # Parse protobuf in executor
        map_data = await loop.run_in_executor(None, _parse_map_data, data)

        _LOGGER.debug("Map: %sx%s", map_data.width, map_data.height)
        _LOGGER.debug("Resolution: %s", map_data.resolution)

        if not map_data.HasField('map_info'):
            raise ValueError("No map data in map_info")

        # Use shared conversion method
        return MapDecoder._protobuf_to_dict(map_data)

    @staticmethod
    def decode_app_map(filepath: str) -> Dict[str, Any]:
        """Decode appMap.bv file (synchronous version)."""
        if not HAS_PROTOBUF:
            raise ImportError("Protobuf modules not loaded")

        with gzip.open(filepath, 'rb') as f:
            data = f.read()

        _LOGGER.debug("Loaded %s bytes", len(data))

        # Parse as MapData
        map_data = sweeper_map_pb2.MapData()
        map_data.ParseFromString(data)

        _LOGGER.debug("Map: %sx%s", map_data.width, map_data.height)
        _LOGGER.debug("Resolution: %s", map_data.resolution)

        # Check for map data
        if not map_data.HasField('map_info'):
            raise ValueError("No map data in map_info")

        # Use shared conversion method
        return MapDecoder._protobuf_to_dict(map_data)

    @staticmethod
    def decode_dev_map(filepath: str) -> Dict[str, str]:
        """Decode devMap.bv archive."""
        import tarfile
        import io

        try:
            with gzip.open(filepath, 'rb') as f:
                tar_data = f.read()

            archive = {}
            with tarfile.open(fileobj=io.BytesIO(tar_data), mode='r:gz') as tar:
                for member in tar.getmembers():
                    if member.isfile():
                        f = tar.extractfile(member)
                        if f:
                            content = f.read()
                            try:
                                # Try to decode as text
                                archive[member.name] = content.decode('utf-8')
                            except UnicodeDecodeError:
                                # If not text, save as hex
                                archive[member.name] = content.hex()

            _LOGGER.debug("DevMap archive: %s files", len(archive))
            return archive

        except Exception as e:
            _LOGGER.error("Error decoding devMap: %s", e)
            return {}

    @staticmethod
    def _decode_cells(data_list, width: int, height: int):
        """Decode map cells as in map_system0.py."""
        map_array = np.zeros((height, width), dtype=np.uint8)
        rooms = {}
        walls = []

        for i, cell_value in enumerate(data_list):
            cell_x = i % width
            cell_y = i // width

            # Save value
            map_array[cell_y, cell_x] = cell_value

            # Extract type and room ID
            cell_type = cell_value & 0b11
            room_id = (cell_value >> 2) & 0b111111

            if cell_type == 1:  # Floor/room cell
                if room_id not in rooms:
                    rooms[room_id] = []
                rooms[room_id].append((cell_x, cell_y))
            elif cell_type == 2:  # Wall
                walls.append((cell_x, cell_y))

        _LOGGER.debug("Decoded: %s cells, %s rooms, %s walls", len(data_list), len(rooms), len(walls))
        return map_array, rooms, walls

    @staticmethod
    def _extract_trajectory(trace_info):
        """Extract trajectory, filtering points (-1, -1)."""
        trajectory = []
        if trace_info and trace_info.data:
            for trace_data in trace_info.data:
                for point in trace_data.points:
                    # FILTER: skip points with coordinates (-1, -1)
                    if point.x != -1 or point.y != -1:
                        trajectory.append((point.x, point.y))

        _LOGGER.debug("Trajectory: %s points (after filtering (-1,-1))", len(trajectory))
        return trajectory

    @staticmethod
    def _extract_position(point_proto):
        """Extract position from protobuf."""
        if point_proto and (point_proto.x != 0 or point_proto.y != 0):
            return {
                'x': point_proto.x,
                'y': point_proto.y,
                'angle': getattr(point_proto, 'angle', 0)
            }
        return None

    @staticmethod
    def analyze_file(filepath: str):
        """Analyze .bv file."""
        with gzip.open(filepath, 'rb') as f:
            data = f.read()

        _LOGGER.info("Data size: %s bytes", len(data))
        _LOGGER.debug("First 50 bytes (hex): %s", data[:50].hex())

        # Try different protobuf messages
        try:
            # Try as MapData
            map_data = sweeper_map_pb2.MapData()
            map_data.ParseFromString(data[:1000])  # Parse only part

            _LOGGER.info("Successfully parsed as MapData")
            _LOGGER.info("  Width: %s", map_data.width)
            _LOGGER.info("  Height: %s", map_data.height)
            _LOGGER.info("  Resolution: %s", map_data.resolution)

            if map_data.HasField('map_info'):
                _LOGGER.info("  Map data: %s values", len(map_data.map_info.data))

            if map_data.HasField('trace_info'):
                _LOGGER.info("  Trace segments: %s", len(map_data.trace_info.data))
                total_points = sum(len(td.points) for td in map_data.trace_info.data)
                _LOGGER.info("  Total trace points: %s", total_points)

            return True

        except Exception as e:
            _LOGGER.debug("Not MapData: %s", e)

        try:
            # Try as MqttMsgMap
            msg = sweeper_map_pb2.MqttMsgMap()
            msg.ParseFromString(data[:1000])
            _LOGGER.info("Successfully parsed as MqttMsgMap")
            return True
        except Exception as e:
            _LOGGER.debug("Not MqttMsgMap: %s", e)

        return False

    @staticmethod
    def decode_mqtt_map(payload: bytes):
        """
        Decode map from MQTT message (new format with Any wrapper).
        Returns same format as decode_app_map().
        """
        if not HAS_PROTOBUF:
            raise ImportError("Protobuf modules not loaded")

        _LOGGER.debug("Received MQTT: %s bytes", len(payload))

        # 1. Decompress GZIP if needed
        if len(payload) >= 2 and payload[:2] == b'\x1f\x8b':
            try:
                import gzip
                payload = gzip.decompress(payload)
                _LOGGER.debug("Decompressed GZIP: %s bytes", len(payload))
            except Exception as e:
                _LOGGER.debug("GZIP decompression error: %s", e)

        # 2. Now payload starts with 0a181211... (as in parse_any_protobuf.py)
        #    This is a message with two fields: MAC and Any
        _LOGGER.debug("HEX start: %s", payload[:30].hex())

        try:
            # 3. Parse structure: [field1: MAC][field2: Any]
            offset = 0

            # Skip first field (MAC address)
            # tag=0x0a (field=1, wire_type=2), length=0x18 (24 bytes)
            if payload[0] == 0x0a and payload[1] == 0x18:
                offset = 2 + 24  # tag + length + MAC data

            # 4. Now parse second field (Any message)
            if offset < len(payload) and payload[offset] == 0x12:
                offset += 1  # tag of second field (0x12)

                # Read Any message length (varint)
                any_length = 0
                shift = 0
                while offset < len(payload):
                    byte = payload[offset]
                    offset += 1
                    any_length |= (byte & 0x7F) << shift
                    if not (byte & 0x80):
                        break
                    shift += 7

                _LOGGER.debug("Any length: %s bytes", any_length)

                # 5. Parse Any: [type_url][value]
                # Skip type_url (field=1 in Any)
                if offset < len(payload) and payload[offset] == 0x0a:
                    offset += 1  # tag type_url

                    # Read type_url length
                    url_length = 0
                    shift = 0
                    while offset < len(payload):
                        byte = payload[offset]
                        offset += 1
                        url_length |= (byte & 0x7F) << shift
                        if not (byte & 0x80):
                            break
                        shift += 7

                    offset += url_length  # Skip the URL itself
                    _LOGGER.debug("Type URL skipped: %s bytes", url_length)

                # 6. Now value (field=2 in Any) - THIS IS THE ACTUAL MAP DATA!
                if offset < len(payload) and payload[offset] == 0x12:
                    offset += 1  # tag value

                    # Read value length
                    value_length = 0
                    shift = 0
                    while offset < len(payload):
                        byte = payload[offset]
                        offset += 1
                        value_length |= (byte & 0x7F) << shift
                        if not (byte & 0x80):
                            break
                        shift += 7

                    _LOGGER.debug("Value length: %s bytes", value_length)

                    # 7. Extract map data
                    map_data_bytes = payload[offset:offset + value_length]
                    _LOGGER.debug("Map data: %s bytes", len(map_data_bytes))
                    _LOGGER.debug("Map HEX: %s", map_data_bytes[:20].hex())

                    # 8. Parse as MapData
                    map_data = sweeper_map_pb2.MapData()
                    map_data.ParseFromString(map_data_bytes)

                    _LOGGER.info("Success! Map: %sx%s", map_data.width, map_data.height)

                    # 9. Use helper method to convert
                    return MapDecoder._protobuf_to_dict(map_data)

        except Exception as e:
            _LOGGER.debug("Parse error: %s", e)
            import traceback
            _LOGGER.debug("Traceback: %s", traceback.format_exc())

        # If the new scheme didn't work, try parsing directly
        try:
            _LOGGER.debug("Trying direct parsing...")
            map_data = sweeper_map_pb2.MapData()
            map_data.ParseFromString(payload)

            if map_data.width > 0 and map_data.height > 0:
                _LOGGER.debug("Direct parsing: %sx%s", map_data.width, map_data.height)
                return MapDecoder._protobuf_to_dict(map_data)
        except Exception as e:
            _LOGGER.debug("Direct parsing failed: %s", e)

        raise ValueError("Failed to decode MQTT message as map")

    @staticmethod
    def _protobuf_to_dict(map_data):
        """
        Convert protobuf MapData to dictionary (like decode_app_map).
        """
        # Decode raster data
        map_array, rooms, walls = MapDecoder._decode_cells(
            map_data.map_info.data,
            map_data.width,
            map_data.height
        )

        # Extract trajectory
        trajectory_points = []
        if map_data.HasField('trace_info'):
            for trace_data in map_data.trace_info.data:
                for point in trace_data.points:
                    if point.x != -1 or point.y != -1:
                        trajectory_points.append((point.x, point.y))

        # Extract positions
        robot_pos = None
        charger_pos = None

        if map_data.HasField('trace_info') and map_data.trace_info.HasField('robot_position'):
            robot_pos = MapDecoder._extract_position(map_data.trace_info.robot_position)

        if map_data.HasField('map_info') and map_data.map_info.HasField('charger_position'):
            charger_pos = MapDecoder._extract_position(map_data.map_info.charger_position)

        # Extract rooms
        room_info = []
        if map_data.HasField('room_info'):
            for room_name in map_data.room_info.room_names:
                room_info.append({
                    'id': room_name.room_id,
                    'name': room_name.name
                })

        # Extract origin
        origin = {'x': 0, 'y': 0}
        if map_data.HasField('map_info') and map_data.map_info.HasField('origin'):
            origin['x'] = map_data.map_info.origin.x
            origin['y'] = map_data.map_info.origin.y

        return {
            'width': map_data.width,
            'height': map_data.height,
            'resolution': map_data.resolution,
            'map_array': map_array,
            'rooms': rooms,
            'walls': walls,
            'trajectory': trajectory_points,
            'robot_position': robot_pos,
            'charger_position': charger_pos,
            'room_names': room_info,
            'origin': origin,
            'map_process_type': map_data.map_process_type,
            'raw': map_data
        }

    @staticmethod
    def get_trace_segments(map_data: Dict[str, Any]) -> List[List[Tuple[int, int]]]:
        """Return trajectory segments separately (for drawing with breaks)."""
        if not map_data.get('raw') or not map_data['raw'].HasField('trace_info'):
            return []

        trace_info = map_data['raw'].trace_info
        segments = []

        for trace_data in trace_info.data:
            segment = []
            for point in trace_data.points:
                if point.x != -1 or point.y != -1:
                    segment.append((point.x, point.y))

            if len(segment) > 1:
                segments.append(segment)

        _LOGGER.debug("Trace segments: %s", len(segments))
        return segments