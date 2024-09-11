"""Represent an album in the reckoning of TIDAL API."""

from __future__ import annotations

import contextlib
import json
import logging
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from io import TextIOWrapper
    from pathlib import Path

    from .media import AudioFormat
    from .models import (
        AlbumsCreditsResponseJSON,
        AlbumsEndpointResponseJSON,
        AlbumsItemsResponseJSON,
        AlbumsReviewResponseJSON,
        TracksEndpointResponseJSON,
    )
from requests import RequestException, Session

from .requesting import (
    request_album_review,
    request_albums,
    request_albums_credits,
    request_albums_items,
)
from .track import Track
from .utils import IMAGE_URL, download_cover_image

logger = logging.getLogger("__name__")


@dataclass
class Album:
    """Class to represent an album in the TIDAL API.

    It just needs the album's ID and a Boolean as arguments to the
    constructor; the Boolean specifies whether to write all JSON
    responses from the TIDAL API to disk, for transparency's sake.

    Methods, e.g. `set_tracks()`, are germane to retrieving data from the
    TIDAL API.
    """

    album_id: int
    transparent: bool = False

    def __post_init__(self) -> None:
        """After dataclass's __init__() runs, this method sets two attributes.

        The attributes will be updated during further method calls.
        """
        self.album_dir: Path | None = None
        self.album_cover_saved: bool = False

    def set_tracks(self, session: Session) -> None:
        """Populate the `tracks` attribute of `self`.

        The attribute is populated by requesting from TIDAL API's
        albums/items endpoint and transforming the response JSON.
        """
        album_items: AlbumsItemsResponseJSON | None = request_albums_items(
            session=session,
            album_id=self.album_id,
            transparent=self.transparent,
        )
        _items = album_items.items if album_items is not None else []
        if self.metadata.number_of_tracks > len(_items):
            items_to_retrieve: int = self.metadata.number_of_tracks - len(_items)
            offset: int = 100
            while items_to_retrieve > 0:
                airj: AlbumsItemsResponseJSON | None = request_albums_items(
                    session=session,
                    album_id=self.album_id,
                    transparent=self.transparent,
                    offset=offset,
                )
                if (airj is not None) and (airj.items is not None):
                    _items += airj.items
                    offset += 100
                    items_to_retrieve -= 100
                else:
                    msg: str = (
                        f"Could not retrieve more than {len(_items)} "
                        f"tracks of album '{self.album_id}'. Continuing "
                        "without the remaining "
                        f"{self.metadata.number_of_tracks - len(_items)}"
                    )
                    logger.warning(msg)

        self.tracks: tuple[TracksEndpointResponseJSON] = tuple(
            _item.item for _item in _items
        )

    def set_metadata(self, session: Session) -> None:
        """Set the attribute `metadata` of `self.

        The attribute is populated by requesting from TIDAL API /albums
        endpoint and converting the response JSON.
        """
        self.metadata: AlbumsEndpointResponseJSON = request_albums(
            session=session,
            album_id=self.album_id,
            transparent=self.transparent,
        )

    def set_album_review(self, session: Session) -> None:
        """Request the review text corresponding to self.album_id.

        If an album review exists, it is written to disk as AlbumReview.json
        in self.album_dir.
        """
        self.album_review: AlbumsReviewResponseJSON | None = request_album_review(
            session=session,
            album_id=self.album_id,
            transparent=self.transparent,
        )
        if self.album_review is not None:
            (self.album_dir / "AlbumReview.json").write_text(
                self.album_review.to_json(),
            )

    def set_album_credits(self, session: Session) -> None:
        """Request the album's top-level credits from TIDAL API.

        An album's credits are distinct from each track's credits. The JSON
        data returned from the TIDAL API is converted and stored as
        self.album_credits. If the JSON data returned is not empty,
        then it is written to the file AlbumCredits.json in self.album_dir.
        """
        self.album_credits: AlbumsCreditsResponseJSON | None = request_albums_credits(
            session=session,
            album_id=self.album_id,
            transparent=self.transparent,
        )
        if self.album_credits is not None:
            num_credit: int = len(self.album_credits.credit)
            if num_credit == 0:
                _msg: str = (
                    "No album credits returned from TIDAL API "
                    f"for album {self.album_id}"
                )
                logger.warning(_msg)
            else:
                ac_file: Path = (self.album_dir / "AlbumCredits.json").absolute()
                with ac_file.open("w") as fp:
                    json.dump(obj=self.album_credits.credit, fp=fp)

    def set_album_dir(self, out_dir: Path) -> None:
        """Populate the attribute `album_dir` of `self`.

        Self.album_dir is a sub-subdirectory of out_dir; i.e.
        out_dir/
            <name of the main artist of the album>/
                album_dir/
        """
        artist_substring: str = self.metadata.artist.name.replace("..", "").replace(
            "/",
            "and",
        )
        album_substring: str = (
            f"{self.metadata.name.replace('..', '')} "
            f"[{self.metadata.id}] [{self.metadata.release_date.year}]"
        )
        self.album_dir = out_dir / artist_substring / album_substring
        self.album_dir.mkdir(parents=True, exist_ok=True)
        # Create cover_path here, even if the API
        # does not return a cover, to avoid AttributeError later
        self.cover_path: Path = self.album_dir / "cover.jpg"

        if self.metadata.number_of_volumes > 1:
            for v in range(1, self.metadata.number_of_volumes + 1):
                volume_substring: str = f"Volume {v}"
                (out_dir / artist_substring / album_substring / volume_substring).mkdir(
                    parents=True,
                    exist_ok=True,
                )

    def save_cover_image(self, session: Session, out_dir: Path) -> None:
        """Write a file named cover.jpg in self.album_dir.

        This is achieved via the utils.download_cover_image() function.
        If successful, then self.album_cover_saved is set to True.
        """
        if self.album_dir is None:
            self.set_album_dir(out_dir=out_dir)
        if not self.cover_path.exists():
            download_cover_image(
                session=session,
                cover_uuid=self.metadata.cover,
                output_dir=self.album_dir,
            )
        else:
            self.album_cover_saved = True

    def original_album_cover(self, session: Session) -> None:
        """Write to disk the "original" album cover of a TIDAL album.

        For most albums, TIDAL features the "original", or highest-resolution
        possible image file. This JPEG can be too large to be embedded into FLAC tracks:
        however, it is ideal to have for music archiving purposes.

        This method requests the original cover and overwrites the smaller, 1280x1280
        image that is embedded into each track file. The filename returned by the TIDAL
        API is consistently origin.jpg.

        It is *probably* okay to get this URL in a track.Track method, as HTTP requests
        are cached, so e.g. executing this method for each track in an album won't
        result in many redundant GET requests.
        """
        origin_jpg_url: str = (
            IMAGE_URL % f"{self.metadata.cover.replace('-', '/')}/origin"
        )
        with session.get(url=origin_jpg_url, headers={"Accept": "image/jpeg"}) as resp:
            try:
                resp.raise_for_status()
            except RequestException as re:
                _msg: str = (
                    "Could not retrieve origin.jpg from TIDAL "
                    f"due to error '{re.args[0]}'"
                )
                logger.warning(_msg)
            else:
                (self.album_dir / "cover.jpg").write_bytes(resp.content)

    def get_tracks(
        self,
        session: Session,
        audio_format: AudioFormat,
        out_dir: Path,
        *,
        no_extra_files: bool,
    ) -> list[str | None]:
        """Call track.Track.get() for each track object in self.tracks.

        The result of each of these calls populates self.track_files.
        """
        track_files: list[str | None] = [None] * self.metadata.number_of_tracks
        for i, t in enumerate(self.tracks):  # type(t) is TracksEndpointResponseJSON
            track: Track = Track(track_id=t.id, transparent=self.transparent)

            track_files_value: str | None = track.get(
                session=session,
                audio_format=audio_format,
                out_dir=out_dir,
                metadata=t,
                album=self.metadata,
                no_extra_files=no_extra_files,
                origin_jpg=False,
            )
            track_files[i] = {track.metadata.track_number: track_files_value}

        self.track_files = track_files

    def dumps(self) -> str:
        """Return a JSON-like string representation of self.track_files."""
        return json.dumps(self.track_files)

    def dump(self, fp: TextIOWrapper = sys.stdout) -> None:
        """Write to `fp` (by default, STDOUT) a JSON-like string of self.track_files."""
        json.dump(self.track_files, fp)

    def get(
        self,
        session: Session,
        audio_format: AudioFormat,
        out_dir: Path,
        metadata: AlbumsEndpointResponseJSON | None = None,
        *,
        no_extra_files: bool = False,
    ) -> None:
        """Execute other methods of self in sequence.

        That is:
            1. set_metadata()
            2. set_tracks()
            3. save_cover_image()
            4. set_album_review()
            5. get_tracks()
        """
        if metadata is None:
            self.set_metadata(session)
        else:
            self.metadata = metadata

        if self.metadata is None:
            self.track_files = {}
            return

        self.set_tracks(session)

        self.set_album_dir(out_dir)

        if self.metadata.cover != "":  # None was sent from the API
            self.save_cover_image(session, out_dir)
        else:
            _msg: str = (
                "No cover image was returned from TIDAL API "
                f"for album {self.album_id}"
            )
            logger.warning(_msg)

        self.get_tracks(session, audio_format, out_dir, no_extra_files=no_extra_files)

        if not no_extra_files:
            self.set_album_review(session)
            self.set_album_credits(session)
            self.original_album_cover(session)
        else:
            with contextlib.suppress(FileNotFoundError):
                self.cover_path.unlink()
