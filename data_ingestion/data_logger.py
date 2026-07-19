"""
Data logger – polls the Modbus server and stores measurements in the database.
Also triggers alerts if an out‑of‑control measurement is detected.
"""

import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to sys.path so 'config' and 'app' are importable when this
# file is run directly (python data_ingestion/data_logger.py only puts
# data_ingestion/ on sys.path by default, not the project root).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
# modbus_server.py writes both values via setValues(3, ...) -> function code 3
# (holding registers). There is no coil datastore configured on the server,
# so OOC_ADDR must be read with read_holding_registers, not read_coils.
DIAMETER_ADDR = 0  # holding register
OOC_ADDR = 1  # holding register


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
            # modbus_server.py stores the diameter as an integer in
            # micrometres (value_um = round(TARGET_UM + drift + noise)),
            # so scale by 1000, not 100, to get back to mm.
            diameter = rr.registers[0] / 1000.0  # scale back to mm

            # Read out‑of‑control flag (holding register, not a coil —
            # see comment on OOC_ADDR above)
            cr = client.read_holding_registers(OOC_ADDR, 1, unit=UNIT_ID)
            if cr.isError():
                print("Modbus read error (OOC flag)")
                time.sleep(1)
                continue
            out_of_control = cr.registers[0]

            # Log to database
            log_measurement(diameter, out_of_control)
            time.sleep(1)
    except KeyboardInterrupt:
        print("Logger stopped.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
