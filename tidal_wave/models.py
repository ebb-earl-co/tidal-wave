import base64
from dataclasses import dataclass, field
from datetime import date, datetime
import logging
import re
from typing import List, Literal, Optional, Tuple, Union
from typing_extensions import Annotated

import dataclass_wizard
from requests.auth import AuthBase

logger = logging.getLogger(__name__)
IMAGE_URL: str = "https://resources.tidal.com/images/%s.jpg"
AudioModeType = Literal["DOLBY_ATMOS", "SONY_360RA", "STEREO"]
AudioQualityType = Literal[
    "HI_RES", "HI_RES_LOSSLESS", "LOSSLESS", "DOLBY_ATMOS", "HIGH", "LOW"
]
VideoQualityType = Literal["HIGH", "MEDIUM", "LOW", "AUDIO_ONLY"]


@dataclass
class TracksEndpointStreamResponseJSON(dataclass_wizard.JSONWizard):
    """Response from the TIDAL API's tracks/{TRACKID} stream
    endpoint. The params and headers, if correctly specified, return the
    manifest of the audio to be streamed. The manifest is a base64-encoded
    XML document or JSON object"""

    track_id: int
    audio_mode: AudioModeType
    audio_quality: AudioQualityType
    manifest: str = field(repr=False)
    manifest_mime_type: str = field(repr=False)
    album_replay_gain: Optional[float] = field(repr=False, default=None)
    album_peak_amplitude: Optional[float] = field(repr=False, default=None)
    track_replay_gain: Optional[float] = field(repr=False, default=None)
    track_peak_amplitude: Optional[float] = field(repr=False, default=None)
    bit_depth: Optional[int] = field(default=None)
    sample_rate: Optional[int] = field(default=None)

    def __post_init__(self):
        self.manifest_bytes: bytes = base64.b64decode(self.manifest)


class BearerAuth(AuthBase):
    """A class to be passed to the `auth` argument in a `requests.Session`
    constructor"""

    def __init__(self, token: str):
        self.token = token

    def __call__(self, r):
        r.headers["Authorization"] = f"Bearer {self.token}"
        return r


@dataclass(frozen=True)
class Client:
    id: int
    name: str
    authorized_for_offline: bool = field(repr=False)


@dataclass(frozen=True)
class SessionsEndpointResponseJSON(dataclass_wizard.JSONWizard):
    session_id: str  # UUID4 value, really
    user_id: int
    country_code: str  # 2-digit country code according to some ISO
    channel_id: int
    partner_id: int
    client: "Client"


@dataclass(frozen=True)
class Artist:
    """A musical artist in the reckoning of the TIDAL API"""

    id: int
    name: str
    type: str
    picture: Optional[str] = field(repr=False, default=None)

    def picture_url(self, dimension: int = 320) -> Optional[str]:
        if self.picture is None:
            return
        elif len(self.picture) != 36 or self.picture.count("-") != 4:
            # Should be a UUID
            return
        else:
            _picture = self.picture.replace("-", "/")
            return IMAGE_URL % f"{_picture}/{dimension}x{dimension}"


@dataclass
class MediaMetadata:
    """The sub-object `mediaMetadata` of /tracks and /albums endpoint responses.
    It represents the quality levels available for the album's songs. These
    quality levels are determined by the client device type, the TIDAL account
    level, the country code (read: licensing), the device's quality settings,
    and, perhaps, the device's network connectivity conditions."""

    tags: List[str]


@dataclass(frozen=True)
class TrackAlbum:
    id: int
    title: str
    cover: str = field(repr=None)


@dataclass
class TracksEndpointResponseJSON(dataclass_wizard.JSONWizard):
    """Response from the TIDAL API, tracks/{TRACKID} endpoint.If the params and
    headers are correctly specified, the API returns metadata of the available
    version of the audio track, including audio quality, track title, ISRC,
    track artists, album, track number, duration, etc."""

    id: int = field(repr=False)
    title: str
    duration: int  # seconds
    replay_gain: float = field(repr=False)
    peak: float = field(repr=False)
    track_number: int
    volume_number: int
    version: Optional[str]
    copyright: str = field(repr=False)
    url: str
    isrc: str = field(repr=False)
    explicit: bool
    audio_quality: str = field(repr=False)
    audio_modes: List[str] = field(repr=False)
    media_metadata: "MediaMetadata"
    artist: "Artist"
    artists: List["Artist"]
    album: "TrackAlbum"

    def __post_init__(self):
        self.name: str = (
            self.title.replace("/", "_").replace("|", "_").replace(":", " -")
            if self.version is None
            else f"{self.title.replace('/', '_').replace('|', '_').replace(':', ' -')} ({self.version})"
        )


