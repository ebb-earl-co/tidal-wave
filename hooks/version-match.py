#!/usr/bin/env python

from __future__ import annotations

from pathlib import Path
from re import Match, search
from sys import exit, stderr
from typing import Any

import tomllib

if __name__ == "__main__":
    pyproject_toml: dict[str, Any] = tomllib.loads(Path("pyproject.toml").read_text())
    pyproject_toml_version: str = pyproject_toml.get("project", {"version": None}).get(
        "version", ""
    )

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
