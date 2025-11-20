#!/usr/bin/env python

from pathlib import Path
from re import Match, search
from sys import exit, stderr, version_info
from typing import Any, Dict, Optional, Tuple

if __name__ == "__main__":
    vi: Tuple[int, int] = version_info[:2]
    if vi < (3, 11):
        from pip._vendor import tomli as tomllib
    else:
        import tomllib

    pyproject_toml: Dict[str, Any] = tomllib.loads(Path("pyproject.toml").read_text())
    pyproject_toml_version: Optional[str] = pyproject_toml.get(
        "project", {"version": None}
    ).get("version")

    pyinstaller_version_match: Optional[Match] = search(
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
