import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from app.config import ConfigurationError
from app.model_artifacts import file_sha256, model_loading_options, validate_packaged_models
from scripts.start_api import api_command, main as api_main
from scripts.validate_build import allowed_source_path, validate_build
from scripts.verify_dependencies import verify_dependencies


ROOT = Path(__file__).resolve().parents[2]
SPECIFICATION = json.loads((ROOT / "backend/model-artifacts.json").read_text())


class ModelArtifactTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_local_development_preserves_existing_model_identifier(self):
        self.assertEqual(model_loading_options("embedding", "all-MiniLM-L6-v2"),
                         {"model_name_or_path": "all-MiniLM-L6-v2"})

    def test_production_never_falls_back_to_remote_model_download(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            with self.assertRaisesRegex(ConfigurationError, "packaged locally"):
                model_loading_options("embedding", "all-MiniLM-L6-v2")

    def test_missing_and_relative_model_paths_are_rejected_without_path_values(self):
        for path in ("relative/private-path", "/absent/private-path"):
            with patch.dict(os.environ, {"EMBEDDING_MODEL_PATH": path}):
                with self.assertRaises(ConfigurationError) as caught:
                    model_loading_options("embedding", "unused")
                self.assertNotIn("private-path", str(caught.exception))

    def make_artifacts(self, root, role):
        kinds = ("embedding", "reranking") if role == "api" else ("embedding",)
        models = {}
        for kind in kinds:
            directory = root / kind
            directory.mkdir()
            for name in ("config.json", "model.safetensors"):
                (directory / name).write_text("synthetic fixture")
            models[kind] = {"specification": SPECIFICATION[kind], "files": {
                name: file_sha256(directory / name) for name in ("config.json", "model.safetensors")
            }}
        manifest = {"role": role, "models": models}
        (root / "artifact-manifest.json").write_text(json.dumps(manifest))
        return manifest

    def test_complete_manifest_checks_hashes_and_forces_safe_offline_cpu_loading(self):
        for role in ("api", "worker"):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                self.make_artifacts(root, role)
                with patch.dict(os.environ, {
                    "CONTAINER_MODEL_ROOT": str(root), "EMBEDDING_MODEL_PATH": str(root / "embedding"),
                    "RERANKING_MODEL_PATH": str(root / "reranking"),
                }):
                    validate_packaged_models(role)
                    options = model_loading_options("embedding", "unused")
                    self.assertTrue(options["local_files_only"])
                    self.assertFalse(options["trust_remote_code"])
                    self.assertEqual(options["device"], "cpu")

    def test_corrupt_missing_extra_wrong_revision_or_role_artifacts_fail_closed(self):
        for mutation in ("corrupt", "missing", "extra", "revision", "role", "path"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                manifest = self.make_artifacts(root, "worker")
                if mutation == "corrupt":
                    (root / "embedding/model.safetensors").write_text("modified")
                elif mutation == "missing":
                    (root / "embedding/model.safetensors").unlink()
                elif mutation == "extra":
                    (root / "embedding/unexpected.py").write_text("unexpected")
                elif mutation == "revision":
                    manifest["models"]["embedding"]["specification"] = SPECIFICATION["embedding"] | {"revision": "main"}
                elif mutation == "role":
                    manifest["role"] = "api"
                (root / "artifact-manifest.json").write_text(json.dumps(manifest))
                with patch.dict(os.environ, {
                    "CONTAINER_MODEL_ROOT": str(root),
                    "EMBEDDING_MODEL_PATH": str(root / ("other" if mutation == "path" else "embedding")),
                }):
                    with self.assertRaisesRegex(ConfigurationError, "integrity check failed"):
                        validate_packaged_models("worker")

    def test_noncontainer_environment_skips_packaged_manifest_check(self):
        validate_packaged_models("api")
        validate_packaged_models("worker")


class ContainerPackagingTests(unittest.TestCase):
    def test_api_expands_port_without_shell_reload_or_multiple_workers(self):
        command = api_command("9090")
        self.assertIn("0.0.0.0", command)
        self.assertEqual(command[command.index("--port") + 1], "9090")
        self.assertEqual(command[command.index("--workers") + 1], "1")
        self.assertNotIn("--reload", command)
        for port in ("", "0", "65536", "abc", "80; command", "１２３", " 8080"):
            with self.assertRaises(ValueError):
                api_command(port)

    @patch("scripts.start_api.os.execv")
    def test_api_launcher_replaces_process_for_correct_signal_delivery(self, execute):
        with patch.dict(os.environ, {"PORT": "8081"}):
            self.assertEqual(api_main(), 0)
        execute.assert_called_once()
        self.assertEqual(execute.call_args.args[1], api_command("8081"))

    def test_source_allowlist_excludes_environment_credentials_data_models_and_frontend(self):
        excluded = ["backend/.env", "backend/.env.production", "frontend/.env.local",
                    ".git/config", ".venv/bin/python", "backend/credentials.json", "backend/token.json",
                    "data/emails.json", "backend/models/model.safetensors", "docs/PROJECT_PLAN.md",
                    "backend/app/private.key", "backend/app/__pycache__/main.pyc"]
        for path in excluded:
            self.assertFalse(allowed_source_path(path), path)
        for path in ("backend/app/main.py", "backend/scripts/start_api.py", "backend/Dockerfile",
                     "supabase/schema.sql", "supabase/migrations/202609300001_harden_client_permissions.sql"):
            self.assertTrue(allowed_source_path(path), path)
        for name in (".dockerignore", ".gcloudignore"):
            content = (ROOT / name).read_text()
            self.assertIn("**/.env", content)
            self.assertIn("**/credentials*.json", content)
            self.assertNotIn("!frontend", content)

    def test_build_preflight_rejects_uncommitted_source_tags_and_unexpected_uploads(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            validate_build("gmailrag-501319", "us-west1", "gmailrag", "a" * 40, root)
            for revision in ("UNSET", "main", "latest", "abcdef"):
                with self.assertRaises(ValueError):
                    validate_build("gmailrag-501319", "us-west1", "gmailrag", revision, root)
            (root / ".env").write_text("synthetic")
            with self.assertRaises(ValueError):
                validate_build("gmailrag-501319", "us-west1", "gmailrag", "a" * 40, root)

    def test_docker_targets_are_nonroot_pinned_and_preserve_job_argument_entrypoint(self):
        dockerfile = (ROOT / "backend/Dockerfile").read_text()
        self.assertIn("python:3.14.6-slim-bookworm@sha256:", dockerfile)
        self.assertIn("--no-deps -r requirements-cpu.txt", dockerfile)
        self.assertIn("--only-binary=:all:", dockerfile)
        self.assertIn("USER 65532:65532", dockerfile)
        self.assertIn('ENTRYPOINT ["python", "-m", "app.worker"]', dockerfile)
        self.assertIn("HF_HUB_OFFLINE=1", dockerfile)
        self.assertIn("TRANSFORMERS_OFFLINE=1", dockerfile)
        self.assertIn("COPY --from=tested /tmp/tests-passed", dockerfile)
        self.assertIn("COPY backend/container/debian.sources", dockerfile)
        sources = (ROOT / "backend/container/debian.sources").read_text()
        self.assertIn("20260930T000000Z", sources)
        self.assertIn("Signed-By:", sources)
        self.assertNotIn("Trusted: yes", sources)
        self.assertNotIn("COPY . ", dockerfile)
        self.assertNotIn("GOOGLE_CLIENT_SECRET", dockerfile)

    def test_cloud_build_only_publishes_after_both_network_disabled_smoke_checks(self):
        config = yaml.safe_load((ROOT / "backend/cloudbuild.yaml").read_text())
        self.assertEqual(config["substitutions"]["_SOURCE_REVISION"], "UNSET")
        self.assertEqual(config["steps"][0]["id"], "source-preflight")
        checks = [step for step in config["steps"] if step["id"].startswith("offline-")]
        self.assertEqual(len(checks), 2)
        for step in checks:
            self.assertIn("--network=none", step["args"])
            self.assertIn("--read-only", step["args"])
            self.assertIn("--require-linux", step["args"])
        self.assertEqual(len(config["images"]), 2)
        self.assertTrue(all("$BUILD_ID" in image for image in config["images"]))
        serialized = json.dumps(config)
        self.assertNotIn("secrets", serialized.lower())
        self.assertNotIn("deploy", serialized)
        self.assertNotIn("gcloud", serialized)

    def test_model_revisions_match_cached_versions_and_are_immutable(self):
        for specification in SPECIFICATION.values():
            self.assertRegex(specification["revision"], r"^[a-f0-9]{40}$")

    @patch("scripts.verify_dependencies.distributions")
    def test_unlocked_dependencies_fail_build_instead_of_silently_changing_runtime(self, installed):
        installed.return_value = [SimpleNamespace(metadata={"Name": "unexpected-package"}, version="1.0")]
        with self.assertRaisesRegex(RuntimeError, "Unpinned"):
            verify_dependencies()


if __name__ == "__main__":
    unittest.main()
