from functools import partial
import json
import logging
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional, Tuple, Union
from uuid import uuid4

from .models import (
    AlbumsCreditsResponseJSON,
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

import backoff
from requests import HTTPError, Response, Session

logger: logging.Logger = logging.getLogger(__name__)

ResponseJSON = Union[
    AlbumsCreditsResponseJSON,
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
    subclass: Optional["ResponseJSON"] = None,
    credits_flag: bool = False,
    transparent: bool = False,
) -> Callable:
    """This function is a function factory: it crafts nearly identical
    versions of the same logic: send a GET request to a certain endpoint;
    if a requests.HTTPError arises, return None; else, transform the
    JSON response into an instance of a subclass of JSONWizard."""

    def function(s, e, i, u, h, p, sc, cf, t):
        url: str = f"{TIDAL_API_URL}/{e}/{i}{u}"
        kwargs: dict = {"url": url}
        if p is not None:
            kwargs["params"] = p
        if h is not None:
            kwargs["headers"] = h

        @backoff.on_predicate(
            backoff.expo,
            predicate=lambda r: r.status_code == 429,
            jitter=backoff.random_jitter,
            max_time=15,
            logger=logger,
        )
        def _get(s: Session, request_kwargs: dict) -> Response:
            """Return a requests.Response object, from having passed request_kwargs
            to s.get(), optionally retrying if 429 error occurs."""
            with s.get(**request_kwargs) as r:
                return r

        data: Optional[sc] = None
        logger.info(f"Requesting from TIDAL API: {e}/{i}{u}")
        resp: Response = _get(s=s, request_kwargs=kwargs)

        try:
            resp.raise_for_status()
        except HTTPError as he:
            if resp.status_code == 404:
                logger.warning(
                    f"404 Client Error: not found for TIDAL API endpoint {e}/{i}{u}"
                )
                return
            elif resp.status_code == 401:
                logger.warning(
                    f"401 Client Error: Unauthorized for TIDAL API endpoint {e}/{i}{u}"
                )
                return
            else:
                logger.exception(he)
                return

        if t:
            json_name: str = f"{e}-{i}-{u.strip('/')}_{uuid4().hex}.json"
            Path(json_name).write_text(
                json.dumps(resp.json(), ensure_ascii=True, indent=4, sort_keys=True)
            )

        if cf:
            data = sc.from_dict({"credits": resp.json()})
        else:
            data = sc.from_dict(resp.json())

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
        t=transparent,
    )


# Functions will curry all arguments except session and identifier, as those
# don't change during runtime, and session is only available once the __main__
# process (on the happy path) creates a requests.Session object. Identifier
# varies with the media type, etc.


def request_albums(
    session: Session, album_id: int, transparent: bool = False
) -> Optional[AlbumsEndpointResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="albums",
        identifier=album_id,
        headers={"Accept": "application/json"},
        subclass=AlbumsEndpointResponseJSON,
        transparent=transparent,
    )


def request_album_items(
    session: Session, album_id: int, transparent: bool = False
) -> Optional[AlbumsItemsResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="albums",
        identifier=album_id,
        headers={"Accept": "application/json"},
        parameters={"limit": 100},
        url_end="/items",
        subclass=AlbumsItemsResponseJSON,
        transparent=transparent,
    )


def request_album_review(
    session: Session, album_id: int, transparent: bool = False
) -> Optional[AlbumsReviewResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="albums",
        identifier=album_id,
        headers={"Accept": "application/json"},
        url_end="/review",
        subclass=AlbumsReviewResponseJSON,
        transparent=transparent,
    )


def request_artist_bio(
    session: Session, artist_id: int, transparent: bool = False
) -> Optional[ArtistsBioResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="artists",
        identifier=artist_id,
        headers={"Accept": "application/json"},
        url_end="/bio",
        subclass=ArtistsBioResponseJSON,
        transparent=transparent,
    )


def request_artists(
    session: Session, artist_id: int, transparent: bool = False
) -> Optional[ArtistsEndpointResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="artists",
        identifier=artist_id,
        headers={"Accept": "application/json"},
        subclass=ArtistsEndpointResponseJSON,
        transparent=transparent,
    )


def request_artists_albums(
    session: Session, artist_id: int, transparent: bool = False
) -> Optional[ArtistsAlbumsResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="artists",
        identifier=artist_id,
        headers={"Accept": "application/json"},
        url_end="/albums",
        subclass=ArtistsAlbumsResponseJSON,
        transparent=transparent,
    )


def request_artists_audio_works(
    session: Session, artist_id: int, transparent: bool = False
) -> Optional[ArtistsAlbumsResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="artists",
        identifier=artist_id,
        headers={"Accept": "application/json"},
        parameters={"filter": "EPSANDSINGLES"},
        url_end="/albums",
        subclass=ArtistsAlbumsResponseJSON,
        transparent=transparent,
    )


