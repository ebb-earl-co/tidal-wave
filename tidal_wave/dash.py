from dataclasses import dataclass, field
import json
import re
from typing import List, Optional, Tuple, Union
from xml.etree import ElementTree as ET

import dataclass_wizard
from requests import Session

from .models import TracksEndpointStreamResponseJSON


class TidalManifestException(Exception):
    pass


@dataclass
class S:
    d: str
    r: Optional[str] = field(default=None)

    def __post_init__(self):
        self.d = int(self.d) if self.d is not None else None
        self.r = int(self.r) if self.r is not None else None


@dataclass(frozen=True)
class SegmentTimeline:
    s: Tuple[Optional["S"]]


@dataclass
class JSONDASHManifest:
    mime_type: Optional[str] = field(default=None)
    codecs: Optional[str] = field(default=None)
    encryption_type: Optional[str] = field(default=None)
    urls: Optional[List[str]] = field(repr=False, default=None)


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
        self.bandwidth = int(self.bandwidth) if self.bandwidth is not None else None
        self.audio_sampling_rate = (
            int(self.audio_sampling_rate)
            if self.audio_sampling_rate is not None
            else None
        )
        self.timescale = int(self.timescale) if self.timescale is not None else None
        self.startNumber = (
            int(self.start_number) if self.start_number is not None else None
        )

    def build_urls(self, session: Session) -> Optional[List[str]]:
        """Parse the MPEG-DASH manifest in the way that it was *supposed* to
        be parsed, with a few network calls because we aren't actually THAT
        clever."""
        if len(self.segment_timeline.s) == 0:
            return

        def sub_number(n: int, p: str = r"\$Number\$", s: str = self.media) -> str:
            return re.sub(p, str(n), s)

        try:
            _r: str = next(S.r for S in self.segment_timeline.s)
        except StopIteration:
            return
        else:
            r = int(_r)

        number_range = range(self.startNumber, r + 1)  # include value of `r`
        urls_list: List[str] = [self.initialization] + [
            sub_number(i) for i in number_range
        ]
        # Now, do the slightly-less-brute-force of adding each incremented value of
        # `r` that doesn't result in a 500 response to a HEAD request.
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
        if tesrj.audio_mode == "DOLBY_ATMOS":
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
            else:
                if manifest.encryption_type != "NONE":
                    raise TidalManifestException(
                        f"Manifest for track {tesrj.track_id}, audio mode "
                        f"{tesrj.audio_mode} is encrypted"
                    )
                else:
                    return manifest
        elif tesrj.audio_mode == "STEREO" and tesrj.audio_quality == "HI_RES":
            # Dealing with MQA here
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
            else:
                if manifest.encryption_type != "NONE":
                    raise TidalManifestException(
                        f"Manifest for track {tesrj.track_id}, audio mode "
                        f"{tesrj.audio_mode} is encrypted"
                    )
                else:
                    return manifest
        elif tesrj.audio_mode == "SONY_360RA":
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
            else:
                if manifest.encryption_type != "NONE":
                    raise TidalManifestException(
                        f"Manifest for track {tesrj.track_id}, audio mode "
                        f"{tesrj.audio_mode} is encrypted"
                    )
                else:
                    return manifest
        else:
            raise TidalManifestException(
                "Expected a manifest for Dolby Atmos, MQA, or Sony 360 Reality Audio "
                f"for track {tesrj.track_id}"
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
