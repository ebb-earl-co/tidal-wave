import json
import logging
from requests import Session
from typing import Dict, List, Optional, Union

from .models import VideosEndpointStreamResponseJSON

import m3u8

logger = logging.getLogger(__name__)


class TidalM3U8Exception(Exception):
    pass


# https://github.com/globocom/m3u8#using-different-http-clients
class RequestsClient:
    """A custom class to pass to the m3u8.load() function"""

    def __init__(self, session: Session):
        self.session = session

    def download(
        self, url: str, timeout: Optional[int] = None, headers={}, verify_ssl=True
    ):
        p: Dict[str, None] = {k: None for k in self.session.params}
        with self.session.get(url=url, timeout=timeout, params=p) as response:
            return response.text, response.url


def playlister(
    session: Session, vesrj: Optional[VideosEndpointStreamResponseJSON]
) -> m3u8.M3U8:
    """Attempts to parse a VideosEndpointStreamResponseJSON object into an
    m3u8.M3U8 object. Requires fetching HTTP(s) resources, so takes a
    requests.Session object as an argument. If error occurs, raises
    TidalM3U8Exception"""
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

        em_three_you_ate: m3u8.M3U8 = m3u8.load(
            url, http_client=RequestsClient(session=session)
        )
    return em_three_you_ate


def variant_streams(
    m3u8: m3u8.M3U8, return_urls: bool = False
) -> Optional[Union[m3u8.Playlist, List[str]]]:
    """By default, return the highest-bandwidth option of m3u8.playlists
    as an m3u8.Playlist object. If return_urls, then returns the object's
    .files attribute, which is a list of strings. N.b. if m3u8.is_variant
    is False, then return None as there are no variant streams."""
    if not m3u8.is_variant:
        return
    playlist: m3u8.Playlist = max(m3u8.playlists, key=lambda p: p.stream_info.bandwidth)
    if return_urls:
        _m3u8: m3u8.M3U8 = m3u8.load(playlist)
        return _m3u8.files
    else:
        return playlist
