from typing import Dict, List, Optional, Union

from dash import Manifest
from models import (
    AlbumsEndpointResponseJSON,
    TracksCreditsResponseJSON,
    TracksEndpointResponseJSON,
    TracksLyricsResponseJSON,
    TracksEndpointStreamResponseJSON,
)

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


def metadata_tags(
    tracks: "TracksEndpointResponseJSON",
    tracks_credits: Optional["TracksCreditsResponseJSON"],
    tracks_lyrics: Optional["TracksLyricsResponseJSON"],
    tracks_stream: "TracksEndpointStreamResponseJSON",
    track_manifest: "Manifest",
    albums: "AlbumsEndpointResponseJSON",
    tag_mapping: Dict[str, Dict[str, str]] = TAG_MAPPING,
) -> Dict[str, Union[str, int, float, List[str]]]:
    """Given several objects that represent responses from various Tidal API
    endpoints for a track and the album it belongs to, craft a dictionary of
    metadata tags. These tags should be able to be passed directly to a
    Mutagen subclass e.g. mutagen.flac.FLAC."""
    # https://dashif.org/codecs/audio/
    if track_manifest.codecs == "flac":
        codec = "flac"
    elif track_manifest.codecs == "mp4a.40.5":  # HE-AAC
        codec = "m4a"
    elif track_manifest.codecs == "mp4a.40.29":  # HE-AAC v2
        codec = "m4a"
    elif track_manifest.codecs == "mp4a.40.2":  # AAC-LC
        codec = "m4a"
    elif track_manifest.codecs == "eac3":  # Enhanced AC-3
        codec = "m4a"
    elif track_manifest.codecs == "mp4a.40.34":  # MP3
        codec = "mp3"

    tracks_stream_tags: Dict[str, str] = {
        tag_mapping[tag][codec]: str(getattr(tracks_stream, tag))
        for tag in {"album_replay_gain", "album_peak_amplitude"}
    }

    tracks_tags: Dict[str, str] = {
        tag_mapping["artists"][codec]: [a.name for a in tracks.artists],
        tag_mapping["artist"][codec]: ";".join((a.name for a in tracks.artists)),
        tag_mapping["comment"][codec]: tracks.url,
        tag_mapping["copyright"][codec]: tracks.copyright,
        tag_mapping["isrc"][codec]: tracks.isrc,
        tag_mapping["title"][codec]: tracks.name,
        tag_mapping["track_peak_amplitude"][codec]: f"{tracks.peak}",
        tag_mapping["track_replay_gain"][codec]: f"{tracks.replay_gain}",
    }

    album_tags: Dict[str, str] = {
        tag_mapping["album"][codec]: albums.title,
        tag_mapping["album_artist"][codec]: ";".join((a.name for a in albums.artists)),
        tag_mapping["barcode"][codec]: albums.upc,
        tag_mapping["date"][codec]: str(albums.release_date),
    }

    credits_tags: Dict[str, str] = dict()
    for tag in {"composer", "lyricist", "mixer", "producer", "remixer"}:
        try:
            _credits_tag = ";".join(getattr(tracks_credits, tag))
        except (TypeError, AttributeError):  # NoneType problems
            continue
        else:
            credits_tags[tag_mapping[tag][codec]] = _credits_tag

    # for some tracks, there are no lyrics
    lyrics_tags: Dict[str, str] = dict()
    try:
        lyrics_tags[tag_mapping["lyrics"][codec]] = tracks_lyrics.subtitles
    except (TypeError, AttributeError):  # NoneType problems
        _tags: Dict[str, str] = (
            tracks_stream_tags | tracks_tags | album_tags | credits_tags
        )
    else:
        _tags: Dict[str, str] = (
            tracks_stream_tags | tracks_tags | album_tags | credits_tags | lyrics_tags
        )

    if codec == "flac":
        _tags[tag_mapping["disc_number"][codec]] = f"{tracks.volume_number}"
        _tags[tag_mapping["discs"][codec]] = f"{albums.number_of_volumes}"
        _tags[tag_mapping["track_number"][codec]] = f"{tracks.track_number}"
        _tags[tag_mapping["total_tracks"][codec]] = f"{albums.number_of_tracks}"
    elif codec == "m4a":
        # Have to convert to bytes the values of the tags starting with '----'
        tags = _tags.copy()
        for k, v in tags.items():
            if k.startswith("----"):
                if isinstance(v, str):
                    _tags[k]: bytes = v.encode("UTF-8")
                elif isinstance(v, list):
                    _tags[k]: List[bytes] = [s.encode("UTF-8") for s in v]

        # track number, total tracks
        _tags["trkn"] = [(tracks.track_number, albums.number_of_tracks)]
        # disc number, total discs
        _tags["disk"] = [(tracks.volume_number, albums.number_of_volumes)]
    elif codec == "mp3":
        pass

    return {k: v for k, v in _tags.items() if v is not None}
