"""Tests for mirach/cli.py — policy subcommand (safe/dangerous toggle).

Side-effect free: config.BASE_DIR is monkeypatched to tmp_path so no real
policy file is written into the repo, and systemd is mocked.
"""

from __future__ import annotations

import pytest

from mirach import config
from mirach.cli import _policy_label, main, read_env


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """Point config.BASE_DIR at a temp dir with a dangerous template present."""
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    (tmp_path / "policy.dangerous.example.yaml").write_text(
        "version: 1\ndefaults:\n  shell:\n    mode: denylist\n"
    )
    monkeypatch.setattr("mirach.cli._systemd_unit_active", lambda: False)
    return tmp_path


# ── _policy_label ──────────────────────────────────────────────────────────────


def test_policy_label_safe(tmp_path):
    assert _policy_label(tmp_path / "policy.yaml") == "safe"


def test_policy_label_dangerous(tmp_path):
    assert _policy_label(tmp_path / "policy.dangerous.yaml") == "dangerous"


def test_policy_label_custom(tmp_path):
    assert _policy_label(tmp_path / "my-policy.yaml") == "custom"


# ── show current policy ─────────────────────────────────────────────────────────


def test_policy_show_reports_dangerous(repo, tmp_path, capsys):
    f = tmp_path / "mirach.env"
    f.write_text(f"MIRACH_NATIVE_POLICY={tmp_path / 'policy.dangerous.yaml'}\n")
    rc = main(["--env-file", str(f), "policy"])
    assert rc == 0
    assert "dangerous" in capsys.readouterr().out


def test_policy_show_reports_safe(repo, tmp_path, capsys):
    f = tmp_path / "mirach.env"
    f.write_text(f"MIRACH_NATIVE_POLICY={tmp_path / 'policy.yaml'}\n")
    rc = main(["--env-file", str(f), "policy"])
    assert rc == 0
    assert "safe" in capsys.readouterr().out


# ── safe ─────────────────────────────────────────────────────────────────────


def test_policy_safe_points_env_at_policy_yaml(repo, tmp_path):
    f = tmp_path / "mirach.env"
    rc = main(["--env-file", str(f), "policy", "safe"])
    assert rc == 0
    env = read_env(f)
    assert env["MIRACH_NATIVE_POLICY"] == str(tmp_path / "policy.yaml")


# ── dangerous ────────────────────────────────────────────────────────────────


def test_policy_dangerous_materializes_file_and_points_env(repo, tmp_path):
    f = tmp_path / "mirach.env"
    rc = main(["--env-file", str(f), "policy", "dangerous", "--yes"])
    assert rc == 0
    dangerous = tmp_path / "policy.dangerous.yaml"
    assert dangerous.exists()  # copied from the template
    env = read_env(f)
    assert env["MIRACH_NATIVE_POLICY"] == str(dangerous)


def test_policy_dangerous_missing_template_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)  # no template created here
    monkeypatch.setattr("mirach.cli._systemd_unit_active", lambda: False)
    f = tmp_path / "mirach.env"
    rc = main(["--env-file", str(f), "policy", "dangerous", "--yes"])
    assert rc != 0
    assert not (tmp_path / "policy.dangerous.yaml").exists()
    assert "MIRACH_NATIVE_POLICY" not in read_env(f)


def test_policy_dangerous_preserves_existing_file(repo, tmp_path):
    """An existing policy.dangerous.yaml is reused, not overwritten."""
    dangerous = tmp_path / "policy.dangerous.yaml"
    dangerous.write_text("# my custom dangerous tweaks\nversion: 1\n")
    f = tmp_path / "mirach.env"
    rc = main(["--env-file", str(f), "policy", "dangerous", "--yes"])
    assert rc == 0
    assert "my custom dangerous tweaks" in dangerous.read_text()


# ── unknown mode ─────────────────────────────────────────────────────────────


def test_policy_unknown_mode_errors(repo, tmp_path):
    f = tmp_path / "mirach.env"
    rc = main(["--env-file", str(f), "policy", "yolo"])
    assert rc != 0
    assert "MIRACH_NATIVE_POLICY" not in read_env(f)
