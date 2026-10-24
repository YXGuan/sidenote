import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("project_setup", Path(__file__).resolve().parents[1] / "tools/setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_new_user_is_required_instead_of_assuming_the_authors_account(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary)
            with self.assertRaisesRegex(ValueError, "--user"):
                setup.username(vault, None)
            self.assertEqual(setup.username(vault, "new_reader"), "new_reader")
            with self.assertRaisesRegex(ValueError, "placeholder"):
                setup.username(vault, "YOUR_HYPOTHESIS_USERNAME")
            self.assertEqual(list(vault.iterdir()), [])

    def test_existing_account_is_reused_and_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary)
            (vault / ".local").mkdir()
            config = vault / ".local/config.json"
            config.write_text('{"user":"existing_reader"}')
            self.assertEqual(setup.username(vault, None), "existing_reader")
            with self.assertRaisesRegex(ValueError, "different user"):
                setup.username(vault, "different_reader")
            self.assertEqual(config.read_text(), '{"user":"existing_reader"}')

    def test_check_never_initializes_builds_or_installs(self):
        with patch.object(setup, "preflight", return_value={"ready": True}), patch.object(setup, "username") as account, patch.object(setup, "dependencies_current") as deps:
            self.assertEqual(setup.main(["--check"]), 0)
            account.assert_not_called()
            deps.assert_not_called()

    def test_account_mismatch_stops_before_installing_dependencies(self):
        with patch.object(setup, "preflight", return_value={"ready": True}), patch.object(setup, "username", side_effect=ValueError("different user")), patch.object(setup, "dependencies_current") as deps:
            self.assertEqual(setup.main(["--user", "other"]), 1)
            deps.assert_not_called()
