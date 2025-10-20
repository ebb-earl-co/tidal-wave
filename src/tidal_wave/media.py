"""Represent various media metadata and formats."""

from __future__ import annotations

from enum import Enum


class AudioFormat(str, Enum):
    """Simple representation of TIDAL's music data quality levels."""

    dolby_atmos = "Atmos"
    hi_res = "HiRes"
    lossless = "Lossless"
    high = "High"
    low = "Low"


TAG_MAPPING: dict[str, dict[str, str]] = {
    "album": {"flac": "ALBUM", "m4a": "\xa9alb"},
    "album_artist": {"flac": "ALBUMARTIST", "m4a": "aART"},
    "artist": {"flac": "ARTIST", "m4a": "\xa9ART"},
    "artists": {"flac": "ARTISTS", "m4a": "----:com.apple.iTunes:ARTISTS"},
    "barcode": {"flac": "BARCODE", "m4a": "----:com.apple.iTunes:BARCODE"},
    "comment": {"flac": "COMMENT", "m4a": "\xa9cmt"},
    "composer": {"flac": "COMPOSER", "m4a": "\xa9wrt"},
    "copyright": {"flac": "COPYRIGHT", "m4a": "cprt"},
    "date": {"flac": "DATE", "m4a": "\xa9day"},
    "director": {"flac": "DIRECTOR", "m4a": "\xa9dir"},
    "engineer": {"flac": "ENGINEER", "m4a": "----:com.apple.iTunes:ENGINEER"},
    "isrc": {"flac": "ISRC", "m4a": "----:com.apple.iTunes:ISRC"},
    "language": {"flac": "LANGUAGE", "m4a": "----:com.apple.iTunes:LANGUAGE"},
    "location": {"flac": "LOCATION", "m4a": "\xa9xyz"},
    "lyrics": {"flac": "LYRICS", "m4a": "\xa9lyr"},
    "lyricist": {"flac": "LYRICIST", "m4a": "----:com.apple.iTunes:LYRICIST"},
    "media": {"flac": "MEDIA", "m4a": "----:com.apple.iTunes:MEDIA"},
    "mixer": {"flac": "MIXER", "m4a": "----:com.apple.iTunes:MIXER"},
    "performer": {"flac": "PERFORMER", "m4a": "perf"},
    "producer": {"flac": "PRODUCER", "m4a": "\xa9prd"},
    "publisher": {"flac": "PUBLISHER", "m4a": "\xa9pub"},
    "rating": {"flac": None, "m4a": "rtng"},  # 0 if None; 1 if clean; 2 if explicit
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