def request_artists_videos(
    session: Session, artist_id: int, transparent: bool = False
) -> Optional[ArtistsVideosResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="artists",
        identifier=artist_id,
        headers={"Accept": "application/json"},
        url_end="/videos",
        subclass=ArtistsVideosResponseJSON,
        transparent=transparent,
    )


def request_tracks(
    session: Session, track_id: int, transparent: bool = False
) -> Optional[TracksEndpointResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="tracks",
        identifier=track_id,
        headers={"Accept": "application/json"},
        subclass=TracksEndpointResponseJSON,
        transparent=transparent,
    )


# This one's special, because its JSON response isn't proper JSON:
# it's just an array of JSON objects, so we have to pass a flag to mark
# that the logic common to the rest of the functions is slightly different here.
def request_credits(
    session: Session, track_id: int, transparent: bool = False
) -> Optional[TracksCreditsResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="tracks",
        identifier=track_id,
        headers={"Accept": "application/json"},
        parameters={"includeContributors": True},
        url_end="/credits",
        subclass=TracksCreditsResponseJSON,
        credits_flag=True,
        transparent=transparent,
    )


# This one's special, because its JSON response isn't proper JSON:
# it's just an array of JSON objects, so we have to pass a flag to mark
# that the logic common to the rest of the functions is slightly different here.
def request_albums_credits(
    session: Session, album_id: int, transparent: bool = False
) -> Optional[AlbumsCreditsResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="albums",
        identifier=album_id,
        headers={"Accept": "application/json"},
        parameters={"includeContributors": True, "limit": 50},
        url_end="/credits",
        subclass=AlbumsCreditsResponseJSON,
        credits_flag=True,
        transparent=transparent,
    )


def request_lyrics(
    session: Session, track_id: int, transparent: bool = False
) -> Optional[TracksLyricsResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="tracks",
        identifier=track_id,
        headers={"Accept": "application/json"},
        url_end="/lyrics",
        subclass=TracksLyricsResponseJSON,
        transparent=transparent,
    )


# One more layer of currying here, as the parameters argument
# is dependent on a runtime variable.
def request_stream(
    session: Session, track_id: int, audio_quality: str, transparent: bool = False
) -> Optional[TracksEndpointStreamResponseJSON]:
    func = partial(
        requester_maker,
        session=session,
        endpoint="tracks",
        identifier=track_id,
        headers={"Accept": "application/json"},
        parameters={
            "audioquality": audio_quality,
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
        },
        url_end="/playbackinfopostpaywall",
        subclass=TracksEndpointStreamResponseJSON,
        transparent=transparent,
    )
    return func()


def request_videos(
    session: Session, video_id: int, transparent: bool = False
) -> Optional[VideosEndpointResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="videos",
        identifier=video_id,
        headers={"Accept": "application/json"},
        subclass=VideosEndpointResponseJSON,
        transparent=transparent,
    )


def request_video_contributors(
    session: Session, video_id: int, transparent: bool = False
) -> Optional[VideosContributorsResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="videos",
        identifier=video_id,
        headers={"Accept": "application/json"},
        parameters={"limit": 100},
        url_end="/contributors",
        subclass=VideosContributorsResponseJSON,
        transparent=transparent,
    )


def request_video_stream(
    session: Session, video_id: int, video_quality: str, transparent: bool = False
) -> Optional[VideosEndpointStreamResponseJSON]:
    func = partial(
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
        transparent=transparent,
    )
    return func()


def request_playlists(
    session: Session, playlist_id: int, transparent: bool = False
) -> Optional[PlaylistsEndpointResponseJSON]:
    return requester_maker(
        session=session,
        endpoint="playlists",
        identifier=playlist_id,
        headers={"Accept": "application/json"},
        subclass=PlaylistsEndpointResponseJSON,
        transparent=transparent,
    )


def get_album_id(session: Session, track_id: int) -> Optional[int]:
    """Given the Tidal ID to a track, query the Tidal API in order to retrieve
    the Tidal ID of the album to which the track belongs"""
    terj: Optional[TracksEndpointResponseJSON] = request_tracks(session, track_id)
    album_id: Optional[int] = None

    try:
        album_id = terj.id
    except AttributeError:
        pass
    finally:
        return album_id


def contiguous_ranges(value: int, range_size: int) -> Iterator[Tuple[int, int]]:
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
        t: Tuple[int, int] = (i, i + rs)
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
    ranges: Iterator[Tuple[int, int]] = contiguous_ranges(content_length, range_size)
    iterable: Iterable = (f"bytes={t[0]}-{t[1]}" for t in ranges)
    if return_tuple:
        return tuple(iterable)
    else:
        return iterable


def fetch_content_length(session: Session, url: str) -> int:
    """Attempt to get the amount of bytes pointed to by `url`. If
    the HEAD request from the requests.Session object, `session`,
    encounters an HTTP request; or if the server does not support
    HTTP range requests; or if the server does not respond with a
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
