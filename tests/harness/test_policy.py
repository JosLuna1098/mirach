"""Tests for PolicyEngine: allow/deny/confirm paths, guards, YAML loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from mirach.harness.policy.engine import Decision, PolicyEngine
from mirach.harness.policy.schema import (
    FilesystemPolicy,
    GuardsPolicy,
    NetworkPolicy,
    Policy,
    PolicyDefaults,
    ShellPolicy,
    WebFetchPolicy,
    load_policy,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _engine(**kwargs) -> PolicyEngine:
    """Build a PolicyEngine with specific policy field overrides."""
    policy = Policy()
    for k, v in kwargs.items():
        setattr(policy.defaults, k, v) if hasattr(policy.defaults, k) else setattr(policy, k, v)
    return PolicyEngine(policy=policy)


# ── shell policy ──────────────────────────────────────────────────────────────


class TestShellPolicy:
    def test_allowlisted_command_is_allowed(self):
        e = PolicyEngine()
        assert e.check_shell("ls -la") == Decision.ALLOW

    def test_unlisted_command_in_allowlist_mode_is_denied(self):
        e = PolicyEngine()
        # nmap is not in allow or confirm, so allowlist mode denies it
        assert e.check_shell("nmap -sS 192.168.1.1") == Decision.DENY

    def test_confirm_list_command_requires_confirm(self):
        e = PolicyEngine()
        assert e.check_shell("rm -rf ./build") == Decision.CONFIRM

    def test_deny_pattern_beats_confirm(self):
        """rm -rf / is in deny even though rm is in confirm."""
        e = PolicyEngine()
        assert e.check_shell("rm -rf /") == Decision.DENY

    def test_deny_beats_allow(self):
        """A deny pattern takes precedence over any allow entry."""
        shell = ShellPolicy(
            mode="allowlist",
            allow=["shutdown"],
            confirm=[],
            deny=["shutdown"],
        )
        e = PolicyEngine(Policy(defaults=PolicyDefaults(shell=shell)))
        assert e.check_shell("shutdown now") == Decision.DENY

    def test_confirm_all_mode(self):
        shell = ShellPolicy(mode="confirm_all", allow=["ls"], confirm=[], deny=[])
        e = PolicyEngine(Policy(defaults=PolicyDefaults(shell=shell)))
        assert e.check_shell("ls -la") == Decision.CONFIRM

    def test_denylist_mode_allows_by_default(self):
        shell = ShellPolicy(mode="denylist", allow=[], confirm=[], deny=["rm"])
        e = PolicyEngine(Policy(defaults=PolicyDefaults(shell=shell)))
        assert e.check_shell("curl https://example.com") == Decision.ALLOW

    def test_denylist_mode_blocks_deny_pattern(self):
        shell = ShellPolicy(mode="denylist", allow=[], confirm=[], deny=["rm"])
        e = PolicyEngine(Policy(defaults=PolicyDefaults(shell=shell)))
        assert e.check_shell("rm ./file") == Decision.DENY

    def test_exact_command_match(self):
        e = PolicyEngine()
        assert e.check_shell("ls") == Decision.ALLOW  # exact, no trailing space


# ── filesystem policy ─────────────────────────────────────────────────────────


class TestFilesystemPolicy:
    def test_read_denied_for_ssh_dir(self, tmp_path):
        e = PolicyEngine()
        ssh_path = Path.home() / ".ssh" / "id_rsa"
        assert e.check_filesystem_read(ssh_path) == Decision.DENY

    def test_read_allowed_when_no_allow_read_configured(self, tmp_path):
        """Empty allow_read = open read access."""
        e = PolicyEngine()
        assert e.check_filesystem_read(tmp_path / "some_file.txt") == Decision.ALLOW

    def test_read_denied_when_not_in_allowlist(self, tmp_path):
        fs = FilesystemPolicy(allow_read=[str(tmp_path / "allowed")], allow_write=[], deny=[])
        e = PolicyEngine(Policy(defaults=PolicyDefaults(filesystem=fs)))
        assert e.check_filesystem_read(tmp_path / "other" / "file.txt") == Decision.DENY

    def test_read_allowed_when_under_allowed_dir(self, tmp_path):
        allowed = tmp_path / "allowed"
        fs = FilesystemPolicy(allow_read=[str(allowed)], allow_write=[], deny=[])
        e = PolicyEngine(Policy(defaults=PolicyDefaults(filesystem=fs)))
        assert e.check_filesystem_read(allowed / "sub" / "file.txt") == Decision.ALLOW

    def test_write_confirm_when_no_allow_write(self, tmp_path):
        """Empty allow_write = all writes require confirmation."""
        e = PolicyEngine()
        assert e.check_filesystem_write(tmp_path / "file.txt") == Decision.CONFIRM

    def test_write_allowed_in_scratch_dir(self, tmp_path):
        scratch = tmp_path / "scratch"
        fs = FilesystemPolicy(allow_read=[], allow_write=[str(scratch)], deny=[])
        e = PolicyEngine(Policy(defaults=PolicyDefaults(filesystem=fs)))
        assert e.check_filesystem_write(scratch / "out.txt") == Decision.ALLOW

    def test_write_denied_for_etc(self):
        e = PolicyEngine()
        assert e.check_filesystem_write(Path("/etc/passwd")) == Decision.DENY


# ── network policy ────────────────────────────────────────────────────────────


class TestNetworkPolicy:
    def test_web_search_allowed_by_default(self):
        e = PolicyEngine()
        assert e.check_web_search() == Decision.ALLOW

    def test_web_search_denied_when_disabled(self):
        net = NetworkPolicy(web_search=False)
        e = PolicyEngine(Policy(defaults=PolicyDefaults(network=net)))
        assert e.check_web_search() == Decision.DENY

    def test_web_fetch_allowed_with_wildcard(self):
        e = PolicyEngine()
        assert e.check_web_fetch("https://example.com/page") == Decision.ALLOW

    def test_web_fetch_denied_domain_in_deny_list(self):
        net = NetworkPolicy(web_fetch=WebFetchPolicy(allow_domains=["*"], deny_domains=["evil.com"]))
        e = PolicyEngine(Policy(defaults=PolicyDefaults(network=net)))
        assert e.check_web_fetch("https://evil.com/payload") == Decision.DENY

    def test_web_fetch_denied_no_allow_domains(self):
        net = NetworkPolicy(web_fetch=WebFetchPolicy(allow_domains=[]))
        e = PolicyEngine(Policy(defaults=PolicyDefaults(network=net)))
        assert e.check_web_fetch("https://example.com") == Decision.DENY

    def test_web_fetch_allowed_specific_domain(self):
        net = NetworkPolicy(
            web_fetch=WebFetchPolicy(allow_domains=["github.com"], deny_domains=[])
        )
        e = PolicyEngine(Policy(defaults=PolicyDefaults(network=net)))
        assert e.check_web_fetch("https://github.com/some/repo") == Decision.ALLOW

    def test_web_fetch_denied_unlisted_domain(self):
        net = NetworkPolicy(
            web_fetch=WebFetchPolicy(allow_domains=["github.com"], deny_domains=[])
        )
        e = PolicyEngine(Policy(defaults=PolicyDefaults(network=net)))
        assert e.check_web_fetch("https://otherdomain.com") == Decision.DENY


# ── check() dispatcher ────────────────────────────────────────────────────────


class TestCheckDispatcher:
    def test_bash_dispatches_to_shell(self):
        e = PolicyEngine()
        assert e.check("bash", {"command": "ls -la"}) == Decision.ALLOW

    def test_read_file_dispatches_to_fs_read(self):
        e = PolicyEngine()
        assert e.check("read_file", {"path": str(Path.home() / ".ssh" / "config")}) == Decision.DENY

    def test_write_file_dispatches_to_fs_write(self):
        e = PolicyEngine()
        # No allow_write configured → confirm
        assert e.check("write_file", {"path": "/tmp/out.txt"}) == Decision.CONFIRM

    def test_web_search_dispatches(self):
        e = PolicyEngine()
        assert e.check("web_search", {"query": "python docs"}) == Decision.ALLOW

    def test_web_fetch_dispatches(self):
        e = PolicyEngine()
        assert e.check("web_fetch", {"url": "https://example.com"}) == Decision.ALLOW

    def test_unknown_tool_is_allowed(self):
        """Tools not in any category default to ALLOW."""
        e = PolicyEngine()
        assert e.check("remember", {"content": "something"}) == Decision.ALLOW
        assert e.check("recall", {"query": "something"}) == Decision.ALLOW


# ── guards ────────────────────────────────────────────────────────────────────


class TestGuards:
    def test_max_tool_calls_default(self):
        e = PolicyEngine()
        assert e.max_tool_calls_per_turn == 25

    def test_max_tool_calls_custom(self):
        policy = Policy(guards=GuardsPolicy(max_tool_calls_per_turn=10))
        e = PolicyEngine(policy)
        assert e.max_tool_calls_per_turn == 10

    def test_never_reveal_system_prompt_default(self):
        e = PolicyEngine()
        assert e.never_reveal_system_prompt is True


# ── YAML loading ──────────────────────────────────────────────────────────────


class TestYAMLLoading:
    def test_load_policy_from_dict(self):
        data = {
            "version": 1,
            "defaults": {
                "shell": {
                    "mode": "denylist",
                    "allow": [],
                    "confirm": [],
                    "deny": ["rm"],
                },
                "filesystem": {
                    "allow_read": ["~/Projects"],
                    "allow_write": ["~/Projects/scratch"],
                    "deny": ["/etc"],
                },
                "network": {"web_search": False},
            },
            "guards": {"max_tool_calls_per_turn": 10, "never_reveal_system_prompt": False},
        }
        policy = load_policy(data)
        assert policy.version == 1
        assert policy.defaults.shell.mode == "denylist"
        assert policy.defaults.shell.deny == ["rm"]
        assert policy.defaults.filesystem.allow_read == ["~/Projects"]
        assert policy.defaults.network.web_search is False
        assert policy.guards.max_tool_calls_per_turn == 10
        assert policy.guards.never_reveal_system_prompt is False

    def test_load_policy_empty_dict_uses_defaults(self):
        policy = load_policy({})
        assert policy.version == 1
        assert policy.defaults.shell.mode == "allowlist"
        assert policy.guards.max_tool_calls_per_turn == 25

    def test_from_file(self, tmp_path):
        pytest.importorskip("yaml")
        import yaml

        policy_data = {"version": 1, "guards": {"max_tool_calls_per_turn": 5}}
        policy_file = tmp_path / "policy.yaml"
        policy_file.write_text(yaml.dump(policy_data))

        e = PolicyEngine.from_file(policy_file)
        assert e.max_tool_calls_per_turn == 5

    def test_load_factory_uses_defaults_when_no_file(self):
        e = PolicyEngine.load(path=None)
        assert e.max_tool_calls_per_turn == 25

    def test_load_factory_reads_file_when_present(self, tmp_path):
        pytest.importorskip("yaml")
        import yaml

        policy_file = tmp_path / "policy.yaml"
        policy_file.write_text(yaml.dump({"guards": {"max_tool_calls_per_turn": 3}}))

        e = PolicyEngine.load(path=policy_file)
        assert e.max_tool_calls_per_turn == 3
