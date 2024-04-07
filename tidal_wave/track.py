from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Dict, Iterable, List, Optional, Union

from .dash import (
    manifester,
    JSONDASHManifest,
    Manifest,
    TidalManifestException,
    XMLDASHManifest,
)
from .media import AudioFormat, TAG_MAPPING
from .models import (
    AlbumsEndpointResponseJSON,
    ArtistsBioResponseJSON,
    TracksCreditsResponseJSON,
    TracksEndpointResponseJSON,
    TracksEndpointStreamResponseJSON,
    TracksLyricsResponseJSON,
    download_artist_image,
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
from .utils import download_cover_image, temporary_file

import ffmpeg
import mutagen
from mutagen.mp4 import MP4Cover
from requests import Session
from Crypto.Cipher import AES
from Crypto.Util import Counter

logger = logging.getLogger("__name__")


@dataclass
class Track:
    track_id: int
    transparent: bool = False

    def __post_init__(self):
        self._has_lyrics: Optional[bool] = None
        self.tags: dict = {}
        self.af_aq: Dict[AudioFormat, str] = {
            AudioFormat.sony_360_reality_audio: "LOW",
            AudioFormat.dolby_atmos: "LOW",
            AudioFormat.hi_res: "HI_RES",
            AudioFormat.mqa: "HI_RES",
            AudioFormat.lossless: "LOSSLESS",
            AudioFormat.high: "HIGH",
            AudioFormat.low: "LOW",
        }

    def set_metadata(self, session: Session):
        """This method executes request_tracks, passing in 'session' and
        self.track_id. If an error occurs, self.metadata is set to None.
        Otherwise, self.metadata is set to the response of request_tracks(),
        a TracksEndpointResponseJSON instance."""
        self.metadata: Optional[TracksEndpointResponseJSON] = request_tracks(
            session=session, track_id=self.track_id, transparent=self.transparent
        )

    def set_album(self, session: Session):
        """This method executes request_albums, passing in 'session' and
        self.metadata.album.id. If an error occurs, self.album is set to None.
        Otherwise, self.album is set to the response of request_albums(),
        an AlbumsEndpointResponseJSON instance."""
        self.album: Optional[AlbumsEndpointResponseJSON] = request_albums(
            session=session,
            album_id=self.metadata.album.id,
            transparent=self.transparent,
        )

    def set_credits(self, session: Session):
        """This method executes request_credits, passing in 'session' and
        self.track_id. If an error occurs, self.credits is set to None.
        Otherwise, self.credits is set to the response of request_credits(),
        a TracksCreditsResponseJSON instance."""
        self.credits: Optional[TracksCreditsResponseJSON] = request_credits(
            session=session, track_id=self.track_id, transparent=self.transparent
        )

    def get_lyrics(self, session: Session):
        """This method executes request_lyrics, passing in 'session' and
        self.track_id. If an error occurs, self.lyrics is set to None
        and self._has_lyrics is set to False. Otherwise, self.lyrics is
        set to the response of request_lyrics(), an instance of
        TracksLyricsResponseJSON."""
        if self._has_lyrics is None:
            self.lyrics: Optional[TracksLyricsResponseJSON] = request_lyrics(
                session=session, track_id=self.track_id, transparent=self.transparent
            )
            if self.lyrics is None:
                self._has_lyrics = False
            else:
                self._has_lyrics = True
        else:
            return self.lyrics

    def set_stream(self, session: Session, audio_format: AudioFormat):
        """This method populates self.stream, which is either None
        (in the event of request error) or TracksEndpointStreamResponseJSON"""
        aq: Optional[str] = self.af_aq.get(audio_format)
        self.stream: Optional[TracksEndpointStreamResponseJSON] = request_stream(
            session, self.track_id, aq, transparent=self.transparent
        )

    def set_manifest(self):
        """This method sets self.manifest and self.codec"""
        try:
            self.manifest: Manifest = manifester(self.stream)
        except TidalManifestException as tme:
            logger.critical(tme.args[0])
            self.manifest = None
            self.codec = None
            return

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
        """This method sets self.album_dir, based on self.album and
        out_dir. In particular, self.album_dir is a subdirectory of out_dir
        based on the name of the album's artist"""
        artist_substring: str = self.album.artist.name.replace("..", "")
        album_substring: str = (
            f"{self.album.name} " f"[{self.album.id}] [{self.album.release_date.year}]"
        )
        self.album_dir: Path = out_dir / artist_substring / album_substring
        self.album_dir.mkdir(parents=True, exist_ok=True)

        # Create cover_path here, even if the API
        # does not return a cover, to avoid AttributeError later
        self.cover_path: Path = self.album_dir / "cover.jpg"

        if self.album.number_of_volumes > 1:
            volume_substring: str = f"Volume {self.metadata.volume_number}"
            (self.album_dir / volume_substring).mkdir(parents=True, exist_ok=True)

    def set_filename(self, audio_format: AudioFormat):
        """This method sets self.filename, which is based on self.metadata
        as well as audio_format. Additionally, if the available codecs in
        self.manifest don't match audio_format, warnings are logged"""
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
                    "Downloading of track will continue, but it will be marked as "
                    "MQA ([Q])."
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
        if self.filename is None:
            self.trackname: Optional[str] = None
        else:
            self.trackname: str = re.match(
                r"(?:\d{2,3} - )(.+?$)", self.filename
            ).groups()[0]

    def set_outfile(self):
        """Uses self.album_dir and self.metadata and self.filename
        to craft the pathlib.Path object, self.outfile, that is a
        reference to where the track will be written on disk."""
        if self.album.number_of_volumes > 1:
            self.outfile: Path = (
                self.album_dir / f"Volume {self.metadata.volume_number}" / self.filename
            )
            self.absolute_outfile = str(self.outfile.absolute())
        else:
            self.outfile: Path = self.album_dir / self.filename
            self.absolute_outfile = str(self.outfile.absolute())

        # Keep absolute_outfile under 260-character limit
        if len(self.absolute_outfile) >= 260:
            outfile: str = f"{self.metadata.track_number:02d}.{self.codec}"
            if len(outfile) >= 260:
                logger.warning(
                    f"Unable to fit title of track {self.track_id} "
                    f"into a valid filename (even '{outfile}'), as "
                    "total character count exceeds Windows' 260-character "
                    "limit. Downloading will not continue"
                )
                return

            self.outfile: Path = Path(self.absolute_outfile).parent / outfile
            self.absolute_outfile: str = str(self.outfile.absolute())
            self.trackname: str = outfile

        if (self.outfile.exists()) and (self.outfile.stat().st_size > 0):
            logger.info(
                f"Track {self.absolute_outfile} already exists "
                "and therefore will not be overwritten"
            )
            return
        else:
            return self.outfile

    def save_artist_image(self, session: Session):
        """This method writes a JPEG file with the name of each of
        self.metadata.artists to self.album_dir"""
        for a in self.metadata.artists:
            track_artist_image: Path = (
                self.album_dir / f"{a.name.replace('..', '')}.jpg"
            )
            if not track_artist_image.exists():
                download_artist_image(session, a, self.album_dir)

    def save_artist_bio(self, session: Session):
        """This method writes a JSON file with the name of each of
        self.metadata.artists to self.album_dir"""
        for a in self.metadata.artists:
            track_artist_bio_json: Path = self.album_dir / f"{a.name}-bio.json"
            if not track_artist_bio_json.exists():
                artist_bio: Optional[ArtistsBioResponseJSON] = request_artist_bio(
                    session=session, artist_id=a.id, transparent=self.transparent
                )
                if artist_bio is not None:
                    logger.info(
                        f"Writing artist bio for artist {a.id} to "
                        f"'{str(track_artist_bio_json.absolute())}"
                    )
                    track_artist_bio_json.write_text(artist_bio.to_json())

    def save_album_cover(self, session: Session):
        """This method saves cover.jpg to self.album_dir; the bytes for cover.jpg
        come from self.album.cover"""
        if not self.cover_path.exists():
            download_cover_image(
                session=session, cover_uuid=self.album.cover, output_dir=self.album_dir
            )

    def set_urls(self, session: Session):
        """This method sets self.urls based on self.manifest"""
        if isinstance(self.manifest, JSONDASHManifest):
            self.urls: List[str] = self.manifest.urls
        elif isinstance(self.manifest, XMLDASHManifest):
            self.urls: List[str] = self.manifest.build_urls(session=session)
        self.download_headers: Dict[str, str] = {"Accept": self.manifest.mime_type}
        if session.session_id is not None:
            self.download_headers["sessionId"] = session.session_id
        self.download_params = {k: None for k in session.params}

    def download_url(self, session: Session, out_dir: Path) -> Optional[Path]:
        """This method downloads self.urls[0], for use in situations when
        the manifest returned by TIDAL API contains one URL. It relies on
        byte range headers to incrementally get all content from a URL"""
        logger.info(f"Writing track {self.track_id} to '{self.absolute_outfile}'")
        # Implement HTTP range requests here to mimic official clients
        range_size: int = 1024 * 1024  # 1 MiB
        content_length: int = fetch_content_length(session=session, url=self.urls[0])
        if content_length == 0:
            return

        range_headers: Iterable[str] = http_request_range_headers(
            content_length=content_length,
            range_size=range_size,
            return_tuple=False,
        )

        with temporary_file(suffix=".mp4") as ntf:
            for rh in range_headers:
                with session.get(
                    self.urls[0], params=self.download_params, headers={"Range": rh}
                ) as rr:
                    if not rr.ok:
                        logger.warning(f"Could not download {self}")
                        return
                    else:
                        ntf.write(rr.content)
                        logger.debug(
                            f"Wrote {rh} of track {self.track_id} to '{ntf.name}'"
                        )
            else:
                ntf.seek(0)
                logger.debug(f"Finished writing track {self.track_id} to '{ntf.name}'")

            if (self.manifest.key is not None) and (self.manifest.nonce is not None):
                logger.info(
                    f"Audio data for track {self.track_id} is encrypted. "
                    "Attempting to decrypt now"
                )
                counter: Dict[str, Union[int, bytes, bool]] = Counter.new(
                    64, prefix=self.manifest.nonce, initial_value=0
                )
                decryptor = AES.new(self.manifest.key, AES.MODE_CTR, counter=counter)

                # decrypt and write to new temporary file
                with temporary_file(suffix=".mp4") as f_decrypted:
                    # I hope that it doesn't come back to bite me, reading the bytes
                    # from a file with an open 'wb' file descriptor context manager
                    audio_bytes: bytes = decryptor.decrypt(Path(ntf.name).read_bytes())
                    f_decrypted.write(audio_bytes)
                    logger.info(
                        f"Audio data for track {self.track_id} has been decrypted."
                    )

                    if self.codec == "flac":
                        # Have to use FFMPEG to re-mux the audio bytes, otherwise
                        # mutagen chokes on NoFlacHeaderError
                        logger.debug(
                            f"Using FFmpeg to remux '{f_decrypted.name}', "
                            f"writing to '{self.absolute_outfile}'"
                        )
                        ffmpeg.input(f_decrypted.name, hide_banner=None, y=None).output(
                            self.absolute_outfile,
                            acodec="copy",
                            loglevel="quiet",
                        ).run()
                    elif self.codec == "m4a":
                        shutil.copyfile(f_decrypted.name, self.outfile)
                    elif self.codec == "mka":
                        shutil.copyfile(f_decrypted.name, self.outfile)

                    logger.info(
                        f"Track {self.track_id} written to '{self.absolute_outfile}'"
                    )
                    return self.outfile
            else:
                if self.codec == "flac":
                    # Have to use FFMPEG to re-mux the audio bytes, otherwise
                    # mutagen chokes on NoFlacHeaderError
                    logger.debug(
                        f"Using FFmpeg to remux '{ntf.name}', "
                        f"writing to '{self.absolute_outfile}'"
                    )
                    ffmpeg.input(ntf.name, hide_banner=None, y=None).output(
                        self.absolute_outfile,
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

    def download_urls(self, session: Session, out_dir: Path) -> Optional[Path]:
        """This method writes the contents from self.urls to a temporary
        directory, then uses FFmpeg to re-mux the data to self.outfile"""
        logger.info(f"Writing track {self.track_id} to '{self.absolute_outfile}'")

        with temporary_file(suffix=".mp4") as ntf:
            for i, u in enumerate(self.urls, 1):
                _url: str = u.split("?")[0]
                logger.debug(
                    f"Requesting part {i} of track {self.track_id} "
                    f"from '{_url}', writing to '{ntf.name}'"
                )
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

            if (self.manifest.key is not None) and (self.manifest.nonce is not None):
                logger.info(
                    f"Audio data for track {self.track_id} is encrypted. "
                    "Attempting to decrypt now"
                )
                counter: Dict[str, Union[int, bytes, bool]] = Counter.new(
                    64, prefix=self.manifest.nonce, initial_value=0
                )
                decryptor = AES.new(self.manifest.key, AES.MODE_CTR, counter=counter)
                # decrypt and write to new temporary file
                with temporary_file(suffix=".mp4") as f_decrypted:
                    # I hope that it doesn't come back to bite me, reading the bytes
                    # from a file with an open 'wb' file descriptor context manager
                    audio_bytes: bytes = decryptor.decrypt(Path(ntf.name).read_bytes())
                    f_decrypted.write(audio_bytes)
                    logger.info(
                        f"Audio data for track {self.track_id} has been decrypted."
                    )

                    if self.codec == "flac":
                        # Have to use FFMPEG to re-mux the audio bytes, otherwise
                        # mutagen chokes on NoFlacHeaderError
                        logger.debug(
                            f"Using FFmpeg to remux '{f_decrypted.name}', "
                            f"writing to '{self.absolute_outfile}'"
                        )
                        ffmpeg.input(f_decrypted.name, hide_banner=None, y=None).output(
                            self.absolute_outfile,
                            acodec="copy",
                            loglevel="quiet",
                        ).run()
                    elif self.codec == "m4a":
                        shutil.copyfile(f_decrypted.name, self.outfile)
                    elif self.codec == "mka":
                        shutil.copyfile(f_decrypted.name, self.outfile)

                    logger.info(
                        f"Track {self.track_id} written to '{self.absolute_outfile}'"
                    )
                    return self.outfile
            else:
                if self.codec == "flac":
                    # Have to use FFmpeg to re-mux the audio bytes, otherwise
                    # mutagen chokes on NoFlacHeaderError
                    logger.debug(
                        f"Using FFmpeg to remux '{ntf.name}', "
                        f"writing to '{self.absolute_outfile}'"
                    )
                    ffmpeg.input(ntf.name, hide_banner=None, y=None).output(
                        self.absolute_outfile, acodec="copy", loglevel="quiet"
                    ).run()
                elif self.codec == "m4a":
                    shutil.copyfile(ntf.name, self.outfile)
                elif self.codec == "mka":
                    shutil.copyfile(ntf.name, self.outfile)

                logger.info(
                    f"Track {self.track_id} written to '{self.absolute_outfile}'"
                )
                return self.outfile

    def download(self, session: Session, out_dir: Path) -> Optional[Path]:
        """This method GETs the data from self.urls and writes it
        to self.outfile."""
        if len(self.urls) == 1:
            outfile: Optional[Path] = self.download_url(
                session=session, out_dir=out_dir
            )
        else:
            outfile: Optional[Path] = self.download_urls(
                session=session, out_dir=out_dir
            )

        return outfile

    def craft_tags(self):
        """Using the TAG_MAPPING dictionary, add the correct values
        of various metadata tags to the attribute self.tags.
        E.g. for .flac files, the album's artist is 'ALBUMARTIST',
        but for .m4a files, the album's artist is 'aART'."""
        tags = dict()
        if (self.codec == "flac") or (self.codec == "mka"):
            tag_map = {k: v["flac"] for k, v in TAG_MAPPING.items()}
        elif self.codec == "m4a":
            tag_map = {k: v["m4a"] for k, v in TAG_MAPPING.items()}

        tags[tag_map["album"]] = self.album.title
        tags[tag_map["album_artist"]] = ";".join((a.name for a in self.album.artists))
        tags[tag_map["album_peak_amplitude"]] = (
            f"{self.stream.album_peak_amplitude}"
            if self.stream.album_peak_amplitude is not None
            else None
        )
        tags[tag_map["album_replay_gain"]] = (
            f"{self.stream.album_replay_gain}"
            if self.stream.album_replay_gain is not None
            else None
        )
        tags[tag_map["artist"]] = ";".join((a.name for a in self.metadata.artists))
        tags[tag_map["artists"]] = [a.name for a in self.metadata.artists]
        tags[tag_map["barcode"]] = self.album.upc
        tags[tag_map["copyright"]] = self.metadata.copyright
        tags[tag_map["date"]] = str(self.album.release_date)
        tags[tag_map["isrc"]] = self.metadata.isrc
        tags[tag_map["media"]] = "Digital Media"
        tags[tag_map["title"]] = self.metadata.name
        tags[tag_map["track_peak_amplitude"]] = f"{self.metadata.peak}"
        tags[tag_map["track_peak_amplitude"]] = (
            f"{self.metadata.peak}" if self.metadata.peak is not None else None
        )
        tags[tag_map["track_replay_gain"]] = (
            f"{self.metadata.replay_gain}"
            if self.metadata.replay_gain is not None
            else None
        )
        # credits
        for tag in {"composer", "engineer", "lyricist", "mixer", "producer", "remixer"}:
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

        if self.codec == "flac":
            tags[tag_map["comment"]] = self.metadata.url
            # track and disk
            tags["DISCTOTAL"] = f"{self.album.number_of_volumes}"
            tags["DISC"] = f"{self.metadata.volume_number}"
            tags["TRACKTOTAL"] = f"{self.album.number_of_tracks}"
            tags["TRACKNUMBER"] = f"{self.metadata.track_number}"
            # instrument-specific
            #     piano
            try:
                piano_credits: List[str] = [
                    f"{{{pc}}} (piano)" for pc in self.credits.piano
                ]
            except (TypeError, AttributeError):  # NoneType problems
                pass
            else:
                tags["PERFORMER"] = piano_credits

        elif self.codec == "m4a":
            tags["\xa9url"] = self.metadata.url
            # Whether explicit field, 'rtng', does not have a FLAC counterpart
            if self.metadata.explicit is None:
                tags["rtng"] = (0,)
            elif not self.metadata.explicit:
                tags["rtng"] = (1,)
            elif self.metadata.explicit:
                tags["rtng"] = (2,)

            tags["pcst"] = 0  # I.e. False because we are not working with podcasts here
            tags["stik"] = (1,)  # Music (https://exiftool.org/TagNames/QuickTime.html)

            # Have to convert to bytes the values of the tags starting with '----'
            for k, v in tags.copy().items():
                if k.startswith("----"):
                    if isinstance(v, str):
                        tags[k] = v.encode("UTF-8")
                    elif isinstance(v, list):
                        tags[k] = [s.encode("UTF-8") for s in v]

            tags["trkn"] = [(self.metadata.track_number, self.album.number_of_tracks)]
            tags["disk"] = [(self.metadata.volume_number, self.album.number_of_volumes)]

        self.tags: dict = {k: v for k, v in tags.items() if v is not None}

    def set_mutagen(self):
        """This method creates self.mutagen, an instance of mutagen.File, pointing
        to self.outfile"""
        self.mutagen = mutagen.File(self.outfile)
        self.mutagen.clear()
        self.mutagen.save()

    def set_cover_image_tag(self, dimension: int = 1280):
        """This method sets the metadata tag 'covr' in the case of .m4a files,
        and adds a mutagen.flac.Picture() tag to self.mutagen in the case of
        .flac files. It has been split out from self.set_tags so that it
        can be executed BEFORE self.remux(): otherwise, the .m4a
        metadata tags starting with '----com.apple.iTunes:' are lost"""
        if self.codec == "flac":
            p = mutagen.flac.Picture()
            p.type = mutagen.id3.PictureType.COVER_FRONT
            p.desc = "Album Cover"
            p.width = p.height = dimension
            p.mime = "image/jpeg"
            p.data = self.cover_path.read_bytes()
            self.mutagen.add_picture(p)
        elif self.codec == "m4a":
            self.mutagen["covr"] = [
                MP4Cover(self.cover_path.read_bytes(), imageformat=MP4Cover.FORMAT_JPEG)
            ]

        self.mutagen.save()

    def set_tags(self):
        """Add self.tags to self.mutagen, and save the changes to disk"""
        self.mutagen.update(**self.tags)
        self.mutagen.save()

    def remux(self):
        """It is currently not possible to have mutagen set the order of
        the tracks in the audio file; that is, sometimes the album cover
        "video" track is reported as the 0th track by FFmpeg. Some audio
        players cannot decode this as an audio file, so this method
        runs an FFmpeg command externally to make sure that self.outfile
        has the audio data as the first (and, potentially, only) stream
        according to FFmpeg."""
        if self.codec == "flac":
            _cmd: str = f"""ffmpeg -hide_banner -loglevel quiet -y -i "%s"
                -map 0:a:0 -map 0:v:0 -map_metadata 0 -c:a copy -c:v copy
                -metadata:s:v title='Album cover' -metadata:s:v comment='Cover (front)'
                -disposition:v attached_pic "{self.absolute_outfile}" """
            if getattr(self.mutagen, "pictures") is not None:
                if (
                    isinstance(self.mutagen.pictures, list)
                    and len(self.mutagen.pictures) == 1
                ):
                    if isinstance(self.mutagen.pictures[0], mutagen.flac.Picture):
                        with temporary_file(suffix=".flac") as tf:
                            shutil.move(self.absolute_outfile, tf.name)
                            cmd: List[str] = shlex.split(_cmd % tf.name)
                            subprocess.run(cmd)

        elif self.codec == "m4a":
            _cmd: str = f"""ffmpeg -hide_banner -loglevel quiet -y -i "{self.absolute_outfile}"
                -map 0:a:0 -map 0:v:0 -map_metadata 0 -c:a copy -c:v copy -movflags +faststart "%s" """
            if self.mutagen.get("covr") is not None:
                if isinstance(self.mutagen["covr"], list):
                    if len(self.mutagen["covr"]) == 1:
                        if isinstance(self.mutagen["covr"][0], MP4Cover):
                            with temporary_file(suffix=".mp4") as tf:
                                cmd: List[str] = shlex.split(_cmd % tf.name)
                                subprocess.run(cmd)
                                shutil.copyfile(tf.name, self.absolute_outfile)

    def get(
        self,
        session: Session,
        audio_format: AudioFormat,
        out_dir: Path,
        metadata: Optional[TracksEndpointResponseJSON] = None,
        album: Optional[AlbumsEndpointResponseJSON] = None,
        no_extra_files: bool = True,
        transparent: bool = False,
    ) -> Optional[str]:
        """This is the main driver method of Track. It executes the other
        methods in order, catching Exceptions and attempting to handle
        edge cases."""

        if metadata is None:
            self.set_metadata(session)
        else:
            self.metadata = metadata

        if self.metadata is None:
            self.outfile = None
            return

        if "DOLBY_ATMOS" in self.metadata.media_metadata.tags:
            if audio_format != AudioFormat.dolby_atmos:
                logger.warning(
                    f"Track {self.track_id} is only available in Dolby Atmos "
                    "format. Downloading of track will not continue."
                )
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
            self.set_album(session)
        else:
            self.album = album

        if self.album is None:
            self.outfile = None
            return
        else:
            self.set_album_dir(out_dir)

        self.set_credits(session)
        self.set_stream(session, audio_format)
        if self.stream is None:
            self.outfile = None
            return

        self.set_manifest()
        if self.manifest is None:
            self.outfile = None
            return

        self.set_filename(audio_format)
        if self.filename is None:
            self.outfile = None
            return

        outfile: Optional[Path] = self.set_outfile()
        if outfile is None:
            if not no_extra_files:
                try:
                    self.save_artist_image(session)
                except Exception:
                    pass

                try:
                    self.save_artist_bio(session)
                except Exception:
                    pass

            return

        try:
            self.get_lyrics(session)
        except Exception:
            pass

        self.set_urls(session)

        if self.download(session, out_dir) is None:
            return

        self.set_mutagen()

        if self.album.cover == "":
            logger.warning(
                f"No cover image was returned from TIDAL API for album {self.album.id}"
            )
        else:
            self.save_album_cover(session)
            if self.cover_path.exists() and self.cover_path.stat().st_size > 0:
                self.set_cover_image_tag()

        self.remux()
        self.craft_tags()
        self.set_tags()

        if not no_extra_files:
            try:
                self.save_artist_image(session)
            except Exception:
                pass

            try:
                self.save_artist_bio(session)
            except Exception:
                pass
        else:
            try:
                self.cover_path.unlink()
            except FileNotFoundError:
                pass

        return self.absolute_outfile

    def dump(self, fp=sys.stdout):
        """This method emulates stdlib json.dump() in that it sends to 'fp'
        a JSON-like object: particularly,
        {self.metadata.track_number: self.absolute_outfile}"""
        k: int = int(self.metadata.track_number)
        if self.outfile is None:
            v: Optional[str] = None
        elif not isinstance(self.outfile, Path):
            v: Optional[str] = None
        else:
            v: Optional[str] = self.absolute_outfile
        json.dump({k: v}, fp)
        return None

    def dumps(self) -> str:
        """This method emulates stdlib json.dumps(). It creates a
        JSON-formatted string from the dict
        {self.metadata.track_number: self.absolute_outfile}
        """
        k: int = int(self.metadata.track_number)
        if self.outfile is None:
            v: Optional[str] = None
        elif not isinstance(self.outfile, Path):
            v: Optional[str] = None
        else:
            v: Optional[str] = self.absolute_outfile
        json.dumps({k: v})
        return None
