"""Repeatable local setup, with an inspect-only preflight and explicit user scope."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT = ROOT / "research-partner/vault"
TOOLS = ("git", "node", "make", "rsync")


def preflight():
    available = {name: shutil.which(name) is not None for name in TOOLS}
    version = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip() if available["node"] else ""
    match = re.match(r"v(\d+)", version)
    pip = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True).returncode == 0
    return {
        "python": sys.version.split()[0], "python_supported": sys.version_info >= (3, 10),
        "node": version or None, "node_supported": bool(match and int(match[1]) >= 22),
        "tools": available, "pip_available": pip,
        "ready": all(available.values()) and sys.version_info >= (3, 10) and bool(match and int(match[1]) >= 22) and pip,
    }


def username(vault, requested):
    config = vault / ".local/config.json"
    existing = json.loads(config.read_text()).get("user") if config.exists() else None
    user = requested or existing
    if user in ("YOUR_USERNAME", "YOUR_HYPOTHESIS_USERNAME", "MY_USERNAME"):
        raise ValueError("Replace the placeholder with your actual Hypothesis username.")
    if not isinstance(user, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", user):
        raise ValueError("Pass --user YOUR_HYPOTHESIS_USERNAME; no example account is selected automatically.")
    if existing and existing != user:
        raise ValueError("This vault belongs to a different user. Reuse that account or choose a new --vault directory.")
    return user


def dependencies_current():
    target = ROOT / "research-partner/.local-tools/python"
    installed = {dist.metadata["Name"].lower(): dist.version for dist in importlib.metadata.distributions(path=[str(target)])}
    required = [line.strip().split("==") for line in (ROOT / "research-partner/requirements.txt").read_text().splitlines() if line.strip() and not line.startswith("#")]
    return all(installed.get(name.lower()) == version for name, version in required)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report prerequisites without installing or changing anything")
    parser.add_argument("--user", help="Your Hypothesis username; existing vaults reuse their configured user")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT, help="Notes directory; default: research-partner/vault")
    parser.add_argument("--install-service", action="store_true", help="On macOS, start/update the per-user storage service and start it at login")
    args = parser.parse_args(argv)
    try:
        state = preflight()
        if args.check:
            print(json.dumps(state, indent=2))
            return 0 if state["ready"] else 1
        if not state["ready"]:
            print(json.dumps(state, indent=2))
            raise ValueError("Install Python 3.10+ with pip, Node.js 22+, Git, Make, and rsync, then retry. See docs/SETUP.md.")
        if args.install_service and sys.platform != "darwin":
            raise ValueError("--install-service uses macOS launchd. Elsewhere, omit it and run notes serve in a separate terminal.")
        vault = args.vault.expanduser().resolve()
        user = username(vault, args.user)  # Reject mismatches before any mutation.
        def run(command):
            subprocess.run(command, cwd=ROOT, check=True)
        if not dependencies_current():
            run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "--target", str(ROOT / "research-partner/.local-tools/python"), "-r", str(ROOT / "research-partner/requirements.txt")])
        run([sys.executable, "-B", "-c", "import sys; sys.path.insert(0, " + repr(str(ROOT / "research-partner")) + "); from research_notes.collections import tools; tools(); print('Local NLP ready')"])
        notes = [sys.executable, "-B", str(ROOT / "research-partner/notes"), "--vault", str(vault)]
        run(notes + ["init", "--user", user])
        run([sys.executable, str(ROOT / "hypothesis/build")])
        if args.install_service:
            run(notes + ["service", "--install"])
        run(notes + ["doctor", "--json"])
        print("\nBuild and vault setup complete. Browser installation/pairing still require verification.")
        print("Load unpacked: " + str(ROOT / "hypothesis/browser-extension/build"))
        print("Next: docs/SETUP.md#connect-chrome and docs/SETUP.md#verify-the-installation")
        if not args.install_service:
            print("Start the local backend in a separate terminal: " + shlex.join(notes + ["serve"]))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Setup stopped: {error}", file=sys.stderr)
        return 1
