import importlib.machinery
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader("native_build", str(Path(__file__).resolve().parents[1] / "hypothesis/build"))
spec = importlib.util.spec_from_loader(loader.name, loader)
build = importlib.util.module_from_spec(spec)
loader.exec_module(build)


class PatchExportTests(unittest.TestCase):
    def test_incomplete_export_preserves_both_patches_then_complete_export_reconstructs_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repos = {}
            for name in ("client", "browser-extension"):
                repo = root / name
                repo.mkdir()
                def git(*args):
                    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL)
                git("init", "--quiet")
                git("config", "user.email", "test@example.org")
                git("config", "user.name", "Synthetic Test")
                (repo / "source").write_text("original\n")
                git("add", "source")
                git("commit", "--quiet", "-m", "Synthetic upstream")
                repos[name] = ("unused", git("rev-parse", "HEAD").decode().strip(), "unused")
            (root / "patches").mkdir()
            for name in repos:
                (root / "patches" / (name + ".patch")).write_text("existing " + name)
            (root / "client/source").write_text("changed\n")
            with patch.object(build, "ROOT", root), patch.object(build, "REPOS", repos), patch("sys.argv", ["build", "--export-patches"]):
                with self.assertRaisesRegex(RuntimeError, "empty export"):
                    build.main()
                for name in repos:
                    self.assertEqual((root / "patches" / (name + ".patch")).read_text(), "existing " + name)
                (root / "browser-extension/new-source").write_text("new file\n")
                self.assertEqual(build.main(), 0)
                self.assertIn("+changed", (root / "patches/client.patch").read_text())
                self.assertIn("new-source", (root / "patches/browser-extension.patch").read_text())
                for name in repos:
                    subprocess.run(["git", "-C", str(root / name), "apply", "--reverse", "--check", str(root / "patches" / (name + ".patch"))], check=True, capture_output=True)
