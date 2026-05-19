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

# ── constants ─────────────────────────────────────────────────────────────────

REPO_DIR = Path(__file__).parent.resolve()
VENV_DIR = REPO_DIR / "venv"
VOICES_DIR = REPO_DIR / "voices"

PIPER_VOICES: list[tuple[str, str, str]] = [
    # (display, filename, hf_url)
    (
        "Español — es_MX-ald-medium (recomendado)",
        "es_MX-ald-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/ald/medium/es_MX-ald-medium.onnx",
    ),
    (
        "English — en_US-lessac-medium (recommended)",
        "en_US-lessac-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
    ),
    (
        "English — en_US-lessac-low (smaller/faster)",
        "en_US-lessac-low.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/en_US-lessac-low.onnx",
    ),
]

LANGUAGES = [
    ("Español latinoamericano", "es"),
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
            raw = input(f"  Opción [{default}]: ").strip()
            if not raw:
                return default
            choice = int(raw)
            if 1 <= choice <= len(options):
                return choice
            warn(f"Ingresa un número entre 1 y {len(options)}")
        except ValueError:
            warn("Ingresa un número válido")
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
    print(f"  Descargando {dest.name}…", end=" ", flush=True)
    try:
        urllib.request.urlretrieve(url, dest)
        print(green("✓"))
    except Exception as e:
        print(red("✗"))
        raise RuntimeError(f"Download failed: {e}") from e


# ── steps ─────────────────────────────────────────────────────────────────────


def step_detect(total: int) -> dict:
    banner(1, total, "Detectando tu sistema…")

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
        f"GPU:     {gpu_name + ' — CUDA disponible' if gpu == 'cuda' else 'No GPU — Whisper usará CPU (más lento)'}"
    )
    ok(f"Usuario: {username}")
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
    banner(2, total, "Configuración del asistente")

    name = ask("Nombre del asistente", "Mirach")

    lang_idx = menu(
        "Idioma de respuesta:",
        [f"{lang} ({code})" for lang, code in LANGUAGES],
        default=1,
    )
    language_name, language_code = LANGUAGES[lang_idx - 1]

    return {
        "assistant_name": name,
        "language": language_name,
        "language_code": language_code,
    }


def step_obsidian(total: int) -> dict:
    banner(3, total, "Notas (Obsidian)")

    default_vault = str(Path.home() / "ObsidianVault")
    vault = ask("¿Ruta del vault de Obsidian?", default_vault)
    vault_path = Path(vault).expanduser()

    if vault_path.exists():
        ok(f"Vault encontrado: {vault_path}")
    else:
        warn(f"El directorio {vault_path} no existe — se creará cuando Obsidian lo use.")

    # Check / offer Obsidian install
    has_obsidian = (
        shutil.which("obsidian") is not None
        or subprocess.run(["flatpak", "list", "--app"], capture_output=True, text=True, check=False)
        .stdout.lower()
        .find("obsidian")
        != -1
    )

    if has_obsidian:
        ok("Obsidian detectado")
    else:
        warn("Obsidian no encontrado.")
        if shutil.which("flatpak") and confirm("¿Instalar Obsidian vía Flatpak?", default=True):
            run("flatpak", "install", "-y", "flathub", "md.obsidian.Obsidian")
            ok("Obsidian instalado")
        else:
            warn("Instala Obsidian manualmente desde https://obsidian.md cuando quieras.")

    return {"obsidian_vault": str(vault_path)}


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
    ok(f"Bind Hyprland escrito: {target}")

    if fallback:
        warn("Añade esta línea a ~/.config/hypr/hyprland.conf para activarlo:")
        warn(f"    source = {target}")
        return

    if shutil.which("hyprctl"):
        result = run("hyprctl", "reload", capture=True, check=False)
        if result.returncode == 0:
            ok(f"Hyprland recargado — pulsa {display} para hablar")
        else:
            warn("hyprctl reload falló — reinicia Hyprland o recarga manualmente.")


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
    ok(f"Bind {wm} escrito: {target}")

    if used_fallback:
        warn(f"Añade esta línea a ~/.config/{wm}/config para activarlo:")
        warn(f"    include {target}")
        return

    if shutil.which(reload_cmd[0]):
        result = run(*reload_cmd, capture=True, check=False)
        if result.returncode == 0:
            ok(f"{wm} recargado — pulsa {display} para hablar")
        else:
            warn(f"{reload_cmd[0]} reload falló — recarga manualmente.")


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
        warn("gsettings no encontrado — no puedo configurar GNOME automáticamente.")
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

    ok(f"GNOME custom shortcut registrado — pulsa {display} para hablar")
    print('    (visible en Settings > Keyboard > Custom Shortcuts → "Mirach")')


# ── manual instructions for unsupported envs ──────────────────────────────────


