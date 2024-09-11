"""Represent JSON responses from TIDAL API as JSONWizard subclasses."""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from typing import TYPE_CHECKING, Literal

import dataclass_wizard
from requests.auth import AuthBase
from typing_extensions import Annotated

from .utils import replace_illegal_characters

if TYPE_CHECKING:
    from pathlib import Path

    from requests import Request, Session


logger = logging.getLogger(__name__)
IMAGE_URL: str = "https://resources.tidal.com/images/%s.jpg"
AudioModeType = Literal["DOLBY_ATMOS", "SONY_360RA", "STEREO"]
AudioQualityType = Literal[
    "HI_RES",
    "HI_RES_LOSSLESS",
    "LOSSLESS",
    "DOLBY_ATMOS",
    "HIGH",
    "LOW",
]
VideoQualityType = Literal["HIGH", "MEDIUM", "LOW", "AUDIO_ONLY"]


@dataclass
class TracksEndpointStreamResponseJSON(dataclass_wizard.JSONWizard):
    """Represent the response from the TIDAL API tracks/{TRACKID} endpoint.

    In particular, the response to a request specifying streaming. The params
    and headers, if correctly specified, return the manifest of the audio to
    be streamed. The manifest is a base64-encoded XML document or JSON object.
    """

    track_id: int
    audio_mode: AudioModeType
    audio_quality: AudioQualityType
    manifest: str = field(repr=False)
    manifest_mime_type: str = field(repr=False)
    album_replay_gain: float | None = field(repr=False, default=None)
    album_peak_amplitude: float | None = field(repr=False, default=None)
    track_replay_gain: float | None = field(repr=False, default=None)
    track_peak_amplitude: float | None = field(repr=False, default=None)
    bit_depth: int | None = field(default=None)
    sample_rate: int | None = field(default=None)

    def __post_init__(self):
        self.manifest_bytes: bytes = base64.b64decode(self.manifest)


class BearerAuth(AuthBase):
    """A class to be passed to `auth` in a `requests.Session` constructor."""

    def __init__(self, token: str):
        self.token = token

    def __call__(self, r: Request):
        r.headers["Authorization"] = f"Bearer {self.token}"
        return r


@dataclass(frozen=True)
class Client:
    id: int
    name: str
    authorized_for_offline: bool = field(repr=False)


@dataclass(frozen=True)
class SessionsEndpointResponseJSON(dataclass_wizard.JSONWizard):
    """Represent the response from the TIDAL API endpoint /sessions."""

    session_id: str  # UUID4 value, really
    user_id: int
    country_code: str  # 2-digit country code according to some ISO
    channel_id: int
    partner_id: int
    client: Client


@dataclass(frozen=True)
class Artist:
    """A musical artist in the reckoning of the TIDAL API."""

    id: int
    name: str
    type: str
    picture: str | None = field(repr=False, default=None)

    def picture_url(self, dimension: int = 320) -> str | None:
        """Create URL pointing to artist's JPEG data."""
        if self.picture is None:
            return None
        if len(self.picture) != 36 or self.picture.count("-") != 4:
            # Should be a UUID
            return None
        _picture = self.picture.replace("-", "/")
        return IMAGE_URL % f"{_picture}/{dimension}x{dimension}"


@dataclass
class MediaMetadata:
    """Represent the sub-object `mediaMetadata` of /tracks and /albums endpoint responses.

    It represents the quality levels available for the album's songs. These
    quality levels are determined by the client device type, the TIDAL account
    level, the country code (read: licensing), the device's quality settings,
    and, perhaps, the device's network connectivity conditions.
    """

    tags: list[str]  # LOSSLESS, HIRES_LOSSLESS


@dataclass(frozen=True)
class TrackAlbum:
    id: int
    title: str
    cover: str = field(repr=None)


