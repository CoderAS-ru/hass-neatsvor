"""Zone cleaning encoder for MQTT."""

import logging
from google.protobuf import any_pb2

_LOGGER = logging.getLogger(__name__)

DP_ZONE_CLEAN = 32
COORDINATE_SCALE = 10


async def encode_zone_clean_command(encoder, x1: int, y1: int, x2: int, y2: int,
                                     repeats: int = 1,
                                     origin_x: int = 0,
                                     origin_y: int = 0,
                                     map_height: int = None,
                                     resolution_cm: float = 6.0) -> bytes:
    """
    Create zone cleaning command with origin support.
    
    Координаты в ПИКСЕЛЯХ карты (относительные).
    Origin добавляется к координатам перед отправкой.
    """
    try:
        from custom_components.neatsvor.liboshome.protobuf import sweeper_com_pb2

        # Масштабируем (как в Java: Math.round(f * 10))
        scaled_x1 = int(round(x1 * 10))
        scaled_y1 = int(round(y1 * 10))
        scaled_x2 = int(round(x2 * 10))
        scaled_y2 = int(round(y2 * 10))

        # Приводим к правильному порядку
        final_x1 = min(scaled_x1, scaled_x2) + origin_x
        final_y1 = min(scaled_y1, scaled_y2) + origin_y
        final_x2 = max(scaled_x1, scaled_x2) + origin_x
        final_y2 = max(scaled_y1, scaled_y2) + origin_y

        _LOGGER.info(
            "Zone: pixels(%d,%d)-(%d,%d) -> with origin(%d,%d): final(%d,%d)-(%d,%d), repeats=%d",
            x1, y1, x2, y2, origin_x, origin_y,
            final_x1, final_y1, final_x2, final_y2, repeats
        )

        # Создаем ZoneClean
        zone_clean = sweeper_com_pb2.ZoneClean()
        zone_clean.times = repeats

        polygon = zone_clean.zones.add()
        polygon.number = 4

        # Точки по часовой стрелке
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

        # Упаковываем
        body_any = any_pb2.Any()
        body_any.Pack(zone_clean, "type.googleapis.com/sweeper.ZoneClean")

        command = encoder.create_dp_command(32, body_any.SerializeToString())
        return command

    except Exception as e:
        _LOGGER.error("Failed to create zone clean command: %s", e, exc_info=True)
        raise