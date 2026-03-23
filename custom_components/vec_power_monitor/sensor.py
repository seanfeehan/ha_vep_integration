"""Sensor platform for VEC Power Monitor."""

import asyncio
import logging
import math
import struct

import websockets

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMeasurement
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the VEC Power Monitor sensor."""
    host = config_entry.data["host"]
    voltage = config_entry.data["voltage"]
    async_add_entities([
        VecPowerMonitorSensor(host, voltage, "line1_current", "Line 1 Current", UnitOfMeasurement.AMPERE, SensorDeviceClass.CURRENT),
        VecPowerMonitorSensor(host, voltage, "line2_current", "Line 2 Current", UnitOfMeasurement.AMPERE, SensorDeviceClass.CURRENT),
        VecPowerMonitorSensor(host, voltage, "total_power", "Total Power", UnitOfMeasurement.WATT, SensorDeviceClass.POWER),
    ])


class VecPowerMonitorSensor(SensorEntity):
    """Representation of a VEC Power Monitor sensor."""

    def __init__(self, host: str, voltage: int, sensor_id: str, name: str, unit: str, device_class: SensorDeviceClass) -> None:
        """Initialize the sensor."""
        self._host = host
        self._voltage = voltage
        self._sensor_id = sensor_id
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_unique_id = f"vec_power_monitor_{host}_{sensor_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name="VEC Power Monitor",
            manufacturer="VEC",
            model="A-60A-2C",
        )
        self._attr_native_value = 0.0

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        self.hass.loop.create_task(self._connect_websocket())

    async def _connect_websocket(self) -> None:
        """Connect to the WebSocket and listen for messages."""
        uri = f"ws://{self._host}/ws"
        while True:
            try:
                async with websockets.connect(uri) as websocket:
                    _LOGGER.info("Connected to WebSocket at %s", uri)
                    async for message in websocket:
                        if isinstance(message, bytes):
                            self._parse_binary_message(message)
            except websockets.exceptions.ConnectionClosed:
                _LOGGER.warning("WebSocket connection closed, reconnecting...")
                await asyncio.sleep(5)
            except Exception as e:
                _LOGGER.error("WebSocket error: %s", e)
                await asyncio.sleep(5)

    def _parse_binary_message(self, data: bytes) -> None:
        """Parse binary WebSocket message."""
        if len(data) == 13:  # Real-time data message
            try:
                # Unpack: 3 uint16 little endian, 3 uint8
                rms1_sq, rms2_sq, sec1, sec2, sec3, status1, status2, status3 = struct.unpack('<HHHBBB', data)
                rms1 = math.sqrt(rms1_sq)
                rms2 = math.sqrt(rms2_sq)
                # Use configured voltage for power calculation
                voltage = float(self._voltage)
                power1 = rms1 * voltage
                power2 = rms2 * voltage
                total_power = power1 + power2

                # Update sensors based on sensor_id
                if self._sensor_id == "line1_current":
                    self._attr_native_value = round(rms1, 1)
                    self.async_write_ha_state()
                elif self._sensor_id == "line2_current":
                    self._attr_native_value = round(rms2, 1)
                    self.async_write_ha_state()
                elif self._sensor_id == "total_power":
                    self._attr_native_value = round(total_power, 1)
                    self.async_write_ha_state()
            except struct.error as e:
                _LOGGER.error("Failed to parse binary message: %s", e)
        # Ignore config messages (len 12) or other lengths