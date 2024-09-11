"""Represent the DASH manifests retrieved from TIDAL API."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from xml.etree import ElementTree

import dataclass_wizard

from .utils import decrypt_manifest_key_id

if TYPE_CHECKING:
    from requests import Session

    from .models import TracksEndpointStreamResponseJSON

logger = logging.getLogger("__name__")


class TidalManifestError(Exception):
    """Exception class to alert issue with parsing of DASH manifest."""


@dataclass
class S:
    d: str
    r: str | None = field(default=None)

    def __post_init__(self) -> None:
        """Set two attributes, d, and r, after dataclass.__init__() executes."""
        self.d: int | None = int(self.d) if self.d is not None else None
        self.r: int | None = int(self.r) if self.r is not None else None


@dataclass(frozen=True)
class SegmentTimeline:
    """Represent a portion of an XML document specifying a DASH manifest."""

    s: tuple[S | None]


@dataclass
class JSONDASHManifest:
    """Represent a JSON document specifying a DASH manifest."""

    mime_type: str | None = field(default=None)
    codecs: str | None = field(default=None)
    encryption_type: str | None = field(default=None)
    key_id: str | None = field(default=None)
    urls: list[str] | None = field(repr=False, default=None)

    def __post_init__(self) -> None:
        """Set two attributes, key and nonce, after dataclass.__init__() executes."""
        self.key: bytes | None = None
        self.nonce: bytes | None = None
        if self.encryption_type == "OLD_AES" and len(self.key_id) > 0:
            logger.debug("Attempting to create decryption key from DASH manifest")
            try:
                self.key, self.nonce = decrypt_manifest_key_id(self.key_id)
            except Exception:
                logger.exception(
                    "An error occurred in the process of decrypting DASH manifest!",
                )


@dataclass
class XMLDASHManifest:
    """Represent an XML document specifying a DASH manifest."""

    mime_type: str | None = field(default=None)
    codecs: str | None = field(default=None)
    content_type: str | None = field(default=None)
    bandwidth: str | None = field(default=None)
    audio_sampling_rate: str | None = field(default=None)
    timescale: str | None = field(default=None)
    initialization: str | None = field(default=None, repr=False)
    media: str | None = field(default=None, repr=False)
    start_number: str | None = field(default=None, repr=False)
    segment_timeline: SegmentTimeline | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Set several instance attributes after __init__() executes."""
        # Initialize key and nonce even though they won't be used in
        # this manifest class
        self.key, self.nonce = None, None

        self.bandwidth: int | None = (
            int(self.bandwidth) if self.bandwidth is not None else None
        )
        self.audio_sampling_rate: int | None = (
            int(self.audio_sampling_rate)
            if self.audio_sampling_rate is not None
            else None
        )
        self.timescale: int | None = (
            int(self.timescale) if self.timescale is not None else None
        )
        self.startNumber: int | None = (
            int(self.start_number) if self.start_number is not None else None
        )

    def build_urls(self, session: Session) -> list[str] | None:
        """Parse the MPEG-DASH manifest into a list of URLs.

        In particular, look for a special value, r, in self.segment_timeline.s.
        If there is no such value, set r=1. In both cases, start substituting
        r into the special substring, '$Number$', in self.initialization.
        Continue incrementing r and substituting until the resulting string
        returns a 500 error to a HEAD request.
        """
        http_code_500: int = 500
        if len(self.segment_timeline.s) == 0:
            return None

        def sub_number(n: int, p: str = r"\$Number\$", s: str = self.media) -> str:
            return re.sub(p, str(n), s)

        try:
            r: int | None = next(S.r for S in self.segment_timeline.s)
        except StopIteration:
            r = None

        # New path for when r is None; e.g. TIDAL track 96154223
        if r is None:
            urls_list: list[str] = [self.initialization]
            number: int = 1
            while session.head(url=sub_number(number)).status_code != http_code_500:
                urls_list.append(sub_number(number))
                number += 1
            return urls_list

        number_range = range(self.startNumber, r + 1)  # include value of `r`
        urls_list: list[str] = [self.initialization] + [
            sub_number(i) for i in number_range
        ]
        number: int = r + 1
        while session.head(url=sub_number(number)).status_code != http_code_500:
            urls_list.append(sub_number(number))
            number += 1
        return urls_list


Manifest = JSONDASHManifest | XMLDASHManifest


def manifester(tesrj: TracksEndpointStreamResponseJSON) -> Manifest:
    """Attempt to return a Manifest-type object based on the attributes of `tesrj`.

    Will raise TidalManifestError upon error.
    """
    if tesrj.manifest_mime_type == "application/vnd.tidal.bts":
        if tesrj.audio_mode not in {"DOLBY_ATMOS", "SONY_360RA", "STEREO"}:
            _msg: str = (
                "Expected a manifest of Dolby Atmos, MQA, Sony 360 Reality Audio, "
                f"or encrypted-for-Windows-client audio for track {tesrj.track_id}"
            )
            raise TidalManifestError(_msg)

        try:
            manifest: Manifest = dataclass_wizard.fromdict(
                JSONDASHManifest, json.loads(tesrj.manifest_bytes)
            )
        except json.decoder.JSONDecodeError as jde:
            _msg: str = (
                "Cannot parse manifest with type "
                f"'{tesrj.manifest_mime_type}' as JSON"
            )
            raise TidalManifestError(_msg) from jde
        except dataclass_wizard.errors.ParseError as pe:
            raise TidalManifestError from pe

        if manifest.encryption_type == "NONE":
            return manifest

        if manifest.encryption_type == "OLD_AES":
            if (manifest.key is not None) and (manifest.nonce is not None):
                return manifest
            _msg: str = (
                f"Audio data for track {tesrj.track_id}, audio mode "
                f"{tesrj.audio_mode} could not be decrypted"
            )
        else:
            _msg: str = (
                f"Audio data for track {tesrj.track_id}, audio mode "
                f"{tesrj.audio_mode} is incorrigibly encrypted with "
                f"encryption type '{manifest.encryption_type}'"
            )
        raise TidalManifestError(_msg)
    elif tesrj.manifest_mime_type == "application/dash+xml":
        try:
            xml: ElementTree.Element = ElementTree.fromstring(tesrj.manifest_bytes)
        except ElementTree.ParseError as pe:
            _msg: str = f"Expected an XML manifest for track {tesrj.track_id}"
            raise TidalManifestError(_msg) from pe

        ns: str = re.match(r"({.*})", xml.tag).groups()[0]
        st: SegmentTimeline = SegmentTimeline(
            tuple(
                S(**el.attrib) if el is not None else None
                for el in xml.findall(f".//{ns}S")
            )
        )

        return XMLDASHManifest(
            xml.find(f".//{ns}AdaptationSet").get("mimeType"),
            xml.find(f".//{ns}Representation").get("codecs"),
            xml.find(f".//{ns}AdaptationSet").get("contentType"),
            xml.find(f".//{ns}Representation").get("bandwidth"),
            xml.find(f".//{ns}Representation").get("audioSamplingRate"),
            xml.find(f".//{ns}SegmentTemplate").get("timescale"),
            xml.find(f".//{ns}SegmentTemplate").get("initialization"),
            xml.find(f".//{ns}SegmentTemplate").get("media"),
            xml.find(f".//{ns}SegmentTemplate").get("startNumber"),
            st,
        )
    else:
        raise TidalManifestError("Manifest MIME type passed is not recognized.")
        return None
