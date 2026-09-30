"""Build-time download of pinned public model artifacts, not runtime secrets."""

import argparse
import json
import re
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download

from app.model_artifacts import file_sha256


def download_models(role: str, output: Path) -> None:
    specification = json.loads(
        (Path(__file__).resolve().parents[1] / "model-artifacts.json").read_text()
    )
    kinds = ("embedding", "reranking") if role == "api" else ("embedding",)
    manifest = {"role": role, "models": {}}
    for kind in kinds:
        model = specification[kind]
        if not re.fullmatch(r"[a-f0-9]{40}", model["revision"]):
            raise ValueError("Model revision must be an immutable commit")
        directory = output / model["directory"]
        snapshot_download(
            repo_id=model["repo_id"], revision=model["revision"],
            local_dir=directory, token=False,
            allow_patterns=["*.json", "*.txt", "*.safetensors"],
            ignore_patterns=["onnx/*", "openvino/*"],
        )
        # Local-dir download metadata isn't needed by offline inference.
        shutil.rmtree(directory / ".cache", ignore_errors=True)
        if not (directory / "model.safetensors").is_file():
            raise ValueError("Safe tensor weights are missing")
        manifest["models"][kind] = {
            "specification": model,
            "files": {
                str(path.relative_to(directory)): file_sha256(path)
                for path in sorted(directory.rglob("*")) if path.is_file()
            },
        }
    output.mkdir(parents=True, exist_ok=True)
    (output / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("api", "worker"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    download_models(args.role, args.output)


if __name__ == "__main__":
    main()
