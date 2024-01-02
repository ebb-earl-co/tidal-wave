from functools import partial
import logging
from typing import Callable, Dict, Iterable, Iterator, Optional, Tuple, Union

from .models import (
    AlbumsEndpointResponseJSON,
    AlbumsItemsResponseJSON,
    AlbumsReviewResponseJSON,
    ArtistsAlbumsResponseJSON,
    ArtistsBioResponseJSON,
    ArtistsEndpointResponseJSON,
    ArtistsVideosResponseJSON,
    PlaylistsEndpointResponseJSON,
    SessionsEndpointResponseJSON,
    SubscriptionEndpointResponseJSON,
    TracksCreditsResponseJSON,
    TracksEndpointResponseJSON,
    TracksEndpointStreamResponseJSON,
    TracksLyricsResponseJSON,
    VideosContributorsResponseJSON,
    VideosEndpointResponseJSON,
    VideosEndpointStreamResponseJSON,
)
from .utils import TIDAL_API_URL

from requests import HTTPError, PreparedRequest, Request, Session

logger: logging.Logger = logging.getLogger(__name__)

ResponseJSON = Union[
    AlbumsEndpointResponseJSON,
    AlbumsItemsResponseJSON,
    AlbumsReviewResponseJSON,
    ArtistsAlbumsResponseJSON,
    ArtistsBioResponseJSON,
    ArtistsEndpointResponseJSON,
    ArtistsVideosResponseJSON,
    PlaylistsEndpointResponseJSON,
    SessionsEndpointResponseJSON,
    SubscriptionEndpointResponseJSON,
    TracksCreditsResponseJSON,
    TracksEndpointResponseJSON,
    TracksEndpointStreamResponseJSON,
    TracksLyricsResponseJSON,
    VideosContributorsResponseJSON,
    VideosEndpointResponseJSON,
    VideosEndpointStreamResponseJSON,
]


def requester_maker(
    session: Session,
    endpoint: str,
    identifier: int,
    url_end: str = "",
    headers: Optional[dict] = None,
    parameters: Optional[dict] = None,
    subclass: Optional[ResponseJSON] = None,
    credits_flag: bool = False,
) -> Callable:
    """This function is a function factory: it crafts nearly identical
    versions of the same logic: send a GET request to a certain endpoint;
    if a requests.HTTPError arises, return None; else, transform the
    JSON response into an instance of a subclass of JSONWizard."""

    def function(s, e, i, u, h, p, sc, cf):
        url: str = f"{TIDAL_API_URL}/{e}/{i}{u}"
        kwargs: dict = {"url": url}
        if p is not None:
            kwargs["params"] = p
        if h is not None:
            kwargs["headers"] = h

        data: Optional[sc] = None
        logger.info(f"Requesting from TIDAL API: {e}/{i}{u}")
        with s.get(**kwargs) as resp:
            try:
                resp.raise_for_status()
            except HTTPError as he:
                if resp.status_code == 404:
                    logger.warning(
                        f"404 Client Error: not found for TIDAL API endpoint {e}/{i}{u}"
                    )
                elif resp.status_code == 401:
                    logger.warning(
                        f"401 Client Error: Unauthorized for TIDAL API endpoint {e}/{i}{u}"
                    )
                else:
                    logger.exception(he)
            else:
                if cf:
                    data = sc.from_dict({"credits": resp.json()})
                else:
                    data = sc.from_dict(resp.json())
            finally:
                return data

    return function(
        s=session,
        e=endpoint,
        i=identifier,
        u=url_end,
        h=headers,
        p=parameters,
        sc=subclass,
        cf=credits_flag,
    )


# Functions will curry all arguments except session and identifier, as those
# don't change during runtime, and session is only available once the __main__
# process (on the happy path) creates a requests.Session object. Identifier
# varies with the media type, etc.

request_albums: Callable[
    [Session, int], Optional[AlbumsEndpointResponseJSON]
] = partial(
    requester_maker,
    endpoint="albums",
    headers={"Accept": "application/json"},
    subclass=AlbumsEndpointResponseJSON,
)

