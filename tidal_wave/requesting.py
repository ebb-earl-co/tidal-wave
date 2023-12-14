from functools import partial
import logging
from typing import Callable, Dict, Optional, Union

from .models import (
    AlbumsEndpointResponseJSON,
    AlbumsItemsResponseJSON,
    AlbumsReviewResponseJSON,
    SessionsEndpointResponseJSON,
    SubscriptionEndpointResponseJSON,
    TracksCreditsResponseJSON,
    TracksEndpointResponseJSON,
    TracksEndpointStreamResponseJSON,
    TracksLyricsResponseJSON,
    VideosContributorsResponseJSON,
    VideosEndpointResponseJSON,
)
from .utils import TIDAL_API_URL

from requests import HTTPError, PreparedRequest, Request, Session

logger: logging.Logger = logging.getLogger(__name__)

ResponseJSON = Union[
    AlbumsEndpointResponseJSON,
    AlbumsItemsResponseJSON,
    AlbumsReviewResponseJSON,
    SessionsEndpointResponseJSON,
    SubscriptionEndpointResponseJSON,
    TracksCreditsResponseJSON,
    TracksEndpointResponseJSON,
    TracksEndpointStreamResponseJSON,
    TracksLyricsResponseJSON,
    VideosContributorsResponseJSON,
    VideosEndpointResponseJSON,
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
                else:
                    logger.exception(he)
            else:
                if cf:
                    data = sc.from_dict({"credits": resp.json()})
                    logger.debug(
                        f"{resp.status_code} response from TIDAL API to request: {e}/{i}{u}"
                    )
                else:
                    data = sc.from_dict(resp.json())
                    logger.debug(
                        f"{resp.status_code} response from TIDAL API to request: {e}/{i}{u}"
                    )
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
    [Session, int, str], Optional[TracksLyricsResponseJSON]
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
    [Session, int], Optional[TracksEndpointResponseJSON]
] = partial(
    requester_maker,
    endpoint="videos",
    headers={"Accept": "application/json"},
    subclass=VideosEndpointResponseJSON,
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
