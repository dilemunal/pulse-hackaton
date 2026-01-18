"""
Build Product Catalog Vector Index for Pulse (demo).

What it does:
- Reads stable product catalog from Postgres
- Creates a Chroma collection (vodafone_products / pulse_products)
- Upserts documents with rich metadata for filtering (category/segment/channel/etc.)

AI concept note:
- This is the "Product Catalog Knowledge Source" index.
- Retrieval should use metadata filters for eligibility/segment/channel constraints.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

import chromadb
from dotenv import load_dotenv

from src.db.connection import db_cursor
from src.adapters.embeddings import VodafoneEmbeddingFunction


def _safe_load_env() -> None:

    load_dotenv(dotenv_path=os.getenv("DOTENV_PATH", ".env"))


def _build_index_text(name: str, category: str, price: float, specs: Dict[str, Any]) -> str:
    """
    Build the text that will be embedded.
    Keep it deterministic and information-dense.
    """

    spec_parts = []
    for k, v in (specs or {}).items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                spec_parts.append(f"{k}.{kk}: {vv}")
        elif isinstance(v, list):
            spec_parts.append(f"{k}: {', '.join(map(str, v))}")
        else:
            spec_parts.append(f"{k}: {v}")

    specs_str = " | ".join(spec_parts) if spec_parts else "specs: -"
    return f"product_name: {name}\ncategory: {category}\nprice_try: {price}\n{specs_str}"


def _to_metadata(product_code: str, name: str, category: str, price: float, specs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Metadata should be filterable + small.
    Put large blobs into the document text, not metadata.
    """
    md: Dict[str, Any] = {
        "product_code": product_code,
        "category": category,
        "price_try": float(price),
        "is_active": True,
    }

   
    if specs:
        for key in ["segment", "subscription_type", "channel", "validity", "contract_months", "type", "brand", "storage"]:
            if key in specs and specs[key] is not None:
                md[key] = specs[key]

        # eligibility hints (flatten)
        eligible = specs.get("eligible")
        if isinstance(eligible, dict):
            for ek, ev in eligible.items():
                md[f"elig_{ek}"] = ev

        # source tag (useful for debugging)
        if "source" in specs:
            md["source"] = specs["source"]

    return md


def fetch_products() -> List[Tuple[str, str, str, float, Dict[str, Any]]]:
    """
    Return list of:
      (product_code, name, category, price, specs_dict)
    """
    with db_cursor() as (_conn, cur):
        cur.execute(
            """
            SELECT product_code, name, category, price, specifications
            FROM products
            WHERE is_active = TRUE
            ORDER BY id ASC;
            """
        )
        rows = cur.fetchall()

    results: List[Tuple[str, str, str, float, Dict[str, Any]]] = []
    for product_code, name, category, price, specs in rows:
        if isinstance(specs, str):
            try:
                specs_dict = json.loads(specs)
            except Exception:
                specs_dict = {}
        else:
            specs_dict = specs or {}
        results.append((product_code, name, category, float(price), specs_dict))
    return results


def build_product_catalog_index(
    *,
    collection_name: str = "pulse_products",
    wipe: bool = True,
    batch_size: int = 64,
) -> None:
    _safe_load_env()

    host = os.getenv("VECTOR_DB_HOST", "localhost")
    port = int(os.getenv("VECTOR_DB_PORT", "8001"))

    chroma = chromadb.HttpClient(host=host, port=port)
    if wipe:
        # best effort delete
        try:
            chroma.delete_collection(name=collection_name)
        except Exception:
            pass

    collection = chroma.get_or_create_collection(
        name=collection_name,
        embedding_function=VodafoneEmbeddingFunction(),
        metadata={"source": "product_catalog"},
    )

    products = fetch_products()
    if not products:
        raise RuntimeError("No products found in Postgres. Run: python3 scripts/products_seed.py")

    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict[str, Any]] = []

    def flush():
        if not ids:
            return
        collection.upsert(ids=ids, documents=docs, metadatas=metas)
        ids.clear()
        docs.clear()
        metas.clear()

    for (product_code, name, category, price, specs) in products:
        doc = _build_index_text(name=name, category=category, price=price, specs=specs)
        md = _to_metadata(product_code=product_code, name=name, category=category, price=price, specs=specs)

        ids.append(product_code)  # stable id: product_code
        docs.append(doc)
        metas.append(md)

        if len(ids) >= batch_size:
            flush()

    flush()

    try:
        c = collection.count()
        print(f"✅ Chroma index built. collection={collection_name} size={c}")
    except Exception:
        print(f"✅ Chroma index built. collection={collection_name}")


if __name__ == "__main__":
    build_product_catalog_index()
