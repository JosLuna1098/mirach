"""mirach CLI — argparse subcommands for everyday daemon operations."""

from __future__ import annotations

import argparse
import contextlib
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from mirach import config
from mirach.langpack import LANGUAGE_PACKS, pack_for

# Default path to mirach.env. Override via hidden --env-file flag (used by tests).
ENV_PATH: Path = config.BASE_DIR / "mirach.env"


# ── mirach.env helpers ─────────────────────────────────────────────────────────


def read_env(path: Path | None = None) -> dict[str, str]:
    """Parse KEY=VALUE lines; ignore blanks and comments. Split on first '='."""
    p = Path(path) if path is not None else ENV_PATH
    if not p.exists():
        return {}
    result: dict[str, str] = {}
    for line in p.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, val = line.partition("=")
        if sep:
            result[key.strip()] = val
    return result


def set_env_vars(updates: dict[str, str], path: Path | None = None) -> None:
    """Upsert KEY=VALUE lines into mirach.env, preserving comments and order."""
    p = Path(path) if path is not None else ENV_PATH
    if p.exists():
        lines = p.read_text().splitlines()
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Generated/edited by mirach CLI.",
            "# See mirach.env.example for all available options.",
            "",
        ]

    remaining = dict(updates)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        k, sep, _ = line.partition("=")
        if sep and k.strip() in remaining:
            key = k.strip()
            lines[i] = f"{key}={remaining.pop(key)}"

    for key, val in remaining.items():
        lines.append(f"{key}={val}")

    p.write_text("\n".join(lines) + "\n")


# ── internal helpers ───────────────────────────────────────────────────────────


def _voice_lang(voice_name: str) -> str:
    """Infer language from a Piper voice filename ('es_MX-ald-medium.onnx' → 'es')."""
    stem = Path(voice_name).stem
    prefix = stem.split("_")[0]
    return prefix if prefix in LANGUAGE_PACKS else ""


def _confirm(prompt: str, default: bool = False) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    try:
        ans = input(f"{prompt} {hint} ").strip().lower()
    except EOFError:
        return default
    return ans.startswith("y") if ans else default


def _systemctl_available() -> bool:
    return bool(shutil.which("systemctl"))


def _systemd_unit_exists() -> bool:
    if not _systemctl_available():
        return False
    r = subprocess.run(
        ["systemctl", "--user", "cat", "mirach.service"],
        capture_output=True,
    )
    return r.returncode == 0


def _systemd_unit_active() -> bool:
    if not _systemctl_available():
        return False
    r = subprocess.run(
        ["systemctl", "--user", "is-active", "mirach.service"],
        capture_output=True,
    )
    return r.returncode == 0


def _run_systemctl(action: str) -> int:
    r = subprocess.run(["systemctl", "--user", action, "mirach.service"])
    return r.returncode


def _download_voice(voice_name: str, voice_url: str, voices_dir: Path) -> None:
    """Download Piper voice (.onnx + .json) if not already present."""
    voices_dir.mkdir(parents=True, exist_ok=True)
    for url in (voice_url, voice_url + ".json"):
        dest = voices_dir / url.split("/")[-1]
        if dest.exists():
            continue
        print(f"Downloading {dest.name}...", end=" ", flush=True)
        urllib.request.urlretrieve(url, dest)
        print("done")


# ── backend validation helpers (also imported by install.py) ──────────────────


def _validate_opencode_bin(bin_path: str) -> tuple[bool, str]:
    """Validate an opencode binary. Returns (ok, resolved_path_or_error_message)."""
    if os.sep in bin_path or (os.altsep and os.altsep in bin_path):
        p = Path(bin_path)
        if not p.is_file() or not os.access(p, os.X_OK):
            return False, f"opencode binary not found or not executable: {bin_path}"
        resolved = str(p)
    else:
        resolved = shutil.which(bin_path) or ""
        if not resolved:
            return False, f"opencode binary '{bin_path}' not found in PATH"
    try:
        r = subprocess.run([resolved, "--version"], capture_output=True, timeout=5)
        if r.returncode != 0:
            return False, f"'{resolved} --version' failed (exit {r.returncode})"
    except subprocess.TimeoutExpired:
        return False, f"'{resolved} --version' timed out"
    except FileNotFoundError:
        return False, f"opencode not found: {resolved}"
    return True, resolved


