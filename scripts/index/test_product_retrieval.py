"""

- Connects to Chroma collection
- Runs a few queries
- Shows top-k results with metadata
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import chromadb
from dotenv import load_dotenv

from src.adapters.embeddings import VodafoneEmbeddingFunction


def _safe_load_env() -> None:
    # Always specify path to avoid python-dotenv stdin edge-case
    env_path = os.getenv("DOTENV_PATH", ".env")
    load_dotenv(dotenv_path=env_path, override=False)


def _print_hit(i: int, doc: str, md: Dict[str, Any], dist: Optional[float] = None) -> None:
    title = md.get("product_code", "NA")
    first_line = (doc.splitlines()[0] if doc else "").strip()
    name_line = first_line.replace("product_name:", "").strip() if first_line.startswith("product_name:") else ""

    cat = md.get("category")
    price = md.get("price_try")
    seg = md.get("segment")
    ch = md.get("channel")

    print(f"{i+1}) {title} | {name_line} | cat={cat} price={price} seg={seg} channel={ch}")
    if dist is not None:
        print(f"   distance={dist}")


def test_retrieval(
    *,
    collection_name: str = "pulse_products",
    queries: List[str] | None = None,
    k: int = 5,
) -> None:
    _safe_load_env()

    host = os.getenv("VECTOR_DB_HOST", "localhost")
    port = int(os.getenv("VECTOR_DB_PORT", "8001"))

    chroma = chromadb.HttpClient(host=host, port=port)

    try:
        collection = chroma.get_collection(
            name=collection_name,
            embedding_function=VodafoneEmbeddingFunction(),
        )
    except Exception as e:
        raise SystemExit(
            f"❌ Collection '{collection_name}' not found or cannot be opened.\n"
            f"   Hint: run index build first:\n"
            f"   PYTHONPATH=. python3 scripts/index/build_product_catalog_index.py\n"
            f"   Error: {e}"
        )

    queries = queries or [
        "roaming paketi yurt dışı internet",
        "Gamer Pass sınırsız oyun",
        "Evde fiber 1000 mbps",
        "Online'a özel Red 40GB",
        "Güvenli internet",
        "iPhone 15 Pro Max 256GB",
    ]

    for q in queries:
        print("\n" + "=" * 90)
        print("QUERY:", q)

        res = collection.query(
            query_texts=[q],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )

        docs = (res.get("documents") or [[]])[0]
        mds = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        if not docs:
            print("No results.")
            continue

        for i, (doc, md, dist) in enumerate(zip(docs, mds, dists)):
            _print_hit(i, doc, md, dist)


if __name__ == "__main__":
    test_retrieval()
