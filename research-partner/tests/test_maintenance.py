from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_notes.maintenance import Maintenance, backup_due, preferences, save_settings, settings
from research_notes.server import make_server, pairing_key
from research_notes.store import Vault, atomic_write, encoded, read_json


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.vault = Vault(Path(self.temp.name) / "vault")
        self.vault.initialize("test_reader")

    def controller(self, **kwargs):
        controller = Maintenance(self.vault, **kwargs)
        self.addCleanup(controller.close)
        return controller

    def wait_for(self, controller, name):
        deadline = time.monotonic() + 5
        while controller.status()[name]["state"] in ("queued", "running"):
            self.assertLess(time.monotonic(), deadline, "Job did not finish")
            threading.Event().wait(0.01)
        return controller.status()[name]

    def test_credentials_are_write_only_private_and_preserve_other_env_entries(self):
        atomic_write(self.vault.env_file, '# Keep this comment\nHYPOTHESIS_TOKEN="synthetic-hypothesis"\nOTHER_VALUE="untouched"\n')
        response = save_settings(self.vault, {"backup_enabled": True, "backup_time": "04:30"}, {
            "OPENALEX_API_KEY": "synthetic-openalex", "S2_API_KEY": "synthetic-semantic"})
        self.assertTrue(response["api_keys"]["OPENALEX_API_KEY"]["configured"])
        self.assertEqual(self.vault.secret("S2_API_KEY"), "synthetic-semantic")
        self.assertEqual(self.vault.token(), "synthetic-hypothesis")
        self.assertIn("# Keep this comment", self.vault.env_file.read_text())
        self.assertIn('OTHER_VALUE="untouched"', self.vault.env_file.read_text())
        self.assertEqual(self.vault.env_file.stat().st_mode & 0o777, 0o600)
        for value in ("synthetic-openalex", "synthetic-semantic", "synthetic-hypothesis"):
            self.assertNotIn(value, json.dumps(response))
            self.assertNotIn(value, json.dumps(self.vault.config()))
            self.assertNotIn(value, self.vault.snapshot().read_text())
        save_settings(self.vault, {}, {"OPENALEX_API_KEY": None})
        self.assertIsNone(self.vault.secret("OPENALEX_API_KEY"))
        self.assertEqual(self.vault.secret("S2_API_KEY"), "synthetic-semantic")
        self.assertTrue(preferences(self.vault)["backup_enabled"])
        with patch.dict(os.environ, {"S2_API_KEY": "synthetic-environment"}):
            self.assertFalse(settings(self.vault)["api_keys"]["S2_API_KEY"]["editable"])
            with self.assertRaises(ValueError):
                save_settings(self.vault, {}, {"S2_API_KEY": "replacement"})

    def test_invalid_settings_never_partially_write_credentials(self):
        before = self.vault.config()
        for values, keys in [({"backup_time": "25:00"}, {"S2_API_KEY": "valid-test-value"}),
                             ({"backup_enabled": "true"}, {}), ({"unexpected": True}, {}),
                             ({}, {"HYPOTHESIS_TOKEN": "not-supported-here"}),
                             ({}, {"S2_API_KEY": "secret\nINJECTED=value"}),
                             ({}, {"S2_API_KEY": []})]:
            with self.assertRaises(ValueError) as error:
                save_settings(self.vault, values, keys)
            self.assertNotIn("INJECTED", str(error.exception))
        self.assertEqual(before, self.vault.config())
        self.assertFalse(self.vault.env_file.exists())

    def test_daily_schedule_catches_up_after_sleep_and_uses_local_calendar_days(self):
        config = preferences(self.vault) | {"backup_enabled": True}
        local = ZoneInfo("America/Toronto")
        clock = datetime(2026, 11, 1, 4, 0, tzinfo=local)  # DST transition day.
        self.assertTrue(backup_due(config, {}, clock))
        self.assertFalse(backup_due(config, {}, clock.replace(hour=2)))
        self.assertFalse(backup_due(config, {"completed": clock.isoformat()}, clock))
        self.assertTrue(backup_due(config, {"completed": (clock - timedelta(days=1)).isoformat()}, clock))
        self.assertFalse(backup_due(config, {"attempted": (clock - timedelta(minutes=30)).isoformat()}, clock))
        self.assertTrue(backup_due(config, {"attempted": (clock - timedelta(hours=2)).isoformat()}, clock))
        self.assertFalse(backup_due(config | {"backup_enabled": False}, {}, clock))

    def test_backup_keeps_a_local_snapshot_on_sync_failure_and_redacts_errors(self):
        controller = self.controller(sync_job=Mock(side_effect=RuntimeError("private-secret-provider-error")))
        self.vault.capture("https://example.org/synthetic", {"title": "Synthetic source"})
        controller.start_job("backup")
        result = self.wait_for(controller, "backup")
        self.assertEqual(result["state"], "failed")
        self.assertTrue(result["local_snapshot_at"])
        self.assertTrue(list((self.vault.root / "snapshots").glob("*.json")))
        self.assertNotIn("private-secret", json.dumps(result))
        self.assertNotIn("private-secret", (self.vault.root / ".local/maintenance.json").read_text())

    def test_jobs_deduplicate_and_daily_success_survives_bridge_restart(self):
        clock = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
        entered, release = threading.Event(), threading.Event()
        def sync_job(vault, *, public_only):
            self.assertTrue(public_only)
            entered.set()
            self.assertTrue(release.wait(3))
            return {"completed": clock.isoformat(), "scope": "public-only"}
        sync_mock = Mock(side_effect=sync_job)
        controller = self.controller(sync_job=sync_mock, clock=lambda: clock)
        save_settings(self.vault, {"backup_enabled": True}, {})
        with patch("research_notes.maintenance.now", return_value=clock.isoformat()):
            controller.tick()
            self.assertTrue(entered.wait(3))
            controller.start_job("backup")
            controller.tick()
            release.set()
            self.assertEqual(self.wait_for(controller, "backup")["state"], "complete")
        sync_mock.assert_called_once()
        restarted_sync = Mock()
        restarted = self.controller(sync_job=restarted_sync, clock=lambda: clock)
        restarted.tick()
        restarted_sync.assert_not_called()
        self.assertEqual(restarted.status()["backup"]["completed"], clock.isoformat())

    def test_automatic_enrichment_honors_toggle_keys_and_periodic_scans(self):
        clock = [datetime(2026, 10, 24, 12, tzinfo=timezone.utc)]
        def enrich_job(vault, *, force, progress):
            self.assertFalse(force)
            progress({"state": "complete", "completed": clock[0].isoformat(), "skipped": 3})
        enriched = Mock(side_effect=enrich_job)
        controller = self.controller(enrich_job=enriched, clock=lambda: clock[0])
        controller.tick()
        enriched.assert_not_called()
        save_settings(self.vault, {"enrichment_enabled": False}, {"S2_API_KEY": "synthetic-key"})
        controller.changed()
        controller.tick()
        enriched.assert_not_called()
        save_settings(self.vault, {"enrichment_enabled": True}, {})
        controller.changed()
        controller.tick()
        self.wait_for(controller, "enrichment")
        controller.tick()
        enriched.assert_called_once()
        clock[0] += timedelta(minutes=16)
        controller.tick()
        self.wait_for(controller, "enrichment")
        self.assertEqual(enriched.call_count, 2)

    def test_interrupted_daily_backup_catches_up_without_retry_delay(self):
        clock = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
        save_settings(self.vault, {"backup_enabled": True}, {})
        atomic_write(self.vault.root / ".local/maintenance.json", encoded({
            "backup": {"state": "running", "attempted": clock.isoformat()}}))
        sync_job = Mock(return_value={"completed": clock.isoformat()})
        controller = self.controller(sync_job=sync_job, clock=lambda: clock)
        self.assertEqual(controller.status()["backup"]["state"], "interrupted")
        controller.tick()
        self.assertEqual(self.wait_for(controller, "backup")["state"], "complete")
        sync_job.assert_called_once()

    def test_settings_bridge_requires_pairing_and_does_not_return_api_key_values(self):
        with patch("research_notes.maintenance.sync", return_value={"completed": "2026-10-24T12:00:00Z"}), patch("research_notes.scholarly.enrich_library"):
            server = make_server(self.vault, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def request(method, path, body=None, auth=True, origin=None):
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                headers = {"Content-Type": "application/json"}
                if auth:
                    headers["Authorization"] = "Bearer " + pairing_key(self.vault)
                if origin:
                    headers["Origin"] = origin
                connection.request(method, path, json.dumps(body) if body is not None else None, headers)
                response = connection.getresponse()
                result = response.status, json.loads(response.read())
                connection.close()
                return result
            try:
                self.assertEqual(request("GET", "/api/settings", auth=False)[0], 401)
                self.assertEqual(request("POST", "/api/settings", {}, auth=False)[0], 401)
                self.assertEqual(request("POST", "/api/backup", {}, auth=False)[0], 401)
                self.assertEqual(request("GET", "/api/settings", origin="https://example.org")[0], 403)
                body = {"preferences": {"backup_time": "22:15", "enrichment_enabled": False}, "api_keys": {"OPENALEX_API_KEY": "synthetic-write-only"}}
                status, result = request("POST", "/api/settings", body)
                self.assertEqual(status, 200)
                self.assertNotIn("synthetic-write-only", json.dumps(result))
                status, result = request("GET", "/api/settings")
                self.assertTrue(result["api_keys"]["OPENALEX_API_KEY"]["configured"])
                self.assertNotIn("synthetic-write-only", json.dumps(result))
                self.assertEqual(result["preferences"]["backup_time"], "22:15")
                self.assertEqual(request("POST", "/api/settings", {"preferences": {"backup_time": "invalid"}})[0], 400)
                self.assertEqual(request("POST", "/api/backup", {})[0], 202)
                deadline = time.monotonic() + 5
                while request("GET", "/api/settings")[1]["backup"]["state"] in ("queued", "running"):
                    self.assertLess(time.monotonic(), deadline)
                    threading.Event().wait(0.01)
                self.assertEqual(request("GET", "/api/settings")[1]["backup"]["state"], "complete")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(5)
