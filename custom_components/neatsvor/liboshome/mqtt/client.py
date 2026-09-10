"""Synchronous MQTT client (legacy)."""

import paho.mqtt.client as mqtt
import logging

_LOGGER = logging.getLogger(__name__)


class MQTTClient:
    """Synchronous MQTT client (for backward compatibility)."""

    def __init__(self, host, port, username, password, client_id):
        """Initialize MQTT client."""
        self.host = host
        self.port = port
        self._connected = False
        self._handlers = []
        self.subscriptions = set()  # Use set instead of list for uniqueness

        self.client = mqtt.Client(
            client_id=client_id,
            protocol=mqtt.MQTTv311,
            clean_session=True
        )
        self.client.username_pw_set(username, password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc):
        """Handle connection."""
        if rc == 0:
            self._connected = True
            _LOGGER.info("MQTT connected to %s:%s", self.host, self.port)
            # Re-subscribe to all topics
            for topic in self.subscriptions:
                client.subscribe(topic)
        else:
            _LOGGER.error("MQTT connection error: %s", rc)

    def _on_disconnect(self, client, userdata, rc):
        """Handle disconnection."""
        self._connected = False
        if rc != 0:
            _LOGGER.warning("Unexpected MQTT disconnection: %s", rc)

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        # Pass message to all handlers
        for handler in self._handlers:
            try:
                handler(msg)
            except Exception as e:
                _LOGGER.error("Error in MQTT handler: %s", e)

    def connect(self, timeout=60):
        """Connect to MQTT broker."""
        if self._connected:
            return

        try:
            self.client.connect(self.host, self.port, timeout)
            self.client.loop_start()
        except Exception as e:
            _LOGGER.error("Error connecting to MQTT: %s", e)
            raise

    def stop(self):
        """Stop MQTT client."""
        try:
            # Stop MQTT
            self.client.loop_stop()
            self.client.disconnect()
            self._connected = False
            _LOGGER.info("MQTT client stopped")
        except Exception as e:
            _LOGGER.error("Error stopping MQTT: %s", e)

    def publish(self, topic, payload, qos=1, retain=False):
        """Publish message."""
        try:
            result = self.client.publish(topic, payload, qos=qos, retain=retain)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                _LOGGER.error("Error publishing to %s: %s", topic, result.rc)
        except Exception as e:
            _LOGGER.error("Exception during publish: %s", e)

    def subscribe(self, topic, qos=1):
        """Subscribe to topic."""
        if topic not in self.subscriptions:
            self.subscriptions.add(topic)

        if self._connected:
            try:
                result = self.client.subscribe(topic, qos=qos)
                if result[0] == mqtt.MQTT_ERR_SUCCESS:
                    _LOGGER.debug("Subscribed to %s", topic)
                else:
                    _LOGGER.error("Error subscribing to %s: %s", topic, result[0])
            except Exception as e:
                _LOGGER.error("Exception during subscribe: %s", e)

    def add_handler(self, handler):
        """Add message handler."""
        if handler not in self._handlers:
            self._handlers.append(handler)

    def remove_handler(self, handler):
        """Remove message handler."""
        if handler in self._handlers:
            self._handlers.remove(handler)

    @property
    def is_connected(self):
        """Check connection status."""
        return self._connected