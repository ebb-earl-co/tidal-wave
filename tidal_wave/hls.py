import json
import logging
from typing import Dict, List, Optional, Union

from .models import VideosEndpointStreamResponseJSON

from httpx import Client, HTTPError, Request, Response, URL
import m3u8
from requests import HTTPError, Session


logger = logging.getLogger(__name__)


class TidalM3U8Exception(Exception):
    pass


# https://github.com/globocom/m3u8#using-different-http-clients
class RequestsClient:
    """A custom class to pass to the m3u8.load() function"""

    def __init__(self, client: Client):
        self.client = client

    def download(
        self, url: str, timeout: Optional[int] = None, headers={}, verify_ssl=True
    ):
        request: Request = self.client.build_request("GET", url)
        # Unset params to avoid 403 response
        request.url: URL = URL(url)
        response: Response = self.client.send(request).raise_for_status()
        return response.text, response.url


def playlister(
    client: Client, vesrj: Optional[VideosEndpointStreamResponseJSON]
) -> m3u8.M3U8:
    """Attempts to parse a VideosEndpointStreamResponseJSON object into an
    m3u8.M3U8 object. Requires fetching HTTP(s) resources, so takes an
    httpx.Client object as an argument. If error occurs, raises TidalM3U8Exception"""
    em_three_you_ate: Optional[m3u8.M3U8] = None
    if vesrj.manifest_mime_type == "application/vnd.tidal.emu":
        try:
            manifest: Dict[str, str] = json.loads(vesrj.manifest_bytes)
        except json.decoder.JSONDecodeError:
            raise TidalM3U8Exception(
                f"Expected an HLS spec. in JSON format for video {vesrj.video_id}"
            )
        else:
            mt: Optional[str] = manifest.get("mimeType")
            url: Optional[str] = manifest.get("urls", [None])[0]

        if (
            (mt is None)
            or (mt != "application/vnd.apple.mpegurl")
            or (url is None)
            or (".m3u8" not in url)
        ):
            raise TidalM3U8Exception(
                f"Manifest for video {vesrj.video_id}, video mode "
                f"{vesrj.video_quality} does not make available an "
                "M3U8 file"
            )

        request: Request = client.build_request("GET", url=url)
        # Unset params to avoid 403 response
        request.url: URL = URL(url=url)

        logger.debug(f"Requesting m3u8 playlists for video {vesrj.video_id}")
        try:
            response: Response = client.send(request).raise_for_status()
        except HTTPError:
            raise TidalM3U8Exception(
                f"Could not retrieve variant streams from manifest for "
                f"video {vesrj.video_id}, video mode {vesrj.video_quality}"
            )
        else:
            em_three_you_ate: m3u8.M3U8 = m3u8.M3U8(content=response.text)

    return em_three_you_ate


def variant_streams(
    em3u8: m3u8.M3U8, client: Client, return_urls: bool = False
) -> Optional[Union[m3u8.M3U8, List[str]]]:
    """By default, return the highest-bandwidth option of em3u8.playlists
    as an m3u8.M3U8 object. If return_urls, then the object's .files
    attribute is returned, which is a list of strings. N.b., if m3u8.is_variant
    is False, then return None as there are no variant streams."""
    if not em3u8.is_variant:
        return

    playlist: m3u8.Playlist = max(
        em3u8.playlists, key=lambda p: p.stream_info.bandwidth
    )
    if not return_urls:
        return playlist

    request: Request = client.build_request("GET", playlist.uri)
    # Unset parameters from client to avoid 403 error
    request.url = URL(playlist.uri)

    try:
        response: Response = client.send(request).raise_for_status()
    except HTTPError:
        raise TidalM3U8Exception(
            "Could not retrieve media URLs from manifest m3u8 due to "
            f"error {response.reason_phrase}"
        )
    else:
        _m3u8: m3u8.M3U8 = m3u8.M3U8(content=response.text)

    if return_urls:
        return _m3u8.files
    else:
        return _m3u8