from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    # --- Model Gateway ---
    MODEL_GATEWAY_URL: str
    token: str
    username: str
    pwd: str
    LLM_CHAT_MODEL: str
    LLM_EMBEDDING_MODEL: str

    # --- Proxy (optional, but important for on-prem) ---
    PROXY_IP: str | None
    PROXY_PORT: str | None
    PROXY_USER: str | None
    PROXY_PASS: str | None

    # --- DB ---
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASS: str
    DB_NAME: str

    # --- Vector DB ---
    VECTOR_DB_HOST: str
    VECTOR_DB_PORT: int

    # --- App knobs ---
    TREND_TTL_HOURS: int
    HTTPX_VERIFY_TLS: bool  # True=verify cert, False=verify disabled (demo)

    @staticmethod
    def load() -> "Settings":
        s = Settings(
            MODEL_GATEWAY_URL=os.getenv("MODEL_GATEWAY_URL", ""),
            token=os.getenv("token", ""),
            username=os.getenv("username", ""),
            pwd=os.getenv("pwd", ""),
            LLM_CHAT_MODEL=os.getenv("LLM_CHAT_MODEL", "practicus/gpt-oss-20b-hackathon"),
            LLM_EMBEDDING_MODEL=os.getenv("LLM_EMBEDDING_MODEL", "practicus/gemma-300m-hackathon"),
            PROXY_IP=os.getenv("PROXY_IP"),
            PROXY_PORT=os.getenv("PROXY_PORT"),
            PROXY_USER=os.getenv("PROXY_USER"),
            PROXY_PASS=os.getenv("PROXY_PASS"),
            DB_HOST=os.getenv("DB_HOST", "localhost"),
            DB_PORT=int(os.getenv("DB_PORT", "5435")),
            DB_USER=os.getenv("DB_USER", "vodafone_user"),
            DB_PASS=os.getenv("DB_PASS", "vodafone_password"),
            DB_NAME=os.getenv("DB_NAME", "vodafone_master"),
            VECTOR_DB_HOST=os.getenv("VECTOR_DB_HOST", "localhost"),
            VECTOR_DB_PORT=int(os.getenv("VECTOR_DB_PORT", "8001")),
            TREND_TTL_HOURS=int(os.getenv("TREND_TTL_HOURS", "6")),
            HTTPX_VERIFY_TLS=_get_bool("HTTPX_VERIFY_TLS", default=False),  # demo default: False
        )

        missing = [k for k in ["MODEL_GATEWAY_URL", "token", "username", "pwd"] if not getattr(s, k)]
        if missing:
            raise ValueError(f"Missing required env vars: {', '.join(missing)}")

        s._apply_proxy_if_needed()
        return s

    def _apply_proxy_if_needed(self) -> None:
        if not (self.PROXY_IP and self.PROXY_PORT and self.PROXY_USER and self.PROXY_PASS):
            return

        proxy_url = f"http://{self.PROXY_USER}:{self.PROXY_PASS}@{self.PROXY_IP}:{self.PROXY_PORT}/"
        os.environ["http_proxy"] = proxy_url
        os.environ["HTTP_PROXY"] = proxy_url
        os.environ["https_proxy"] = proxy_url
        os.environ["HTTPS_PROXY"] = proxy_url

        base_no_proxy = ".vodafone.local,localhost,127.0.0.1"
        prev = os.getenv("NO_PROXY") or os.getenv("no_proxy") or ""
        merged = f"{prev},{base_no_proxy}".strip(",") if prev else base_no_proxy
        os.environ["no_proxy"] = merged
        os.environ["NO_PROXY"] = merged


# singleton
SETTINGS = Settings.load()
