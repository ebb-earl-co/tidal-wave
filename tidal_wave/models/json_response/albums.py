"""Represent with Pydantic the JSON responses from the TIDAL API, /albums endpoint."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import (
    UUID4,
    BaseModel,
    Field,
    HttpUrl,
    NonNegativeInt,
    PositiveInt,
    computed_field,
    field_validator,
)

from .artists import Artist


class AlbumsResponse(BaseModel):
    """Parse the JSON response from the TIDAL API, /albums endpoint."""

    id: int = Field(frozen=True, ge=10, le=999_999_999)  # 2- to 9-digit number
    title: str = Field(
        frozen=True,
        description=(
            "The title of the album. N.b., if the album is a special version, "
            "that is not denoted here."
        ),
    )
    duration: int = Field(
        frozen=True,
        description="Total runtime, in seconds, of album's tracks and/or videos.",
        repr=False,
    )
    number_of_tracks: PositiveInt = Field(
        alias="numberOfTracks",
        frozen=True,
        repr=False,
        strict=True,
    )
    number_of_videos: NonNegativeInt = Field(
        alias="numberOfVideos",
        frozen=True,
        repr=False,
        strict=True,
    )
    number_of_volumes: PositiveInt = Field(
        alias="numberOfVolumes",
        frozen=True,
        repr=False,
        strict=True,
    )
    release_date: date = Field(
        alias="releaseDate",
        frozen=True,
        repr=False,
        strict=False,  # so that pydantic parses str to date
    )
    copyright: str = Field(repr=False)
    album_type: str = Field(alias="type", strict=True, repr=False)
    version: str | None = Field(repr=False)
    url: HttpUrl = Field(repr=False)
    cover: UUID4 = Field(repr=False)
    explicit: bool = Field(repr=False)
    upc: str = Field(pattern=r"\d", strict=True, repr=False)
    audio_quality: Literal[
        "HI_RES",
        "HIRES_LOSSLESS",
        "LOSSLESS",
        "DOLBY_ATMOS",
        "HIGH",
        "LOW",
    ] = Field(alias="audioQuality", repr=False)
    audio_modes: frozenset[Literal["DOLBY_ATMOS", "STEREO"]] = Field(
        alias="audioModes",
        strict=False,  # to cast from list
        repr=False,
    )
    media_metadata: frozenset[
        Literal["HI_RES", "HIRES_LOSSLESS", "LOSSLESS", "DOLBY_ATMOS", "HIGH", "LOW"]
    ] = Field(alias="mediaMetadata")
    artist: Artist = Field(repr=False)
    artists: frozenset[Artist]

    @staticmethod
    def replace_illegal_characters(input_str: str) -> str | None:
        """Replace troublesome characters in album title, version.

        Troublesome characters either crash the program on Windows or cause
        difficulties with file names on all systems.
        """
        if input_str is None:
            return input_str
        return (
            input_str.replace("/", "_")
            .replace("|", "_")
            .replace(":", " -")
            .replace('"', "")
            .replace(">", "")
            .replace("<", "")
            .replace("/", "")
            .replace("\\", "")
            .replace("?", "")
            .replace(" ?", "")
            .replace("? ", "")
            .replace("*", "")
            .replace("\0", "")  # ASCII null character
        )

    @field_validator("release_date", mode="before")
    @classmethod
    def non_future_date(cls, rd: str) -> date:
        """Validate self.release_date is a date NOT in the future."""
        _release_date: date = datetime.strptime(rd, "%Y-%m-%d").date()  # noqa:DTZ007
        try:
            assert _release_date <= date.today()  # noqa:S101,DTZ011
        except AssertionError:
            _msg: str = "Field releaseDate must not be a date in the future."
            raise ValueError(_msg) from None
        else:
            return _release_date

    @field_validator("media_metadata", mode="before")
    @classmethod
    def unnest_media_metadata(
        cls,
        raw: dict[
            Literal["tags"],
            list[
                Literal[
                    "HI_RES",
                    "HIRES_LOSSLESS",
                    "LOSSLESS",
                    "DOLBY_ATMOS",
                    "HIGH",
                    "LOW",
                ]
            ],
        ],
    ) -> set[
        Literal["HI_RES", "HIRES_LOSSLESS", "LOSSLESS", "DOLBY_ATMOS", "HIGH", "LOW"]
    ]:
        """Convert single-key dict value from list of str to set of str."""
        return {*raw["tags"]}

    @computed_field
    def name(self) -> str:
        """Set as property self's title and version, if there is a version."""
        _title: str = self.replace_illegal_characters(self.title)
        _version: str = self.replace_illegal_characters(self.version)
        if _version is not None:
            return f"{_title} ({_version})"
        return _title

    @computed_field(repr=False)
    def cover_url(self) -> HttpUrl:
        """Set as property the URL to self's JPEG file."""
        _cover_path: str = self.cover.replace("-", "/")
        return f"https://resources.tidal.com/images/{_cover_path}/1280x1280.jpg"

    @computed_field(repr=False)
    def original_cover_url(self) -> HttpUrl:
        """Set as property the URL to self's highest-quality JPEG file."""
        _original_cover_path: str = self.cover.replace("-", "/")
        return f"https://resources.tidal.com/images/{_original_cover_path}/origin.jpg"