@dataclass
class AlbumsEndpointResponseJSON(dataclass_wizard.JSONWizard):
    """This dataclass is the `dataclass-wizard`-generated class that represents
    the JSON response from https://api.tidal.com/v1/albums/<ALBUMID>"""

    id: int = field(repr=False)
    title: str
    duration: int
    number_of_tracks: int
    number_of_volumes: int = field(repr=False)
    release_date: date
    copyright: str = field(repr=False)
    type: str
    version: Optional[str]
    url: str
    cover: str = field(repr=False)
    explicit: bool
    upc: Union[int, str]
    audio_quality: str
    audio_modes: List[str]
    media_metadata: "MediaMetadata" = field(repr=False)
    artist: "Artist" = field(repr=False)
    artists: List["Artist"]

    def __post_init__(self):
        self.cover_url: str = IMAGE_URL % f"{self.cover.replace('-', '/')}/1280x1280"
        self.name: str = (
            self.title.replace("/", "_").replace("|", "_").replace(":", " -")
        )


@dataclass(frozen=True)
class SubscriptionEndpointResponseJSONSubscription:
    type: str
    offline_grace_period: int


@dataclass(frozen=True)
class SubscriptionEndpointResponseJSON(dataclass_wizard.JSONWizard):
    start_date: datetime
    valid_until: datetime
    status: str
    subscription: "SubscriptionEndpointResponseJSONSubscription"
    highest_sound_quality: str
    premium_access: bool
    can_get_trial: bool
    payment_type: str
    payment_overdue: bool


@dataclass(frozen=True)
class AlbumsItemsResponseJSONItem:
    """A sub-object of the response from the TIDAL API endpoint
    /albums/<ID>/items. It simply denotes the type of item, which is surely
    going to be 'track', and the same object that is returned from the TIDAL
    API /tracks endpoint."""

    item: "TracksEndpointResponseJSON"
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
    items: List["AlbumsItemsResponseJSONItem"]


