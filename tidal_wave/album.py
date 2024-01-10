from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import List, Optional

from requests import Session

from .media import AudioFormat
from .models import (
    AlbumsEndpointResponseJSON,
    AlbumsItemsResponseJSON,
    AlbumsReviewResponseJSON,
)
from .requesting import request_albums, request_album_items, request_album_review
from .track import Track
from .utils import download_cover_image


@dataclass
class Album:
    album_id: int

    def __post_init__(self):
        self.album_dir: Optional[Path] = None
        self.album_cover_saved: bool = False

    def get_items(self, session: Session):
        """This method populates self.tracks by requesting from
        TIDAL albums/items endpoint."""
        album_items: AlbumsItemsResponseJSON = request_album_items(
            session=session, identifier=self.album_id
        )
        _items = album_items.items if album_items is not None else ()
        self.tracks = tuple(_item.item for _item in _items)

    def get_metadata(self, session: Session):
        """This method populates self.metadata by requesting from
        TIDAL /albums endpoint"""
        self.metadata: AlbumsEndpointResponseJSON = request_albums(
            session=session, identifier=self.album_id
        )

    def get_review(self, session: Session):
        """This method requests the review corresponding to self.album_id
        in TIDAL. If it exists, it is written to disk as AlbumReview.json
        in self.album_dir"""
        self.album_review: Optional[AlbumsReviewResponseJSON] = request_album_review(
            session=session, identifier=self.album_id
        )
        if self.album_review is not None:
            (self.album_dir / "AlbumReview.json").write_text(
                self.album_review.to_json()
            )

    def set_dir(self, out_dir: Path):
        """This method populates self.album_dir as a sub-subdirectory of
        out_dir: its parent directory is the name of the (main) artist of
        the album"""
        artist_substring: str = self.metadata.artist.name.replace("..", "")
        album_substring: str = (
            f"{self.metadata.name.replace('..', '')} "
            f"[{self.metadata.id}] [{self.metadata.release_date.year}]"
        )
        self.album_dir = out_dir / artist_substring / album_substring
        self.album_dir.mkdir(parents=True, exist_ok=True)

        if self.metadata.number_of_volumes > 1:
            for v in range(1, self.metadata.number_of_volumes + 1):
                volume_substring: str = f"Volume {v}"
                (out_dir / artist_substring / album_substring / volume_substring).mkdir(
                    parents=True, exist_ok=True
                )

    def save_cover_image(self, session: Session, out_dir: Path):
        """This method writes cover.jpg in self.album_dir via the 
        utils.download_cover_image() function. If successful,
        then self.album_cover_saved takes the value True"""
        if self.album_dir is None:
            self.set_dir(out_dir=out_dir)
        self.cover_path: Path = self.album_dir / "cover.jpg"
        if not self.cover_path.exists():
            download_cover_image(
                session=session,
                cover_uuid=self.metadata.cover,
                output_dir=self.album_dir,
            )
        else:
            self.album_cover_saved = True

    def get_tracks(
        self, session: Session, audio_format: AudioFormat, out_dir: Path
    ) -> List[Optional[str]]:
        """This method uses self.tracks to call track.Track.get() for each
        track in self.tracks. It uses the result of each of these calls to
        populate self.track_files"""
        track_files: List[str] = [None] * self.metadata.number_of_tracks
        for i, t in enumerate(self.tracks):  # type(t) is TracksEndpointResponseJSON
            track: Track = Track(track_id=t.id)

            track_files_value: Optional[str] = track.get(
                session=session,
                audio_format=audio_format,
                out_dir=out_dir,
                metadata=t,
                album=self.metadata,
            )
            track_files[i] = {track.metadata.track_number: track_files_value}
        else:
            self.track_files = track_files

    def dumps(self):
        """This method returns a JSON-like string of self.track_files"""
        return json.dumps(self.track_files)

    def dump(self, fp=sys.stdout):
        """This method writes to (by default) STDOUT a
        JSON-like string of self.track_files"""
        json.dump(self.track_files, fp)

    def get(
        self,
        session: Session,
        audio_format: AudioFormat,
        out_dir: Path,
        metadata: Optional[AlbumsEndpointResponseJSON] = None,
    ):
        """This method is the driver method of the class. It calls the
        other methods in order:
            1. get_metadata()  
            2. get_items()
            3. save_cover_image()
            4. get_review()
            5. get_tracks()
        """
        if metadata is None:
            self.get_metadata(session)
        else:
            self.metadata = metadata

        self.get_items(session)
        self.save_cover_image(session, out_dir)
        self.get_review(session)
        self.get_tracks(session, audio_format, out_dir)
