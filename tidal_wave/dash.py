from dataclasses import dataclass, field
import json
import logging
import re
from typing import List, Optional, Tuple, Union
from xml.etree import ElementTree as ET

import dataclass_wizard
from requests import Session

from .models import TracksEndpointStreamResponseJSON
from .utils import decrypt_manifest_key_id

logger = logging.getLogger("__name__")


class TidalManifestException(Exception):
    pass


@dataclass
class S:
    d: str
    r: Optional[str] = field(default=None)

    def __post_init__(self):
        self.d: Optional[int] = int(self.d) if self.d is not None else None
        self.r: Optional[int] = int(self.r) if self.r is not None else None


@dataclass(frozen=True)
class SegmentTimeline:
    s: Tuple[Optional["S"]]


@dataclass
class JSONDASHManifest:
    mime_type: Optional[str] = field(default=None)
    codecs: Optional[str] = field(default=None)
    encryption_type: Optional[str] = field(default=None)
    key_id: Optional[str] = field(default=None)
    urls: Optional[List[str]] = field(repr=False, default=None)

    def __post_init__(self):
        self.key: Optional[bytes] = None
        self.nonce: Optional[bytes] = None
        if self.encryption_type == "OLD_AES":
            if len(self.key_id) > 0:
                logger.debug("Attempting to create decryption key from DASH manifest")
                try:
                    self.key, self.nonce = decrypt_manifest_key_id(self.key_id)
                except Exception as e:
                    logger.exception(e)


@dataclass
class XMLDASHManifest:
    mime_type: Optional[str] = field(default=None)
    codecs: Optional[str] = field(default=None)
    content_type: Optional[str] = field(default=None)
    bandwidth: Optional[str] = field(default=None)
    audio_sampling_rate: Optional[str] = field(default=None)
    timescale: Optional[str] = field(default=None)
    initialization: Optional[str] = field(default=None, repr=False)
    media: Optional[str] = field(default=None, repr=False)
    start_number: Optional[str] = field(default=None, repr=False)
    segment_timeline: Optional["SegmentTimeline"] = field(default=None, repr=False)

    def __post_init__(self):
        # Initialize key and nonce even though they won't be used in
        # this manifest class
        self.key, self.nonce = None, None

        self.bandwidth: Optional[int] = (
            int(self.bandwidth) if self.bandwidth is not None else None
        )
        self.audio_sampling_rate: Optional[int] = (
            int(self.audio_sampling_rate)
            if self.audio_sampling_rate is not None
            else None
        )
        self.timescale: Optional[int] = (
            int(self.timescale) if self.timescale is not None else None
        )
        self.startNumber: Optional[int] = (
            int(self.start_number) if self.start_number is not None else None
        )

    def build_urls(self, session: Session) -> Optional[List[str]]:
        """Parse the MPEG-DASH manifest into a list of URLs. In
        particular, look for a special value, r, in self.segment_timeline.s.
        If there is no such value, set r=1. In both cases, start substituting
        r into the special substring, '$Number$', in self.initialization.
        Continue incrementing r and substituting until the resulting string
        returns a 500 error to a HEAD request."""
        if len(self.segment_timeline.s) == 0:
            return

        def sub_number(n: int, p: str = r"\$Number\$", s: str = self.media) -> str:
            return re.sub(p, str(n), s)

        try:
            r: Optional[int] = next(S.r for S in self.segment_timeline.s)
        except StopIteration:
            r = None

        # New path for when r is None; e.g. TIDAL track 96154223
        if r is None:
            urls_list: List[str] = [self.initialization]
            number: int = 1
            while session.head(url=sub_number(number)).status_code != 500:
                urls_list.append(sub_number(number))
                number += 1
            else:
                return urls_list
        else:
            number_range = range(self.startNumber, r + 1)  # include value of `r`
            urls_list: List[str] = [self.initialization] + [
                sub_number(i) for i in number_range
            ]
            number: int = r + 1
            while session.head(url=sub_number(number)).status_code != 500:
                urls_list.append(sub_number(number))
                number += 1
            else:
                return urls_list


Manifest = Union[JSONDASHManifest, XMLDASHManifest]


def manifester(tesrj: TracksEndpointStreamResponseJSON) -> Manifest:
    """Attempt to return a Manifest-type object based on
    the attributes of `tesrj`. Will raise TidalManifestException upon
    error"""
    if tesrj.manifest_mime_type == "application/vnd.tidal.bts":
        if tesrj.audio_mode not in {"DOLBY_ATMOS", "SONY_360RA", "STEREO"}:
            raise TidalManifestException(
                "Expected a manifest of Dolby Atmos, MQA, Sony 360 Reality Audio, "
                f"or encrypted-for-Windows-client audio for track {tesrj.track_id}"
            )

        try:
            manifest: Manifest = dataclass_wizard.fromdict(
                JSONDASHManifest, json.loads(tesrj.manifest_bytes)
            )
        except json.decoder.JSONDecodeError:
            raise TidalManifestException(
                f"Cannot parse manifest with type '{tesrj.manifest_mime_type}' as JSON"
            )
        except dataclass_wizard.errors.ParseError as pe:
            raise TidalManifestException(pe.message.split("\n")[0])

        if manifest.encryption_type == "NONE":
            return manifest
        elif manifest.encryption_type == "OLD_AES":
            if (manifest.key is not None) and (manifest.nonce is not None):
                return manifest
            else:
                raise TidalManifestException(
                    f"Audio data for track {tesrj.track_id}, audio mode "
                    f"{tesrj.audio_mode} could not be decrypted"
                )
        else:
            raise TidalManifestException(
                f"Audio data for track {tesrj.track_id}, audio mode "
                f"{tesrj.audio_mode} is incorrigibly encrypted with "
                f"encryption type '{manifest.encryption_type}'"
            )
    elif tesrj.manifest_mime_type == "application/dash+xml":
        try:
            xml: ET.Element = ET.fromstring(tesrj.manifest_bytes)
        except ET.ParseError:
            raise TidalManifestException(
                f"Expected an XML manifest for track {tesrj.track_id}"
            )

        ns: str = re.match(r"({.*})", xml.tag).groups()[0]
        st: SegmentTimeline = SegmentTimeline(
            tuple(
                S(**el.attrib) if el is not None else None
                for el in xml.findall(f".//{ns}S")
            )
        )

        manifest = XMLDASHManifest(
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
        return manifest
