"""Emulate TIDAL API JSON responses with Pydantic."""

from __future__ import annotations

import json
import string
import sys
from base64 import b64decode
from datetime import date, datetime  # noqa:TC003
from pathlib import Path
from typing import Literal

from pydantic import (
    UUID4,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    NonNegativeInt,
    PositiveInt,
    ValidationError,
    field_validator,
)

HERE: Path = Path(__file__).parent


class SessionsResponseClient(BaseModel):
    """A session's client in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    id: PositiveInt = Field(frozen=True)
    name: str = Field(frozen=True)


class SessionsResponse(BaseModel):
    """A session in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    session_id: UUID4 = Field(frozen=True, alias="sessionId", strict=False)
    user_id: PositiveInt = Field(frozen=True, alias="userId")
    country_code: str = Field(
        frozen=True,
        alias="countryCode",
        min_length=2,
        max_length=2,
    )
    client: SessionsResponseClient = Field(frozen=True)

    @field_validator("country_code")
    def validate_two_character_uppercase(cls, v):  # noqa: ANN001,ANN201,D102,N805
        assert all(char in string.ascii_uppercase for char in v)  # noqa: S101
        return v


class ArtistsResponse(BaseModel):
    """An artist in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    id: PositiveInt = Field(frozen=True)
    name: str = Field(min_length=1, frozen=True)
    artist_types: list[Literal["ARTIST", "CONTRIBUTOR"]] = Field(
        alias="artistTypes",
        frozen=True,
    )
    url: HttpUrl = Field(frozen=True)
    picture: UUID4 | None = Field(frozen=True, strict=False)


class AlbumsResponseArtist(BaseModel):
    """An album's artist in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    id: PositiveInt = Field(frozen=True)
    name: str = Field(min_length=1, frozen=True)
    artist_type: str = Field(frozen=True, alias="type")  # TODO: Literal["MAIN"]
    picture: UUID4 | None = Field(frozen=True, strict=False)


class AlbumsResponse(BaseModel):
    """An album in the reckoning of TIDAL API."""

    id: PositiveInt = Field(frozen=True)
    title: str = Field(frozen=True, min_length=1)
    duration: PositiveInt = Field(frozen=True)
    number_of_tracks: PositiveInt = Field(frozen=True, alias="numberOfTracks", ge=1)
    number_of_videos: NonNegativeInt = Field(frozen=True, alias="numberOfVideos")
    number_of_volumes: PositiveInt = Field(frozen=True, alias="numberOfVolumes", ge=1)
    release_date: date = Field(frozen=True, alias="releaseDate")
    album_type: str = Field(
        frozen=True,
        alias="type",
    )  # TODO: Literal["SINGLE", "ALBUM", "EP"]
    version: str | None = Field(frozen=True)
    copyright: str | None = Field(frozen=True)
    url: HttpUrl = Field(frozen=True)
    cover: UUID4 | None = Field(frozen=True, strict=False)

    upc: PositiveInt = Field(frozen=True, strict=False)
    explicit: bool = Field(frozen=True)
    audio_quality: str = Field(
        frozen=True,
        alias="audioQuality",
    )  # TODO: Literal["LOSSLESS", ...]
    audio_modes: list[Literal["STEREO", "DOLBY_ATMOS"]] = Field(
        frozen=True,
        alias="audioModes",
    )
    media_metadata: AlbumsResponseMediaMetadata = Field(
        frozen=True,
        alias="mediaMetadata",
    )
    artist: AlbumsResponseArtist = Field(frozen=True)
    artists: list[AlbumsResponseArtist] = Field(frozen=True)


class AlbumsCreditsResponseContributor(BaseModel):
    """An album's contributor in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    name: str = Field(min_length=1, frozen=True)
    id: PositiveInt | None = Field(default=None, frozen=True)


class AlbumsCreditsResponseRole(BaseModel):
    """An album's credited role in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    contributor_type: str = Field(alias="type", frozen=True)
    contributors: list[AlbumsCreditsResponseContributor] = Field(frozen=True)


class AlbumsCreditsResponse(BaseModel):
    """An album's credits in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    credits: list[AlbumsCreditsResponseRole] = Field(frozen=True)


class TracksResponseAlbum(BaseModel):
    """An album's item's album in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    id: PositiveInt = Field(frozen=True)
    title: str = Field(frozen=True, min_length=1)
    cover: UUID4 | None = Field(frozen=True, strict=False)


