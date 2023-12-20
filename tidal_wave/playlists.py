from dataclasses import dataclass
from types import SimpleNamespace

import logging
from requests import Session
from typing import Dict, List, Optional, Tuple, Union

from .models import TracksEndpointResponseJSON, VideosEndpointResponseJSON
from .utils import TIDAL_API_URL

logger = logging.getLogger(__name__)


class TidalPlaylistException(Exception):
    pass


def request_playlist_items(session: Session, playlist_id: str) -> Optional[dict]:
    url: str = f"{TIDAL_API_URL}/playlists/{playlist_id}/items"
    kwargs: dict = {"url": url}
    kwargs["params"] = {"limit": 100}
    kwargs["headers"] = {"Accept": "application/json"}

    data: Optional[dict] = None
    logger.info(f"Requesting from TIDAL API: playlists/items/{playlist_id}")
    with session.get(**kwargs) as resp:
        try:
            resp.raise_for_status()
        except HTTPError as he:
            if resp.status_code == 404:
                logger.warning(
                    f"404 Client Error: not found for TIDAL API endpoint playlists/items/{playlist_id}"
                )
            else:
                logger.exception(he)
        else:
            data = resp.json()
            logger.debug(
                f"{resp.status_code} response from TIDAL API to request: playlists/items/{playlist_id}"
            )
        finally:
            return data


@dataclass(frozen=True)
class PlaylistsItemsResponseJSON:
    """The response from the TIDAL API endpoint /playlists/<ID>/items
    is modeled by this class."""

    limit: int
    offset: int
    total_number_of_items: int
    items: Tuple[
        Optional[Union["TracksEndpointResponseJSON", "VideosEndpointResponseJSON"]]
    ]


def playlist_maker(
    playlists_response: Dict[str, Union[int, List[dict]]]
) -> "PlaylistsItemsResponseJSON":
    init_args: dict = {}
    init_args["limit"] = playlists_response.get("limit")
    init_args["offset"] = playlists_response.get("offset")
    init_args["total_number_of_items"] = playlists_response.get("totalNumberOfItems")

    items: Tuple[SimpleNamespace] = tuple(
        SimpleNamespace(**d) for d in playlists_response["items"]
    )
    if len(items) == 0:
        return

    playlist_items: List[
        Optional[Union["TracksEndpointResponseJSON", "VideosEndpointResponseJSON"]]
    ] = [None] * init_args["total_number_of_items"]

    for i, namespace in enumerate(items):
        if namespace.type == "track":
            try:
                playlist_item = TracksEndpointResponseJSON.from_dict(namespace.item)
            except Exception as e:
                logger.warning(
                    f"TidalPlaylistException: unable to parse playlist item [i] "
                    f"with type '{namespace.type}'"
                )
                logger.debug(e)
                # value stays None
            else:
                playlist_items[i] = playlist_item
        elif namespace.type == "video":
            try:
                playlist_item = VideosEndpointResponseJSON.from_dict(namespace.item)
            except Exception as e:
                logger.warning(
                    f"TidalPlaylistException: unable to parse playlist item [i] "
                    f"with type '{namespace.type}'"
                )
                logger.debug(e)
                # value stays None
            else:
                playlist_items[i] = playlist_item
        else:
            continue  # value stays None
    else:
        init_args["items"] = tuple(playlist_items)

    return PlaylistsItemsResponseJSON(**init_args)


def get_playlist(
    session: Session, playlist_id: str
) -> Optional["PlaylistsItemsResponseJSON"]:
    playlists_items_response_json: Optional["PlaylistsItemsResponseJSON"] = None
    try:
        playlists_response: dict = request_playlist_items(
            session=session, playlist_id=playlist_id
        )
        playlists_items_response_json: Optional[
            "PlaylistsItemsResponseJSON"
        ] = playlist_maker(playlists_response=playlists_response)
    except Exception as e:
        logger.exception(TidalException(e.args[0]))
    finally:
        return playlists_items_response_json


# union type for type hinting
PlaylistItem = Optional[
    Union["TracksEndpointResponseJSON", "VideosEndpointResponseJSON"]
]
