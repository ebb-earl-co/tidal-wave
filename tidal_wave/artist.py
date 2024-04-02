from dataclasses import dataclass
import logging
from pathlib import Path
from typing import List, Optional

from requests import Session

from .album import Album
from .media import AudioFormat
from .models import (
    ArtistsAlbumsResponseJSON,
    ArtistsEndpointResponseJSON,
    ArtistsVideosResponseJSON,
)
from .requesting import (
    request_artists,
    request_artists_albums,
    request_artists_audio_works,
    request_artists_videos,
)
from .utils import download_cover_image
from .video import Video

logger = logging.getLogger("__name__")


@dataclass
class Artist:
    artist_id: int
    transparent: bool = False

    def set_metadata(self, session: Session):
        """This function requests from TIDAL API endpoint /artists and
        stores the results in self.metadata"""
        self.metadata: Optional[ArtistsEndpointResponseJSON] = request_artists(
            session=session, artist_id=self.artist_id, transparent=self.transparent
        )

    def save_artist_image(self, session: Session):
        """This method writes the bytes of self.metadata.picture to
        the file cover.jpg in self.artist_dir"""
        artist_image: Path = self.artist_dir / "cover.jpg"
        if not artist_image.exists():
            if self.metadata.picture is not None:
                download_cover_image(
                    session, self.metadata.picture, self.artist_dir, dimension=750
                )

    def set_albums(self, session: Session):
        """This method requests from TIDAL API endpoint /artists/albums and
        stores the results in self.albums"""
        self.albums: Optional[ArtistsAlbumsResponseJSON] = request_artists_albums(
            session=session, artist_id=self.artist_id, transparent=self.transparent
        )

    def set_audio_works(self, session: Session):
        """This method requests from TIDAL API endpoint
        /artists/albums?filter=EPSANDSINGLES and stores the results in self.albums"""
        self.albums: Optional[ArtistsAlbumsResponseJSON] = request_artists_audio_works(
            session=session, artist_id=self.artist_id, transparent=self.transparent
        )

    def set_videos(self, session: Session):
        """This method requests from TIDAL API endpoint /artists/videos and
        stores the results in self.videos"""
        self.videos: Optional[ArtistsVideosResponseJSON] = request_artists_videos(
            session=session, artist_id=self.artist_id, transparent=self.transparent
        )

    def set_artist_dir(self, out_dir: Path):
        """This method sets self.artist_dir and creates the directory on the file system
        if it does not exist"""
        self.name: str = self.metadata.name.replace("..", "")
        self.artist_dir = out_dir / self.name
        self.artist_dir.mkdir(parents=True, exist_ok=True)

    def get_albums(
        self,
        session: Session,
        audio_format: AudioFormat,
        out_dir: Path,
        include_eps_singles: bool,
        no_extra_files: bool,
    ) -> List[Optional[str]]:
        """This method first fetches the total albums on TIDAL's service
        corresponding to the artist with ID self.artist_id. Then, each of
        the albums (and, optionally, EPs and singles) is requested and
        written to subdirectories of out_dir"""
        if include_eps_singles:
            self.set_audio_works(session)
            logger.info(
                f"Starting attempt to get {self.albums.total_number_of_items} "
                "albums, EPs, and singles for artist with ID "
                f"{self.metadata.id},  '{self.name}'"
            )
        else:
            self.set_albums(session)
            logger.info(
                f"Starting attempt to get {self.albums.total_number_of_items} albums "
                f"for artist with ID {self.metadata.id}, '{self.name}'"
            )

        for i, a in enumerate(self.albums.items):
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
    ) -> List[Optional[str]]:
        """This method sets self.videos by calling self.set_videos() and
        then, for each video, instantiates a Video object and executes
        the object's .get() method"""
        self.set_videos(session)
        logger.info(
            f"Starting attempt to get {self.videos.total_number_of_items} videos "
            f"for artist with ID {self.metadata.id}, '{self.name}'"
        )
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
        include_eps_singles: bool,
        no_extra_files: bool,
    ):
        """This is the driver method of the class. It executes the other
        methods in order:
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
