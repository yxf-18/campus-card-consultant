from __future__ import annotations

import hashlib
import math
import re
from typing import Sequence

import httpx

from .config import get_settings

settings = get_settings()


def _tokens(text: str) -> list[str]:
    lowered = text.lower()
    latin = re.findall(r"[a-z0-9]+", lowered)
    chinese = re.findall(r"[\u4e00-\u9fff]", lowered)
    bigrams = ["".join(chinese[index:index + 2]) for index in range(max(0, len(chinese) - 1))]
    return latin + chinese + bigrams


def hash_embedding(text: str, dim: int | None = None) -> list[float]:
    dim = dim or settings.embedding_dim
    vector = [0.0] * dim
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


class EmbeddingProvider:
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if settings.embedding_provider == "openai_compatible" and settings.embedding_base_url and settings.embedding_model:
            headers = {"Content-Type": "application/json"}
            if settings.embedding_api_key:
                headers["Authorization"] = f"Bearer {settings.embedding_api_key}"
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{settings.embedding_base_url}/embeddings", headers=headers,
                    json={"model": settings.embedding_model, "input": list(texts)})
            response.raise_for_status()
            return [item["embedding"] for item in response.json().get("data", [])]
        return [hash_embedding(text) for text in texts]

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]


embedding_provider = EmbeddingProvider()
