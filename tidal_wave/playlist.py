"""Represent a playlist in the reckoning of the TIDAL API."""

from __future__ import annotations

import json
import logging
import math
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from uuid import uuid4

import ffmpeg
import mutagen
from requests import HTTPError, Session

from .models import (
    PlaylistsEndpointResponseJSON,
    TracksEndpointResponseJSON,
    VideosEndpointResponseJSON,
)
from .requesting import request_playlists
from .track import Track
from .utils import (
    TIDAL_API_URL,
    download_cover_image,
    replace_illegal_characters,
    temporary_file,
)
from .video import Video

if TYPE_CHECKING:
    from .media import AudioFormat

logger = logging.getLogger("__name__")


@dataclass
class Playlist:
    playlist_id: str  # UUID4
    transparent: bool = False

    def __post_init__(self):
        self.playlist_dir: Path | None = None
        self.playlist_cover_saved: bool = False

    def set_metadata(self, session: Session) -> None:
        """Request from TIDAL API /playlists endpoint."""
        self.metadata: PlaylistsEndpointResponseJSON | None = request_playlists(
            session=session,
            playlist_id=self.playlist_id,
            transparent=self.transparent,
        )

        if self.metadata is None:
            return

        self.name = replace_illegal_characters(self.metadata.title)

    def set_items(self, session: Session):
        """Populate self.items using data from TIDAL API /playlists/items endpoint.

        If 'totalNumberOfItems' field returned
        has value greater than 100, multiple requests of size <= 100 will be
        sent to the endpoint until all items for the playlist are retrieved.
        """
        playlist_items: PlaylistsItemsResponseJSON | None = retrieve_playlist_items(
            session=session, playlist_id=self.playlist_id,
        )
        if playlist_items is None:
            self.items = ()
        else:
            self.items: tuple[PlaylistItem] = tuple(
                filter(None, playlist_items.items),
            )

    def set_playlist_dir(self, out_dir: Path):
        """Populate self.playlist_dir based on self.name, self.playlist_id."""
        playlist_substring: str = f"{self.name} [{self.playlist_id}]"
        self.playlist_dir: Path = out_dir / "Playlists" / playlist_substring
        self.playlist_dir.mkdir(parents=True, exist_ok=True)

    def save_cover_image(self, session: Session, out_dir: Path):
        """Request self.metadata.image and attempts to write it to disk."""
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
        """Request self.metadata.description and attempts to write it to disk."""
        self.description_path: Path = self.playlist_dir / "PlaylistDescription.txt"
        if (
            self.metadata.description is not None
            and len(self.metadata.description) > 0
            and not self.description_path.exists()
        ):
            self.description_path.write_text(f"{self.metadata.description}\n")

    def get_items(
        self,
        session: Session,
        audio_format: AudioFormat,
        no_extra_files: bool,
    ) -> tuple[Track | Video | None] | None:
        """Using either Track.get() or Video.get(), attempt to request
        the data for each track or video in self.items. If no_extra_files
        is True, do not attempt to retrieve or save any of: playlist
        description text, playlist m3u8 text, playlist cover image."""
        if len(self.items) == 0:
            return None
        tracks_videos: list = [None] * len(self.items)
        for i, item in enumerate(self.items):
            if item is None:
                tracks_videos[i] = None
                continue
            if isinstance(item, TracksEndpointResponseJSON):
                track: Track = Track(track_id=item.id, transparent=self.transparent)
                track.get(
                    session=session,
                    audio_format=audio_format,
                    out_dir=self.playlist_dir,
                    metadata=item,
                    no_extra_files=no_extra_files,
                    origin_jpg=False,
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
        self.tracks_videos: tuple[Track | Video | None] = tuple(tracks_videos)
        return tracks_videos

    def flatten_playlist_dir(self):
        """When self.get_items() is called, the tracks and/or videos in
        self.items are downloaded using their self-contained .get() logic;
        this means that they will be downloaded to albums. This function
        "flattens" self.playlist_dir, meaning that it moves all downloaded
        audio and video files to self.playlist_dir, and removes the various
        subdirectories created"""
        files: list[dict[int, str | None]] = [None] * len(self.tracks_videos)
        if len(self.tracks_videos) == 0:
            return None
        subdirs: set[Path] = set()

        for i, tv in enumerate(self.tracks_videos, 1):
            if tv.outfile is None:
                try:
                    _ = tv.album_dir
                except AttributeError:
                    pass
                else:
                    subdirs.add(tv.album_dir)
                    subdirs.add(tv.album_dir.parent)
                files[i - 1] = {i: None}
                continue

            _path: Path | None = Path(tv.outfile) if tv is not None else None
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
        self.files: list[dict[int, str | None]] = files

        # Find all subdirectories written to
        for tv in self.tracks_videos:
            if isinstance(tv, Track):
                try:
                    _ = tv.album_dir
                except AttributeError:
                    pass
                else:
                    subdirs.add(tv.album_dir)
                    subdirs.add(tv.album_dir.parent)
            elif isinstance(tv, Video):
                subdirs.add(tv.artist_dir)

        # Copy all artist images, artist bio JSON files out
        # of subdirs
        artist_images: set[Path] = set()
        for subdir in subdirs:
            for p in subdir.glob("*.jpg"):
                if p.name == "cover.jpg":
                    continue
                artist_images.add(p)
        for artist_image_path in artist_images:
            if artist_image_path.exists():
                shutil.copyfile(
                    artist_image_path.absolute(),
                    self.playlist_dir / artist_image_path.name,
                )

        artist_bios: set[Path] = set()
        for subdir in subdirs:
            for p in subdir.glob("*bio.json"):
                artist_bios.add(p)
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
        return self.playlist_dir

    def craft_m3u8_text(self):
        """This method creates a file called playlist.m3u8 in self.playlist_dir
        that is a standard M3U. Needs to be called after self.flatten_playlist_dir
        in order to be able to access self.files
        N.b. the already-written file is temporarily copied to a .mp4 version in a
        temporary directory because .m4a files cannot be read with mutagen."""
        m3u_text: str = f"#EXTM3U\n#EXTENC:UTF-8\n#EXTIMG:{str(self.cover_path.absolute())}\n#PLAYLIST:{self.name}\n"

        _msg: str = (
            f"Creating .m3u8 playlist file for Playlist with ID '{self.playlist_id}'"
        )
        logger.info(_msg)
        for d in self.files:
            file: str = next(iter(d.values()))
            if file is None:
                continue
            if file.endswith(".flac"):
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
        return m3u_text

    def dumps(self) -> str:
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
        """Execute a number of other methods in a row.

        The methods are:
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
            _msg: str = f"Could not retrieve playlist with ID '{self.playlist_id}'"
            logger.critical(_msg)
            self.files = {}
            return

        self.flatten_playlist_dir()
        _msg: str = f"Playlist files written to '{self.playlist_dir}'"
        logger.info(_msg)

        if not no_extra_files:
            try:
                self.save_description()
            except Exception:
                logger.exception()
            else:
                _msg: str = (
                    "Playlist description written to "
                    f"{self.playlist_dir / 'PlaylistDescription.txt'}"
                )
                logger.info(_msg)

            self.save_cover_image(session, out_dir)

            try:
                m3u8_text: str = self.craft_m3u8_text()
            except Exception as e:
                _msg: str = (
                    "Unable to create playlist.m3u8 file for "
                    f"playlist with ID '{self.playlist_id}'"
                )
                logger.warning(_msg)
                logger.debug(e)
            else:
                (self.playlist_dir / "playlist.m3u8").write_text(m3u8_text)
                _msg: str = (
                    "Playlist M3U file written to "
                    f"{self.playlist_dir / 'playlist.m3u8'}"
                )
                logger.info(_msg)

    def get_elements(
        self,
        session: Session,
        audio_format: AudioFormat,
        out_dir: Path,
        no_extra_files: bool,
    ) -> None:
        """Execute a number of other methods in a row.

        The main method of this class when no_flatten is True at
        the program top level. The methods executed are:
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
        files: list[dict[int, str | None]] = [None] * len(self.items)

        for i, item in enumerate(self.items):
            if item is None:
                files[i] = {i: None}
                continue
            if isinstance(item, TracksEndpointResponseJSON):
                track: Track = Track(track_id=item.id, transparent=self.transparent)
                track_file: str | None = track.get(
                    session=session,
                    audio_format=audio_format,
                    out_dir=out_dir,
                    metadata=item,
                    no_extra_files=no_extra_files,
                    origin_jpg=False,
                )
                files[i] = {i: track_file}
            elif isinstance(item, VideosEndpointResponseJSON):
                video: Video = Video(video_id=item.id, transparent=self.transparent)
                video_file: str | None = video.get(
                    session=session,
                    out_dir=out_dir,
                    metadata=item,
                )
                files[i] = {i: video_file}
            else:
                files[i] = {i: None}
                continue
        self.files: list[dict[int, str | None]] = files


class TidalPlaylistError(Exception):
    """Catch-all custom exception for retrieval of playlist data from TIDAL API."""


def request_playlists_items(
    session: Session,
    playlist_id: str,
    offset: int | None = None,
    transparent: bool = False,
) -> dict | None:
    """Request from TIDAL API /playlists/items endpoint. If requests.HTTPError
    arises, warning is logged; upon this or any other exception, None is returned.
    If no exception arises from 'session'.get(), the requests.Response.json()
    object is returned. If transparent is True, all JSON responses from the API
    are written to disk"""
    url: str = f"{TIDAL_API_URL}/playlists/{playlist_id}/items"
    kwargs: dict = {"url": url}
    kwargs["params"] = (
        {"limit": 100} if offset is None else {"limit": 100, "offset": offset}
    )
    kwargs["headers"] = {"Accept": "application/json"}
    json_name: str = f"playlists-{playlist_id}-items_{uuid4().hex}.json"

    data: dict | None = None
    _msg: str = f"Requesting from TIDAL API: playlists/{playlist_id}/items"
    logger.info(_msg)
    with session.get(**kwargs) as r:
        try:
            r.raise_for_status()
        except HTTPError:
            if r.status_code == 404:
                _msg: str = (
                    "404 Client Error: not found for TIDAL API endpoint "
                    f"playlists/{playlist_id}/items"
                )
                logger.warning(_msg)
            else:
                logger.exception()

        _msg: str = (
            f"{r.status_code} response from TIDAL API to request: "
            f"playlists/{playlist_id}/items"
        )
        if transparent:
            Path(json_name).write_text(
                json.dumps(r.json(), ensure_ascii=True, indent=4, sort_keys=True),
            )
        data = r.json()
        logger.debug(_msg)
        return data


@dataclass(frozen=True)
class PlaylistsItemsResponseJSON:
    """Represent the response from the TIDAL API endpoint /playlists/<ID>/items."""

    limit: int
    offset: int
    total_number_of_items: int
    items: tuple[TracksEndpointResponseJSON | VideosEndpointResponseJSON | None]


def playlists_items_response_json_maker(
    playlists_response: dict[str, int | list[dict]],
) -> PlaylistsItemsResponseJSON | None:
    """This function massages the response from the TIDAL API endpoint
    /playlists/items into a format that PlaylistsItemsResponseJSON.__init__()
    can ingest, and then returns a PlaylistsItemsResponseJSON instance"""
    init_args: dict[str, int | None] = {
        "limit": playlists_response.get("limit"),
        "offset": playlists_response.get("offset"),
        "total_number_of_items": playlists_response.get("totalNumberOfItems"),
    }

    items: tuple[SimpleNamespace] = tuple(
        SimpleNamespace(**d) for d in playlists_response["items"]
    )
    if len(items) == 0:
        return None

    playlist_items: list[
        TracksEndpointResponseJSON | VideosEndpointResponseJSON | None
    ] = [None] * init_args["total_number_of_items"]

    for i, namespace in enumerate(items):
        if namespace.type == "track":
            try:
                playlist_item = TracksEndpointResponseJSON.from_dict(namespace.item)
            except Exception as e:
                _msg: str = (
                    f"TidalPlaylistError: unable to parse playlist item {i} "
                    f"with type '{namespace.type}'"
                )
                logger.warning(_msg)
                logger.debug(e)
                # value stays None
            else:
                playlist_items[i] = playlist_item
        elif namespace.type == "video":
            try:
                playlist_item = VideosEndpointResponseJSON.from_dict(namespace.item)
            except Exception as e:
                _msg: str = (
                    f"TidalPlaylistError: unable to parse playlist item {i} "
                    f"with type '{namespace.type}'"
                )
                logger.warning(_msg)
                logger.debug(e)
                # value stays None
            else:
                playlist_items[i] = playlist_item
        else:
            continue  # value stays None
    init_args["items"] = tuple(playlist_items)

    return PlaylistsItemsResponseJSON(**init_args)


def retrieve_playlist_items(
    session: Session,
    playlist_id: str,
    transparent: bool = False,
) -> PlaylistsItemsResponseJSON | None:
    """The pattern for playlist items retrieval does not follow the
    requesting.request_* functions, hence its implementation here. N.b.
    if the first response from /playlists/items endpoint indicates that
    the playlist contains more than 100 items, multiple requests will be
    sent until all N > 100 items are retrieved."""
    playlists_items_response_json: PlaylistsItemsResponseJSON | None = None
    playlists_response: dict | None = request_playlists_items(
        session=session, playlist_id=playlist_id, transparent=transparent
    )
    if playlists_response is None:
        _msg: str = f"Could not retrieve the items in playlist '{playlist_id}'"
        raise TidalPlaylistError(_msg)

    total_number_of_items: int | None = playlists_response.get("totalNumberOfItems")
    _msg: str = (
        f"Playlist '{playlist_id}' is comprised of {total_number_of_items} items"
    )
    logger.info(_msg)
    if total_number_of_items is None:
        _msg: str = (
            "TIDAL API did not respond with number of items "
            f"in playlist '{playlist_id}'"
        )
        raise TidalPlaylistError(_msg)
    items_to_retrieve: int = total_number_of_items

    all_items_playlist_response: dict = playlists_response

    if total_number_of_items > 100:
        items_list: list[dict] = playlists_response.pop("items")
        offset: int = 100
        while items_to_retrieve > 0:
            pr: dict | None = request_playlists_items(
                session=session, playlist_id=playlist_id, offset=offset
            )

            if (pr is not None) and ((pr_items := pr.get("items")) is not None):
                items_list += pr_items
                offset += 100
                items_to_retrieve -= 100
            else:
                logger.exception(
                    TidalPlaylistError(
                        f"Could not retrieve more than {len(items_list)} "
                        f"elements of playlist '{playlist_id}'. Continuing "
                        "without the remaining "
                        f"{total_number_of_items - len(items_list)}",
                    ),
                )
        all_items_playlist_response["items"] = items_list

    try:
        playlists_items_response_json: PlaylistsItemsResponseJSON | None = (
            playlists_items_response_json_maker(
                playlists_response=all_items_playlist_response,
            )
        )
    except Exception as e:
        logger.exception(TidalPlaylistError(e.args[0]))
    return playlists_items_response_json


# union type for type hinting
PlaylistItem = TracksEndpointResponseJSON | VideosEndpointResponseJSON | None
