"""A per-user macOS LaunchAgent for daily exports, never an LLM by default."""
import hashlib
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

from .store import atomic_write


def label_for(vault):
    return "local.research-notes." + hashlib.sha256(str(vault.root).encode()).hexdigest()[:10]


def agent_definition(vault, hour=3, minute=0, public_only=False, analyze=False):
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Use a valid hour and minute")
    launcher = Path(__file__).resolve().parents[1] / "notes"
    args = [sys.executable, "-B", str(launcher), "--vault", str(vault.root), "sync"]
    if public_only:
        args.append("--public-only")
    if analyze:
        args.append("--analyze")
    codex = os.environ.get("NOTES_CODEX_BIN") or shutil.which("codex")
    search_dirs = [str(Path(sys.executable).parent)]
    if codex:
        search_dirs.append(str(Path(codex).parent))
    search_dirs.extend(["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"])
    environment = {"PATH": ":".join(dict.fromkeys(search_dirs))}
    if codex:
        environment["NOTES_CODEX_BIN"] = str(codex)
    return {"Label": label_for(vault), "ProgramArguments": args, "EnvironmentVariables": environment, "WorkingDirectory": str(launcher.parent), "StartCalendarInterval": {"Hour": hour, "Minute": minute}, "RunAtLoad": True, "StandardOutPath": str(vault.root / ".local/daily.log"), "StandardErrorPath": str(vault.root / ".local/daily-error.log"), "ProcessType": "Background"}


def install(vault, **kwargs):
    if sys.platform != "darwin":
        raise ValueError("Automatic installation currently supports macOS; use cron or systemd elsewhere")
    if not kwargs.get("public_only") and not vault.token():
        raise ValueError("Configure a locally saved Hypothesis token before scheduling authenticated sync")
    definition = agent_definition(vault, **kwargs)
    destination = Path.home() / "Library/LaunchAgents" / (definition["Label"] + ".plist")
    atomic_write(destination, plistlib.dumps(definition))
    domain = f"gui/{os.getuid()}"
    subprocess.run(["/bin/launchctl", "bootout", domain + "/" + definition["Label"]], capture_output=True)
    result = subprocess.run(["/bin/launchctl", "bootstrap", domain, str(destination)], capture_output=True)
    if result.returncode:
        raise RuntimeError("LaunchAgent file was written, but launchctl could not load it in this login session")
    return destination


def uninstall(vault):
    label = label_for(vault)
    destination = Path.home() / "Library/LaunchAgents" / (label + ".plist")
    subprocess.run(["/bin/launchctl", "bootout", f"gui/{os.getuid()}/{label}"], capture_output=True)
    if destination.exists():
        destination.unlink()
    return destination
