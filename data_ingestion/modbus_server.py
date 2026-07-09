"""
data_ingestion/modbus_server.py

Simulates a CNC machine's measurement output over Modbus TCP.
"""

import asyncio
import logging
import random
import sys
from pathlib import Path

# Add project root to sys.path so that 'config' and 'app' can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartAsyncTcpServer

from config.settings import (
    MODBUS_HOST,
    MODBUS_PORT,
    TARGET_MM,
    NOISE_STD_MM,
    DRIFT_PER_TICK_MM,
    UPDATE_INTERVAL_S,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("modbus_server")

TARGET_UM = int(TARGET_MM * 1000)
NOISE_STD_UM = int(NOISE_STD_MM * 1000)
DRIFT_PER_TICK_UM = DRIFT_PER_TICK_MM * 1000


async def simulate_process(context: ModbusServerContext) -> None:
    slave_ctx: ModbusSlaveContext = context[0x00]
    drift = 0.0
    tick = 0
    while True:
        tick += 1
        drift += DRIFT_PER_TICK_UM
        noise = random.gauss(0, NOISE_STD_UM)
        value_um = round(TARGET_UM + drift + noise)
        value_um = max(0, min(65535, value_um))

        out_of_control_flag = 1 if abs(drift + noise) > 3 * NOISE_STD_UM else 0

        slave_ctx.setValues(3, 0, [value_um])
        slave_ctx.setValues(3, 1, [out_of_control_flag])

        if tick % 10 == 0:
            log.info(
                "tick=%d diameter=%.3fmm drift=%.3fum flag=%d",
                tick,
                value_um / 1000,
                drift,
                out_of_control_flag,
            )
        await asyncio.sleep(UPDATE_INTERVAL_S)


async def main() -> None:
    slave_ctx = ModbusSlaveContext(
        hr=ModbusSequentialDataBlock(0, [0] * 10),
    )
    context = ModbusServerContext(slaves=slave_ctx, single=True)

    log.info(
        "Starting simulated CNC Modbus TCP server on %s:%d", MODBUS_HOST, MODBUS_PORT
    )

    server_task = asyncio.create_task(
        StartAsyncTcpServer(context=context, address=(MODBUS_HOST, MODBUS_PORT))
    )
    sim_task = asyncio.create_task(simulate_process(context))

    await asyncio.gather(server_task, sim_task)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Server stopped.")
