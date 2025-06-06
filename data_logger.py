import smbus
import time
from ctypes import c_short
import signal
import sys
import adafruit_dht
import board
import spidev
import csv
import os
import json
import logging
from datetime import datetime
from pathlib import Path

# Load configuration
def load_config():
    config_path = Path(__file__).parent / 'sensor_logger.json'
    with open(config_path, 'r') as f:
        return json.load(f)

# Initialize logging
def setup_logging(config):
    log_level = getattr(logging, config['logger']['log_level'])
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize hardware
def initialize_hardware():
    # SPI setup for analog sensors
    spi = spidev.SpiDev()
    spi.open(0, 0)  # Open SPI bus 0, device 0
    spi.max_speed_hz = 1000000  # Set SPI speed to 1MHz
    
    # DHT22 setup - use proper board pin definition
    import board
    try:
        # Try using the board's pin definitions
        if hasattr(board, 'D26'):
            dht_pin = board.D26
        elif hasattr(board, 'GPIO26'):
            dht_pin = board.GPIO26
        else:
            # For Raspberry Pi, we can use the BCM pin numbering
            from adafruit_blinka.microcontroller.bcm283x.pin import Pin
            dht_pin = Pin(26)
            
        dht_sensor = adafruit_dht.DHT22(dht_pin)
    except Exception as e:
        logging.error(f"Error initializing DHT22: {e}")
        raise
    
    # I2C setup for BMP180
    bus = smbus.SMBus(1)  # Use I2C bus 1 on Raspberry Pi
    
    return spi, dht_sensor, bus

# Channel definitions
MOISTURE_CHANNEL = 0 
LDR_CHANNEL = 1
RAIN_CHANNEL = 2

# BMP180 constants
DEVICE = 0x77  # I2C address of BMP180 sensor

# Calibration values
# Soil moisture sensor
SOIL_DRY_VALUE = 930  # Value when sensor is in dry air
SOIL_WET_VALUE = 415  # Value when sensor is in water

# LDR sensor
LDR_MIN = 0      # ADC value in complete darkness (0V)
LDR_MAX = 1023   # ADC value in bright light (3.3V)

# Rain sensor
RAIN_DRY_VALUE = 1023   # Value when sensor is completely dry
RAIN_WET_VALUE = 300    # Value when sensor is wet

# ADC reading functions
def read_adc(spi, channel):
    """Read the analog value from the MCP3008 ADC"""
    adc_request = [1, (8 + channel) << 4, 0]
    adc_response = spi.xfer2(adc_request)
    return ((adc_response[1] & 3) << 8) + adc_response[2]

# Soil moisture functions
def calculate_moisture_percentage(value):
    """Convert ADC value to moisture percentage"""
    value = max(min(value, SOIL_DRY_VALUE), SOIL_WET_VALUE)
    return ((SOIL_DRY_VALUE - value) / (SOIL_DRY_VALUE - SOIL_WET_VALUE)) * 100

# Light sensor functions
def convert_to_percent(value, min_val, max_val):
    """Convert raw ADC value to percentage"""
    percent = ((max_val - value) / (max_val - min_val)) * 100
    return max(0, min(100, percent))  # Clamp values to 0-100% range

# Rain sensor functions
def calculate_wetness_percentage(value):
    """Convert ADC value to wetness percentage"""
    value = max(min(value, RAIN_DRY_VALUE), RAIN_WET_VALUE)
    return ((RAIN_DRY_VALUE - value) / (RAIN_DRY_VALUE - RAIN_WET_VALUE)) * 100

# BMP180 helper functions
def getShort(data, index):
    """Combine two bytes and return signed 16-bit value"""
    return c_short((data[index] << 8) + data[index + 1]).value

def getUshort(data, index):
    """Combine two bytes and return unsigned 16-bit value"""
    return (data[index] << 8) + data[index + 1]

def readBmp180Id(bus, addr=DEVICE):
    """Read chip ID and version from the sensor"""
    REG_ID = 0xD0
    (chip_id, chip_version) = bus.read_i2c_block_data(addr, REG_ID, 2)
    return (chip_id, chip_version)

