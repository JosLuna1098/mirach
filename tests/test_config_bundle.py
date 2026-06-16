"""
Round-trip tests for `mirach config export / import`.

All I/O is redirected to tmp_path — no writes to HOME or the real repo.
systemd helpers are mocked to a no-op lambda.
"""

from __future__ import annotations

import io
import json
import tarfile

import pytest

yaml = pytest.importorskip("yaml")

from mirach import config  # noqa: E402
from mirach.cli import main, read_env  # noqa: E402

# ── shared fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _no_systemd(monkeypatch):
    monkeypatch.setattr("mirach.cli._systemd_unit_active", lambda: False)


@pytest.fixture()
def src_repo(tmp_path, monkeypatch):
    """Minimal fake repo with exportable content."""
    repo = tmp_path / "src"
    repo.mkdir()
    monkeypatch.setattr(config, "BASE_DIR", repo)

    (repo / "system_prompt.md").write_text("# You are Mirach\n")

    skill = repo / "skills" / "test-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Test skill\nDoes something.\n")

    us = repo / "user_scripts"
    us.mkdir()
    (us / "hello.sh").write_text("#!/bin/bash\necho hi\n")
    (us / ".gitkeep").touch()

    (repo / "policy.yaml").write_text("version: 1\ndefaults:\n  shell:\n    mode: allowlist\n")
    (repo / "policy.dangerous.example.yaml").write_text(
        "version: 1\ndefaults:\n  shell:\n    mode: denylist\n"
    )

    env_file = repo / "mirach.env"
    env_file.write_text(
        "MIRACH_LOCALE=es\n"
        "MIRACH_WHISPER_MODEL=medium\n"
        "MIRACH_WHISPER_LANG=es\n"
        "MIRACH_BACKEND=opencode_serve\n"
        "MIRACH_HOTKEY=Alt+Z\n"
        "MIRACH_VOICE=es_MX-ald-medium.onnx\n"
    )
    return repo


# ── export tests ───────────────────────────────────────────────────────────────


def test_export_creates_bundle(src_repo, tmp_path):
    out = tmp_path / "bundle.tar.gz"
    env_file = src_repo / "mirach.env"
    rc = main(["--env-file", str(env_file), "config", "export", "--out", str(out)])
    assert rc == 0
    assert out.exists()

    with tarfile.open(out, "r:gz") as tf:
        names = tf.getnames()

    assert "manifest.yaml" in names
    assert "system_prompt.md" in names
    assert "skills/test-skill/SKILL.md" in names
    assert "policy.yaml" in names
    assert "policy.dangerous.example.yaml" in names


def test_export_gitkeep_excluded(src_repo, tmp_path):
    out = tmp_path / "bundle.tar.gz"
    env_file = src_repo / "mirach.env"
    main(["--env-file", str(env_file), "config", "export", "--out", str(out)])

    with tarfile.open(out, "r:gz") as tf:
        names = tf.getnames()

    assert ".gitkeep" not in names


def test_export_user_script_included(src_repo, tmp_path):
    out = tmp_path / "bundle.tar.gz"
    env_file = src_repo / "mirach.env"
    main(["--env-file", str(env_file), "config", "export", "--out", str(out)])

    with tarfile.open(out, "r:gz") as tf:
        names = tf.getnames()

    assert "user_scripts/hello.sh" in names


def test_manifest_portable_keys(src_repo, tmp_path):
    out = tmp_path / "bundle.tar.gz"
    env_file = src_repo / "mirach.env"
    main(["--env-file", str(env_file), "config", "export", "--out", str(out)])

    with tarfile.open(out, "r:gz") as tf:
        manifest = yaml.safe_load(tf.extractfile("manifest.yaml").read())

    assert manifest["manifest_version"] == 1
    assert "exported_at" in manifest
    p = manifest["portable"]
    assert p["MIRACH_LOCALE"] == "es"
    assert p["MIRACH_WHISPER_MODEL"] == "medium"
    assert p["MIRACH_BACKEND"] == "opencode_serve"
    assert p["policy_mode"] == "safe"


