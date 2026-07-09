"""
data_ingestion/seed_demo_data.py

Generates an initial batch of simulated measurements directly into
cnc_measurements.db, using the same process model as modbus_server.py.
"""

import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    DB_PATH,
    TARGET_MM,
    NOISE_STD_MM,
    DRIFT_PER_TICK_MM,
    SEED_COUNT,
)


def main() -> None:
    # Ensure database directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

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
