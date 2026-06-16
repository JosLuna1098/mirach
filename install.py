#!/usr/bin/env python3
"""
Mirach — interactive setup wizard.

Run from the repo root:
    python3 install.py            # interactive
    python3 install.py --yes      # non-interactive, accept all defaults
    python3 install.py --help

One-liner (Linux / macOS):
    git clone https://github.com/JosLuna1098/mirach ~/mirach && python3 ~/mirach/install.py
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from mirach import config, langpack
from mirach.cli import _validate_ollama, _validate_opencode_bin

# ── constants ─────────────────────────────────────────────────────────────────

REPO_DIR = Path(__file__).parent.resolve()
VENV_DIR = REPO_DIR / "venv"
VOICES_DIR = REPO_DIR / "voices"
SKILLS_SRC = REPO_DIR / "skills"
USER_SCRIPTS_DIR = REPO_DIR / "user_scripts"
OPENCODE_SKILLS_DIR = Path.home() / ".config" / "opencode" / "skills"
OPENCODE_CONFIG = Path.home() / ".config" / "opencode" / "opencode.json"

PIPER_VOICES: list[tuple[str, str, str, str]] = [
    # (display, filename, hf_url, lang)
    (
        "Spanish — es_MX-ald-medium (recommended)",
        "es_MX-ald-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/ald/medium/es_MX-ald-medium.onnx",
        "es",
    ),
    (
        "English — en_US-lessac-medium (recommended)",
        "en_US-lessac-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "en",
    ),
    (
        "English — en_US-lessac-low (smaller/faster)",
        "en_US-lessac-low.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/en_US-lessac-low.onnx",
        "en",
    ),
]

LANGUAGES = [
    ("Latin American Spanish", "es"),
    ("English", "en"),
]

HOTKEY_MODIFIERS = {"ALT", "SUPER", "CTRL", "SHIFT"}

OPENCODE_INSTALL_URL = "https://opencode.ai/install"

# ── ANSI colours (disabled if not a tty) ─────────────────────────────────────

_COLOUR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOUR else text


def green(t: str) -> str:
    return _c("1;32", t)


def yellow(t: str) -> str:
    return _c("1;33", t)


def blue(t: str) -> str:
    return _c("1;34", t)


def red(t: str) -> str:
    return _c("1;31", t)


def bold(t: str) -> str:
    return _c("1", t)


# ── helpers ───────────────────────────────────────────────────────────────────

ASSUME_YES = False


def ok(msg: str) -> None:
    print(f"  {green('✓')} {msg}")


def warn(msg: str) -> None:
    print(f"  {yellow('!')} {msg}", file=sys.stderr)


def err(msg: str) -> None:
    print(f"  {red('✗')} {msg}", file=sys.stderr)


def banner(step: int, total: int, title: str) -> None:
    print(f"\n{blue(f'[{step}/{total}]')} {bold(title)}")


def ask(prompt: str, default: str = "") -> str:
    """Prompt the user for input with an optional default."""
    if ASSUME_YES:
        print(f"  {prompt} [{default}]: {default}")
        return default
    hint = f" [{default}]" if default else ""
    try:
        val = input(f"  {prompt}{hint}: ").strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def menu(prompt: str, options: list[str], default: int = 1) -> int:
    """Show a numbered menu and return the 1-based selected index."""
    if ASSUME_YES:
        print(f"  {prompt} → {options[default - 1]} (default)")
        return default
    print(f"  {prompt}")
    for i, opt in enumerate(options, 1):
        marker = green("▶") if i == default else " "
        print(f"    {marker} ({i}) {opt}")
    while True:
        try:
            raw = input(f"  Option [{default}]: ").strip()
            if not raw:
                return default
            choice = int(raw)
            if 1 <= choice <= len(options):
                return choice
            warn(f"Enter a number between 1 and {len(options)}")
        except ValueError:
            warn("Enter a valid number")
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)


def confirm(prompt: str, default: bool = True) -> bool:
    """Yes/no prompt."""
    if ASSUME_YES:
        return default
    hint = "[Y/n]" if default else "[y/N]"
    try:
        raw = input(f"  {prompt} {hint}: ").strip().lower()
        if not raw:
            return default
        return raw in ("y", "yes", "s", "si", "sí", "o", "oui")
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def run(*cmd: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    kwargs: dict = {"check": check}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    return subprocess.run(list(cmd), **kwargs)


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {dest.name}…", end=" ", flush=True)
    try:
        urllib.request.urlretrieve(url, dest)
        print(green("✓"))
    except Exception as e:
        print(red("✗"))
        raise RuntimeError(f"Download failed: {e}") from e


# ── steps ─────────────────────────────────────────────────────────────────────


def step_detect(total: int) -> dict:
    banner(1, total, "Detecting your system…")

    uname = platform.uname()
    os_desc = f"{uname.system} ({uname.machine})"
    if uname.system == "Linux":
        try:
            import distro  # type: ignore

            os_desc = f"Linux ({distro.name(pretty=True)})"
        except ImportError:
            with contextlib.suppress(Exception):
                os_desc = (
                    "Linux ("
                    + Path("/etc/os-release").read_text().split('PRETTY_NAME="')[1].split('"')[0]
                    + ")"
                )

    username = getpass.getuser()
    shell = os.environ.get("SHELL", shutil.which("bash") or "bash")
    python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    gpu = "cpu"
    gpu_name = "none"
    if shutil.which("nvidia-smi"):
        try:
            result = run(
                "nvidia-smi",
                "--query-gpu=name",
                "--format=csv,noheader,nounits",
                capture=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                gpu = "cuda"
                gpu_name = result.stdout.strip().split("\n")[0]
        except Exception:
            pass

    ok(f"OS:      {os_desc}")
    ok(
        f"GPU:     {gpu_name + ' — CUDA available' if gpu == 'cuda' else 'No GPU — Whisper will use CPU (slower)'}"
    )
    ok(f"User:    {username}")
    ok(f"Shell:   {shell}")
    ok(f"Python:  {python_ver}")

    return {
        "os_desc": os_desc,
        "username": username,
        "shell": shell,
        "gpu": gpu,
        "gpu_name": gpu_name,
        "mirach_dir": str(REPO_DIR),
    }


def step_config(detected: dict, total: int) -> dict:
    banner(2, total, "Assistant configuration")

    name = ask("Assistant name", "Mirach")

    lang_idx = menu(
        "Response language:",
        [f"{lang} ({code})" for lang, code in LANGUAGES],
        default=1,
    )
    language_name, language_code = LANGUAGES[lang_idx - 1]

    # Derive STT model / Whisper language / locale from the shared language pack
    # so the daemon language, voice and transcription stay consistent.
    pack = langpack.pack_for(language_code)

    return {
        "assistant_name": name,
        "language": language_name,
        "language_code": language_code,
        "whisper_model": pack["whisper_model"],
        "whisper_lang": pack["whisper_lang"],
        "locale": pack["locale"],
    }


def step_backend(total: int) -> str:
    """Ask which LLM backend to use; soft-validates; returns 'opencode_serve' or 'native'."""
    banner(3, total, "LLM backend")

    idx = menu(
        "Which LLM backend should Mirach use?",
        [
            "opencode (cloud AI — requires opencode CLI and an account)",
            "native  (local Ollama — private, no account needed)",
        ],
        default=1,
    )

    if idx == 1:
        ok_flag, _ = _validate_opencode_bin("opencode")
        if ok_flag:
            ok("opencode found in PATH")
        else:
            warn("opencode not found in PATH — the next step will offer to install it")
        return "opencode_serve"
    else:
        base_url = config.NATIVE_BASE_URL
        ok_flag, msg = _validate_ollama(base_url)
        if ok_flag:
            ok(f"Ollama reachable at {base_url}")
        else:
            warn(f"Ollama not reachable at {base_url}")
            warn("Start Ollama before launching the daemon: ollama serve")
        return "native"


def step_obsidian(total: int) -> dict:
    banner(4, total, "Notes (Obsidian)")

    default_vault = str(Path.home() / "ObsidianVault")
    vault = ask("Obsidian vault path?", default_vault)
    vault_path = Path(vault).expanduser()

    if vault_path.exists():
        ok(f"Vault found: {vault_path}")
        _init_vault_files(vault_path)
    else:
        warn(f"Directory {vault_path} does not exist — will be created when Obsidian uses it.")

    # Check / offer Obsidian install
    has_obsidian = (
        shutil.which("obsidian") is not None
        or subprocess.run(["flatpak", "list", "--app"], capture_output=True, text=True, check=False)
        .stdout.lower()
        .find("obsidian")
        != -1
    )

    if has_obsidian:
        ok("Obsidian detected")
    else:
        warn("Obsidian not found.")
        if shutil.which("flatpak") and confirm("Install Obsidian via Flatpak?", default=True):
            run("flatpak", "install", "-y", "flathub", "md.obsidian.Obsidian")
            ok("Obsidian installed")
        else:
            warn("Install Obsidian manually from https://obsidian.md when ready.")

    return {"obsidian_vault": str(vault_path)}


VAULT_FILES = {
    "conocimiento.md": "# Knowledge\n\nPersistent instructions and rules for the assistant.\n",
    "recordatorios.md": "# Reminders\n\n- [ ] Pending tasks will appear here.\n",
    "preferencias.md": "# Preferences\n\nUser preferences and habits.\n",
    "proyectos.md": "# Projects\n\nActive projects and their status.\n",
}


def _init_vault_files(vault_path: Path) -> None:
    """Create standard vault memory files if they don't exist."""
    created = 0
    for filename, content in VAULT_FILES.items():
        target = vault_path / filename
        if not target.exists():
            target.write_text(content)
            created += 1
    if created:
        ok(f"{created} memory files created in vault")
    else:
        ok("Vault memory files already exist")


