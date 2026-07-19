"""
Central configuration – constants, database paths, limits, and DB connection helpers.
"""

import os
import sqlite3
import psycopg2
from urllib.parse import urlparse

# ----- CNC specifications -----
TARGET = 10.0  # mm
SPEC_LOWER = 9.8
SPEC_UPPER = 10.2

# ----- Modbus/OPC UA simulation constants -----
# Used only by data_ingestion/modbus_server.py, opcua_server.py, data_logger.py
# for the local live-protocol demo (not used by the deployed api.py simulator).
MODBUS_HOST = "localhost"
MODBUS_PORT = 5020
OPCUA_ENDPOINT = "opc.tcp://0.0.0.0:4840/cnc/server/"
OPCUA_NAMESPACE = "http://cnc.example/opcua"

TARGET_MM = TARGET
NOISE_STD_MM = 0.03  # 1-sigma process noise
DRIFT_PER_TICK_MM = 0.0005  # slow tool-wear drift per tick, mm
UPDATE_INTERVAL_S = 1.0

# ----- Paths -----
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "measurements.db")

# ----- Database URL (optional PostgreSQL) -----
DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_db_connection():
    """Return a database connection (SQLite or PostgreSQL)."""
    if DATABASE_URL:
        # PostgreSQL
        return psycopg2.connect(
            DATABASE_URL, sslmode="require" if "render" in DATABASE_URL else "disable"
        )
    else:
        # SQLite
        return sqlite3.connect(DB_PATH)


def get_db_placeholder():
    """Return the correct placeholder for parameterised queries."""
    return "%s" if DATABASE_URL else "?"


def get_create_table_sql():
    """Return the CREATE TABLE statement for the current DB engine."""
    if DATABASE_URL:
        return """
        CREATE TABLE IF NOT EXISTS measurements (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            diameter REAL NOT NULL,
            out_of_control INTEGER DEFAULT 0
        )
        """
    else:
        return """
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            diameter REAL NOT NULL,
            out_of_control INTEGER DEFAULT 0
        )
        """