def _validate_ollama(base_url: str) -> tuple[bool, str]:
    """Check if Ollama is running at base_url. Returns (ok, error_message)."""
    url = base_url.rstrip("/") + "/api/tags"
    try:
        urllib.request.urlopen(url, timeout=3)
        return True, ""
    except urllib.error.URLError as e:
        return False, f"Ollama not reachable at {base_url}: {e.reason}"
    except OSError as e:
        return False, f"Ollama not reachable at {base_url}: {e}"


def _ollama_has_model(base_url: str, model: str) -> bool:
    """Return True if model exists in ollama's local tag list."""
    url = base_url.rstrip("/") + "/api/tags"
    try:
        resp = urllib.request.urlopen(url, timeout=3)
        data = json.loads(resp.read())
        names = [m.get("name", "") for m in data.get("models", [])]
        for n in names:
            if n == model:
                return True
            if ":" not in model and n.startswith(model + ":"):
                return True
        return False
    except Exception:
        return False


# ── config bundle constants & helpers ─────────────────────────────────────────

_PORTABLE_KEYS = (
    "MIRACH_LOCALE",
    "MIRACH_WHISPER_MODEL",
    "MIRACH_WHISPER_LANG",
    "MIRACH_BACKEND",
    "MIRACH_NATIVE_MODEL",
    "MIRACH_OPENCODE_SERVE_PROVIDER_ID",
    "MIRACH_OPENCODE_SERVE_MODEL_ID",
)

_MACHINE_KEYS = (
    "MIRACH_HOTKEY",
    "MIRACH_VOICE",
    "MIRACH_MIC",
    "MIRACH_OPENCODE_BIN",
    "MIRACH_NATIVE_BASE_URL",
    "MIRACH_WHISPER_DEVICE",
    "MIRACH_WHISPER_COMPUTE",
)

# Overridable in tests to avoid writing to the real ~/.config/opencode/.
_OPENCODE_HOME: Path | None = None


def _get_opencode_home() -> Path:
    return _OPENCODE_HOME if _OPENCODE_HOME is not None else Path.home()


def _ask(prompt: str, default: str = "", yes: bool = False) -> str:
    """Prompt for text; return default immediately in non-interactive / --yes mode."""
    if yes or not sys.stdin.isatty():
        return default
    hint = f" [{default}]" if default else ""
    try:
        val = input(f"  {prompt}{hint}: ").strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def _safe_tar_member(name: str) -> bool:
    """Return True if the archive member path has no '..' and is not absolute."""
    if name.startswith("/"):
        return False
    return ".." not in Path(name).parts


def _install_skills_to_opencode(skills_src: Path) -> None:
    """Copy skills_src/* to ~/.config/opencode/skills/ and update opencode.json."""
    home = _get_opencode_home()
    opencode_skills_dir = home / ".config" / "opencode" / "skills"
    opencode_config = home / ".config" / "opencode" / "opencode.json"

    opencode_skills_dir.mkdir(parents=True, exist_ok=True)
    for src_file in sorted(skills_src.rglob("*")):
        if src_file.is_file():
            rel = src_file.relative_to(skills_src)
            dest = opencode_skills_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)

    opencode_config.parent.mkdir(parents=True, exist_ok=True)
    if opencode_config.exists():
        try:
            cfg = json.loads(opencode_config.read_text())
        except (json.JSONDecodeError, OSError):
            cfg = {}
    else:
        cfg = {"$schema": "https://opencode.ai/config.json"}

    cfg.setdefault("skills", {}).setdefault("paths", [])
    sp = str(opencode_skills_dir)
    if sp not in cfg["skills"]["paths"]:
        cfg["skills"]["paths"].append(sp)

    opencode_config.write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"  Skills installed → {opencode_skills_dir}")


# ── subcommand handlers ────────────────────────────────────────────────────────


