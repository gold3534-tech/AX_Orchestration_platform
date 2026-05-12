from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Protocol


DEFAULT_EMBEDDING_PROVIDER = "openai"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSION = 1536


class KnowledgeEmbeddingError(ValueError):
    pass


class EmbeddingProvider(Protocol):
    provider: str
    model: str
    dimension: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


@dataclass(frozen=True)
class DeterministicEmbeddingProvider:
    dimension: int = DEFAULT_EMBEDDING_DIMENSION
    provider: str = "deterministic"
    model: str = "test-hash"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_hash_embedding(text, self.dimension) for text in texts]


@dataclass(frozen=True)
class OpenAIEmbeddingProvider:
    api_key: str | None = None
    model: str = DEFAULT_EMBEDDING_MODEL
    dimension: int = DEFAULT_EMBEDDING_DIMENSION
    provider: str = DEFAULT_EMBEDDING_PROVIDER

    def __post_init__(self) -> None:
        if self.dimension != DEFAULT_EMBEDDING_DIMENSION:
            raise KnowledgeEmbeddingError("Only 1536-dimensional embeddings are supported for Knowledge.")

        api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise KnowledgeEmbeddingError("Embedding provider is not configured")
        object.__setattr__(self, "api_key", api_key)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        from openai import OpenAI

        clean_texts = [text.strip() for text in texts]
        if not clean_texts:
            return []

        client = OpenAI(api_key=self.api_key)
        response = client.embeddings.create(model=self.model, input=clean_texts)
        embeddings = [list(item.embedding) for item in response.data]
        if any(len(embedding) != self.dimension for embedding in embeddings):
            raise KnowledgeEmbeddingError("Embedding provider returned an unexpected vector dimension.")
        return embeddings


def get_default_embedding_provider() -> EmbeddingProvider:
    if os.environ.get("AX_KNOWLEDGE_ALLOW_DEMO_EMBEDDINGS") == "1":
        return DeterministicEmbeddingProvider()
    return OpenAIEmbeddingProvider()


def _hash_embedding(text: str, dimension: int) -> list[float]:
    if dimension <= 0:
        return []

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    while len(values) < dimension:
        values.extend(round(byte / 255, 6) for byte in digest)
        digest = hashlib.sha256(digest).digest()
    return values[:dimension]