def test_manifest_machine_keys(src_repo, tmp_path):
    out = tmp_path / "bundle.tar.gz"
    env_file = src_repo / "mirach.env"
    main(["--env-file", str(env_file), "config", "export", "--out", str(out)])

    with tarfile.open(out, "r:gz") as tf:
        manifest = yaml.safe_load(tf.extractfile("manifest.yaml").read())

    mref = manifest["machine_specific_reference"]
    assert mref["MIRACH_HOTKEY"] == "Alt+Z"
    assert mref["MIRACH_VOICE"] == "es_MX-ald-medium.onnx"


def test_bundle_excludes_secrets(src_repo, tmp_path):
    """auth files, .env, and mirach.env itself must never appear in the bundle."""
    # Place secret files inside the repo tree
    (src_repo / "auth.json").write_text('{"token": "s3cr3t"}')
    (src_repo / ".env").write_text("OPENAI_KEY=s3cr3t")

    out = tmp_path / "bundle.tar.gz"
    env_file = src_repo / "mirach.env"
    main(["--env-file", str(env_file), "config", "export", "--out", str(out)])

    with tarfile.open(out, "r:gz") as tf:
        names = tf.getnames()

    assert "auth.json" not in names
    assert ".env" not in names
    assert "mirach.env" not in names


def test_default_out_name(src_repo, monkeypatch, tmp_path):
    """When --out is omitted, the bundle appears in cwd with a date-based name."""
    monkeypatch.chdir(tmp_path)
    env_file = src_repo / "mirach.env"
    rc = main(["--env-file", str(env_file), "config", "export"])
    assert rc == 0
    bundles = list(tmp_path.glob("mirach-config-*.tar.gz"))
    assert len(bundles) == 1


# ── import tests ───────────────────────────────────────────────────────────────


@pytest.fixture()
def bundle(src_repo, tmp_path):
    """Pre-built bundle from src_repo."""
    out = tmp_path / "bundle.tar.gz"
    env_file = src_repo / "mirach.env"
    main(["--env-file", str(env_file), "config", "export", "--out", str(out)])
    return out


def test_roundtrip_content(src_repo, bundle, tmp_path, monkeypatch):
    dest_repo = tmp_path / "dest"
    dest_repo.mkdir()
    dest_env = dest_repo / "mirach.env"
    fake_home = tmp_path / "fakehome"

    monkeypatch.setattr(config, "BASE_DIR", dest_repo)
    monkeypatch.setattr("mirach.cli._OPENCODE_HOME", fake_home)

    rc = main(["--env-file", str(dest_env), "config", "import", str(bundle), "--yes"])
    assert rc == 0

    assert (dest_repo / "system_prompt.md").read_text() == "# You are Mirach\n"
    assert (dest_repo / "skills" / "test-skill" / "SKILL.md").exists()
    assert (dest_repo / "user_scripts" / "hello.sh").exists()
    assert (dest_repo / "policy.yaml").exists()


def test_roundtrip_portable_settings(src_repo, bundle, tmp_path, monkeypatch):
    dest_repo = tmp_path / "dest"
    dest_repo.mkdir()
    dest_env = dest_repo / "mirach.env"
    fake_home = tmp_path / "fakehome"

    monkeypatch.setattr(config, "BASE_DIR", dest_repo)
    monkeypatch.setattr("mirach.cli._OPENCODE_HOME", fake_home)

    main(["--env-file", str(dest_env), "config", "import", str(bundle), "--yes"])

    env = read_env(dest_env)
    assert env["MIRACH_LOCALE"] == "es"
    assert env["MIRACH_WHISPER_MODEL"] == "medium"
    assert env["MIRACH_BACKEND"] == "opencode_serve"


def test_roundtrip_machine_hints_in_yes_mode(src_repo, bundle, tmp_path, monkeypatch):
    """In --yes mode, machine-specific hints from the bundle are written to mirach.env."""
    dest_repo = tmp_path / "dest"
    dest_repo.mkdir()
    dest_env = dest_repo / "mirach.env"
    fake_home = tmp_path / "fakehome"

    monkeypatch.setattr(config, "BASE_DIR", dest_repo)
    monkeypatch.setattr("mirach.cli._OPENCODE_HOME", fake_home)

    main(["--env-file", str(dest_env), "config", "import", str(bundle), "--yes"])

    env = read_env(dest_env)
    assert env.get("MIRACH_HOTKEY") == "Alt+Z"
    assert env.get("MIRACH_VOICE") == "es_MX-ald-medium.onnx"