def cmd_lang(args: argparse.Namespace) -> int:
    env_path = Path(args.env_file) if args.env_file else ENV_PATH

    if args.code is None:
        env = read_env(env_path)
        current = env.get("MIRACH_LOCALE") or config.WHISPER_LANG
        print(f"Daemon language: {current}")
        print(f"Available: {', '.join(LANGUAGE_PACKS)}")
        if sys.stdin.isatty() and not args.yes:
            raw = input("Enter language code to change (or Enter to cancel): ").strip()
            if raw not in LANGUAGE_PACKS:
                return 0
            args.code = raw
        else:
            return 0

    code = args.code
    if code not in LANGUAGE_PACKS:
        print(
            f"Unknown language '{code}'. Available: {', '.join(LANGUAGE_PACKS)}",
            file=sys.stderr,
        )
        return 1

    pack = pack_for(code)
    set_env_vars(
        {
            "MIRACH_LOCALE": pack["locale"],
            "MIRACH_WHISPER_MODEL": pack["whisper_model"],
            "MIRACH_WHISPER_LANG": pack["whisper_lang"],
        },
        env_path,
    )
    print(f"Language → {code}  (locale={pack['locale']}, model={pack['whisper_model']})")

    # ── voice mismatch check ───────────────────────────────────────────────────
    env = read_env(env_path)
    current_voice = env.get("MIRACH_VOICE") or config.VOICE_NAME
    voice_lang = _voice_lang(current_voice)

    if voice_lang and voice_lang != code:
        print(f"Voice '{current_voice}' appears to be for '{voice_lang}', not '{code}'.")
        do_change = False
        if args.yes:
            do_change = True
        elif sys.stdin.isatty():
            do_change = _confirm(f"Switch to recommended voice {pack['voice']}?", default=True)
        else:
            print(
                f"Run interactively or use --yes to switch to {pack['voice']}.",
                file=sys.stderr,
            )

        if do_change:
            _download_voice(pack["voice"], pack["voice_url"], config.VOICES_DIR)
            set_env_vars({"MIRACH_VOICE": pack["voice"]}, env_path)
            print(f"Voice → {pack['voice']}")
        elif sys.stdin.isatty() and not args.yes:
            print(f"Voice left as '{current_voice}' — may not match language '{code}'.")

    # ── restart daemon ─────────────────────────────────────────────────────────
    if _systemd_unit_active():
        print("Restarting daemon...", end=" ", flush=True)
        rc = _run_systemctl("restart")
        print("done" if rc == 0 else f"failed (exit {rc})")
    else:
        print("Restart the daemon: mirach start  or  ./run_daemon.sh")

    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    if shutil.which("journalctl") and _systemd_unit_exists():
        cmd = ["journalctl", "--user", "-u", "mirach"]
        if args.n:
            cmd += ["-n", str(args.n)]
        if not args.no_follow:
            cmd.append("-f")
        with contextlib.suppress(FileNotFoundError):
            os.execvp(cmd[0], cmd)
        # fall through to log-file fallback

    log_path = config.LOG_PATH
    if not log_path.exists():
        print(f"No log file at {log_path}.", file=sys.stderr)
        print("Start the daemon: mirach start  or  ./run_daemon.sh", file=sys.stderr)
        return 1

    cmd = ["tail"]
    if not args.no_follow:
        cmd.append("-f")
    if args.n:
        cmd += ["-n", str(args.n)]
    cmd.append(str(log_path))
    try:
        os.execvp(cmd[0], cmd)
    except OSError as e:
        print(f"Cannot run tail: {e}", file=sys.stderr)
        return 1
    return 0  # unreachable when execvp succeeds


def _systemctl_cmd(action: str) -> int:
    if not _systemctl_available():
        if action == "start":
            print("systemd not available. Start the daemon with: ./run_daemon.sh")
        elif action == "status":
            sock = Path(config.SOCKET_PATH)
            state = "running" if sock.exists() else "stopped (socket not found)"
            print(f"mirach: {state}")
        else:
            print(f"systemd not available — cannot {action} the daemon.")
        return 0
    return _run_systemctl(action)


