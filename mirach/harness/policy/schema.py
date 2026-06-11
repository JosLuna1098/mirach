"""Pure-Python schema types for policy.yaml — no Pydantic, no external deps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FilesystemPolicy:
    allow_read: list[str] = field(default_factory=list)
    allow_write: list[str] = field(default_factory=list)
    deny: list[str] = field(
        default_factory=lambda: [
            "~/.ssh",
            "~/.gnupg",
            "~/.config",
            "/etc",
            "/usr",
            "/boot",
            "/sys",
            "/proc",
        ]
    )


@dataclass
class ShellPolicy:
    # allowlist: only listed prefixes are allowed
    # denylist:  listed prefixes are denied, everything else allowed
    # confirm_all: every command requires confirmation
    mode: str = "allowlist"
    allow: list[str] = field(
        default_factory=lambda: [
            "ls",
            "cat",
            "grep",
            "rg",
            "find",
            "echo",
            "pwd",
            "git status",
            "git diff",
            "git log",
            "git show",
            "python",
            "python3",
        ]
    )
    confirm: list[str] = field(
        default_factory=lambda: [
            "rm",
            "mv",
            "cp",
            "mkdir",
            "touch",
            "git push",
            "git commit",
            "git checkout",
            "git merge",
            "git reset",
            "pip install",
            "pip uninstall",
            "systemctl",
            "sudo",
            "curl",
            "wget",
            "chmod",
            "chown",
        ]
    )
    deny: list[str] = field(
        default_factory=lambda: [
            "rm -rf /",
            "rm -rf ~/.",
            "rm -fr /",
            "mkfs",
            "dd ",
            "shutdown",
            "reboot",
            "halt",
            ":(){:|:&};:",  # fork bomb
        ]
    )


@dataclass
class WebFetchPolicy:
    allow_domains: list[str] = field(default_factory=lambda: ["*"])
    deny_domains: list[str] = field(default_factory=list)


@dataclass
class NetworkPolicy:
    web_search: bool = True
    web_fetch: WebFetchPolicy = field(default_factory=WebFetchPolicy)


@dataclass
class SystemConfigPolicy:
    require_confirmation: bool = True


@dataclass
class PolicyDefaults:
    filesystem: FilesystemPolicy = field(default_factory=FilesystemPolicy)
    shell: ShellPolicy = field(default_factory=ShellPolicy)
    network: NetworkPolicy = field(default_factory=NetworkPolicy)
    system_config: SystemConfigPolicy = field(default_factory=SystemConfigPolicy)


@dataclass
class GuardsPolicy:
    never_reveal_system_prompt: bool = True
    max_tool_calls_per_turn: int = 25


@dataclass
class Policy:
    version: int = 1
    defaults: PolicyDefaults = field(default_factory=PolicyDefaults)
    guards: GuardsPolicy = field(default_factory=GuardsPolicy)


# ── YAML → dataclass loader ───────────────────────────────────────────────────


def load_policy(data: dict[str, Any]) -> Policy:
    """Deserialize a policy.yaml dict into a Policy dataclass tree."""
    p = Policy(version=data.get("version", 1))
    d = data.get("defaults", {})

    fs = d.get("filesystem", {})
    p.defaults.filesystem = FilesystemPolicy(
        allow_read=fs.get("allow_read", []),
        allow_write=fs.get("allow_write", []),
        deny=fs.get("deny", FilesystemPolicy().deny),
    )

    sh = d.get("shell", {})
    p.defaults.shell = ShellPolicy(
        mode=sh.get("mode", "allowlist"),
        allow=sh.get("allow", ShellPolicy().allow),
        confirm=sh.get("confirm", ShellPolicy().confirm),
        deny=sh.get("deny", ShellPolicy().deny),
    )

    net = d.get("network", {})
    wf = net.get("web_fetch", {})
    p.defaults.network = NetworkPolicy(
        web_search=net.get("web_search", True),
        web_fetch=WebFetchPolicy(
            allow_domains=wf.get("allow_domains", ["*"]),
            deny_domains=wf.get("deny_domains", []),
        ),
    )

    sc = d.get("system_config", {})
    p.defaults.system_config = SystemConfigPolicy(
        require_confirmation=sc.get("require_confirmation", True),
    )

    g = data.get("guards", {})
    p.guards = GuardsPolicy(
        never_reveal_system_prompt=g.get("never_reveal_system_prompt", True),
        max_tool_calls_per_turn=g.get("max_tool_calls_per_turn", 25),
    )

    return p
