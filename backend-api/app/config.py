from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent


def _load_env_files() -> None:
    for candidate in (Path.cwd() / ".env", PROJECT_DIR / ".env", BASE_DIR / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)


def _default_sqlite_url() -> str:
    db_path = (BASE_DIR / "data" / "campus_card.db").resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    api_prefix: str
    database_url: str
    jwt_secret: str
    jwt_expires_seconds: int
    internal_token: str
    ai_base_url: str
    public_base_url: str
    admin_web_url: str
    cors_origins: tuple[str, ...]
    upload_dir: Path
    export_dir: Path
    data_dir: Path
    auto_seed: bool
    initial_admin_username: str
    initial_admin_password: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env_files()
    backend_root = BASE_DIR
    upload_dir = backend_root / "uploads"
    export_dir = backend_root / "exports"
    data_dir = backend_root / "data"
    for directory in (upload_dir, export_dir, data_dir):
        directory.mkdir(parents=True, exist_ok=True)
    origins = tuple(
        item.strip()
        for item in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174").split(",")
        if item.strip()
    )
    return Settings(
        app_name="校园一卡通智能咨询工具 API",
        app_env=os.getenv("APP_ENV", "development"),
        api_prefix="/api/v1",
        database_url=os.getenv("DATABASE_URL", _default_sqlite_url()),
        jwt_secret=os.getenv("JWT_SECRET", "dev-only-secret"),
        jwt_expires_seconds=int(os.getenv("JWT_EXPIRES_SECONDS", "86400")),
        internal_token=os.getenv("INTERNAL_TOKEN", "local-internal-token-change-me"),
        ai_base_url=os.getenv("AI_BASE_URL", "http://127.0.0.1:8001").rstrip("/"),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
        admin_web_url=os.getenv("ADMIN_WEB_URL", "http://127.0.0.1:5173").rstrip("/"),
        cors_origins=origins,
        upload_dir=upload_dir,
        export_dir=export_dir,
        data_dir=data_dir,
        auto_seed=os.getenv("AUTO_SEED", "true").lower() in {"1", "true", "yes"},
        initial_admin_username=os.getenv("INITIAL_ADMIN_USERNAME", "admin"),
        initial_admin_password=os.getenv("INITIAL_ADMIN_PASSWORD", "Admin12345"),
    )
