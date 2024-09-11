"""Represent an artist in the reckoning of TIDAL API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .album import Album
from .requesting import (
    request_artists,
    request_artists_albums,
    request_artists_audio_works,
    request_artists_videos,
)
from .utils import download_cover_image
from .video import Video

if TYPE_CHECKING:
    from pathlib import Path

    from requests import Session

    from .media import AudioFormat
    from .models import (
        ArtistsAlbumsResponseJSON,
        ArtistsEndpointResponseJSON,
        ArtistsVideosResponseJSON,
    )

logger = logging.getLogger("__name__")


@dataclass
class Artist:
    """Class to represent an artist in the TIDAL API.

    It just needs the artist's ID and a Boolean as arguments to the
    constructor; the Boolean specifies whether to write all JSON
    responses from the TIDAL API to disk, for transparency's sake.

    Methods, e.g. `set_audio_works()`, are germane to retrieving data from
    the TIDAL API.
    """

    artist_id: int
    transparent: bool = False

    def set_metadata(self, session: Session) -> None:
        """Request from the TIDAL API endpoint /artists.

        Convert the JSON data returned from the API and store the resulting
        object as self.metadata.
        """
        self.metadata: ArtistsEndpointResponseJSON | None = request_artists(
            session=session,
            artist_id=self.artist_id,
            transparent=self.transparent,
        )

    def save_artist_image(self, session: Session) -> None:
        """Write the bytes of self.metadata.picture to disk.

        Specifically, the file cover.jpg in self.artist_dir.
        """
        artist_image: Path = self.artist_dir / "cover.jpg"
        if (not artist_image.exists()) and (self.metadata.picture is not None):
            download_cover_image(
                session,
                self.metadata.picture,
                self.artist_dir,
                dimension=750,
            )

    def set_albums(self, session: Session) -> None:
        """Populate the attribute `self.albums`.

        The JSON data from the TIDAL API endpoint /artists/albums is
        converted and stored as self.albums.
        """
        self.albums: ArtistsAlbumsResponseJSON | None = request_artists_albums(
            session=session,
            artist_id=self.artist_id,
            transparent=self.transparent,
        )

    def set_audio_works(self, session: Session) -> None:
        """Populate self.albums.

        Request from TIDAL API endpoint /artists/albums?filter=EPSANDSINGLES,
        convert the JSON data returned, and store the result as self.albums.
        """
        self.albums: ArtistsAlbumsResponseJSON | None = request_artists_audio_works(
            session=session,
            artist_id=self.artist_id,
            transparent=self.transparent,
        )

    def set_videos(self, session: Session) -> None:
        """Populate self.videos.

        Request from TIDAL API endpoint /artists/videos, convert the JSON
        data returned, and store the results as self.videos.
        """
        self.videos: ArtistsVideosResponseJSON | None = request_artists_videos(
            session=session,
            artist_id=self.artist_id,
            transparent=self.transparent,
        )

    def set_artist_dir(self, out_dir: Path) -> None:
        """Populate self.artist_dir.

        Set self.artist_dir as the subdirectory of `out_dir` simply named the
        value of `self.name`. N.b., a side effect is that the subdirectory on
        the file system is created if it does not exist.
        """
        self.name: str = self.metadata.name.replace("..", "").replace("/", "and")
        self.artist_dir = out_dir / self.name
        self.artist_dir.mkdir(parents=True, exist_ok=True)

    def get_albums(
        self,
        session: Session,
        audio_format: AudioFormat,
        out_dir: Path,
        *,
        include_eps_singles: bool,
        no_extra_files: bool,
    ) -> list[str | None]:
        """First, fetch all of the albums for `self.artist_id`.

        Then, each of the albums (and, optionally, EPs and singles) is requested and
        written to subdirectories of out_dir.
        """
        if include_eps_singles:
            self.set_audio_works(session)
            _msg: str = (
                f"Starting attempt to get {self.albums.total_number_of_items} "
                "albums, EPs, and singles for artist with ID "
                f"{self.metadata.id},  '{self.name}'"
            )
        else:
            self.set_albums(session)
            _msg: str = (
                f"Starting attempt to get {self.albums.total_number_of_items} albums "
                f"for artist with ID {self.metadata.id}, '{self.name}'"
            )
        logger.info(_msg)

        for a in self.albums.items:
            album: Album = Album(album_id=a.id)
            album.get(
                session=session,
                audio_format=audio_format,
                out_dir=out_dir,
                metadata=a,
                no_extra_files=no_extra_files,
            )

    def get_videos(
        self,
        session: Session,
        out_dir: Path,
    ) -> list[str | None]:
        """Populate `self.videos` by calling self.set_videos().

        Then, for each video, instantiates a Video object and execute
        the object's .get() method.
        """
        self.set_videos(session)
        _msg: str = (
            f"Starting attempt to get {self.videos.total_number_of_items} videos "
            f"for artist with ID {self.metadata.id}, '{self.name}'"
        )
        logger.info(_msg)
        for v in self.videos.items:
            video: Video = Video(video_id=v.id, transparent=self.transparent)
            video.get(
                session=session,
                out_dir=out_dir,
                metadata=v,
            )

    def get(
        self,
        session: Session,
        audio_format: AudioFormat,
        out_dir: Path,
        *,
        include_eps_singles: bool,
        no_extra_files: bool,
    ) -> None:
        """Execute other methods in sequence.

            1. set_metadata()
            2. set_artist_dir()
            3. get_videos()
            4. get_albums()
        Then, if no_extra_files is False, save_artist_image()
        """
        self.set_metadata(session)
        if self.metadata is None:
            return

        self.set_artist_dir(out_dir)
        self.get_videos(session, out_dir)
        if include_eps_singles:
            self.get_albums(
                session,
                audio_format,
                out_dir,
                include_eps_singles=True,
                no_extra_files=no_extra_files,
            )
        self.get_albums(
            session,
            audio_format,
            out_dir,
            include_eps_singles=False,
            no_extra_files=no_extra_files,
        )

        if not no_extra_files:
            self.save_artist_image(session)
