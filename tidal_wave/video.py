from dataclasses import dataclass
from enum import Enum
import json
import logging
from pathlib import Path
import sys
from typing import Dict, List, Optional
import urllib

from .hls import playlister, variant_streams, TidalM3U8Exception
from .media import TAG_MAPPING
from .models import (
    VideosContributorsResponseJSON,
    VideosEndpointResponseJSON,
    VideosEndpointStreamResponseJSON,
)
from .requesting import request_videos, request_video_contributors, request_video_stream
from .utils import replace_illegal_characters, temporary_file

import ffmpeg
import mutagen
import m3u8
from requests import Session

logger = logging.getLogger("__name__")


class VideoFormat(str, Enum):
    high = "HIGH"
    medium = "MEDIUM"
    low = "LOW"
    audio_only = "AUDIO_ONLY"


@dataclass
class Video:
    video_id: int

    def __post_init__(self):
        self.tags: dict = {}
        self.codec: str = "mp4"

    def get_metadata(self, session: Session):
        """Request from TIDAL API /videos endpoint and set self.metadata
        attribute as None or VideosEndpointResponseJSON instance. N.b.,
        self.metadata.name is a sanitized version of self.metadata.title"""
        self.metadata: Optional[VideosEndpointResponseJSON] = request_videos(
            session=session, video_id=self.video_id
        )

    def get_contributors(self, session: Session):
        """Request from TIDAL API /videos/contributors endpoint"""
        self.contributors: Optional[VideosContributorsResponseJSON] = (
            request_video_contributors(session=session, video_id=self.video_id)
        )

    def get_stream(self, session: Session, video_format=VideoFormat.high):
        """Populates self.stream by requesting from TIDAL API
        /videos/playbackinfopostpaywall endpoint"""
        self.stream: Optional[VideosEndpointStreamResponseJSON] = request_video_stream(
            session=session, video_id=self.video_id, video_quality=video_format.value
        )

    def get_m3u8(self, session: Session):
        """This method sets self.m3u8, an m3u8.M3U8 object
        following the HTTP Live Streaming specification; parsed from
        self.stream. I.e., self.get_stream() needs to have been executed
        before calling this method. N.b. self.m3u8 almost certainly will
        be a multivariant playlist, meaning further processing of its
        contents will be necessary."""
        self.m3u8: m3u8.M3U8 = playlister(session=session, vesrj=self.stream)

    def set_urls(self, session: Session):
        """This method uses self.m3u8, an m3u8.M3U8 object that is variant:
        (https://developer.apple.com/documentation/http-live-streaming/creating-a-multivariant-playlist)
        It retrieves the highest-quality .m3u8 in its .playlists attribute,
        and sets self.urls as the list of strings from that m3u8.M3U8 object"""
        # for now, just get the highest-bandwidth playlist
        m3u8_files: List[str] = variant_streams(self.m3u8, session, return_urls=True)
        m3u8_parse_results = (urllib.parse.urlparse(url=f) for f in m3u8_files)
        if not all(u.netloc == "vmz-ad-cf.video.tidal.com" for u in m3u8_parse_results):
            raise TidalM3U8Exception(
                f"HLS media segments are not available for video {self.video_id}"
            )
        self.urls: List[str] = m3u8_files

    def set_artist_dir(self, out_dir: Path):
        """Set self.artist_dir, which is the subdirectory of `out_dir`
        with name `self.metadata.artist.name`"""
        self.artist_dir: Path = out_dir / self.metadata.artist.name
        self.artist_dir.mkdir(parents=True, exist_ok=True)

    def set_filename(self, out_dir: Path):
        """Set self.filename, which is constructed from self.metadata.name
        and self.stream.video_quality"""
        self.filename: str = (
            f"{self.metadata.name} [{self.stream.video_quality}].{self.codec}"
        )

    def set_outfile(self):
        """Uses self.artist_dir and self.metadata and self.filename
        to craft the pathlib.Path object, self.outfile, that is a
        reference to where the track will be written on disk."""
        self.outfile: Path = self.artist_dir / self.filename
        self.absolute_outfile: str = str(self.outfile.absolute())

        if (self.outfile.exists()) and (self.outfile.stat().st_size > 0):
            logger.info(
                f"Video {self.absolute_outfile} already exists "
                "and therefore will not be overwritten"
            )
            return
        else:
            return self.outfile

    def download(self, session: Session, out_dir: Path) -> Optional[Path]:
        """Requests the HLS video files that constitute self.video_id.
        Writes HLS bytes to a temporary file, then uses FFmpeg to write the
        video data to self.outfile"""
        download_params: Dict[str, None] = {k: None for k in session.params}
        # self.outfile should already have been set by self.set_outfile()
        logger.info(
            f"Writing video {self.video_id} to '{str(self.outfile.absolute())}'"
        )

        with temporary_file(suffix=".mp4") as ntf:
            request_headers: Dict[str, str] = (
                {"sessionId": session.session_id}
                if session.session_id is not None
                else dict()
            )
            for i, u in enumerate(self.urls, 1):
                logger.debug(
                    f"\tRequesting part {i} of video {self.video_id}: {u.split('?')[0]}"
                )
                with session.get(
                    url=u, headers=request_headers, params=download_params
                ) as download_response:
                    if not download_response.ok:
                        logger.warning(f"Could not download {self}")
                        return
                    else:
                        ntf.write(download_response.content)
            else:
                ntf.seek(0)
            self.outfile.write_bytes(Path(ntf.name).read_bytes())

            if self.outfile.exists() and self.outfile.stat().st_size > 0:
                logger.info(
                    f"Video {self.video_id} written to '{self.absolute_outfile}'"
                )

            try:
                ffmpeg.input(ntf.name, hide_banner=None, y=None).output(
                    self.absolute_outfile,
                    vcodec="copy",
                    acodec="copy",
                    loglevel="quiet",
                ).run()
            except ffmpeg.Error:
                logger.warning(
                    f"Could not convert video {self.video_id} with FFmpeg: "
                    "metadata will not be added and format will stay as MPEG-TS"
                )

        return self.outfile

    def craft_tags(self):
        """Using the TAG_MAPPING dictionary, write the correct values of
        various metadata tags to the file. Videos are .mp4"""
        tags = dict()
        tag_map = {k: v["m4a"] for k, v in TAG_MAPPING.items()}

        tags[tag_map["artist"]] = ";".join((a.name for a in self.metadata.artists))
        tags[tag_map["artists"]] = [a.name for a in self.metadata.artists]
        tags[tag_map["comment"]] = f"https://tidal.com/browse/video/{self.video_id}"
        tags[tag_map["date"]] = str(self.metadata.release_date.date())
        tags[tag_map["title"]] = self.metadata.title

        for tag in {"composer", "director", "lyricist", "producer"}:
            try:
                _credits_tag = ";".join(getattr(self.contributors, tag))
            except (TypeError, AttributeError):  # NoneType problems
                continue
            else:
                tags[tag_map[tag]] = _credits_tag

        # Have to convert to bytes the values of the tags starting with '----'
        for k, v in tags.copy().items():
            if k.startswith("----"):
                if isinstance(v, str):
                    tags[k]: bytes = v.encode("UTF-8")
                elif isinstance(v, list):
                    tags[k]: List[bytes] = [s.encode("UTF-8") for s in v]

        self.tags: dict = {k: v for k, v in tags.items() if v is not None}

    def set_tags(self):
        """Instantiate a mutagen.File instance, add self.tags to it, and
        save it to disk. If video container is still in MPEG-TS format,
        this is expected to fail"""
        try:
            self.mutagen = mutagen.File(self.outfile)
        except Exception:
            logger.warning(f"Unable to write metadata tags to {self.video_id}")
            return

        self.mutagen.clear()
        self.mutagen.update(**self.tags)
        self.mutagen.save()

    def get(
        self,
        session: Session,
        out_dir: Path,
        metadata: Optional["VideosEndpointResponseJSON"] = None,
    ) -> Optional[str]:
        """The main method of this class. Executes a number of other methods
        in a row:
          - self.get_metadata()
          - self.get_contributors()
          - self.get_stream()
          - self.get_m3u8()
          - self.set_urls()
          - self.set_artist_dir()
          - self.set_filename()
          - self.set_outfile()
          - self.download()
          - self.craft_tags()
          - self.set_tags()
        """
        if metadata is None:
            self.get_metadata(session)
        else:
            self.metadata = metadata

        if self.metadata is None:
            return None

        self.get_contributors(session)
        self.get_stream(session)
        if self.stream is None:
            return None
        self.get_m3u8(session)
        self.set_urls(session)
        self.set_artist_dir(out_dir)
        self.set_filename(out_dir)
        outfile: Optional[Path] = self.set_outfile()
        if outfile is None:
            return None

        if self.download(session, out_dir) is None:
            return None

        self.craft_tags()
        self.set_tags()

        return self.absolute_outfile

    def dump(self, fp=sys.stdout):
        """This method emulates stdlib json.dump(). In particular,
        it sends to 'fp' the JSON-formatted dict
        {self.metadata.title: self.absolute_outfile}"""
        json.dump({self.metadata.title: self.absolute_outfile}, fp)

    def dumps(self) -> str:
        """This method emulates stdlib json.dumps(). In particular,
        it returns the JSON-formatted str from the dict
        {self.metadata.title: self.absolute_outfile}"""
        return json.dumps({self.metadata.title: self.absolute_outfile})
