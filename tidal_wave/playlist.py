from dataclasses import dataclass
import json
import logging
import math
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from typing import Dict, List, Optional, Set, Tuple, Union

from .media import AudioFormat
from .models import (
    PlaylistsEndpointResponseJSON,
    TracksEndpointResponseJSON,
    VideosEndpointResponseJSON,
)
from .requesting import request_playlists
from .track import Track
from .utils import (
    download_cover_image,
    replace_illegal_characters,
    temporary_file,
    TIDAL_API_URL,
)
from .video import Video

import ffmpeg
import mutagen
from requests import HTTPError, Session

logger = logging.getLogger("__name__")


@dataclass
class Playlist:
    playlist_id: str  # UUID4
    transparent: bool = False

    def __post_init__(self):
        self.playlist_dir: Optional[Path] = None
        self.playlist_cover_saved: bool = False

    def set_metadata(self, session: Session):
        """Request from TIDAL API /playlists endpoint"""
        self.metadata: Optional[PlaylistsEndpointResponseJSON] = request_playlists(
            session=session, playlist_id=self.playlist_id, transparent=self.transparent
        )

        if self.metadata is None:
            return

        self.name = replace_illegal_characters(self.metadata.title)

    def set_items(self, session: Session):
        """Uses data from TIDAL API /playlists/items endpoint to
        populate self.items"""
        playlist_items: Optional[PlaylistsItemsResponseJSON] = get_playlist(
            session=session, playlist_id=self.playlist_id
        )
        if playlist_items is None:
            self.items = tuple()
        else:
            # For now, if playlist size, N, exceeds 100 items,
            # N items are returned, and all those between 101 and N
            # are simply None. It's a temporary fix before properly
            # handling paginated API requests, but it should stop
            # NoneType errors!
            self.items: Tuple[Optional[PlaylistItem]] = tuple(
                filter(None, playlist_items.items)
            )

    def set_playlist_dir(self, out_dir: Path):
        """Populates self.playlist_dir based on self.name, self.playlist_id"""
        playlist_substring: str = f"{self.name} [{self.playlist_id}]"
        self.playlist_dir: Path = out_dir / "Playlists" / playlist_substring
        self.playlist_dir.mkdir(parents=True, exist_ok=True)

    def save_cover_image(self, session: Session, out_dir: Path):
        """Requests self.metadata.image and attempts to write it to disk"""
        if self.playlist_dir is None:
            self.set_playlist_dir(out_dir=out_dir)
        self.cover_path: Path = self.playlist_dir / "cover.jpg"
        if not self.cover_path.exists():
            download_cover_image(
                session=session,
                cover_uuid=self.metadata.square_image,
                output_dir=self.playlist_dir,
                dimension=1080,
            )
        else:
            self.playlist_cover_saved = True

    def save_description(self):
        """Requests self.metadata.description and attempts to write it to disk"""
        self.description_path: Path = self.playlist_dir / "PlaylistDescription.txt"
        if self.metadata.description is not None and len(self.metadata.description) > 0:
            if not self.description_path.exists():
                self.description_path.write_text(f"{self.metadata.description}\n")

    def get_items(
        self, session: Session, audio_format: AudioFormat, no_extra_files: bool
    ):
        """Using either Track.get() or Video.get(), attempt to request
        the data for each track or video in self.items. If no_extra_files
        is True, do not attempt to retrieve or save any of: playlist
        description text, playlist m3u8 text, playlist cover image."""
        if len(self.items) == 0:
            return
        tracks_videos: list = [None] * len(self.items)
        for i, item in enumerate(self.items):
            if item is None:
                tracks_videos[i] = None
                continue
            elif isinstance(item, TracksEndpointResponseJSON):
                track: Track = Track(track_id=item.id, transparent=self.transparent)
                track.get(
                    session=session,
                    audio_format=audio_format,
                    out_dir=self.playlist_dir,
                    metadata=item,
                    no_extra_files=no_extra_files,
                )
                tracks_videos[i] = track
            elif isinstance(item, VideosEndpointResponseJSON):
                video: Video = Video(video_id=item.id, transparent=self.transparent)
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
            self.tracks_videos: Tuple[Tuple[int, Optional[Union[Track, Video]]]] = (
                tuple(tracks_videos)
            )
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

    def craft_m3u8_text(self):
        """This method creates a file called playlist.m3u8 in self.playlist_dir
        that is a standard M3U. Needs to be called after self.flatten_playlist_dir
        in order to be able to access self.files
        N.b. the already-written file is temporarily copied to a .mp4 version in a
        temporary directory because .m4a files cannot be read with mutagen."""
        m3u_text: str = (
            f"#EXTM3U\n#EXTENC:UTF-8\n#EXTIMG:{str(self.cover_path.absolute())}\n#PLAYLIST:{self.name}\n"
        )

        logger.info(
            f"Creating .m3u8 playlist file for Playlist with ID '{self.playlist_id}'"
        )
        for d in self.files:
            file: str = next(iter(d.values()))
            if file is None:
                continue
            elif file.endswith(".flac"):
                m = mutagen.File(file)
                artist: str = m.get("artist", [""])[0]
                title: str = m.get("title", [""])[0]
                extinf: str = (
                    f"#EXTINF:{math.ceil(m.info.length)},"
                    f"{artist} - {title}\n{file}\n"
                )
                m3u_text += extinf
            elif file.endswith(".mka"):
                m = mutagen.File(file)
                artist: str = m.get("ARTI", [""])[0]
                title: str = m.get("TITL", [""])[0]
                extinf: str = (
                    f"#EXTINF:{math.ceil(m.info.length)},"
                    f"{artist} - {title}\n{file}\n"
                )
                m3u_text += extinf
            elif file.endswith(".m4a"):
                # Mutagen cannot read .m4a files, so make a copy with all
                # of the metadata tags as a .mp4 in a temporary directory
                with temporary_file(suffix=".mp4") as tf:
                    ffmpeg.input(file, hide_banner=None, y=None).output(
                        tf.name,
                        acodec="copy",
                        vcodec="copy",
                        loglevel="quiet",
                    ).run()

                    m = mutagen.File(tf.name)
                    artist: str = m.get("\xa9ART", [""])[0]
                    title: str = m.get("\xa9nam", [""])[0]
                    extinf: str = (
                        f"#EXTINF:{math.ceil(m.info.length)},"
                        f"{artist} - {title}\n{file}\n"
                    )
                    m3u_text += extinf
            elif file.endswith(".mp4"):  # video files
                m = mutagen.mp4.MP4(file)
                artist: str = m.get("\xa9ART", [""])[0]
                title: str = m.get("\xa9nam", [""])[0]
                extinf: str = (
                    f"#EXTINF:{math.ceil(m.info.length)},"
                    f"{artist} - {title}\n{file}\n"
                )
                m3u_text += extinf
        else:
            return m3u_text

    def dumps(self):
        """This method emulates the stdlib json.dumps(). In particular,
        it returns the JSON-formatted string of the self.files attribute,
        which is an array of objects with one key each: the index in the
        playlist of the track or video, and the absolute file path to the
        track or video"""
        return json.dumps(self.files)

    def dump(self, fp=sys.stdout):
        """This method emulates the stdlib json.dump(). In particular,
        it sends to 'fp' the JSON-formatted string of the self.files attribute,
        which is an array of objects with one key each: the index in the
        playlist of the track or video, and the absolute file path to the
        track or video"""
        json.dump(self.files, fp)

    def get(
        self,
        session: Session,
        audio_format: AudioFormat,
        out_dir: Path,
        no_extra_files: bool,
    ):
        """The main method of this class, executing a number of other methods
        in a row:
          - self.set_metadata()
          - self.set_items()
          - self.set_playlist_dir()
          - self.get_items()
          - self.flatten_playlist_dir()
        Then, if no_extra_files is False,
          - self.save_cover_image()
          - self.save_description()
          - self.craft_m3u8_text()
        """
        self.set_metadata(session)

        if self.metadata is None:
            self.files = {}
            return

        self.set_items(session)
        self.set_playlist_dir(out_dir)

        if self.get_items(session, audio_format, no_extra_files) is None:
            logger.critical(f"Could not retrieve playlist with ID '{self.playlist_id}'")
            self.files = {}
            return

        self.flatten_playlist_dir()
        logger.info(f"Playlist files written to '{self.playlist_dir}'")

        if not no_extra_files:
            try:
                self.save_description()
            except Exception:
                pass
            else:
                logger.info(
                    "Playlist description written to "
                    f"{self.playlist_dir / 'PlaylistDescription.txt'}"
                )

            self.save_cover_image(session, out_dir)

            try:
                m3u8_text: str = self.craft_m3u8_text()
            except Exception as e:
                logger.warning(
                    "Unable to create playlist.m3u8 file for "
                    f"playlist with ID '{self.playlist_id}'"
                )
                logger.debug(e)
            else:
                (self.playlist_dir / "playlist.m3u8").write_text(m3u8_text)
                logger.info(
                    "Playlist M3U file written to "
                    f"{self.playlist_dir / 'playlist.m3u8'}"
                )

    def get_elements(
        self,
        session: Session,
        audio_format: AudioFormat,
        out_dir: Path,
        no_extra_files: bool,
    ):
        """The main method of this class when no_flatten is True at
        the program top level. It executes a number of other methods
        in a row:
          - self.set_metadata()
          - self.set_items()
        """
        self.set_metadata(session)

        if self.metadata is None:
            self.files = {}
            return

        self.set_items(session)
        if len(self.items) == 0:
            self.files = {}
            return
        else:
            files: List[Dict[int, Optional[str]]] = [None] * len(self.items)

        for i, item in enumerate(self.items):
            if item is None:
                files[i] = {i: None}
                continue
            elif isinstance(item, TracksEndpointResponseJSON):
                track: Track = Track(track_id=item.id, transparent=self.transparent)
                track_file: Optional[str] = track.get(
                    session=session,
                    audio_format=audio_format,
                    out_dir=out_dir,
                    metadata=item,
                    no_extra_files=no_extra_files,
                )
                files[i] = {i: track_file}
            elif isinstance(item, VideosEndpointResponseJSON):
                video: Video = Video(video_id=item.id, transparent=self.transparent)
                video_file: Optional[str] = video.get(
                    session=session,
                    out_dir=out_dir,
                    metadata=item,
                )
                files[i] = {i: video_file}
            else:
                files[i] = {i: None}
                continue
        else:
            self.files: List[Dict[int, Optional[str]]] = files


class TidalPlaylistException(Exception):
    pass


def request_playlist_items(session: Session, playlist_id: str) -> Optional[dict]:
    """Request from TIDAL API /playlists/items endpoint. If requests.HTTPError
    arises, warning is logged; upon this or any other exception, None is returned.
    If no exception arises from 'session'.get(), the requests.Response.json()
    object is returned."""
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
    playlists_response: Dict[str, Union[int, List[dict]]],
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
                    f"TidalPlaylistException: unable to parse playlist item {i} "
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
                    f"TidalPlaylistException: unable to parse playlist item {i} "
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
        playlists_items_response_json: Optional["PlaylistsItemsResponseJSON"] = (
            playlist_maker(playlists_response=playlists_response)
        )
    except Exception as e:
        logger.exception(TidalPlaylistException(e.args[0]))
    finally:
        return playlists_items_response_json


# union type for type hinting
PlaylistItem = Optional[
    Union["TracksEndpointResponseJSON", "VideosEndpointResponseJSON"]
]
