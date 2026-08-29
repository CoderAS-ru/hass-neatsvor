"""Zone cleaning encoder for MQTT."""

import logging
from typing import List, Tuple
from google.protobuf import any_pb2

_LOGGER = logging.getLogger(__name__)

COORDINATE_SCALE = 10


async def encode_zone_clean_command(encoder, dp_id: int, x1: int, y1: int, x2: int, y2: int,
                                     repeats: int = 1,
                                     origin_x: int = 0,
                                     origin_y: int = 0,
                                     map_height: int = None,
                                     already_scaled: bool = True) -> bytes:
    """
    Create zone cleaning command with origin support.
    
    Args:
        x1, y1, x2, y2: Zone coordinates
        repeats: Number of cleaning passes
        origin_x, origin_y: Map origin offset
        already_scaled: If True, coordinates are already in cells (no scaling needed)
                       If False, coordinates are in pixels and need scaling
    """
    _LOGGER.warning("=== ENCODE ZONE CLEAN CALLED ===")
    _LOGGER.warning("Input: x1=%s, y1=%s, x2=%s, y2=%s, repeats=%s, already_scaled=%s", 
                   x1, y1, x2, y2, repeats, already_scaled)
    
    try:
        from custom_components.neatsvor.liboshome.protobuf import sweeper_com_pb2

        _LOGGER.info("Zone clean: x1=%s, y1=%s, x2=%s, y2=%s, repeats=%s", x1, y1, x2, y2, repeats)
        _LOGGER.info("Origin: x=%s, y=%s", origin_x, origin_y)

        # Применяем origin
        final_x1 = x1 + origin_x
        final_y1 = y1 + origin_y
        final_x2 = x2 + origin_x
        final_y2 = y2 + origin_y

        _LOGGER.info("After origin: final(%d,%d)-(%d,%d)", final_x1, final_y1, final_x2, final_y2)

        # Масштабируем только если координаты НЕ в ячейках
        if already_scaled:
            # Координаты уже в ячейках — используем как есть
            scaled_x1 = final_x1
            scaled_y1 = final_y1
            scaled_x2 = final_x2
            scaled_y2 = final_y2
            _LOGGER.info("Coordinates already in cells, no scaling applied")
        else:
            # Координаты в пикселях — масштабируем
            scaled_x1 = int(round(final_x1 * COORDINATE_SCALE))
            scaled_y1 = int(round(final_y1 * COORDINATE_SCALE))
            scaled_x2 = int(round(final_x2 * COORDINATE_SCALE))
            scaled_y2 = int(round(final_y2 * COORDINATE_SCALE))
            _LOGGER.info("Coordinates scaled by %s", COORDINATE_SCALE)

        # Убеждаемся, что координаты в правильном порядке
        final_scaled_x1 = min(scaled_x1, scaled_x2)
        final_scaled_y1 = min(scaled_y1, scaled_y2)
        final_scaled_x2 = max(scaled_x1, scaled_x2)
        final_scaled_y2 = max(scaled_y1, scaled_y2)

        _LOGGER.info("Final zone: (%d,%d)-(%d,%d)", final_scaled_x1, final_scaled_y1, final_scaled_x2, final_scaled_y2)

        zone_clean = sweeper_com_pb2.ZoneClean()
        zone_clean.times = repeats

        polygon = zone_clean.zones.add()
        polygon.number = 4

        # Points in clockwise order
        p1 = polygon.points.add()
        p1.x = final_scaled_x1
        p1.y = final_scaled_y1

        p2 = polygon.points.add()
        p2.x = final_scaled_x2
        p2.y = final_scaled_y1

        p3 = polygon.points.add()
        p3.x = final_scaled_x2
        p3.y = final_scaled_y2

        p4 = polygon.points.add()
        p4.x = final_scaled_x1
        p4.y = final_scaled_y2

        # Pack into Any with correct type
        body_any = any_pb2.Any()
        body_any.Pack(zone_clean, "type.googleapis.com/sweeper.ZoneClean")
        
        _LOGGER.warning(f"=== FINAL ENCODED ===")
        _LOGGER.warning(f"Final: ({final_scaled_x1},{final_scaled_y1})-({final_scaled_x2},{final_scaled_y2})")

        return encoder.create_dp_command(dp_id, body_any.SerializeToString())

    except Exception as e:
        _LOGGER.error("Failed to create zone clean command: %s", e, exc_info=True)
        raise


async def encode_multiple_zones_command(encoder, dp_id: int, 
                                         zones: List[Tuple[int, int, int, int, int]],
                                         origin_x: int = 0,
                                         origin_y: int = 0,
                                         already_scaled: bool = True) -> bytes:
    """Create multiple zones cleaning command with origin support."""
    try:
        from custom_components.neatsvor.liboshome.protobuf import sweeper_com_pb2
        from google.protobuf import any_pb2

        _LOGGER.info("Encoding %s zones with origin(%s,%s), already_scaled=%s", 
                    len(zones), origin_x, origin_y, already_scaled)

        zone_clean = sweeper_com_pb2.ZoneClean()
        if zones:
            zone_clean.times = zones[0][4] if len(zones[0]) > 4 else 1

        for idx, zone in enumerate(zones):
            if len(zone) < 4:
                _LOGGER.warning("Skipping invalid zone: %s", zone)
                continue
                
            x1, y1, x2, y2 = zone[:4]
            repeats = zone[4] if len(zone) > 4 else 1

            # Apply origin
            final_x1 = x1 + origin_x
            final_y1 = y1 + origin_y
            final_x2 = x2 + origin_x
            final_y2 = y2 + origin_y

            # Scale only if not already in cells
            if already_scaled:
                scaled_x1 = final_x1
                scaled_y1 = final_y1
                scaled_x2 = final_x2
                scaled_y2 = final_y2
            else:
                scaled_x1 = int(round(final_x1 * COORDINATE_SCALE))
                scaled_y1 = int(round(final_y1 * COORDINATE_SCALE))
                scaled_x2 = int(round(final_x2 * COORDINATE_SCALE))
                scaled_y2 = int(round(final_y2 * COORDINATE_SCALE))

            final_scaled_x1 = min(scaled_x1, scaled_x2)
            final_scaled_y1 = min(scaled_y1, scaled_y2)
            final_scaled_x2 = max(scaled_x1, scaled_x2)
            final_scaled_y2 = max(scaled_y1, scaled_y2)

            polygon = zone_clean.zones.add()
            polygon.number = 4

            p1 = polygon.points.add()
            p1.x = final_scaled_x1
            p1.y = final_scaled_y1

            p2 = polygon.points.add()
            p2.x = final_scaled_x2
            p2.y = final_scaled_y1

            p3 = polygon.points.add()
            p3.x = final_scaled_x2
            p3.y = final_scaled_y2

            p4 = polygon.points.add()
            p4.x = final_scaled_x1
            p4.y = final_scaled_y2

            _LOGGER.info("Zone %s: final(%d,%d)-(%d,%d), repeats=%d", 
                         idx, final_scaled_x1, final_scaled_y1, final_scaled_x2, final_scaled_y2, repeats)

        body_any = any_pb2.Any()
        body_any.Pack(zone_clean, "type.googleapis.com/sweeper.ZoneClean")

        return encoder.create_dp_command(dp_id, body_any.SerializeToString())

    except Exception as e:
        _LOGGER.error("Failed to create multiple zones command: %s", e, exc_info=True)
        raise