def _normalize_mods(raw: str) -> str:
    """'alt+shift' / 'alt shift' / 'ALT, SHIFT' → 'ALT SHIFT'. Drops unknown tokens."""
    tokens = raw.upper().replace("+", " ").replace(",", " ").split()
    valid = [t for t in tokens if t in HOTKEY_MODIFIERS]
    seen: set[str] = set()
    out: list[str] = []
    for tok in valid:
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return " ".join(out)


def _detect_compositor() -> str:
    """Best-effort detection of the active compositor / DE for hotkey wiring."""
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "hyprland"
    if os.environ.get("SWAYSOCK"):
        return "sway"
    if os.environ.get("I3SOCK"):
        return "i3"

    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    for token in ("hyprland", "sway", "i3", "gnome", "kde", "plasma", "xfce", "mate", "cinnamon"):
        if token in desktop:
            return "plasma" if token == "kde" else token

    # Fallback: at least detect Hyprland binary even if env var was lost (e.g. sudo)
    if shutil.which("hyprctl"):
        return "hyprland"
    return "other"


# ── per-compositor writers ────────────────────────────────────────────────────


def _bind_hyprland(mods: str, key: str, display: str, trigger_cmd: str) -> None:
    """Write a Hyprland bind snippet. Tries common include dirs first."""
    hypr_dir = Path.home() / ".config" / "hypr"
    candidates = [
        hypr_dir / "custom" / "mirach.conf",  # Omarchy / dots-hyprland convention
        hypr_dir / "conf.d" / "mirach.conf",  # some Hyprland rices
    ]
    target = next((c for c in candidates if c.parent.is_dir()), None)
    fallback = target is None
    if target is None:
        target = hypr_dir / "mirach.conf"
        target.parent.mkdir(parents=True, exist_ok=True)

    target.write_text(
        "# Mirach hotkey — generated by install.py. Safe to edit or delete.\n"
        f"bind = {mods}, {key}, exec, {trigger_cmd}\n"
    )
    ok(f"Hyprland bind written: {target}")

    if fallback:
        warn("Add this line to ~/.config/hypr/hyprland.conf to activate:")
        warn(f"    source = {target}")
        return

    if shutil.which("hyprctl"):
        result = run("hyprctl", "reload", capture=True, check=False)
        if result.returncode == 0:
            ok(f"Hyprland reloaded — press {display} to talk")
        else:
            warn("hyprctl reload failed — restart Hyprland or reload manually.")