def cmd_start(args: argparse.Namespace) -> int:
    return _systemctl_cmd("start")


def cmd_stop(args: argparse.Namespace) -> int:
    return _systemctl_cmd("stop")


def cmd_restart(args: argparse.Namespace) -> int:
    return _systemctl_cmd("restart")


def cmd_status(args: argparse.Namespace) -> int:
    return _systemctl_cmd("status")


def cmd_run(args: argparse.Namespace) -> int:
    """Launch run_daemon.sh in the foreground (non-systemd environments)."""
    run_sh = config.BASE_DIR / "run_daemon.sh"
    if not run_sh.exists():
        print(f"run_daemon.sh not found at {run_sh}", file=sys.stderr)
        return 1
    try:
        os.execv(str(run_sh), [str(run_sh)])
    except OSError as e:
        print(f"Cannot launch {run_sh}: {e}", file=sys.stderr)
        return 1
    return 0  # unreachable when execv succeeds


def cmd_backend(args: argparse.Namespace) -> int:
    env_path = Path(args.env_file) if args.env_file else ENV_PATH

    if args.backend_name is None:
        env = read_env(env_path)
        current = env.get("MIRACH_BACKEND") or config.BACKEND
        print(f"Backend: {current}")
        if current == "opencode_serve":
            bin_val = env.get("MIRACH_OPENCODE_BIN") or config.OPENCODE_BIN
            provider = (
                env.get("MIRACH_OPENCODE_SERVE_PROVIDER_ID") or config.OPENCODE_SERVE_PROVIDER_ID
            )
            model = env.get("MIRACH_OPENCODE_SERVE_MODEL_ID") or config.OPENCODE_SERVE_MODEL_ID
            if bin_val != "opencode":
                print(f"  Binary: {bin_val}")
            if provider:
                print(f"  Provider: {provider}")
            if model:
                print(f"  Model: {model}")
        elif current == "native":
            base_url = env.get("MIRACH_NATIVE_BASE_URL") or config.NATIVE_BASE_URL
            model = env.get("MIRACH_NATIVE_MODEL") or config.NATIVE_MODEL
            print(f"  Ollama URL: {base_url}")
            print(f"  Model: {model}")
        return 0

    name = args.backend_name
    if name not in {"opencode", "native"}:
        print(f"Unknown backend '{name}'. Choose: opencode or native", file=sys.stderr)
        return 1

    if name == "opencode":
        env = read_env(env_path)
        bin_path = getattr(args, "bin", None) or env.get("MIRACH_OPENCODE_BIN") or "opencode"
        ok_flag, resolved = _validate_opencode_bin(bin_path)
        if not ok_flag:
            print(f"Error: {resolved}", file=sys.stderr)
            print("Install opencode: curl -fsSL https://opencode.ai/install | sh", file=sys.stderr)
            print(
                "Or pass a custom path: mirach backend opencode --bin /path/to/opencode",
                file=sys.stderr,
            )
            return 1

        updates: dict[str, str] = {"MIRACH_BACKEND": "opencode_serve"}
        if getattr(args, "bin", None) and args.bin != "opencode":
            updates["MIRACH_OPENCODE_BIN"] = args.bin
        if args.model:
            provider, _, model_id = args.model.partition("/")
            if model_id:
                updates["MIRACH_OPENCODE_SERVE_PROVIDER_ID"] = provider
                updates["MIRACH_OPENCODE_SERVE_MODEL_ID"] = model_id
            else:
                updates["MIRACH_OPENCODE_SERVE_MODEL_ID"] = provider
        set_env_vars(updates, env_path)
        print(f"Backend → opencode_serve  (binary: {resolved})")

    else:  # native
        env = read_env(env_path)
        base_url = (
            getattr(args, "base_url", None)
            or env.get("MIRACH_NATIVE_BASE_URL")
            or config.NATIVE_BASE_URL
        )
        ok_flag, err_msg = _validate_ollama(base_url)
        if not ok_flag:
            print(f"Error: {err_msg}", file=sys.stderr)
            print("Is Ollama running? Start with: ollama serve", file=sys.stderr)
            return 1

        if args.model and not _ollama_has_model(base_url, args.model):
            do_pull = False
            if args.yes:
                do_pull = True
            elif sys.stdin.isatty():
                do_pull = _confirm(
                    f"Model '{args.model}' not found locally. Pull it now?", default=True
                )
            else:
                print(
                    f"Warning: model '{args.model}' not in ollama list. "
                    f"Run: ollama pull {args.model}",
                    file=sys.stderr,
                )
            if do_pull:
                print(f"Pulling {args.model}...")
                subprocess.run(["ollama", "pull", args.model], check=False)

        updates = {"MIRACH_BACKEND": "native"}
        if getattr(args, "base_url", None):
            updates["MIRACH_NATIVE_BASE_URL"] = base_url
        if args.model:
            updates["MIRACH_NATIVE_MODEL"] = args.model
        set_env_vars(updates, env_path)
        print(f"Backend → native  (Ollama: {base_url})")

    if _systemd_unit_active():
        print("Restarting daemon...", end=" ", flush=True)
        rc = _run_systemctl("restart")
        print("done" if rc == 0 else f"failed (exit {rc})")
    else:
        print("Restart the daemon: mirach start  or  ./run_daemon.sh")

    return 0


