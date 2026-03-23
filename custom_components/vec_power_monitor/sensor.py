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
        VecPowerMonitorSensor(host, voltage, "load1_status", "Load 1 Status", None, None),
        VecPowerMonitorSensor(host, voltage, "load2_status", "Load 2 Status", None, None),
        VecPowerMonitorSensor(host, voltage, "load3_status", "Load 3 Status", None, None),
    ])


class VecPowerMonitorSensor(SensorEntity):
    """Representation of a VEC Power Monitor sensor."""

    def __init__(self, host: str, voltage: int, sensor_id: str, name: str, unit: str | None, device_class: SensorDeviceClass | None) -> None:
        """Initialize the sensor."""
        self._host = host
        self._voltage = voltage
        self._sensor_id = sensor_id
        self._attr_name = name
        if unit:
            self._attr_native_unit_of_measurement = unit
        if device_class:
            self._attr_device_class = device_class
        self._attr_unique_id = f"vec_power_monitor_{host}_{sensor_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name="VEC Power Monitor",
            manufacturer="VEC",
            model="A-60A-2C",
        )
        self._attr_native_value = 0.0
        # For load delays
        self._on_delay_min = [0, 0, 0]
        self._off_delay_sec = [0, 0, 0]

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
        if len(data) == 12:
            # Config message: 10 bytes sliders + 2 bytes activeCh, ctIndex
            # sliders[2], [5], [8] = onDelayMin for loads 0,1,2
            # sliders[3], [6], [9] = offDelaySec
            self._on_delay_min[0] = data[2]
            self._on_delay_min[1] = data[5]
            self._on_delay_min[2] = data[8]
            self._off_delay_sec[0] = data[3]
            self._off_delay_sec[1] = data[6]
            self._off_delay_sec[2] = data[9]
        elif len(data) == 13:
            # Real-time message
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
                elif self._sensor_id.startswith("load"):
                    load_index = int(self._sensor_id[4]) - 1  # load1 -> 0, etc.
                    status = [status1, status2, status3][load_index]
                    sec_cntr = [sec1, sec2, sec3][load_index]
                    
                    if status == 0:
                        state = "Off"
                        countdown = None
                    elif status == 1:
                        state = "On"
                        countdown = None
                    elif status == 2:  # Wait Off
                        remaining = self._off_delay_sec[load_index] - sec_cntr
                        if remaining < 0:
                            remaining = 0
                        state = f"Wait Off ({remaining}s)"
                        countdown = remaining
                    elif status == 3:  # Wait On
                        remaining = self._on_delay_min[load_index] * 60 - sec_cntr
                        if remaining < 0:
                            remaining = 0
                        state = f"Wait On ({remaining}s)"
                        countdown = remaining
                    else:
                        state = "Unknown"
                        countdown = None
                    
                    self._attr_native_value = state
                    if countdown is not None:
                        self._attr_extra_state_attributes = {"countdown_seconds": countdown}
                    else:
                        self._attr_extra_state_attributes = {}
                    self.async_write_ha_state()
            except struct.error as e:
                _LOGGER.error("Failed to parse binary message: %s", e)
        # Ignore other lengths