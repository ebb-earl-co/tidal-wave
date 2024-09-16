"""Represent with Pydantic the JSON responses from the TIDAL API, /artists endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import (
    UUID4,
    AwareDatetime,
    BaseModel,
    Field,
    HttpUrl,
    NonNegativeInt,
    PositiveInt,
    computed_field,
)

from .albums import AlbumsResponse
from .videos import VideosEndpointResponseJSON


class ArtistsEndpointResponseJSON(BaseModel):
    """Represent the response from the TIDAL API endpoint /artists."""

    # artist_types: Literal["ARTIST", "CONTRIBUTOR"]
    id: PositiveInt = Field(frozen=True)
    name: str = Field(frozen=True)
    picture: UUID4 | None = Field(
        default=None,
        frozen=True,
        repr=False,
    )
    url: HttpUrl = Field(
        examples=["http://www.tidal.com/artist/4950177"], frozen=True, repr=False
    )

    @computed_field(repr=False)
    def picture_url(self) -> HttpUrl:
        """Set as property the URL to self's JPEG file."""
        url_path: str = str(self.picture).replace("-", "/")
        # TODO: figure out which dimension is ideal here. Is non-square a no-go?
        # is 750x750 (the largest square dimensions) embeddable into fLaC, m4a?
        return f"https://resources.tidal.com/images/{url_path}/750x750.jpg"


class ArtistsBioResponseJSON(BaseModel):
    """Represent the response from the TIDAL API endpoint /artists/<ID>/bio."""

    source: str = Field(
        examples=["TiVo"],
        frozen=True,
    )
    last_updated: AwareDatetime = Field(
        alias="lastUpdated",
        frozen=True,
        repr=False,
        strict=False,  # so that pydantic parses str to date
    )
    text: str = Field(frozen=True, repr=False)
    summary: str = Field(frozen=True, repr=False)


class ArtistsAlbumsResponseJSON(BaseModel):
    """Represent the response from the TIDAL API endpoint /artists/<ID>/albums."""

    limit: NonNegativeInt = Field(frozen=True)
    offset: NonNegativeInt = Field(frozen=True)
    total_number_of_items: NonNegativeInt = Field(frozen=True)
    items: list[AlbumsResponse] = Field(frozen=True, repr=False)


class ArtistsVideosResponseJSON(BaseModel):
    """Represent the response from the TIDAL API endpoint /artists/<ID>/videos."""

    limit: NonNegativeInt = Field(frozen=True)
    offset: NonNegativeInt = Field(frozen=True)
    total_number_of_items: PositiveInt = Field(frozen=True)
    items: list[VideosEndpointResponseJSON] = Field(frozen=True, repr=False)