request_album_items: Callable[
    [Session, int], Optional[AlbumsItemsResponseJSON]
] = partial(
    requester_maker,
    endpoint="albums",
    headers={"Accept": "application/json"},
    parameters={"limit": 100},
    url_end="/items",
    subclass=AlbumsItemsResponseJSON,
)

request_album_review: Callable[
    [Session, int], Optional[AlbumsItemsResponseJSON]
] = partial(
    requester_maker,
    endpoint="albums",
    headers={"Accept": "application/json"},
    url_end="/review",
    subclass=AlbumsReviewResponseJSON,
)

request_artist_bio: Callable[
    [Session, int], Optional[ArtistsBioResponseJSON]
] = partial(
    requester_maker,
    endpoint="artists",
    headers={"Accept": "application/json"},
    url_end="/bio",
    subclass=ArtistsBioResponseJSON,
)

request_artists: Callable[
    [Session, int], Optional[ArtistsEndpointResponseJSON]
] = partial(
    requester_maker,
    endpoint="artists",
    headers={"Accept": "application/json"},
    subclass=ArtistsEndpointResponseJSON,
)

request_artists_albums: Callable[
    [Session, int], Optional[ArtistsAlbumsResponseJSON]
] = partial(
    requester_maker,
    endpoint="artists",
    headers={"Accept": "application/json"},
    url_end="/albums",
    subclass=ArtistsAlbumsResponseJSON,
)

request_artists_audio_works: Callable[
    [Session, int], Optional[ArtistsAlbumsResponseJSON]
] = partial(
    requester_maker,
    endpoint="artists",
    headers={"Accept": "application/json"},
    parameters={"filter": "EPSANDSINGLES"},
    url_end="/albums",
    subclass=ArtistsAlbumsResponseJSON,
)

request_artists_videos: Callable[
    [Session, int], Optional[ArtistsAlbumsResponseJSON]
] = partial(
    requester_maker,
    endpoint="artists",
    headers={"Accept": "application/json"},
    url_end="/videos",
    subclass=ArtistsVideosResponseJSON,
)

request_tracks: Callable[
    [Session, int], Optional[TracksEndpointResponseJSON]
] = partial(
    requester_maker,
    endpoint="tracks",
    headers={"Accept": "application/json"},
    subclass=TracksEndpointResponseJSON,
)

# This one's special, because its JSON response isn't proper JSON:
# it's just an array of JSON objects, so we have to pass a flag to mark
# that the logic common to the rest of the functions is slightly different here.
request_credits: Callable[
    [Session, int], Optional[TracksCreditsResponseJSON]
] = partial(
    requester_maker,
    endpoint="tracks",
    headers={"Accept": "application/json"},
    parameters={"includeContributors": True},
    url_end="/credits",
    subclass=TracksCreditsResponseJSON,
    credits_flag=True,
)

request_lyrics: Callable[[Session, int], Optional[TracksLyricsResponseJSON]] = partial(
    requester_maker,
    endpoint="tracks",
    headers={"Accept": "application/json"},
    url_end="/lyrics",
    subclass=TracksLyricsResponseJSON,
)

# One more layer of currying here, as the parameters argument
# is dependent on a runtime variable.
request_stream: Callable[
    [Session, int, str], Optional[TracksEndpointStreamResponseJSON]
] = lambda session, track_id, audio_quality: partial(
    requester_maker,
    session=session,
    identifier=track_id,
    endpoint="tracks",
    headers={"Accept": "application/json"},
    parameters={
        "audioquality": audio_quality,
        "playbackmode": "STREAM",
        "assetpresentation": "FULL",
    },
    url_end="/playbackinfopostpaywall",
    subclass=TracksEndpointStreamResponseJSON,
)()

request_videos: Callable[
    [Session, int], Optional[VideosEndpointResponseJSON]
] = partial(
    requester_maker,
    endpoint="videos",
    headers={"Accept": "application/json"},
    subclass=VideosEndpointResponseJSON,
)

