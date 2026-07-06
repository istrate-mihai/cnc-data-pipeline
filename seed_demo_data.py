"""
seed_demo_data.py

Generates an initial batch of simulated measurements directly into
cnc_measurements.db, using the same process model as modbus_server.py
(target 10.006mm, Gaussian noise, linear drift). Used at container
build time so the deployed dashboard has data to show immediately,
without needing a live Modbus/OPC UA source on the hosting platform.

Run manually if you want to reset/reseed the demo DB:
    python3 seed_demo_data.py
"""

import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "cnc_measurements.db"

TARGET_MM = 10.006
NOISE_STD_MM = 0.021
DRIFT_PER_TICK_MM = 0.0004
SEED_COUNT = 40


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
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

    drift = 0.0
    now = datetime.now(timezone.utc)
    for i in range(SEED_COUNT):
        drift += DRIFT_PER_TICK_MM
        noise = random.gauss(0, NOISE_STD_MM)
        value_mm = round(TARGET_MM + drift + noise, 4)
        flag = 1 if abs(drift + noise) > 3 * NOISE_STD_MM else 0
        ts = (now - timedelta(seconds=(SEED_COUNT - i))).isoformat()
        conn.execute(
            "INSERT INTO measurements (timestamp, diameter_mm, out_of_control) VALUES (?, ?, ?)",
            (ts, value_mm, flag),
        )

    conn.commit()
    conn.close()
    print(f"Seeded {SEED_COUNT} demo measurements into {DB_PATH}")


if __name__ == "__main__":
    main()
