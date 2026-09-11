"""Create a deliberately empty registry around an approved profile."""
from __future__ import annotations

import importlib.resources
import shutil
from pathlib import Path


class InitError(Exception):
    pass


def _template(name: str) -> str:
    return importlib.resources.files("supreme_metric").joinpath("templates", name).read_text()


def init_registry(directory: Path, profile: Path) -> None:
    directory, profile = Path(directory), Path(profile)
    if not profile.is_file():
        raise InitError(f"approved profile not found: {profile}")
    if directory.exists() and any(directory.iterdir()):
        raise InitError(f"refusing to overwrite non-empty directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(profile, directory / "profile.yaml")
    for rel in ("questions", "metrics", "rulings"):
        target = directory / rel
        target.mkdir(exist_ok=True)
        (target / ".gitkeep").touch()
    (directory / "ADOPTION.md").write_text(
        "# Registry adoption\n\n"
        "1. Add one decision question under `questions/`.\n"
        "2. Add two owner-grouped metrics under `metrics/`.\n"
        "3. Add one ruling under `rulings/<owner>/`.\n"
        "4. Run `supreme validate .` and `supreme compile .`.\n"
    )
    for name in ("CODEOWNERS.template", "ci.yml.template"):
        (directory.parent / name).write_text(_template(name))
