"""Leitura read-only do Postgres para o dashboard."""

from __future__ import annotations

import os

import pandas as pd
import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://ephemnous:ephemnous@localhost:5432/ephemnous"
)


def connect():
    return psycopg.connect(DATABASE_URL)


def list_nodes(conn) -> list[tuple]:
    return conn.execute("SELECT id, name, kind FROM nodes ORDER BY name").fetchall()


def node_state_df(conn, node_id: int, limit: int = 150) -> pd.DataFrame:
    rows = conn.execute(
        """SELECT ts_server, power_avail_w, temp_k, soc_frac, thermal_margin_k, in_eclipse, orbit_phase
           FROM node_state WHERE node_id = %s ORDER BY ts_server DESC LIMIT %s""",
        (node_id, limit),
    ).fetchall()
    df = pd.DataFrame(rows, columns=["ts", "power_w", "temp_k", "soc", "margin_k", "eclipse", "phase"])
    if not df.empty:
        df["temp_c"] = df["temp_k"] - 273.15
    return df.iloc[::-1].reset_index(drop=True)


def decisions_df(conn, node_id: int, limit: int = 15) -> pd.DataFrame:
    rows = conn.execute(
        """SELECT ts_server, action, target_pwm, mode, reason
           FROM decisions WHERE node_id = %s ORDER BY id DESC LIMIT %s""",
        (node_id, limit),
    ).fetchall()
    return pd.DataFrame(rows, columns=["ts", "ação", "pwm", "modo", "motivo"])


def latest_forecast(conn, node_id: int) -> dict | None:
    row = conn.execute(
        """SELECT ts_server, pred_power_w, pred_thermal_margin_k, model_version
           FROM forecasts WHERE node_id = %s ORDER BY id DESC LIMIT 1""",
        (node_id,),
    ).fetchone()
    if row is None:
        return None
    return {"ts": row[0], "pred_power_w": row[1], "pred_margin_k": row[2], "model": row[3]}


def latest_telemetry(conn, node_id: int) -> dict | None:
    row = conn.execute(
        """SELECT irradiance_frac, force_eclipse, load_frac, state
           FROM telemetry WHERE node_id = %s ORDER BY id DESC LIMIT 1""",
        (node_id,),
    ).fetchone()
    if row is None:
        return None
    return {"irradiance_frac": row[0], "force_eclipse": row[1], "load_frac": row[2], "state": row[3]}