def _sway_i3_modifiers(mods: str) -> str:
    """'ALT SHIFT' → 'Mod1+Shift' (sway/i3 syntax)."""
    mod_map = {"ALT": "Mod1", "SUPER": "Mod4", "CTRL": "Ctrl", "SHIFT": "Shift"}
    return "+".join(mod_map[m] for m in mods.split() if m in mod_map)


def _write_wm_include(wm: str, snippet: str, display: str, reload_cmd: list[str]) -> None:
    """Shared logic for sway/i3 — write a snippet to <wm>/config.d/ or fall back."""
    wm_dir = Path.home() / ".config" / wm
    confd = wm_dir / "config.d" / "mirach.conf"
    fallback_target = wm_dir / "mirach.conf"

    if confd.parent.is_dir():
        target = confd
        used_fallback = False
    else:
        target = fallback_target
        target.parent.mkdir(parents=True, exist_ok=True)
        used_fallback = True

    target.write_text(f"# Mirach hotkey — generated by install.py.\n{snippet}\n")
    ok(f"{wm} bind written: {target}")

    if used_fallback:
        warn(f"Add this line to ~/.config/{wm}/config to activate:")
        warn(f"    include {target}")
        return

    if shutil.which(reload_cmd[0]):
        result = run(*reload_cmd, capture=True, check=False)
        if result.returncode == 0:
            ok(f"{wm} reloaded — press {display} to talk")
        else:
            warn(f"{reload_cmd[0]} reload failed — reload manually.")


def _bind_sway(mods: str, key: str, display: str, trigger_cmd: str) -> None:
    sway_mods = _sway_i3_modifiers(mods)
    snippet = f"bindsym {sway_mods}+{key.lower()} exec {trigger_cmd}"
    _write_wm_include("sway", snippet, display, ["swaymsg", "reload"])


def _bind_i3(mods: str, key: str, display: str, trigger_cmd: str) -> None:
    i3_mods = _sway_i3_modifiers(mods)
    snippet = f"bindsym {i3_mods}+{key.lower()} exec {trigger_cmd}"
    _write_wm_include("i3", snippet, display, ["i3-msg", "reload"])


def _gnome_accelerator(mods: str, key: str) -> str:
    """'ALT SHIFT' + 'Z' → '<Alt><Shift>z' (GNOME format)."""
    mod_map = {"ALT": "<Alt>", "SUPER": "<Super>", "CTRL": "<Primary>", "SHIFT": "<Shift>"}
    prefix = "".join(mod_map[m] for m in mods.split() if m in mod_map)
    return f"{prefix}{key.lower()}"