request_video_contributors: Callable[
    [Session, int], Optional[VideosContributorsResponseJSON]
] = partial(
    requester_maker,
    endpoint="videos",
    headers={"Accept": "application/json"},
    parameters={"limit": 100},
    url_end="/contributors",
    subclass=VideosContributorsResponseJSON,
)

# One more layer of currying here, as the parameters argument
# is dependent on a runtime variable.
request_video_stream: Callable[
    [Session, int, str], Optional[VideosEndpointStreamResponseJSON]
] = lambda session, video_id, video_quality: partial(
    requester_maker,
    session=session,
    identifier=video_id,
    endpoint="videos",
    headers={"Accept": "application/json"},
    parameters={
        "videoquality": video_quality,
        "playbackmode": "STREAM",
        "assetpresentation": "FULL",
    },
    url_end="/playbackinfopostpaywall",
    subclass=VideosEndpointStreamResponseJSON,
)()

request_playlists: Callable[
    [Session, int], Optional[PlaylistsEndpointResponseJSON]
] = partial(
    requester_maker,
    endpoint="playlists",
    headers={"Accept": "application/json"},
    subclass=PlaylistsEndpointResponseJSON,
)


def get_album_id(session: Session, track_id: int) -> Optional[int]:
    """Given the Tidal ID to a track, query the Tidal API in order to retrieve
    the Tidal ID of the album to which the track belongs"""
    terj: Optional[TracksEndpointResponseJSON] = request_tracks(
        session=session, identifier=track_id
    )
    album_id: Optional[int] = None

    try:
        album_id = terj.id
    except AttributeError:
        pass
    finally:
        return album_id


def contiguous_ranges(value: int, range_size: int) -> Iterator[Tuple[int]]:
    """This function is a generator: it yields two-tuples of int, with the
    tuples representing the (inclusive) boundaries of ranges of size
    range_size. The final tuple will represent a range <= range_size if
    range_size does not evenly divide value. E.g.
    ```>>> list(ranges(16, 3))
    [(0, 2), (3, 5), (6, 8), (9, 11), (12, 14), (15, 16)]
    ```
    N.b. the first tuple will always have first element 0 and the final tuple
    will always have second element `value`."""
    i: int = 0
    rs: int = range_size - 1
    while i + rs < value:
        t: Tuple[int] = (i, i + rs)
        i = t[-1] + 1
        yield t
    else:
        yield (i, value)


def http_request_range_headers(
    content_length: int, range_size: int, return_tuple: bool = True
) -> Iterable[str]:
    """This function creates HTTP request Range headers. Its iterable
    returned is of tuples; each tuple describes the (inclusive) boundaries
    of a bytes range with size range_size. If return_tuple is False, it returns
    a generator of tuples. E.g.
    ```>>> http_request_range_headers(16, 3)
    ('bytes=0-2',
     'bytes=3-5',
     'bytes=6-8',
     'bytes=9-11',
     'bytes=12-14',
     'bytes=15-16')
    ```
    """
    ranges: Iterator[Tuple[int]] = contiguous_ranges(content_length, range_size)
    iterable: Iterable = (f"bytes={t[0]}-{t[1]}" for t in ranges)
    if return_tuple:
        return tuple(iterable)
    else:
        return iterable


def fetch_content_length(session: Session, url: str) -> dict:
    """Attempt to get the amount of bytes pointed to by `url`. If
    the HEAD request from the requests.Session object, `session`,
    encounters an HTTP request; or if the server does not support
    HTTP range requests; or if the server does not response with a
    Content-Length header, return 0"""
    session_params: dict = session.params
    # Unset params to avoid 403 response
    _params: dict = {k: None for k in session_params}
    with session.head(url=url, params=_params) as resp:
        if not resp.ok:
            cl: str = "0"
        else:
            cl: str = resp.headers.get("Content-Length", "0")
    return int(cl)
