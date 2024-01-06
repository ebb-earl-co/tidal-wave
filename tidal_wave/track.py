from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Dict, Iterable, List, Optional

import mutagen
from mutagen.mp4 import MP4Cover
import ffmpeg
from requests import Session

from .dash import manifester, JSONDASHManifest, Manifest, XMLDASHManifest
from .media import af_aq, AudioFormat, TAG_MAPPING
from .models import (
    AlbumsEndpointResponseJSON,
    ArtistsBioResponseJSON,
    TracksCreditsResponseJSON,
    TracksEndpointResponseJSON,
    TracksEndpointStreamResponseJSON,
    TracksLyricsResponseJSON,
)
from .requesting import (
    fetch_content_length,
    http_request_range_headers,
    request_albums,
    request_artist_bio,
    request_credits,
    request_lyrics,
    request_stream,
    request_tracks,
)
from .utils import download_artist_image, download_cover_image, temporary_file

logger = logging.getLogger("__name__")


@dataclass
class Track:
    track_id: int

    def __post_init__(self):
        self._has_lyrics: Optional[bool] = None
        self.tags: dict = {}
        self.album_cover_saved: bool = False

    def get_metadata(self, session: Session):
        self.metadata: Optional[TracksEndpointResponseJSON] = request_tracks(
            session, self.track_id
        )

    def get_album(self, session: Session):
        self.album: Optional[AlbumsEndpointResponseJSON] = request_albums(
            session, self.metadata.album.id
        )

    def get_credits(self, session: Session):
        self.credits: Optional[TracksCreditsResponseJSON] = request_credits(
            session, self.track_id
        )

    def get_lyrics(self, session: Session):
        if self._has_lyrics is None:
            self.lyrics: Optional[TracksLyricsResponseJSON] = request_lyrics(
                session, self.track_id
            )
            if self.lyrics is None:
                self._has_lyrics = False
            else:
                self._has_lyrics = True
        else:
            return self.lyrics

    def get_stream(self, session: Session, audio_format: AudioFormat):
        """Populates self.stream, self.manifest"""
        aq: Optional[str] = af_aq.get(audio_format)
        self.stream: Optional[TracksEndpointStreamResponseJSON] = request_stream(
            session, self.track_id, aq
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
        artist_substring: str = self.album.artist.name.replace("..", "")
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

        # for use in playlist file ordering
        self.trackname: str = re.match(r"(?:\d{2,3} - )(.+?$)", self.filename).groups()[
            0
        ]

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
            track_artist_image: Path = (
                self.album_dir / f"{a.name.replace('..', '')}.jpg"
            )
            if not track_artist_image.exists():
                download_artist_image(session, a, self.album_dir)

    def save_artist_bio(self, session: Session):
        for a in self.metadata.artists:
            track_artist_bio_json: Path = self.album_dir / f"{a.name}-bio.json"
            if not track_artist_bio_json.exists():
                artist_bio: Optional[ArtistsBioResponseJSON] = request_artist_bio(
                    session, a.id
                )
                if artist_bio is not None:
                    logger.info(
                        f"Writing artist bio for artist {a.id} to "
                        f"'{str(track_artist_bio_json.absolute())}"
                    )
                    track_artist_bio_json.write_text(artist_bio.to_json())

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
        logger.info(
            f"Writing track {self.track_id} to '{str(self.outfile.absolute())}'"
        )

        # NamedTemporaryFile experiences permission error on Windows
        with temporary_file() as ntf:
            if len(urls) == 1:
                # Implement HTTP range requests here to mimic official clients
                range_size: int = 1024 * 1024  # 1 MiB
                content_length: int = fetch_content_length(session=session, url=urls[0])
                if content_length == 0:
                    # move on to the all-at-once flow
                    pass
                else:
                    range_headers: Iterable[str] = http_request_range_headers(
                        content_length=content_length,
                        range_size=range_size,
                        return_tuple=False,
                    )
                    for rh in range_headers:
                        with session.get(
                            urls[0],
                            params={k: None for k in session.params},
                            headers={"Range": rh},
                        ) as rr:
                            if not rr.ok:
                                logger.warning(f"Could not download {self}")
                                return
                            else:
                                ntf.write(rr.content)
                    else:
                        ntf.seek(0)

                    if self.codec == "flac":
                        # Have to use FFMPEG to re-mux the audio bytes, otherwise
                        # mutagen chokes on NoFlacHeaderError
                        ffmpeg.input(ntf.name, hide_banner=None, y=None).output(
                            str(self.outfile.absolute()),
                            acodec="copy",
                            loglevel="quiet",
                        ).run()
                    elif self.codec == "m4a":
                        shutil.copyfile(ntf.name, self.outfile)
                    elif self.codec == "mka":
                        shutil.copyfile(ntf.name, self.outfile)

                    logger.info(
                        f"Track {self.track_id} written to '{str(self.outfile.absolute())}'"
                    )
                    return self.outfile

            for u in urls:
                with session.get(
                    url=u, headers=self.download_headers, params=self.download_params
                ) as resp:
                    if not resp.ok:
                        logger.warning(f"Could not download {self}")
                        return
                    else:
                        ntf.write(resp.content)
            else:
                ntf.seek(0)

            if self.codec == "flac":
                # Have to use FFmpeg to re-mux the audio bytes, otherwise
                # mutagen chokes on NoFlacHeaderError
                ffmpeg.input(ntf.name, hide_banner=None, y=None).output(
                    str(self.outfile.absolute()), acodec="copy", loglevel="quiet"
                ).run()
            elif self.codec == "m4a":
                shutil.copyfile(ntf.name, self.outfile)
            elif self.codec == "mka":
                shutil.copyfile(ntf.name, self.outfile)

        logger.info(
            f"Track {self.track_id} written to '{str(self.outfile.absolute())}'"
        )
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
            tags["DISCTOTAL"] = f"{self.metadata.volume_number}"
            tags["DISC"] = f"{self.album.number_of_volumes}"
            tags["TRACKTOTAL"] = f"{self.album.number_of_tracks}"
            tags["TRACKNUMBER"] = f"{self.metadata.track_number}"
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
        elif self.codec == "mka":
            # FFmpeg chokes here with
            # [matroska @ 0x5eb6a424f840] No wav codec tag found for codec none
            # so DON'T attempt to add a cover image, and DON'T run the
            # FFmpeg to put streams in order
            self.mutagen.save()
            return

        self.mutagen.save()
        # Make sure audio track comes first because of
        # less-sophisticated audio players
        with temporary_file(suffix=".mka") as tf:
            cmd: List[str] = shlex.split(
                f"""ffmpeg -hide_banner -loglevel quiet -y -i "{str(self.outfile.absolute())}"
                -map 0:a:0 -map 0:v:0 -c copy "{tf.name}" """
            )
            subprocess.run(cmd)
            shutil.copyfile(tf.name, str(self.outfile.absolute()))

    def get(
        self,
        session: Session,
        audio_format: AudioFormat,
        out_dir: Path,
        metadata: Optional[TracksEndpointResponseJSON] = None,
        album: Optional[AlbumsEndpointResponseJSON] = None,
    ) -> Optional[str]:
        if metadata is None:
            self.get_metadata(session)
        else:
            self.metadata = metadata

        if self.metadata is None:
            # self.failed = True
            self.outfile = None
            return

        if audio_format == AudioFormat.dolby_atmos:
            if "DOLBY_ATMOS" not in self.metadata.media_metadata.tags:
                logger.warning(
                    "Dolby Atmos audio format was requested, but track "
                    f"{self.track_id} is not available in Dolby Atmos "
                    "format. Downloading of track will not continue."
                )
                self.outfile = None
                return
        elif audio_format == AudioFormat.sony_360_reality_audio:
            if "SONY_360RA" not in self.metadata.media_metadata.tags:
                logger.warning(
                    "Sony 360 Reality Audio audio format was requested, but track "
                    f"{self.track_id} is not available in Sony 360 Reality Audio "
                    "format. Downloading of track will not continue."
                )
                self.outfile = None
                return
        elif audio_format == AudioFormat.mqa:
            if "MQA" not in self.metadata.media_metadata.tags:
                logger.warning(
                    "MQA audio format was requested, but track "
                    f"{self.track_id} is not available in MQA audio "
                    "format. Downloading of track will not continue."
                )
                self.outfile = None
                return

        if album is None:
            self.get_album(session)
        else:
            self.album = album

        if self.album is None:
            # self.failed = True
            self.outfile = None
            return

        self.get_credits(session)
        self.get_stream(session, audio_format)
        if self.stream is None:
            return
        self.set_manifest()
        self.set_album_dir(out_dir)
        self.set_filename(audio_format, out_dir)
        outfile: Optional[Path] = self.set_outfile()
        if outfile is None:
            return

        try:
            self.get_lyrics(session)
        except Exception:
            pass

        self.save_album_cover(session)

        try:
            self.save_artist_image(session)
        except Exception:
            pass

        try:
            self.save_artist_bio(session)
        except Exception:
            pass

        if self.download(session, out_dir) is None:
            return

        self.craft_tags()
        self.set_tags()

        return str(self.outfile.absolute())

    def dump(self, fp=sys.stdout):
        k: int = int(self.metadata.track_number)
        if self.outfile is None:
            v: Optional[str] = None
        elif not isinstance(self.outfile, Path):
            v: Optional[str] = None
        else:
            v: Optional[str] = str(self.outfile.absolute())
        json.dump({k: v}, fp)
        return None

    def dumps(self) -> str:
        k: int = int(self.metadata.track_number)
        if self.outfile is None:
            v: Optional[str] = None
        elif not isinstance(self.outfile, Path):
            v: Optional[str] = None
        else:
            v: Optional[str] = str(self.outfile.absolute())
        json.dumps({k: v})
        return None
