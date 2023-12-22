from typing import Optional

import m3u8
from requests import Session


@dataclass
class Video:
    video_id: int

    def __post_init__(self):
        self.tags: dict = {}
        self.codec: str = "mp4"

    def get_metadata(self, session: Session):
        self.metadata: Optional[VideosEndpointResponseJSON] = request_videos(
            session=session, identifier=self.video_id
        )

    def get_contributors(self, session: Session):
        self.contributors: Optional[
            VideosContributorsResponseJSON
        ] = request_video_contributors(session=session, identifier=self.video_id)

    def get_stream(self, session: Session, video_format=VideoFormat.high):
        """Populates self.stream"""
        self.stream: Optional[VideosEndpointStreamResponseJSON] = request_video_stream(
            session=session, video_id=self.video_id, video_quality=video_format.value
        )

    def get_m3u8(self, session: Session):
        """This method sets self.m3u8, an m3u8.M3U8 object
        following the HTTP Live Streaming specification; parsed from
        self.stream. I.e., self.get_stream() needs to have been executed
        before calling this method. N.b. self.m3u8 almost certainly will
        be a multivariant playlist, meaning further processing of its
        contents will be necessary."""
        self.m3u8: m3u8.Playlist = playlister(session=session, vesrj=self.stream)

    def set_urls(self):
        """This method uses self.m3u8, an m3u8.M3U8 object that is variant:
        (https://developer.apple.com/documentation/http-live-streaming/creating-a-multivariant-playlist)
        It retrieves the highest-quality .m3u8 in its .playlists attribute,
        and sets self.urls as the list of strings from that m3u8.Playlist"""
        # for now, just get the highest-bandwidth playlist
        playlist: m3u8.Playlist = variant_streams(self.m3u8)
        self.M3U8 = m3u8.load(playlist.uri)
        if self.M3U8 is None or len(self.M3U8.files) == 0:
            raise TidalM3U8Exception(
                f"HLS media segments are not available for video {self.video_id}"
            )
        self.urls: List[str] = self.M3U8.files

    def set_artist_dir(self, out_dir: Path):
        self.artist_dir: Path = out_dir / self.metadata.artist.name
        self.artist_dir.mkdir(parents=True, exist_ok=True)

    def set_filename(self, out_dir: Path):
        self.filename: str = (
            f"{self.metadata.name} [{self.stream.video_quality}].{self.codec}"
        )

    def set_outfile(self):
        """Uses self.artist_dir and self.metadata and self.filename
        to craft the pathlib.Path object, self.outfile, that is a
        reference to where the track will be written on disk."""
        self.outfile: Path = self.artist_dir / self.filename

        if (self.outfile.exists()) and (self.outfile.stat().st_size > 0):
            logger.info(
                f"Video {str(self.outfile.absolute())} already exists "
                "and therefore will not be overwritten"
            )
            return
        else:
            return self.outfile

    def download(self, session: Session, out_dir: Path) -> Optional[Path]:
        if session.session_id is not None:
            download_headers: Dict[str, str] = {"sessionId": session.session_id}
        else:
            download_headers: dict = dict()
        download_params: Dict[str, None] = {k: None for k in session.params}
        # self.outfile should already have been setted by self.set_outfile()
        logger.info(
            f"Writing video {self.video_id} to '{str(self.outfile.absolute())}'"
        )

        with temporary_file() as ntf:
            for u in self.urls:
                download_request = session.prepare_request(
                    Request(
                        "GET",
                        url=u,
                        headers=download_headers,
                        params=download_params,
                    )
                )
                with session.send(download_request) as download_response:
                    if not download_response.ok:
                        logger.warning(f"Could not download {self}")
                    else:
                        ntf.write(download_response.content)
            else:
                ntf.seek(0)

            # will always be .mp4 because HLS
            ffmpeg.input(ntf.name, hide_banner=None, y=None).output(
                str(self.outfile.absolute()),
                vcodec="copy",
                acodec="copy",
                loglevel="quiet",
            ).run()

        logger.info(
            f"Video {self.video_id} written to '{str(self.outfile.absolute())}'"
        )
        return self.outfile

    def craft_tags(self):
        """Using the TAG_MAPPING dictionary, write the correct values of
        various metadata tags to the file. Videos are .mp4"""
        tags = dict()
        tag_map = {k: v["m4a"] for k, v in TAG_MAPPING.items()}

        tags[tag_map["artist"]] = ";".join((a.name for a in self.metadata.artists))
        tags[tag_map["artists"]] = [a.name for a in self.metadata.artists]
        tags[tag_map["comment"]] = f"https://tidal.com/browse/video/{self.video_id}"
        tags[tag_map["date"]] = str(self.metadata.release_date.date())
        tags[tag_map["title"]] = self.metadata.title

        for tag in {"composer", "director", "lyricist", "producer"}:
            try:
                _credits_tag = ";".join(getattr(self.contributors, tag))
            except (TypeError, AttributeError):  # NoneType problems
                continue
            else:
                tags[tag_map[tag]] = _credits_tag

        # Have to convert to bytes the values of the tags starting with '----'
        for k, v in tags.copy().items():
            if k.startswith("----"):
                if isinstance(v, str):
                    tags[k]: bytes = v.encode("UTF-8")
                elif isinstance(v, list):
                    tags[k]: List[bytes] = [s.encode("UTF-8") for s in v]

        self.tags: dict = {k: v for k, v in tags.items() if v is not None}

    def set_tags(self):
        """Instantiate a mutagen.File instance, add self.tags to it, and
        save it to disk"""
        self.mutagen = mutagen.File(self.outfile)
        self.mutagen.clear()
        self.mutagen.update(**self.tags)
        self.mutagen.save()

    def get(
        self,
        session: Session,
        out_dir: Path,
        metadata: Optional["VideosEndpointResponseJSON"] = None,
    ) -> Optional[str]:
        if metadata is None:
            self.get_metadata(session)
        else:
            self.metadata = metadata

        # check for 404 error with metadata
        if self.metadata is None:
            return

        self.get_contributors(session)
        self.get_stream(session)
        if self.stream is None:
            return
        self.get_m3u8(session)
        self.set_urls()
        self.set_artist_dir(out_dir)
        self.set_filename(out_dir)
        outfile: Optional[Path] = self.set_outfile()
        if outfile is None:
            return

        if self.download(session, out_dir) is None:
            return

        self.craft_tags()
        self.set_tags()
        return str(self.outfile.absolute())

    def dump(self, fp=sys.stdout):
        json.dump({self.metadata.title: str(self.outfile.absolute())}, fp)

    def dumps(self) -> str:
        return json.dumps({self.metadata.title: str(self.outfile.absolute())})