@dataclass
class TracksEndpointResponseJSON(dataclass_wizard.JSONWizard):
    """Represent the response from the TIDAL API endpoint tracks/{TRACKID}.

    If the params and headers are correctly specified, the API returns metadata
    of the available version of the audio track, including audio quality,
    track title, ISRC, track artists, album, track number, duration, etc.
    """

    id: int = field(repr=False)
    title: str
    duration: int  # seconds
    replay_gain: float = field(repr=False)
    peak: float = field(repr=False)
    track_number: int
    volume_number: int
    version: str | None
    copyright: str = field(repr=False)
    url: str
    isrc: str = field(repr=False)
    explicit: bool
    audio_quality: str = field(repr=False)
    audio_modes: list[str] = field(repr=False)
    media_metadata: MediaMetadata
    artist: Artist
    artists: list[Artist]
    album: TrackAlbum

    def __post_init__(self):
        """Set attribute self.name based on values passed to __init__()."""
        name: str = replace_illegal_characters(self.title)
        if self.version is not None:
            version: str = replace_illegal_characters(self.version)
            self.name: str = f"{name} ({version})"
        else:
            self.name: str = name


@dataclass
class AlbumsEndpointResponseJSON(dataclass_wizard.JSONWizard):
    """Represent the response from the TIDAL API endpoint /albums/<ALBUMID>.

    If the params and headers are correctly specified, the response should
    contain metadata about the album; e.g. title, number of tracks, copyright,
    date of release, etc.
    """

    id: int = field(repr=False)
    title: str
    duration: int
    number_of_tracks: int
    number_of_volumes: int = field(repr=False)
    release_date: date
    copyright: str = field(repr=False)
    type: str
    version: str | None
    url: str
    cover: str = field(repr=False)
    explicit: bool
    upc: int | str
    audio_quality: str
    audio_modes: list[str]
    media_metadata: MediaMetadata = field(repr=False)
    artist: Artist = field(repr=False)
    artists: list[Artist]

    def __post_init__(self):
        """Set attributes 'name', 'cover_url' based on values passed to __init__()."""
        self.cover_url: str = IMAGE_URL % f"{self.cover.replace('-', '/')}/1280x1280"
        self.name = replace_illegal_characters(self.title)


@dataclass
class AlbumsCreditsResponseJSON(dataclass_wizard.JSONWizard):
    """Represent the response from the TIDAL API endpoint /albums/<ID>/credits."""

    credits: list[Credit]

    def get_credit(self, type_: str) -> Credit | None:
        """Given a contributor type (e.g. Producer, Engineer),
        go through the `credits` attribute, returning the `Credit` object
        for the given contributor type if it exists"""
        _credit = None
        try:
            _credit = next(c for c in self.credits if c.type == type_)
        except StopIteration:
            _msg: str = f"There are no credits of type {type_} for this album"
            logger.debug(_msg)
            return _credit
        else:
            return _credit

    def get_contributors(self, type_: str) -> list[str] | None:
        """Given a contributor type (e.g. Producer, Engineer),
        go through the `credits` attribute: for each Credit
        object in `self.credits`, if there is a Credit with
        `type` attribute matching `type_` argument, then return
        the `name` attribute for each Contributor object in
        `Credit.contributors`"""
        _credit: Credit | None = self.get_credit(type_)
        _to_return = None
        if _credit is not None:
            _to_return = [c.name for c in _credit.contributors]
        return _to_return

    def __post_init__(self):
        """Create self.credit, a JSON-format amenable dict."""
        _credit: dict[str, str | list[str]] = {
            c: self.get_contributors(c)
            for c in (
                "Cover Design",
                "Creative Director",
                "Design",
                "Engineer",
                "Group Member",
                "Layout",
                "Mastering",
                "Mixing",
                "Photography",
                "Primary Artist",
                "Producer",
                "Record Label",
            )
        }

        self.credit: dict[str, str | list[str]] = {
            k: v for k, v in _credit.items() if v is not None
        }


