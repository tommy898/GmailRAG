"""Fail the Linux build rather than silently installing an unlocked/GPU runtime."""

from importlib.metadata import distributions
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def verify_dependencies() -> None:
    constraints = {}
    for line in (Path(__file__).resolve().parents[1] / "constraints.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            requirement = Requirement(line)
            constraints[canonicalize_name(requirement.name)] = requirement.specifier
    for distribution in distributions():
        name = canonicalize_name(distribution.metadata["Name"])
        if name == "pip":
            if distribution.version != "26.1.2":
                raise RuntimeError("Build installer version mismatch")
            continue
        if name not in constraints or distribution.version not in constraints[name]:
            raise RuntimeError(f"Unpinned or unexpected runtime dependency: {name}")
    import torch
    if torch.__version__ != "2.13.0+cpu" or torch.version.cuda is not None:
        raise RuntimeError("Runtime must use the pinned CPU-only PyTorch build")
    print("Pinned dependency inventory and CPU-only PyTorch verified")


if __name__ == "__main__":
    verify_dependencies()
