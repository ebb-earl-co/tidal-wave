"""Represent with Pydantic the JSON responses from the TIDAL API, /videos endpoint."""

from __future__ import annotations

import base64
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    NonNegativeInt,
    PositiveInt,
    computed_field,
)

from . import Artist
from .. import replace_illegal_characters


class VideosEndpointResponseJSON(BaseModel):
    """Response from the TIDAL API, videos/<VIDEOID> endpoint.If the params and
    headers are correctly specified, the API returns metadata of the available
    version of the (music) video, including video quality, video title, date,
    video artists, duration, etc."""

    id: PositiveInt = Field(repr=False)
    title: str = Field(frozen=True, repr=True)
    volume_number: PositiveInt = Field(alias="volumeNumber", frozen=True)
    track_number: PositiveInt = Field(alias="trackNumber", frozen=True)
    release_date: AwareDatetime = Field(
        alias="releaseDate",
        frozen=True,
        repr=False,
        strict=False,  # so that pydantic parses str to date
    )
    duration: NonNegativeInt = Field(
        description="The length of the video in seconds.",
        examples=[145, 252],
        frozen=True,
    )
    quality: str
    explicit: bool = Field(
        frozen=True,
        repr=False,
    )
    type: str
    artist: Artist = Field(
        frozen=True,
        repr=False,
    )
    artists: list[Artist] = Field(
        frozen=True,
        repr=False,
    )

    @computed_field
    def name(self) -> str:
        """Set the attribute self.name based on self.title."""
        return replace_illegal_characters(self.title)


class VideosEndpointStreamResponseJSON(BaseModel):
    """Represent the response from the TIDAL API videos/<VIDEO_ID> endpoint.

    In particular, when the stream response was requested. The params and
    headers, if correctly specified, return the manifest of the video to be
    streamed. The manifest is a Base 64-encoded JSON object containing a .m3u8 URL.
    """

    video_id: PositiveInt = Field(frozen=True)
    video_quality: Literal["HIGH", "MEDIUM", "LOW", "AUDIO_ONLY"] = Field(frozen=True)
    manifest: str = Field(repr=False, frozen=True)
    manifest_mime_type: str = Field(frozen=True, repr=False)

    @computed_field
    def manifest_bytes(self) -> bytes:
        """Set the attribute self.manifest_bytes based on self.manifest."""
        return base64.b64decode(self.manifest)


class VideoContributor(BaseModel):
    """Model part of the response from the TIDAL API endpoint /videos/<ID>/credits.

    The entire response is an array of objects, each of which is modeled by this
    class. It is simply the name of a contributor to a video, and the role of that
    contributor.
    """

    name: str = Field(frozen=True)
    role: str = Field(frozen=True)


class VideosContributorsResponseJSON(BaseModel):
    """Model the response from the TIDAL API endpoint /videos/<ID>/contributors."""

    limit: NonNegativeInt = Field(frozen=True)
    offset: NonNegativeInt = Field(frozen=True)
    total_number_of_items: NonNegativeInt = Field(frozen=True)
    items: list[VideoContributor] = Field(frozen=True, repr=False)