POLICY_MODES = {"safe", "dangerous"}


def _policy_label(path: Path) -> str:
    """Best-effort label for a policy file based on its filename."""
    name = path.name
    if name == "policy.dangerous.yaml":
        return "dangerous"
    if name == "policy.yaml":
        return "safe"
    return "custom"


def cmd_policy(args: argparse.Namespace) -> int:
    env_path = Path(args.env_file) if args.env_file else ENV_PATH
    safe_path = config.BASE_DIR / "policy.yaml"
    dangerous_path = config.BASE_DIR / "policy.dangerous.yaml"
    dangerous_template = config.BASE_DIR / "policy.dangerous.example.yaml"

    if args.mode is None:
        env = read_env(env_path)
        active = env.get("MIRACH_NATIVE_POLICY") or str(config.NATIVE_POLICY_PATH)
        print(f"Policy: {_policy_label(Path(active))}")
        print(f"  File: {active}")
        return 0

    mode = args.mode
    if mode not in POLICY_MODES:
        print(f"Unknown policy mode '{mode}'. Choose: safe or dangerous", file=sys.stderr)
        return 1

    if mode == "safe":
        set_env_vars({"MIRACH_NATIVE_POLICY": str(safe_path)}, env_path)
        print(f"Policy → safe  ({safe_path})")
    else:  # dangerous
        print("⚠  DANGEROUS policy: Mirach will run almost anything WITHOUT asking.")
        print("   Still blocked: sudo/privilege escalation, disk format/wipe, shutdown,")
        print("   and writes to system + credential directories.")
        if (
            not args.yes
            and sys.stdin.isatty()
            and not _confirm("Enable the dangerous policy?", default=False)
        ):
            print("Cancelled — policy unchanged.")
            return 0
        if not dangerous_path.exists():
            if not dangerous_template.exists():
                print(f"Template not found: {dangerous_template}", file=sys.stderr)
                return 1
            shutil.copyfile(dangerous_template, dangerous_path)
            print(f"Created {dangerous_path} (edit it to tune the profile).")
        set_env_vars({"MIRACH_NATIVE_POLICY": str(dangerous_path)}, env_path)
        print(f"Policy → dangerous  ({dangerous_path})")

    if _systemd_unit_active():
        print("Restarting daemon...", end=" ", flush=True)
        rc = _run_systemctl("restart")
        print("done" if rc == 0 else f"failed (exit {rc})")
    else:
        print("Restart the daemon: mirach start  or  ./run_daemon.sh")

    return 0


