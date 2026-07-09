"""
app/api.py

FastAPI dashboard for the CNC data pipeline.
Reads from SQLite, exposes /api/measurements, /api/stats and serves
the dashboard HTML directly.
"""

import asyncio
import random
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from config.settings import (
    DB_PATH,
    USL,
    LSL,
    TARGET_MM,
    NOISE_STD_MM,
    DRIFT_PER_TICK_MM,
)
from app.spc_analysis import calculate_capability

app = FastAPI(title="CNC Data Pipeline Dashboard")
_drift_state = {"value": 0.0}

# Read the HTML template once at startup (or on each request – either is fine)
TEMPLATE_DIR = Path(__file__).parent / "templates"
DASHBOARD_HTML = (TEMPLATE_DIR / "dashboard.html").read_text(encoding="utf-8")


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
    # Create database directory if it doesn't exist
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
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
    return df.iloc[::-1].reset_index(drop=True)


@app.get("/api/measurements")
def get_measurements(limit: int = 100) -> JSONResponse:
    df = _load_recent(limit)
    return JSONResponse(df.to_dict(orient="records"))


@app.get("/api/stats")
def get_stats() -> JSONResponse:
    df = _load_recent(limit=1000)
    if df.empty or len(df) < 2:
        return JSONResponse({"error": "Not enough data yet."})
    stats = calculate_capability(df, USL, LSL)
    stats["usl"] = USL
    stats["lsl"] = LSL
    return JSONResponse(stats)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard HTML page."""
    return HTMLResponse(content=DASHBOARD_HTML)
