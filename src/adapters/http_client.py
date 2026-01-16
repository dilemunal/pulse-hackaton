# DOSYA: src/adapters/http_client.py
"""
HTTP client factory for the project (Pulse demo).

Why this exists:
- Centralize proxy handling for Vodafone on-prem access (Model Gateway).
- Centralize TLS verify behavior (often disabled in internal hackathon envs).
- Provide consistent sync/async httpx clients.

AI concept note:
- "Adapter layer" = Infra abstraction so RAG/tools/workflows don't care about
  network quirks (proxy/TLS/timeouts). Keeps AI pipeline clean and repeatable.
"""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator, Optional

import httpx

from config.settings import SETTINGS


def _default_headers() -> dict[str, str]:
    # Minimal headers; do NOT add credentials here.
    return {
        "User-Agent": "Pulse-Demo/1.0",
        "Accept": "application/json,text/plain,*/*",
    }


def _verify_tls() -> bool:
    """
    TLS verification switch.

    Old code had verify=False scattered across files.
    Now it's controlled via env: HTTPX_VERIFY_TLS (demo default: false).
    """
    return SETTINGS.HTTPX_VERIFY_TLS


def build_sync_httpx_client(
    *,
    timeout_s: float = 60.0,
    verify: Optional[bool] = None,
) -> httpx.Client:
    """
    Synchronous httpx client (e.g., OpenAI sync embeddings).

    Proxy note:
    - We rely on proxy env vars (http_proxy/https_proxy/no_proxy)
      being applied centrally by SETTINGS on import.
    """
    return httpx.Client(
        timeout=httpx.Timeout(timeout_s),
        verify=_verify_tls() if verify is None else verify,
        headers=_default_headers(),
    )


def build_async_httpx_client(
    *,
    timeout_s: float = 120.0,
    verify: Optional[bool] = None,
) -> httpx.AsyncClient:

    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s),
        verify=_verify_tls() if verify is None else verify,
        headers=_default_headers(),
    )


@contextmanager
def sync_http_client(
    *,
    timeout_s: float = 60.0,
    verify: Optional[bool] = None,
) -> Iterator[httpx.Client]:
    client = build_sync_httpx_client(timeout_s=timeout_s, verify=verify)
    try:
        yield client
    finally:
        client.close()


@asynccontextmanager
async def async_http_client(
    *,
    timeout_s: float = 120.0,
    verify: Optional[bool] = None,
) -> AsyncIterator[httpx.AsyncClient]:
    client = build_async_httpx_client(timeout_s=timeout_s, verify=verify)
    try:
        yield client
    finally:
        await client.aclose()
