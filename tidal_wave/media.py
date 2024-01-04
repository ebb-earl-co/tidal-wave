from enum import Enum
from typing import Dict


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
