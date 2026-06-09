"""Persistência: funções diretas de escrita/leitura no Postgres (sem ORM)."""

from __future__ import annotations

from psycopg.types.json import Jsonb

from ephemnous.core.models import Decision, Forecast, NodeState, Telemetry
from ephemnous.infra import db


def get_or_create_node(name: str, kind: str, params: dict) -> int:
    with db.connection() as conn:
        row = conn.execute("SELECT id FROM nodes WHERE name = %s", (name,)).fetchone()
        if row:
            return row[0]
        row = conn.execute(
            "INSERT INTO nodes (name, kind, params) VALUES (%s, %s, %s) RETURNING id",
            (name, kind, Jsonb(params)),
        ).fetchone()
        conn.commit()
        return row[0]


def save_telemetry(node_id: int, tel: Telemetry) -> int:
    with db.connection() as conn:
        row = conn.execute(
            """INSERT INTO telemetry
                 (node_id, ts_device, irradiance_frac, force_eclipse, temp_k, load_frac, state)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (node_id, tel.ts_device, tel.irradiance_frac, tel.force_eclipse,
             tel.temp_k, tel.load_frac, tel.state),
        ).fetchone()
        conn.commit()
        return row[0]


def save_node_state(node_id: int, s: NodeState) -> int:
    with db.connection() as conn:
        row = conn.execute(
            """INSERT INTO node_state
                 (node_id, soc_frac, temp_k, thermal_margin_k, power_avail_w, in_eclipse, orbit_phase)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (node_id, s.soc_frac, s.temp_k, s.thermal_margin_k, s.power_avail_w,
             s.in_eclipse, s.orbit_phase),
        ).fetchone()
        conn.commit()
        return row[0]


def save_forecast(node_id: int, f: Forecast) -> int:
    with db.connection() as conn:
        row = conn.execute(
            """INSERT INTO forecasts
                 (node_id, horizon_s, pred_power_w, pred_thermal_margin_k, model_version)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (node_id, f.horizon_s, Jsonb(f.pred_power_w), Jsonb(f.pred_thermal_margin_k),
             f.model_version),
        ).fetchone()
        conn.commit()
        return row[0]


def save_decision(node_id: int, d: Decision, forecast_id: int | None) -> int:
    with db.connection() as conn:
        row = conn.execute(
            """INSERT INTO decisions
                 (node_id, forecast_id, action, target_pwm, lookahead, reason, mode)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (node_id, forecast_id, d.action, d.target_pwm, d.lookahead, d.reason, d.mode),
        ).fetchone()
        conn.commit()
        return row[0]
