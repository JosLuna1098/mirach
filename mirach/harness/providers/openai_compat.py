"""OpenAI-compatible provider: Ollama, llama.cpp, LM Studio, vLLM, OpenRouter, OpenAI."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from mirach.harness.providers.base import Message, Response, ToolCall, ToolDef


class OpenAICompatProvider:
    """
    Talks to any OpenAI /v1/chat/completions-compatible endpoint.

    num_ctx is forwarded inside options.num_ctx — critical for Ollama, which
    defaults to 4096 and silently truncates context, breaking tool calling for
    any model larger than a few billion parameters. Non-Ollama servers ignore
    unknown fields, so it is always safe to include.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str,
        api_key: str = "ollama",
        num_ctx: int = 32768,
        timeout: float = 120.0,
        temperature: float = 0.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._num_ctx = num_ctx
        self._timeout = timeout
        self._temperature = temperature

    def send(
        self,
        messages: list[Message],
        tools: list[ToolDef],
        ctx: dict[str, Any] | None = None,
    ) -> Response:
        payload = self._build_payload(messages, tools, ctx or {})
        data = self._post(payload)
        return self._parse(data)

    # ── private ──────────────────────────────────────────────────────────────

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[ToolDef],
        ctx: dict[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [_msg_to_wire(m) for m in messages],
            "temperature": self._temperature,
            "options": {"num_ctx": self._num_ctx},
        }
        if tools:
            payload["tools"] = [_tooldef_to_wire(t) for t in tools]
            payload["tool_choice"] = "auto"
        # ctx carries provider-specific overrides (e.g. format schema for prompted mode)
        payload.update(ctx)
        return payload

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}/v1/chat/completions"
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

    def _parse(self, data: dict[str, Any]) -> Response:
        choice = data["choices"][0]
        msg = choice["message"]
        content: str = msg.get("content") or ""

        raw_calls: list[dict[str, Any]] = msg.get("tool_calls") or []
        tool_calls = [
            ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=(
                    json.loads(tc["function"]["arguments"])
                    if isinstance(tc["function"]["arguments"], str)
                    else tc["function"]["arguments"]
                ),
            )
            for tc in raw_calls
        ]

        stop_reason = "tool_use" if tool_calls else "stop"
        return Response(content=content, stop_reason=stop_reason, tool_calls=tool_calls)


# ── wire-format helpers ───────────────────────────────────────────────────────


def _msg_to_wire(m: Message) -> dict[str, Any]:
    if m.role == "tool":
        return {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
    d: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in m.tool_calls
        ]
    return d


def _tooldef_to_wire(t: ToolDef) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        },
    }
