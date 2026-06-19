"""
Persistence layer — PostgreSQL (Ir Além 1).

Uses SQLAlchemy + psycopg2. Credentials come from `.env` (or environment
variables) and match the project's docker-compose.yml.

Main functions:
    test_connection()      -> (ok: bool, message: str)
    init_db()              -> creates tables/seed from src/schema.sql
    insert_reading(...)    -> stores reading + predictions, returns id_reading
    load_history()         -> DataFrame with JOIN (history_view)
    load_devices()         -> devices DataFrame
    register_device()      -> inserts a device (idempotent)

Quick test:
    python src/database.py
"""
from __future__ import annotations

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import ROOT, SCHEMA_PATH, postgres_url

load_dotenv(ROOT / ".env")

_engine: Engine | None = None


def get_engine() -> Engine:
    """Singleton engine with pool_pre_ping (reconnects if the connection drops)."""
    global _engine
    if _engine is None:
        _engine = create_engine(postgres_url(), pool_pre_ping=True, future=True)
    return _engine


def test_connection() -> tuple[bool, str]:
    """Check whether PostgreSQL is reachable. Never raises."""
    try:
        with get_engine().connect() as con:
            con.execute(text("SELECT 1"))
        return True, "Conexão com PostgreSQL OK."
    except Exception as exc:  # noqa: BLE001 — we want the message for the UI
        return False, f"{type(exc).__name__}: {exc}"


def init_db() -> None:
    """Run src/schema.sql (idempotent: creates tables/indexes/seed/view).

    Uses the raw psycopg2 connection because the script has several statements
    in a single text — which the driver executes natively, without
    SQLAlchemy's parameter handling.
    """
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    raw = get_engine().raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(sql)
        raw.commit()
    finally:
        raw.close()


def insert_reading(
    *,
    id_device: int,
    temperature: float,
    ph: float,
    soil_humidity: float,
    n: int, p: int, k: int,
    pump: int,
    yield_ton_ha: float,
    irrigation_volume_l_m2: float,
    fertilizer_kg_ha: float,
    recommendation_irrigation: str = "",
    recommendation_fertilization: str = "",
    recommendation_yield: str = "",
) -> int:
    """Insert a full reading and return the generated id_reading."""
    sql = text("""
        INSERT INTO sensor_readings (
            id_device, temperature, ph, soil_humidity,
            n, p, k, pump,
            yield_ton_ha, irrigation_volume_l_m2, fertilizer_kg_ha,
            recommendation_irrigation, recommendation_fertilization, recommendation_yield
        ) VALUES (
            :id_device, :temperature, :ph, :soil_humidity,
            :n, :p, :k, :pump,
            :yield_ton_ha, :irrigation_volume_l_m2, :fertilizer_kg_ha,
            :recommendation_irrigation, :recommendation_fertilization, :recommendation_yield
        )
        RETURNING id_reading
    """)
    with get_engine().begin() as con:
        new_id = con.execute(sql, {
            "id_device": id_device,
            "temperature": temperature, "ph": ph, "soil_humidity": soil_humidity,
            "n": n, "p": p, "k": k, "pump": pump,
            "yield_ton_ha": yield_ton_ha,
            "irrigation_volume_l_m2": irrigation_volume_l_m2,
            "fertilizer_kg_ha": fertilizer_kg_ha,
            "recommendation_irrigation": recommendation_irrigation,
            "recommendation_fertilization": recommendation_fertilization,
            "recommendation_yield": recommendation_yield,
        }).scalar_one()
    return int(new_id)


def load_history(limit: int = 100) -> pd.DataFrame:
    """Most recent history (sensors + sector JOIN) via the history_view."""
    sql = text("SELECT * FROM history_view LIMIT :lim")
    with get_engine().connect() as con:
        return pd.read_sql_query(sql, con, params={"lim": limit})


def load_devices() -> pd.DataFrame:
    sql = text("SELECT * FROM devices ORDER BY id_device")
    with get_engine().connect() as con:
        return pd.read_sql_query(sql, con)


def register_device(id_device: int, sector: str,
                    sensor_model: str, install_date: str) -> None:
    sql = text("""
        INSERT INTO devices (id_device, plantation_sector, sensor_model, install_date)
        VALUES (:id, :sector, :model, :date)
        ON CONFLICT (id_device) DO NOTHING
    """)
    with get_engine().begin() as con:
        con.execute(sql, {"id": id_device, "sector": sector,
                          "model": sensor_model, "date": install_date})


# ── Quick end-to-end test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    ok, msg = test_connection()
    print(msg)
    if not ok:
        print("Start the database with:  docker compose up -d")
        raise SystemExit(1)

    init_db()
    print("[OK] Schema applied.")

    new_id = insert_reading(
        id_device=101,
        temperature=32.0, ph=5.8, soil_humidity=30.0,
        n=0, p=1, k=0, pump=1,
        yield_ton_ha=1.85,
        irrigation_volume_l_m2=7.2,
        fertilizer_kg_ha=98.4,
        recommendation_irrigation="Solo seco — irrigar 7.2 L/m² com urgência.",
        recommendation_fertilization="Déficit de N e K — aplicar 98.4 kg/ha.",
        recommendation_yield="Produtividade estimada: 1.85 ton/ha.",
    )
    print(f"[OK] Reading inserted (id_reading = {new_id}).")

    df = load_history(limit=5)
    print("\n[TEST] Latest readings:")
    print(df[["id_reading", "plantation_sector", "reading_ts",
              "soil_humidity", "yield_ton_ha",
              "irrigation_volume_l_m2", "fertilizer_kg_ha"]].to_string(index=False))