class AlbumsResponseMediaMetadata(BaseModel):
    """The media metadata of an album's item (e.g. track) in TIDAL API's reckoning."""

    model_config = ConfigDict(strict=True)
    tags: list[Literal["LOSSLESS", "HIRES_LOSSLESS", "DOLBY_ATMOS"], ...] = Field(
        Frozen=True,
    )


class AlbumsItemsResponseItemsElement(BaseModel):
    """A constituent item of an album's items in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    item: TracksResponse = Field(frozen=True)  # TODO: also could be a video
    item_type: Literal["track"] = Field(frozen=True, alias="type")


class AlbumsItemsResponse(BaseModel):
    """An album's items in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    limit: NonNegativeInt = Field(frozen=True)
    offset: NonNegativeInt = Field(frozen=True)
    total_number_of_times: PositiveInt = Field(frozen=True, alias="totalNumberOfItems")
    items: list[AlbumsItemsResponseItemsElement] = Field(frozen=True)


class AlbumsReviewResponse(BaseModel):
    """The review of an album in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    source: str = Field(frozen=True)  # TODO: Literal["TiVo", ...]
    last_updated: datetime = Field(frozen=True, alias="lastUpdated", strict=False)
    text: str = Field(frozen=True)
    summary: str = Field(frozen=True)


class ArtistsAlbumsResponse(BaseModel):
    """The albums (and, potentially, EPs) of an artist per TIDAL API."""

    model_config = ConfigDict(strict=True)
    limit: PositiveInt = Field(frozen=True)
    offset: NonNegativeInt = Field(frozen=True)
    total_number_of_items: NonNegativeInt = Field(
        frozen=True,
        alias="totalNumberOfItems",
    )
    items: list[AlbumsResponse] = Field(frozen=True)


class ArtistsBioResponse(BaseModel):
    """The biography of an artist in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    source: str = Field(frozen=True)  # TODO: Literal["TiVo", ...]
    last_updated: datetime = Field(frozen=True, alias="lastUpdated", strict=False)
    text: str = Field(frozen=True)
    summary: str = Field(frozen=True)


class PlaylistsResponseCreator(BaseModel):
    """The creator of a playlist in the reckoning of TIDAL API."""

    id: PositiveInt = Field(frozen=True, strict=True)


class PlaylistsResponse(BaseModel):
    """A playlist in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    uuid: UUID4 = Field(frozen=True, strict=False)
    title: str = Field(frozen=True, min_length=1)
    number_of_tracks: NonNegativeInt = Field(frozen=True, alias="numberOfTracks")
    number_of_videos: NonNegativeInt = Field(frozen=True, alias="numberOfVideos")
    creator: PlaylistsResponseCreator = Field(frozen=True)
    description: str = Field(frozen=True)
    duration: NonNegativeInt = Field(frozen=True)
    last_updated: datetime = Field(frozen=True, alias="lastUpdated", strict=False)
    created: datetime = Field(frozen=True, strict=False)
    playlist_type: str = Field(frozen=True, alias="type")  # TODO: Literal["USER"]
    public_playlist: bool = Field(frozen=True, alias="publicPlaylist")
    url: HttpUrl = Field(frozen=True)
    image: UUID4 | None = Field(frozen=True, strict=False)
    square_image: UUID4 | None = Field(frozen=True, strict=False, alias="squareImage")
    last_item_added_at: datetime = Field(
        frozen=True,
        alias="lastItemAddedAt",
        strict=False,
    )


class TracksResponse(BaseModel):
    """An track in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    id: PositiveInt = Field(frozen=True)
    title: str = Field(frozen=True, min_length=1)
    duration: PositiveInt = Field(frozen=True)
    replay_gain: float = Field(frozen=True, alias="replayGain", le=0.0)
    peak: float = Field(frozen=True, ge=0.0)
    track_number: PositiveInt = Field(frozen=True, alias="trackNumber", ge=1)
    volume_number: PositiveInt = Field(frozen=True, alias="volumeNumber", ge=1)
    version: str | None = Field(frozen=True)
    copyright: str | None = Field(frozen=True)
    url: HttpUrl = Field(frozen=True)
    isrc: str = Field(frozen=True)
    explicit: bool = Field(frozen=True)
    # TODO: Literal["LOSSLESS", ...]
    audio_quality: str = Field(
        frozen=True,
        alias="audioQuality",
    )
    audio_modes: list[Literal["STEREO", "DOLBY_ATMOS"]] = Field(
        frozen=True,
        alias="audioModes",
    )
    media_metadata: AlbumsResponseMediaMetadata = Field(
        frozen=True,
        alias="mediaMetadata",
    )
    artist: AlbumsResponseArtist = Field(frozen=True)
    artists: list[AlbumsResponseArtist] = Field(frozen=True)
    album: TracksResponseAlbum = Field(frozen=True)

    @field_validator("isrc")
    def validate_alphanumeric(cls, v):  # noqa: ANN001,ANN201,D102,N805
        _allowed: set[str] = set(string.digits) | set(string.ascii_uppercase)
        assert all(char in _allowed for char in v)  # noqa: S101
        return v


