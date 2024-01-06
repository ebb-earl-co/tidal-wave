from dataclasses import dataclass
import json
import logging
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from typing import Dict, List, Optional, Set, Tuple, Union

from requests import HTTPError, Session

from .media import AudioFormat
from .models import (
    PlaylistsEndpointResponseJSON,
    TracksEndpointResponseJSON,
    VideosEndpointResponseJSON,
)
from .requesting import request_playlists
from .track import Track
from .utils import download_cover_image, TIDAL_API_URL
from .video import Video

logger = logging.getLogger("__name__")


@dataclass
class Playlist:
    playlist_id: str  # UUID4

    def __post_init__(self):
        self.playlist_dir: Optional[Path] = None
        self.playlist_cover_saved: bool = False

    def get_metadata(self, session: Session):
        """Request from TIDAL API /playlists endpoint"""
        self.metadata: Optional[PlaylistsEndpointResponseJSON] = request_playlists(
            session=session, identifier=self.playlist_id
        )
        self.name = (
            self.metadata.title.replace("/", "_")
            .replace("|", "_")
            .replace(":", " -")
            .replace('"', "")
            .replace("..", "")
        )

    def set_items(self, session: Session):
        """Uses data from TIDAL API /playlists/items endpoint to
        populate self.items"""
        playlist_items: Optional[PlaylistsItemsResponseJSON] = get_playlist(
            session=session, playlist_id=self.playlist_id
        )
        if playlist_items is None:
            self.items = tuple()
        else:
            self.items: Tuple[Optional[PlaylistItem]] = tuple(playlist_items.items)

    def set_dir(self, out_dir: Path):
        """Populates self.playlist_dir based on self.name, self.playlist_id"""
        playlist_substring: str = f"{self.name} [{self.playlist_id}]"
        self.playlist_dir: Path = out_dir / "Playlists" / playlist_substring
        self.playlist_dir.mkdir(parents=True, exist_ok=True)

    def save_cover_image(self, session: Session, out_dir: Path):
        """Requests self.metadata.image and attempts to write it to disk"""
        if self.playlist_dir is None:
            self.set_dir(out_dir=out_dir)
        self.cover_path: Path = self.playlist_dir / "cover.jpg"
        if not self.cover_path.exists():
            download_cover_image(
                session=session,
                cover_uuid=self.metadata.image,
                output_dir=self.playlist_dir,
                dimension=1080,
            )
        else:
            self.playlist_cover_saved = True

    def save_description(self):
        """Requests self.metadata.description and attempts to write it to disk"""
        description_path: Path = self.playlist_dir / "PlaylistDescription.txt"
        if self.metadata.description is not None and len(self.metadata.description) > 0:
            if not description_path.exists():
                description_path.write_text(f"{self.metadata.description}\n")

    def get_items(self, session: Session, audio_format: AudioFormat):
        """Using either Track.get() or Video.get(), attempt to request
        the data for each track or video in self.items"""
        if len(self.items) == 0:
            return
        tracks_videos: list = [None] * len(self.items)
        for i, item in enumerate(self.items):
            if item is None:
                tracks_videos[i] = None
                continue
            elif isinstance(item, TracksEndpointResponseJSON):
                track: Track = Track(track_id=item.id)
                track.get(
                    session=session,
                    audio_format=audio_format,
                    out_dir=self.playlist_dir,
                    metadata=item,
                )
                tracks_videos[i] = track
            elif isinstance(item, VideosEndpointResponseJSON):
                video: Video = Video(video_id=item.id)
                video.get(
                    session=session,
                    out_dir=self.playlist_dir,
                    metadata=item,
                )
                tracks_videos[i] = video
            else:
                tracks_videos[i] = None
                continue
        else:
            self.tracks_videos: Tuple[
                Tuple[int, Optional[Union[Track, Video]]]
            ] = tuple(tracks_videos)
        return tracks_videos

    def flatten_playlist_dir(self):
        """When self.get_items() is called, the tracks and/or videos in
        self.items are downloaded using their self-contained .get() logic;
        this means that they will be downloaded to albums. This function
        "flattens" self.playlist_dir, meaning that it moves all downloaded
        audio and video files to self.playlist_dir, and removes the various
        subdirectories created"""
        files: List[Dict[int, Optional[str]]] = [None] * len(self.tracks_videos)
        if len(self.tracks_videos) == 0:
            return
        subdirs: Set[Path] = set()

        for i, tv in enumerate(self.tracks_videos, 1):
            if getattr(tv, "outfile") is None:
                try:
                    getattr(tv, "album_dir")
                except AttributeError:
                    pass
                else:
                    subdirs.add(tv.album_dir)
                    subdirs.add(tv.album_dir.parent)
                files[i - 1] = {i: None}
                continue

            _path: Optional[Path] = Path(tv.outfile) if tv is not None else None
            # if the item never got turned into a track or video
            if _path is None:
                files[i - 1] = {i: None}
                continue

            # if the track or video didn't download
            if _path.exists():
                if _path.stat().st_size == 0:
                    files[i - 1] = {i: None}
                    continue
            else:
                files[i - 1] = {i: None}
                continue

            # otherwise, move files and clean up
            if isinstance(tv, Track):
                new_path: Path = self.playlist_dir / f"{i:03d} - {tv.trackname}"
                new_path.write_bytes(_path.read_bytes())
                _path.unlink()
                files[i - 1] = {i: str(new_path.absolute())}
            elif isinstance(tv, Video):
                new_path: Path = self.playlist_dir / f"{i:03d} - {_path.name}"
                new_path.write_bytes(_path.read_bytes())
                _path.unlink()
                files[i - 1] = {i: str(new_path.absolute())}
        else:
            self.files: List[Dict[int, Optional[str]]] = files

        # Find all subdirectories written to
        subdirs: Set[Path] = set()
        for tv in self.tracks_videos:
            if isinstance(tv, Track):
                try:
                    getattr(tv, "album_dir")
                except AttributeError:
                    pass
                else:
                    subdirs.add(tv.album_dir)
                    subdirs.add(tv.album_dir.parent)
            elif isinstance(tv, Video):
                subdirs.add(tv.artist_dir)

        # Copy all artist images, artist bio JSON files out
        # of subdirs
        artist_images: Set[Path] = set()
        for subdir in subdirs:
            for p in subdir.glob("*.jpg"):
                if p.name == "cover.jpg":
                    continue
                artist_images.add(p)
        else:
            for artist_image_path in artist_images:
                if artist_image_path.exists():
                    shutil.copyfile(
                        artist_image_path.absolute(),
                        self.playlist_dir / artist_image_path.name,
                    )

        artist_bios: Set[Path] = set()
        for subdir in subdirs:
            for p in subdir.glob("*bio.json"):
                artist_bios.add(p)
        else:
            for artist_bio_path in artist_bios:
                if artist_bio_path.exists():
                    shutil.copyfile(
                        artist_bio_path.absolute(),
                        self.playlist_dir / artist_bio_path.name,
                    )

        # Remove all subdirs
        for subdir in subdirs:
            if subdir.exists():
                shutil.rmtree(subdir)
        else:
            return self.playlist_dir

    def dumps(self):
        return json.dumps(self.files)

    def dump(self, fp=sys.stdout):
        json.dump(self.files, fp)

    def get(self, session: Session, audio_format: AudioFormat, out_dir: Path):
        """The main method of this class, executing a number of other methods
        in a row:
          - self.get_metadata()
          - self.set_items()
          - self.set_dir()
          - self.save_cover_image()
          - self.save_description()
          - self.get_items()
          - self.flatten_playlist_dir()
        """
        self.get_metadata(session)
        self.set_items(session)
        self.set_dir(out_dir)
        self.save_cover_image(session, out_dir)
        try:
            self.save_description()
        except Exception:
            pass

        _get_items = self.get_items(session, audio_format)
        if _get_items is None:
            logger.critical(f"Could not retrieve playlist with ID '{self.playlist_id}'")
            return
        self.flatten_playlist_dir()
        logger.info(f"Playlist files written to '{self.playlist_dir}'")


