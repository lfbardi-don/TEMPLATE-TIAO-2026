"""Aplica db/schema.sql no Postgres. Idempotente (CREATE TABLE IF NOT EXISTS)."""

import os
from pathlib import Path

import psycopg

# espelha o default de ephemnous/config.py
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://ephemnous:ephemnous@localhost:5432/ephemnous"
)
SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def main() -> None:
    sql = SCHEMA.read_text(encoding="utf-8")
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(sql)
        conn.commit()
    print(f"OK: schema aplicado de {SCHEMA}")


if __name__ == "__main__":
    main()
