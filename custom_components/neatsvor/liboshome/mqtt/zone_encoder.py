"""Zone cleaning encoder for MQTT."""

import logging
from typing import List, Tuple
from google.protobuf import any_pb2

_LOGGER = logging.getLogger(__name__)

COORDINATE_SCALE = 10


async def encode_zone_clean_command(encoder, dp_id: int, x1: int, y1: int, x2: int, y2: int,
                                     repeats: int = 1) -> bytes:
    """
    Create zone cleaning command.
    
    Args:
        encoder: NeatsvorEncoder instance
        dp_id: DP ID for zone_clean (from dp_manager)
        x1, y1, x2, y2: Zone coordinates in robot's coordinate system
        repeats: Number of cleaning passes
    """
    try:
        from custom_components.neatsvor.liboshome.protobuf import sweeper_com_pb2

        scaled_x1 = int(round(x1 * COORDINATE_SCALE))
        scaled_y1 = int(round(y1 * COORDINATE_SCALE))
        scaled_x2 = int(round(x2 * COORDINATE_SCALE))
        scaled_y2 = int(round(y2 * COORDINATE_SCALE))

        final_x1 = min(scaled_x1, scaled_x2)
        final_y1 = min(scaled_y1, scaled_y2)
        final_x2 = max(scaled_x1, scaled_x2)
        final_y2 = max(scaled_y1, scaled_y2)

        _LOGGER.info("Zone: final(%d,%d)-(%d,%d), repeats=%d", final_x1, final_y1, final_x2, final_y2, repeats)

        zone_clean = sweeper_com_pb2.ZoneClean()
        zone_clean.times = repeats

        polygon = zone_clean.zones.add()
        polygon.number = 4

        p1 = polygon.points.add()
        p1.x = final_x1
        p1.y = final_y1

        p2 = polygon.points.add()
        p2.x = final_x2
        p2.y = final_y1

        p3 = polygon.points.add()
        p3.x = final_x2
        p3.y = final_y2

        p4 = polygon.points.add()
        p4.x = final_x1
        p4.y = final_y2

        body_any = any_pb2.Any()
        body_any.Pack(zone_clean)

        return encoder.create_dp_command(dp_id, body_any.SerializeToString())

    except Exception as e:
        _LOGGER.error("Failed to create zone clean command: %s", e, exc_info=True)
        raise


async def encode_multiple_zones_command(encoder, dp_id: int, zones: List[Tuple[int, int, int, int, int]]) -> bytes:
    """Create multiple zones cleaning command."""
    try:
        from custom_components.neatsvor.liboshome.protobuf import sweeper_com_pb2
        from google.protobuf import any_pb2

        zone_clean = sweeper_com_pb2.ZoneClean()
        if zones:
            zone_clean.times = zones[0][4] if len(zones[0]) > 4 else 1

        for zone in zones:
            x1, y1, x2, y2 = zone[:4]
            repeats = zone[4] if len(zone) > 4 else 1

            scaled_x1 = int(round(x1 * COORDINATE_SCALE))
            scaled_y1 = int(round(y1 * COORDINATE_SCALE))
            scaled_x2 = int(round(x2 * COORDINATE_SCALE))
            scaled_y2 = int(round(y2 * COORDINATE_SCALE))

            final_x1 = min(scaled_x1, scaled_x2)
            final_y1 = min(scaled_y1, scaled_y2)
            final_x2 = max(scaled_x1, scaled_x2)
            final_y2 = max(scaled_y1, scaled_y2)

            polygon = zone_clean.zones.add()
            polygon.number = 4

            p1 = polygon.points.add()
            p1.x = final_x1
            p1.y = final_y1

            p2 = polygon.points.add()
            p2.x = final_x2
            p2.y = final_y1

            p3 = polygon.points.add()
            p3.x = final_x2
            p3.y = final_y2

            p4 = polygon.points.add()
            p4.x = final_x1
            p4.y = final_y2

        body_any = any_pb2.Any()
        body_any.Pack(zone_clean)

        return encoder.create_dp_command(dp_id, body_any.SerializeToString())

    except Exception as e:
        _LOGGER.error("Failed to create multiple zones command: %s", e, exc_info=True)
        raise