"""Map utilities for Neatsvor."""

import logging
from typing import Tuple

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
    # Convert from app coordinates to robot coordinates
    robot_x1 = (x1 - origin_x) // resolution
    robot_y1 = (y1 - origin_y) // resolution
    robot_x2 = (x2 - origin_x) // resolution
    robot_y2 = (y2 - origin_y) // resolution
    
    return (robot_x1, robot_y1, robot_x2, robot_y2)