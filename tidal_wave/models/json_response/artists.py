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
    field_validator,
)

from .albums import AlbumsEndpointResponseJSON

class Artist(BaseModel):
    """Parse the JSON response from the TIDAL API, /artists endpoint.

    This class is a sub-object of the JSON response, representing the album's
    artist(s).
    """

    id: PositiveInt = Field(frozen=True)
    name: str = Field(frozen=True)
    artist_type: Literal["MAIN", "FEATURED"] = Field(alias="type", frozen=True)
    picture: UUID4 = Field(repr=False, frozen=True)

    @computed_field(repr=False)
    def picture_url(self) -> HttpUrl:
        """Set as property the URL to self's highest-quality JPEG file."""
        _path: str = self.picture.replace("-", "/")
        return f"https://resources.tidal.com/images/{_path}/750x750.jpg"


class ArtistsBioResponseJSON(BaseModel):
    """Represent the response from the TIDAL API endpoint /artists/<ID>/bio."""

    source: str = Field(frozen=True)
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
    items: list[AlbumsEndpointResponseJSON] = Field(frozen=True)