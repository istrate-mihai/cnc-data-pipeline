# CNC Data Pipeline

Simulates the full data flow a real CNC/Modbus-connected machine would produce, matching the "colectare de date din producție" + "dashboard-uri SPC" requirements from the Schaeffler Programator Aplicații Industriale JD.

![Live SPC Dashboard](./images/spc_dashboard.png)

```
modbus_server.py --Modbus TCP--> data_logger.py --writes--> SQLite <--reads-- api.py (FastAPI dashboard)
opcua_server.py  --OPC UA----> (alt. client, same DB) <--reads-- spc_analysis.py (CLI report + PNG chart)
```

---

## Project Structure

```text
cnc-data-pipeline/
├── app/                       # Dashboard & SPC logic
│   ├── api.py                 # FastAPI endpoints
│   ├── spc_analysis.py        # Cp/Cpk + control chart generator
│   └── templates/
│       └── dashboard.html     # Live UI
├── data_ingestion/            # Simulated sources + logger
│   ├── modbus_server.py       # Modbus TCP simulator
│   ├── opcua_server.py        # OPC UA simulator
│   ├── data_logger.py         # Modbus -> SQLite gateway
│   └── seed_demo_data.py      # Initial data populator
├── config/
│   └── settings.py            # Centralized constants (limits, paths, etc.)
├── db/                        # SQLite database (auto-created)
├── requirements.txt
├── Dockerfile
└── render.yaml
```

---

## Why This Architecture

* **Two protocols (Modbus + OPC UA)** simulated in parallel, on purpose: the JD explicitly lists both as "avantaj". Same underlying signal, different wire format — demonstrates the actual integration tradeoff at interview.
* **SQLite** instead of Postgres/MySQL: zero external dependencies, portable. In production this slot is exactly where a MES database would sit.
* **Cp/Cpk formulas implemented from scratch** (not a library call) — every number in the report is explainable line by line.
* **FastAPI dashboard** with a background simulator: makes the deployed instance genuinely live (new data every 2s) without needing a separate always-on Modbus process on a free hosting tier.
* **Modular structure**: `app/`, `data_ingestion/`, `config/` separate concerns, easy to extend with new protocols (MQTT, etc.).

---

## Setup

```bash
# Clone the repo and enter the directory
cd cnc_data_pipeline

# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/Scripts/activate     # Git Bash / Linux
# or: venv\Scripts\activate      # Windows CMD

# Install dependencies
pip install -r requirements.txt
```

> ⚠️ **Note:** Pinned to `pymodbus==3.6.9` deliberately. `pymodbus 3.13+` deprecated the `context[slave].setValues(...)` API in favor of a `SimData/SimDevice` rewrite — 3.6.9 matches almost all tutorials/docs and is stable for this scope.

---

## Running Locally

### Full Pipeline (Requires 3 terminals)
All commands must be run from the project root (`cnc_data_pipeline/`) with the virtual environment activated.

| Terminal | Command | Description |
| :--- | :--- | :--- |
| **1** | `python data_ingestion/modbus_server.py` | Simulated CNC machine (Modbus TCP) |
| **2** | `python data_ingestion/data_logger.py` | Reads Modbus, writes to SQLite |
| **3** | `uvicorn app.api:app --reload --port 8000` | Live dashboard (http://localhost:8000) |

* Terminals 1 & 2 run forever – press `Ctrl+C` to stop.
* Terminal 3 can be stopped with `Ctrl+C` as well.
* *Optional:* Use `--max-reads 30` with `data_logger.py` to stop after N readings.

### OPC UA Variant
```bash
python data_ingestion/opcua_server.py
```
Exposes the same simulated signal as a typed OPC UA object (`CNC_Machine_1.Diameter_mm`, `CNC_Machine_1.OutOfControlFlag`) at `opc.tcp://127.0.0.1:4840/cnc/server/`, instead of raw Modbus registers. 

Browse it with any OPC UA client (e.g., UAExpert) or asyncua's own `Client` class to see the difference in practice: named/typed nodes vs. flat register addresses.

### Seed Initial Data (Optional)
If you want to populate the database with 40 simulated measurements before starting the logger:
```bash
python data_ingestion/seed_demo_data.py
```
*Note: This is also automatically executed during the Docker build (used on Render).*

### Offline SPC Analysis
After collecting enough data (e.g., 100+ readings), generate a console report and a control chart PNG:
```bash
python app/spc_analysis.py
```
The chart is saved as `images/control_chart.png`.

---

## Protocol & Data Mapping

### Register Map (`modbus_server.py`)
| Address | Meaning | Encoding |
| :--- | :--- | :--- |
| **0** | Part diameter | micrometers, int (10006 = 10.006mm) |
| **1** | Out-of-control flag | 0 = normal, 1 = beyond 3σ from drift |

### OPC UA Node Map (`opcua_server.py`)
| Node | Type | Meaning |
| :--- | :--- | :--- |
| `CNC_Machine_1.Diameter_mm` | Double | Part diameter, mm (no scaling needed — floats are native) |
| `CNC_Machine_1.OutOfControlFlag` | Int16 | 0 = normal, 1 = beyond 3σ from drift |

---

## Simulated Process Behavior

* **Target:** 10.006mm (matches the hand-calculated example from theory prep)
* **Noise:** Gaussian, σ ≈ 0.021mm
* **Drift:** Slow linear drift simulates tool wear — Cp stays roughly stable, Cpk degrades over time as the mean walks away from center. This serves as a concrete example of *"Cp good, Cpk bad"* to reference during the interview.

---

## Troubleshooting

* **`ModuleNotFoundError: No module named 'config'`** when running scripts from `data_ingestion/` or `app/`: This is fixed. All scripts now add the project root to `sys.path` automatically.
* **`No module named 'pymodbus'`**: Ensure your virtual environment is activated and dependencies are installed (`pip install -r requirements.txt`).
* **Port conflicts**: Change the port in `app.api` or in the `modbus_server.py`/`data_logger.py` settings (adjust `config/settings.py`).
