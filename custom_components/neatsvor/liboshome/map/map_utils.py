"""Map utilities for Neatsvor."""

import logging
from typing import Tuple, Dict, Any, Optional
import asyncio
from pathlib import Path
import json
from datetime import datetime

_LOGGER = logging.getLogger(__name__)


def calculate_map_scale(width: int, height: int) -> int:
    """
    Calculate the appropriate map scale (multiple) based on map dimensions.
    
    This is the shared logic used by both map_renderer and vacuum zone cleaning.
    
    Args:
        width: Map width in pixels
        height: Map height in pixels
        
    Returns:
        int: Scale multiplier (2, 4, 6, or 8)
    """
    if width < 100 and height < 100:
        return 8
    elif width < 200 and height < 200:
        return 6
    elif width >= 300 or height >= 300:
        return 2
    else:
        return 4

def calculate_legend_height(room_count: int, has_presets: bool = True) -> int:
    """
    Calculate legend height based on number of rooms.

    Если has_presets=True — добавляется вторая строка под иконки пресетов.

    Args:
        room_count: Number of rooms on the map
        has_presets: Whether to reserve space for preset icons row

    Returns:
        int: Height of legend in pixels
    """
    if room_count == 0:
        return 0

    rows = (room_count - 1) // 4 + 1
    base_height = 50 + rows * 40

    if has_presets:
        # Вторая строка под иконки пресетов: 35px на строку
        base_height += 45

    return base_height
        
def calculate_zone_coordinates(x1: int, y1: int, x2: int, y2: int, 
                               origin_x: int, origin_y: int, 
                               resolution: int = 10) -> Tuple[int, int, int, int]:
    """
    Convert zone coordinates from app format to robot format.
    
    The robot expects coordinates relative to origin with resolution scaling.
    
    Args:
        x1, y1, x2, y2: Zone coordinates in app format
        origin_x, origin_y: Map origin coordinates
        resolution: Resolution divisor (default 10)
        
    Returns:
        Tuple of (x1, y1, x2, y2) in robot coordinate system
    """
    # Convert from app coordinates to robot coordinates with rounding
    robot_x1 = int(round((x1 - origin_x) / resolution))
    robot_y1 = int(round((y1 - origin_y) / resolution))
    robot_x2 = int(round((x2 - origin_x) / resolution))
    robot_y2 = int(round((y2 - origin_y) / resolution))
    
    return (robot_x1, robot_y1, robot_x2, robot_y2)
    
async def get_latest_realtime_png() -> Optional[Path]:
    """
    Get the latest realtime map PNG file from the realtime directory.
    
    Returns:
        Path to the latest PNG file or None if no files found.
    """
    realtime_dir = Path("/config/www/neatsvor/maps/realtime")
    if not realtime_dir.exists():
        return None
    
    try:
        # Используем asyncio.to_thread для неблокирующего чтения файловой системы
        png_files = await asyncio.to_thread(lambda: list(realtime_dir.glob("*.png")))
        if not png_files:
            return None
        
        # Сортируем по времени модификации, берём последний
        latest_file = max(png_files, key=lambda f: f.stat().st_mtime)
        return latest_file
    except Exception as e:
        _LOGGER.debug("Error getting latest realtime PNG: %s", e)
        return None
        
# =====================================================================
# DEBUG DUMPER — временный код для отладки трёх потоков карт.
# Управляется флагом DEBUG_MAPS в const.py.
# Удалить вместе с флагом, когда отладка закончится.
# =====================================================================

