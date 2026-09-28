"""Database construction and request-local SQLAlchemy sessions."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/tractor_usage"


@dataclass(frozen=True)
class Settings:
    database_url: str
    model_dir: Path

    @classmethod
    def from_environment(cls) -> "Settings":
        repository_root = Path(__file__).resolve().parents[3]
        return cls(
            database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            model_dir=Path(
                os.environ.get(
                    "FROZEN_MODEL_DIR",
                    repository_root / "models" / "fendt314-hybrid-v2.0.1",
                )
            ),
        )


def create_database_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
