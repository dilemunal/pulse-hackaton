"""
Chroma vector store adapter for Pulse (demo).

Purpose:
- Centralize all vector DB interactions (RAG retrieval layer).
- Keep Chroma usage simple, explicit, and debuggable.
- Allow metadata filtering & future hybrid retrieval.

AI concept note:
- "Vector store" = memory of knowledge chunks.
- We will store PRODUCT CATALOG here (stable knowledge source).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import chromadb
from chromadb.api.models.Collection import Collection

from config.settings import SETTINGS


class VectorStore:
    """
    Thin wrapper around Chroma HttpClient.

    Design choice (important):
    - We DO NOT bind an embedding_function here.
    - We compute embeddings explicitly (via EmbeddingsClient) and pass them in.
      This makes behavior deterministic and avoids Chroma embedding-function conflicts.
    """

    def __init__(self) -> None:
        self._client = chromadb.HttpClient(
            host=SETTINGS.VECTOR_DB_HOST,
            port=int(SETTINGS.VECTOR_DB_PORT),
        )

    # ----------------------------
    # Collections
    # ----------------------------
    def get_or_create_collection(
        self,
        name: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Collection:
        return self._client.get_or_create_collection(
            name=name,
            metadata=metadata or {"source": "pulse-demo"},
        )

    def get_collection(self, name: str) -> Collection:
        return self._client.get_collection(name=name)

    def delete_collection(self, name: str) -> None:
        self._client.delete_collection(name=name)

    # ----------------------------
    # Upsert
    # ----------------------------
    def upsert_documents(
        self,
        collection: Collection,
        *,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Insert or update documents with precomputed embeddings.

        Required alignment:
        - len(ids) == len(documents) == len(embeddings)
        - (optional) len(metadatas) == len(ids)
        """
        if not (len(ids) == len(documents) == len(embeddings)):
            raise ValueError("ids, documents and embeddings length mismatch")
        if metadatas is not None and len(metadatas) != len(ids):
            raise ValueError("metadatas length mismatch with ids")

        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    # ----------------------------
    # Query
    # ----------------------------
    def query(
        self,
        collection: Collection,
        *,
        query_embedding: List[float],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Vector similarity search with optional metadata filter.

        where example:
          {"category": "Tariff"}
          {"segment": "Red", "channel": "Online"}

        include default:
          ["documents", "metadatas", "distances"]
        """
        if include is None:
            include = ["documents", "metadatas", "distances"]

        return collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=include,
        )
