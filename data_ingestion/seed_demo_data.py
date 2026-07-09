"""
Seed the database with 40 initial measurements for demonstration.
"""

import random
import sqlite3
from datetime import datetime, timedelta
from config.settings import (
    DB_PATH,
    TARGET,
    SPEC_LOWER,
    SPEC_UPPER,
    get_create_table_sql,
    get_db_connection,
    get_db_placeholder,
)


def seed_demo_data():
    """Insert 40 random readings into the measurements table."""
    conn = get_db_connection()
    cur = conn.cursor()
    # Ensure table exists
    cur.execute(get_create_table_sql())

    placeholder = get_db_placeholder()
    now = datetime.now()
    for i in range(40):
        # Generate a random diameter mostly within spec, some slightly outside
        diameter = TARGET + random.uniform(-0.20, 0.20)
        # Out-of-control ~10% of the time for demo variety
        out_of_control = 1 if random.random() < 0.10 else 0
        timestamp = now - timedelta(seconds=(40 - i))
        cur.execute(
            f"INSERT INTO measurements (timestamp, diameter, out_of_control) VALUES ({placeholder}, {placeholder}, {placeholder})",
            (timestamp.isoformat(), diameter, out_of_control),
        )
    conn.commit()
    conn.close()
    print(f"✅ Seeded 40 demo measurements into {DB_PATH}")


if __name__ == "__main__":
    seed_demo_data()
