CNC Data Pipeline

Simulates the full data flow a real CNC/Modbus-connected machine would produce, matching the "colectare de date din producție" + "dashboard-uri SPC" requirements from the Schaeffler Programator Aplicații Industriale JD.

modbus_server.py  --Modbus TCP-->  data_logger.py  --writes-->  SQLite  --reads-->  spc_analysis.py  -->  control_chart.png
(simulated gauge)                  (gateway/client)             (measurements.db)   (Cp/Cpk report)

Why this architecture

Modbus TCP chosen over OPC UA for the simulator because it's simpler to stand up without a real PLC, and still demonstrates the register-read/scaling problem (floats → uint16) that's the actual gotcha in industrial protocols.
SQLite instead of Postgres/MySQL: zero external dependencies, portable, sufficient for a demo. In production this slot is exactly where a MES database would sit.
Cp/Cpk formulas implemented from scratch (not a library call) — deliberate, so every number in the report can be explained line by line at interview.

Setup

bashpip install -r requirements.txt --break-system-packages   # Linux/Git Bash

⚠ Pinned to pymodbus==3.6.9 deliberately. pymodbus 3.13+ deprecated the context[slave].setValues(...) API in favor of a SimData/SimDevice rewrite — 3.6.9 matches ~all tutorials and docs you'll find and is stable for this scope.

Run (3 terminals)

bash# Terminal 1 — start the simulated machine
python3 modbus_server.py

# Terminal 2 — start logging its output
python3 data_logger.py                  # runs forever, Ctrl+C to stop
python3 data_logger.py --max-reads 30    # or stop after N readings

# Terminal 3 — analyze what's been logged so far
python3 spc_analysis.py

Output: console report (Cp, Cpk, verdict) + control_chart.png.

Register map (modbus_server.py)

AddressMeaningEncoding0Part diametermicrometers, int (10006 = 10.006mm)1Out-of-control flag0 = normal, 1 = beyond 3σ from drift

Simulated process behavior

Target: 10.006mm (matches the hand-calculated example from theory prep)
Noise: Gaussian, σ ≈ 0.021mm
Slow linear drift (+0.4µm/tick) simulates tool wear — Cp stays roughly stable, Cpk degrades over time as the mean walks away from center. This is intentional: it's a concrete example of "Cp good, Cpk bad" to reference at interview.
