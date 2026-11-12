from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent


def _load_env() -> None:
    for candidate in (Path.cwd() / ".env", PROJECT_DIR / ".env", BASE_DIR / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)


@dataclass(frozen=True)
class Settings:
    app_name: str
    internal_token: str
    core_base_url: str
    vector_backend: str
    chroma_dir: Path
    local_vector_file: Path
    embedding_provider: str
    embedding_dim: int
    embedding_base_url: str
    embedding_api_key: str
    embedding_model: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout_seconds: float
    search_provider: str
    search_site_domain: str
    tavily_api_key: str
    data_dir: Path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env()
    data_dir = BASE_DIR / "data"
    chroma_dir = Path(os.getenv("CHROMA_DIR", str(data_dir / "chroma")))
    vector_file = Path(os.getenv("LOCAL_VECTOR_FILE", str(data_dir / "vectors.json")))
    if not chroma_dir.is_absolute():
        chroma_dir = (BASE_DIR / chroma_dir).resolve()
    if not vector_file.is_absolute():
        vector_file = (BASE_DIR / vector_file).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    chroma_dir.mkdir(parents=True, exist_ok=True)
    vector_file.parent.mkdir(parents=True, exist_ok=True)
    return Settings(
        app_name="校园一卡通智能咨询 AI 服务", internal_token=os.getenv("INTERNAL_TOKEN", "local-internal-token-change-me"),
        core_base_url=os.getenv("CORE_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
        vector_backend=os.getenv("VECTOR_BACKEND", "chroma").lower(), chroma_dir=chroma_dir,
        local_vector_file=vector_file, embedding_provider=os.getenv("EMBEDDING_PROVIDER", "hashing").lower(),
        embedding_dim=int(os.getenv("EMBEDDING_DIM", "384")),
        embedding_base_url=os.getenv("EMBEDDING_BASE_URL", "").rstrip("/"),
        embedding_api_key=os.getenv("EMBEDDING_API_KEY", ""), embedding_model=os.getenv("EMBEDDING_MODEL", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", "").rstrip("/"), llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", ""), llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
        search_provider=os.getenv("SEARCH_PROVIDER", "none").lower(),
        search_site_domain=os.getenv("SEARCH_SITE_DOMAIN", "").removeprefix("https://").removeprefix("http://").strip("/"),
        tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
        data_dir=data_dir)
