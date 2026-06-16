"""mirach CLI — argparse subcommands for everyday daemon operations."""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import subprocess
import sys
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
