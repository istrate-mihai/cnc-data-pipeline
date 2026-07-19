"""
SPC Analysis Tool – generates a console report and control chart from stored measurements.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pandas as pd
import matplotlib

matplotlib.use("Agg")  # Use non-interactive backend for server-side generation
import matplotlib.pyplot as plt
import numpy as np
import argparse
import base64
from io import BytesIO
from datetime import datetime
from config.settings import DB_PATH, SPEC_UPPER, SPEC_LOWER, TARGET, get_db_connection

# Number of most-recent readings shown on the SPC/distribution charts.
# Keeps charts legible at scale (thousands of rows) and reflects current
# process state rather than the entire lifetime history.
CHART_WINDOW = 300


def load_measurements(limit=None):
    """Load measurements using the configured database connection.

    limit=None loads the full history (used by the CLI report). Chart
    generators pass a limit so that at scale (thousands of rows) the plot
    stays legible and reflects current process state, consistent with
    /api/stats which already windows to the last 200 readings.
    """
    conn = get_db_connection()
    try:
        if limit:
            # Pull the most recent N rows, then re-sort ascending so the
            # chart still reads left-to-right in chronological order.
            df = pd.read_sql_query(
                f"SELECT id, timestamp, diameter, out_of_control FROM measurements "
                f"ORDER BY id DESC LIMIT {int(limit)}",
                conn,
            )
            df = df.sort_values("id").reset_index(drop=True)
        else:
            df = pd.read_sql_query(
                "SELECT id, timestamp, diameter, out_of_control FROM measurements ORDER BY id",
                conn,
            )
    except Exception as e:
        print(f"Error loading data: {e}")
        df = pd.DataFrame()
    conn.close()
    return df


def calculate_spc_stats(df):
    """Calculate basic SPC statistics."""
    if df.empty:
        return None
    diameters = df["diameter"]
    n = len(diameters)
    mean = diameters.mean()
    std = diameters.std(ddof=1)
    cp = (SPEC_UPPER - SPEC_LOWER) / (6 * std) if std > 0 else None
    cpu = (SPEC_UPPER - mean) / (3 * std) if std > 0 else None
    cpl = (mean - SPEC_LOWER) / (3 * std) if std > 0 else None
    cpk = min(cpu, cpl) if cpu is not None and cpl is not None else None
    ooc_count = df["out_of_control"].sum()
    ooc_pct = 100 * ooc_count / n

    return {
        "n": n,
        "mean": mean,
        "std": std,
        "cp": cp,
        "cpk": cpk,
        "ooc_count": ooc_count,
        "ooc_pct": ooc_pct,
    }


def generate_control_chart_figure(df):
    """Create a matplotlib figure of the control chart."""
    if df.empty:
        return None
    diameters = df["diameter"]
    mean = diameters.mean()
    std = diameters.std(ddof=1)
    ucl = mean + 3 * std
    lcl = mean - 3 * std

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df.index, diameters, "b-", label="Diameter", linewidth=1)
    ax.axhline(y=mean, color="g", linestyle="--", label=f"Mean = {mean:.3f}")
    ax.axhline(y=ucl, color="r", linestyle="--", label=f"UCL = {ucl:.3f}")
    ax.axhline(y=lcl, color="r", linestyle="--", label=f"LCL = {lcl:.3f}")
    ax.axhline(y=SPEC_UPPER, color="orange", linestyle=":", label=f"USL = {SPEC_UPPER}")
    ax.axhline(y=SPEC_LOWER, color="orange", linestyle=":", label=f"LSL = {SPEC_LOWER}")
    ax.axhline(y=TARGET, color="gray", linestyle="-.", label=f"Target = {TARGET}")

    ax.set_xlabel("Measurement Index")
    ax.set_ylabel("Diameter (mm)")
    ax.set_title("SPC Control Chart")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def generate_distribution_figure(df):
    """Create a histogram of diameters overlaid with the fitted normal curve
    and spec/target reference lines — shows process centering and spread
    relative to tolerance, complementary to the time-ordered control chart."""
    if df.empty:
        return None
    diameters = df["diameter"]
    mean = diameters.mean()
    std = diameters.std(ddof=1)

    fig, ax = plt.subplots(figsize=(12, 6))
    n_bins = max(10, min(40, len(diameters) // 5))
    ax.hist(
        diameters,
        bins=n_bins,
        density=True,
        color="#1f77b4",
        alpha=0.6,
        edgecolor="white",
        label="Diameter distribution",
    )

    if std > 0:
        x = np.linspace(diameters.min(), diameters.max(), 200)
        pdf = (1 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean) / std) ** 2)
        ax.plot(x, pdf, "b-", linewidth=2, label=f"Normal fit (μ={mean:.3f}, σ={std:.3f})")

    ax.axvline(x=mean, color="g", linestyle="--", label=f"Mean = {mean:.3f}")
    ax.axvline(x=SPEC_UPPER, color="orange", linestyle=":", label=f"USL = {SPEC_UPPER}")
    ax.axvline(x=SPEC_LOWER, color="orange", linestyle=":", label=f"LSL = {SPEC_LOWER}")
    ax.axvline(x=TARGET, color="gray", linestyle="-.", label=f"Target = {TARGET}")

    ax.set_xlabel("Diameter (mm)")
    ax.set_ylabel("Density")
    ax.set_title("Diameter Distribution vs. Specification")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def generate_distribution_chart_base64():
    """Generate the distribution/histogram chart and return as base64 PNG string."""
    df = load_measurements(limit=CHART_WINDOW)
    if df.empty:
        return None
    fig = generate_distribution_figure(df)
    if fig is None:
        return None
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return img_base64


def generate_spc_chart_base64():
    """Generate the control chart and return as base64 PNG string."""
    df = load_measurements(limit=CHART_WINDOW)
    if df.empty:
        return None
    fig = generate_control_chart_figure(df)
    if fig is None:
        return None
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return img_base64


def main():
    parser = argparse.ArgumentParser(description="SPC Analysis Tool")
    parser.add_argument(
        "--output", default="control_chart.png", help="Output file for control chart"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Only use the most recent N readings (matches the dashboard's "
            f"chart window, default {CHART_WINDOW}). Omit for full history."
        ),
    )
    args = parser.parse_args()

    df = load_measurements(limit=args.limit)
    if df.empty:
        print("❌ No measurements found in database.")
        return

    stats = calculate_spc_stats(df)
    if stats:
        print("\n📊 SPC Report")
        print("=" * 50)
        print(f"Number of readings: {stats['n']}")
        print(f"Mean diameter: {stats['mean']:.4f} mm")
        print(f"Standard deviation: {stats['std']:.4f} mm")
        print(f"Cp: {stats['cp']:.3f}" if stats["cp"] is not None else "Cp: —")
        print(f"Cpk: {stats['cpk']:.3f}" if stats["cpk"] is not None else "Cpk: —")
        print(f"Out-of-control count: {stats['ooc_count']} ({stats['ooc_pct']:.1f}%)")
    else:
        print("❌ Could not compute statistics.")

    fig = generate_control_chart_figure(df)
    if fig:
        fig.savefig(args.output, dpi=150)
        print(f"✅ Control chart saved as {args.output}")
        plt.show()
    else:
        print("❌ Could not generate chart.")


if __name__ == "__main__":
    main()
