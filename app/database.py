from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

IN_MEMORY_URLS = {"sqlite://", "sqlite:///:memory:"}


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    if database_url in IN_MEMORY_URLS:
        # One shared connection, so every session sees the same in-memory database.
        return create_engine(database_url, connect_args=connect_args, poolclass=StaticPool)
    if database_url.startswith("sqlite:///"):
        # SQLite creates the file but not the folder around it.
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, connect_args=connect_args)


def build_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def ensure_schema(engine) -> list[str]:
    """Create missing tables and add columns that older databases do not have.

    ``create_all`` never alters an existing table, so a database made by an
    earlier version would break on the first query that touches a new column.
    Returns the names of the columns that were added.
    """
    from . import models  # noqa: F401  (registers the tables on Base)

    Base.metadata.create_all(engine)
    added: list[str] = []
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            column_type = column.type.compile(dialect=engine.dialect)
            default = "''" if column_type.upper().startswith(("TEXT", "VARCHAR")) else "0"
            with engine.begin() as connection:
                connection.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {column_type} DEFAULT {default}'))
            added.append(f"{table.name}.{column.name}")
    return added
