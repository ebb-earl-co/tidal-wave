from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
import json
import logging
from pathlib import Path
import random
import sys
import time
from tempfile import NamedTemporaryFile
from typing import Dict, List, Optional, Tuple

from .dash import (
    manifester,
    JSONDASHManifest,
    Manifest,
    TidalManifestException,
    XMLDASHManifest,
)
from .models import (
    AlbumsEndpointResponseJSON,
    AlbumsItemsResponseJSON,
    AlbumsReviewResponseJSON,
    TracksCreditsResponseJSON,
    TracksEndpointResponseJSON,
    TracksEndpointStreamResponseJSON,
    TracksLyricsResponseJSON,
)
from .requesting import (
    request_album_items,
    request_album_review,
    request_albums,
    request_credits,
    request_lyrics,
    request_stream,
    request_tracks,
    ResponseJSON,
)
from .utils import download_artist_image, download_cover_image

import ffmpeg
import mutagen
from mutagen.mp4 import MP4Cover
from platformdirs import user_music_path
from requests import Request, Session

MaybeResponse = Optional[ResponseJSON]


class AudioFormat(str, Enum):
    sony_360_reality_audio = "360"
    dolby_atmos = "Atmos"
    hi_res = "HiRes"
    mqa = "MQA"
    lossless = "Lossless"
    high = "High"
    low = "Low"


af_aq: Dict[AudioFormat, str] = {
    AudioFormat.sony_360_reality_audio: "LOW",
    AudioFormat.dolby_atmos: "LOW",
    AudioFormat.hi_res: "HI_RES",
    AudioFormat.mqa: "HI_RES",
    AudioFormat.lossless: "LOSSLESS",
    AudioFormat.high: "HIGH",
    AudioFormat.low: "LOW",
}

TAG_MAPPING: Dict[str, Dict[str, str]] = {
    "album": {"flac": "ALBUM", "m4a": "\xa9alb"},
    "album_artist": {"flac": "ALBUMARTIST", "m4a": "aART"},
    "artist": {"flac": "ARTIST", "m4a": "\xa9ART"},
    "artists": {"flac": "ARTISTS", "m4a": "----:com.apple.iTunes:ARTISTS"},
    "barcode": {"flac": "BARCODE", "m4a": "----:com.apple.iTunes:BARCODE"},
    "comment": {"flac": "COMMENT", "m4a": "\xa9cmt"},
    "composer": {"flac": "COMPOSER", "m4a": "\xa9wrt"},
    "copyright": {"flac": "COPYRIGHT", "m4a": "cprt"},
    "date": {"flac": "DATE", "m4a": "\xa9day"},
    "engineer": {"flac": "ENGINEER", "m4a": "----:com.apple.iTunes:ENGINEER"},
    "isrc": {"flac": "ISRC", "m4a": "----:com.apple.iTunes:ISRC"},
    "lyrics": {"flac": "LYRICS", "m4a": "\xa9lyr"},
    "lyricist": {"flac": "LYRICIST", "m4a": "----:com.apple.iTunes:LYRICIST"},
    "mixer": {"flac": "MIXER", "m4a": "----:com.apple.iTunes:MIXER"},
    "producer": {"flac": "PRODUCER", "m4a": "----:com.apple.iTunes:PRODUCER"},
    "remixer": {"flac": "REMIXER", "m4a": "----:com.apple.iTunes:REMIXER"},
    "album_peak_amplitude": {
        "flac": "REPLAYGAIN_ALBUM_PEAK",
        "m4a": "----:com.apple.iTunes:REPLAYGAIN_ALBUM_PEAK",
    },
    "album_replay_gain": {
        "flac": "REPLAYGAIN_ALBUM_GAIN",
        "m4a": "----:com.apple.iTunes:REPLAYGAIN_ALBUM_GAIN",
    },
    "track_peak_amplitude": {
        "flac": "REPLAYGAIN_TRACK_PEAK",
        "m4a": "----:com.apple.iTunes:REPLAYGAIN_TRACK_PEAK",
    },
    "track_replay_gain": {
        "flac": "REPLAYGAIN_TRACK_GAIN",
        "m4a": "----:com.apple.iTunes:REPLAYGAIN_TRACK_GAIN",
    },
    "title": {"flac": "TITLE", "m4a": "\xa9nam"},
}

logger = logging.getLogger(__name__)


