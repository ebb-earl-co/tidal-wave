"""Represent the HLS manifests retrieved from TIDAL API."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import m3u8
from requests import HTTPError, Session

if TYPE_CHECKING:
    from .models import VideosEndpointStreamResponseJSON

logger = logging.getLogger(__name__)


class TidalM3U8Error(Exception):
    """For the arising of exception in processing HLS's .m3u8 files."""


# https://github.com/globocom/m3u8#using-different-http-clients
class RequestsClient:
    """A custom class to pass to the m3u8.load() function."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def download(
        self,
        url: str,
        timeout: int | None = None,
    ) -> tuple[str, str]:
        """Use self.session to GET `url`, returning response text and URL."""
        p: dict[str, None] = {k: None for k in self.session.params}
        with self.session.get(url=url, timeout=timeout, params=p) as response:
            return response.text, response.url


def playlister(
    session: Session,
    vesrj: VideosEndpointStreamResponseJSON | None,
) -> m3u8.M3U8:
    """Attempt to parse a VideosEndpointStreamResponseJSON into an m3u8.M3U8.

    Requires fetching HTTP(s) resources, so takes a requests.Session object
    as an argument. If exception occurs, raises TidalM3U8Error.
    """
    em_three_you_ate: m3u8.M3U8 | None = None
    if vesrj.manifest_mime_type == "application/vnd.tidal.emu":
        try:
            manifest: dict[str, str] = json.loads(vesrj.manifest_bytes)
        except json.decoder.JSONDecodeError as jde:
            _msg: str = (
                "Expected an HLS specification in JSON format "
                f"for video {vesrj.video_id}"
            )
            raise TidalM3U8Error(_msg) from jde
        else:
            mt: str | None = manifest.get("mimeType")
            url: str | None = manifest.get("urls", [None])[0]

        if (
            (mt is None)
            or (mt != "application/vnd.apple.mpegurl")
            or (url is None)
            or (".m3u8" not in url)
        ):
            _msg: str = (
                f"Manifest for video {vesrj.video_id}, video mode "
                f"{vesrj.video_quality} does not make available an "
                "M3U8 file"
            )
            raise TidalM3U8Error(_msg)

        download_params: dict[str, None] = {k: None for k in session.params}
        with session.get(url=url, params=download_params) as m3u8_response:
            try:
                m3u8_response.raise_for_status()
            except HTTPError as he:
                _msg: str = (
                    f"Could not retrieve variant streams from manifest for "
                    f"video {vesrj.video_id}, video mode {vesrj.video_quality}"
                )
                raise TidalM3U8Error(_msg) from he
            else:
                em_three_you_ate: m3u8.M3U8 | None = m3u8.M3U8(
                    content=m3u8_response.text,
                )

    return em_three_you_ate


def variant_streams(
    em3u8: m3u8.M3U8,
    session: Session,
    *,
    return_urls: bool = False,
) -> m3u8.M3U8 | list[str] | None:
    """By default, return the highest-bandwidth of em3u8.playlists as m3u8.M3U8 object.

    If return_urls, then the object's .files attribute is returned, which is a list of
    strings.
    N.b., if m3u8.is_variant is False, then return None as there are no variant streams.
    """
    if not em3u8.is_variant:
        return None

    playlist: m3u8.Playlist = max(
        em3u8.playlists,
        key=lambda p: p.stream_info.bandwidth,
    )
    if not return_urls:
        return playlist

    download_params: dict[str, None] = {k: None for k in session.params}
    with session.get(url=playlist.uri, params=download_params) as response:
        try:
            response.raise_for_status()
        except HTTPError as he:
            _msg: str = f"Could not retrieve media URLs from manifest {em3u8}"
            raise TidalM3U8Error(_msg) from he
        else:
            _m3u8: m3u8.M3U8 = m3u8.M3U8(content=response.text)

    return _m3u8.files
