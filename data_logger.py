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
from datetime import datetime
from pathlib import Path 



spi = spidev.SpiDev()
spi.open(0, 0)  # Open SPI bus 0, device 0
spi.max_speed_hz = 1000000  # Set SPI speed to 1MHz

MOISTURE_CHANNEL = 0 
LDR_CHANNEL = 1
RAIN_CHANNEL = 2


"""Soil moisture sensor"""
# Calibration values for soil
DRY_VALUE = 930  # Value when sensor is in dry air
WET_VALUE = 415  # Value when sensor is in water

def read_adc(channel):
    """Read the analog value from the MCP3008 ADC"""
    adc_request = [1, (8 + channel) << 4, 0]
    adc_response = spi.xfer2(adc_request)
    return ((adc_response[1] & 3) << 8) + adc_response[2]

def calculate_moisture_percentage(value):
    """Convert ADC value to moisture percentage"""
    value = max(min(value, DRY_VALUE), WET_VALUE)
    return ((DRY_VALUE - value) / (DRY_VALUE - WET_VALUE)) * 100

raw_value = read_adc(MOISTURE_CHANNEL)
moisture = calculate_moisture_percentage(raw_value)



"""LDR sensor analog output"""

def read_channel(channel):
    # Read analog data from MCP3008 ADC
    # MCP3008 communication protocol requires 3 bytes:
    # 1st byte: Start bit (1)
    # 2nd byte: Single-ended mode (1) + channel selection (3 bits) + padding
    # 3rd byte: Don't care (0) - needed to clock out the data
    adc = spi.xfer2([1, (8 + channel) << 4, 0])
    
    # Extract the 10-bit ADC value from the response:
    # - adc[1] contains 2 least significant bits of the result
    # - adc[2] contains the remaining 8 bits
    data = ((adc[1] & 3) << 8) + adc[2]
    return data

def convert_to_percent(value, min_val, max_val):
    # Convert raw ADC value to percentage based on calibration range
    # Formula: ((current - min) / (max - min)) * 100
    percent = ((max_val - value) / (max_val - min_val)) * 100
    return max(0, min(100, percent))  # Clamp values to 0-100% range

# Calibration values for the LDR sensor
LDR_MIN = 0      # ADC value in complete darkness (0V)
LDR_MAX = 1023   # ADC value in bright light (3.3V) - 10-bit ADC has max value of 1023

ldr_raw = read_channel(LDR_CHANNEL)
ldr_percent = convert_to_percent(ldr_raw, LDR_MIN, LDR_MAX)



"""Rain Drop Sensor analog output"""

# Calibration values for the rain sensor
DRY_VALUE = 1023   # Value when sensor is completely dry
WET_VALUE = 300    # Value when sensor is wet (adjust based on your sensor)

def read_channel(channel):
    # Read analog data from MCP3008 ADC
    adc = spi.xfer2([1, (8 + channel) << 4, 0])
    data = ((adc[1] & 3) << 8) + adc[2]
    return data

def calculate_wetness_percentage(value):
    # Convert ADC value to wetness percentage
    # Clamp value to calibration range
    value = max(min(value, DRY_VALUE), WET_VALUE)
    # Calculate percentage (reversed because higher ADC value = drier)
    return ((DRY_VALUE - value) / (DRY_VALUE - WET_VALUE)) * 100

raw_value = read_channel(RAIN_CHANNEL)
wetness = calculate_wetness_percentage(raw_value)



"""DHT-22 Sensor"""

# Define sensor type and pin (using BCM pin numbering)
DHT_PIN = 26
dht_sensor = adafruit_dht.DHT22(getattr(board, f"D{DHT_PIN}"))

# Read temperature and humidity
temperature = dht_sensor.temperature
humidity = dht_sensor.humidity



"""BMP180 Sensor"""

# Configuration
DEVICE = 0x77  # I2C address of BMP180 sensor
bus = smbus.SMBus(1)  # Use I2C bus 1 on Raspberry Pi

def getShort(data, index):
    # Combine two bytes and return signed 16-bit value
    return c_short((data[index] << 8) + data[index + 1]).value

def getUshort(data, index):
    # Combine two bytes and return unsigned 16-bit value
    return (data[index] << 8) + data[index + 1]

def readBmp180Id(addr=DEVICE):
    # Read chip ID and version from the sensor
    REG_ID = 0xD0
    (chip_id, chip_version) = bus.read_i2c_block_data(addr, REG_ID, 2)
    return (chip_id, chip_version)

def readBmp180(addr=DEVICE):
    # Register addresses
    REG_CALIB  = 0xAA
    REG_MEAS   = 0xF4
    REG_MSB    = 0xF6
    REG_LSB    = 0xF7
    CRV_TEMP   = 0x2E
    CRV_PRES   = 0x34
    OVERSAMPLE = 3  # Oversampling setting (0-3)

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

    # Request temperature measurement
    bus.write_byte_data(addr, REG_MEAS, CRV_TEMP)
    time.sleep(0.005)  # Wait for measurement
    msb, lsb = bus.read_i2c_block_data(addr, REG_MSB, 2)
    UT = (msb << 8) + lsb

    # Request pressure measurement
    bus.write_byte_data(addr, REG_MEAS, CRV_PRES + (OVERSAMPLE << 6))
    time.sleep(0.04)  # Wait for measurement
    msb, lsb, xsb = bus.read_i2c_block_data(addr, REG_MSB, 3)
    UP = ((msb << 16) + (lsb << 8) + xsb) >> (8 - OVERSAMPLE)

    # Calculate true temperature
    X1 = ((UT - AC6) * AC5) >> 15
    X2 = int((MC << 11) / (X1 + MD))
    B5 = X1 + X2
    temperature = int(B5 + 8) >> 4
    temperature = temperature / 10.0

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

    # Calculate altitude using pressure
    altitude = 44330.0 * (1.0 - pow(pressure / 1013.25, 1.0 / 5.255))
    altitude = round(altitude, 2)

    return (temperature, pressure, altitude)