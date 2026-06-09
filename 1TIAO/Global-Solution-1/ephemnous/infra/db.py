"""Acesso ao Postgres via connection pool (sem ORM)."""

from psycopg_pool import ConnectionPool

from ephemnous.config import settings

_pool: ConnectionPool | None = None


def open_pool() -> None:
    """Abre a pool (idempotente)."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.database_url, min_size=1, max_size=10, open=True)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def _require_pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("pool não inicializado, chame open_pool() primeiro")
    return _pool


def connection():
    return _require_pool().connection()


def ping() -> bool:
    with _require_pool().connection() as conn:
        row = conn.execute("SELECT 1").fetchone()
        return row is not None and row[0] == 1


def list_tables() -> list[str]:
    with _require_pool().connection() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        ).fetchall()
        return [r[0] for r in rows]