@dataclass
class Album:
    album_id: int

    def __post_init__(self):
        self.album_dir: Optional[Path] = None
        self.album_cover_saved: bool = False

    def get_items(self, session: Session):
        album_items: AlbumsItemsResponseJSON = request_album_items(
            session=session, identifier=self.album_id
        )
        _items = album_items.items if album_items is not None else ()
        self.tracks = tuple(_item.item for _item in _items)

    def get_metadata(self, session: Session):
        self.metadata: AlbumsEndpointResponseJSON = request_albums(
            session=session, identifier=self.album_id
        )

    def get_review(self, session: Session):
        if self.album_dir is None:
            self.set_dir(out_dir=out_dir)
        self.album_review: Optional[AlbumsReviewResponseJSON] = request_album_review(
            session=session, identifier=self.album_id
        )
        if self.album_review is not None:
            (self.album_dir / "AlbumReview.json").write_text(
                self.album_review.to_json()
            )

    def set_dir(self, out_dir: Path):
        artist_substring: str = self.metadata.artist.name
        album_substring: str = (
            f"{self.metadata.name} "
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
    ) -> List[str]:
        track_files: List[str] = [None] * self.metadata.number_of_tracks
        for i, t in enumerate(self.tracks):  # type(t) is TracksEndpointResponseJSON
            if audio_format == AudioFormat.dolby_atmos:
                if "DOLBY_ATMOS" not in t.media_metadata.tags:
                    logger.warning(
                        "Dolby Atmos audio format was requested, but track "
                        f"{t.id} is not available in Dolby Atmos "
                        "format. Downloading of track will not continue."
                    )
                    track_files[i] = {track.metadata.track_number: None}
                    sleep_to_mimic_human_activity()
                    continue
            elif audio_format == AudioFormat.sony_360_reality_audio:
                if "SONY_360RA" not in t.media_metadata.tags:
                    logger.warning(
                        "Sony 360 Reality Audio audio format was requested, "
                        f"but track {t.id} is not available in "
                        "Sony 360 Reality Audio format. Downloading of track "
                        "will not continue."
                    )
                    track_files[i] = {track.metadata.track_number: None}
                    sleep_to_mimic_human_activity()
                    continue

            track: Track = Track(track_id=t.id)
            track.metadata = t
            track.album = self.metadata
            track.get_credits(session)
            track.get_lyrics(session)
            track.get_stream(session, audio_format)
            track.set_manifest()
            track.set_album_dir(out_dir)
            track.set_filename(audio_format, out_dir)
            outfile: Optional[Path] = track.set_outfile()
            if outfile is None:
                track_files[i] = {track.metadata.track_number: None}
                sleep_to_mimic_human_activity()
                continue
            track.save_album_cover(session)
            track.save_artist_image(session)
            path_to_track: Optional[Path] = track.download(session, out_dir)
            if path_to_track is None:  # already exists
                track_files[i] = {track.metadata.track_number: None}
                sleep_to_mimic_human_activity()
                continue
            track_files[i] = json.loads(track.dumps())
            track.craft_tags()
            track.set_tags()
            sleep_to_mimic_human_activity()
        else:
            self.track_files = track_files

    def dumps(self):
        return json.dumps(self.track_files)

    def dump(self, fp=sys.stdout):
        json.dump(self.track_files, fp)

    def get(self, session: Session, audio_format: AudioFormat, out_dir: Path):
        self.get_metadata(session)
        self.get_items(session)
        self.save_cover_image(session, out_dir)
        self.get_review(session)
        self.get_tracks(session, audio_format, out_dir)