@dataclass(frozen=True)
class SubscriptionEndpointResponseJSONSubscription:
    """Represent the response from a TIDAL API endpoint.

    In particular, the 'subscription' object that is returned from the
    endpoint /subscription.
    """

    type: str
    offline_grace_period: int


@dataclass(frozen=True)
class SubscriptionEndpointResponseJSON(dataclass_wizard.JSONWizard):
    """Represent the response from a TIDAL API endpoint.

    In particular, the endpoint /subscription.
    """

    start_date: datetime
    valid_until: datetime
    status: str
    subscription: SubscriptionEndpointResponseJSONSubscription
    highest_sound_quality: str
    premium_access: bool
    can_get_trial: bool
    payment_type: str
    payment_overdue: bool


@dataclass(frozen=True)
class AlbumsItemsResponseJSONItem:
    """A sub-object of the response from the TIDAL API endpoint
    /albums/<ID>/items. It simply denotes the type of item, which is surely
    going to be 'track', and is the same object that is returned from the TIDAL
    API /tracks endpoint."""

    item: TracksEndpointResponseJSON
    type: str  # "track"


@dataclass(frozen=True)
class AlbumsItemsResponseJSON(dataclass_wizard.JSONWizard):
    """This class represents the JSON response from the TIDAL API endpoint
    /albums/<ID>/items. It is a list of TracksEndpointResponseJSON objects,
    with a bit of metadata based on the query parameters (offset and limit;
    i.e. pagination logic)."""

    limit: int = field(repr=None)
    offset: int = field(repr=None)
    total_number_of_items: int
    items: list[AlbumsItemsResponseJSONItem]


@dataclass(frozen=True)
class AlbumsReviewResponseJSON(dataclass_wizard.JSONWizard):
    """Represent the response from the TIDAL API endpoint /albums/<ID>/review."""

    source: str
    last_updated: Annotated[
        datetime,
        dataclass_wizard.Pattern("%Y-%m-%dT%H:%M:%S.%f%z"),
    ]
    text: str = field(repr=None)
    summary: str = field(repr=None)


@dataclass(frozen=True)
class Contributor:
    """The response from the TIDAL API endpoint /tracks/<ID>/credits is
    an array of objects, one of the attributes of which is modeled by
    this class. It is simply the name of a contributor to a track,
    and possibly the numerical TIDAL resource ID of that contributor."""

    name: str
    id: int | None = field(repr=False, default=None)


@dataclass(frozen=True)
class Credit:
    """The response from the TIDAL API endpoint /tracks/<ID>/credits is
    an array of objects modeled by this class. It has an attribute,
    `type`, which is one of the roles a person or entity has in the
    creation of a song/album: Composer, Lyricist, Producer, Mixer,
    Engineer, etc. The `contributors` attribute is an array of Name
    and, optionally, TIDAL resource ID for the role"""

    type: str
    contributors: list[Contributor] = field(repr=False)


