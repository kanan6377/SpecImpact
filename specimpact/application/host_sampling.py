from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.types import SamplingMessage, TextContent
from pydantic import BaseModel, ValidationError

from specimpact.graphrag import redact_payload

DEFAULT_MAX_TOKENS = 1024


class HostSamplingAdapter:
    """Small adapter around an MCP host's ``sampling/createMessage`` request."""

    def __init__(
        self,
        context: Any,
        host: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")

        self.context = context
        self.host = host or "unknown"
        self.provider = f"host:{self.host}"
        self.model = "unknown"
        self.max_tokens = max_tokens

    async def structured(
        self,
        purpose: str,
        payload: dict[str, Any],
        schema: type[BaseModel],
    ) -> BaseModel:
        """Request and validate one JSON response from the connected host."""
        system_prompt = _system_prompt(schema)
        safe_payload = redact_payload(payload)
        message = SamplingMessage(
            role="user",
            content=TextContent(
                type="text",
                text=json.dumps(
                    {"purpose": purpose, "payload": safe_payload},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        )

        try:
            result = await self._session().create_message(
                [message],
                system_prompt=system_prompt,
                max_tokens=self.max_tokens,
            )
        except asyncio.CancelledError as error:
            raise ValueError("Host sampling was cancelled") from error
        except Exception as error:
            raise ValueError("Host sampling failed") from error

        model = getattr(result, "model", None)
        self.model = model.strip() if isinstance(model, str) and model.strip() else "unknown"

        content = getattr(result, "content", None)
        if not isinstance(content, TextContent):
            raise ValueError("Host sampling returned non-text content")

        try:
            return schema.model_validate_json(content.text)
        except (ValidationError, ValueError, TypeError) as error:
            raise ValueError(f"Host sampling response did not match {schema.__name__}") from error

    def _session(self) -> Any:
        session = getattr(self.context, "session", None)
        if session is not None:
            return session
        if hasattr(self.context, "create_message"):
            return self.context
        raise ValueError("MCP sampling session is unavailable")


def _system_prompt(schema: type[BaseModel]) -> str:
    schema_json = json.dumps(
        schema.model_json_schema(),
        ensure_ascii=False,
        sort_keys=True,
    )
    return (
        "Return exactly one valid JSON value. Do not use Markdown fences or add commentary. "
        "The JSON must validate against this JSON Schema:\n"
        f"{schema_json}"
    )