@dataclass
class Track:
    track_id: int

    def __post_init__(self):
        self._has_lyrics: Optional[bool] = None
        self.tags: dict = {}
        self.album_cover_saved: bool = False

    def _lookup(self, af) -> AudioFormat:
        af_aq: Dict[AudioFormat, str] = {
            AudioFormat.sony_360_reality_audio: "LOW",
            AudioFormat.dolby_atmos: "LOW",
            AudioFormat.hi_res: "HI_RES",
            AudioFormat.mqa: "HI_RES",
            AudioFormat.lossless: "LOSSLESS",
            AudioFormat.high: "HIGH",
            AudioFormat.low: "LOW",
        }
        return af_aq.get(af)

    def get_metadata(self, session: Session):
        self.metadata: Optional[TracksEndpointResponseJSON] = request_tracks(
            session=session, identifier=self.track_id
        )

    def get_album(self, session: Session):
        self.album: Optional[AlbumsEndpointResponseJSON] = request_albums(
            session=session, identifier=self.metadata.album.id
        )

    def get_credits(self, session: Session):
        self.credits: Optional[TracksCreditsResponseJSON] = request_credits(
            session=session, identifier=self.track_id
        )

    def get_lyrics(self, session: Session):
        if self._has_lyrics is None:
            self.lyrics: Optional[TracksLyricsResponseJSON] = request_lyrics(
                session=session, identifier=self.track_id
            )
            if self.lyrics is None:
                self._has_lyrics = False
            else:
                self._has_lyrics = True
        else:
            return self.lyrics

    def get_stream(self, session: Session, audio_format: AudioFormat):
        """Populates self.stream, self.manifest"""
        aq: Optional[str] = self._lookup(audio_format)
        self.stream: Optional[TracksEndpointStreamResponseJSON] = request_stream(
            session=session, track_id=self.track_id, audio_quality=aq
        )

    def set_manifest(self):
        """This method sets self.manifest and self.codec"""
        self.manifest: Manifest = manifester(self.stream)
        # https://dashif.org/codecs/audio/
        if self.manifest.codecs == "flac":
            self.codec = "flac"
        elif self.manifest.codecs == "mqa":
            self.codec = "flac"
        elif self.manifest.codecs == "mha1":  # Sony 360 Reality Audio
            self.codec = "mka"
        elif self.manifest.codecs == "mp4a.40.5":  # HE-AAC
            self.codec = "m4a"
        elif self.manifest.codecs == "mp4a.40.29":  # HE-AAC v2
            self.codec = "m4a"
        elif self.manifest.codecs == "mp4a.40.2":  # AAC-LC
            self.codec = "m4a"
        elif self.manifest.codecs == "eac3":  # Enhanced AC-3
            self.codec = "m4a"
        elif self.manifest.codecs == "mp4a.40.34":  # MP3
            self.codec = "mp3"

    def set_album_dir(self, out_dir: Path):
        artist_substring: str = self.album.artist.name
        album_substring: str = (
            f"{self.album.name} " f"[{self.album.id}] [{self.album.release_date.year}]"
        )
        self.album_dir: Path = out_dir / artist_substring / album_substring
        self.album_dir.mkdir(parents=True, exist_ok=True)

        if self.album.number_of_volumes > 1:
            volume_substring: str = f"Volume {self.metadata.volume_number}"
            (self.album_dir / volume_substring).mkdir(parents=True, exist_ok=True)

    def set_filename(self, audio_format: AudioFormat, out_dir: Path):
        _track_part: str = f"{self.metadata.track_number:02d} - {self.metadata.name}"
        if audio_format == AudioFormat.low:
            track_substring: str = f"{_track_part} [L]"
        elif audio_format == AudioFormat.high:
            track_substring: str = f"{_track_part} [H]"
        elif audio_format == AudioFormat.lossless:
            track_substring: str = f"{_track_part} [CD]"
        elif audio_format == AudioFormat.mqa:
            track_substring: str = f"{_track_part} [Q]"
        elif audio_format == AudioFormat.hi_res:
            track_substring: str = f"{_track_part} [HiRes]"
        elif audio_format == AudioFormat.dolby_atmos:
            track_substring: str = f"{_track_part} [A]"
        elif audio_format == AudioFormat.sony_360_reality_audio:
            track_substring: str = f"{_track_part} [360]"
        else:
            track_substring: str = _track_part

        # Check for MQA masquerading as HiRes here
        if audio_format == AudioFormat.hi_res:
            if self.manifest.codecs == "mqa":
                logger.warning(
                    "Even though HiRes audio format was requested, this track is only "
                    "available in MQA format. TIDAL regards this as 'HiRes' even though "
                    "it is probably only lossless; i.e. 16-bit 44.1 kHz quality. "
                    "Downloading of track will continue, but it will be marked as MQA."
                )
                self.filename: Optional[str] = f"{_track_part} [Q].{self.codec}"
            elif (self.stream.bit_depth == 16) and (self.stream.sample_rate == 44100):
                logger.warning(
                    "Even though HiRes audio format was requested, and TIDAL responded to "
                    "that request without error, this track is only available in lossless "
                    "format; i.e. 16-bit 44.1 kHz quality. Downloading of track will "
                    "continue, but it will be marked as Lossless ([CD])."
                )
                self.filename: Optional[str] = f"{_track_part} [CD].{self.codec}"
            else:
                self.filename: Optional[str] = f"{track_substring}.{self.codec}"
        else:
            self.filename: Optional[str] = f"{track_substring}.{self.codec}"

    def set_outfile(self):
        """Uses self.album_dir and self.metadata and self.filename
        to craft the pathlib.Path object, self.outfile, that is a
        reference to where the track will be written on disk."""
        if self.album.number_of_volumes > 1:
            self.outfile: Path = (
                self.album_dir / f"Volume {self.metadata.volume_number}" / self.filename
            )
        else:
            self.outfile: Path = self.album_dir / self.filename

        if (self.outfile.exists()) and (self.outfile.stat().st_size > 0):
            logger.info(
                f"Track {str(self.outfile.absolute())} already exists "
                "and therefore will not be overwritten"
            )
            return
        else:
            return self.outfile

    def save_artist_image(self, session: Session):
        for a in self.metadata.artists:
            track_artist_image: path = self.album_dir / f"{a.name}.jpg"
            if not track_artist_image.exists():
                download_artist_image(session, a, self.album_dir)

    def save_album_cover(self, session: Session):
        self.cover_path: Path = self.album_dir / "cover.jpg"
        if (not self.cover_path.exists()) or (not self.album_cover_saved):
            download_cover_image(
                session=session, cover_uuid=self.album.cover, output_dir=self.album_dir
            )
        else:
            self.album_cover_saved = True

    def download(self, session: Session, out_dir: Path) -> Optional[Path]:
        if isinstance(self.manifest, JSONDASHManifest):
            urls: List[str] = self.manifest.urls
        elif isinstance(self.manifest, XMLDASHManifest):
            urls: List[str] = self.manifest.build_urls(session=session)
        self.download_headers: Dict[str, str] = {"Accept": self.manifest.mime_type}
        if session.session_id is not None:
            self.download_headers["sessionId"] = session.session_id
        self.download_params = {"deviceType": None, "locale": None, "countryCode": None}
        # self.outfile should already have been setted by set_outfile()
        logger.info(f"Writing track {self.track_id} to {str(self.outfile.absolute())}")

        with NamedTemporaryFile() as ntf:
            for u in urls:
                download_request = session.prepare_request(
                    Request(
                        "GET",
                        url=u,
                        headers=self.download_headers,
                        params=self.download_params,
                    )
                )
                with session.send(download_request) as download_response:
                    if not download_response.ok:
                        logger.warning(f"Could not download {self}")
                    else:
                        ntf.write(download_response.content)
            else:
                ntf.seek(0)

            if self.codec == "flac":
                # Have to use FFMPEG to re-mux the audio bytes, otherwise
                # mutagen chokes on NoFlacHeaderError
                ffmpeg.input(ntf.name, hide_banner=None, y=None).output(
                    str(self.outfile.absolute()), acodec="copy", loglevel="quiet"
                ).run()
            elif self.codec == "m4a":
                self.outfile.write_bytes(ntf.read())
            elif self.codec == "mka":
                self.outfile.write_bytes(ntf.read())

        logger.info(f"Track {self.track_id} written to {str(self.outfile.absolute())}")
        return self.outfile

    def craft_tags(self):
        """Using the TAG_MAPPING dictionary,
        write the correct values of various metadata tags to the file.
        E.g. for .flac files, the album's artist is 'ALBUMARTIST',
        but for .m4a files, the album's artist is 'aART'."""
        tags = dict()
        if (self.codec == "flac") or (self.codec == "mka"):
            tag_map = {k: v["flac"] for k, v in TAG_MAPPING.items()}
        elif self.codec == "m4a":
            tag_map = {k: v["m4a"] for k, v in TAG_MAPPING.items()}

        tags[tag_map["album"]] = self.album.title
        tags[tag_map["album_artist"]] = ";".join((a.name for a in self.album.artists))
        tags[tag_map["album_peak_amplitude"]] = f"{self.stream.album_peak_amplitude}"
        tags[tag_map["album_replay_gain"]] = f"{self.stream.album_replay_gain}"
        tags[tag_map["artist"]] = ";".join((a.name for a in self.metadata.artists))
        tags[tag_map["artists"]] = [a.name for a in self.metadata.artists]
        tags[tag_map["barcode"]] = self.album.upc
        tags[tag_map["comment"]] = self.metadata.url
        tags[tag_map["copyright"]] = self.metadata.copyright
        tags[tag_map["date"]] = str(self.album.release_date)
        tags[tag_map["isrc"]] = self.metadata.isrc
        tags[tag_map["title"]] = self.metadata.name
        tags[tag_map["track_peak_amplitude"]] = f"{self.metadata.peak}"
        tags[tag_map["track_replay_gain"]] = f"{self.metadata.replay_gain}"
        # credits
        for tag in {"composer", "lyricist", "mixer", "producer", "remixer"}:
            try:
                _credits_tag = ";".join(getattr(self.credits, tag))
            except (TypeError, AttributeError):  # NoneType problems
                continue
            else:
                tags[tag_map[tag]] = _credits_tag
        # lyrics
        try:
            _lyrics = self.lyrics.subtitles
        except (TypeError, AttributeError):  # NoneType problems
            pass
        else:
            tags[tag_map["lyrics"]] = _lyrics
        # track and disk
        if self.codec == "flac":
            tags["disc_number"] = f"{self.metadata.volume_number}"
            tags["discs"] = f"{self.album.number_of_volumes}"
            tags["total_tracks"] = f"{self.album.number_of_tracks}"
            tags["track_number"] = f"{self.metadata.track_number}"
        elif self.codec == "m4a":
            # Have to convert to bytes the values of the tags starting with '----'
            for k, v in tags.copy().items():
                if k.startswith("----"):
                    if isinstance(v, str):
                        tags[k]: bytes = v.encode("UTF-8")
                    elif isinstance(v, list):
                        tags[k]: List[bytes] = [s.encode("UTF-8") for s in v]

            tags["trkn"] = [(self.metadata.track_number, self.album.number_of_tracks)]
            tags["disk"] = [(self.metadata.volume_number, self.album.number_of_volumes)]
        self.tags: dict = {k: v for k, v in tags.items() if v is not None}

    def set_tags(self):
        """Instantiate a mutagen.File instance, add self.tags to it, and
        save it to disk"""
        self.mutagen = mutagen.File(self.outfile)
        self.mutagen.clear()
        self.mutagen.update(**self.tags)
        # add album cover
        if self.codec == "flac":
            p = mutagen.flac.Picture()
            p.type = mutagen.id3.PictureType.COVER_FRONT
            p.desc = "Album Cover"
            p.width = p.height = 1280
            p.mime = "image/jpeg"
            p.data = self.cover_path.read_bytes()
            self.mutagen.add_picture(p)
        elif self.codec == "m4a":
            self.mutagen["covr"] = [
                MP4Cover(self.cover_path.read_bytes(), imageformat=MP4Cover.FORMAT_JPEG)
            ]
        self.mutagen.save()

    def get(self, session: Session, audio_format: AudioFormat, out_dir: Path):
        self.get_metadata(session)
        if audio_format == AudioFormat.dolby_atmos:
            if "DOLBY_ATMOS" not in t.media_metadata.tags:
                logger.warning(
                    "Dolby Atmos audio format was requested, but track "
                    f"{self.track_id} is not available in Dolby Atmos "
                    "format. Downloading of track will not continue."
                )
                return
        elif audio_format == AudioFormat.sony_360_reality_audio:
            if "SONY_360RA" not in t.media_metadata.tags:
                logger.warning(
                    "Sony 360 Reality Audio audio format was requested, but track "
                    f"{self.track_id} is not available in Sony 360 Reality Audio "
                    "format. Downloading of track will not continue."
                )
                return

        self.get_album(session)
        self.get_credits(session)
        self.get_lyrics(session)
        self.get_stream(session, audio_format)
        self.set_manifest()
        self.set_album_dir(out_dir)
        self.set_filename(audio_format, out_dir)
        outfile: Optional[Path] = self.set_outfile()
        if outfile is None:
            return

        self.save_album_cover(session)
        try:
            self.save_artist_image(session)
        except:
            pass
        self.download(session, out_dir)
        self.craft_tags()
        self.set_tags()

    def dump(self, fp=sys.stdout):
        json.dump({self.metadata.track_number: str(self.outfile.absolute())}, fp)

    def dumps(self) -> str:
        return json.dumps({self.metadata.track_number: str(self.outfile.absolute())})


def sleep_to_mimic_human_activity():
    _time = random.randint(500, 5000) / 500
    logger.info(f"Sleeping for {_time} seconds to mimic human activity")
    time.sleep(_time)
