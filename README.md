# CNC Data Pipeline

Simulates the full data flow a real CNC/Modbus-connected machine would produce, matching the "colectare de date din producție" + "dashboard-uri SPC" requirements from the Schaeffler Programator Aplicații Industriale JD.

![Live SPC Dashboard](./images/spc_dashboard.png)

```
modbus_server.py   --Modbus TCP-->  data_logger.py  --writes-->  SQLite  <--reads--  api.py (FastAPI dashboard)
opcua_server.py     --OPC UA-->     (alt. client, same DB)                <--reads--  spc_analysis.py (CLI report + PNG chart)
```

## Why this architecture

- **Two protocols (Modbus + OPC UA)** simulated in parallel, on purpose: the JD explicitly lists both as "avantaj". Same underlying signal, different wire format — demonstrates the actual integration tradeoff at interview.
- **SQLite** instead of Postgres/MySQL: zero external dependencies, portable. In production this slot is exactly where a MES database would sit.
- **Cp/Cpk formulas implemented from scratch** (not a library call) — every number in the report is explainable line by line.
- **FastAPI dashboard** with a background simulator: makes the deployed instance genuinely live (new data every 2s) without needing a separate always-on Modbus process on a free hosting tier.

## Setup

```bash
pip install -r requirements.txt --break-system-packages   # Linux/Git Bash
```

⚠ Pinned to `pymodbus==3.6.9` deliberately. pymodbus 3.13+ deprecated the `context[slave].setValues(...)` API in favor of a SimData/SimDevice rewrite — 3.6.9 matches ~all tutorials/docs and is stable for this scope.

## Run locally — full pipeline (3 terminals)

```bash
# Terminal 1 — simulated machine (Modbus)
python3 modbus_server.py

# Terminal 2 — logging its output
python3 data_logger.py --max-reads 30    # or omit --max-reads to run forever

# Terminal 3 — CLI analysis (console report + control_chart.png)
python3 spc_analysis.py
```

## Run locally — OPC UA variant

```bash
python3 opcua_server.py
```

Exposes the same simulated signal as a typed OPC UA object (`CNC_Machine_1.Diameter_mm`, `CNC_Machine_1.OutOfControlFlag`) at `opc.tcp://127.0.0.1:4840/cnc/server/`, instead of raw Modbus registers. Browse it with any OPC UA client (e.g. UAExpert) or `asyncua`'s own `Client` class to see the difference in practice: named/typed nodes vs. flat register addresses.

## Run locally — live dashboard

```bash
uvicorn api:app --reload --port 8000
```

Open `http://localhost:8000` — live chart + Cp/Cpk cards, refreshing every 2s. Reads from `cnc_measurements.db`; if you're also running `modbus_server.py` + `data_logger.py`, the dashboard shows real pipeline data. If not, its own background task keeps generating simulated readings so the page isn't static.

## Deploy to Render (public URL)

1. Push this folder to a GitHub repo.
2. On Render: **New → Blueprint**, point at the repo — `render.yaml` auto-configures the service (Docker, free plan).
3. Alternatively, **New → Web Service**, select "Docker" as the environment, point at this repo — Render will use the included `Dockerfile`.
4. First deploy runs `seed_demo_data.py` (via `Dockerfile`) so the dashboard has data immediately; the background simulator in `api.py` keeps it moving after that.
5. Render gives you a public URL (`https://<service-name>.onrender.com`) — that's what you send/show at the interview.

⚠ Free tier note: Render's free web services spin down after inactivity and take a few seconds to wake on the next request — mention this if asked, it's normal and expected for a free-tier demo, not a bug.

## Register map (modbus_server.py)

| Address | Meaning | Encoding |
|---|---|---|
| 0 | Part diameter | micrometers, int (10006 = 10.006mm) |
| 1 | Out-of-control flag | 0 = normal, 1 = beyond 3σ from drift |

## OPC UA node map (opcua_server.py)

| Node | Type | Meaning |
|---|---|---|
| `CNC_Machine_1.Diameter_mm` | Double | Part diameter, mm (no scaling needed — floats are native) |
| `CNC_Machine_1.OutOfControlFlag` | Int16 | 0 = normal, 1 = beyond 3σ from drift |

## Simulated process behavior

- Target: 10.006mm (matches the hand-calculated example from theory prep)
- Noise: Gaussian, σ ≈ 0.021mm
- Slow linear drift simulates tool wear — Cp stays roughly stable, **Cpk degrades over time** as the mean walks away from center. Concrete example of "Cp good, Cpk bad" to reference at interview.
