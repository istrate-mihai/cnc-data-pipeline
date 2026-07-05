"""
spc_analysis.py

Reads logged measurements from SQLite (written by data_logger.py),
calculates process capability (Cp, Cpk) per the formulas derived in
the theory session:

    Cp  = (USL - LSL) / 6s
    Cpk = min[(USL - x_bar) / 3s, (x_bar - LSL) / 3s]

...and renders an X-bar control chart with UCL/LCL at x_bar +/- 3s,
matching the 68-95-99.7 empirical rule.

Requires: pandas, matplotlib
"""

import argparse
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

DB_PATH = Path(__file__).parent / "cnc_measurements.db"
OUTPUT_CHART = Path(__file__).parent / "control_chart.png"

# Specification limits, mm -- matches the worked example from theory session
USL = 10.10
LSL = 9.90


def load_measurements(db_path: Path) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT id, timestamp, diameter_mm, out_of_control FROM measurements ORDER BY id",
        conn,
    )
    conn.close()
    if df.empty:
        raise ValueError(
            f"No measurements found in {db_path}. Run data_logger.py first."
        )
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def calculate_capability(df: pd.DataFrame, usl: float, lsl: float) -> dict:
    x_bar = df["diameter_mm"].mean()
    s = df["diameter_mm"].std(ddof=1)  # ddof=1 -> divide by n-1, sample std

    cp = (usl - lsl) / (6 * s)
    cpk_upper = (usl - x_bar) / (3 * s)
    cpk_lower = (x_bar - lsl) / (3 * s)
    cpk = min(cpk_upper, cpk_lower)

    return {
        "n": len(df),
        "x_bar": x_bar,
        "s": s,
        "cp": cp,
        "cpk": cpk,
        "cpk_upper": cpk_upper,
        "cpk_lower": cpk_lower,
        "ucl": x_bar + 3 * s,
        "lcl": x_bar - 3 * s,
    }


def print_report(stats: dict) -> None:
    print("=" * 50)
    print("SPC / Process Capability Report")
    print("=" * 50)
    print(f"Sample size (n):       {stats['n']}")
    print(f"Mean (x_bar):          {stats['x_bar']:.4f} mm")
    print(f"Std dev (s, n-1):      {stats['s']:.4f} mm")
    print(f"UCL (x_bar + 3s):      {stats['ucl']:.4f} mm")
    print(f"LCL (x_bar - 3s):      {stats['lcl']:.4f} mm")
    print(f"Spec limits:           LSL={LSL} / USL={USL} mm")
    print("-" * 50)
    print(f"Cp:                    {stats['cp']:.3f}")
    print(f"Cpk:                   {stats['cpk']:.3f}")
    print(f"  (upper side: {stats['cpk_upper']:.3f}, lower side: {stats['cpk_lower']:.3f})")
    print("-" * 50)

    if stats["cpk"] >= 1.33:
        verdict = "CAPABLE (meets typical automotive Cpk >= 1.33 threshold)"
    elif stats["cpk"] >= 1.0:
        verdict = "MARGINAL (Cpk between 1.0-1.33, process needs attention)"
    else:
        verdict = "NOT CAPABLE (Cpk < 1.0, process will produce non-conforming parts)"
    print(f"Verdict: {verdict}")
    print("=" * 50)


def plot_control_chart(df: pd.DataFrame, stats: dict, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 6))

    ax.plot(df["id"], df["diameter_mm"], marker="o", markersize=3,
            linewidth=1, color="#2563eb", label="Diameter (mm)")

    ax.axhline(stats["x_bar"], color="#16a34a", linestyle="-", linewidth=1.5, label="x̄ (mean)")
    ax.axhline(stats["ucl"], color="#dc2626", linestyle="--", linewidth=1.2, label="UCL (x̄+3s)")
    ax.axhline(stats["lcl"], color="#dc2626", linestyle="--", linewidth=1.2, label="LCL (x̄-3s)")
    ax.axhline(USL, color="#7c3aed", linestyle=":", linewidth=1.2, label=f"USL ({USL})")
    ax.axhline(LSL, color="#7c3aed", linestyle=":", linewidth=1.2, label=f"LSL ({LSL})")

    # highlight points outside control limits (special-cause candidates)
    out_of_control = df[
        (df["diameter_mm"] > stats["ucl"]) | (df["diameter_mm"] < stats["lcl"])
    ]
    if not out_of_control.empty:
        ax.scatter(out_of_control["id"], out_of_control["diameter_mm"],
                   color="red", s=60, zorder=5, label="Out of control")

    ax.set_xlabel("Sample #")
    ax.set_ylabel("Diameter (mm)")
    ax.set_title(f"X-bar Control Chart — Cp={stats['cp']:.2f}, Cpk={stats['cpk']:.2f}")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    print(f"\nChart saved to: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SPC analysis on logged CNC measurements.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_CHART)
    parser.add_argument("--usl", type=float, default=USL)
    parser.add_argument("--lsl", type=float, default=LSL)
    args = parser.parse_args()

    df = load_measurements(args.db)
    stats = calculate_capability(df, args.usl, args.lsl)
    print_report(stats)
    plot_control_chart(df, stats, args.output)


if __name__ == "__main__":
    main()
