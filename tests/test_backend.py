"""Tests for mirach/cli.py — backend subcommand.

All tests are side-effect free: no real mirach.env is written (tmp_path fixture),
no real opencode or Ollama process is contacted (validation helpers are mocked).
No sounddevice dependency.
"""

from __future__ import annotations

from mirach.cli import main, read_env

# ── show current backend (no positional arg) ───────────────────────────────────


def test_backend_show_opencode_current(tmp_path, capsys):
    f = tmp_path / "mirach.env"
    f.write_text("MIRACH_BACKEND=opencode_serve\n")
    rc = main(["--env-file", str(f), "backend"])
    assert rc == 0
    assert "opencode_serve" in capsys.readouterr().out


def test_backend_show_native_current(tmp_path, capsys):
    f = tmp_path / "mirach.env"
    f.write_text("MIRACH_BACKEND=native\n")
    rc = main(["--env-file", str(f), "backend"])
    assert rc == 0
    assert "native" in capsys.readouterr().out


def test_backend_show_when_no_env_file(tmp_path, capsys):
    f = tmp_path / "mirach.env"  # does not exist — falls back to config default
    rc = main(["--env-file", str(f), "backend"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "opencode_serve" in out or "native" in out  # some backend shown


# ── opencode — binary available → writes env ───────────────────────────────────


def test_backend_opencode_valid_bin_writes_env(tmp_path, monkeypatch):
    f = tmp_path / "mirach.env"
    monkeypatch.setattr("mirach.cli._validate_opencode_bin", lambda b: (True, "/usr/bin/opencode"))
    monkeypatch.setattr("mirach.cli._systemd_unit_active", lambda: False)

    rc = main(["--env-file", str(f), "backend", "opencode"])
    assert rc == 0
    env = read_env(f)
    assert env["MIRACH_BACKEND"] == "opencode_serve"


def test_backend_opencode_with_model_splits_provider(tmp_path, monkeypatch):
    f = tmp_path / "mirach.env"
    monkeypatch.setattr("mirach.cli._validate_opencode_bin", lambda b: (True, "/usr/bin/opencode"))
    monkeypatch.setattr("mirach.cli._systemd_unit_active", lambda: False)

    rc = main(["--env-file", str(f), "backend", "opencode", "--model", "opencode/deepseek-v4"])
    assert rc == 0
    env = read_env(f)
    assert env["MIRACH_OPENCODE_SERVE_PROVIDER_ID"] == "opencode"
    assert env["MIRACH_OPENCODE_SERVE_MODEL_ID"] == "deepseek-v4"


# ── opencode — binary missing → error, env unchanged ──────────────────────────


def test_backend_opencode_missing_bin_does_not_write(tmp_path, monkeypatch):
    f = tmp_path / "mirach.env"
    monkeypatch.setattr(
        "mirach.cli._validate_opencode_bin",
        lambda b: (False, "opencode binary 'opencode' not found in PATH"),
    )

    rc = main(["--env-file", str(f), "backend", "opencode"])
    assert rc != 0
    env = read_env(f)
    assert "MIRACH_BACKEND" not in env


# ── native — Ollama reachable → writes env ────────────────────────────────────


def test_backend_native_ollama_available_writes_env(tmp_path, monkeypatch):
    f = tmp_path / "mirach.env"
    monkeypatch.setattr("mirach.cli._validate_ollama", lambda u: (True, ""))
    monkeypatch.setattr("mirach.cli._systemd_unit_active", lambda: False)

    rc = main(["--env-file", str(f), "backend", "native"])
    assert rc == 0
    env = read_env(f)
    assert env["MIRACH_BACKEND"] == "native"


def test_backend_native_with_model_writes_model(tmp_path, monkeypatch):
    f = tmp_path / "mirach.env"
    monkeypatch.setattr("mirach.cli._validate_ollama", lambda u: (True, ""))
    monkeypatch.setattr("mirach.cli._ollama_has_model", lambda u, m: True)
    monkeypatch.setattr("mirach.cli._systemd_unit_active", lambda: False)

    rc = main(["--env-file", str(f), "backend", "native", "--model", "qwen3:14b"])
    assert rc == 0
    env = read_env(f)
    assert env["MIRACH_NATIVE_MODEL"] == "qwen3:14b"


# ── native — Ollama unreachable → error, env unchanged ────────────────────────


def test_backend_native_ollama_unreachable_does_not_write(tmp_path, monkeypatch):
    f = tmp_path / "mirach.env"
    monkeypatch.setattr(
        "mirach.cli._validate_ollama",
        lambda u: (False, "Ollama not reachable at http://localhost:11434: Connection refused"),
    )

    rc = main(["--env-file", str(f), "backend", "native"])
    assert rc != 0
    env = read_env(f)
    assert "MIRACH_BACKEND" not in env


# ── unknown backend name → error ──────────────────────────────────────────────


def test_backend_unknown_name_returns_error(tmp_path):
    f = tmp_path / "mirach.env"
    rc = main(["--env-file", str(f), "backend", "foobar"])
    assert rc != 0


# ── _validate_opencode_bin: version gate ──────────────────────────────────────


def _fake_run(version_output: bytes):
    """Stub subprocess.run for `opencode --version`."""

    class _R:
        returncode = 0
        stdout = version_output
        stderr = b""

    def _run(*_args, **_kwargs):
        return _R()

    return _run


def test_validate_opencode_bin_rejects_v1(monkeypatch, tmp_path):
    from mirach.cli import _validate_opencode_bin

    fake_bin = tmp_path / "opencode"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)
    monkeypatch.setattr("subprocess.run", _fake_run(b"1.18.29\n"))

    ok, msg = _validate_opencode_bin(str(fake_bin))
    assert not ok
    assert "requires opencode >= 2.0" in msg
    assert "1.18.29" in msg


def test_validate_opencode_bin_accepts_v2(monkeypatch, tmp_path):
    from mirach.cli import _validate_opencode_bin

    fake_bin = tmp_path / "opencode"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)
    monkeypatch.setattr("subprocess.run", _fake_run(b"opencode v2.0.5\n"))

    ok, resolved = _validate_opencode_bin(str(fake_bin))
    assert ok
    assert resolved == str(fake_bin)


def test_validate_opencode_bin_accepts_unparseable_version(monkeypatch, tmp_path):
    from mirach.cli import _validate_opencode_bin

    fake_bin = tmp_path / "opencode"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)
    monkeypatch.setattr("subprocess.run", _fake_run(b"dev build\n"))

    ok, resolved = _validate_opencode_bin(str(fake_bin))
    assert ok
    assert resolved == str(fake_bin)
