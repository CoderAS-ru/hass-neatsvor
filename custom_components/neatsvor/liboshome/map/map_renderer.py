"""Map renderer for Neatsvor."""

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, Any, Optional, Tuple, List
import os
from pathlib import Path
import platform
import logging
import mdi_pil as mdi

from custom_components.neatsvor.liboshome.map.map_utils import (
    calculate_map_scale,
    extract_room_presets,
)

_LOGGER = logging.getLogger(__name__)


class MapRenderer:
    """Map renderer based on map_system0.py."""

    # Colors from the original app (fully preserved)
    FLOOR_COLOR = "#FFFFFFFF"  # "#FFE1E3E6"
    WALL_COLOR = "#FF3F475C"
    ROOM_COLORS = [
        "#C0E7FE", "#FDDCC0", "#FFB1B2", "#A5D2C0",
        "#DCBAFF", "#FB9ECB", "#FABAA5", "#FACE97",
        "#B5F4FA", "#AFCCF7", "#E1BBAB", "#F1B1D3",
        "#A1BED9", "#EFD0B9", "#B4E3E6", "#F2FBC5"
    ]

    def __init__(self, config: Optional[Dict] = None):
        """Initialize map renderer."""
        self.config = config or {}
        self.multiple = 4  # Default scale
        self._robot_icon = None
        self._charger_icon = None

        # Кэш MDI-иконок пресетов: {"mdi:fan-speed-1": Image, ...}
        self._preset_icons_cache: Dict[str, Image.Image] = {}
        
        # Load fonts of different sizes
        self._font_normal = self._load_font(20)      # Main font
        self._font_large = self._load_font(32)       # For headers
        self._font_legend = self._load_font(30)      # For room names (enlarged)

        # Main font for backward compatibility
        self._font = self._font_normal

        # Log font status
        self._log_font_status()
        
    def _log_font_status(self):
        """Log font loading status."""
        fonts_loaded = []
        for font_name, font in [("normal", self._font_normal),
                                ("large", self._font_large),
                                ("legend", self._font_legend)]:
            if font and hasattr(font, 'path'):
                fonts_loaded.append(f"{font_name}: {font.path}")
            else:
                fonts_loaded.append(f"{font_name}: default")

        _LOGGER.debug("Fonts loaded: %s", ', '.join(fonts_loaded))

    def _load_font(self, size: int = 20) -> Optional[ImageFont]:
        """Load font from local fonts folder."""
        try:
            from pathlib import Path

            current_dir = Path(__file__).parent
            liboshome_dir = current_dir.parent
            fonts_dir = liboshome_dir / 'fonts'
            font_path = fonts_dir / 'arial.ttf'

            _LOGGER.debug("Looking for font: %s (size %s)", font_path, size)

            if font_path.exists():
                try:
                    font = ImageFont.truetype(str(font_path), size)
                    _LOGGER.debug("Loaded font from local folder: %s (size %s)", font_path, size)
                    return font
                except Exception as e:
                    _LOGGER.error("Failed to load font from %s: %s", font_path, e)
            else:
                _LOGGER.error("Font file not found: %s", font_path)

                _LOGGER.debug("Searching for available fonts:")
                for p in [fonts_dir, Path("/usr/share/fonts/")]:
                    if p.exists():
                        _LOGGER.debug("  %s: %s", p, list(p.glob('*.ttf'))[:5])

            _LOGGER.warning("Using default PIL font (size %s)", size)
            return ImageFont.load_default()

        except Exception as e:
            _LOGGER.error("Error loading font: %s", e)
            return ImageFont.load_default()

    def set_scale(self, width: int, height: int):
        """Set MULTIPLE scale using shared utility."""
        self.multiple = calculate_map_scale(width, height)

    def hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """Convert hex to RGB."""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 8:  # ARGB format
            hex_color = hex_color[2:]  # Skip alpha channel
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def render_map(self, map_data: Dict[str, Any], output_file: Optional[str] = None,
                   show_legend: bool = True, root_window=None) -> Image.Image:
        """Render map to image with optional legend."""
        width = map_data['width']
        height = map_data['height']

        # Set scale
        self.set_scale(width, height)

        # Create image (with legend space)
        img_width = width * self.multiple
        img_height = height * self.multiple

        y_offset = 0
        
        if show_legend and map_data.get('room_names'):
            from custom_components.neatsvor.liboshome.map.map_utils import calculate_legend_height
            # has_presets=True — резервируем вторую строку под иконки
            legend_height = calculate_legend_height(len(map_data['room_names']), has_presets=True)
            img_height += legend_height
            y_offset = legend_height

        image = Image.new('RGB', (img_width, img_height),
                         color=self.hex_to_rgb(self.FLOOR_COLOR))
        draw = ImageDraw.Draw(image)

        # Draw rooms
        for room_id, cells in map_data['rooms'].items():
            color = self._get_room_color(room_id)
            for cell_x, cell_y in cells:
                self._draw_cell(draw, cell_x, cell_y, color, y_offset)

        # Draw walls
        wall_color = self.hex_to_rgb(self.WALL_COLOR)
        for cell_x, cell_y in map_data['walls']:
            self._draw_cell(draw, cell_x, cell_y, wall_color, y_offset)

        # Draw trajectory
        if map_data['trajectory']:
            self._draw_trajectory(image, map_data, y_offset)

        # Add icons (pass root_window)
        self._draw_icons(image, map_data, y_offset, root_window)

        # Add legend (extra large font) — передаём image для иконок пресетов
        if show_legend and map_data.get('room_names'):
            self._draw_legend(draw, map_data, img_width, image=image)

        # Save if needed
        if output_file:
            image.save(output_file)
            _LOGGER.debug("Map saved: %s", output_file)

        return image

    def _draw_cell(self, draw, x: int, y: int, color: Tuple[int, int, int], y_offset: int = 0):
        """Draw a single map cell."""
        x1 = x * self.multiple
        y1 = y * self.multiple + y_offset
        x2 = x1 + self.multiple
        y2 = y1 + self.multiple
        draw.rectangle([x1, y1, x2, y2], fill=color, outline=color)

    def _get_room_color(self, room_id: int) -> Tuple[int, int, int]:
        """Return room color."""
        if room_id == 0:  # Floor (not a room)
            return self.hex_to_rgb(self.FLOOR_COLOR)
        color_idx = (room_id - 1) % len(self.ROOM_COLORS)
        return self.hex_to_rgb(self.ROOM_COLORS[color_idx])

    def _draw_trajectory(self, image: Image.Image, map_data: Dict, y_offset: int = 0):
        """Draw cleaning trajectory with breaks as in original app."""
        if not map_data.get('raw') or not map_data['raw'].HasField('trace_info'):
            return

        trace_info = map_data['raw'].trace_info
        if not trace_info.data:
            return

        # Create layer for trajectory
        trajectory_layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(trajectory_layer)

        origin_x = map_data['origin']['x']
        origin_y = map_data['origin']['y']

        # Counter for drawn segments
        segments_drawn = 0

        # Each trace_data is drawn separately
        for trace_data in trace_info.data:
            points = trace_data.points
            if len(points) < 2:
                continue

            # Filter points (-1, -1) within each segment
            filtered_points = []
            for point in points:
                if point.x != -1 or point.y != -1:  # Filter (-1, -1)
                    # Convert coordinates
                    px = ((point.x / 10) - (origin_x / 10)) * self.multiple
                    py = ((point.y / 10) - (origin_y / 10)) * self.multiple + y_offset
                    filtered_points.append((px, py))

            # Draw segment only if there are at least 2 points
            if len(filtered_points) > 1:
                draw.line(filtered_points, fill=(255, 255, 255, 180), width=2)
                segments_drawn += 1

        _LOGGER.debug("Drawn trace segments: %s", segments_drawn)

        # Composite onto main image
        if segments_drawn > 0:
            image.paste(
                Image.alpha_composite(image.convert('RGBA'), trajectory_layer).convert('RGB')
            )

    def _load_icons(self):
        """Load robot and charger icons."""
        if self._robot_icon is not None and self._charger_icon is not None:
            return

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        mqtt_dir = os.path.join(project_root, 'liboshome', 'map')

        robot_path = os.path.join(mqtt_dir, 'ic_robot.png')
        charger_path = os.path.join(mqtt_dir, 'ic_charger.png')

        _LOGGER.debug("Loading icons from %s", mqtt_dir)

        try:
            self._robot_icon = Image.open(robot_path).convert('RGBA')
            _LOGGER.debug("Robot icon loaded")
        except Exception as e:
            _LOGGER.warning("Error loading robot icon: %s", e)
            self._robot_icon = self._create_simple_icon((255, 0, 0, 200), "R")

        try:
            self._charger_icon = Image.open(charger_path).convert('RGBA')
            _LOGGER.debug("Charger icon loaded")
        except Exception as e:
            _LOGGER.warning("Error loading charger icon: %s", e)
            self._charger_icon = self._create_simple_icon((0, 255, 0, 200), "C")

    def _draw_icons(self, image: Image.Image, map_data: Dict, y_offset: int = 0, root_window=None):
        """Add robot and charger icons to map."""
        self._load_icons()

        if not self._robot_icon or not self._charger_icon:
            return

        # Create layer for icons
        icon_layer = Image.new('RGBA', image.size, (0, 0, 0, 0))

        origin_x = map_data['origin']['x']
        origin_y = map_data['origin']['y']

        # Charger (under robot)
        if map_data.get('charger_position'):
            pos = map_data['charger_position']
            x = ((pos['x'] / 10) - (origin_x / 10)) * self.multiple
            y = ((pos['y'] / 10) - (origin_y / 10)) * self.multiple + y_offset

            paste_x = int(x) - self._charger_icon.width // 2
            paste_y = int(y) - self._charger_icon.height // 2
            icon_layer.paste(self._charger_icon, (paste_x, paste_y), self._charger_icon)
            _LOGGER.debug("Charger: (%s, %s)", paste_x, paste_y)

            if root_window:
                root_window.charger_icon = self._charger_icon

        # Robot (on top of charger)
        if map_data.get('robot_position'):
            pos = map_data['robot_position']
            x = ((pos['x'] / 10) - (origin_x / 10)) * self.multiple
            y = ((pos['y'] / 10) - (origin_y / 10)) * self.multiple + y_offset

            angle = pos.get('angle', 0)
            if angle != 0:
                rotation_angle = angle - 90
                robot_icon = self._robot_icon.rotate(
                    rotation_angle,
                    expand=True,
                    resample=Image.Resampling.BICUBIC,
                    fillcolor=(0, 0, 0, 0)
                )
            else:
                robot_icon = self._robot_icon

            paste_x = int(x) - robot_icon.width // 2
            paste_y = int(y) - robot_icon.height // 2
            icon_layer.paste(robot_icon, (paste_x, paste_y), robot_icon)
            _LOGGER.debug("Robot: (%s, %s), angle: %s°", paste_x, paste_y, angle)

            if root_window:
                root_window.robot_icon = robot_icon

        # Composite
        image.paste(
            Image.alpha_composite(image.convert('RGBA'), icon_layer).convert('RGB')
        )

    def _create_simple_icon(self, color: Tuple[int, int, int, int], text: str) -> Image.Image:
        """Create simple icon if files are not found."""
        icon = Image.new('RGBA', (54, 54), (0, 0, 0, 0))
        draw = ImageDraw.Draw(icon)

        # Circle
        draw.ellipse([10, 10, 44, 44], fill=color, outline=(255, 255, 255, 255))

        # Text (use large font for icons)
        font_to_use = self._font_large if self._font_large else self._font_normal

        try:
            bbox = draw.textbbox((0, 0), text, font=font_to_use)
            text_x = (54 - (bbox[2] - bbox[0])) // 2
            text_y = (54 - (bbox[3] - bbox[1])) // 2
            draw.text((text_x, text_y), text, fill=(255, 255, 255), font=font_to_use)
        except Exception:
            # Fallback
            draw.text((20, 15), text, fill=(255, 255, 255))

        return icon

    def _get_preset_icon(self, mdi_name: str, size: int = 24) -> Optional[Image.Image]:
        """
        Возвращает RGBA-изображение MDI-иконки нужного размера.
        Использует кэш, чтобы не пересоздавать при каждом рендере.
        """
        cache_key = f"{mdi_name}@{size}"
        if cache_key in self._preset_icons_cache:
            return self._preset_icons_cache[cache_key]

        try:
            # mdi_pil рисует на квадратном полотне; размер задаётся неявно
            # (обычно 24x24 у mdi_pil, но проверим на всякий случай)
            base = Image.new("RGBA", (100, 100), None)
            base = mdi.draw_mdi_icon(base, mdi_name, icon_color="black")

            # Обрезаем по контенту и ресайзим под нужный size
            bbox = base.getbbox()
            if bbox:
                base = base.crop(bbox)

            # Вписываем в квадрат size×size с сохранением пропорций
            base.thumbnail((size, size), Image.Resampling.LANCZOS)

            # Создаём финальное полотно size×size и центрируем
            final = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            paste_x = (size - base.width) // 2
            paste_y = (size - base.height) // 2
            final.paste(base, (paste_x, paste_y), base)

            self._preset_icons_cache[cache_key] = final
            return final

        except Exception as e:
            _LOGGER.warning("Failed to draw MDI icon %s: %s", mdi_name, e)
            return None

    def _draw_legend(self, draw, map_data: Dict, image_width: int,
                     image: Optional[Image.Image] = None):
        """
        Draw legend with room names + presets row.

        Первая строка: цветной квадрат + название комнаты.
        Вторая строка: иконки пресетов (fan, water, mode, times) под каждой комнатой.
        """
        room_names = map_data.get('room_names', [])
        if not room_names:
            return

        _LOGGER.debug("Adding legend for %s rooms (with presets)", len(room_names))

        # Параметры первой строки
        item_height = 45
        items_per_row = min(4, len(room_names))
        box_size = 32
        margin = 15
        text_offset = 12

        # Параметры второй строки (пресеты)
        presets_row_height = 35

        # Высота фона легенды
        legend_bg_y1 = 5
        legend_bg_y2 = 50 + ((len(room_names) - 1) // items_per_row + 1) * item_height
        legend_bg_y2 += presets_row_height  # место под вторую строку

        draw.rectangle(
            [margin - 5, legend_bg_y1, image_width - margin + 5, legend_bg_y2],
            fill=(255, 255, 255, 220),
            outline=(200, 200, 200)
        )

        # Собираем позиции комнат (для второй строки)
        room_cols = []

        for i, room in enumerate(room_names):
            row = i // items_per_row
            col = i % items_per_row

            col_width = image_width // items_per_row
            x = margin + col * col_width
            y = 45 + row * item_height

            color = self._get_room_color(room['id'])

            # Цветной квадрат
            draw.rectangle([x, y, x + box_size, y + box_size],
                          fill=color,
                          outline=(100, 100, 100),
                          width=1)

            # Название комнаты (с тенью)
            draw.text((x + box_size + text_offset + 1, y + 5 + 1),
                     room['name'],
                     fill=(150, 150, 150),
                     font=self._font_legend or self._font_normal)
            draw.text((x + box_size + text_offset, y + 5),
                     room['name'],
                     fill=(0, 0, 0),
                     font=self._font_legend or self._font_normal)

            # Центр всей ячейки (квадрат + отступ + текст комнаты)
            try:
                text_w = draw.textlength(
                    room['name'],
                    font=self._font_legend or self._font_normal,
                )
            except Exception:
                # fallback для старых версий PIL
                bbox = draw.textbbox(
                    (0, 0), room['name'],
                    font=self._font_legend or self._font_normal,
                )
                text_w = bbox[2] - bbox[0]

            cell_width = box_size + text_offset + text_w
            cell_center_x = int(x + cell_width // 2)

            room_cols.append({
                'id': room['id'],
                'name': room['name'],
                'center_x': cell_center_x,
            })

        # Вторая строка — иконки пресетов
        if image is not None:
            # Y для второй строки: сразу под последней строкой первой части
            rows_used = (len(room_names) - 1) // items_per_row + 1
            presets_y = int(45 + rows_used * item_height)
            self._draw_presets_row(image, map_data, room_cols, image_width, presets_y)

        # Разделитель
        draw.line([margin, legend_bg_y2 + 5, image_width - margin, legend_bg_y2 + 5],
                 fill=(200, 200, 200), width=2)
                 
    def _draw_presets_row(self, image: Image.Image, map_data: Dict,
                          room_cols: List[Dict], image_width: int,
                          y_base: int):
        """
        Рисует вторую строку легенды — иконки пресетов под каждой комнатой.

        Args:
            image: полотно (RGBA или RGB)
            map_data: декодированная карта
            room_cols: [{'id': ..., 'name': ..., 'x': ..., 'center_x': ...}, ...]
            image_width: ширина изображения
            y_base: верхняя Y-координата для второй строки
        """
        presets = extract_room_presets(map_data)

        icon_size = 32
        gap = 8          # отступ между иконками
        row_y = y_base

        # Карта: значение → mdi-имя
        fan_icons = {
            1: "mdi:fan-speed-1",
            2: "mdi:fan-speed-2",
            3: "mdi:fan-speed-3",
            4: "mdi:fan-plus",
        }
        water_icons = {
            1: "mdi:water-minus",
            2: "mdi:water",
            3: "mdi:water-plus",
        }
        mode_icons = {
            0: "mdi:broom",           # sweep
            1: "mdi:spray",           # mop
            2: "mdi:vacuum-outline",  # sweepMop
        }
        times_icons = {
            1: "mdi:numeric-1-box-multiple-outline",
            2: "mdi:numeric-2-box-multiple-outline",
            3: "mdi:numeric-3-box-multiple-outline",
        }

        for room in room_cols:
            room_id = room['id']
            preset = presets.get(room_id)
            if not preset:
                continue

            # Собираем список MDI-имён для этой комнаты
            icons_to_draw = []

            fan = preset.get('fan')
            if fan in fan_icons:
                icons_to_draw.append(fan_icons[fan])

            water = preset.get('water')
            if water in water_icons:
                icons_to_draw.append(water_icons[water])

            mode = preset.get('mode')
            if mode in mode_icons:
                icons_to_draw.append(mode_icons[mode])

            times = preset.get('times')
            if times in times_icons:
                icons_to_draw.append(times_icons[times])

            if not icons_to_draw:
                continue

            # Общая ширина блока иконок
            total_width = len(icons_to_draw) * icon_size + (len(icons_to_draw) - 1) * gap
            start_x = int(room['center_x'] - total_width // 2)

            # Рисуем слева направо
            for i, mdi_name in enumerate(icons_to_draw):
                icon_img = self._get_preset_icon(mdi_name, icon_size)
                if icon_img is None:
                    continue
                x = int(start_x + i * (icon_size + gap))
                y = int(row_y)
                # image может быть RGB — конвертируем для альфа-композита
                image.paste(icon_img, (x, y), icon_img)