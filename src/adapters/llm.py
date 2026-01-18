
"""
LLM adapter for Pulse (demo).

Purpose:
- Provide a single, consistent way to callPracticus Model Gateway.
- Enforce prompt hygiene (system vs user), structured outputs (JSON), and basic guardrails.

AI concept notes:
- "System prompt" = global behavioral contract (tone, constraints, safety).
- "Structured output" = force JSON so downstream logic is deterministic .
- "Gateway" = single endpoint; model selection is done via the `model` parameter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from config.settings import SETTINGS
from src.adapters.http_client import build_async_httpx_client



def system_message(content: str) -> ChatCompletionMessageParam:
    return {"role": "system", "content": content}


def user_message(content: str) -> ChatCompletionMessageParam:
    return {"role": "user", "content": content}


def developer_message(content: str) -> ChatCompletionMessageParam:

    return {"role": "developer", "content": content}



# Client factory

def _gateway_metadata() -> Dict[str, Any]:
    return {"metadata": {"username": SETTINGS.username, "pwd": SETTINGS.pwd}}


@dataclass(frozen=True)
class LlmResult:
    """
    Standard return type for structured JSON calls.
    """
    raw_text: str
    json: Dict[str, Any]
    usage: Optional[Dict[str, Any]] = None


class LlmClient:


    def __init__(self) -> None:
        self._http_client = build_async_httpx_client(timeout_s=120.0)
        self._client = AsyncOpenAI(
            base_url=SETTINGS.MODEL_GATEWAY_URL,
            api_key=SETTINGS.token,
            http_client=self._http_client,
        )

    async def aclose(self) -> None:
        await self._http_client.aclose()

    async def chat_json(
        self,
        *,
        messages: List[ChatCompletionMessageParam],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> LlmResult:
        """
        Call chat completion with JSON object output.

        - Uses response_format={"type":"json_object"} to force JSON.
        - Returns parsed JSON dict.
        - If model is None, uses SETTINGS.LLM_CHAT_MODEL.
        """
        chat_model = model or SETTINGS.LLM_CHAT_MODEL
        extra_body = _gateway_metadata()
        if extra:
          
            extra_body.update(extra)

        resp: ChatCompletion = await self._client.chat.completions.create(
            model=chat_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            extra_body=extra_body,
        )

        content = resp.choices[0].message.content or "{}"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
         
            parsed = {"_parse_error": True, "raw": content}

        usage = None
   
        if getattr(resp, "usage", None):
            usage = {
                "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
                "completion_tokens": getattr(resp.usage, "completion_tokens", None),
                "total_tokens": getattr(resp.usage, "total_tokens", None),
            }

        return LlmResult(raw_text=content, json=parsed, usage=usage)

    async def chat_text(
        self,
        *,
        messages: List[ChatCompletionMessageParam],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
    
        chat_model = model or SETTINGS.LLM_CHAT_MODEL
        extra_body = _gateway_metadata()
        if extra:
            extra_body.update(extra)

        resp: ChatCompletion = await self._client.chat.completions.create(
            model=chat_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
        )
        return resp.choices[0].message.content or ""