@dataclass
class TracksCreditsResponseJSON(dataclass_wizard.JSONWizard):
    """Represent the response from the TIDAL API endpoint /tracks/<ID>/credits."""

    credits: list[Credit]

    def get_credit(self, type_: str) -> Credit | None:
        """Get the credit for the specified type of contributor.

        Given a contributor type (e.g. Lyricist, Composer),
        go through self.credits, returning the `Credit` object
        for the given contributor type if it exists
        """
        _credit = None
        try:
            _credit = next(c for c in self.credits if c.type == type_)
        except StopIteration:
            _msg: str = f"There are no credits of type {type_} for this track"
            logger.debug(_msg)
            return _credit
        else:
            return _credit

    def get_contributors(self, type_: str) -> tuple[str] | None:
        """Given a contributor type (e.g. Lyricist, Composer),
        go through the `credits` attribute: for each Credit
        object in `self.credits`, if there is a Credit with
        `type` attribute matching `type_` argument, then return
        the `name` attribute for each Contributor object in
        `Credit.contributors`"""
        _credit: Credit | None = self.get_credit(type_)
        _to_return: None = None
        if _credit is not None:
            _to_return = tuple(c.name for c in _credit.contributors)
        return _to_return

    def __post_init__(self):
        """Set instance attributes based on self.credits.

        In particular: composer, engineer, lyricist, mixer, producer, remixer, piano.
        """
        self.composer: tuple[str] | None = self.get_contributors("Composer")
        self.engineer: tuple[str] | None = (
            self.get_contributors("Engineer")
            or self.get_contributors("Mastering Engineer")
            or self.get_contributors("Immersive Mastering Engineer")
        )
        self.lyricist: tuple[str] | None = self.get_contributors("Lyricist")
        self.mixer: tuple[str] | None = (
            self.get_contributors("Mixer")
            or self.get_contributors("Mix Engineer")
            or self.get_contributors("Mixing Engineer")
            or self.get_contributors("Atmos Mixing Engineer")
        )
        self.producer: tuple[str] | None = self.get_contributors("Producer")
        self.remixer: tuple[str] | None = self.get_contributors("Remixer")
        self.piano: tuple[str] | None = self.get_contributors("Piano")


@dataclass(frozen=True)
class TracksLyricsResponseJSON(dataclass_wizard.JSONWizard):
    """Represent the response from the TIDAL API endpoint /tracks/<ID>/lyrics."""

    track_id: int
    lyrics_provider: str
    provider_commontrack_id: str
    provider_lyrics_id: str
    lyrics: str
    subtitles: str
    is_right_to_left: bool


@dataclass
class ArtistsEndpointResponseJSON(dataclass_wizard.JSONWizard):
    """Represent the response from the TIDAL API endpoint /artists."""

    id: int
    name: str
    artist_types: list[str]
    url: str
    picture: str | None = field(repr=False, default=None)

    def picture_url(self, dimension: int = 750) -> str | None:
        """Create URL pointing to artist's JPEG data."""
        _to_return: str | None = None
        if self.picture is None:
            return _to_return
        if len(self.picture) != 36 or self.picture.count("-") != 4:
            # Should be a UUID
            return _to_return
        _picture = self.picture.replace("-", "/")
        _to_return: str = IMAGE_URL % f"{_picture}/{dimension}x{dimension}"
        return _to_return


@dataclass(frozen=True)
class ArtistsAlbumsResponseJSON(dataclass_wizard.JSONWizard):
    """Represent the response from the TIDAL API endpoint /artists/<ID>/albums."""

    limit: int
    offset: int
    total_number_of_items: int
    items: list[AlbumsEndpointResponseJSON]


@dataclass(frozen=True)
class ArtistsVideosResponseJSON(dataclass_wizard.JSONWizard):
    """Represent the response from the TIDAL API endpoint /artists/<ID>/videos."""

    limit: int
    offset: int
    total_number_of_items: int
    items: list[VideosEndpointResponseJSON]


@dataclass(frozen=True)
class ArtistsBioResponseJSON(dataclass_wizard.JSONWizard):
    """Represent the response from the TIDAL API endpoint /artists/<ID>/bio."""

    source: str
    last_updated: Annotated[
        datetime, dataclass_wizard.Pattern("%Y-%m-%dT%H:%M:%S.%f%z")
    ]
    text: str = field(repr=None)
    summary: str = field(repr=None)


@dataclass
class VideosEndpointStreamResponseJSON(dataclass_wizard.JSONWizard):
    """Represent the response from the TIDAL API videos/<VIDEO_ID> endpoint.

    In particular, when the stream response was requested. The params and
    headers, if correctly specified, return the manifest of the video to be
    streamed. The manifest is a base64-encoded JSON object containing a .m3u8 URL
    """

    video_id: int
    stream_type: str  # ON_DEMAND
    video_quality: VideoQualityType
    manifest: str = field(repr=False)
    manifest_mime_type: str = field(repr=False)

    def __post_init__(self):
        """Set the attribute self.manifest_bytes based on self.manifest."""
        self.manifest_bytes: bytes = base64.b64decode(self.manifest)


