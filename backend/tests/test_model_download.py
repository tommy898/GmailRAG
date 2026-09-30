import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.download_models import download_models


class ModelDownloadTests(unittest.TestCase):
    @patch("scripts.download_models.snapshot_download")
    def test_downloads_only_pinned_role_models_and_records_checksums(self, download):
        def create_synthetic_snapshot(**arguments):
            root = arguments["local_dir"]
            root.mkdir(parents=True)
            (root / "config.json").write_text("{}")
            (root / "model.safetensors").write_bytes(b"synthetic weights")
            (root / ".cache").mkdir()
            (root / ".cache/metadata").write_text("not a runtime artifact")
        download.side_effect = create_synthetic_snapshot
        for role, expected in (("worker", {"embedding"}), ("api", {"embedding", "reranking"})):
            download.reset_mock()
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                download_models(role, root)
                manifest = json.loads((root / "artifact-manifest.json").read_text())
                self.assertEqual(manifest["role"], role)
                self.assertEqual(set(manifest["models"]), expected)
                self.assertEqual(download.call_count, len(expected))
                for arguments in download.call_args_list:
                    options = arguments.kwargs
                    self.assertRegex(options["revision"], r"^[0-9a-f]{40}$")
                    self.assertFalse(options["token"])
                    self.assertIn("*.safetensors", options["allow_patterns"])
                    self.assertIn("onnx/*", options["ignore_patterns"])
                for kind, model in manifest["models"].items():
                    self.assertFalse((root / kind / ".cache").exists())
                    self.assertEqual(set(model["files"]), {"config.json", "model.safetensors"})
                    self.assertTrue(all(len(digest) == 64 for digest in model["files"].values()))

    @patch("scripts.download_models.snapshot_download")
    def test_missing_safe_tensor_weights_prevents_a_success_manifest(self, download):
        download.side_effect = lambda **arguments: arguments["local_dir"].mkdir(parents=True)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, "weights are missing"):
                download_models("worker", root)
            self.assertFalse((root / "artifact-manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
