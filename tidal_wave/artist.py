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

    def set_metadata(self, session: Session):
        """This function requests from TIDAL API endpoint /artists and
        stores the results in self.metadata"""
        self.metadata: Optional[ArtistsEndpointResponseJSON] = request_artists(
            session, self.artist_id
        )

    def save_artist_image(self, session: Session):
        artist_image: Path = self.artist_dir / "cover.jpg"
        if not artist_image.exists():
            download_cover_image(
                session, self.metadata.picture, self.artist_dir, dimension=750
            )

    def set_albums(self, session: Session):
        """This function requests from TIDAL API endpoint /artists/albums and
        stores the results in self.albums"""
        self.albums: Optional[ArtistsAlbumsResponseJSON] = request_artists_albums(
            session, self.artist_id
        )

    def set_audio_works(self, session: Session):
        """This function requests from TIDAL API endpoint
        /artists/albums?filter=EPSANDSINGLES and stores the results in self.albums"""
        self.albums: Optional[ArtistsAlbumsResponseJSON] = request_artists_audio_works(
            session, self.artist_id
        )

    def set_videos(self, session: Session):
        """This function requests from TIDAL API endpoint /artists/videos and
        stores the results in self.albums"""
        self.videos: Optional[ArtistsVideosResponseJSON] = request_artists_videos(
            session, self.artist_id
        )

    def set_dir(self, out_dir: Path):
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
        include_eps_singles: bool = False,
    ) -> List[Optional[str]]:
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
            )

    def get_videos(
        self,
        session: Session,
        out_dir: Path,
    ) -> List[Optional[str]]:
        """This method sets self.videos by calling self.set_videos()
        then, for each video, instantiates a Video object and executes
        video.get()"""
        self.set_videos(session)
        logger.info(
            f"Starting attempt to get {self.videos.total_number_of_items} videos "
            f"for artist with ID {self.metadata.id}, '{self.name}'"
        )
        for i, v in enumerate(self.videos.items):
            video: Video = Video(video_id=v.id)
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
    ):
        self.set_metadata(session)
        self.set_dir(out_dir)
        self.save_artist_image(session)
        self.get_videos(session, out_dir)
        self.get_albums(session, audio_format, out_dir, include_eps_singles)