def _bind_gnome(mods: str, key: str, display: str, trigger_cmd: str) -> None:
    """Register a GNOME custom keybinding via gsettings (idempotent)."""
    if not shutil.which("gsettings"):
        warn("gsettings not found — cannot configure GNOME automatically.")
        return

    schema = "org.gnome.settings-daemon.plugins.media-keys"
    key_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/mirach/"
    custom_schema = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"

    # 1) Read existing list, add ours if missing.
    current = run(
        "gsettings", "get", schema, "custom-keybindings", capture=True, check=False
    ).stdout.strip()
    paths: list[str] = []
    if current and current not in ("@as []", "[]"):
        # gsettings prints Python-list-like syntax with single quotes
        try:
            import ast

            paths = list(ast.literal_eval(current))
        except (SyntaxError, ValueError):
            paths = []
    if key_path not in paths:
        paths.append(key_path)
    new_list = "[" + ", ".join(f"'{p}'" for p in paths) + "]"
    run("gsettings", "set", schema, "custom-keybindings", new_list, check=False)

    # 2) Set name / command / binding for our path.
    accel = _gnome_accelerator(mods, key)
    run("gsettings", "set", f"{custom_schema}:{key_path}", "name", "Mirach", check=False)
    run("gsettings", "set", f"{custom_schema}:{key_path}", "command", trigger_cmd, check=False)
    run("gsettings", "set", f"{custom_schema}:{key_path}", "binding", accel, check=False)

    ok(f"GNOME custom shortcut registered — press {display} to talk")
    print('    (visible in Settings > Keyboard > Custom Shortcuts → "Mirach")')


# ── manual instructions for unsupported envs ──────────────────────────────────


def _print_manual(env: str, mods: str, key: str, display: str, trigger_cmd: str) -> None:
    """Print clear instructions for envs we don't auto-configure."""
    print()
    print(f"  {bold('Configure the hotkey manually:')}")
    print(f"    Shortcut: {display}")
    print(f"    Command:  {trigger_cmd}")
    print()

    if env == "plasma":
        print("  KDE Plasma:")
        print(
            "    System Settings → Shortcuts → Custom Shortcuts → Edit → New → Global Shortcut → Command/URL"
        )
        print(f"    Name: Mirach   Command: {trigger_cmd}   Trigger: {display}")
    elif env == "xfce":
        print("  XFCE:")
        print("    Settings → Keyboard → Application Shortcuts → Add")
        print(f"    Command: {trigger_cmd}   Shortcut: {display}")
    elif env == "mate":
        print("  MATE:")
        print("    System → Preferences → Hardware → Keyboard Shortcuts → Add")
    elif env == "cinnamon":
        print("  Cinnamon:")
        print("    System Settings → Keyboard → Shortcuts → Custom Shortcuts → Add custom shortcut")
    else:
        print("  Your environment was not detected. Configure the hotkey in DE settings,")
        print("  or use sxhkd / xbindkeys on X11 with a line like:")
        print(f"    {display.lower().replace('+', ' + ')}  →  {trigger_cmd}")


# ── hotkey step ───────────────────────────────────────────────────────────────


def step_hotkey(total: int) -> dict:
    banner(14, total, "Keyboard shortcut")

    print("  Mirach is activated with a global shortcut. Configure yours (default: Alt+Z).")
    print("  Modifiers: ALT, SUPER, CTRL, SHIFT (combine with spaces or '+').")

    while True:
        mods_raw = ask("Modifier(s)", "ALT")
        mods = _normalize_mods(mods_raw)
        if mods:
            break
        warn("Invalid modifier. Use ALT, SUPER, CTRL or SHIFT.")

    key = ask("Key", "Z").strip().upper() or "Z"
    display = "+".join([m.capitalize() for m in mods.split()] + [key])
    trigger_cmd = f"python3 {REPO_DIR / 'trigger.py'}"

    ok(f"Hotkey: {display}")

    env = _detect_compositor()
    handlers = {
        "hyprland": ("Hyprland", _bind_hyprland),
        "sway": ("Sway", _bind_sway),
        "i3": ("i3", _bind_i3),
        "gnome": ("GNOME", _bind_gnome),
    }

    if env in handlers:
        name, fn = handlers[env]
        if confirm(f"Detected {name}. Configure hotkey automatically?", default=True):
            fn(mods, key, display, trigger_cmd)
        else:
            _print_manual(env, mods, key, display, trigger_cmd)
    else:
        if env != "other":
            ok(f"Detected: {env}")
        _print_manual(env, mods, key, display, trigger_cmd)

    return {"hotkey_display": display, "hotkey_mods": mods, "hotkey_key": key}


def step_voice(language_code: str, total: int) -> tuple[str, str]:
    banner(7, total, "Piper voice")

    VOICES_DIR.mkdir(exist_ok=True)

    # Show only voices for the chosen language; fall back to all if none match.
    voices = [v for v in PIPER_VOICES if v[3] == language_code] or list(PIPER_VOICES)

    # Default to the language pack's recommended voice when it's in the list.
    recommended = langpack.pack_for(language_code)["voice"]
    default_idx = next((i for i, v in enumerate(voices, 1) if v[1] == recommended), 1)

    options = [v[0] for v in voices] + ["Specify URL manually"]
    idx = menu("Choose a voice:", options, default=default_idx)

    if idx <= len(voices):
        _label, voice_name, voice_url, _lang = voices[idx - 1]
    else:
        voice_url = ask("URL of the .onnx file on Hugging Face")
        voice_name = voice_url.split("/")[-1]

    dest_onnx = VOICES_DIR / voice_name
    dest_json = VOICES_DIR / (voice_name + ".json")

    if dest_onnx.exists() and dest_json.exists():
        ok(f"Voice already downloaded: {voice_name}")
    else:
        download(voice_url, dest_onnx)
        download(voice_url + ".json", dest_json)
        ok(f"Voice ready: {voice_name}")

    return voice_name, voice_url