def test_roundtrip_opencode_json_updated(src_repo, bundle, tmp_path, monkeypatch):
    """Import updates ~/.config/opencode/opencode.json with the skills path."""
    dest_repo = tmp_path / "dest"
    dest_repo.mkdir()
    dest_env = dest_repo / "mirach.env"
    fake_home = tmp_path / "fakehome"

    monkeypatch.setattr(config, "BASE_DIR", dest_repo)
    monkeypatch.setattr("mirach.cli._OPENCODE_HOME", fake_home)

    main(["--env-file", str(dest_env), "config", "import", str(bundle), "--yes"])

    ocode_cfg = fake_home / ".config" / "opencode" / "opencode.json"
    assert ocode_cfg.exists()
    cfg = json.loads(ocode_cfg.read_text())
    skills_paths = cfg.get("skills", {}).get("paths", [])
    assert any("opencode/skills" in p for p in skills_paths)


def test_import_yes_overwrites_existing(src_repo, bundle, tmp_path, monkeypatch):
    """--yes (yes-to-everything) overwrites existing files."""
    dest_repo = tmp_path / "dest"
    dest_repo.mkdir()
    dest_env = dest_repo / "mirach.env"
    fake_home = tmp_path / "fakehome"

    (dest_repo / "system_prompt.md").write_text("# Old prompt\n")

    monkeypatch.setattr(config, "BASE_DIR", dest_repo)
    monkeypatch.setattr("mirach.cli._OPENCODE_HOME", fake_home)

    main(["--env-file", str(dest_env), "config", "import", str(bundle), "--yes"])

    assert (dest_repo / "system_prompt.md").read_text() == "# You are Mirach\n"


def test_import_interactive_decline_keeps_existing(src_repo, bundle, tmp_path, monkeypatch):
    """Interactive run: declining the overwrite prompt keeps existing files."""
    dest_repo = tmp_path / "dest"
    dest_repo.mkdir()
    dest_env = dest_repo / "mirach.env"
    fake_home = tmp_path / "fakehome"

    (dest_repo / "system_prompt.md").write_text("# My existing prompt\n")

    monkeypatch.setattr(config, "BASE_DIR", dest_repo)
    monkeypatch.setattr("mirach.cli._OPENCODE_HOME", fake_home)
    # Force interactive code path and decline the overwrite question.
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("mirach.cli._confirm", lambda *a, **k: False)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")  # wizard keeps defaults

    main(["--env-file", str(dest_env), "config", "import", str(bundle)])

    # The existing file must not be overwritten when the user declines.
    assert (dest_repo / "system_prompt.md").read_text() == "# My existing prompt\n"


def test_import_missing_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    rc = main(
        [
            "--env-file",
            str(tmp_path / "mirach.env"),
            "config",
            "import",
            str(tmp_path / "nope.tar.gz"),
        ]
    )
    assert rc != 0


# ── path-traversal guard ───────────────────────────────────────────────────────


def test_path_traversal_rejected(tmp_path, monkeypatch):
    """A bundle containing '../evil' must be rejected before any extraction."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(config, "BASE_DIR", repo)

    bad_bundle = tmp_path / "evil.tar.gz"
    evil_content = b"malicious content"
    with tarfile.open(bad_bundle, "w:gz") as tf:
        info = tarfile.TarInfo("../evil.txt")
        info.size = len(evil_content)
        tf.addfile(info, io.BytesIO(evil_content))

    rc = main(
        ["--env-file", str(repo / "mirach.env"), "config", "import", str(bad_bundle), "--yes"]
    )
    assert rc != 0
    # The file must not have been written anywhere near tmp_path
    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path.parent / "evil.txt").exists()


def test_absolute_path_in_bundle_rejected(tmp_path, monkeypatch):
    """A bundle member with an absolute path must be rejected."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(config, "BASE_DIR", repo)

    bad_bundle = tmp_path / "abs.tar.gz"
    content = b"bad"
    with tarfile.open(bad_bundle, "w:gz") as tf:
        info = tarfile.TarInfo("/etc/passwd")
        info.size = len(content)
        tf.addfile(info, io.BytesIO(content))

    rc = main(
        ["--env-file", str(repo / "mirach.env"), "config", "import", str(bad_bundle), "--yes"]
    )
    assert rc != 0


