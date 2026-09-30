"""Local-only packaged model loading and integrity checks; no model downloads."""

import hashlib
import json
import os
from pathlib import Path

from app.config import ConfigurationError, is_production


MODEL_ENVIRONMENT = {
    "embedding": "EMBEDDING_MODEL_PATH",
    "reranking": "RERANKING_MODEL_PATH",
}


def model_loading_options(kind: str, default_model: str) -> dict:
    path = os.environ.get(MODEL_ENVIRONMENT[kind], "").strip()
    if not path:
        if is_production():
            raise ConfigurationError("Production model artifacts must be packaged locally")
        return {"model_name_or_path": default_model}
    root = Path(path)
    if not root.is_absolute() or not all(
        (root / filename).is_file() for filename in ("config.json", "model.safetensors")
    ):
        raise ConfigurationError("Packaged model artifacts are unavailable")
    return {
        "model_name_or_path": str(root),
        "device": "cpu",
        "local_files_only": True,
        "trust_remote_code": False,
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_packaged_models(role: str) -> None:
    """Only container runtimes set CONTAINER_MODEL_ROOT. Local dev is unchanged."""
    configured_root = os.environ.get("CONTAINER_MODEL_ROOT")
    if not configured_root:
        return
    try:
        root = Path(configured_root).resolve(strict=True)
        expected = json.loads(
            (Path(__file__).resolve().parents[1] / "model-artifacts.json").read_text()
        )
        manifest = json.loads((root / "artifact-manifest.json").read_text())
        kinds = ("embedding", "reranking") if role == "api" else ("embedding",)
        if manifest["role"] != role or set(manifest["models"]) != set(kinds):
            raise ValueError("Artifact role mismatch")
        for kind in kinds:
            model = manifest["models"][kind]
            if model["specification"] != expected[kind]:
                raise ValueError("Artifact revision mismatch")
            model_root = root / expected[kind]["directory"]
            if Path(os.environ.get(MODEL_ENVIRONMENT[kind], "")).resolve() != model_root:
                raise ValueError("Artifact path mismatch")
            options = model_loading_options(kind, expected[kind]["repo_id"])
            if not options["local_files_only"] or not model["files"]:
                raise ValueError("Missing artifact inventory")
            actual_files = {
                str(path.relative_to(model_root)) for path in model_root.rglob("*")
                if path.is_file()
            }
            if actual_files != set(model["files"]):
                raise ValueError("Artifact inventory mismatch")
            for relative, digest in model["files"].items():
                path = (model_root / relative).resolve(strict=True)
                if not path.is_relative_to(root) or file_sha256(path) != digest:
                    raise ValueError("Artifact checksum mismatch")
    except Exception:
        # Paths and parsing errors never reach application logs.
        raise ConfigurationError("Packaged model integrity check failed") from None
