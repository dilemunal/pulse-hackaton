# DOSYA: src/tools/product_search.py
"""
Product Search Tool (Pulse demo)

What it does:
- Takes a natural language query (e.g., "roaming paketi yurt dışı internet")
- Embeds the query using Vodafone/Practicus gateway embedding model
- Runs vector search against Chroma collection (pulse_products)
- Optionally applies metadata filters (where)
- Returns top-k product candidates with metadata + short extracted name

AI concept note:
- This is the retrieval tool in RAG.
- LLM should output a search_query + optional filters; this tool returns grounded products.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.adapters.embeddings import EmbeddingsClient
from src.adapters.vector_store import VectorStore


@dataclass(frozen=True)
class ProductCandidate:
    product_code: str
    name: str
    category: Optional[str]
    price_try: Optional[float]
    metadata: Dict[str, Any]
    distance: Optional[float]


def _extract_name_from_doc(doc: str) -> str:
    """
    Our index doc format starts with:
      product_name: <NAME>
    If not found, fallback to first line or empty.
    """
    if not doc:
        return ""
    first_line = (doc.splitlines()[0] if doc else "").strip()
    if first_line.lower().startswith("product_name:"):
        return first_line.split(":", 1)[1].strip()
    return first_line[:120].strip()


def product_search(
    query: str,
    *,
    collection_name: str = "pulse_products",
    k: int = 5,
    where: Optional[Dict[str, Any]] = None,
) -> List[ProductCandidate]:
    """
    Search product catalog by semantic similarity.

    Args:
        query: Natural language query
        collection_name: Chroma collection name
        k: number of results
        where: Chroma metadata filter dict. Examples:
            {"category": "Roaming"}
            {"segment": "Red", "channel": "Online"}
            {"elig_requires_no_overdue_bill": True}

    Returns:
        List[ProductCandidate] sorted by best match (lowest distance).
    """
    q = (query or "").strip()
    if not q:
        return []

    # 1) Embed query (explicit)
    emb_client = EmbeddingsClient()
    try:
        q_vec = emb_client.embed_texts([q]).vectors[0]
    finally:
        emb_client.close()

    # 2) Query Chroma
    vs = VectorStore()
    collection = vs.get_or_create_collection(collection_name)

    res = vs.query(
        collection,
        query_embedding=q_vec,
        n_results=k,
        where=where,
    )

    docs = (res.get("documents") or [[]])[0]
    mds = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    out: List[ProductCandidate] = []
    for i in range(len(docs)):
        doc = docs[i] if i < len(docs) else ""
        md = mds[i] if i < len(mds) else {}
        dist = dists[i] if i < len(dists) else None

        product_code = str(md.get("product_code") or "")
        name = _extract_name_from_doc(doc)

        category = md.get("category")
        price_try = md.get("price_try")
        try:
            price_try = float(price_try) if price_try is not None else None
        except Exception:
            price_try = None

        out.append(
            ProductCandidate(
                product_code=product_code,
                name=name,
                category=category,
                price_try=price_try,
                metadata=md,
                distance=float(dist) if dist is not None else None,
            )
        )

    return out


# manual CLI test
if __name__ == "__main__":
    qs = [
        "roaming paketi yurt dışı internet",
        "Gamer Pass sınırsız oyun",
        "Evde fiber 1000 mbps",
        "Online'a özel Red 40GB",
        "Güvenli internet",
        "iPhone 15 Pro Max 256GB",
    ]

    for q in qs:
        print("\n" + "=" * 80)
        print("QUERY:", q)
        hits = product_search(q, k=5)
        for i, h in enumerate(hits, start=1):
            seg = h.metadata.get("segment")
            ch = h.metadata.get("channel")
            print(
                f"{i}) {h.product_code} | {h.name} | cat={h.category} price={h.price_try} "
                f"seg={seg} channel={ch} dist={h.distance}"
            )