def step_venv(detected: dict, voice_name: str, total: int) -> None:
    banner(8, total, "Python environment")

    # Create venv if needed
    if not VENV_DIR.exists():
        run(sys.executable, "-m", "venv", str(VENV_DIR))
        ok("venv created")
    else:
        ok("venv already exists")

    pybin = VENV_DIR / "bin" / "python3"
    pipbin = [str(pybin), "-m", "pip"]

    run(*pipbin, "install", "--upgrade", "pip", "-q")
    ok("pip updated")

    run(*pipbin, "install", "-e", str(REPO_DIR), "-q")
    ok("Dependencies installed")

    if detected["gpu"] == "cuda":
        run(*pipbin, "install", "-q", "nvidia-cublas-cu12>=12.0", "nvidia-cudnn-cu12>=9.0")
        ok("CUDA libs installed (cublas + cudnn)")
    else:
        ok("No GPU — skipping CUDA libs")


def _list_input_devices() -> list[str] | None:
    """List input-device names via the venv's sounddevice. None if unavailable."""
    pybin = VENV_DIR / "bin" / "python3"
    if not pybin.exists():
        return None

    code = (
        "import sounddevice as sd\n"
        "for d in sd.query_devices():\n"
        "    if d['max_input_channels'] > 0:\n"
        "        print(d['name'])\n"
    )
    res = run(str(pybin), "-c", code, capture=True, check=False)
    if res.returncode != 0:
        return None

    devices: list[str] = []
    seen: set[str] = set()
    for line in res.stdout.splitlines():
        name = line.strip()
        if name and name not in seen:
            seen.add(name)
            devices.append(name)
    return devices


def step_mic(total: int) -> dict:
    banner(9, total, "Microphone")

    devices = _list_input_devices()
    if devices is None:
        warn("Could not list input devices (sounddevice unavailable) — using system default")
        return {"mic_name": ""}
    if not devices:
        ok("No input devices found — using system default")
        return {"mic_name": ""}

    # "System default" is first and the default choice (stored as empty string).
    options = ["System default device"] + devices
    idx = menu("Which microphone should Mirach use?", options, default=1)
    if idx == 1:
        ok("Using system default input device")
        return {"mic_name": ""}

    # The full device name is itself a valid case-insensitive substring for audio.py.
    mic_name = devices[idx - 2]
    ok(f"Microphone: {mic_name}")
    return {"mic_name": mic_name}


def step_opencode(total: int) -> None:
    banner(10, total, "OpenCode CLI (LLM backend)")

    if shutil.which("opencode"):
        try:
            ver = run("opencode", "--version", capture=True, check=False).stdout.strip()
        except Exception:
            ver = "?"
        ok(f"OpenCode already installed ({ver})")
        return

    if confirm("Install OpenCode CLI?", default=True):
        if shutil.which("curl"):
            run("bash", "-c", f"curl -fsSL {OPENCODE_INSTALL_URL} | bash")
            ok("OpenCode installed — run 'opencode auth' to configure")
        else:
            warn("curl not found. Install OpenCode manually:")
            warn(f"  {OPENCODE_INSTALL_URL}")
    else:
        warn("Install OpenCode manually before starting the daemon.")


def step_prompt(tvars: dict, total: int) -> None:
    banner(12, total, "System prompt")

    dest = REPO_DIR / "system_prompt.md"
    if dest.exists():
        ok("system_prompt.md already exists — not overwritten")
        return

    template_path = REPO_DIR / "system_prompt.example.md"
    if not template_path.exists():
        warn("system_prompt.example.md not found — skipping")
        return

    content = template_path.read_text()
    for key, value in tvars.items():
        content = content.replace("{{" + key + "}}", str(value))

    dest.write_text(content)
    ok(f"system_prompt.md generated (edit at: {dest})")


