"""PolicyEngine — enforces policy.yaml rules before every tool execute.

check(tool_name, args) is the single entry point used by the AgentLoop.
It dispatches to the appropriate sub-check based on tool name and returns a
Decision that the loop acts on:

  ALLOW  → execute immediately
  DENY   → reject, return an error result to the model
  CONFIRM → emit AwaitingConfirmationEvent and block until the user responds
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from mirach.harness.policy.schema import Policy, load_policy

try:
    import yaml as _yaml  # PyYAML — optional at import time

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    CONFIRM = "confirm"


# Tools whose check is handled by their category.
# Tools not listed here default to ALLOW (safe read-only helpers, memory, etc.)
_SHELL_TOOLS = {"bash"}
_READ_TOOLS = {"read_file", "search"}
_WRITE_TOOLS = {"write_file", "edit_file"}
_SEARCH_TOOLS = {"web_search"}
_FETCH_TOOLS = {"web_fetch"}


class PolicyEngine:
    """
    Stateless policy enforcer.  Constructed once at daemon start, re-used for
    every tool call.  Thread-safe (read-only after construction).
    """

    def __init__(self, policy: Policy | None = None) -> None:
        self._policy = policy or Policy()

    # ── factory methods ───────────────────────────────────────────────────────

    @classmethod
    def from_file(cls, path: Path) -> PolicyEngine:
        if not _HAS_YAML:
            raise RuntimeError(
                "pyyaml is required to load policy.yaml — install it with: pip install pyyaml"
            )
        with path.open() as fh:
            data = _yaml.safe_load(fh) or {}
        return cls(policy=load_policy(data))

    @classmethod
    def load(cls, path: Path | None = None) -> PolicyEngine:
        """Load from path if it exists, otherwise use built-in restrictive defaults."""
        if path and path.exists():
            return cls.from_file(path)
        return cls()

    # ── primary interface (used by AgentLoop) ─────────────────────────────────

    def check(self, tool_name: str, args: dict[str, Any]) -> Decision:
        """Dispatch to the right sub-check and return the policy decision."""
        if tool_name in _SHELL_TOOLS:
            return self.check_shell(args.get("command", ""))
        if tool_name in _READ_TOOLS:
            return self.check_filesystem_read(Path(args.get("path", ".")))
        if tool_name in _WRITE_TOOLS:
            return self.check_filesystem_write(Path(args.get("path", ".")))
        if tool_name in _SEARCH_TOOLS:
            return self.check_web_search()
        if tool_name in _FETCH_TOOLS:
            return self.check_web_fetch(args.get("url", ""))
        return Decision.ALLOW

    # ── sub-checks ────────────────────────────────────────────────────────────

    def check_shell(self, command: str) -> Decision:
        shell = self._policy.defaults.shell
        # deny patterns are checked first (highest priority)
        for pattern in shell.deny:
            if command.startswith(pattern) or pattern in command:
                return Decision.DENY
        if shell.mode == "confirm_all":
            return Decision.CONFIRM
        # confirm patterns
        for pattern in shell.confirm:
            if command.startswith(pattern + " ") or command == pattern:
                return Decision.CONFIRM
        # allowlist mode: only listed prefixes pass
        if shell.mode == "allowlist":
            for pattern in shell.allow:
                if command.startswith(pattern + " ") or command == pattern:
                    return Decision.ALLOW
            return Decision.DENY
        # denylist mode: allow by default
        return Decision.ALLOW

    def check_filesystem_read(self, path: Path) -> Decision:
        resolved = _resolve(path)
        fs = self._policy.defaults.filesystem
        for pattern in fs.deny:
            if _path_under(resolved, pattern):
                return Decision.DENY
        if not fs.allow_read:
            return Decision.ALLOW  # no explicit allowlist = open read access
        for pattern in fs.allow_read:
            if _path_under(resolved, pattern):
                return Decision.ALLOW
        return Decision.DENY

    def check_filesystem_write(self, path: Path) -> Decision:
        resolved = _resolve(path)
        fs = self._policy.defaults.filesystem
        for pattern in fs.deny:
            if _path_under(resolved, pattern):
                return Decision.DENY
        if not fs.allow_write:
            return Decision.CONFIRM  # no explicit allowlist = confirm all writes
        for pattern in fs.allow_write:
            if _path_under(resolved, pattern):
                return Decision.ALLOW
        return Decision.CONFIRM

    def check_web_search(self) -> Decision:
        return Decision.ALLOW if self._policy.defaults.network.web_search else Decision.DENY

    def check_web_fetch(self, url: str) -> Decision:
        wf = self._policy.defaults.network.web_fetch
        if not wf.allow_domains:
            return Decision.DENY
        if "*" in wf.allow_domains:
            if wf.deny_domains:
                domain = _extract_domain(url)
                if any(d in domain for d in wf.deny_domains):
                    return Decision.DENY
            return Decision.ALLOW
        domain = _extract_domain(url)
        if any(d in domain for d in wf.deny_domains):
            return Decision.DENY
        if any(d in domain for d in wf.allow_domains):
            return Decision.ALLOW
        return Decision.DENY

    # ── guards (read by AgentLoop directly) ──────────────────────────────────

    @property
    def max_tool_calls_per_turn(self) -> int:
        return self._policy.guards.max_tool_calls_per_turn

    @property
    def never_reveal_system_prompt(self) -> bool:
        return self._policy.guards.never_reveal_system_prompt


# ── helpers ───────────────────────────────────────────────────────────────────


def _resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def _path_under(resolved: Path, pattern: str) -> bool:
    """Return True if resolved path is at or under the pattern directory."""
    try:
        base = Path(pattern).expanduser().resolve()
    except OSError:
        base = Path(pattern).expanduser()
    try:
        resolved.relative_to(base)
        return True
    except ValueError:
        return False


def _extract_domain(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).netloc
