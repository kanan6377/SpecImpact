from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from mcp.types import ImageContent, SamplingMessage, TextContent
from pydantic import BaseModel

from specimpact.application.host_sampling import HostSamplingAdapter


class Result(BaseModel):
    answer: str


class FakeSession:
    def __init__(self, result: Any = None, error: BaseException | None = None) -> None:
        self.result = result
        self.error = error
        self.messages: list[SamplingMessage] | None = None
        self.system_prompt: str | None = None
        self.max_tokens: int | None = None

    async def create_message(
        self,
        messages: list[SamplingMessage],
        *,
        system_prompt: str | None = None,
        max_tokens: int,
    ) -> Any:
        self.messages = messages
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        if self.error is not None:
            raise self.error
        return self.result


class FakeContext:
    def __init__(self, session: FakeSession) -> None:
        self.session = session


def test_structured_uses_json_prompt_sampling_message_and_validates_text() -> None:
    session = FakeSession(
        SimpleNamespace(
            model="host-model",
            content=TextContent(type="text", text='{"answer":"ok"}'),
        )
    )
    adapter = HostSamplingAdapter(FakeContext(session), host="cursor", max_tokens=321)

    result = asyncio.run(
        adapter.structured("impact-analysis", {"chunk": "one"}, Result)
    )

    assert result == Result(answer="ok")
    assert adapter.provider == "host:cursor"
    assert adapter.model == "host-model"
    assert session.max_tokens == 321
    assert session.system_prompt is not None
    assert "valid JSON" in session.system_prompt
    assert '"properties"' in session.system_prompt
    assert session.messages is not None
    assert len(session.messages) == 1
    assert isinstance(session.messages[0], SamplingMessage)
    assert isinstance(session.messages[0].content, TextContent)
    assert '"purpose": "impact-analysis"' in session.messages[0].content.text
    assert '"chunk": "one"' in session.messages[0].content.text


def test_structured_uses_unknown_model_when_host_does_not_return_one() -> None:
    session = FakeSession(
        SimpleNamespace(content=TextContent(type="text", text='{"answer":"ok"}'))
    )
    adapter = HostSamplingAdapter(FakeContext(session), host="antigravity")

    asyncio.run(adapter.structured("test", {}, Result))

    assert adapter.model == "unknown"


def test_structured_redacts_sensitive_payload_before_sampling() -> None:
    session = FakeSession(
        SimpleNamespace(content=TextContent(type="text", text='{"answer":"ok"}'))
    )
    adapter = HostSamplingAdapter(FakeContext(session), host="cursor")

    asyncio.run(
        adapter.structured(
            "test",
            {"email": "person@example.com", "note": "call 090-1234-5678"},
            Result,
        )
    )

    assert session.messages is not None
    sent = session.messages[0].content
    assert isinstance(sent, TextContent)
    assert "person@example.com" not in sent.text
    assert "090-1234-5678" not in sent.text
    assert "[REDACTED]" in sent.text


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (
            SimpleNamespace(
                model="m",
                content=TextContent(type="text", text='{"answer": 3}'),
            ),
            "did not match Result",
        ),
        (
            SimpleNamespace(
                model="m",
                content=ImageContent(type="image", data="aW1hZ2U=", mimeType="image/png"),
            ),
            "non-text content",
        ),
    ],
)
def test_structured_rejects_invalid_or_non_text_host_response(
    result: Any,
    message: str,
) -> None:
    session = FakeSession(result)
    adapter = HostSamplingAdapter(FakeContext(session), host="cursor")

    with pytest.raises(ValueError, match=message):
        asyncio.run(adapter.structured("test", {"secret": "do-not-echo"}, Result))


def test_structured_wraps_cancellation_and_does_not_store_response_body() -> None:
    body = "private response body"
    session = FakeSession(error=asyncio.CancelledError(body))
    adapter = HostSamplingAdapter(FakeContext(session), host="cursor")

    with pytest.raises(ValueError, match="cancelled") as raised:
        asyncio.run(adapter.structured("test", {"secret": body}, Result))

    assert body not in str(raised.value)
    assert body not in repr(raised.value)


def test_structured_wraps_host_exception_without_exception_body() -> None:
    body = "private provider error"
    session = FakeSession(error=RuntimeError(body))
    adapter = HostSamplingAdapter(FakeContext(session), host="cursor")

    with pytest.raises(ValueError, match="failed") as raised:
        asyncio.run(adapter.structured("test", {"secret": body}, Result))

    assert body not in str(raised.value)
    assert body not in repr(raised.value)
