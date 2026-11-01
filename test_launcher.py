import os
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
