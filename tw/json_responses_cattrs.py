"""Emulate TIDAL API JSON responses with dataclasses for cattrs."""

from __future__ import annotations

from datetime import date  # noqa: TC003
from typing import Literal
from uuid import UUID

from attrs import Attribute, define, field
from attrs.validators import ge, gt, matches_re, min_len, optional
from cattrs.preconf.orjson import make_converter

albums_response: bytes = b'{"id":312622039,"title":"Intermundia","duration":2994,"streamReady":true,"adSupportedStreamReady":true,"djReady":true,"stemReady":false,"streamStartDate":"2024-02-23T00:00:00.000+0000","allowStreaming":true,"premiumStreamingOnly":false,"numberOfTracks":14,"numberOfVideos":0,"numberOfVolumes":1,"releaseDate":"2024-02-23","copyright":"(P) 2023 Olivia Belli, under exclusive license to XXIM Records, a label of Sony Music Entertainment","type":"ALBUM","version":null,"url":"http://www.tidal.com/album/312622039","cover":"d0a49570-bf83-4f15-afa6-74c66367c0b5","vibrantColor":"#beaf78","videoCover":null,"explicit":false,"upc":"196871260893","popularity":5,"audioQuality":"LOW","audioModes":["DOLBY_ATMOS"],"mediaMetadata":{"tags":["DOLBY_ATMOS"]},"upload":false,"artist":{"id":8438465,"name":"Olivia Belli","handle":null,"type":"MAIN","picture":"6d6d8d14-f046-4dd9-b3c1-df21c5bd11d6"},"artists":[{"id":8438465,"name":"Olivia Belli","handle":null,"type":"MAIN","picture":"6d6d8d14-f046-4dd9-b3c1-df21c5bd11d6"}]}'

converter = make_converter()


def valid_uuid4(
    instance: AlbumsResponseArtist | AlbumsResponse,  # noqa: ARG001
    attribute: Attribute,  # noqa: ARG001
    value: str,
) -> bool:
    """Whether candidate string is a valid UUID, version 4."""
    u: UUID = UUID(value, version=4)
    return u.hex == value.replace("-", "")


@define(slots=True, frozen=True)
class MediaMetadata:  # noqa: D101
    tags: list[Literal["LOSSLESS", "HIRES_LOSSLESS", "DOLBY_ATMOS"]]


@define(slots=True, repr=False, frozen=True)
class AlbumsResponseArtist:  # noqa: D101
    id: int = field(validator=ge(0))
    name: str = field(validator=min_len(1))
    type: Literal["MAIN"]
    picture: str | None = field(validator=optional(valid_uuid4))


@define(slots=True)
class AlbumsResponse:
    """The JSON response from https://api.tidal.com/v1/albums."""

    id: int = field(validator=ge(0))
    title: str = field(validator=min_len(1))
    duration: int = field(validator=gt(0))
    streamReady: bool = field(repr=False)  # noqa: N815
    adSupportedStreamReady: bool = field(repr=False)  # noqa: N815
    djReady: bool = field(repr=False)  # noqa: N815
    stemReady: bool = field(repr=False)  # noqa: N815
    streamStartDate: bool = field(repr=False)  # noqa: N815
    allowStreaming: bool = field(repr=False)  # noqa: N815
    premiumStreamingOnly: bool = field(repr=False)  # noqa: N815
    numberOfTracks: int = field(alias="number_of_tracks", validator=ge(0))  # noqa: N815
    numberOfVideos: int = field(alias="number_of_videos", validator=ge(0))  # noqa: N815
    numberOfVolumes: int = field(alias="number_of_volumes", validator=ge(1))  # noqa: N815
    releaseDate: date = field(alias="release_date")  # noqa: N815
    copyright: str = field(repr=False)
    type: Literal["ALBUM", "SINGLE", "EP"] = field(repr=False)
    version: str | None
    url: str = field(
        repr=False,
        validator=matches_re(r"^http://www.tidal.com/album/[0-9]+$"),
    )
    cover: str | None = field(repr=False, validator=optional(valid_uuid4))
    vibrantColor: str | None = field(  # noqa: N815
        repr=False,
        validator=optional(matches_re(r"^#[a-zA-Z0-9]+")),
    )
    videoCover: str | None = field(  # noqa: N815
        alias="video_cover",
        repr=False,
        validator=optional(valid_uuid4),
    )
    explicit: bool = field(repr=False)
    upc: str = field(repr=False)
    popularity: int | None = field(repr=False)
    audioQuality: Literal["LOW", "HIGH", "LOSSLESS"] = field(alias="audio_quality")  # noqa: N815
    audioModes: list[Literal["STEREO", "DOLBY_ATMOS"]] = field(alias="audio_modes")  # noqa: N815
    mediaMetadata: MediaMetadata = field(alias="media_metadata", repr=False)  # noqa: N815
    upload: bool = field(repr=False)
    artist: AlbumsResponseArtist = field(repr=False)
    artists: list[AlbumsResponseArtist] = field(repr=False)


if __name__ == "__main__":
    json_response = converter.loads(albums_response, AlbumsResponse)
    print(dir(json_response))
