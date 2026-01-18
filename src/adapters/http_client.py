
"""

- Centralize proxy handling for Vodafone on-prem access (Model Gateway).
- Centralize TLS verify behavior.
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
    return {
        "User-Agent": "Pulse-Demo/1.0",
        "Accept": "application/json,text/plain,*/*",
    }


def _verify_tls() -> bool:

    return SETTINGS.HTTPX_VERIFY_TLS


def build_sync_httpx_client(
    *,
    timeout_s: float = 60.0,
    verify: Optional[bool] = None,
) -> httpx.Client:
    """
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
