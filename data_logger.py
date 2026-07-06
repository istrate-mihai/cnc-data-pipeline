"""
data_logger.py

Modbus TCP client that polls modbus_server.py at a fixed interval,
reads the simulated diameter measurement + out-of-control flag, and
persists every reading to SQLite with a timestamp.

This is the "gateway" layer in the real-world data flow:
    Sensor/CMM/Calibru -> Protocol (Modbus/OPC UA) -> Gateway/Script -> DB -> Dashboard

Requires: pymodbus>=3.13
Run modbus_server.py in a separate terminal first.
"""

import argparse
import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pymodbus.client import AsyncModbusTcpClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("data_logger")

HOST = "127.0.0.1"
PORT = 5020
DB_PATH = Path(__file__).parent / "cnc_measurements.db"
POLL_INTERVAL_S = 1.0


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            diameter_mm REAL NOT NULL,
            out_of_control INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def insert_measurement(conn: sqlite3.Connection, diameter_mm: float, flag: int) -> None:
    conn.execute(
        "INSERT INTO measurements (timestamp, diameter_mm, out_of_control) VALUES (?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), diameter_mm, flag),
    )
    conn.commit()


async def poll_loop(
    client: AsyncModbusTcpClient, conn: sqlite3.Connection, max_reads: int | None
) -> None:
    reads = 0
    while max_reads is None or reads < max_reads:
        result = await client.read_holding_registers(address=0, count=2, slave=0)

        if result.isError():
            log.warning("Modbus read error: %s", result)
            await asyncio.sleep(POLL_INTERVAL_S)
            continue

        raw_diameter_um, flag = result.registers
        diameter_mm = raw_diameter_um / 1000.0

        insert_measurement(conn, diameter_mm, flag)
        reads += 1

        if reads % 10 == 0:
            log.info(
                "logged %d readings | last=%.3fmm flag=%d", reads, diameter_mm, flag
            )

        await asyncio.sleep(POLL_INTERVAL_S)


async def main(max_reads: int | None) -> None:
    conn = init_db(DB_PATH)
    log.info("SQLite DB ready at %s", DB_PATH)

    client = AsyncModbusTcpClient(HOST, port=PORT)
    await client.connect()

    if not client.connected:
        log.error(
            "Could not connect to Modbus server at %s:%d. Is modbus_server.py running?",
            HOST,
            PORT,
        )
        return

    log.info("Connected to Modbus server. Logging every %.1fs...", POLL_INTERVAL_S)

    try:
        await poll_loop(client, conn, max_reads)
    finally:
        client.close()
        conn.close()
        log.info("Logger stopped, connection closed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Poll simulated CNC Modbus server and log to SQLite."
    )
    parser.add_argument(
        "--max-reads",
        type=int,
        default=None,
        help="Stop after N readings (omit to run forever, Ctrl+C to stop).",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.max_reads))
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