def readBmp180(bus, addr=DEVICE):
    """Read pressure from BMP180 sensor"""
    # Register addresses
    REG_CALIB  = 0xAA
    REG_MEAS   = 0xF4
    REG_MSB    = 0xF6
    REG_LSB    = 0xF7
    CRV_TEMP   = 0x2E
    CRV_PRES   = 0x34
    OVERSAMPLE = 3  # Oversampling setting (0-3)

    try:
        # Read calibration data from the sensor
        cal = bus.read_i2c_block_data(addr, REG_CALIB, 22)

        # Convert bytes to calibration values
        AC1 = getShort(cal, 0)
        AC2 = getShort(cal, 2)
        AC3 = getShort(cal, 4)
        AC4 = getUshort(cal, 6)
        AC5 = getUshort(cal, 8)
        AC6 = getUshort(cal, 10)
        B1  = getShort(cal, 12)
        B2  = getShort(cal, 14)
        MB  = getShort(cal, 16)
        MC  = getShort(cal, 18)
        MD  = getShort(cal, 20)

        # Request temperature measurement (needed for pressure calculation)
        bus.write_byte_data(addr, REG_MEAS, CRV_TEMP)
        time.sleep(0.005)  # Wait for measurement
        msb, lsb = bus.read_i2c_block_data(addr, REG_MSB, 2)
        UT = (msb << 8) + lsb

        # Request pressure measurement
        bus.write_byte_data(addr, REG_MEAS, CRV_PRES + (OVERSAMPLE << 6))
        time.sleep(0.04)  # Wait for measurement
        msb, lsb, xsb = bus.read_i2c_block_data(addr, REG_MSB, 3)
        UP = ((msb << 16) + (lsb << 8) + xsb) >> (8 - OVERSAMPLE)

        # Calculate true temperature (needed for pressure calculation)
        X1 = ((UT - AC6) * AC5) >> 15
        X2 = int((MC << 11) / (X1 + MD))
        B5 = X1 + X2

        # Calculate true pressure
        B6 = B5 - 4000
        X1 = (B2 * (B6 * B6 >> 12)) >> 11
        X2 = (AC2 * B6) >> 11
        X3 = X1 + X2
        B3 = (((AC1 * 4 + X3) << OVERSAMPLE) + 2) >> 2
        X1 = (AC3 * B6) >> 13
        X2 = (B1 * (B6 * B6 >> 12)) >> 16
        X3 = ((X1 + X2) + 2) >> 2
        B4 = (AC4 * (X3 + 32768)) >> 15
        B7 = (UP - B3) * (50000 >> OVERSAMPLE)

        if B7 < 0x80000000:
            P = (B7 * 2) // B4
        else:
            P = (B7 // B4) * 2

        X1 = (P >> 8) * (P >> 8)
        X1 = (X1 * 3038) >> 16
        X2 = (-7357 * P) >> 16
        pressure = P + ((X1 + X2 + 3791) >> 4)
        pressure = pressure / 100.0  # Convert to hPa

        return pressure
    except Exception as e:
        logging.error(f"Error reading BMP180 sensor: {e}")
        return None

# Read DHT22 sensor with error handling
def read_dht22(dht_sensor):
    """Read temperature and humidity from DHT22 sensor"""
    try:
        temperature = dht_sensor.temperature
        humidity = dht_sensor.humidity
        return (temperature, humidity)
    except Exception as e:
        logging.error(f"Error reading DHT22 sensor: {e}")
        return (None, None)

# Read all sensors
def read_all_sensors(spi, dht_sensor, bus, config):
    """Read all sensor values and validate them"""
    # Read soil moisture
    try:
        soil_raw = read_adc(spi, MOISTURE_CHANNEL)
        soil_moisture = calculate_moisture_percentage(soil_raw)
    except Exception as e:
        logging.error(f"Error reading soil moisture sensor: {e}")
        soil_moisture = None

    # Read light level
    try:
        ldr_raw = read_adc(spi, LDR_CHANNEL)
        light_level = convert_to_percent(ldr_raw, LDR_MIN, LDR_MAX)
    except Exception as e:
        logging.error(f"Error reading light sensor: {e}")
        light_level = None

    # Read rain sensor
    try:
        rain_raw = read_adc(spi, RAIN_CHANNEL)
        rain_level = calculate_wetness_percentage(rain_raw)
    except Exception as e:
        logging.error(f"Error reading rain sensor: {e}")
        rain_level = None

    # Read temperature and humidity from DHT22
    temperature, humidity = read_dht22(dht_sensor)

    # Read pressure sensor
    pressure = readBmp180(bus)

    # Validate readings if enabled
    if config['validation']['enabled']:
        limits = config['validation']['limits']
        
        # Validate temperature (DHT22 only)
        if temperature is not None:
            if not (limits['temperature']['min'] <= temperature <= limits['temperature']['max']):
                logging.warning(f"Temperature {temperature}°C outside valid range")
        
        # Validate humidity
        if humidity is not None:
            if not (limits['humidity']['min'] <= humidity <= limits['humidity']['max']):
                logging.warning(f"Humidity {humidity}% outside valid range")
        
        # Validate soil moisture
        if soil_moisture is not None:
            if not (limits['soil_moisture']['min'] <= soil_moisture <= limits['soil_moisture']['max']):
                logging.warning(f"Soil moisture {soil_moisture}% outside valid range")
        
        # Validate pressure
        if pressure is not None:
            if not (limits['pressure']['min'] <= pressure <= limits['pressure']['max']):
                logging.warning(f"Pressure {pressure}hPa outside valid range")
        
        # Validate light level
        if light_level is not None:
            if not (limits['light']['min'] <= light_level <= limits['light']['max']):
                logging.warning(f"Light level {light_level}% outside valid range")
        
        # Validate rain level
        if rain_level is not None:
            if not (limits['rain']['min'] <= rain_level <= limits['rain']['max']):
                logging.warning(f"Rain level {rain_level}% outside valid range")

    # Return all readings
    return {
        'timestamp': datetime.now().strftime(config['logger']['timestamp_format']),
        'temperature': temperature,  # °C
        'humidity': humidity,  # %
        'soil_moisture': soil_moisture,  # %
        'light_level': light_level,  # %
        'rain_level': rain_level,  # %
        'pressure': pressure,  # hPa
    }

# Setup CSV logging
def setup_csv_file(config):
    """Setup CSV file with headers including units"""
    # Expand ~ to user's home directory
    data_folder = os.path.expanduser(config['logger']['data_folder'])
    
    # Create folder if it doesn't exist
    os.makedirs(data_folder, exist_ok=True)
    
    # Create filename based on current date
    today = datetime.now().strftime('%Y-%m-%d')
    csv_path = os.path.join(data_folder, f"{today}.csv")
    
    # Check if file exists to determine if we need to write headers
    file_exists = os.path.isfile(csv_path)
    
    # Open file in append mode
    csv_file = open(csv_path, 'a', newline='')
    csv_writer = csv.writer(csv_file)
    
    # Write headers if file is new
    if not file_exists:
        headers = [
            'Timestamp',
            'Temperature (°C)',
            'Humidity (%)',
            'Soil Moisture (%)',
            'Light Level (%)',
            'Rain Level (%)',
            'Pressure (hPa)',
            'Altitude (m)'
        ]
        csv_writer.writerow(headers)
    
    return csv_file, csv_writer

# Log data to CSV
def log_data(csv_writer, data):
    """Write sensor data to CSV file"""
    row = [
        data['timestamp'],
        data['temperature'],
        data['humidity'],
        data['soil_moisture'],
        data['light_level'],
        data['rain_level'],
        data['pressure']
    ]
    csv_writer.writerow(row)

# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    logging.info("Shutting down data logger...")
    sys.exit(0)

# Main function
def main():
    # Load configuration
    config = load_config()
    
    # Setup logging
    setup_logging(config)
    logging.info("Starting data logger...")
    
    # Initialize hardware
    try:
        spi, dht_sensor, bus = initialize_hardware()
        logging.info("Hardware initialized successfully")
    except Exception as e:
        logging.error(f"Failed to initialize hardware: {e}")
        sys.exit(1)
    
    # Setup signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Main loop
    csv_file = None
    csv_writer = None
    last_day = None
    
    try:
        while True:
            # Check if we need a new CSV file (day changed)
            today = datetime.now().day
            if last_day != today:
                # Close previous file if open
                if csv_file:
                    csv_file.close()
                
                # Create new CSV file for the day
                csv_file, csv_writer = setup_csv_file(config)
                last_day = today
                logging.info(f"Created new log file for {datetime.now().strftime('%Y-%m-%d')}")
            
            # Read all sensors
            sensor_data = read_all_sensors(spi, dht_sensor, bus, config)
            
            # Log data to CSV
            log_data(csv_writer, sensor_data)
            logging.debug(f"Logged data: {sensor_data}")
            
            # Flush to ensure data is written
            csv_file.flush()
            
            # Wait for next logging interval
            time.sleep(config['logger']['log_interval'])
    
    except Exception as e:
        logging.error(f"Error in main loop: {e}")
    
    finally:
        # Clean up
        if csv_file:
            csv_file.close()
        spi.close()
        logging.info("Data logger shutdown complete")

# Run the program if executed directly
if __name__ == "__main__":
    main()