class TracksCreditsResponseContributor(BaseModel):
    """A contributor to a track in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    name: str = Field(min_length=1, frozen=True)
    id: PositiveInt | None = Field(default=None, frozen=True)


class TracksCreditsResponseCredit(BaseModel):
    """A track credit in the reckoning of TIDAL API."""

    # TODO: Literal["Producer", "Music Publisher", ]
    credit_type: str = Field(frozen=True, alias="type")
    contributors: list[TracksCreditsResponseContributor] = Field(frozen=True)


class TracksCreditsResponse(BaseModel):
    """A track's credits in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    credits: list[TracksCreditsResponseCredit] = Field(frozen=True)


class TracksLyricsResponse(BaseModel):
    """The lyrics of a track in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    track_id: PositiveInt = Field(frozen=True, alias="trackId")
    lyrics_provider: Literal["MUSIXMATCH"] = Field(frozen=True, alias="lyricsProvider")
    provider_common_track_id: PositiveInt = Field(
        frozen=True,
        alias="providerCommontrackId",
        strict=False,
    )
    provider_lyrics_id: PositiveInt = Field(
        frozen=True,
        alias="providerLyricsId",
        strict=False,
    )
    lyrics: str = Field(frozen=True)
    subtitles: str = Field(frozen=True)
    is_right_to_left: bool = Field(frozen=True, alias="isRightToLeft")


class TracksPlaybackInfoPostPaywallResponse(BaseModel):
    """The stream information for a track in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    track_id: PositiveInt = Field(frozen=True, alias="trackId")
    # TODO: Literal["FULL", ]
    asset_presentation: str = Field(frozen=True, alias="assetPresentation")
    # TODO: Literal["STEREO", "DOLBY_ATMOS", ]
    audio_mode: str = Field(frozen=True, alias="audioMode")
    # TODO: Literal["LOSSLESS", ]
    audio_quality: str = Field(frozen=True, alias="audioQuality")
    # TODO: Literal["", ]
    manifest_mime_type: str = Field(frozen=True, alias="manifestMimeType")
    manifest: str = Field(frozen=True, strict=False)  # pydantic.Base64Str
    album_replay_gain: float = Field(frozen=True, alias="albumReplayGain", le=0.0)
    album_peak_amplitude: float = Field(frozen=True, ge=0.0, alias="albumPeakAmplitude")
    track_replay_gain: float = Field(frozen=True, alias="trackReplayGain", le=0.0)
    track_peak_amplitude: float = Field(frozen=True, ge=0.0, alias="trackPeakAmplitude")
    # TODO: Literal[16, ]
    bit_depth: PositiveInt = Field(frozen=True, alias="bitDepth")
    # TODO: Literal[44100, 48000, 96000, 192000, ]
    sample_rate: PositiveInt = Field(frozen=True, alias="sampleRate")

    @field_validator("manifest")
    def validate_base64(cls, v):  # noqa: ANN001,ANN201,D102,N805
        assert b64decode(v)  # noqa: S101
        return v


