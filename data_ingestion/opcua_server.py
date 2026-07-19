"""
data_ingestion/opcua_server.py

OPC UA variant of modbus_server.py. Same simulated CNC diameter signal,
exposed through OPC UA's object/node model.
"""

import asyncio
import logging
import random

from asyncua import Server, ua

from config.settings import (
    OPCUA_ENDPOINT,
    OPCUA_NAMESPACE,
    TARGET_MM,
    NOISE_STD_MM,
    DRIFT_PER_TICK_MM,
    UPDATE_INTERVAL_S,
)

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s"
)
logging.getLogger("opcua_server").setLevel(logging.INFO)
log = logging.getLogger("opcua_server")


async def simulate_process(diameter_var, flag_var) -> None:
    drift = 0.0
    tick = 0
    DRIFT_RESET_THRESHOLD_MM = 2 * NOISE_STD_MM + abs(DRIFT_PER_TICK_MM) * 50
    while True:
        tick += 1
        drift += DRIFT_PER_TICK_MM
        if abs(drift) > DRIFT_RESET_THRESHOLD_MM:
            log.info("tick=%d drift=%.4fmm exceeded threshold — simulating tool change, resetting drift", tick, drift)
            drift = 0.0
        noise = random.gauss(0, NOISE_STD_MM)
        value_mm = round(TARGET_MM + drift + noise, 4)

        out_of_control = 1 if abs(drift + noise) > 3 * NOISE_STD_MM else 0

        await diameter_var.write_value(value_mm, ua.VariantType.Double)
        await flag_var.write_value(out_of_control, ua.VariantType.Int16)

        if tick % 10 == 0:
            log.info(
                "tick=%d diameter=%.4fmm drift=%.4fmm flag=%d",
                tick,
                value_mm,
                drift,
                out_of_control,
            )
        await asyncio.sleep(UPDATE_INTERVAL_S)


async def main() -> None:
    server = Server()
    await server.init()
    server.set_endpoint(OPCUA_ENDPOINT)
    server.set_server_name("CNC OPC UA Demo Server")

    idx = await server.register_namespace(OPCUA_NAMESPACE)

    objects = server.nodes.objects
    machine = await objects.add_object(idx, "CNC_Machine_1")

    diameter_var = await machine.add_variable(
        idx, "Diameter_mm", 0.0, varianttype=ua.VariantType.Double
    )
    flag_var = await machine.add_variable(
        idx, "OutOfControlFlag", 0, varianttype=ua.VariantType.Int16
    )

    await diameter_var.set_writable()
    await flag_var.set_writable()

    log.info("Starting OPC UA server at %s", OPCUA_ENDPOINT)

    async with server:
        await simulate_process(diameter_var, flag_var)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Server stopped.")