def cmd_config_export(args: argparse.Namespace) -> int:
    try:
        import yaml
    except ImportError:
        print("PyYAML is required for export. Run: pip install pyyaml", file=sys.stderr)
        return 1

    env_path = Path(args.env_file) if args.env_file else ENV_PATH
    base_dir = config.BASE_DIR

    out_path = (
        Path(args.out)
        if args.out
        else Path.cwd() / f"mirach-config-{datetime.date.today().isoformat()}.tar.gz"
    )

    # Build manifest
    env = read_env(env_path)
    portable = {k: env[k] for k in _PORTABLE_KEYS if k in env}

    policy_path_str = env.get("MIRACH_NATIVE_POLICY", "")
    portable["policy_mode"] = _policy_label(Path(policy_path_str)) if policy_path_str else "safe"

    manifest: dict = {
        "manifest_version": 1,
        "exported_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "portable": portable,
        "machine_specific_reference": {k: env[k] for k in _MACHINE_KEYS if k in env},
    }
    manifest_bytes = yaml.dump(manifest, default_flow_style=False, allow_unicode=True).encode()

    with tarfile.open(out_path, "w:gz") as tf:
        # manifest.yaml (in-memory — not a real file)
        info = tarfile.TarInfo("manifest.yaml")
        info.size = len(manifest_bytes)
        tf.addfile(info, io.BytesIO(manifest_bytes))

        # system_prompt.md
        sp = base_dir / "system_prompt.md"
        if sp.exists():
            tf.add(sp, arcname="system_prompt.md")

        # skills/ (files only, recursive)
        skills_dir = base_dir / "skills"
        if skills_dir.is_dir():
            for item in sorted(skills_dir.rglob("*")):
                if item.is_file():
                    tf.add(item, arcname=str(item.relative_to(base_dir)))

        # user_scripts/ (files only, skip .gitkeep)
        us_dir = base_dir / "user_scripts"
        if us_dir.is_dir():
            for item in sorted(us_dir.rglob("*")):
                if item.is_file() and item.name != ".gitkeep":
                    tf.add(item, arcname=str(item.relative_to(base_dir)))

        # policy files
        for fname in (
            "policy.yaml",
            "policy.dangerous.yaml",
            "policy.dangerous.example.yaml",
        ):
            p = base_dir / fname
            if p.exists():
                tf.add(p, arcname=fname)

    with tarfile.open(out_path, "r:gz") as tf:
        count = len(tf.getmembers())
    print(f"Bundle created: {out_path}  ({count} files)")
    return 0


