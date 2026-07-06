"""
api.py

FastAPI dashboard for the CNC data pipeline. Reads from the same SQLite
DB that data_logger.py writes to, and exposes:

    GET /api/measurements   -> latest N readings as JSON
    GET /api/stats          -> current Cp/Cpk report as JSON
    GET /                   -> HTML page with a live-updating chart
                               (polls /api/measurements + /api/stats
                               every 2s via vanilla JS + Chart.js CDN)

This is the "dashboard" deliverable for the Schaeffler interview --
a single deployable service (Render-friendly) that turns the pipeline
into something a non-technical reviewer can open in a browser.

On startup, a background asyncio task keeps appending new simulated
measurements (same process model as modbus_server.py) so the deployed
instance stays "live" without needing a separate Modbus/OPC UA process
running on the hosting platform. Locally, you can instead run the real
pipeline (modbus_server.py + data_logger.py) and this API will read
whatever is actually in the DB -- the background simulator only adds
extra ticks, it doesn't replace real data.

Run locally:
    uvicorn api:app --reload --port 8000

Requires: fastapi, uvicorn, pandas (reuses spc_analysis.py's logic)
"""

import asyncio
import random
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from spc_analysis import calculate_capability, USL, LSL

DB_PATH = Path(__file__).parent / "cnc_measurements.db"

# Same process model as modbus_server.py / seed_demo_data.py, so the
# background simulator here produces a signal consistent with the rest
# of the pipeline.
TARGET_MM = 10.006
NOISE_STD_MM = 0.021
DRIFT_PER_TICK_MM = 0.0004

app = FastAPI(title="CNC Data Pipeline Dashboard")
_drift_state = {"value": 0.0}


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            diameter_mm REAL NOT NULL,
            out_of_control INTEGER NOT NULL
        )
        """
    )


async def _background_simulator() -> None:
    """Appends one new simulated measurement every 2s, forever."""
    while True:
        _drift_state["value"] += DRIFT_PER_TICK_MM
        noise = random.gauss(0, NOISE_STD_MM)
        value_mm = round(TARGET_MM + _drift_state["value"] + noise, 4)
        flag = 1 if abs(_drift_state["value"] + noise) > 3 * NOISE_STD_MM else 0

        conn = sqlite3.connect(DB_PATH)
        _ensure_table(conn)
        conn.execute(
            "INSERT INTO measurements (timestamp, diameter_mm, out_of_control) VALUES (?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), value_mm, flag),
        )
        conn.commit()
        conn.close()

        await asyncio.sleep(2.0)


@app.on_event("startup")
async def start_background_simulator() -> None:
    conn = sqlite3.connect(DB_PATH)
    _ensure_table(conn)
    conn.commit()
    conn.close()
    asyncio.create_task(_background_simulator())


def _load_recent(limit: int = 100) -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame(
            columns=["id", "timestamp", "diameter_mm", "out_of_control"]
        )
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT id, timestamp, diameter_mm, out_of_control FROM measurements "
        "ORDER BY id DESC LIMIT ?",
        conn,
        params=(limit,),
    )
    conn.close()
    return df.iloc[::-1].reset_index(drop=True)  # chronological order


@app.get("/api/measurements")
def get_measurements(limit: int = 100) -> JSONResponse:
    df = _load_recent(limit)
    return JSONResponse(df.to_dict(orient="records"))


@app.get("/api/stats")
def get_stats() -> JSONResponse:
    df = _load_recent(limit=1000)
    if df.empty or len(df) < 2:
        return JSONResponse({"error": "Not enough data yet. Run data_logger.py first."})
    stats = calculate_capability(df, USL, LSL)
    stats["usl"] = USL
    stats["lsl"] = LSL
    return JSONResponse(stats)


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CNC Data Pipeline Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, Segoe UI, sans-serif; margin: 1rem; background: #0f172a; color: #e2e8f0; }
  h1 { font-size: 1.3rem; margin-bottom: 0.25rem; }
  .subtitle { color: #94a3b8; margin-bottom: 1.5rem; font-size: 0.85rem; }
  
  /* Mobile-first CSS Grid for stats */
  .stats { 
    display: grid; 
    grid-template-columns: repeat(2, 1fr); 
    gap: 0.75rem; 
    margin-bottom: 1.5rem; 
  }
  .card { background: #1e293b; border-radius: 8px; padding: 0.85rem 1rem; min-width: 0; }
  .card .label { font-size: 0.7rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
  .card .value { font-size: 1.3rem; font-weight: 600; margin-top: 0.25rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  
  .verdict-capable { color: #4ade80; }
  .verdict-marginal { color: #facc15; }
  .verdict-notcapable { color: #f87171; }
  
  /* Chart Container to handle aspect ratios cleanly */
  .chart-container { position: relative; width: 100%; height: 260px; background: #1e293b; border-radius: 8px; padding: 0.5rem; }
  canvas { width: 100% !important; height: 100% !important; }

  /* Desktop layout upgrades */
  @media (min-width: 640px) {
    body { margin: 2rem; }
    h1 { font-size: 1.6rem; }
    .subtitle { font-size: 0.9rem; }
    .stats { grid-template-columns: repeat(5, 1fr); gap: 1rem; }
    .card { padding: 1rem 1.5rem; }
    .card .value { font-size: 1.6rem; }
    .chart-container { height: 350px; padding: 1rem; }
  }
</style>
</head>
<body>
  <h1>CNC Data Pipeline &mdash; Live SPC Dashboard</h1>
  <div class="subtitle">Simulated part diameter measurements, polled every 2s</div>

  <div class="stats" id="stats"></div>
  <div class="chart-container">
    <canvas id="chart"></canvas>
  </div>

  <script>
    const ctx = document.getElementById('chart').getContext('2d');
    const chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          label: 'Diameter (mm)',
          data: [],
          borderColor: '#60a5fa',
          backgroundColor: 'rgba(96,165,250,0.1)',
          tension: 0.2,
          pointRadius: 1.5,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false, // Allows container height via CSS media queries
        scales: {
          x: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: '#334155' } },
          y: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: '#334155' } }
        },
        plugins: { 
          legend: { labels: { color: '#e2e8f0', font: { size: 11 } } } 
        }
      }
    });

    async function refresh() {
      try {
        const [meas, stats] = await Promise.all([
          fetch('/api/measurements?limit=60').then(r => r.json()),
          fetch('/api/stats').then(r => r.json()),
        ]);

        chart.data.labels = meas.map(m => m.id);
        chart.data.datasets[0].data = meas.map(m => m.diameter_mm);
        chart.update();

        if (!stats.error) {
          const verdictClass = stats.cpk >= 1.33 ? 'verdict-capable'
                              : stats.cpk >= 1.0 ? 'verdict-marginal'
                              : 'verdict-notcapable';
          document.getElementById('stats').innerHTML = `
            <div class="card"><div class="label">Samples</div><div class="value">${stats.n}</div></div>
            <div class="card"><div class="label">Mean</div><div class="value">${stats.x_bar.toFixed(4)}</div></div>
            <div class="card"><div class="label">Std Dev</div><div class="value">${stats.s.toFixed(4)}</div></div>
            <div class="card"><div class="label">Cp</div><div class="value">${stats.cp.toFixed(2)}</div></div>
            <div class="card"><div class="label">Cpk</div><div class="value ${verdictClass}">${stats.cpk.toFixed(2)}</div></div>
          `;
        }
      } catch (err) {
        console.error("Error fetching dashboard data:", err);
      }
    }

    refresh();
    setInterval(refresh, 2000);
  </script>
</body>
</html>
"""