def step_service(tvars: dict, total: int) -> None:
    banner(15, total, "systemd service")

    if platform.system() != "Linux" or not shutil.which("systemctl"):
        warn("systemd not available — start daemon manually with ./run_daemon.sh")
        return

    service_dest = Path.home() / ".config" / "systemd" / "user" / "mirach.service"
    service_dest.parent.mkdir(parents=True, exist_ok=True)

    if not service_dest.exists():
        template = REPO_DIR / "mirach.service.example"
        content = template.read_text()

        # Patch ExecStart to this repo's run_daemon.sh
        content = content.replace("%h/mirach/run_daemon.sh", str(REPO_DIR / "run_daemon.sh"))

        # Pin MIRACH_BASE_DIR to this repo (structural — never goes in mirach.env).
        content = content.replace(
            "# Environment=MIRACH_BASE_DIR=%h/mirach",
            f"Environment=MIRACH_BASE_DIR={REPO_DIR}",
        )

        # Point EnvironmentFile to this repo's mirach.env
        content = content.replace(
            "EnvironmentFile=-%h/mirach/mirach.env",
            f"EnvironmentFile=-{REPO_DIR}/mirach.env",
        )

        service_dest.write_text(content)
        ok(f"mirach.service installed → {service_dest}")
    else:
        ok("mirach.service already exists — not overwritten")

    # Write mirach.env with installer-chosen values (idempotent — never overwrites).
    env_dest = REPO_DIR / "mirach.env"
    if not env_dest.exists():
        lang_code = tvars.get("locale") or tvars.get("language_code", "en")
        hotkey = tvars.get("hotkey_display", "Alt+Z")
        whisper_model = tvars.get("whisper_model", "medium")
        whisper_lang = tvars.get("whisper_lang", "")
        voice_name = tvars.get("voice_name", "")
        mic_name = tvars.get("mic_name", "")
        gpu = tvars.get("gpu", "cuda")
        backend = tvars.get("backend", "opencode_serve")

        lines = [
            "# Generated by install.py — edit to tune your setup.",
            "# See mirach.env.example for all available options.\n",
            f"MIRACH_LOCALE={lang_code}",
            f"MIRACH_HOTKEY={hotkey}",
            f"MIRACH_BACKEND={backend}",
            f"MIRACH_WHISPER_MODEL={whisper_model}",
        ]
        if whisper_lang:
            lines.append(f"MIRACH_WHISPER_LANG={whisper_lang}")
        if voice_name:
            lines.append(f"MIRACH_VOICE={voice_name}")
        if mic_name:
            lines.append(f"MIRACH_MIC={mic_name}")
        if gpu == "cpu":
            lines.append("MIRACH_WHISPER_DEVICE=cpu")
            lines.append("MIRACH_WHISPER_COMPUTE=int8")

        env_dest.write_text("\n".join(lines) + "\n")
        ok(f"mirach.env written → {env_dest}")
    else:
        ok("mirach.env already exists — not overwritten")

    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "enable", "mirach.service", capture=True, check=False)

    already_running = (
        subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", "mirach.service"],
            check=False,
        ).returncode
        == 0
    )

    if already_running:
        run("systemctl", "--user", "restart", "mirach.service")
        ok("Daemon restarted")
    else:
        run("systemctl", "--user", "start", "mirach.service")
        ok("Daemon started")


# ── user context step ─────────────────────────────────────────────────────────


# Small offline lookup so a locale country code becomes a readable name. Anything
# not listed falls back to the raw code (still a useful, editable hint).
_COUNTRY_BY_CODE = {
    "US": "United States",
    "GB": "United Kingdom",
    "CA": "Canada",
    "AU": "Australia",
    "EC": "Ecuador",
    "MX": "Mexico",
    "ES": "Spain",
    "AR": "Argentina",
    "CO": "Colombia",
    "CL": "Chile",
    "PE": "Peru",
    "BR": "Brazil",
    "DE": "Germany",
    "FR": "France",
    "IT": "Italy",
    "PT": "Portugal",
}

KNOWN_TERMINALS = [
    "ghostty",
    "alacritty",
    "kitty",
    "foot",
    "wezterm",
    "konsole",
    "gnome-terminal",
    "xterm",
]

KNOWN_BROWSERS = [
    "firefox",
    "chromium",
    "google-chrome",
    "google-chrome-stable",
    "brave",
    "brave-browser",
    "vivaldi",
    "vivaldi-stable",
    "microsoft-edge",
]

_CHROMIUM_FAMILY = ("chrom", "brave", "vivaldi", "edge")


def _detect_country() -> str:
    """Best-effort, network-free country hint from locale env vars or timezone."""
    for var in ("LC_ALL", "LC_CTYPE", "LANG"):
        val = os.environ.get(var, "")
        if "_" in val:
            code = val.split("_", 1)[1][:2].upper()
            if code.isalpha():
                return _COUNTRY_BY_CODE.get(code, code)

    # Timezone city is a weak hint, but better than nothing for editing.
    with contextlib.suppress(OSError):
        tz = Path("/etc/timezone").read_text().strip()
        if "/" in tz:
            return tz.split("/")[-1].replace("_", " ")
    with contextlib.suppress(OSError):
        link = os.readlink("/etc/localtime")
        if "zoneinfo/" in link:
            tz = link.split("zoneinfo/")[-1]
            if "/" in tz:
                return tz.split("/")[-1].replace("_", " ")
    return ""


def _detect_cpu() -> str:
    """CPU model name via lscpu, falling back to /proc/cpuinfo."""
    if shutil.which("lscpu"):
        res = run("lscpu", capture=True, check=False)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if line.lower().startswith("model name:"):
                    return line.split(":", 1)[1].strip()
    with contextlib.suppress(OSError):
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    return ""


def _detect_ram() -> str:
    """Total RAM as a short string ('31Gi' / '32 GB'), best-effort."""
    if shutil.which("free"):
        res = run("free", "-h", capture=True, check=False)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if line.lower().startswith("mem:"):
                    fields = line.split()
                    if len(fields) >= 2:
                        return fields[1]
    with contextlib.suppress(OSError, ValueError, IndexError):
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                gb = int(line.split()[1]) / (1024 * 1024)
                return f"{gb:.0f} GB"
    return ""


def _detect_hardware(detected: dict) -> str:
    """Compose 'CPU, GPU, RAM' from autodetected parts (GPU reused from step_detect)."""
    parts: list[str] = []
    cpu = _detect_cpu()
    if cpu:
        parts.append(cpu)
    gpu = detected.get("gpu_name", "none")
    if gpu and gpu != "none":
        parts.append(gpu)
    ram = _detect_ram()
    if ram:
        parts.append(f"{ram} RAM")
    return ", ".join(parts)


