"""Sensor platform for VEC Power Monitor."""

import asyncio
import logging
import math
import struct

import websockets

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
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
        VecPowerMonitorSensor(host, voltage, "line1_current", "Line 1 Current", "A", SensorDeviceClass.CURRENT),
        VecPowerMonitorSensor(host, voltage, "line2_current", "Line 2 Current", "A", SensorDeviceClass.CURRENT),
        VecPowerMonitorSensor(host, voltage, "total_power", "Total Power", "W", SensorDeviceClass.POWER),
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
                    # Send initial command 'i'
                    await websocket.send(b'i')
                    _LOGGER.debug("Sent initial command: b'i'")
                    # Immediately send 'g' to request real-time data
                    await asyncio.sleep(0.1)  # slight delay to mimic JS timing
                    await websocket.send(b'g')
                    _LOGGER.debug("Sent immediate command: b'g'")
                    # Start periodic command sending (every 10 seconds)
                    self._send_task = self.hass.loop.create_task(self._send_periodic_commands(websocket))
                    async for message in websocket:
                        if isinstance(message, bytes):
                            _LOGGER.debug("Received binary message: %s", message.hex())
                            self._parse_binary_message(message)
                        else:
                            _LOGGER.debug("Received non-binary message: %s", message)
            except websockets.exceptions.ConnectionClosed as e:
                _LOGGER.warning("WebSocket connection closed (%s), reconnecting...", e)
                if hasattr(self, '_send_task') and not self._send_task.done():
                    self._send_task.cancel()
                await asyncio.sleep(5)
            except Exception as e:
                _LOGGER.error("WebSocket error: %s", e)
                if hasattr(self, '_send_task') and not self._send_task.done():
                    self._send_task.cancel()
                await asyncio.sleep(5)

    async def _send_periodic_commands(self, websocket) -> None:
        """Send periodic 'g' commands to the device every 10 seconds."""
        while True:
            await asyncio.sleep(10)
            try:
                await websocket.send(b'g')
                _LOGGER.debug("Sent periodic command: b'g'")
            except Exception as e:
                _LOGGER.error("Failed to send command: %s", e)
                break

    def _parse_binary_message(self, data: bytes) -> None:
        """Parse binary WebSocket message."""
        _LOGGER.warning("Binary message length: %d, hex: %s", len(data), data.hex())
        if len(data) == 12:
            # Config/status message: 10 bytes sliders + 2 bytes activeCh, ctIndex
            _LOGGER.info("12-byte config/status packet: %s", ' '.join(f'{b:02x}' for b in data))
            self._on_delay_min[0] = data[2]
            self._on_delay_min[1] = data[5]
            self._on_delay_min[2] = data[8]
            self._off_delay_sec[0] = data[3]
            self._off_delay_sec[1] = data[6]
            self._off_delay_sec[2] = data[9]
            # Set sensors to unavailable/0 since this is not real-time data
            if self._sensor_id in ("line1_current", "line2_current", "total_power"):
                self._attr_native_value = 0.0
                self.async_write_ha_state()
            elif self._sensor_id.startswith("load"):
                self._attr_native_value = "Unavailable"
                self._attr_extra_state_attributes = {}
                self.async_write_ha_state()
            return
        elif len(data) >= 13:
            _LOGGER.warning("Entering 13+ byte branch with data: %s", data.hex())
            # Real-time message: parse as per protocol (use first 13 bytes)
            try:
                d = data[:13]
                rms1_sq = int.from_bytes(d[0:2], 'little')
                rms2_sq = int.from_bytes(d[2:4], 'little')
                sec1 = int.from_bytes(d[4:6], 'little')
                sec2 = int.from_bytes(d[6:8], 'little')
                sec3 = int.from_bytes(d[8:10], 'little')
                status1 = d[10]
                status2 = d[11]
                status3 = d[12]
                rms1 = math.sqrt(rms1_sq)
                rms2 = math.sqrt(rms2_sq)
                voltage = float(self._voltage)
                power1 = rms1 * voltage
                power2 = rms2 * voltage
                total_power = power1 + power2
                _LOGGER.info(
                    "13-byte real-time packet: rms1_sq=%d rms2_sq=%d sec1=%d sec2=%d sec3=%d status1=%d status2=%d status3=%d rms1=%.2f rms2=%.2f power1=%.2f power2=%.2f total_power=%.2f",
                    rms1_sq, rms2_sq, sec1, sec2, sec3, status1, status2, status3, rms1, rms2, power1, power2, total_power
                )
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
                    load_index = int(self._sensor_id[4]) - 1
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
            except Exception as e:
                _LOGGER.error("Failed to parse 13+ byte real-time message: %s | data: %s", e, data.hex())
        # Ignore other lengths