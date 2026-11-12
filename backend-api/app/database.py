from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401
    from . import conversation_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # Older development databases still have columns for the removed login-lock
    # behavior. Drop only those two obsolete columns so fresh inserts remain valid.
    inspector = inspect(engine)
    if "sys_user" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("sys_user")}
        with engine.begin() as connection:
            for column in ("locked_until", "failed_login_count"):
                if column in columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE sys_user DROP COLUMN {column}"
                    )
