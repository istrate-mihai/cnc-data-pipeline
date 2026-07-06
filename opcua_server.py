"""
opcua_server.py

OPC UA variant of modbus_server.py. Same simulated CNC diameter signal,
exposed through OPC UA's object/node model instead of raw Modbus
registers. Runs independently of modbus_server.py -- pick either
protocol to feed data_logger_opcua.py, or run both to show you
understand both integration patterns.

Key difference from Modbus, demonstrated in code below:
    - Modbus: raw register address, no type info, no security
      (client reads "register 0" and has to know externally it means
      "diameter in micrometers")
    - OPC UA: a typed, named node ("Diameter_mm", Double) inside a
      structured object ("CNC_Machine_1") -- self-describing, and the
      server can enforce access control per node.

Requires: asyncua>=2.0
"""

import asyncio
import logging
import random

from asyncua import Server, ua

logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s"
)
logging.getLogger("opcua_server").setLevel(logging.INFO)
log = logging.getLogger("opcua_server")

ENDPOINT = "opc.tcp://0.0.0.0:4840/cnc/server/"
NAMESPACE_URI = "http://schaeffler-demo.local/cnc-pipeline"

# Same process parameters as modbus_server.py, so both protocols simulate
# the same underlying physical process -- lets you cross-check Cp/Cpk
# results between the two ingestion paths if you run both.
TARGET_MM = 10.006
NOISE_STD_MM = 0.021
DRIFT_PER_TICK_MM = 0.0004
UPDATE_INTERVAL_S = 1.0


async def simulate_process(diameter_var, flag_var) -> None:
    """Background task: writes a new fake measurement every second."""
    drift = 0.0
    tick = 0
    while True:
        tick += 1
        drift += DRIFT_PER_TICK_MM
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
    server.set_endpoint(ENDPOINT)
    server.set_server_name("CNC OPC UA Demo Server")

    idx = await server.register_namespace(NAMESPACE_URI)

    # Object model: a "CNC_Machine_1" object with two typed variables.
    # This is the structural difference vs Modbus's flat register list --
    # a client browsing this server sees named, typed, organized nodes.
    objects = server.nodes.objects
    machine = await objects.add_object(idx, "CNC_Machine_1")

    diameter_var = await machine.add_variable(
        idx, "Diameter_mm", 0.0, varianttype=ua.VariantType.Double
    )
    flag_var = await machine.add_variable(
        idx, "OutOfControlFlag", 0, varianttype=ua.VariantType.Int16
    )

    # Allow clients to write too (not used by our read-only logger, but
    # realistic: some OPC UA setups let MES write setpoints back down)
    await diameter_var.set_writable()
    await flag_var.set_writable()

    log.info("Starting OPC UA server at %s", ENDPOINT)

    async with server:
        await simulate_process(diameter_var, flag_var)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Server stopped.")
