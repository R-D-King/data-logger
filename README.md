
# Raspberry Pi Environmental Data Logger

A comprehensive environmental monitoring system built for Raspberry Pi that collects and logs data from multiple sensors.

## Features

- Collects data from multiple environmental sensors:
  - Temperature and humidity (DHT22)
  - Barometric pressure and altitude (BMP180)
  - Soil moisture (analog sensor via MCP3008)
  - Light level (LDR via MCP3008)
  - Rain detection (rain sensor via MCP3008)
- Logs data to CSV files with one file per day
- Configurable logging interval and data validation
- Error handling and validation for all sensor readings

## Hardware Requirements

- Raspberry Pi (any model with GPIO pins)
- DHT22 temperature and humidity sensor
- BMP180 pressure sensor
- MCP3008 analog-to-digital converter
- Soil moisture sensor (analog)
- Light dependent resistor (LDR)
- Rain detection sensor
- Jumper wires and breadboard

## Wiring Diagram

### DHT22 Sensor
- Connect VCC to 3.3V or 5V
- Connect GND to ground
- Connect DATA to GPIO 26
- Use a 10K ohm resistor between VCC and DATA

### BMP180 Sensor (I2C)
- Connect VCC to 3.3V
- Connect GND to ground
- Connect SDA to GPIO 2 (SDA)
- Connect SCL to GPIO 3 (SCL)

### MCP3008 ADC (SPI)
- Connect VDD to 3.3V
- Connect VREF to 3.3V
- Connect AGND to ground
- Connect DGND to ground
- Connect CLK to GPIO 11 (SCLK)
- Connect DOUT to GPIO 9 (MISO)
- Connect DIN to GPIO 10 (MOSI)
- Connect CS to GPIO 8 (CE0)
- Connect soil moisture sensor to CH0
- Connect LDR sensor to CH1
- Connect rain sensor to CH2

## Software Setup

### Prerequisites

- Raspberry Pi OS (formerly Raspbian)
- Python 3.7 or higher
- Enabled I2C and SPI interfaces

### Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/raspberry-pi-data-logger.git
   cd raspberry-pi-data-logger
   ```

2. Run the setup script to create a virtual environment and install dependencies:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```

3. Activate the virtual environment:
   ```bash
   source venv/bin/activate
   ```

### Configuration

Edit the `sensor_logger.json` file to configure the data logger:

```json
{
  "logger": {
    "data_folder": "~/sensor_data",
    "log_interval": 60,
    "timestamp_format": "%Y-%m-%d %H:%M:%S",
    "log_level": "INFO"
  },
  "validation": {
    "enabled": true,
    "limits": {
      "temperature": {
        "min": -10.0,
        "max": 50.0
      },
      "humidity": {
        "min": 0.0,
        "max": 100.0
      },
      "soil_moisture": {
        "min": 0.0,
        "max": 100.0
      },
      "pressure": {
        "min": 900.0,
        "max": 1100.0
      },
      "light": {
        "min": 0.0,
        "max": 100.0
      },
      "rain": {
        "min": 0.0,
        "max": 100.0
      }
    }
  }
}
```

- `data_folder`: Directory where CSV files will be stored
- `log_interval`: Time between readings in seconds
- `timestamp_format`: Format for timestamps in the CSV file
- `log_level`: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `validation`: Settings for validating sensor readings

## Usage

1. Ensure all sensors are properly connected
2. Activate the virtual environment if not already active:
   ```bash
   source venv/bin/activate
   ```
3. Run the data logger:
   ```bash
   python3 data_logger.py
   ```

### Running as a Service

To run the data logger as a service that starts automatically on boot:

1. Create a systemd service file:
   ```bash
   sudo nano /etc/systemd/system/data-logger.service
   ```

2. Add the following content (adjust paths as needed):
   ```
   [Unit]
   Description=Environmental Data Logger
   After=multi-user.target

   [Service]
   Type=simple
   User=pi
   WorkingDirectory=/home/pi/raspberry-pi-data-logger
   ExecStart=/home/pi/raspberry-pi-data-logger/venv/bin/python /home/pi/raspberry-pi-data-logger/data_logger.py
   Restart=on-failure
   RestartSec=5s

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start the service:
   ```bash
   sudo systemctl enable data-logger.service
   sudo systemctl start data-logger.service
   ```

4. Check the status:
   ```bash
   sudo systemctl status data-logger.service
   ```

## Data Format

The logger creates CSV files with the following columns:

- Timestamp: Date and time of the reading
- Temperature (°C): Air temperature
- Humidity (%): Relative humidity
- Soil Moisture (%): Soil moisture percentage
- Light Level (%): Ambient light level percentage
- Rain Level (%): Rain detection percentage
- Pressure (hPa): Barometric pressure
- Altitude (m): Estimated altitude based on pressure
