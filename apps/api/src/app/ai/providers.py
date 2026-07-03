"""AI provider seam (docs/02 §6, docs/03 §8).

Two capabilities, each behind a small interface with a deterministic local
implementation (dev/test/CI need no API keys) and a metered remote one:

- embeddings: Voyage (Anthropic's recommended partner) | local hash
- completions: Anthropic Claude | local (raises — callers must offer a
  heuristic path when no LLM is configured; M1 classification does)

Every remote call records a usage event — COGS is measured from the first
AI feature, not reconstructed later.
"""

import hashlib
import math
import re
import uuid
from typing import Protocol

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.modules.documents.elements import EMBEDDING_DIM, UsageEvent


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars/token) — used for chunk sizing and
    local usage accounting; remote providers report exact counts."""
    return max(1, len(text) // 4)


def record_usage(
    session: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None,
    kind: str,
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int = 0,
    ref: str | None = None,
) -> None:
    session.add(
        UsageEvent(
            org_id=org_id,
            project_id=project_id,
            kind=kind,
            provider=provider,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            ref=ref,
        )
    )


class EmbeddingProvider(Protocol):
    name: str
    model: str

    def embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        """input_type is 'document' or 'query' (asymmetric embedding models)."""
        ...


class LocalHashEmbeddings:
    """Deterministic bag-of-hashed-words embedding.

    Not semantically meaningful — it gives stable lexical-overlap similarity
    so retrieval code paths (KNN, fusion, thresholds) are exercised end to
    end in tests. Never enabled outside dev/test by config validation.
    """

    name = "local"
    model = "hash-bow-v1"

    def embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * EMBEDDING_DIM
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                digest = hashlib.md5(token.encode()).digest()
                idx = int.from_bytes(digest[:4], "little") % EMBEDDING_DIM
                sign = 1.0 if digest[4] % 2 else -1.0
                vec[idx] += sign
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class VoyageEmbeddings:
    name = "voyage"

    def __init__(self, api_key: str, model: str = "voyage-3"):
        self._api_key = api_key
        self.model = model

    def embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        response = httpx.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self.model,
                "input": texts,
                "input_type": input_type,
                "output_dimension": EMBEDDING_DIM,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str: ...


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self.model = model

    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01"},
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"]


class NoLLMConfigured(RuntimeError):
    pass


def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider == "voyage":
        if not settings.voyage_api_key:
            raise RuntimeError("embedding_provider=voyage requires ATC_VOYAGE_API_KEY")
        return VoyageEmbeddings(settings.voyage_api_key, settings.embedding_model)
    return LocalHashEmbeddings()


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.anthropic_api_key:
        return AnthropicLLM(settings.anthropic_api_key, settings.llm_model)
    raise NoLLMConfigured(
        "No LLM configured (set ATC_ANTHROPIC_API_KEY); caller should fall back"
    )
