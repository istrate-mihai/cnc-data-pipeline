"""
FMEA RPN Calculator – reads recent measurements and computes Risk Priority Number.
Supports both SQLite and PostgreSQL.
"""

import sys
import statistics
from config.settings import (
    SPEC_LOWER,
    SPEC_UPPER,
    TARGET,
    get_db_connection,
    get_db_placeholder,
)


def get_recent_measurements(limit=100):
    """Fetch the most recent measurements from the database."""
    conn = get_db_connection()
    cur = conn.cursor()
    placeholder = get_db_placeholder()
    try:
        cur.execute(
            f"SELECT diameter, out_of_control FROM measurements ORDER BY timestamp DESC LIMIT {placeholder}",
            (limit,),
        )
        rows = cur.fetchall()
    except Exception as e:
        # Table may not exist
        rows = []
    finally:
        conn.close()
    return rows


def calculate_rpn(measurements):
    """
    Compute RPN and its components.
    Returns (rpn, severity, occurrence, detection) or (None, None, None, None) if no data.
    """
    if not measurements:
        return None, None, None, None

    diameters = [m[0] for m in measurements]
    out_of_control_flags = [m[1] for m in measurements]
    tolerance = (SPEC_UPPER - SPEC_LOWER) / 2

    # Severity: scaled by maximum deviation from target (0‑10)
    max_dev = max(abs(d - TARGET) for d in diameters) if diameters else 0
    if tolerance == 0:
        severity = 10 if max_dev > 0 else 1
    elif max_dev >= tolerance:
        severity = 10
    else:
        severity = 1 + 9 * (max_dev / tolerance)

    # Occurrence: percentage of out-of-control flags (0‑1) scaled to 1‑10
    occ_ratio = sum(out_of_control_flags) / len(out_of_control_flags)
    occurrence = 1 + 9 * occ_ratio

    # Detection: inverse of process capability Cp (1‑10)
    if len(diameters) >= 2:
        std_dev = statistics.stdev(diameters)
        cp = (SPEC_UPPER - SPEC_LOWER) / (6 * std_dev) if std_dev > 0 else 0
        if cp >= 1.67:
            detection = 1
        elif cp <= 1.0:
            detection = 10
        else:
            detection = 10 - 9 * ((cp - 1.0) / 0.67)
    else:
        detection = 5

    rpn = severity * occurrence * detection
    return rpn, severity, occurrence, detection


def main():
    measurements = get_recent_measurements(100)
    rpn, sev, occ, det = calculate_rpn(measurements)
    if rpn is None:
        print(
            "No measurements available. Please seed the database first (python -m data_ingestion.seed_demo_data) or run the data logger."
        )
        sys.exit(1)
    print(
        f"RPN = {rpn:.2f} (Severity={sev:.2f}, Occurrence={occ:.2f}, Detection={det:.2f})"
    )


if __name__ == "__main__":
    main()
