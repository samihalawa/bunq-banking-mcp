import os
import json
import tomllib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from plugin_launcher import configure


class LauncherTests(unittest.TestCase):
    def test_prefers_executable_user_local_op_and_deduplicates_path(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            local_bin = home / ".local" / "bin"
            local_bin.mkdir(parents=True)
            (local_bin / "op").touch(mode=0o700)
            with patch("plugin_launcher.Path.home", return_value=home), patch.dict(os.environ, {"PATH": os.pathsep.join(["/usr/bin", str(local_bin), "/bin", str(local_bin)])}, clear=True):
                configure()
                self.assertEqual(os.environ["PATH"], os.pathsep.join([str(local_bin), "/usr/bin", "/bin"]))
                self.assertEqual(os.environ["OP_BIOMETRIC_UNLOCK_ENABLED"], "false")

    def test_missing_or_nonexecutable_op_preserves_inherited_path(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            for installed in (False, True):
                if installed:
                    local_bin = home / ".local" / "bin"
                    local_bin.mkdir(parents=True)
                    (local_bin / "op").touch(mode=0o600)
                with self.subTest(installed=installed), patch("plugin_launcher.Path.home", return_value=home), patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True):
                    configure()
                    self.assertEqual(os.environ["PATH"], "/usr/bin:/bin")

    def test_explicit_environment_precedes_defaults_and_settings(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            settings = home / ".config" / "bunq-banking-mcp" / "settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text('{"BUNQ_OP_ITEM_ID":"file-item","BUNQ_OP_VAULT_ID":"file-vault"}')
            with patch("plugin_launcher.Path.home", return_value=home), patch.dict(os.environ, {"OP_BIOMETRIC_UNLOCK_ENABLED": "true", "BUNQ_OP_ITEM_ID": "inherited-item"}, clear=True):
                configure()
                self.assertEqual(os.environ["OP_BIOMETRIC_UNLOCK_ENABLED"], "true")
                self.assertEqual(os.environ["BUNQ_OP_ITEM_ID"], "inherited-item")
                self.assertEqual(os.environ["BUNQ_OP_VAULT_ID"], "file-vault")
                self.assertNotIn("PATH", os.environ)


class LockedLaunchTests(unittest.TestCase):
    def test_host_launchers_use_the_committed_project_lock_without_extra_requirements(self):
        root = Path(__file__).parent
        project = tomllib.loads((root / "pyproject.toml").read_text())
        lock = tomllib.loads((root / "uv.lock").read_text())
        self.assertEqual(project["project"]["version"], "0.3.5")
        self.assertTrue(lock["package"])
        for manifest in ("mcp.json", ".mcp.json", ".claude-plugin/plugin.json"):
            entry = json.loads((root / manifest).read_text())["mcpServers"]["bunq-banking"]
            self.assertEqual(entry["command"], "uv")
            self.assertIn("--locked", entry["args"])
            self.assertIn("--project", entry["args"])
            self.assertNotIn("--no-project", entry["args"])
            self.assertNotIn("--with-requirements", entry["args"])
