# CNC Data Pipeline

A complete data pipeline that simulates a CNC machine producing diameter measurements, exposes them via Modbus TCP and OPC UA, logs them to a database (SQLite or PostgreSQL), and serves a live SPC dashboard with FastAPI + Chart.js.

---

## Features

* **Simulated Modbus server** (port 5020) generating diameter + out‑of‑control flag every second, with drift capped and reset (simulated tool change) so long-running sessions stay within a realistic range.
* **OPC UA server** (port 4840) exposing the same data as typed nodes.
* **Data logger** polls Modbus and writes to the database.
* **FastAPI dashboard** with live chart, `/api/measurements`, `/api/stats` (Cp/Cpk), and `/api/fmea` (RPN).
* **SPC control chart** (`/api/spc_chart`) and **diameter distribution chart** (`/api/distribution_chart`, histogram + normal fit) — both windowed to the most recent readings (`CHART_WINDOW`, default 300) so they stay readable at scale.
* **Background simulator** keeps data flowing even when Modbus is off.
* **FMEA RPN calculator** – CLI script and API endpoint.
* **PostgreSQL support** via `DATABASE_URL` environment variable.
* **Alerting** – sends Slack or email notifications when an out‑of‑control measurement occurs.

---

## Screenshots

![CNC Dashboard](images/spc_dashboard.png)

*Live dashboard showing diameter trends, Cp/Cpk, FMEA RPN, and one‑click SPC control chart.*

## Setup

1. **Clone the repository** and navigate into the project root.
2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Git Bash / Linux
   # or: venv\Scripts\activate on Windows
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## Running the Pipeline

### Local (SQLite Default)

Always ensure you run these commands from the project root directory.

1. **Start the Modbus server** (in a separate terminal):
   ```bash
   python -m data_ingestion.modbus_server
   ```
2. **Start the OPC UA server** (optional, separate terminal):
   ```bash
   python -m data_ingestion.opcua_server
   ```
3. **Start the data logger** (in a separate terminal):
   ```bash
   python -m data_ingestion.data_logger
   ```
4. **Start the FastAPI dashboard** (in another terminal):
   ```bash
   uvicorn app.api:app --reload
   ```
5. Open [http://localhost:8000](http://localhost:8000) in your browser.

### Using PostgreSQL

1. **Start PostgreSQL via Docker Compose:**
   ```bash
   docker-compose up -d
   ```
2. **Set the environment variable:**
   ```bash
   export DATABASE_URL=postgresql://cnc:cncpass@localhost:5432/cnc_db
   ```
3. Run the pipeline components as described in the SQLite steps above. The logger and API will automatically detect the environment variable and switch to PostgreSQL.

### Seed Initial Data (Optional)

To populate the database with demonstration data before running the logger:
```bash
python -m data_ingestion.seed_demo_data
```

To start fresh (e.g. before a live demo, if local test runs have accumulated a lot of data):
```bash
rm db/measurements.db
python -m data_ingestion.seed_demo_data
```

---

## FMEA RPN Calculator (CLI)

To calculate Risk Priority Numbers via the command-line utility:
```bash
python -m app.fmea_rpn
```
*Note: Alternatively, you can query this dynamically via the API endpoint at `GET /api/fmea`.*

---

## Alerting Configuration

To enable automated alerts when measurements cross control limits, set the relevant environment variables before starting the data logger:

### Slack Integration
```bash
export SLACK_WEBHOOK_URL=[https://hooks.slack.com/services/](https://hooks.slack.com/services/)...
```

### Email Integration (SMTP)
```bash
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=your_email@gmail.com
export SMTP_PASSWORD=your_app_password
export ALERT_RECIPIENT=recipient@example.com
```

---

## Deployment on Render

1. Push your repository to GitHub.
2. Create a new **Web Service** on Render pointing to your repository.
3. Add the `DATABASE_URL` environment variable if connecting to Render's managed PostgreSQL instance.
4. The included `render.yaml` and `Dockerfile` will automatically handle the multi-component build sequence.

---

## Project Structure

```text
.
├── app/
│   ├── api.py                 # FastAPI app & endpoints
│   ├── fmea_rpn.py            # RPN calculator (CLI + endpoint)
│   ├── alerting.py            # Slack and email alert logic
│   └── templates/
│       └── dashboard.html     # Live UI elements (Chart.js)
├── data_ingestion/
│   ├── modbus_server.py       # Simulates industrial Modbus TCP data map
│   ├── opcua_server.py        # Simulates industrial OPC UA node structure
│   ├── data_logger.py         # Polls Modbus, commits to DB, triggers alerts
│   └── seed_demo_data.py      # Populates database with evaluation data
├── config/
│   └── settings.py            # Central config, thresholds, and database helpers
├── db/                        # SQLite storage destination (auto‑created)
├── docker-compose.yml         # Local PostgreSQL container configuration
├── requirements.txt           # Application dependencies
├── Dockerfile                 # Multi-stage container assembly blueprint
└── render.yaml                # Infrastructure-as-code orchestration manifest
```

---

## SPC Analysis

Run the standalone Statistical Process Control report generator to run off-line calculations:
```bash
python -m app.spc_analysis
```
This utility outputs a detailed calculation log to the console and generates a statistical chart saved locally as `control_chart.png`. By default it uses the full measurement history.

To match the dashboard's windowed view (last 300 readings) instead of the full history:
```bash
python -m app.spc_analysis --limit 300
```

Or any other window size:
```bash
python -m app.spc_analysis --limit 100 --output recent_chart.png
```

The dashboard also exposes a second chart — a histogram of diameters with a fitted normal curve (`/api/distribution_chart`) — showing process centering and spread relative to spec, complementary to the time-ordered control chart.
