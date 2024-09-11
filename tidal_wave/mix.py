"""Represent a mix of tracks and/or videos in the reckoning of TIDAL API."""

import json
import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional, Set, Tuple, Union
from uuid import uuid4

from requests import HTTPError, Session

from .media import AudioFormat
from .models import (
    TracksEndpointResponseJSON,
    VideosEndpointResponseJSON,
)
from .track import Track
from .utils import TIDAL_API_URL, replace_illegal_characters
from .video import Video

logger = logging.getLogger("__name__")

# union type for type hinting
MixItem = Optional[Union["TracksEndpointResponseJSON", "VideosEndpointResponseJSON"]]


@dataclass
class Mix:
    mix_id: str
    transparent: bool = False

    def __post_init__(self):
        self.mix_dir: Optional[Path] = None
        self.mix_cover_saved: bool = False

    def set_metadata(self, session: Session):
        """Request from TIDAL API /mixes endpoint"""
        self.metadata: Optional[SimpleNamespace] = request_mix(
            session=session, mix_id=self.mix_id, transparent=self.transparent
        )

        if self.metadata is None:
            return

        self.name = replace_illegal_characters(self.metadata.title)

    def set_items(self, session: Session):
        """Uses data from TIDAL API /mixes/items endpoint to
        populate self.items"""
        try:
            mix_items: Optional[MixesItemsResponseJSON] = retrieve_mix_items(
                session=session, mix_id=self.mix_id, transparent=self.transparent
            )
        except TidalMixError as tme:
            logger.exception(tme.args[0])
            self.items = tuple()
        else:
            if mix_items is None:
                self.items = tuple()
            else:
                self.items: Tuple[Optional[MixItem]] = tuple(
                    filter(None, mix_items.items)
                )

    def set_mix_dir(self, out_dir: Path):
        """Populates self.mix_dir based on self.name, self.mix_id"""
        mix_substring: str = f"{self.name} [{self.mix_id}]"
        self.mix_dir: Path = out_dir / "Mixes" / mix_substring
        self.mix_dir.mkdir(parents=True, exist_ok=True)

    def save_cover_image(self, session: Session, out_dir: Path):
        """Requests self.metadata.image and attempts to write it to disk"""
        if self.mix_dir is None:
            self.set_mix_dir(out_dir=out_dir)
        self.cover_path: Path = self.mix_dir / "cover.jpg"

        if not self.cover_path.exists():
            with session.get(
                url=self.metadata.image, params={k: None for k in session.params}
            ) as r:
                (self.mix_dir / "cover.jpg").write_bytes(r.content)

            self.mix_cover_saved = True
        else:
            if self.cover_path.stat().st_size > 0:
                self.mix_cover_saved = True

    def get_items(
        self, session: Session, audio_format: AudioFormat, no_extra_files: bool
    ) -> Tuple[Optional[Union[Track, Video]]]:
        """Using either Track.get() or Video.get(), attempt to request
        the data for each track or video in self.items."""
        if len(self.items) == 0:
            self.files = {}
            return

        tracks_videos: List[Optional[Union[Track, Video]]] = [None] * len(self.items)
        for i, item in enumerate(self.items):
            if item is None:
                tracks_videos[i] = None
                continue
            elif isinstance(item, TracksEndpointResponseJSON):
                track: Track = Track(track_id=item.id, transparent=self.transparent)
                track.get(
                    session=session,
                    audio_format=audio_format,
                    out_dir=self.mix_dir,
                    metadata=item,
                    no_extra_files=no_extra_files,
                    origin_jpg=False,
                )
                tracks_videos[i] = track
            elif isinstance(item, VideosEndpointResponseJSON):
                video: Video = Video(video_id=item.id, transparent=self.transparent)
                video.get(
                    session=session,
                    out_dir=self.mix_dir,
                    metadata=item,
                )
                tracks_videos[i] = video
            else:
                tracks_videos[i] = None
                continue
        else:
            self.tracks_videos: Tuple[Optional[Union[Track, Video]]] = tuple(
                tracks_videos
            )
        return tracks_videos

    def flatten_mix_dir(self):
        """When self.get_items() is called, the tracks and/or videos in
        self.items are downloaded using their self-contained .get() logic;
        this means that they will be downloaded to albums. This function
        "flattens" self.mix_dir, meaning that it moves all downloaded
        audio and video files to self.mix_dir, and removes the various
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
                new_path: Path = self.mix_dir / f"{i:03d} - {tv.trackname}"
                new_path.write_bytes(_path.read_bytes())
                _path.unlink()
                files[i - 1] = {i: str(new_path.absolute())}
            elif isinstance(tv, Video):
                new_path: Path = self.mix_dir / f"{i:03d} - {_path.name}"
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
                        self.mix_dir / artist_image_path.name,
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
                        self.mix_dir / artist_bio_path.name,
                    )

        # Remove all subdirs
        for subdir in subdirs:
            if subdir.exists():
                shutil.rmtree(subdir)
        else:
            return self.mix_dir

    def dumps(self):
        return json.dumps(self.files)

    def dump(self, fp=sys.stdout):
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
          - self.set_mix_dir()
          - self.get_items()
          - self.flatten_playlist_dir()
        Then, if no_extra_files is False,
          - self.save_cover_image()
        """
        self.set_metadata(session)
        if self.metadata is None:
            self.files = {}
            return

        self.set_items(session)
        self.set_mix_dir(out_dir)

        if self.get_items(session, audio_format, no_extra_files) is None:
            logger.critical(f"Could not retrieve mix with ID '{self.mix_id}'")
            self.files = {}
            return

        self.flatten_mix_dir()
        logger.info(f"Mix files written to '{self.mix_dir}'")

        if not no_extra_files:
            self.save_cover_image(session, out_dir)

    def get_elements(
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
            files: List[Optional[str]] = [None] * len(self.items)

        for i, item in enumerate(self.items):
            if item is None:
                files[i] = None
                continue
            elif isinstance(item, TracksEndpointResponseJSON):
                track: Track = Track(track_id=item.id, transparent=self.transparent)
                track_file: Optional[str] = track.get(
                    session=session,
                    audio_format=audio_format,
                    out_dir=out_dir,
                    metadata=item,
                    no_extra_files=no_extra_files,
                    origin_jpg=False,
                )
                files[i] = track_file
            elif isinstance(item, VideosEndpointResponseJSON):
                video: Video = Video(video_id=item.id, transparent=self.transparent)
                video_file: Optional[str] = video.get(
                    session=session,
                    out_dir=self.mix_dir,
                    metadata=item,
                )
                files[i] = video_file
            else:
                files[i] = None
                continue
        else:
            self.files: List[Optional[str]] = files


class TidalMixError(Exception):
    pass


def request_mix(
    session: Session, mix_id: str, transparent: bool = False
) -> Optional[SimpleNamespace]:
    """Request from TIDAL API /pages/mix endpoint. If an error occurs from
    session.get(), None is returned. Otherwise, a typing.SimpleNamespace
    object is returned with some metadata to do with the mix: title,
    description, URL to cover image."""
    url: str = f"{TIDAL_API_URL}/pages/mix?mixId={mix_id}"
    kwargs: dict = {"url": url}
    kwargs["headers"] = {"Accept": "application/json"}

    json_name: str = f"pages-mix-{mix_id}_{uuid4().hex}.json"

    logger.info(f"Requesting from TIDAL API: mixes/{mix_id}")
    with session.get(**kwargs) as resp:
        try:
            resp.raise_for_status()
        except HTTPError as he:
            if resp.status_code == 404:
                logger.warning(
                    "404 Client Error: not found for TIDAL API endpoint pages/mix"
                )
            else:
                logger.exception(he)
            return
        else:
            if transparent:
                Path(json_name).write_text(
                    json.dumps(resp.json(), ensure_ascii=True, indent=4, sort_keys=True)
                )

        d: Dict[str, str] = {
            "title": resp.json().get("title"),
            "description": resp.json().get("rows")[0]["modules"][0]["mix"]["subTitle"],
        }
        d["image"] = (
            resp.json()
            .get("rows", [{}])[0]
            .get("modules")[0]["mix"]["images"]["LARGE"]["url"]
        )

        logger.debug(
            f"{resp.status_code} response from TIDAL API to request: pages/mix"
        )
        return SimpleNamespace(**d)


def request_mixes_items(
    session: Session,
    mix_id: str,
    offset: Optional[int] = None,
    transparent: bool = False,
) -> Optional[Dict]:
    """Request from TIDAL API /mixes/items endpoint. If error arises when
    requesting with 'session'.get(), None is returned. Otherwise, the
    dict object returned by requests.Response.json() is returned."""
    url: str = f"{TIDAL_API_URL}/mixes/{mix_id}/items"
    kwargs: dict = {"url": url}
    kwargs["params"] = (
        {"limit": 100} if offset is None else {"limit": 100, "offset": offset}
    )
    kwargs["headers"] = {"Accept": "application/json"}
    json_name: str = f"mixes-{mix_id}-items_{uuid4().hex}.json"

    data: Optional[dict] = None
    logger.info(f"Requesting from TIDAL API: mixes/{mix_id}/items")
    with session.get(**kwargs) as resp:
        try:
            resp.raise_for_status()
        except HTTPError as he:
            if resp.status_code == 404:
                logger.warning(
                    f"404 Client Error: not found for TIDAL API endpoint mixes/{mix_id}/items"
                )
            else:
                logger.exception(he)
        else:
            if transparent:
                Path(json_name).write_text(
                    json.dumps(resp.json(), ensure_ascii=True, indent=4, sort_keys=True)
                )
                data = resp.json()
                logger.debug(
                    f"{resp.status_code} response from TIDAL API to request: mixes/{mix_id}/items"
                )
            else:
                data = resp.json()
                logger.debug(
                    f"{resp.status_code} response from TIDAL API to request: mixes/{mix_id}/items"
                )
        finally:
            return data


@dataclass(frozen=True)
class MixesItemsResponseJSON:
    """The response from the TIDAL API endpoint /mixes/<ID>/items
    is modeled by this class."""

    limit: int
    offset: int
    total_number_of_items: int
    items: Tuple[
        Optional[Union["TracksEndpointResponseJSON", "VideosEndpointResponseJSON"]]
    ]


def mix_items_response_json_maker(
    mixes_response: Dict[str, Union[int, List[dict]]],
) -> "MixesItemsResponseJSON":
    """This function massages the response from the TIDAL API endpoint
    mixes/items into a format that MixesItemsResponseJSON.from_dict()
    can ingest. Returns a MixesItemsResponseJSON instance"""
    init_args: dict = {}
    init_args["limit"] = mixes_response.get("limit")
    init_args["offset"] = mixes_response.get("offset")
    init_args["total_number_of_items"] = mixes_response.get("totalNumberOfItems")

    items: Tuple[SimpleNamespace] = tuple(
        SimpleNamespace(**d) for d in mixes_response["items"]
    )
    if len(items) == 0:
        return

    mixes_items: List[
        Optional[Union["TracksEndpointResponseJSON", "VideosEndpointResponseJSON"]]
    ] = [None] * init_args["total_number_of_items"]

    for i, namespace in enumerate(items):
        if namespace.type == "track":
            try:
                mix_item = TracksEndpointResponseJSON.from_dict(namespace.item)
            except Exception as e:
                _msg: str = (
                    f"TidalMixError: unable to parse playlist item [i] "
                    f"with type '{namespace.type}'"
                )
                logger.warning(_msg)
                logger.debug(e)
                # value stays None
            else:
                mixes_items[i] = mix_item
        elif namespace.type == "video":
            try:
                mix_item = VideosEndpointResponseJSON.from_dict(namespace.item)
            except Exception as e:
                _msg: str = (
                    f"TidalMixError: unable to parse mix item [i] "
                    f"with type '{namespace.type}'"
                )
                logger.warning(_msg)
                logger.debug(e)
                # value stays None
            else:
                mixes_items[i] = mix_item
        else:
            continue  # value stays None
    init_args["items"] = tuple(mixes_items)

    return MixesItemsResponseJSON(**init_args)


def retrieve_mix_items(
    session: Session, mix_id: str, transparent: bool = False
) -> Optional["MixesItemsResponseJSON"]:
    """The pattern for mix items retrieval does not follow the
    requesting.request_* functions, hence its implementation here. N.b.
    if the first response from /mixes/<ID>/items endpoint indicates that
    the playlist contains more than 100 items, multiple requests will be
    sent until all N > 100 items are retrieved.
    """
    mixes_items_response_json: Optional["MixesItemsResponseJSON"] = None
    mixes_response: Optional[dict] = request_mixes_items(
        session=session, mix_id=mix_id, transparent=transparent
    )
    if mixes_response is None:
        raise TidalMixError(f"Could not retrieve the items in mix '{mix_id}'")

    total_number_of_items: Optional[int] = mixes_response.get("totalNumberOfItems")
    if total_number_of_items is None:
        raise TidalMixError(
            f"TIDAL API did not respond with number of items in mix '{mix_id}'"
        )
    else:
        logger.info(f"Mix '{mix_id}' is comprised of {total_number_of_items} items")

    num_items: int = len(mixes_response.get("items", []))
    if num_items == 0:
        raise TidalMixError(
            f"TIDAL API did not return any mix items for mix '{mix_id}'"
        )

    if num_items < total_number_of_items:
        items_to_retrieve: int = total_number_of_items
        all_items_mixes_response: dict = mixes_response
        if total_number_of_items > 100:
            items_list: List[dict] = mixes_response.pop("items")
            offset: int = 100
            while items_to_retrieve > 0:
                mr: Optional[dict] = request_mixes_items(
                    session=session, mix_id=mix_id, offset=offset
                )
                if (mr is not None) and ((mr_items := mr.get("items")) is not None):
                    items_list += mr_items
                    offset += 100
                    items_to_retrieve -= 100
                else:
                    logger.exception(
                        TidalMixError(
                            f"Could not retrieve more than {len(items_list)} "
                            f"elements of mix '{mix_id}'. Continuing "
                            "without the remaining "
                            f"{total_number_of_items - len(items_list)}"
                        )
                    )
        else:
            all_items_mixes_response = mixes_response
    else:
        all_items_mixes_response = mixes_response

    try:
        mixes_items_response_json: Optional["MixesItemsResponseJSON"] = (
            mix_items_response_json_maker(mixes_response=all_items_mixes_response)
        )
    except Exception as e:
        logger.exception(TidalMixError(e.args[0]))
    finally:
        return mixes_items_response_json