@dataclass
class VideosEndpointResponseJSON(dataclass_wizard.JSONWizard):
    """Response from the TIDAL API, videos/<VIDEOID> endpoint.If the params and
    headers are correctly specified, the API returns metadata of the available
    version of the (music) video, including video quality, video title, date,
    video artists, duration, etc."""

    id: int = field(repr=False)
    title: str
    volume_number: int
    track_number: int
    release_date: Annotated[
        datetime, dataclass_wizard.Pattern("%Y-%m-%dT%H:%M:%S.%f%z")
    ]
    duration: int  # seconds
    quality: str
    explicit: bool
    type: str
    artist: Artist
    artists: list[Artist]

    def __post_init__(self):
        """Set the attribute self.name based on self.title."""
        self.name = replace_illegal_characters(self.title)


@dataclass(frozen=True)
class VideoContributor:
    """The response from the TIDAL API endpoint /videos/<ID>/credits has
    an array of objects, each of which is modeled by this class.
    It is simply the name of a contributor to a video, and the role of that
    contributor."""

    name: str
    role: str


@dataclass
class VideosContributorsResponseJSON(dataclass_wizard.JSONWizard):
    """The response from the TIDAL API endpoint /videos/<ID>/contributors
    is modeled by this class."""

    limit: int
    offset: int
    total_number_of_items: int
    items: list[VideoContributor]

    def get_role(self, role: str) -> tuple[VideoContributor] | None:
        """Given a contributor role (e.g. Composer, Film Director), go through
        `self.items` object, returning the `VideoContributor` object(s)
        for the given contributor type if there are any"""
        role_contributors = tuple(vc for vc in self.items if vc.role == role)
        try:
            role_contributors[0]
        except IndexError:
            _msg: str = f"There are no credits of type '{role}' for this video"
            logger.debug(_msg)
            return None
        else:
            return role_contributors

    def get_contributors(self, role: str) -> tuple[str] | None:
        """Return a tuple of all contributor names of type 'role'."""
        vcs: tuple[VideoContributor] | None = self.get_role(role)
        _to_return: tuple[str] | None = None
        if vcs is not None:
            _to_return = tuple(vc.name for vc in vcs)
        return _to_return

    def __post_init__(self):
        """Set several instance attributes based on self.get_contributors()."""
        self.associated_performer: tuple[str] | None = self.get_contributors(
            "Associated Performer",
        )
        self.composer: tuple[str] | None = self.get_contributors("Composer")
        self.director: tuple[str] | None = self.get_contributors("Director")
        self.engineer: tuple[str] | None = self.get_contributors("Engineer")
        self.film_director: tuple[str] | None = self.get_contributors(
            "Film Director",
        )
        self.film_producer: tuple[str] | None = self.get_contributors(
            "Film Producer",
        )
        self.location: tuple[str] | None = self.get_contributors("Studio")
        self.lyricist: tuple[str] | None = self.get_contributors("Lyricist")
        self.mastering_engineer: tuple[str] | None = self.get_contributors(
            "Mastering Engineer",
        )
        self.mixing_engineer: tuple[str] | None = self.get_contributors(
            "Mixing Engineer",
        )
        self.music_publisher: tuple[str] | None = self.get_contributors(
            "Music Publisher",
        )
        self.producer: tuple[str] | None = self.get_contributors("Producer")
        self.video_director: tuple[str] | None = self.get_contributors(
            "Video Director",
        )
        self.video_producer: tuple[str] | None = self.get_contributors(
            "Video Producer",
        )
        self.vocal_engineer: tuple[str] | None = self.get_contributors(
            "Vocal Engineer",
        )


