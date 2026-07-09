"""
config/settings.py

Constante partajate între toate modulele proiectului.
Toate căile și parametrii de simulare sunt centralizați aici.
"""

from pathlib import Path

# Calea absolută a rădăcinii proiectului (cnc-data-pipeline/)
BASE_DIR = Path(__file__).parent.parent

# Către baza de date SQLite
DB_DIR = BASE_DIR / "db"
DB_PATH = DB_DIR / "cnc_measurements.db"

# Limitele de specificație (mm)
USL = 10.10
LSL = 9.90

# Parametrii procesului (simulare)
TARGET_MM = 10.006
NOISE_STD_MM = 0.021
DRIFT_PER_TICK_MM = 0.0004

# Intervale (secunde)
UPDATE_INTERVAL_S = 1.0
POLL_INTERVAL_S = 1.0

# Modbus/OPC UA
MODBUS_HOST = "127.0.0.1"
MODBUS_PORT = 5020
OPCUA_ENDPOINT = "opc.tcp://0.0.0.0:4840/cnc/server/"
OPCUA_NAMESPACE = "http://schaeffler-demo.local/cnc-pipeline"

# Seed
SEED_COUNT = 40