class VideosResponse(BaseModel):
    """A video in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    id: PositiveInt = Field(frozen=True)
    title: str = Field(frozen=True)
    volume_number: NonNegativeInt = Field(frozen=True, alias="volumeNumber", ge=1)
    track_number: NonNegativeInt = Field(frozen=True, alias="trackNumber", ge=1)
    release_date: date = Field(frozen=True, alias="releaseDate", strict=False)
    image_id: UUID4 = Field(frozen=True, alias="imageId", strict=False)
    duration: PositiveInt = Field(frozen=True)
    quality: str = Field(frozen=True)  # TODO: Literal["MP4_1080P"]
    explicit: bool = Field(frozen=True)
    video_type: Literal["Music Video"] = Field(frozen=True, alias="type")
    artist: AlbumsResponseArtist = Field(frozen=True)
    artists: list[AlbumsResponseArtist] = Field(frozen=True)
    album: TracksResponseAlbum | None = Field(frozen=True, default=None)


class VideoContributor(BaseModel):
    """A contributor to a video in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    name: str = Field(frozen=True)
    role: str = Field(frozen=True)
    # TODO: Literal["Producer", "Composer", "Lyricist", "Associated Performer", ...]


class VideosContributorsResponse(BaseModel):
    """The contributors to a video in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    limit: PositiveInt = Field(frozen=True)
    offset: NonNegativeInt = Field(frozen=True)
    total_number_of_items: NonNegativeInt = Field(
        frozen=True,
        alias="totalNumberOfItems",
    )
    items: list[VideoContributor] = Field(frozen=True)


class VideosPlaybackInfoPostPaywallResponse(BaseModel):
    """The stream information for a video in the reckoning of TIDAL API."""

    model_config = ConfigDict(strict=True)
    video_id: PositiveInt = Field(frozen=True, alias="videoId")
    # TODO: Literal["FULL", ]
    asset_presentation: str = Field(frozen=True, alias="assetPresentation")
    # TODO: Literal["HIGH", ]
    video_quality: str = Field(frozen=True, alias="videoQuality")
    # TODO: Literal["application/vnd.tidal.emu", ]
    manifest_mime_type: str = Field(frozen=True, alias="manifestMimeType")
    manifest: str = Field(frozen=True)  # pydantic.Base64Str

    @field_validator("manifest")
    def validate_base64(cls, v):  # noqa: ANN001,ANN201,D102,N805
        assert b64decode(v)  # noqa: S101
        return v


def main(argv: list[str, ...] | None = None) -> None:  # noqa:D103
    if argv is None:
        argv = sys.argv

    def read_json_from_disk(filename: str, p: Path = HERE) -> dict:
        """Return the JSON bytes from a file."""
        f: Path = p / filename
        return json.loads(f.read_bytes())

    class_tests: tuple[tuple[BaseModel, dict], ...] = (
        (AlbumsResponse, read_json_from_disk("albums.json")),
        (
            AlbumsCreditsResponse,
            {"credits": read_json_from_disk("albums_credits.json")},
        ),
        (AlbumsItemsResponse, read_json_from_disk("albums_items.json")),
        (AlbumsReviewResponse, read_json_from_disk("albums_review.json")),
        (ArtistsResponse, read_json_from_disk("artists.json")),
        (ArtistsBioResponse, read_json_from_disk("artists_bio.json")),
        (ArtistsAlbumsResponse, read_json_from_disk("artists_albums.json")),
        (
            ArtistsAlbumsResponse,
            read_json_from_disk("artists_albums_EPSANDSINGLES.json"),
        ),
        (PlaylistsResponse, read_json_from_disk("playlists.json")),
        (SessionsResponse, read_json_from_disk("sessions.json")),
        (TracksResponse, read_json_from_disk("tracks.json")),
        (
            TracksCreditsResponse,
            {"credits": read_json_from_disk("tracks_credits.json")},
        ),
        (TracksLyricsResponse, read_json_from_disk("tracks_lyrics.json")),
        (
            TracksPlaybackInfoPostPaywallResponse,
            read_json_from_disk("tracks_playbackinfopostpaywall.json"),
        ),
        (VideosResponse, read_json_from_disk("videos.json")),
        (VideosContributorsResponse, read_json_from_disk("videos_contributors.json")),
        (
            VideosPlaybackInfoPostPaywallResponse,
            read_json_from_disk("videos_playbackinfopostpaywall.json"),
        ),
    )

    for base_model, json_data in class_tests:
        try:
            base_model.model_validate(json_data)
        except ValidationError as ve:  # noqa: PERF203
            print(ve, file=sys.stderr)  # noqa: T201


if __name__ == "__main__":
    main()