@dataclass
class PlaylistsEndpointResponseJSON(dataclass_wizard.JSONWizard):
    """Response from the TIDAL API, videos/<VIDEOID> endpoint.If the params and
    headers are correctly specified, the API returns metadata of the available
    version of the (music) video, including video quality, video title, date,
    video artists, duration, etc."""

    uuid: str = field(repr=False)
    title: str
    number_of_tracks: int
    number_of_videos: int
    description: str
    created: Annotated[datetime, dataclass_wizard.Pattern("%Y-%m-%dT%H:%M:%S.%f%z")]
    type: str
    public_playlist: bool
    url: str
    square_image: str  # UUID v4


class TidalResource:
    """Parent class to subclasses representing different TIDAL music
    service objects; e.g. Track, Album. This class is not meant to be
    instantiated itself: rather, its purpose is to pre-populate its
    subclasses with the `match_url` method."""

    def __init__(self, pattern: str | None = None, url: str | None = None):
        self.pattern = pattern
        self.url = url

    def match_url(self) -> int | str | None:
        _match: re.Match = re.match(self.pattern, self.url, re.IGNORECASE)
        try:
            _id: str = _match.groups()[0]
        except AttributeError:
            return None
        else:
            return _id


@dataclass
class TidalAlbum(TidalResource):
    """Class representing a TIDAL album. Its main purpose is the
    __post_init__ checking process"""

    url: str

    def __post_init__(self):
        self.pattern: str = (
            r"http(?:s)?://(?:listen\.|www\.)?tidal\.com/"
            r"(?:browse/)?album/(\d{2,9})(?:.*?)?"
        )
        _id = self.match_url()

        if _id is None:
            _msg: str = f"'{self.url}' is not a valid TIDAL album URL"
            raise ValueError(_msg)
        self.tidal_id = int(_id)
        _msg: str = f"TIDAL album ID parsed from input: {self.tidal_id}"
        logger.info(_msg)


@dataclass
class TidalArtist(TidalResource):
    """Represent the concept of a TIDAL artist.

    Its main purpose is the __post_init__ checking process.
    """

    url: str

    def __post_init__(self):
        self.pattern: str = (
            r"http(?:s)?://(?:listen\.|www\.)?tidal\.com/"
            r"(?:browse/)?artist/(\d{2,9})(?:.*?)?"
        )
        _id = self.match_url()

        if _id is None:
            _msg: str = f"'{self.url}' is not a valid TIDAL album URL"
            raise ValueError(_msg)
        self.tidal_id = int(_id)
        _msg: str = f"TIDAL album ID parsed from input: {self.tidal_id}"
        logger.info(_msg)


@dataclass
class TidalMix(TidalResource):
    """Represent the concept of a TIDAL mix.

    Its main purpose is the __post_init__ checking process.
    """

    url: str

    def __post_init__(self):
        self.pattern: str = (
            r"http(?:s)?://(?:listen\.|www\.)?tidal\.com/"
            r"(?:browse/)?mix/(\w{30})(?:.*?)?"
        )
        _id = self.match_url()

        if _id is None:
            _msg: str = f"'{self.url}' is not a valid TIDAL mix URL"
            raise ValueError(_msg)
        self.tidal_id = _id
        _msg: str = f"TIDAL mix ID parsed from input: {self.tidal_id}"
        logger.info(_msg)


@dataclass
class TidalTrack(TidalResource):
    """Represent the concept of a TIDAL track.

    Its main purpose is the __post_init__ checking process.
    """

    url: str

    def __post_init__(self):
        self.pattern: str = (
            r"http(?:s)?://(?:listen\.|www\.)?tidal\.com/"
            r"(?:browse/)?(?:album/\d{5,9}/)?track/(\d{5,9})(?:.*?)?"
        )
        _id = self.match_url()

        if _id is None:
            _msg: str = f"'{self.url}' is not a valid TIDAL track URL"
            raise ValueError(_msg)
        self.tidal_id = int(_id)
        _msg: str = f"TIDAL track ID parsed from input: {self.tidal_id}"
        logger.info(_msg)


