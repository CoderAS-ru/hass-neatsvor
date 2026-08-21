"""
Encoder for room cleaning.
Uses existing encoder from mqtt.encoder.
"""

import logging
from typing import List, Dict, Any

_LOGGER = logging.getLogger(__name__)


def encode_room_clean_command(encoder, room_ids: List[int], dp_id: int = 31) -> bytes:
    """
    Create command for room cleaning using existing encoder.

    Args:
        encoder: NeatsvorEncoder instance
        room_ids: List of room IDs (e.g. [16, 17, 18])
        dp_id: DP ID (31 for room_clean, 45 for room_clean_attr)

    Returns:
        GZip-compressed command bytes for sending
    """
    try:
        # Import protobuf
        from custom_components.neatsvor.liboshome.protobuf import sweeper_com_pb2 as sweeper
        from google.protobuf import any_pb2

        # Create RoomAttrs
        room_attrs = sweeper.RoomAttrs()

        for room_id in room_ids:
            attr = room_attrs.attrs.add()
            attr.room_id = room_id
            attr.fan_level = sweeper.FanLevel.kFanNormal  # 2 = normal
            attr.tank_level = sweeper.TankLevel.kTankMiddle  # 2 = middle
            attr.clean_mode = 2  # standard cleaning
            attr.clean_times = 1

        # Pack into Any
        body_any = any_pb2.Any()
        body_any.Pack(room_attrs, "type.googleapis.com/sweeper.Rooms")

        # Use existing encoder
        # For type 3 pass serialized Any as bytes
        command = encoder.create_dp_command(dp_id, body_any.SerializeToString())

        _LOGGER.info("Created room cleaning command for rooms %s, DP %s", room_ids, dp_id)
        _LOGGER.debug("Command size: %s bytes", len(command))

        return command

    except Exception as e:
        _LOGGER.error("Error creating room cleaning command: %s", e)
        raise