class TidalPlaylistException(Exception):
    pass


def request_playlist_items(session: Session, playlist_id: str) -> Optional[dict]:
    """Request from TIDAL API /playlists/items endpoint."""
    url: str = f"{TIDAL_API_URL}/playlists/{playlist_id}/items"
    kwargs: dict = {"url": url}
    kwargs["params"] = {"limit": 100}
    kwargs["headers"] = {"Accept": "application/json"}

    data: Optional[dict] = None
    logger.info(f"Requesting from TIDAL API: playlists/{playlist_id}/items")
    with session.get(**kwargs) as resp:
        try:
            resp.raise_for_status()
        except HTTPError as he:
            if resp.status_code == 404:
                logger.warning(
                    f"404 Client Error: not found for TIDAL API endpoint playlists/{playlist_id}/items"
                )
            else:
                logger.exception(he)
        else:
            data = resp.json()
            logger.debug(
                f"{resp.status_code} response from TIDAL API to request: playlists/{playlist_id}/items"
            )
        finally:
            return data


@dataclass(frozen=True)
class PlaylistsItemsResponseJSON:
    """The response from the TIDAL API endpoint /playlists/<ID>/items
    is modeled by this class."""

    limit: int
    offset: int
    total_number_of_items: int
    items: Tuple[
        Optional[Union["TracksEndpointResponseJSON", "VideosEndpointResponseJSON"]]
    ]