@dataclass
class TidalPlaylist(TidalResource):
    """Represent the concept of a TIDAL playlist.

    Its main purpose is the __post_init__ checking process.
    """

    url: str

    def __post_init__(self):
        self.pattern: str = (
            r"http(?:s)?://(?:listen\.|www\.)?tidal\.com/(?:browse/)?playlist/"
            r"([0-9a-f]{8}\-[0-9a-f]{4}\-4[0-9a-f]{3}\-[89ab][0-9a-f]{3}\-[0-9a-f]{12})(?:.*?)?"
        )

        _id = self.match_url()

        if _id is None:
            _msg: str = f"'{self.url}' is not a valid TIDAL playlist URL"
            raise ValueError(_msg)
        self.tidal_id = _id
        _msg: str = f"TIDAL playlist ID parsed from input: {self.tidal_id}"
        logger.info(_msg)


@dataclass
class TidalVideo(TidalResource):
    """Represent the concept of a TIDAL video.

    Its main purpose is the __post_init__ checking process.
    """

    url: str

    def __post_init__(self):
        self.pattern: str = (
            r"http(?:s)?://(?:listen\.|www\.)?tidal\.com/"
            r"(?:browse/)?video/(\d{7,9})(?:.*?)?"
        )
        _id = self.match_url()

        if _id is None:
            _msg: str = f"'{self.url}' is not a valid TIDAL video URL"
            raise ValueError(_msg)

        self.tidal_id = int(_id)
        _msg: str = f"TIDAL video ID parsed from input: {self.tidal_id}"
        logger.info(_msg)


def match_tidal_url(input_str: str) -> TidalResource | None:
    """Attempt to match the `input_str` to either the URL of a track or an
    album in the Tidal API service. Returns None if `input_str` matches
    neither, otherwise a subclass of TidalResource corresponding to the
    parsed input_str type
    """
    resource_match: TidalResource | None = None
    tidal_resources: tuple[
        TidalResource,
        TidalResource,
        TidalResource,
        TidalResource,
        TidalResource,
        TidalResource,
    ] = (
        TidalTrack,
        TidalAlbum,
        TidalVideo,
        TidalPlaylist,
        TidalMix,
        TidalArtist,
    )
    for T in tidal_resources:
        try:
            resource_match = T(input_str)
        except ValueError as v:
            logger.debug(v)
            continue

        return resource_match


def download_artist_image(
    session: Session,
    artist: Artist,
    output_dir: Path,
    dimension: int = 320,
) -> Path | None:
    """Given a UUID that corresponds to a (JPEG) image on Tidal's servers,
    download the image file and write it as '{artist name}.jpeg'
    in the directory `output_dir`. Returns path to downloaded file"""
    _url: str = artist.picture_url(dimension)
    if _url is None:
        _msg: str = (
            f"Cannot download image for artist '{artist.name}', "
            "as Tidal supplied no URL for this artist's image."
        )
        logger.info(_msg)
        return None

    with session.get(url=_url, headers={"Accept": "image/jpeg"}) as r:
        if not r.ok:
            _msg: str = (
                "Could not retrieve data from Tidal resources/images URL "
                f"for artist '{artist.name}' due to error code: {r.status_code}"
            )
            logger.warning(_msg)
            logger.debug(r.reason)
            return None
        bytes_to_write: BytesIO = BytesIO(r.content)

    file_name: str = f"{artist.name.replace('..', '')}.jpg"
    output_file: Path | None = None
    if bytes_to_write is not None:
        output_file: Path = output_dir / file_name
        bytes_to_write.seek(0)
        output_file.write_bytes(bytes_to_write.read())
        bytes_to_write.close()
        _msg: str = (
            f"Wrote artist image JPEG for {artist} to "
            f"'{output_file.absolute()}'"
        )
        logger.info(_msg)
    return output_file
