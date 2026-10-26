"""Local maintenance preferences, write-only credentials, and bridge-owned jobs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
import os
import re
import threading

from .hypothesis import sync
from .store import atomic_write, encoded, now, read_json

API_KEYS = ("OPENALEX_API_KEY", "S2_API_KEY", "ZOTERO_API_KEY")


def preferences(vault):
    return {"backup_enabled": False, "backup_time": "03:00",
            "backup_public_only": not bool(vault.token()), "enrichment_enabled": True} | vault.config().get("maintenance", {})


def settings(vault):
    return {"preferences": preferences(vault), "api_keys": {
        name: {"configured": bool(vault.secret(name)), "editable": not bool(os.environ.get(name))}
        for name in API_KEYS}}


def save_settings(vault, values, api_keys):
    if not isinstance(values, dict) or not isinstance(api_keys, dict):
        raise ValueError("Expected settings and API key objects")
    if set(values) - set(preferences(vault)) or set(api_keys) - set(API_KEYS):
        raise ValueError("Unsupported setting or API key")
    for name, value in values.items():
        if name == "backup_time":
            if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                raise ValueError("Choose a valid daily backup time")
        elif not isinstance(value, bool):
            raise ValueError("Settings switches must be true or false")
    for name, value in api_keys.items():
        if os.environ.get(name):
            raise ValueError("This API key is managed by the service environment")
        if value is not None and (not isinstance(value, str) or not value or len(value) > 4096 or any(c.isspace() for c in value) or not value.isprintable()):
            raise ValueError("Enter a valid API key without whitespace")
    with vault.lock():
        config = vault.config()
        config["maintenance"] = preferences(vault) | values
        if api_keys:
            lines = vault.env_file.read_text().splitlines() if vault.env_file.exists() else []
            for name, value in api_keys.items():
                lines = [line for line in lines if not re.match(r"\s*(?:export\s+)?" + name + r"\s*=", line)]
                if value is not None:
                    lines.append(name + "=" + json.dumps(value))
            atomic_write(vault.env_file, "\n".join(lines) + "\n")
            vault.env_file.chmod(0o600)
        atomic_write(vault.root / ".local/config.json", encoded(config))
    return settings(vault)


def backup_due(preferences, state, clock):
    """Catch up after sleep/restart; one successful backup per local calendar day."""
    if not preferences["backup_enabled"] or clock.strftime("%H:%M") < preferences["backup_time"]:
        return False
    for field, delay in (("completed", None), ("attempted", timedelta(hours=1))):
        if state.get(field):
            stamp = datetime.fromisoformat(state[field].replace("Z", "+00:00")).astimezone(clock.tzinfo)
            if delay is None and stamp.date() >= clock.date() or delay is not None and clock - stamp < delay:
                return False
    return True


class Maintenance:
    """Jobs keep running with Chrome closed while the local bridge is running."""
    def __init__(self, vault, *, sync_job=None, enrich_job=None, clock=None):
        from .scholarly import enrich_library
        self.vault = vault
        self.sync_job = sync_job or sync
        self.enrich_job = enrich_job or enrich_library
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.stopped = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="library-maintenance")
        saved = read_json(vault.root / ".local/maintenance.json", {})
        self.jobs = {name: saved.get(name, {"state": "idle"}) for name in ("backup", "enrichment")}
        last_sync = read_json(vault.root / ".local/last-sync.json", {})
        if last_sync.get("completed"):
            self.jobs["backup"].setdefault("completed", last_sync["completed"])
        for job in self.jobs.values():
            if job["state"] in ("queued", "running"):
                job["state"] = "interrupted"
                job.pop("attempted", None)
        self.next_scan = self.clock()
        self.thread = None

    def status(self):
        with self.lock:
            return {name: dict(job) for name, job in self.jobs.items()}

    def report(self, name, values):
        with self.lock:
            self.jobs[name].update(values)
            atomic_write(self.vault.root / ".local/maintenance.json", encoded(self.jobs))

    def start_job(self, name, *, public_only=None, force=False):
        with self.lock:
            if self.jobs[name]["state"] in ("queued", "running"):
                return dict(self.jobs[name])
            # Preserve the last successful timestamp if a retry subsequently fails.
            previous = {key: self.jobs[name][key] for key in ("completed",) if key in self.jobs[name]}
            self.jobs[name] = previous | {"state": "queued", "attempted": now(), "done": 0, "total": 0, "matched": 0, "failed": 0}
            status = dict(self.jobs[name])
        scope = preferences(self.vault)["backup_public_only"] if public_only is None else public_only
        self.pool.submit(self.run, name, scope, force)
        return status

    def run(self, name, public_only, force):
        self.report(name, {"state": "running"})
        try:
            if name == "backup":
                # Save local-only notes even when the remote service is offline.
                with self.vault.lock():
                    self.vault.snapshot()
                self.report(name, {"local_snapshot_at": now()})
                result = self.sync_job(self.vault, public_only=public_only)
                self.report(name, {"state": "complete", "completed": result["completed"], "scope": result.get("scope", "public-only" if public_only else "authenticated")})
                self.changed()
            else:
                self.enrich_job(self.vault, force=force, progress=lambda status: self.report(name, status))
        except Exception:
            # Provider errors may contain private context or API keys.
            self.report(name, {"state": "failed", "error": "Local snapshot saved; annotation sync failed. Check your Hypothesis connection and retry." if name == "backup" and self.status()[name].get("local_snapshot_at") else "Maintenance failed. Check your connection and settings, then retry."})

    def changed(self):
        with self.lock:
            self.next_scan = self.clock()
        self.wake.set()

    def tick(self):
        config = preferences(self.vault)
        clock = self.clock()
        if backup_due(config, self.status()["backup"], clock):
            self.start_job("backup")
        with self.lock:
            scan = clock >= self.next_scan and self.jobs["enrichment"]["state"] not in ("queued", "running")
            if scan:
                self.next_scan = clock + timedelta(minutes=15)
        if scan and config["enrichment_enabled"] and any(self.vault.secret(name) for name in API_KEYS):
            self.start_job("enrichment")

    def start(self):
        if self.thread:
            return
        def loop():
            while not self.stopped.is_set():
                self.wake.clear()
                try:
                    self.tick()
                except (ValueError, OSError):
                    pass
                self.wake.wait(60)
        self.thread = threading.Thread(target=loop, daemon=True, name="library-scheduler")
        self.thread.start()

    def close(self):
        self.stopped.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=2)
        self.pool.shutdown(wait=False, cancel_futures=True)
