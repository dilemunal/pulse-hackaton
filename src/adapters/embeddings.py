"""
Embeddings adapter for Pulse (demo).

Purpose:
- Provide a single, consistent embeddings interface via Vodafone/Practicus Model Gateway.
- Hide OpenAI SDK + httpx details from the rest of the codebase.
- Keep embedding calls deterministic and easy to batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import httpx
from openai import OpenAI

from config.settings import SETTINGS
from src.adapters.http_client import build_sync_httpx_client


# =========================================================
# Core embedding client (OpenAI / Practicus)
# =========================================================

@dataclass(frozen=True)
class EmbeddingResult:
    vectors: List[List[float]]
    model: str


class EmbeddingsClient:
    """
    Sync embeddings client (OpenAI SDK).
    """

    def __init__(self) -> None:
        self._http_client: httpx.Client = build_sync_httpx_client(timeout_s=60.0)
        self._client = OpenAI(
            base_url=SETTINGS.MODEL_GATEWAY_URL,
            api_key=SETTINGS.token,
            http_client=self._http_client,
        )

    def close(self) -> None:
        self._http_client.close()

    def embed_texts(
        self,
        texts: List[str],
        *,
        model: Optional[str] = None,
    ) -> EmbeddingResult:
        emb_model = model or SETTINGS.LLM_EMBEDDING_MODEL

        cleaned = [(t or "").replace("\n", " ").strip() for t in texts]

        resp = self._client.embeddings.create(
            model=emb_model,
            input=cleaned,
            extra_body={
                "metadata": {
                    "username": SETTINGS.username,
                    "pwd": SETTINGS.pwd,
                }
            },
        )

        vectors = [d.embedding for d in resp.data]
        return EmbeddingResult(vectors=vectors, model=emb_model)


def embed_texts(texts: List[str], *, model: Optional[str] = None) -> List[List[float]]:
    """
    Convenience helper.
    """
    client = EmbeddingsClient()
    try:
        return client.embed_texts(texts, model=model).vectors
    finally:
        client.close()


# =========================================================
# Chroma compatibility layer (THIS FIXES YOUR ERROR)
# =========================================================

from chromadb import Documents, EmbeddingFunction, Embeddings  # type: ignore


class ChromaVodafoneEmbeddingFunction(EmbeddingFunction):
    """
    Chroma-compatible embedding function.
    """

    def __init__(self, *, model: Optional[str] = None) -> None:
        self._model = model

    def __call__(self, input: Documents) -> Embeddings:
        client = EmbeddingsClient()
        try:
            return client.embed_texts(list(input), model=self._model).vectors
        finally:
            client.close()

    def name(self) -> str:
        return "pulse_practicus_gateway_embeddings"


# Backward compatibility (scripts eski ismi kullanıyorsa)
VodafoneEmbeddingFunction = ChromaVodafoneEmbeddingFunction