def _print_manual(env: str, mods: str, key: str, display: str, trigger_cmd: str) -> None:
    """Print clear instructions for envs we don't auto-configure."""
    print()
    print(f"  {bold('Configura el hotkey manualmente:')}")
    print(f"    Atajo:    {display}")
    print(f"    Comando:  {trigger_cmd}")
    print()

    if env == "plasma":
        print("  KDE Plasma:")
        print(
            "    System Settings → Shortcuts → Custom Shortcuts → Edit → New → Global Shortcut → Command/URL"
        )
        print(f"    Nombre: Mirach   Comando: {trigger_cmd}   Trigger: {display}")
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
        print("  Tu entorno no fue detectado. Configura el hotkey en los settings del DE,")
        print("  o usa sxhkd / xbindkeys en X11 con una línea como:")
        print(f"    {display.lower().replace('+', ' + ')}  →  {trigger_cmd}")


# ── hotkey step ───────────────────────────────────────────────────────────────


def step_hotkey(total: int) -> dict:
    banner(4, total, "Atajo de teclado")

    print("  Mirach se activa con un atajo global. Configura el tuyo (default: Alt+Z).")
    print("  Modificadores: ALT, SUPER, CTRL, SHIFT (combina con espacios o '+').")

    while True:
        mods_raw = ask("Modificador(es)", "ALT")
        mods = _normalize_mods(mods_raw)
        if mods:
            break
        warn("Modificador inválido. Usa ALT, SUPER, CTRL o SHIFT.")

    key = ask("Tecla", "Z").strip().upper() or "Z"
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
        if confirm(f"Detecté {name}. ¿Configurar el hotkey automáticamente?", default=True):
            fn(mods, key, display, trigger_cmd)
        else:
            _print_manual(env, mods, key, display, trigger_cmd)
    else:
        if env != "other":
            ok(f"Detecté: {env}")
        _print_manual(env, mods, key, display, trigger_cmd)

    return {"hotkey_display": display, "hotkey_mods": mods, "hotkey_key": key}


def step_voice(total: int) -> tuple[str, str]:
    banner(5, total, "Voz Piper")

    VOICES_DIR.mkdir(exist_ok=True)

    options = [label for label, _, _ in PIPER_VOICES] + ["Especificar URL manualmente"]
    idx = menu("Elige una voz:", options, default=1)

    if idx <= len(PIPER_VOICES):
        label, voice_name, voice_url = PIPER_VOICES[idx - 1]
    else:
        voice_url = ask("URL del archivo .onnx en Hugging Face")
        voice_name = voice_url.split("/")[-1]

    dest_onnx = VOICES_DIR / voice_name
    dest_json = VOICES_DIR / (voice_name + ".json")

    if dest_onnx.exists() and dest_json.exists():
        ok(f"Voz ya descargada: {voice_name}")
    else:
        download(voice_url, dest_onnx)
        download(voice_url + ".json", dest_json)
        ok(f"Voz lista: {voice_name}")

    return voice_name, voice_url


def step_venv(detected: dict, voice_name: str, total: int) -> None:
    banner(6, total, "Entorno Python")

    # Create venv if needed
    if not VENV_DIR.exists():
        run(sys.executable, "-m", "venv", str(VENV_DIR))
        ok("venv creado")
    else:
        ok("venv ya existe")

    pybin = VENV_DIR / "bin" / "python3"
    pipbin = [str(pybin), "-m", "pip"]

    run(*pipbin, "install", "--upgrade", "pip", "-q")
    ok("pip actualizado")

    run(*pipbin, "install", "-e", str(REPO_DIR), "-q")
    ok("Dependencias instaladas")

    if detected["gpu"] == "cuda":
        run(*pipbin, "install", "-q", "nvidia-cublas-cu12>=12.0", "nvidia-cudnn-cu12>=9.0")
        ok("CUDA libs instaladas (cublas + cudnn)")
    else:
        ok("Sin GPU — omitiendo CUDA libs")


def step_opencode(total: int) -> None:
    banner(7, total, "OpenCode CLI (LLM backend)")

    if shutil.which("opencode"):
        try:
            ver = run("opencode", "--version", capture=True, check=False).stdout.strip()
        except Exception:
            ver = "?"
        ok(f"OpenCode ya instalado ({ver})")
        return

    if confirm("¿Instalar OpenCode CLI?", default=True):
        if shutil.which("curl"):
            run("bash", "-c", f"curl -fsSL {OPENCODE_INSTALL_URL} | bash")
            ok("OpenCode instalado — ejecuta 'opencode auth' para configurar")
        else:
            warn("curl no encontrado. Instala OpenCode manualmente:")
            warn(f"  {OPENCODE_INSTALL_URL}")
    else:
        warn("Instala OpenCode manualmente antes de iniciar el daemon.")


