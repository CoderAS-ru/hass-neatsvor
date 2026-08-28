"""
Configuration module for Neatsvor project.
For Home Assistant - dataclasses only, no YAML loading!
"""

from typing import Optional
from dataclasses import dataclass
import logging

_LOGGER = logging.getLogger(__name__)


@dataclass
class RestConfig:
    """REST API configuration."""
    base_url: str
    app_key: str
    app_secret: str
    package_name: str
    source: str
    reg_id: str
    country: str
    user_agent: str

    def __post_init__(self):
        """Validate required fields."""
        if not self.base_url:
            raise ValueError("base_url is required for REST configuration")


@dataclass
class MQTTConfig:
    """MQTT configuration."""
    host: str
    port: int
    username: str
    password: str

    def __post_init__(self):
        """Validate required fields."""
        if not self.host:
            raise ValueError("host is required for MQTT configuration")


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: str = "neatsvor.log"
    console: bool = True


@dataclass
class DeviceConfig:
    """Device configuration."""
    default_timeout: int = 30
    command_delay: float = 1.0
    retry_count: int = 3


@dataclass
class Credentials:
    """User credentials."""
    email: str
    password: str

    def __post_init__(self):
        """Validate credentials."""
        if not self.email or not self.password:
            raise ValueError("email and password are required")


@dataclass
class NeatsvorConfig:
    """Main application configuration."""
    rest: RestConfig
    mqtt: MQTTConfig
    credentials: Credentials
    logging: Optional[LoggingConfig] = None
    device: Optional[DeviceConfig] = None

    def __post_init__(self):
        """Initialize with default values."""
        if self.logging is None:
            self.logging = LoggingConfig()
        if self.device is None:
            self.device = DeviceConfig()