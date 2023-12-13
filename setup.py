from pathlib import Path
from setuptools import setup, find_packages


def read_file(filename: str):
  return Path(filename).read_text()

requirements = [
  "dataclass-wizard",
  "ffmpeg-python",
  "mutagen",
  "platformdirs",
  "requests",
  "typer",
]

setup(
  name="tidal-wave",
  version="2023.12.1",
  author="colinho",
  author_email="pypi@colin.technology",
  description="A tool to wave at the TIDAL music service.",
  long_description=read_file("README.md"),
  long_description_content_type="text/markdown",
  url="https://github.com/ebb-earl-co/tidal-wave",
  install_requires=requirements,
  entry_points={
   "console_scripts": [
      "tidal-wave = tidal_wave:main"
    ],
  },
  packages=find_packages(),
  classifiers=[
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Operating System :: OS Independent",
  ],
  python_requires=">=3.8",
)