def cmd_config_import(args: argparse.Namespace) -> int:
    try:
        import yaml
    except ImportError:
        print("PyYAML is required for import. Run: pip install pyyaml", file=sys.stderr)
        return 1

    env_path = Path(args.env_file) if args.env_file else ENV_PATH
    base_dir = config.BASE_DIR
    bundle = Path(args.bundle)
    yes: bool = getattr(args, "yes", False)
    # Non-interactive (--yes or no tty) means "yes to everything": overwrite + use
    # previous values for the machine-specific wizard.
    non_interactive = yes or not sys.stdin.isatty()

    if not bundle.exists():
        print(f"Bundle not found: {bundle}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="mirach-import-") as tmpdir:
        tmp = Path(tmpdir)
        try:
            with tarfile.open(bundle, "r:gz") as tf:
                # Path-traversal guard — check every member before extracting.
                for member in tf.getmembers():
                    if not _safe_tar_member(member.name):
                        print(
                            f"Rejecting bundle: unsafe path in archive: {member.name!r}",
                            file=sys.stderr,
                        )
                        return 1
                tf.extractall(tmp)
        except tarfile.TarError as e:
            print(f"Cannot open bundle: {e}", file=sys.stderr)
            return 1

        # Load and validate manifest
        mfile = tmp / "manifest.yaml"
        if not mfile.exists():
            print("Bundle is missing manifest.yaml", file=sys.stderr)
            return 1
        try:
            manifest = yaml.safe_load(mfile.read_text()) or {}
        except yaml.YAMLError as e:
            print(f"Cannot parse manifest.yaml: {e}", file=sys.stderr)
            return 1
        if manifest.get("manifest_version") != 1:
            print(
                f"Unsupported manifest version: {manifest.get('manifest_version')}",
                file=sys.stderr,
            )
            return 1

        # ── Collect every (src, dest, label) restore the bundle would perform ──
        restores: list[tuple[Path, Path, str]] = []

        for fname in (
            "system_prompt.md",
            "policy.yaml",
            "policy.dangerous.yaml",
            "policy.dangerous.example.yaml",
        ):
            src = tmp / fname
            if src.exists():
                restores.append((src, base_dir / fname, fname))

        skills_tmp = tmp / "skills"
        skills_dest = base_dir / "skills"
        if skills_tmp.is_dir():
            for src_file in sorted(skills_tmp.rglob("*")):
                if src_file.is_file():
                    rel = src_file.relative_to(skills_tmp)
                    restores.append((src_file, skills_dest / rel, f"skills/{rel}"))

        us_tmp = tmp / "user_scripts"
        if us_tmp.is_dir():
            us_dest = base_dir / "user_scripts"
            for src_file in sorted(us_tmp.rglob("*")):
                if src_file.is_file():
                    rel = src_file.relative_to(us_tmp)
                    restores.append((src_file, us_dest / rel, f"user_scripts/{rel}"))

        # ── One overwrite decision for the whole import ───────────────────────
        existing = [label for _src, dest, label in restores if dest.exists()]
        overwrite = True
        if existing and not non_interactive:
            print(f"{len(existing)} file(s) already exist and would be overwritten:")
            for label in existing:
                print(f"  - {label}")
            overwrite = _confirm("Overwrite them?", default=False)

        for src, dest, label in restores:
            if dest.exists() and not overwrite:
                print(f"  Kept (not overwritten): {label}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            print(f"  Restored: {label}")

        if skills_tmp.is_dir() and skills_dest.is_dir():
            _install_skills_to_opencode(skills_dest)

        # ── Apply portable prefs ──────────────────────────────────────────────
        portable = dict(manifest.get("portable", {}))
        # policy_mode is NOT auto-applied: importing always lands on the SAFE
        # policy regardless of the source machine. A dangerous source only
        # prints a hint on how to re-enable it explicitly.
        source_policy_mode = portable.pop("policy_mode", None)
        if portable:
            set_env_vars(portable, env_path)
            print(f"  Portable settings applied → {env_path}")

        # Always land on the safe policy.
        set_env_vars({"MIRACH_NATIVE_POLICY": str(base_dir / "policy.yaml")}, env_path)
        print("  Policy → safe")
        if source_policy_mode == "dangerous":
            print("  Note: source machine used the DANGEROUS policy. Imported as SAFE.")
            print("        Run `mirach policy dangerous` to re-enable it on this machine.")

        # ── Machine-specific wizard ───────────────────────────────────────────
        machine_ref = manifest.get("machine_specific_reference", {})
        if machine_ref:
            print("\nMachine-specific settings (press Enter to keep the previous value):")
            updates: dict[str, str] = {}
            for key, hint in machine_ref.items():
                val = _ask(key, str(hint), yes)
                if val:
                    updates[key] = val
            if updates:
                set_env_vars(updates, env_path)

    print("\nImport complete.")
    if _systemd_unit_active():
        print("Restarting daemon...", end=" ", flush=True)
        rc = _run_systemctl("restart")
        print("done" if rc == 0 else f"failed (exit {rc})")
    else:
        print("Restart the daemon: mirach start  or  ./run_daemon.sh")
    return 0


# ── entry point ────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mirach",
        description="Mirach voice assistant — CLI for everyday operations.",
    )
    # Hidden global option: lets tests point to a temp mirach.env.
    parser.add_argument("--env-file", metavar="PATH", default=None, help=argparse.SUPPRESS)

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # lang ────────────────────────────────────────────────────────────────────
    p_lang = sub.add_parser("lang", help="Show or change the daemon language (es/en).")
    p_lang.add_argument("code", nargs="?", metavar="CODE", help="Language code: es or en.")
    p_lang.add_argument(
        "--yes", "-y", action="store_true", help="Accept all prompts non-interactively."
    )
    p_lang.set_defaults(func=cmd_lang)

    # logs ────────────────────────────────────────────────────────────────────
    p_logs = sub.add_parser("logs", help="Follow the daemon log (journalctl or tail fallback).")
    p_logs.add_argument(
        "--no-follow", action="store_true", help="Print recent lines; do not follow."
    )
    p_logs.add_argument("-n", type=int, metavar="N", help="Number of lines to show.")
    p_logs.set_defaults(func=cmd_logs)

    # start / stop / restart / status ─────────────────────────────────────────
    for _name, _help, _func in [
        ("start", "Start the daemon via systemd (background, logs to journal).", cmd_start),
        ("stop", "Stop the daemon via systemd.", cmd_stop),
        ("restart", "Restart the daemon via systemd.", cmd_restart),
        ("status", "Show daemon status via systemd.", cmd_status),
    ]:
        _p = sub.add_parser(_name, help=_help)
        _p.set_defaults(func=_func)

    # run (foreground launcher — no systemd) ──────────────────────────────────
    p_run = sub.add_parser(
        "run",
        help="Run the daemon in the foreground (no systemd; blocks terminal; use for debugging or non-systemd setups).",
    )
    p_run.set_defaults(func=cmd_run)

    # backend ─────────────────────────────────────────────────────────────────
    p_backend = sub.add_parser(
        "backend",
        help="Show or change the LLM backend (opencode|native).",
    )
    p_backend.add_argument(
        "backend_name",
        nargs="?",
        metavar="BACKEND",
        help="Backend to activate: opencode or native. Omit to show current.",
    )
    p_backend.add_argument(
        "--model",
        metavar="MODEL",
        help=(
            "For opencode: provider/model_id (e.g. opencode/deepseek-v4-flash-free). "
            "For native: Ollama model name (e.g. qwen3:14b)."
        ),
    )
    p_backend.add_argument(
        "--base-url",
        metavar="URL",
        dest="base_url",
        help="Native backend: Ollama base URL (default: http://localhost:11434).",
    )
    p_backend.add_argument(
        "--bin",
        metavar="PATH",
        help="OpenCode backend: path to opencode binary (default: opencode from PATH).",
    )
    p_backend.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Accept all prompts non-interactively (e.g. auto-pull missing Ollama model).",
    )
    p_backend.set_defaults(func=cmd_backend)

    # policy ──────────────────────────────────────────────────────────────────
    p_policy = sub.add_parser(
        "policy",
        help="Show or switch the permission policy (safe|dangerous).",
    )
    p_policy.add_argument(
        "mode",
        nargs="?",
        metavar="MODE",
        help="Policy to activate: safe or dangerous. Omit to show current.",
    )
    p_policy.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip the confirmation prompt when enabling the dangerous policy.",
    )
    p_policy.set_defaults(func=cmd_policy)

    # config ──────────────────────────────────────────────────────────────────
    p_config = sub.add_parser(
        "config",
        help="Export or import the Mirach configuration bundle.",
    )
    csub = p_config.add_subparsers(dest="config_cmd", metavar="<action>")

    p_export = csub.add_parser("export", help="Pack config into a portable .tar.gz bundle.")
    p_export.add_argument(
        "--out",
        metavar="PATH",
        help="Output path (default: mirach-config-<date>.tar.gz in current directory).",
    )
    p_export.add_argument("--yes", "-y", action="store_true", help="Non-interactive.")
    p_export.set_defaults(func=cmd_config_export)

    p_import = csub.add_parser(
        "import",
        help="Restore config from a bundle: applies portable prefs, then wizard for machine-specific values.",
    )
    p_import.add_argument("bundle", metavar="BUNDLE", help="Path to the .tar.gz bundle.")
    p_import.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Non-interactive: overwrite existing files and keep the bundle's machine-specific hints.",
    )
    p_import.set_defaults(func=cmd_config_import)

    p_config.set_defaults(func=lambda a: p_config.print_help() or 0)

    # help ────────────────────────────────────────────────────────────────────
    p_help = sub.add_parser("help", help="Show this help message.")
    p_help.set_defaults(func=lambda args: parser.print_help() or 0)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
