"""
Data logger – polls the Modbus server and stores measurements in the database.
Also triggers alerts if an out‑of‑control measurement is detected.
"""

import time
from datetime import datetime
from pymodbus.client import ModbusTcpClient

from config.settings import (
    get_db_connection,
    get_db_placeholder,
    get_create_table_sql,
)
from app.alerting import notify

# Modbus server settings (must match modbus_server.py)
MODBUS_HOST = "localhost"
MODBUS_PORT = 5020
UNIT_ID = 1

# Addresses
DIAMETER_ADDR = 0  # holding register
OOC_ADDR = 1  # coil


def log_measurement(diameter, out_of_control):
    """
    Insert a measurement into the database and trigger alerts if out_of_control is 1.
    Returns True on success.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    # Ensure the table exists
    cur.execute(get_create_table_sql())
    placeholder = get_db_placeholder()
    cur.execute(
        f"INSERT INTO measurements (diameter, out_of_control) VALUES ({placeholder}, {placeholder})",
        (diameter, int(out_of_control)),
    )
    conn.commit()
    timestamp = datetime.now().isoformat()
    conn.close()

    # Alert if out of control
    if out_of_control:
        notify(
            {
                "diameter": diameter,
                "timestamp": timestamp,
                "out_of_control": int(out_of_control),
            }
        )
    return True


def main():
    """Main polling loop – reads Modbus every second and logs."""
    client = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT)
    if not client.connect():
        print("ERROR: Cannot connect to Modbus server. Is it running?")
        return

    print("Data logger started. Press Ctrl+C to stop.")
    try:
        while True:
            # Read diameter (holding register)
            rr = client.read_holding_registers(DIAMETER_ADDR, 1, unit=UNIT_ID)
            if rr.isError():
                print("Modbus read error (diameter)")
                time.sleep(1)
                continue
            diameter = rr.registers[0] / 100.0  # scale back to mm

            # Read out‑of‑control flag (coil)
            cr = client.read_coils(OOC_ADDR, 1, unit=UNIT_ID)
            if cr.isError():
                print("Modbus read error (OOC flag)")
                time.sleep(1)
                continue
            out_of_control = cr.bits[0]

            # Log to database
            log_measurement(diameter, out_of_control)
            time.sleep(1)
    except KeyboardInterrupt:
        print("Logger stopped.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
