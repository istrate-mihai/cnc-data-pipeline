"""
modbus_server.py

Simulates a CNC machine's measurement output over Modbus TCP.
A real machine would expose sensor/gauge readings (e.g. part diameter
from an inline digital caliper) via holding registers. This server
fakes that signal so the rest of the pipeline (data_logger.py,
spc_analysis.py) can be built and tested without real hardware.

Register map (holding registers, function code 0x03/0x06):
    Address 0: part diameter, encoded as micrometers (int, e.g. 10006 = 10.006 mm)
               Modbus registers are 16-bit unsigned ints (0-65535), so we
               can't send floats directly -- this is the standard real-world
               workaround: scale to an integer unit.
    Address 1: simulated process drift flag (0 = normal, 1 = out-of-control
               injected for testing alerting logic downstream)

Pinned to pymodbus==3.6.9 deliberately: pymodbus 3.13+ deprecated the
context[slave_id].setValues(...) API in favor of a SimData/SimDevice
rewrite. 3.6.9 is the API you'll find in ~all tutorials and pymodbus docs,
and is stable enough for this use case.
"""

import asyncio
import logging
import random

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartAsyncTcpServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("modbus_server")

HOST = "127.0.0.1"
PORT = 5020  # >1024 so it doesn't need root/admin privileges

# Process parameters -- centered at 10.006mm, matching the worked example
# from the SPC theory session. Real drift is simulated as a slow linear
# shift plus random noise, so Cp stays stable but Cpk degrades over time.
TARGET_UM = 10_006        # target diameter in micrometers (10.006 mm)
NOISE_STD_UM = 21         # ~ the s=0.0207mm we calculated by hand
DRIFT_PER_TICK_UM = 0.4   # slow centerline shift, simulates tool wear
UPDATE_INTERVAL_S = 1.0


async def simulate_process(context: ModbusServerContext) -> None:
    """Background task: writes a new fake measurement every second."""
    slave_ctx: ModbusSlaveContext = context[0x00]
    drift = 0.0
    tick = 0
    while True:
        tick += 1
        drift += DRIFT_PER_TICK_UM
        noise = random.gauss(0, NOISE_STD_UM)
        value_um = round(TARGET_UM + drift + noise)
        value_um = max(0, min(65535, value_um))  # clamp to uint16 range

        out_of_control_flag = 1 if abs(drift + noise) > 3 * NOISE_STD_UM else 0

        # function code 3 = holding registers
        slave_ctx.setValues(3, 0, [value_um])
        slave_ctx.setValues(3, 1, [out_of_control_flag])

        if tick % 10 == 0:
            log.info(
                "tick=%d diameter=%.3fmm drift=%.3fum flag=%d",
                tick, value_um / 1000, drift, out_of_control_flag,
            )
        await asyncio.sleep(UPDATE_INTERVAL_S)


async def main() -> None:
    slave_ctx = ModbusSlaveContext(
        hr=ModbusSequentialDataBlock(0, [0] * 10),  # holding registers, 10 slots
    )
    context = ModbusServerContext(slaves=slave_ctx, single=True)

    log.info("Starting simulated CNC Modbus TCP server on %s:%d", HOST, PORT)

    server_task = asyncio.create_task(
        StartAsyncTcpServer(context=context, address=(HOST, PORT))
    )
    sim_task = asyncio.create_task(simulate_process(context))

    await asyncio.gather(server_task, sim_task)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Server stopped.")