class MapDebugDumper:
    """
    Сохраняет полный читаемый дамп map_data в JSON рядом с PNG.

    Использование:
        MapDebugDumper.dump(map_data, map_type="realtime", identifier="live")
    """

    # Поля protobuf, которые не нужно писать целиком (слишком большие).
    # Для них пишем только длину / метаданные.
    _SKIP_BYTES_FIELDS = {"map_info.data"}  # repeated int32 растр

    @staticmethod
    def dump(map_data: Dict[str, Any], map_type: str, identifier: str,
             base_dir: str = "/config/www/neatsvor/maps") -> None:
        """
        Сохранить дамп map_data в {base_dir}/{map_type}/{ts}_{map_type}_{id}_raw.json

        Args:
            map_data: словарь от MapDecoder
            map_type: 'realtime' | 'cloud' | 'history'
            identifier: строка-идентификатор (live / device_map_id / record_id)
            base_dir: базовая папка maps
        """
        try:
            # Ленивая проверка флага — чтобы не тянуть const при импорте
            from custom_components.neatsvor.const import DEBUG_MAPS
            if not DEBUG_MAPS:
                return
        except Exception:
            return

        try:
            out_dir = Path(base_dir) / map_type
            out_dir.mkdir(parents=True, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{ts}_{map_type}_{identifier}_raw.json"
            out_path = out_dir / filename

            payload = {
                "map_type": map_type,
                "identifier": identifier,
                "timestamp": ts,
                "map_data": MapDebugDumper._serialize_map_data(map_data),
            }

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(
                    payload, f,
                    ensure_ascii=False,
                    default=str,
                    separators=(",", ":"),   # ← компактно, без пробелов
                )

            _LOGGER.info("MapDebugDumper: saved %s", out_path)

        except Exception as e:
            _LOGGER.error("MapDebugDumper error: %s", e, exc_info=True)

    @staticmethod
    def _serialize_map_data(map_data: Dict[str, Any]) -> Dict[str, Any]:
        """Сериализовать map_data, включая raw protobuf."""
        if not isinstance(map_data, dict):
            return {"error": f"map_data is not a dict: {type(map_data).__name__}"}

        result: Dict[str, Any] = {}

        # === Простые поля ===
        for key in ("width", "height", "resolution", "map_process_type"):
            if key in map_data:
                result[key] = map_data[key]

        # === origin ===
        if "origin" in map_data:
            result["origin"] = map_data["origin"]

        # === Позиции ===
        for key in ("robot_position", "charger_position"):
            if key in map_data and map_data[key]:
                result[key] = map_data[key]

        # === room_names: [{id, name}, ...] ===
        if "room_names" in map_data:
            result["room_names"] = map_data["room_names"]

        # === rooms: {room_id: [(x, y), ...]} ===
        # Пишем как {"1": [[x,y], ...], "2": [...]}
        if "rooms" in map_data:
            rooms_serialized = {}
            for room_id, cells in map_data["rooms"].items():
                rooms_serialized[str(room_id)] = [
                    [int(c[0]), int(c[1])] for c in cells
                ]
            result["rooms"] = rooms_serialized

        # === walls: [(x, y), ...] ===
        if "walls" in map_data:
            result["walls"] = [[int(c[0]), int(c[1])] for c in map_data["walls"]]

        # === trajectory: [(x, y), ...] ===
        if "trajectory" in map_data:
            result["trajectory"] = [
                [int(p[0]), int(p[1])] for p in map_data["trajectory"]
            ]

        # === map_array: numpy — НЕ пишем, избыточно (есть rooms/walls) ===
        if "map_array" in map_data:
            arr = map_data["map_array"]
            result["map_array_meta"] = {
                "shape": list(arr.shape) if hasattr(arr, "shape") else None,
                "dtype": str(arr.dtype) if hasattr(arr, "dtype") else None,
                "note": "полные данные не сохранены (избыточно)",
            }

        # === raw: protobuf — рекурсивно ===
        if "raw" in map_data:
            result["raw"] = MapDebugDumper._serialize_protobuf(map_data["raw"])

        return result

    @staticmethod
    def _serialize_protobuf(obj, depth: int = 0, max_depth: int = 20,
                            path: str = "raw") -> Any:
        """
        Рекурсивно обходит protobuf-объект через ListFields().

        Поведение:
          - скаляры → как есть
          - enum → {name, value}
          - вложенные сообщения → dict рекурсивно
          - repeated → список
          - bytes / large repeated int32 (map_info.data) → пропускаем, пишем meta
        """
        if depth > max_depth:
            return "<max depth>"

        # Защита от огромных repeated int32 (map_info.data)
        # Определяем по имени поля через path
        # (см. ниже — эта проверка вызывается ДО обхода)

        try:
            from google.protobuf.message import Message
        except Exception:
            # Если protobuf недоступен — вернём repr
            return repr(obj)

        if not isinstance(obj, Message):
            # Скаляр / bytes / enum / строка
            if isinstance(obj, bytes):
                return {
                    "_type": "bytes",
                    "length": len(obj),
                    "preview_hex": obj[:64].hex(),
                }
            if hasattr(obj, "name") and hasattr(obj, "value"):
                # Enum
                return {"_enum": obj.name, "value": obj.value}
            if isinstance(obj, (int, float, str, bool)) or obj is None:
                return obj
            return str(obj)

        # Это сообщение — обходим поля
        result: Dict[str, Any] = {}
        result["_type"] = obj.DESCRIPTOR.name

        for field, value in obj.ListFields():
            field_name = field.name
            field_path = f"{path}.{field_name}"

            # === Пропускаем гигантские поля ===
            if field_path == "raw.map_info.data":
                # repeated int32, десятки тысяч значений
                result[field_name] = {
                    "_skipped": True,
                    "reason": "large repeated int32 (raster)",
                    "length": len(value) if hasattr(value, "__len__") else None,
                }
                continue

            # === repeated поля ===
            if field.label == field.LABEL_REPEATED:
                items = []
                for item in value:
                    items.append(
                        MapDebugDumper._serialize_protobuf(
                            item, depth + 1, max_depth, field_path
                        )
                    )
                result[field_name] = items
                continue

            # === вложенное сообщение ===
            if field.type == field.TYPE_MESSAGE:
                result[field_name] = MapDebugDumper._serialize_protobuf(
                    value, depth + 1, max_depth, field_path
                )
                continue

            # === enum ===
            if field.type == field.TYPE_ENUM:
                enum_desc = field.enum_type
                enum_value = value
                # value — уже int
                enum_name = None
                for v in enum_desc.values:
                    if v.number == enum_value:
                        enum_name = v.name
                        break
                result[field_name] = {
                    "_enum": enum_name,
                    "value": enum_value,
                    "enum_type": enum_desc.name,
                }
                continue

            # === bytes ===
            if field.type == field.TYPE_BYTES:
                result[field_name] = {
                    "_type": "bytes",
                    "length": len(value),
                    "preview_hex": value[:64].hex(),
                }
                continue

            # === скаляры ===
            result[field_name] = value

        return result
        
# =====================================================================
# EXTRACTORS — единые функции для извлечения данных комнат из map_data.
# Используются всеми сенсорами, чтобы не дублировать логику.
# =====================================================================

def extract_room_presets(map_data: Dict[str, Any]) -> Dict[int, Dict[str, int]]:
    """
    Извлекает пресеты комнат из raw.room_info.room_attrs.

    Возвращает:
        {room_id: {'fan': int, 'water': int, 'times': int, 'mode': int}}

    Если raw или room_attrs отсутствуют — возвращает пустой dict.
    """
    presets: Dict[int, Dict[str, int]] = {}

    if not isinstance(map_data, dict):
        return presets

    raw = map_data.get('raw')
    if raw is None or not hasattr(raw, 'room_info'):
        return presets

    if not hasattr(raw.room_info, 'room_attrs'):
        return presets

    for attr in raw.room_info.room_attrs:
        presets[attr.room_id] = {
            'fan': attr.fan_level,
            'water': attr.tank_level,
            'times': attr.clean_times,
            'mode': attr.clean_mode,
        }

    return presets


def extract_room_names_map(map_data: Dict[str, Any]) -> Dict[int, str]:
    """
    Возвращает {room_id: name} из room_names.

    Если room_names отсутствует — возвращает пустой dict.
    """
    if not isinstance(map_data, dict):
        return {}
    return {r['id']: r['name'] for r in map_data.get('room_names', [])}
    
# =====================================================================
# DEBUG DUMPER CLEANUP — удаление устаревших debug-дампов.
# Работает только при DEBUG_MAPS = True.
# Удалить вместе с MapDebugDumper, когда отладка закончится.
# =====================================================================

def cleanup_old_debug_dumps(
    base_dir: str = "/config/www/neatsvor/maps",
    max_age_hours: int = 24,
) -> int:
    """
    Удаляет *_raw.json старше max_age_hours из realtime/, history/, cloud/.

    Возвращает количество удалённых файлов.
    """
    try:
        from custom_components.neatsvor.const import DEBUG_MAPS
        if not DEBUG_MAPS:
            return 0
    except Exception:
        return 0

    import time
    from pathlib import Path

    deleted = 0
    cutoff = time.time() - max_age_hours * 3600

    for sub in ("realtime", "history", "cloud"):
        sub_dir = Path(base_dir) / sub
        if not sub_dir.exists():
            continue

        try:
            # glob по подпапкам — файлы могут быть и в cloud/ (не только в cloud/json)
            for json_file in sub_dir.rglob("*_raw.json"):
                try:
                    if json_file.stat().st_mtime < cutoff:
                        json_file.unlink()
                        deleted += 1
                except Exception as e:
                    _LOGGER.debug("cleanup_old_debug_dumps: cannot delete %s: %s", json_file, e)
        except Exception as e:
            _LOGGER.debug("cleanup_old_debug_dumps: error scanning %s: %s", sub_dir, e)

    if deleted:
        _LOGGER.info(
            "cleanup_old_debug_dumps: deleted %s old dump(s) (older than %sh)",
            deleted, max_age_hours,
        )
    else:
        _LOGGER.debug("cleanup_old_debug_dumps: nothing to delete")

    return deleted