def _detect_terminals() -> list[str]:
    """Terminals from KNOWN_TERMINALS that are actually installed."""
    return [t for t in KNOWN_TERMINALS if shutil.which(t)]


def _detect_browser() -> str:
    """The default/installed web browser binary, or '' if none found."""
    if shutil.which("xdg-settings"):
        res = run("xdg-settings", "get", "default-web-browser", capture=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            name = res.stdout.strip().removesuffix(".desktop")
            if shutil.which(name):
                return name
            base = name.split("-")[0].split("_")[0]
            if shutil.which(base):
                return base
    return next((b for b in KNOWN_BROWSERS if shutil.which(b)), "")


def _browser_app_cmd(browser: str, url: str) -> str:
    """Build a detached browser launch command for a web app URL."""
    if not browser:
        return f"setsid -f xdg-open {url}"
    if any(tag in browser for tag in _CHROMIUM_FAMILY):
        return f"setsid -f {browser} --app={url}"
    return f"setsid -f {browser} {url}"


def step_user_context(detected: dict, total: int) -> dict:
    banner(5, total, "User context")

    country = ask("Country", _detect_country())

    hardware = ask("Hardware specs (CPU, GPU, RAM)", _detect_hardware(detected))

    terminals = _detect_terminals() or KNOWN_TERMINALS
    current_term = os.environ.get("TERMINAL", "") or os.environ.get("TERM", "")
    term_default = next((i for i, t in enumerate(terminals, 1) if t in current_term), 1)
    terminal_idx = menu("Default terminal:", terminals, default=term_default)
    terminal = terminals[terminal_idx - 1]

    browser = _detect_browser()
    local_player = next(
        (
            p
            for p in ("clementine", "rhythmbox", "vlc", "audacious", "strawberry")
            if shutil.which(p)
        ),
        "vlc",
    )
    music_players = [
        ("YouTube Music (browser)", _browser_app_cmd(browser, "https://music.youtube.com")),
        ("Spotify (browser)", _browser_app_cmd(browser, "https://open.spotify.com")),
        ("Spotify (native)", "setsid -f spotify"),
        (f"Local files ({local_player})", f"setsid -f {local_player}"),
    ]
    music_idx = menu("Music player:", [p[0] for p in music_players], default=1)
    music_player_cmd = music_players[music_idx - 1][1]

    return {
        "country": country,
        "hardware_spec": hardware,
        "terminal": terminal,
        "music_player": music_player_cmd,
    }


# ── capability selection ──────────────────────────────────────────────────────

ALL_CAPABILITIES = [
    ("mirach-core", "Core identity & TTS rules", True),
    ("mirach-user-context", "User context (OS, hardware, country)", True),
    ("mirach-apps", "Opening applications", True),
    ("mirach-web-search", "Web search (DuckDuckGo)", True),
    ("mirach-system", "System management (Hyprland/Arch/systemd)", True),
    ("mirach-obsidian", "Obsidian notes (local memory)", True),
    ("mirach-hardware", "Hardware status (GPU, temps, OC)", True),
    ("mirach-system-monitor", "System monitoring (btop, htop, free)", True),
    ("mirach-media-control", "Media control (volume, playback)", True),
    ("mirach-git", "Git operations", True),
    ("mirach-network", "Network (WiFi, Bluetooth)", True),
    ("mirach-files", "File operations (find, open, search)", True),
    ("mirach-quick-actions", "Quick actions (lock, screenshot, power)", True),
]


def step_capabilities(total: int) -> list[str]:
    banner(6, total, "Select capabilities")

    print("  Which capabilities do you want to enable? (comma-separated numbers, or Enter for all)")
    print()

    for i, (name, desc, _) in enumerate(ALL_CAPABILITIES, 1):
        marker = green("▶")
        print(f"    {marker} ({i:2d}) {name:25s} — {desc}")

    print()

    if ASSUME_YES:
        ok("All capabilities enabled (--yes mode)")
        return [name for name, _, _ in ALL_CAPABILITIES]

    try:
        raw = input("  Capabilities [all]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)

    if not raw or raw.lower() in ("all", "todas", "todo"):
        return [name for name, _, _ in ALL_CAPABILITIES]

    selected: list[str] = []
    for token in raw.replace(",", " ").split():
        try:
            idx = int(token) - 1
            if 0 <= idx < len(ALL_CAPABILITIES):
                selected.append(ALL_CAPABILITIES[idx][0])
        except ValueError:
            pass

    if not selected:
        warn("No valid selection — enabling all")
        return [name for name, _, _ in ALL_CAPABILITIES]

    ok(f"{len(selected)} capabilities selected")
    return selected


# ── skills installation ──────────────────────────────────────────────────────


def _inject_variables(content: str, tvars: dict) -> str:
    """Replace {{variable}} placeholders with values from tvars."""
    for key, value in tvars.items():
        content = content.replace("{{" + key + "}}", str(value))
    return content


def _update_opencode_config(skills_path: str) -> None:
    """Add or update skills.paths in the user's opencode.json."""
    import json

    OPENCODE_CONFIG.parent.mkdir(parents=True, exist_ok=True)

    if OPENCODE_CONFIG.exists():
        try:
            cfg = json.loads(OPENCODE_CONFIG.read_text())
        except (json.JSONDecodeError, OSError):
            cfg = {}
    else:
        cfg = {"$schema": "https://opencode.ai/config.json"}

    if "skills" not in cfg:
        cfg["skills"] = {}
    if "paths" not in cfg["skills"]:
        cfg["skills"]["paths"] = []

    if skills_path not in cfg["skills"]["paths"]:
        cfg["skills"]["paths"].append(skills_path)

    OPENCODE_CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
    ok(f"opencode.json updated with skills path: {skills_path}")


def step_skills(tvars: dict, selected: list[str], total: int) -> None:
    banner(11, total, "Installing OpenCode skills")

    if not SKILLS_SRC.is_dir():
        warn("Skills directory not found — skipping")
        return

    OPENCODE_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    installed = 0
    for skill_name in selected:
        src = SKILLS_SRC / skill_name
        if not src.is_dir():
            warn(f"Skill {skill_name} not found in {SKILLS_SRC}")
            continue

        dest = OPENCODE_SKILLS_DIR / skill_name
        dest.mkdir(parents=True, exist_ok=True)

        skill_file = src / "SKILL.md"
        if not skill_file.exists():
            warn(f"SKILL.md not found in {src}")
            continue

        content = skill_file.read_text()
        content = _inject_variables(content, tvars)
        (dest / "SKILL.md").write_text(content)
        ok(f"Skill installed: {skill_name}")
        installed += 1

    if installed > 0:
        _update_opencode_config(str(OPENCODE_SKILLS_DIR))
        ok(f"{installed} skills installed to {OPENCODE_SKILLS_DIR}")
        print(f"\n  {blue('💡')} You can add your own skills in {SKILLS_SRC}/")
        print("     Drop a <name>/SKILL.md file there and re-run the installer to activate it.")
    else:
        warn("No skills installed")


# ── user scripts directory ────────────────────────────────────────────────────


def step_user_scripts(total: int) -> None:
    banner(13, total, "User scripts directory")

    USER_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    gitkeep = USER_SCRIPTS_DIR / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()

    # Ensure any existing scripts are executable
    for entry in sorted(USER_SCRIPTS_DIR.iterdir()):
        if entry.suffix in (".sh", ".py") and entry.name != ".gitkeep":
            mode = entry.stat().st_mode
            entry.chmod(mode | 0o111)

    ok(f"User scripts directory ready: {USER_SCRIPTS_DIR}")


# ── summary ───────────────────────────────────────────────────────────────────


def print_summary(tvars: dict) -> None:
    print()
    print("═" * 50)
    print(green("✓  Installation complete."))
    print()
    name = tvars.get("assistant_name", "Mirach")
    hotkey = tvars.get("hotkey_display", "Alt+Z")
    print(bold("Next steps:"))
    print(f"  • Talk to {name}:       press {hotkey}")
    print(f"  • Edit prompt:          $EDITOR {REPO_DIR / 'system_prompt.md'}")
    print(f"  • Installed skills:     {OPENCODE_SKILLS_DIR}/")
    print(f"  • User scripts:         {USER_SCRIPTS_DIR}/")
    print("  • Watch logs live:      journalctl --user -u mirach -f")
    if not shutil.which("opencode"):
        print(yellow("\n  ⚠  Remember to install OpenCode and run 'opencode auth'."))
    print()


# ── entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    global ASSUME_YES

    parser = argparse.ArgumentParser(description="Mirach setup wizard")
    parser.add_argument("--yes", "-y", action="store_true", help="Non-interactive, accept defaults")
    args = parser.parse_args()
    ASSUME_YES = args.yes

    if sys.version_info < (3, 11):  # noqa: UP036 — installer is the one Python that may be older
        err(f"Python 3.11+ required (got {sys.version})")
        sys.exit(1)

    TOTAL = 15

    print()
    print("╔══════════════════════════════════╗")
    print("║     Mirach — Setup Wizard        ║")
    print("╚══════════════════════════════════╝")

    try:
        tvars: dict = {}
        tvars.update(step_detect(TOTAL))
        tvars.update(step_config(tvars, TOTAL))
        tvars["backend"] = step_backend(TOTAL)
        tvars.update(step_obsidian(TOTAL))
        tvars.update(step_user_context(tvars, TOTAL))
        selected = step_capabilities(TOTAL)
        voice_name, _ = step_voice(tvars["language_code"], TOTAL)
        tvars["voice_name"] = voice_name
        step_venv(tvars, voice_name, TOTAL)
        tvars.update(step_mic(TOTAL))
        if tvars["backend"] != "native":
            step_opencode(TOTAL)
        step_skills(tvars, selected, TOTAL)
        step_prompt(tvars, TOTAL)
        step_user_scripts(TOTAL)
        tvars.update(step_hotkey(TOTAL))
        step_service(tvars, TOTAL)
        print_summary(tvars)
    except KeyboardInterrupt:
        print(f"\n{yellow('Installation cancelled.')}")
        sys.exit(1)
    except Exception as e:
        err(f"Error during installation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
