"""PostgreSQL connection setup (SQLAlchemy 2.x + psycopg2).

Connection settings are read from environment variables (loaded from
backend/.env if present). See backend/.env.example.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv(Path(__file__).resolve().parent / ".env")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "invoice_processing")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")


def build_url(database: str = DB_NAME) -> URL:
    # URL.create escapes special characters in the password (e.g. "@").
    return URL.create(
        drivername="postgresql+psycopg2",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=database,
    )


engine = create_engine(build_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_database_if_missing() -> bool:
    """Create DB_NAME on the server if it does not exist. Returns True if created."""
    admin_engine = create_engine(build_url("postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": DB_NAME}
            ).scalar()
            if exists:
                return False
            conn.execute(text(f'CREATE DATABASE "{DB_NAME}"'))
            return True
    finally:
        admin_engine.dispose()


def check_connection() -> str:
    with engine.connect() as conn:
        return conn.execute(text("SELECT version()")).scalar_one()
