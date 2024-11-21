"""Retrieve data from TIDAL API and save it locally."""

from __future__ import annotations

import logging
from contextlib import closing
from pathlib import Path

import typer
from cachecontrol import CacheControl
from platformdirs import user_music_path
from typing_extensions import Annotated

from .album import Album
from .artist import Artist
from .login import AudioFormat, LogLevel, login
from .mix import Mix
from .models import (
    TidalAlbum,
    TidalArtist,
    TidalMix,
    TidalPlaylist,
    TidalTrack,
    TidalVideo,
    match_tidal_url,
)
from .playlist import Playlist
from .track import Track
from .utils import is_tidal_api_reachable
from .video import Video

__version__ = "2024.11.1"


# https://typer.tiangolo.com/tutorial/options/version/#fix-with-is_eager
def version_callback(value: bool) -> None:  # noqa: FBT001
    """Pass this function to typer to specify eager option behavior."""
    if value:
        print(f"tidal-wave {__version__}")  # noqa: T201
        raise typer.Exit


app = typer.Typer()
_user_music_path: Path = user_music_path()


@app.command()
def main(
    tidal_url: Annotated[
        str,
        typer.Argument(
            help="The URL to the TIDAL resource that is desired to retrieve.",
        ),
    ],
    audio_format: Annotated[
        AudioFormat,
        typer.Option(case_sensitive=False),
    ] = AudioFormat.lossless.value,
    output_directory: Annotated[
        Path,
        typer.Argument(
            help="The directory under which directory(ies) of files will be written",
        ),
    ] = _user_music_path,
    loglevel: Annotated[
        LogLevel, typer.Option(case_sensitive=False),
    ] = LogLevel.info.value,
    include_eps_singles: Annotated[  # noqa: FBT002
        bool,
        typer.Option(
            "--include-eps-singles",
            help=(
                "No-op unless passing TIDAL artist. Whether to include artist's EPs and"
                " singles with albums"
            ),
        ),
    ] = False,
    no_extra_files: Annotated[  # noqa: FBT002
        bool,
        typer.Option(
            "--no-extra-files",
            help=(
                "Whether to not even attempt to retrieve artist bio, artist image, "
                "album credits, album review, or playlist m3u8"
            ),
        ),
    ] = False,
    no_flatten: Annotated[  # noqa: FBT002
        bool,
        typer.Option(
            "--no-flatten",
            help=(
                "Whether to treat playlists or mixes as a list of tracks/videos and, as"
                " such, retrieve them independently"
            ),
        ),
    ] = False,
    transparent: Annotated[  # noqa: FBT002
        bool,
        typer.Option(
            "--transparent",
            help="Whether to dump JSON responses from TIDAL API; maximum verbosity",
        ),
    ] = False,
    version: Annotated[  # noqa: ARG001
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True),
    ] = None,
):
    """Parse command line arguments and retrieve data from TIDAL."""
    logging.basicConfig(
        format="%(asctime)s,%(msecs)03d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d:%H:%M:%S",
        level=logging.getLevelName(loglevel.value),
    )
    logger = logging.getLogger(__name__)

    tidal_resource: (
        TidalAlbum | TidalMix | TidalPlaylist | TidalTrack | TidalVideo | None
    ) = match_tidal_url(tidal_url)

    if tidal_resource is None:
        _msg: str = (
            f"Cannot parse '{tidal_url}' as a TIDAL album, artist, mix, playlist, "
            "track, or video URL"
        )
        logger.critical(_msg)
        raise typer.Exit(code=1)

    # Check Internet connectivity, and whether api.tidal.com is up
    if not is_tidal_api_reachable():
        user_wishes_to_continue: bool = typer.confirm(
            "\nEven though tidal-wave cannot seem to connect to the Internet, "
            "would you like program execution to continue?",
        )
        if not user_wishes_to_continue:
            raise typer.Exit(code=1)

    s, audio_format = login(audio_format=audio_format)
    if s is None:
        raise typer.Exit(code=1)

    with closing(CacheControl(s)) as session:
        if isinstance(tidal_resource, TidalTrack):
            track = Track(track_id=tidal_resource.tidal_id, transparent=transparent)
            track.get(
                session=session,
                audio_format=audio_format,
                out_dir=output_directory,
                no_extra_files=no_extra_files,
            )

            if loglevel == LogLevel.debug:
                track.dump()
            raise typer.Exit(code=0)
        if isinstance(tidal_resource, TidalAlbum):
            album = Album(album_id=tidal_resource.tidal_id, transparent=transparent)
            album.get(
                session=session,
                audio_format=audio_format,
                out_dir=output_directory,
                no_extra_files=no_extra_files,
            )

            if loglevel == LogLevel.debug:
                album.dump()
            raise typer.Exit(code=0)
        if isinstance(tidal_resource, TidalArtist):
            artist = Artist(artist_id=tidal_resource.tidal_id, transparent=transparent)
            artist.get(
                session=session,
                audio_format=audio_format,
                out_dir=output_directory,
                include_eps_singles=include_eps_singles,
                no_extra_files=no_extra_files,
            )
            raise typer.Exit(code=0)
        if isinstance(tidal_resource, TidalVideo):
            video = Video(video_id=tidal_resource.tidal_id, transparent=transparent)
            video.get(session=session, out_dir=output_directory)

            if loglevel == LogLevel.debug:
                video.dump()
            raise typer.Exit(code=0)
        if isinstance(tidal_resource, TidalPlaylist):
            playlist = Playlist(
                playlist_id=tidal_resource.tidal_id, transparent=transparent,
            )
            if no_flatten:
                playlist.get_elements(
                    session=session,
                    audio_format=audio_format,
                    out_dir=output_directory,
                    no_extra_files=no_extra_files,
                )
            else:
                playlist.get(
                    session=session,
                    audio_format=audio_format,
                    out_dir=output_directory,
                    no_extra_files=no_extra_files,
                )

            if loglevel == LogLevel.debug:
                playlist.dump()
            raise typer.Exit(code=0)
        if isinstance(tidal_resource, TidalMix):
            mix = Mix(mix_id=tidal_resource.tidal_id, transparent=transparent)
            if no_flatten:
                mix.get_elements(
                    session=session,
                    audio_format=audio_format,
                    out_dir=output_directory,
                    no_extra_files=no_extra_files,
                )
            else:
                mix.get(
                    session=session,
                    audio_format=audio_format,
                    out_dir=output_directory,
                    no_extra_files=no_extra_files,
                )

            if loglevel == LogLevel.debug:
                mix.dump()
            raise typer.Exit(code=0)

        raise NotImplementedError


if __name__ == "__main__":
    app()
