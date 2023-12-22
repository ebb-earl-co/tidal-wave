from pathlib import Path
import shutil
from typing import Optional, Tuple

from requests import Session


@dataclass
class Playlist:
    playlist_id: str  # UUID4

    def __post_init__(self):
        self.playlist_dir: Optional[Path] = None
        self.playlist_cover_saved: bool = False

    def get_metadata(self, session: Session):
        self.metadata: Optional[PlaylistsEndpointResponseJSON] = request_playlists(
            session=session, identifier=self.playlist_id
        )
        self.name = (
            self.metadata.title.replace("/", "_").replace("|", "_").replace(":", " -")
        )

    def set_items(self, session: Session):
        playlist_items: Optional[PlaylistsItemsResponseJSON] = get_playlist(
            session=session, playlist_id=self.playlist_id
        )
        if playlist_items is None:
            self.items = tuple()
        else:
            self.items: Tuple[Optional[PlaylistItem]] = tuple(playlist_items.items)

    def set_dir(self, out_dir: Path):
        playlist_substring: str = f"{self.name} [{self.playlist_id}]"
        self.playlist_dir: Path = out_dir / "Playlists" / playlist_substring
        self.playlist_dir.mkdir(parents=True, exist_ok=True)

    def save_cover_image(self, session: Session, out_dir: Path):
        if self.playlist_dir is None:
            self.set_dir(out_dir=out_dir)
        self.cover_path: Path = self.playlist_dir / "cover.jpg"
        if not self.cover_path.exists():
            download_cover_image(
                session=session,
                cover_uuid=self.metadata.image,
                output_dir=self.playlist_dir,
            )
        else:
            self.playlist_cover_saved = True

    def save_description(self):
        description_path: Path = self.playlist_dir / "PlaylistDescription.txt"
        if self.metadata.description is not None and len(self.metadata.description) > 0:
            if not description_path.exists():
                description_path.write_text(f"{self.metadata.description}\n")

    def get_items(self, session: Session, audio_format: AudioFormat):
        if len(self.items) == 0:
            return
        tracks_videos: list = [None] * len(self.items)
        for i, item in enumerate(self.items):
            if item is None:
                tracks_videos[i] = None
                sleep_to_mimic_human_activity()
                continue
            elif isinstance(item, TracksEndpointResponseJSON):
                track: Track = Track(track_id=item.id)
                track.get(
                    session=session,
                    audio_format=audio_format,
                    out_dir=self.playlist_dir,
                    metadata=item,
                )
                tracks_videos[i] = track
                sleep_to_mimic_human_activity()
            elif isinstance(item, VideosEndpointResponseJSON):
                video: Video = Video(video_id=item.id)
                video.get(
                    session=session,
                    out_dir=self.playlist_dir,
                    metadata=item,
                )
                tracks_videos[i] = video
                sleep_to_mimic_human_activity()
            else:
                tracks_videos[i] = None
                sleep_to_mimic_human_activity()
                continue
        else:
            self.tracks_videos: Tuple[
                Tuple[int, Optional[Union[Track, Video]]]
            ] = tuple(tracks_videos)

    def flatten_playlist_dir(self):
        """When self.get_items() is called, the tracks and/or videos in
        self.items are downloaded using their self-contained .get() logic;
        this means that they will be downloaded to albums. This function
        "flattens" self.playlist_dir, meaning that it moves all downloaded
        audio and video files to self.playlist_dir, and removes the various
        subdirectories created"""
        files: List[Dict[int, Optional[str]]] = [None] * len(self.tracks_videos)
        subdirs: Set[Path] = set()

        for i, tv in enumerate(self.tracks_videos, 1):
            if getattr(tv, "outfile") is None:
                subdirs.add(tv.album_dir)
                subdirs.add(tv.album_dir.parent)
                files[i - 1] = {i: None}
                continue

            _path: Optional[Path] = Path(tv.outfile) if tv is not None else None
            # if the item never got turned into a track or video
            if _path is None:
                files[i - 1] = {i: None}
                continue

            # if the track or video didn't download
            if _path.exists():
                if _path.stat().st_size == 0:
                    files[i - 1] = {i: None}
                    continue
            else:
                files[i - 1] = {i: None}
                continue

            # otherwise, move files and clean up
            if isinstance(tv, Track):
                new_path: Path = self.playlist_dir / f"{i:03d} - {tv.trackname}"
                new_path.write_bytes(_path.read_bytes())
                _path.unlink()
                files[i - 1] = {i: str(new_path.absolute())}
            elif isinstance(tv, Video):
                new_path: Path = self.playlist_dir / f"{i:03d} - {_path.name}"
                new_path.write_bytes(_path.read_bytes())
                _path.unlink()
                files[i - 1] = {i: str(new_path.absolute())}
        else:
            self.files: List[Dict[int, Optional[str]]] = files

        # Find all subdirectories written to
        subdirs: Set[Path] = set()
        for tv in self.tracks_videos:
            if isinstance(tv, Track):
                subdirs.add(tv.album_dir)
                subdirs.add(tv.album_dir.parent)
            elif isinstance(tv, Video):
                subdirs.add(tv.artist_dir)

        # Copy all artist images, artist bio JSON files out
        # of subdirs
        artist_images: Set[Path] = set()
        for subdir in subdirs:
            for p in subdir.glob("*.jpg"):
                if p.name == "cover.jpeg":
                    continue
                artist_images.add(p)
        else:
            for artist_image_path in artist_images:
                if artist_image_path.exists():
                    shutil.copyfile(
                        artist_image_path.absolute(),
                        self.playlist_dir / artist_image_path.name,
                    )

        artist_bios: Set[Path] = set()
        for subdir in subdirs:
            for p in subdir.glob("*bio.json"):
                artist_bios.add(p)
        else:
            for artist_bio_path in artist_bios:
                if artist_bio_path.exists():
                    shutil.copyfile(
                        artist_bio_path.absolute(),
                        self.playlist_dir / artist_bio_path.name,
                    )

        # Remove all subdirs
        for subdir in subdirs:
            if subdir.exists():
                shutil.rmtree(subdir)
        else:
            return self.playlist_dir

    def dumps(self):
        return json.dumps(self.files)

    def dump(self, fp=sys.stdout):
        json.dump(self.files, fp)

    def get(self, session: Session, audio_format: AudioFormat, out_dir: Path):
        self.get_metadata(session)
        self.set_items(session)
        self.set_dir(out_dir)
        self.save_cover_image(session, out_dir)
        try:
            self.save_description()
        except:
            pass
        self.get_items(session, audio_format)
        self.flatten_playlist_dir()
        logger.info(f"Playlist files written to '{self.playlist_dir}'")

