from dataclasses import dataclass
from enum import Enum
import json
import logging
from pathlib import Path
import random
import shutil
import sys
import time
from typing import Dict, Iterator, List, Optional, Set, Tuple

from .dash import (
    manifester,
    JSONDASHManifest,
    Manifest,
    TidalManifestException,
    XMLDASHManifest,
)
from .hls import m3u8, playlister, variant_streams, TidalM3U8Exception
from .models import (
    AlbumsEndpointResponseJSON,
    AlbumsItemsResponseJSON,
    AlbumsReviewResponseJSON,
    ArtistsBioResponseJSON,
    TracksCreditsResponseJSON,
    TracksEndpointResponseJSON,
    TracksEndpointStreamResponseJSON,
    TracksLyricsResponseJSON,
    VideosEndpointResponseJSON,
)
from .playlists import get_playlist, PlaylistItem, PlaylistsItemsResponseJSON
from .requesting import (
    fetch_content_length,
    http_request_range_headers,
    request_album_items,
    request_album_review,
    request_albums,
    request_artist_bio,
    request_credits,
    request_lyrics,
    request_playlists,
    request_stream,
    request_tracks,
    request_video_contributors,
    request_video_stream,
    request_videos,
    ResponseJSON,
)
from .utils import download_artist_image, download_cover_image, temporary_file

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


class VideoFormat(str, Enum):
    high = "HIGH"
    medium = "MEDIUM"
    low = "LOW"
    audio_only = "AUDIO_ONLY"


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
    "director": {"flac": None, "m4a": "\xa9dir"},
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


def sleep_to_mimic_human_activity():
    _time = random.randint(500, 5000) / 500
    logger.info(f"Sleeping for {_time} seconds to mimic human activity")
    time.sleep(_time)
