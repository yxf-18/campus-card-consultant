from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from .config import get_settings

settings = get_settings()


class AIServiceError(RuntimeError):
    pass


class AIClient:
    def __init__(self) -> None:
        self.base_url = settings.ai_base_url
        self.headers = {"X-Internal-Token": settings.internal_token}

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        timeout = kwargs.pop("timeout", 35.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, f"{self.base_url}{path}", headers=self.headers, **kwargs)
        if response.status_code >= 400:
            raise AIServiceError(f"AI service returned {response.status_code}: {response.text[:300]}")
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise AIServiceError("AI service returned invalid JSON") from exc

    async def index_document(self, document_id: int, version_no: int, title: str, category: str,
                             file_path: Path, file_name: str, content_type: str) -> dict[str, Any]:
        with file_path.open("rb") as handle:
            return await self._request(
                "POST", "/internal/v1/index",
                data={"document_id": str(document_id), "version_no": str(version_no),
                      "title": title, "category": category},
                files={"file": (file_name, handle, content_type or "application/octet-stream")},
                timeout=90.0,
            )

    async def unindex(self, document_id: int) -> dict[str, Any]:
        return await self._request("POST", "/internal/v1/unindex", json={"document_id": document_id})

    async def retrieve(self, question: str, allowed_versions: dict[int, int], top_k: int,
                       threshold: float, document_id: int | None = None) -> list[dict[str, Any]]:
        payload = {
            "question": question,
            "allowed_versions": [{"document_id": key, "version_no": value} for key, value in allowed_versions.items()],
            "top_k": top_k, "threshold": threshold, "document_id": document_id,
        }
        data = await self._request("POST", "/internal/v1/retrieve", json=payload)
        return list(data.get("contexts", []))

    async def summarize(self, messages: list[dict[str, str]], previous_summary: str | None = None) -> str:
        data = await self._request(
            "POST", "/internal/v1/summarize",
            json={"messages": messages, "previous_summary": previous_summary or ""}, timeout=25.0,
        )
        return str(data.get("summary", "")).strip()

    async def stream_chat(self, payload: dict[str, Any]) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(40.0, connect=5.0)) as client:
            async with client.stream("POST", f"{self.base_url}/internal/v1/chat/stream",
                                     headers=self.headers, json=payload) as response:
                if response.status_code >= 400:
                    text = (await response.aread()).decode("utf-8", errors="ignore")
                    raise AIServiceError(f"AI stream returned {response.status_code}: {text[:300]}")
                event_name = "message"
                data_lines: list[str] = []
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip("\ufeff")
                    if not line:
                        if data_lines:
                            raw_data = "\n".join(data_lines)
                            try:
                                parsed = json.loads(raw_data)
                            except json.JSONDecodeError:
                                parsed = {"content": raw_data}
                            yield event_name, parsed
                        event_name, data_lines = "message", []
                    elif line.startswith("event:"):
                        event_name = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                if data_lines:
                    raw_data = "\n".join(data_lines)
                    try:
                        parsed = json.loads(raw_data)
                    except json.JSONDecodeError:
                        parsed = {"content": raw_data}
                    yield event_name, parsed


ai_client = AIClient()