def step_prompt(tvars: dict, total: int) -> None:
    banner(8, total, "System prompt")

    dest = REPO_DIR / "system_prompt.md"
    if dest.exists():
        ok("system_prompt.md ya existe — no se sobreescribe")
        return

    template_path = REPO_DIR / "system_prompt.example.md"
    if not template_path.exists():
        warn("system_prompt.example.md no encontrado — omitiendo")
        return

    content = template_path.read_text()
    for key, value in tvars.items():
        content = content.replace("{{" + key + "}}", str(value))

    dest.write_text(content)
    ok(f"system_prompt.md generado (edítalo en: {dest})")


def step_service(tvars: dict, total: int) -> None:
    banner(9, total, "Servicio systemd")

    if platform.system() != "Linux" or not shutil.which("systemctl"):
        warn("systemd no disponible — el daemon deberá iniciarse manualmente con ./run_daemon.sh")
        return

    service_dest = Path.home() / ".config" / "systemd" / "user" / "mirach.service"
    service_dest.parent.mkdir(parents=True, exist_ok=True)

    if not service_dest.exists():
        template = REPO_DIR / "mirach.service.example"
        content = template.read_text()

        # Patch ExecStart to this repo's run_daemon.sh
        content = content.replace("%h/mirach/run_daemon.sh", str(REPO_DIR / "run_daemon.sh"))

        # Activate locale/language
        lang_code = tvars.get("language_code", "en")
        content = content.replace(
            "# Environment=MIRACH_LOCALE=es", f"Environment=MIRACH_LOCALE={lang_code}"
        )

        # Activate hotkey label (cosmetic — shown in notifications)
        hotkey = tvars.get("hotkey_display", "Alt+Z")
        content = content.replace(
            "# Environment=MIRACH_HOTKEY=Alt+Z", f"Environment=MIRACH_HOTKEY={hotkey}"
        )

        # Activate voice
        voice_name = tvars.get("voice_name", "")
        if voice_name:
            content = content.replace(
                "# Environment=MIRACH_VOICE=en_US-lessac-low.onnx",
                f"Environment=MIRACH_VOICE={voice_name}",
            )

        # Activate CPU mode if no GPU
        if tvars.get("gpu") == "cpu":
            content = content.replace(
                "# Environment=MIRACH_WHISPER_DEVICE=cpu",
                "Environment=MIRACH_WHISPER_DEVICE=cpu",
            )
            content = content.replace(
                "# Environment=MIRACH_WHISPER_COMPUTE=int8",
                "Environment=MIRACH_WHISPER_COMPUTE=int8",
            )

        service_dest.write_text(content)
        ok(f"mirach.service instalado → {service_dest}")
    else:
        ok("mirach.service ya existe — no se sobreescribe")

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
        ok("Daemon reiniciado")
    else:
        run("systemctl", "--user", "start", "mirach.service")
        ok("Daemon iniciado")


# ── summary ───────────────────────────────────────────────────────────────────


def print_summary(tvars: dict) -> None:
    print()
    print("═" * 50)
    print(green("✓  Instalación completa."))
    print()
    name = tvars.get("assistant_name", "Mirach")
    hotkey = tvars.get("hotkey_display", "Alt+Z")
    print(bold("Próximos pasos:"))
    print(f"  • Habla con {name}:       pulsa {hotkey}")
    print(f"  • Editar prompt:          $EDITOR {REPO_DIR / 'system_prompt.md'}")
    print("  • Ver logs en vivo:       journalctl --user -u mirach -f")
    print(f"  • Ver última conv.:       {REPO_DIR / 'view_conversation.sh'}")
    if not shutil.which("opencode"):
        print(yellow("\n  ⚠  Recuerda instalar OpenCode y ejecutar 'opencode auth'."))
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

    TOTAL = 9

    print()
    print("╔══════════════════════════════════╗")
    print("║     Mirach — Setup Wizard        ║")
    print("╚══════════════════════════════════╝")

    try:
        tvars: dict = {}
        tvars.update(step_detect(TOTAL))
        tvars.update(step_config(tvars, TOTAL))
        tvars.update(step_obsidian(TOTAL))
        tvars.update(step_hotkey(TOTAL))
        voice_name, _ = step_voice(TOTAL)
        tvars["voice_name"] = voice_name
        step_venv(tvars, voice_name, TOTAL)
        step_opencode(TOTAL)
        step_prompt(tvars, TOTAL)
        step_service(tvars, TOTAL)
        print_summary(tvars)
    except KeyboardInterrupt:
        print(f"\n{yellow('Instalación cancelada.')}")
        sys.exit(1)
    except Exception as e:
        err(f"Error durante la instalación: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
