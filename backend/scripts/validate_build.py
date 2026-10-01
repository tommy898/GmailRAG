"""Cloud Build preflight: identifiers and the uploaded source allowlist only."""

import argparse
import re
from pathlib import Path


def allowed_source_path(path: str) -> bool:
    parts = Path(path).parts
    if path in {".dockerignore", ".gcloudignore", "backend/db/schema.sql"}:
        return True
    if path == "backend/container/debian.sources":
        return True
    if len(parts) == 4 and parts[:3] == ("backend", "db", "migrations"):
        return parts[3].endswith(".sql")
    if len(parts) == 2 and parts[0] == "backend":
        return parts[1] in {
            "Dockerfile", "cloudbuild.yaml", "constraints.txt", "requirements.txt",
            "requirements-dev.txt", "requirements-cpu.txt", "model-artifacts.json",
        }
    return len(parts) == 3 and parts[0] == "backend" and parts[1] in {
        "app", "scripts", "tests",
    } and parts[2].endswith(".py")


def validate_build(project: str, region: str, repository: str, revision: str, root: Path) -> None:
    for value in (project, region, repository):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", value):
            raise ValueError("Build resource identifiers must be explicit and valid")
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Set _SOURCE_REVISION to the full committed Git SHA")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Source upload must not contain symlinks")
        if path.is_file() and not allowed_source_path(str(path.relative_to(root))):
            raise ValueError("Source upload contains a file outside the build allowlist")


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("project", "region", "repository", "revision"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    try:
        validate_build(args.project, args.region, args.repository, args.revision, Path.cwd())
    except ValueError as exc:
        print(str(exc))  # Fixed messages only; never file contents or env values.
        return 1
    print("Build identifiers and source allowlist verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
