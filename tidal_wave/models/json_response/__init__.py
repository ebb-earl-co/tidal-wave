"""Represent with Pydantic the JSON responses from the TIDAL API."""

from __future__ import annotations

from typing import Literal

from pydantic import (
    UUID4,
    BaseModel,
    Field,
    HttpUrl,
    PositiveInt,
    computed_field,
)


class Artist(BaseModel):
    """

    This class is also a sub-object of the JSON response from several other
    endpoints, including /albums, /videos, /tracks.
    """

    id: PositiveInt = Field(frozen=True)
    name: str = Field(frozen=True)
    artist_type: Literal["MAIN", "FEATURED"] = Field(
        alias="type", frozen=True, repr=False
    )
    picture: UUID4 = Field(frozen=True, repr=False)

    @computed_field(repr=False)
    def picture_url(self) -> HttpUrl:
        """Set as property the URL to self's highest-quality JPEG file."""
        _path: str = self.picture.replace("-", "/")
        return f"https://resources.tidal.com/images/{_path}/750x750.jpg"
