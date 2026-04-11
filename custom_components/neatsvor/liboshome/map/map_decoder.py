"""Map decoder for Neatsvor."""

import gzip
import numpy as np
from typing import Dict, Any, List, Tuple
import struct
import aiofiles
import asyncio

import os
import sys

proto_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'protobuf')
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

try:
    import sweeper_map_pb2
    HAS_PROTOBUF = True
except ImportError as e:
    print(f"Error importing protobuf from {proto_dir}: {e}")
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

        print(f"Loaded {len(data)} bytes")

        # Parse protobuf in executor
        map_data = await loop.run_in_executor(None, _parse_map_data, data)

        print(f"Map: {map_data.width}x{map_data.height}")
        print(f"Resolution: {map_data.resolution}")

        if not map_data.HasField('map_info'):
            raise ValueError("No map data in map_info")

        # Decode raster data
        map_array, rooms, walls = MapDecoder._decode_cells(
            map_data.map_info.data,
            map_data.width,
            map_data.height
        )

        # Extract trajectory with filter (-1, -1)
        trajectory_points = []
        if map_data.HasField('trace_info'):
            for trace_data in map_data.trace_info.data:
                for point in trace_data.points:
                    if point.x != -1 or point.y != -1:
                        trajectory_points.append((point.x, point.y))

        print(f"Trajectory: {len(trajectory_points)} points (after filtering (-1,-1))")

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
    def decode_app_map(filepath: str) -> Dict[str, Any]:
        """Decode appMap.bv file (synchronous version)."""
        if not HAS_PROTOBUF:
            raise ImportError("Protobuf modules not loaded")

        with gzip.open(filepath, 'rb') as f:
            data = f.read()

        print(f"Loaded {len(data)} bytes")

        # Parse as MapData
        map_data = sweeper_map_pb2.MapData()
        map_data.ParseFromString(data)

        print(f"Map: {map_data.width}x{map_data.height}")
        print(f"Resolution: {map_data.resolution}")

        # Check for map data
        if not map_data.HasField('map_info'):
            raise ValueError("No map data in map_info")

        # Decode raster data
        map_array, rooms, walls = MapDecoder._decode_cells(
            map_data.map_info.data,
            map_data.width,
            map_data.height
        )

        # Extract trajectory with filter (-1, -1)
        trajectory_points = []
        if map_data.HasField('trace_info'):
            for trace_data in map_data.trace_info.data:
                for point in trace_data.points:
                    # FILTER: skip points with coordinates (-1, -1)
                    if point.x != -1 or point.y != -1:
                        trajectory_points.append((point.x, point.y))

        print(f"Trajectory: {len(trajectory_points)} points (after filtering (-1,-1))")

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
            'map_array': map_array,  # numpy array with cell_value
            'rooms': rooms,  # dictionary room_id -> list of cells
            'walls': walls,  # list of walls
            'trajectory': trajectory_points,  # filtered trajectory points
            'robot_position': robot_pos,
            'charger_position': charger_pos,
            'room_names': room_info,
            'origin': origin,
            'map_process_type': map_data.map_process_type,
            'raw': map_data  # raw protobuf data for working with trace_info.data
        }

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

            print(f"DevMap archive: {len(archive)} files")
            return archive

        except Exception as e:
            print(f"Error decoding devMap: {e}")
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

        print(f"Decoded: {len(data_list)} cells, {len(rooms)} rooms, {len(walls)} walls")
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

        print(f"Trajectory: {len(trajectory)} points (after filtering (-1,-1))")
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

        print(f"Data size: {len(data)} bytes")
        print(f"First 50 bytes (hex): {data[:50].hex()}")

        # Try different protobuf messages
        try:
            # Try as MapData
            map_data = sweeper_map_pb2.MapData()
            map_data.ParseFromString(data[:1000])  # Parse only part

            print("\n✅ Successfully parsed as MapData")
            print(f"  Width: {map_data.width}")
            print(f"  Height: {map_data.height}")
            print(f"  Resolution: {map_data.resolution}")

            if map_data.HasField('map_info'):
                print(f"  Map data: {len(map_data.map_info.data)} values")

            if map_data.HasField('trace_info'):
                print(f"  Trace segments: {len(map_data.trace_info.data)}")
                total_points = sum(len(td.points) for td in map_data.trace_info.data)
                print(f"  Total trace points: {total_points}")

            return True

        except Exception as e:
            print(f"Not MapData: {e}")

        try:
            # Try as MqttMsgMap
            msg = sweeper_map_pb2.MqttMsgMap()
            msg.ParseFromString(data[:1000])
            print("\n✅ Successfully parsed as MqttMsgMap")
            return True
        except Exception as e:
            print(f"Not MqttMsgMap: {e}")

        return False

    @staticmethod
    def decode_mqtt_map(payload: bytes):
        """
        Decode map from MQTT message (new format with Any wrapper).
        Returns same format as decode_app_map().
        """
        if not HAS_PROTOBUF:
            raise ImportError("Protobuf modules not loaded")

        print(f"[MapDecoder] Received MQTT: {len(payload)} bytes")

        # 1. Decompress GZIP if needed
        if len(payload) >= 2 and payload[:2] == b'\x1f\x8b':
            try:
                import gzip
                payload = gzip.decompress(payload)
                print(f"[MapDecoder] Decompressed GZIP: {len(payload)} bytes")
            except Exception as e:
                print(f"[MapDecoder] GZIP decompression error: {e}")

        # 2. Now payload starts with 0a181211... (as in parse_any_protobuf.py)
        #    This is a message with two fields: MAC and Any
        print(f"[MapDecoder] HEX start: {payload[:30].hex()}")

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

                print(f"[MapDecoder] Any length: {any_length} bytes")

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
                    print(f"[MapDecoder] Type URL skipped: {url_length} bytes")

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

                    print(f"[MapDecoder] Value length: {value_length} bytes")

                    # 7. Extract map data
                    map_data_bytes = payload[offset:offset + value_length]
                    print(f"[MapDecoder] Map data: {len(map_data_bytes)} bytes")
                    print(f"[MapDecoder] Map HEX: {map_data_bytes[:20].hex()}")

                    # 8. Parse as MapData
                    map_data = sweeper_map_pb2.MapData()
                    map_data.ParseFromString(map_data_bytes)

                    print(f"[MapDecoder] ✅ Success! Map: {map_data.width}x{map_data.height}")

                    # 9. Use helper method to convert
                    return MapDecoder._protobuf_to_dict(map_data)

        except Exception as e:
            print(f"[MapDecoder] Parse error: {e}")
            import traceback
            traceback.print_exc()

        # If the new scheme didn't work, try parsing directly
        try:
            print(f"[MapDecoder] Trying direct parsing...")
            map_data = sweeper_map_pb2.MapData()
            map_data.ParseFromString(payload)

            if map_data.width > 0 and map_data.height > 0:
                print(f"[MapDecoder] ✅ Direct parsing: {map_data.width}x{map_data.height}")
                return MapDecoder._protobuf_to_dict(map_data)
        except:
            pass

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

        print(f"Trace segments: {len(segments)}")
        return segments