def playlist_maker(
    playlists_response: Dict[str, Union[int, List[dict]]]
) -> "PlaylistsItemsResponseJSON":
    """This function massages the response from the TIDAL API endpoint
    playlists/items into a format that PlaylistsItemsResponseJSON.from_dict()
    can ingest. Returns a PlaylistsItemsResponseJSON instance"""
    init_args: dict = {}
    init_args["limit"] = playlists_response.get("limit")
    init_args["offset"] = playlists_response.get("offset")
    init_args["total_number_of_items"] = playlists_response.get("totalNumberOfItems")

    items: Tuple[SimpleNamespace] = tuple(
        SimpleNamespace(**d) for d in playlists_response["items"]
    )
    if len(items) == 0:
        return

    playlist_items: List[
        Optional[Union["TracksEndpointResponseJSON", "VideosEndpointResponseJSON"]]
    ] = [None] * init_args["total_number_of_items"]

    for i, namespace in enumerate(items):
        if namespace.type == "track":
            try:
                playlist_item = TracksEndpointResponseJSON.from_dict(namespace.item)
            except Exception as e:
                logger.warning(
                    f"TidalPlaylistException: unable to parse playlist item [i] "
                    f"with type '{namespace.type}'"
                )
                logger.debug(e)
                # value stays None
            else:
                playlist_items[i] = playlist_item
        elif namespace.type == "video":
            try:
                playlist_item = VideosEndpointResponseJSON.from_dict(namespace.item)
            except Exception as e:
                logger.warning(
                    f"TidalPlaylistException: unable to parse playlist item [i] "
                    f"with type '{namespace.type}'"
                )
                logger.debug(e)
                # value stays None
            else:
                playlist_items[i] = playlist_item
        else:
            continue  # value stays None
    else:
        init_args["items"] = tuple(playlist_items)

    return PlaylistsItemsResponseJSON(**init_args)


def get_playlist(
    session: Session, playlist_id: str
) -> Optional["PlaylistsItemsResponseJSON"]:
    """The pattern for playlist items retrieval does not follow the
    requesting.request_* functions, hence its implementation here.
    """
    playlists_items_response_json: Optional["PlaylistsItemsResponseJSON"] = None
    try:
        playlists_response: dict = request_playlist_items(
            session=session, playlist_id=playlist_id
        )
        playlists_items_response_json: Optional[
            "PlaylistsItemsResponseJSON"
        ] = playlist_maker(playlists_response=playlists_response)
    except Exception as e:
        logger.exception(TidalPlaylistException(e.args[0]))
    finally:
        return playlists_items_response_json


# union type for type hinting
PlaylistItem = Optional[
    Union["TracksEndpointResponseJSON", "VideosEndpointResponseJSON"]
]
