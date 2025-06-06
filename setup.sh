#!/bin/bash

echo "===== Raspberry Pi Data Logger Setup ====="
echo "This script will set up the environment for the data logger application."

# Check if running on Raspberry Pi
if [ ! -f /etc/os-release ] || ! grep -q "Raspberry Pi" /etc/os-release; then
    echo "Warning: This script is designed for Raspberry Pi. It may not work correctly on other systems."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled."
        exit 1
    fi
 fi

# Install system dependencies
echo "\nInstalling system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv i2c-tools python3-smbus python3-dev

# Enable I2C and SPI if not already enabled
echo "\nEnabling I2C and SPI interfaces..."
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt; then
    echo "dtparam=i2c_arm=on" | sudo tee -a /boot/config.txt
    echo "I2C interface enabled."
fi

if ! grep -q "^dtparam=spi=on" /boot/config.txt; then
    echo "dtparam=spi=on" | sudo tee -a /boot/config.txt
    echo "SPI interface enabled."
fi

# Create virtual environment
echo "\nCreating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install required Python packages
echo "\nInstalling required Python packages..."
pip install adafruit-circuitpython-dht
pip install board
pip install spidev
pip install RPi.GPIO
pip install smbus2

# Create data directory from config
DATA_DIR=$(python3 -c "import json; print(json.load(open('sensor_logger.json'))['logger']['data_folder'])")
DATA_DIR=${DATA_DIR/#~/$HOME}
echo "\nCreating data directory: $DATA_DIR"
mkdir -p "$DATA_DIR"

echo "\n===== Setup Complete! ====="
echo "To activate the virtual environment, run: source venv/bin/activate"
echo "To start the data logger, run: python data_logger.py"