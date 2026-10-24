from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_notes import service
from research_notes import schedule
from research_notes.schedule import label_for as backup_label
from research_notes.store import Vault


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.vault = Vault(Path(self.temporary.name) / "vault")
        self.vault.initialize("test_reader")

    def test_login_agent_keeps_the_bridge_alive_and_excludes_credentials(self):
        self.vault.configure(hypothesis_token="synthetic-token-not-for-launchd")
        definition = service.agent_definition(self.vault)
        body = plistlib.dumps(definition)
        self.assertNotIn(b"synthetic-token-not-for-launchd", body)
        self.assertTrue(definition["KeepAlive"])
        self.assertTrue(definition["RunAtLoad"])
        self.assertNotIn("StartCalendarInterval", definition)
        self.assertNotEqual(definition["Label"], backup_label(self.vault))
        self.assertEqual(definition["ProgramArguments"][-1], "serve")
        self.assertEqual(definition["Umask"], 0o077)
        self.assertEqual(set(definition["EnvironmentVariables"]) - {"PATH", "NOTES_CODEX_BIN", "NOTES_CODEX_MODEL"}, set())

    def test_install_refuses_to_stop_an_unmanaged_listener(self):
        with patch.object(service.sys, "platform", "darwin"), patch.object(service, "loaded", return_value=False), patch.object(service, "port_in_use", return_value=True), patch.object(service.subprocess, "run") as command:
            with self.assertRaisesRegex(ValueError, "already in use"):
                service.install(self.vault)
        command.assert_not_called()

    def test_daily_sync_accepts_token_from_the_ignored_env_file(self):
        self.vault.configure(hypothesis_token="synthetic-token-in-env")
        self.assertNotIn("hypothesis_token", self.vault.config())
        success = subprocess.CompletedProcess([], 0)
        with patch.object(schedule.sys, "platform", "darwin"), patch.object(schedule.Path, "home", return_value=Path(self.temporary.name)), patch.object(schedule.subprocess, "run", return_value=success):
            destination = schedule.install(self.vault)
        body = destination.read_bytes()
        self.assertNotIn(b"synthetic-token-in-env", body)
        self.assertIn(b"StartCalendarInterval", body)

    def test_install_and_uninstall_own_only_the_bridge_job(self):
        destination = Path(self.temporary.name) / "agents/bridge.plist"
        success = subprocess.CompletedProcess([], 0)
        with patch.object(service.sys, "platform", "darwin"), patch.object(service, "agent_path", return_value=destination), patch.object(service, "port_in_use", return_value=False), patch.object(service, "loaded", return_value=False), patch.object(service.subprocess, "run", return_value=success) as command:
            self.assertEqual(service.install(self.vault), destination)
            self.assertEqual(plistlib.loads(destination.read_bytes())["Label"], service.label_for(self.vault))
            self.assertEqual(command.call_args.args[0], ["/bin/launchctl", "bootstrap", f"gui/{service.os.getuid()}", str(destination)])
        with patch.object(service.sys, "platform", "darwin"), patch.object(service, "agent_path", return_value=destination), patch.object(service, "loaded", return_value=True), patch.object(service.subprocess, "run", return_value=success) as command:
            service.uninstall(self.vault)
            self.assertEqual(command.call_args.args[0], ["/bin/launchctl", "bootout", service.target(self.vault)])
        self.assertFalse(destination.exists())
