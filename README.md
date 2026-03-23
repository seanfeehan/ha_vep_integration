# VEC Power Monitor Integration

A custom Home Assistant integration for monitoring power from a VEC-A-60A-2C device via WebSocket.

**Device Website**: [V-Electric](https://v-electric.com/)

## Branding (logo)

![VEC logo](custom_components/vec_power_monitor/vec_logo.png)

*Note: Place the official logo at `custom_components/vec_power_monitor/vec_logo.png`.*

## Installation

1. Copy the `custom_components/vec_power_monitor` directory to your Home Assistant's `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration through the UI: Settings > Devices & Services > Add Integration > VEC Power Monitor.
4. Enter the host IP address and voltage for your VEC-A-60A-2C device. The integration will test the WebSocket connection to ensure it's reachable.

## Configuration

- **Host**: The IP address of the VEC-A-60A-2C device (e.g., `192.168.1.100`)
- **Voltage**: The voltage of your house electrical system (default: 120V)

## WebSocket Protocol

The integration connects to the specified WebSocket URL and parses binary messages containing RMS current values for two lines.

It creates six sensors:
- Line 1 Current (A)
- Line 2 Current (A)
- Total Power (W) - calculated as (Line1 + Line2) × Voltage
- Load 1 Status
- Load 2 Status
- Load 3 Status

## Features

- Real-time power monitoring via WebSocket connection on port 80.
- Automatic reconnection on connection loss.

## Requirements

- Home Assistant 2023.1.0 or later
- `websockets` Python library

## Lovelace Dashboard

Here are some suggested Lovelace card configurations for displaying your VEC Power Monitor data:

### Entities Card
```yaml
type: entities
title: VEC Power Monitor
entities:
  - entity: sensor.vec_power_monitor_192_168_1_100_line1_current  # Replace with your actual entity ID
  - entity: sensor.vec_power_monitor_192_168_1_100_line2_current
  - entity: sensor.vec_power_monitor_192_168_1_100_total_power
  - entity: sensor.vec_power_monitor_192_168_1_100_load1_status
  - entity: sensor.vec_power_monitor_192_168_1_100_load2_status
  - entity: sensor.vec_power_monitor_192_168_1_100_load3_status
```

### Gauge Cards for Currents
```yaml
type: horizontal-stack
cards:
  - type: gauge
    entity: sensor.vec_power_monitor_192_168_1_100_line1_current  # Replace with your actual entity ID
    name: Line 1 Current
    unit: A
    min: 0
    max: 60
  - type: gauge
    entity: sensor.vec_power_monitor_192_168_1_100_line2_current
    name: Line 2 Current
    unit: A
    min: 0
    max: 60
```

### Power Consumption Chart
```yaml
type: history-graph
title: Power Consumption
entities:
  - entity: sensor.vec_power_monitor_192_168_1_100_total_power  # Replace with your actual entity ID
hours_to_show: 24
```

**Note**: Replace `192_168_1_100` with your device's IP address (underscores instead of dots) in the entity IDs. You can find the exact entity IDs in Home Assistant's Developer Tools > States.
