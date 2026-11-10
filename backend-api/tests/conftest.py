from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BASE = Path(__file__).resolve().parents[1]
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(BASE / 'data' / 'pytest_campus.db').as_posix()}")
os.environ.setdefault("AUTO_SEED", "true")
os.environ.setdefault("AI_BASE_URL", "http://127.0.0.1:65534")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("INTERNAL_TOKEN", "test-internal")
(BASE / "data").mkdir(exist_ok=True)
(BASE / "data" / "pytest_campus.db").unlink(missing_ok=True)

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, account: str, password: str, client_type: str | None = None) -> str:
    payload = {"account": account, "password": password}
    if client_type:
        payload["client_type"] = client_type
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]["token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
