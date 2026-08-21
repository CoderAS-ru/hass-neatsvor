"""
Protobuf modules for Neatsvor protocol.
"""

import sys
from pathlib import Path

# Добавляем текущую директорию в sys.path для корректных импортов
_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

from . import sdk_com_pb2
from . import sweeper_any_pb2
from . import sweeper_com_pb2
from . import sweeper_map_pb2

__all__ = [
    'sdk_com_pb2',
    'sweeper_any_pb2',
    'sweeper_com_pb2',
    'sweeper_map_pb2'
]