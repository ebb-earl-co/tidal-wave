#!/usr/bin/env python

from pathlib import Path
from re import Match, search
from sys import exit, stderr, version_info
from typing import Any

if __name__ == "__main__":
    vi: tuple[int, int] = version_info[:2]
    if vi < (3, 11):
        from pip._vendor import tomli as tomllib
    else:
        import tomllib

    pyproject_toml: dict[str, Any] = tomllib.loads(Path("pyproject.toml").read_text())
    pyproject_toml_version: str | None = pyproject_toml.get(
        "project", {"version": None}
    ).get("version")

    pyinstaller_version_match: Match | None = search(
        pyproject_toml_version, Path("pyinstaller.py").read_text()
    )
    if pyinstaller_version_match is None:
        print(
            f"Version in 'pyinstaller.py' does not match '{pyproject_toml_version}'!",
            file=stderr,
        )
        exit(1)
    else:
        exit(0)
