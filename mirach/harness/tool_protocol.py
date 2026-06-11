"""Tool-calling strategy: native | prompted | auto.

Both strategies feed the same inner loop via a single interface.

- native  — tools go in the API request; provider returns structured tool_calls.
- prompted — tool descriptions are injected into a system message; the model
             output is constrained to a JSON schema (Ollama format param) and
             parsed back into ToolCall objects. Works with any instruction-following
             model. Hardened with few-shot examples and a parse-repair retry.
- auto    — native when tools are present (the common case for OpenAI-compat
             endpoints); prompted when the caller explicitly requests it or native
             parsing fails at the response level.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from mirach.harness.providers.base import Message, Response, ToolCall, ToolDef

if TYPE_CHECKING:
    from mirach.harness.providers.base import Provider

# Maximum parse-repair retries in prompted mode before giving up.
_MAX_REPAIR = 2

# JSON Schema that Ollama's `format` parameter will enforce.
# Discriminated by `action`; both branches are in a single flat object so
# weak models don't have to navigate nested oneOf.
_FORMAT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["action"],
    "properties": {
        "action": {"type": "string", "enum": ["tool_call", "final_answer"]},
        "tool": {"type": "string"},
        "arguments": {"type": "object"},
        "answer": {"type": "string"},
    },
}

_SYSTEM_HEADER = textwrap.dedent("""\
    You are a helpful assistant with access to tools.
    You MUST respond with valid JSON matching exactly one of these two forms:

    To call a tool:
      {{"action": "tool_call", "tool": "<tool_name>", "arguments": {{<args>}}}}

    To give a final answer:
      {{"action": "final_answer", "answer": "<your response>"}}

    Do not include any text outside the JSON object.

    Available tools:
    {tool_block}

    Examples:
    User: list files in /tmp
    Assistant: {{"action": "tool_call", "tool": "bash", "arguments": {{"command": "ls /tmp"}}}}

    User: what is 2+2?
    Assistant: {{"action": "final_answer", "answer": "4"}}
""")


class PromptedParseError(ValueError):
    def __init__(self, reason: str, *, raw: str) -> None:
        super().__init__(reason)
        self.raw = raw


@dataclass
class PreparedTurn:
    messages: list[Message]
    tools: list[ToolDef]
    ctx: dict[str, Any] = field(default_factory=dict)


class ToolProtocol:
    """
    Wraps the provider call to give any model access to harness tools.

    Usage:
        protocol = ToolProtocol(mode="auto")
        response = protocol.send_with_repair(provider, messages, tools)
    """

    def __init__(self, mode: Literal["auto", "native", "prompted"] = "auto") -> None:
        self._mode = mode

    # ── public interface ──────────────────────────────────────────────────────

    def prepare(self, messages: list[Message], tools: list[ToolDef]) -> PreparedTurn:
        """Transform messages+tools before handing them to the provider.

        native  → pass through unchanged.
        prompted → inject tool descriptions into system message, clear tools list,
                   add Ollama format schema to ctx.
        """
        if self._effective_mode(tools) == "native":
            return PreparedTurn(messages=messages, tools=tools)
        return self._prepare_prompted(messages, tools)

    def extract_response(self, response: Response, tools: list[ToolDef]) -> Response:
        """Normalize the provider's response.

        native  → pass through.
        prompted → parse the JSON content into ToolCall objects.
        Raises PromptedParseError on invalid JSON or unexpected action.
        """
        if self._effective_mode(tools) == "native":
            return response
        return _parse_prompted(response)

    def send_with_repair(
        self,
        provider: Provider,
        messages: list[Message],
        tools: list[ToolDef],
    ) -> Response:
        """Call the provider, parse the response, retry with error context on parse failure."""
        prepared = self.prepare(messages, tools)
        for attempt in range(_MAX_REPAIR + 1):
            raw = provider.send(prepared.messages, prepared.tools, prepared.ctx)
            try:
                return self.extract_response(raw, tools)
            except PromptedParseError as exc:
                if attempt >= _MAX_REPAIR:
                    raise
                prepared = _add_repair_context(prepared, exc)
        raise RuntimeError("unreachable")  # pragma: no cover

    # ── private ───────────────────────────────────────────────────────────────

    def _effective_mode(self, tools: list[ToolDef]) -> Literal["native", "prompted"]:
        if self._mode == "prompted":
            return "prompted"
        if self._mode == "native":
            return "native"
        # auto: use native when there are tools (standard OpenAI-compat behaviour);
        # fall back to prompted when no tools (plain completion, format not needed)
        return "native"

    def _prepare_prompted(self, messages: list[Message], tools: list[ToolDef]) -> PreparedTurn:
        tool_block = _render_tools(tools)
        system_content = _SYSTEM_HEADER.format(tool_block=tool_block).strip()

        if messages and messages[0].role == "system":
            merged = Message(
                role="system",
                content=system_content + "\n\n" + messages[0].content,
            )
            augmented = [merged, *messages[1:]]
        else:
            augmented = [Message(role="system", content=system_content), *messages]

        ctx = {"format": _FORMAT_SCHEMA} if tools else {}
        return PreparedTurn(messages=augmented, tools=[], ctx=ctx)


# ── module-level helpers ──────────────────────────────────────────────────────


def _render_tools(tools: list[ToolDef]) -> str:
    lines: list[str] = []
    for t in tools:
        lines.append(f"- {t.name}: {t.description}")
        if t.parameters:
            lines.append(f"  Parameters (JSON schema): {json.dumps(t.parameters)}")
    return "\n".join(lines)


def _parse_prompted(response: Response) -> Response:
    text = (response.content or "").strip()
    # Strip markdown code fences if the model wrapped the JSON
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PromptedParseError(f"JSON decode failed: {exc}", raw=text) from exc

    action = data.get("action")

    if action == "final_answer":
        answer = data.get("answer", "")
        if not isinstance(answer, str):
            answer = str(answer)
        return Response(content=answer, stop_reason="stop")

    if action == "tool_call":
        tool_name = data.get("tool", "")
        arguments = data.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise PromptedParseError(
                f"'arguments' must be an object, got {type(arguments).__name__}",
                raw=text,
            )
        call_id = f"prompted_{tool_name}_{abs(hash(text)) % 10**8}"
        tc = ToolCall(id=call_id, name=tool_name, arguments=arguments)
        return Response(content="", stop_reason="tool_use", tool_calls=[tc])

    raise PromptedParseError(
        f"Unknown action: {action!r}. Expected 'tool_call' or 'final_answer'.",
        raw=text,
    )


def _add_repair_context(prepared: PreparedTurn, exc: PromptedParseError) -> PreparedTurn:
    """Append the failed assistant output + a repair instruction to the message history."""
    repair_user = Message(
        role="user",
        content=(
            f"Your previous response was not valid JSON:\n\n"
            f"Error: {exc}\n\n"
            f"Raw output:\n{exc.raw}\n\n"
            "Please respond again with a valid JSON object using ONLY the allowed schema."
        ),
    )
    # Also include the bad assistant response so the model has context
    bad_assistant = Message(role="assistant", content=exc.raw)
    return PreparedTurn(
        messages=[*prepared.messages, bad_assistant, repair_user],
        tools=prepared.tools,
        ctx=prepared.ctx,
    )
