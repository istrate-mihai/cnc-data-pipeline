from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
import jinja2
import threading
import time
import random

from config.settings import DB_PATH, SPEC_LOWER, SPEC_UPPER, TARGET
from app.fmea_rpn import get_recent_measurements, calculate_rpn
from data_ingestion.data_logger import log_measurement

app = FastAPI(title="CNC SPC Dashboard")

# ---- Custom Jinja2 environment (no caching) ----
templates_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader("app/templates"),
    auto_reload=True,
    cache_size=0,  # Disable caching to avoid key errors
)


def background_simulator():
    print("🔁 Background simulator started")
    while True:
        try:
            diameter = TARGET + random.uniform(-0.15, 0.15)
            out_of_control = 1 if random.random() < 0.05 else 0
            log_measurement(diameter, out_of_control)
        except Exception as e:
            print(f"❌ Simulator error: {e}")
        time.sleep(1)


if not hasattr(app, "_simulator_started"):
    thread = threading.Thread(target=background_simulator, daemon=True)
    thread.start()
    app._simulator_started = True


# ---- Helper DB functions (unchanged) ----
def get_db_connection():
    from config.settings import get_db_connection as db_conn

    return db_conn()


def get_db_placeholder():
    from config.settings import get_db_placeholder as db_pl

    return db_pl()


# ---- Endpoints ----
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    template = templates_env.get_template("dashboard.html")
    content = template.render(request=request)
    return HTMLResponse(content=content)


@app.get("/api/measurements")
async def get_measurements(limit: int = 100):
    conn = get_db_connection()
    cur = conn.cursor()
    placeholder = get_db_placeholder()
    cur.execute(
        f"SELECT timestamp, diameter, out_of_control FROM measurements ORDER BY timestamp DESC LIMIT {placeholder}",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return [{"timestamp": r[0], "diameter": r[1], "out_of_control": r[2]} for r in rows]


@app.get("/api/stats")
async def get_stats():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT diameter FROM measurements ORDER BY timestamp DESC LIMIT 200")
    rows = cur.fetchall()
    conn.close()
    if len(rows) < 2:
        return {"cp": None, "cpk": None, "message": "Insufficient data"}
    diameters = [r[0] for r in rows]
    mean = sum(diameters) / len(diameters)
    std_dev = (sum((x - mean) ** 2 for x in diameters) / (len(diameters) - 1)) ** 0.5
    if std_dev == 0:
        return {"cp": None, "cpk": None, "message": "Zero standard deviation"}
    cp = (SPEC_UPPER - SPEC_LOWER) / (6 * std_dev)
    cpu = (SPEC_UPPER - mean) / (3 * std_dev)
    cpl = (mean - SPEC_LOWER) / (3 * std_dev)
    cpk = min(cpu, cpl)
    return {"cp": round(cp, 3), "cpk": round(cpk, 3), "n": len(diameters)}


@app.get("/api/fmea")
async def fmea():
    measurements = get_recent_measurements(100)
    rpn, sev, occ, det = calculate_rpn(measurements)
    if rpn is None:
        raise HTTPException(status_code=404, detail="No measurements available")
    return {
        "rpn": round(rpn, 2),
        "severity": round(sev, 2),
        "occurrence": round(occ, 2),
        "detection": round(det, 2),
    }