# ── policy_mode handling ───────────────────────────────────────────────────────


def test_export_policy_mode_safe(src_repo, tmp_path):
    env_file = src_repo / "mirach.env"
    out = tmp_path / "bundle.tar.gz"
    main(["--env-file", str(env_file), "config", "export", "--out", str(out)])

    with tarfile.open(out, "r:gz") as tf:
        manifest = yaml.safe_load(tf.extractfile("manifest.yaml").read())

    assert manifest["portable"]["policy_mode"] == "safe"


def test_export_policy_mode_dangerous(src_repo, tmp_path):
    env_file = src_repo / "mirach.env"
    dangerous_path = src_repo / "policy.dangerous.yaml"
    dangerous_path.write_text("version: 1\n")
    # Point mirach.env at the dangerous policy
    env_file.write_text(env_file.read_text() + f"MIRACH_NATIVE_POLICY={dangerous_path}\n")

    out = tmp_path / "bundle.tar.gz"
    main(["--env-file", str(env_file), "config", "export", "--out", str(out)])

    with tarfile.open(out, "r:gz") as tf:
        names = tf.getnames()
        manifest = yaml.safe_load(tf.extractfile("manifest.yaml").read())

    assert manifest["portable"]["policy_mode"] == "dangerous"
    assert "policy.dangerous.yaml" in names


def test_import_policy_safe_writes_env(src_repo, bundle, tmp_path, monkeypatch):
    dest_repo = tmp_path / "dest"
    dest_repo.mkdir()
    dest_env = dest_repo / "mirach.env"
    fake_home = tmp_path / "fakehome"

    monkeypatch.setattr(config, "BASE_DIR", dest_repo)
    monkeypatch.setattr("mirach.cli._OPENCODE_HOME", fake_home)

    main(["--env-file", str(dest_env), "config", "import", str(bundle), "--yes"])

    env = read_env(dest_env)
    assert env.get("MIRACH_NATIVE_POLICY", "").endswith("policy.yaml")
    assert not env.get("MIRACH_NATIVE_POLICY", "").endswith("policy.dangerous.yaml")


def test_import_dangerous_source_lands_on_safe(src_repo, tmp_path, monkeypatch, capsys):
    """A bundle exported from a dangerous machine still imports as SAFE."""
    # Build a dangerous-source bundle.
    env_file = src_repo / "mirach.env"
    dangerous_path = src_repo / "policy.dangerous.yaml"
    dangerous_path.write_text("version: 1\n")
    env_file.write_text(env_file.read_text() + f"MIRACH_NATIVE_POLICY={dangerous_path}\n")
    out = tmp_path / "bundle.tar.gz"
    main(["--env-file", str(env_file), "config", "export", "--out", str(out)])

    # Import into a fresh repo.
    dest_repo = tmp_path / "dest"
    dest_repo.mkdir()
    dest_env = dest_repo / "mirach.env"
    fake_home = tmp_path / "fakehome"
    monkeypatch.setattr(config, "BASE_DIR", dest_repo)
    monkeypatch.setattr("mirach.cli._OPENCODE_HOME", fake_home)

    main(["--env-file", str(dest_env), "config", "import", str(out), "--yes"])

    env = read_env(dest_env)
    assert env.get("MIRACH_NATIVE_POLICY", "").endswith("policy.yaml")
    assert not env.get("MIRACH_NATIVE_POLICY", "").endswith("policy.dangerous.yaml")
    # And the user is told how to re-enable it.
    assert "mirach policy dangerous" in capsys.readouterr().out