@dataclass(frozen=True)
class AlbumsReviewResponseJSON(dataclass_wizard.JSONWizard):
    """This class represents the JSON response from the TIDAL API endpoint
    /albums/<ID>/review."""

    source: str
    last_updated: Annotated[
        datetime, dataclass_wizard.Pattern("%Y-%m-%dT%H:%M:%S.%f%z")
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
    id: Optional[int] = field(repr=False, default=None)


@dataclass(frozen=True)
class Credit:
    """The response from the TIDAL API endpoint /tracks/<ID>/credits is
    an array of objects modeled by this class. It has an attribute,
    `type`, which is one of the roles a person or entity has in the
    creation of a song/album: Composer, Lyricist, Producer, Mixer,
    Engineer, etc. The `contributors` attribute is an array of Name
    and, optionally, TIDAL resource ID for the role"""

    type: str
    contributors: List["Contributor"] = field(repr=False)


@dataclass
class TracksCreditsResponseJSON(dataclass_wizard.JSONWizard):
    """The response from the TIDAL API endpoint /tracks/<ID>/credits
    is modeled by this class."""

    credits: List["Credit"]

    def get_credit(self, type_: str) -> Optional["Credit"]:
        """Given a contributor type (e.g. Lyricist, Composer),
        go through the `credits` attribute, returning the `Credit` object
        for the given contributor type if it exists"""
        _credit = None
        try:
            _credit = next(c for c in self.credits if c.type == type_)
        except StopIteration:
            logger.debug(f"There are no credits of type {type_} for this track")
        finally:
            return _credit

    def get_contributors(self, type_: str) -> Optional[Tuple[str]]:
        """Given a contributor type (e.g. Lyricist, Composer),
        go through the `credits` attribute: for each Credit
        object in `self.credits`, if there is a Credit with
        `type` attribute matching `type_` argument, then return
        the `name` attribute for each Contributor object in
        `Credit.contributors`"""
        _credit: Optional["Credit"] = self.get_credit(type_)
        if _credit is not None:
            return tuple(c.name for c in _credit.contributors)
        else:
            return

    def __post_init__(self):
        """Try to parse the various Contributors to top-level
        attributes of this class"""
        self.composer: Optional[Tuple[str]] = self.get_contributors("Composer")
        self.engineer: Optional[Tuple[str]] = self.get_contributors("Engineer")
        self.lyricist: Optional[Tuple[str]] = self.get_contributors("Lyricist")
        self.mixer: Optional[Tuple[str]] = self.get_contributors("Mixer")
        self.producer: Optional[Tuple[str]] = self.get_contributors("Producer")
        self.remixer: Optional[Tuple[str]] = self.get_contributors("Remixer")


@dataclass(frozen=True)
class TracksLyricsResponseJSON(dataclass_wizard.JSONWizard):
    """The response from the TIDAL API endpoint /tracks/<ID>/lyrics
    is modeled by this class."""

    track_id: int
    lyrics_provider: str
    provider_commontrack_id: str
    provider_lyrics_id: str
    lyrics: str
    subtitles: str
    is_right_to_left: bool


@dataclass(frozen=True)
class ArtistsBioResponseJSON(dataclass_wizard.JSONWizard):
    """The response from the TIDAL API endpoint /artists/<ID>/bio
    is modeled by this class."""

    source: str
    last_updated: Annotated[
        datetime, dataclass_wizard.Pattern("%Y-%m-%dT%H:%M:%S.%f%z")
    ]
    text: str = field(repr=None)
    summary: str = field(repr=None)


@dataclass
class VideosEndpointStreamResponseJSON(dataclass_wizard.JSONWizard):
    """Response from the TIDAL API's videos/<VIDEO_ID> stream
    endpoint. The params and headers, if correctly specified, return the
    manifest of the video to be streamed. The manifest is a base64-encoded
    JSON object containing a .m3u8 URL"""

    video_id: int
    stream_type: str  # ON_DEMAND
    video_quality: VideoQualityType
    manifest: str = field(repr=False)
    manifest_mime_type: str = field(repr=False)

    def __post_init__(self):
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
    artist: "Artist"
    artists: List["Artist"]

    def __post_init__(self):
        self.name: str = (
            self.title.replace("/", "_").replace("|", "_").replace(":", " -")
        )


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
    items: List["VideoContributor"]

    def get_role(self, role: str) -> Optional[Tuple["VideoContributor"]]:
        """Given a contributor role (e.g. Composer, Film Director), go through
        `self.items` object, returning the `VideoContributor` object(s)
        for the given contributor type if there are any"""
        role_contributors = tuple(vc for vc in self.items if vc.role == role)
        try:
            role_contributors[0]
        except IndexError:
            logger.debug(f"There are no credits of type '{role}' for this video")
            return
        else:
            return role_contributors

    def get_contributors(self, role: str) -> Optional[Tuple[str]]:
        """Given a contributor role (e.g. Lyricist, Composer),
        return a tuple of all the names of the contributors
        """
        vcs: Optional[Tuple["VideoContributor"]] = self.get_role(role)
        if vcs is not None:
            return tuple(vc.name for vc in vcs)
        else:
            return

    def __post_init__(self):
        """Try to parse the various Contributors to top-level
        attributes of this class"""
        self.composer: Optional[Tuple[str]] = self.get_contributors("Composer")
        self.director: Optional[Tuple[str]] = self.get_contributors("Director")
        self.film_director: Optional[Tuple[str]] = self.get_contributors(
            "Film Director"
        )
        self.film_producer: Optional[Tuple[str]] = self.get_contributors(
            "Film Producer"
        )
        self.lyricist: Optional[Tuple[str]] = self.get_contributors("Lyricist")
        self.mastering_engineer: Optional[Tuple[str]] = self.get_contributors(
            "Mastering Engineer"
        )
        self.producer: Optional[Tuple[str]] = self.get_contributors("Producer")
        self.video_producer: Optional[Tuple[str]] = self.get_contributors(
            "Video Producer"
        )


@dataclass(frozen=True)
class PlaylistCreator:
    id: int
    name: Optional[str] = field(default=None)
    type: Optional[str] = field(default=None)


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
    # creator: "PlaylistCreator"
    description: str
    # duration: int
    last_updated: Annotated[
        datetime, dataclass_wizard.Pattern("%Y-%m-%dT%H:%M:%S.%f%z")
    ]
    created: Annotated[datetime, dataclass_wizard.Pattern("%Y-%m-%dT%H:%M:%S.%f%z")]
    type: str
    public_playlist: bool
    url: str
    image: str  # UUID v4
    popularity: int
    square_image: str  # UUID v4
    # promoted_artists: List["Artist"]
    last_item_added_at: Annotated[
        datetime, dataclass_wizard.Pattern("%Y-%m-%dT%H:%M:%S.%f%z")
    ]


class TidalResource:
    """Parent class to subclasses representing different TIDAL music
    service objects; e.g. Track, Album. This class is not meant to be
    instantiated itself: rather, its purpose is to pre-populate its
    subclasses with the `match_url` method."""

    def __init__(self, pattern: Optional[str] = None, url: Optional[str] = None):
        self.pattern = pattern
        self.url = url

    def match_url(self) -> Optional[int]:
        _match: re.Match = re.match(self.pattern, self.url, re.IGNORECASE)
        try:
            _id: str = _match.groups()[0]
        except AttributeError:
            return
        else:
            return _id


@dataclass
class TidalAlbum(TidalResource):
    """Class representing a TIDAL album. Its main purpose is the
    __post_init__ checking process"""

    url: str

    def __post_init__(self):
        self.pattern: str = (
            r"http(?:s)?://(?:listen\.)?tidal\.com/(?:browse/)?album/(\d{7,9})(?:.*?)?"
        )
        _id = self.match_url()

        if _id is None:
            raise ValueError(f"'{self.url}' is not a valid TIDAL album URL")
        else:
            self.tidal_id = int(_id)
            logger.info(f"TIDAL album ID parsed from input: {self.tidal_id}")


@dataclass
class TidalTrack(TidalResource):
    """Class representing a TIDAL track. Its main purpose is the
    __post_init__ checking process"""

    url: str

    def __post_init__(self):
        self.pattern: str = r"http(?:s)?://(?:listen\.)?tidal\.com/(?:browse/)?(?:album/\d{7,9}/)?track/(\d{7,9})(?:.*?)?"
        _id = self.match_url()

        if _id is None:
            raise ValueError(f"'{self.url}' is not a valid TIDAL track URL")
        else:
            self.tidal_id = int(_id)
            logger.info(f"TIDAL track ID parsed from input: {self.tidal_id}")


@dataclass
class TidalPlaylist(TidalResource):
    """Class representing a TIDAL playlist. Its main purpose is the
    __post_init__ checking process"""

    url: str

    def __post_init__(self):
        self.pattern: str = r"http(?:s)?://(?:listen\.)?tidal\.com/(?:browse/)?playlist/([0-9a-f]{8}\-[0-9a-f]{4}\-4[0-9a-f]{3}\-[89ab][0-9a-f]{3}\-[0-9a-f]{12})(?:.*?)?"

        _id = self.match_url()

        if _id is None:
            raise ValueError(f"'{self.url}' is not a valid TIDAL playlist URL")
        else:
            self.tidal_id = _id
            logger.info(f"TIDAL playlist ID parsed from input: {self.tidal_id}")


@dataclass
class TidalVideo(TidalResource):
    """Class representing a TIDAL video. Its main purpose is the
    __post_init__ checking process"""

    url: str

    def __post_init__(self):
        self.pattern: str = (
            r"http(?:s)?://(?:listen\.)?tidal\.com/(?:browse/)?video/(\d{7,9})(?:.*?)?"
        )
        _id = self.match_url()

        if _id is None:
            raise ValueError(f"'{self.url}' is not a valid TIDAL video URL")
        else:
            self.tidal_id = int(_id)
            logger.info(f"TIDAL video ID parsed from input: {self.tidal_id}")


def match_tidal_url(input_str: str) -> Optional[TidalResource]:
    """Attempt to match the `input_str` to either the URL of a track or an
    album in the Tidal API service. Returns None if `input_str` matches
    neither, otherwise a subclass of TidalResource corresponding to the
    parsed input_str type
    """
    tidal_resource: Optional[TidalResource] = None
    try:
        tidal_resource: TidalAlbum = TidalAlbum(input_str)
    except ValueError as v:
        logger.debug(v)
        try:
            tidal_resource: TidalTrack = TidalTrack(input_str)
        except ValueError as ve:
            logger.debug(ve)
            try:
                tidal_resource: TidalVideo = TidalVideo(input_str)
            except ValueError as ver:
                logger.debug(ver)
                try:
                    tidal_resource: TidalPlaylist = TidalPlaylist(input_str)
                except ValueError as verr:
                    logger.debug(verr)
    finally:
        return tidal_resource
