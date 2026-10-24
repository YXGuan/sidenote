"""Keep the authenticated loopback bridge running in the user's login session."""
from http.client import HTTPConnection, HTTPException
import json
import os
from pathlib import Path
import plistlib
import shutil
import socket
import subprocess
import sys

from .intelligence import codex_binary, codex_model
from .schedule import label_for as backup_label
from .store import atomic_write


def label_for(vault):
    return backup_label(vault) + ".bridge"


def agent_path(vault):
    return Path.home() / "Library/LaunchAgents" / (label_for(vault) + ".plist")


def agent_definition(vault):
    launcher = Path(__file__).resolve().parents[1] / "notes"
    paths = [str(Path(sys.executable).parent)]
    node = shutil.which("node")
    if node:
        paths.append(str(Path(node).parent))
    paths.extend(("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"))
    environment = {"PATH": ":".join(dict.fromkeys(paths)), "NOTES_CODEX_MODEL": codex_model()}
    codex = codex_binary()
    if codex:
        environment["NOTES_CODEX_BIN"] = codex
    return {
        "Label": label_for(vault),
        "ProgramArguments": [sys.executable, "-B", str(launcher), "--vault", str(vault.root), "serve"],
        "WorkingDirectory": str(launcher.parent),
        "EnvironmentVariables": environment,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "ProcessType": "Background",
        "Umask": 0o077,
        "StandardOutPath": str(vault.root / ".local/bridge.log"),
        "StandardErrorPath": str(vault.root / ".local/bridge-error.log"),
    }


def target(vault):
    return f"gui/{os.getuid()}/{label_for(vault)}"


def loaded(vault):
    return sys.platform == "darwin" and subprocess.run(
        ["/bin/launchctl", "print", target(vault)], capture_output=True,
    ).returncode == 0


def port_in_use():
    try:
        with socket.create_connection(("127.0.0.1", 8765), timeout=1):
            return True
    except OSError:
        return False


def healthy():
    connection = HTTPConnection("127.0.0.1", 8765, timeout=2)
    try:
        connection.request("GET", "/health")
        response = connection.getresponse()
        body = json.loads(response.read())
        return response.status == 200 and body.get("ok") is True and body.get("service") == "research-notes"
    except (OSError, ValueError, HTTPException):
        return False
    finally:
        connection.close()


def status(vault):
    managed = loaded(vault)
    return {"installed": agent_path(vault).exists(), "loaded": managed,
            "running": managed and healthy(), "url": "http://127.0.0.1:8765",
            "launch_agent": str(agent_path(vault))}


def install(vault):
    if sys.platform != "darwin":
        raise ValueError("The persistent bridge currently supports macOS; run notes serve elsewhere")
    if not vault.config().get("user"):
        raise ValueError("Initialize this vault first")
    managed = loaded(vault)
    if not managed and port_in_use():
        raise ValueError("Port 8765 is already in use. Stop the manually started notes serve process before installing the background service.")
    destination = agent_path(vault)
    # launchd can open the log files only after their parent directory exists.
    (vault.root / ".local").mkdir(parents=True, exist_ok=True)
    atomic_write(destination, plistlib.dumps(agent_definition(vault)))
    if managed:
        subprocess.run(["/bin/launchctl", "bootout", target(vault)], check=True, capture_output=True)
    result = subprocess.run(["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(destination)], capture_output=True)
    if result.returncode:
        raise RuntimeError("The bridge LaunchAgent was written but could not be loaded in this login session")
    return destination


def uninstall(vault):
    if sys.platform != "darwin":
        raise ValueError("Automatic bridge management currently supports macOS")
    if loaded(vault):
        subprocess.run(["/bin/launchctl", "bootout", target(vault)], check=True, capture_output=True)
    destination = agent_path(vault)
    if destination.exists():
        destination.unlink()
    return destination
