#!/usr/bin/env python3
#! -*- coding: utf-8 -*-

from contextlib import closing
import logging
from pathlib import Path
import sys
from typing import Optional

from .login import login, AudioFormat, LogLevel
from .media import Album, Track
from .models import match_tidal_url, TidalAlbum, TidalTrack
from .requesting import get_album_id

from platformdirs import user_music_path
import typer
from typing_extensions import Annotated

app = typer.Typer()


@app.command()
def main(
    tidal_url: Annotated[
        str, typer.Argument(help="The Tidal track or album to download")
    ],
    audio_format: Annotated[
        AudioFormat, typer.Option(case_sensitive=False)
    ] = AudioFormat.lossless.value,
    output_directory: Annotated[
        Path,
        typer.Argument(
            help="The parent directory under which files will be written; i.e. output_directory/<artist name>/<album name>/"
        ),
    ] = user_music_path(),
    loglevel: Annotated[
        LogLevel, typer.Option(case_sensitive=False)
    ] = LogLevel.info.value,
):
    logging.basicConfig(
        format="%(asctime)s,%(msecs)03d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d:%H:%M:%S",
        level=logging.getLevelName(loglevel.value),
    )
    logger = logging.getLogger(__name__)

    tidal_resource: Optional[Union[TidalResource, TidalTrack]] = match_tidal_url(
        tidal_url
    )
    if tidal_resource is None:
        logger.critical(f"Cannot parse '{tidal_url}' as a Tidal track or Album URL")
        raise typer.Exit(code=1)

    s, audio_format = login(audio_format=audio_format)
    if s is None:
        raise typer.Exit(code=1)

    with closing(s) as session:
        if isinstance(tidal_resource, TidalTrack):
            track = Track(track_id=tidal_resource.tidal_id)
            track.get(
                session=session, audio_format=audio_format, out_dir=output_directory
            )
            if loglevel == LogLevel.debug:
                track.dump()
            raise typer.Exit(code=0)
        elif isinstance(tidal_resource, TidalAlbum):
            album = Album(album_id=tidal_resource.tidal_id)
            album.get(
                session=session, audio_format=audio_format, out_dir=output_directory
            )
            if loglevel == LogLevel.debug:
                album.dump()
            raise typer.Exit(code=0)
        else:
            raise NotImplementedError


if __name__ == "__main__":
    app()
