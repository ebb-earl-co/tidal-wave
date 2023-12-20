from contextlib import contextmanager
from io import BytesIO
import logging
import os
from pathlib import Path
import tempfile
from typing import Optional

from .models import Artist

from requests import Session

TIDAL_API_URL: str = "https://api.tidal.com/v1"
IMAGE_URL: str = "https://resources.tidal.com/images/%s.jpg"

logger = logging.getLogger(__name__)


def download_cover_image(
    session: Session,
    cover_uuid: str,
    output_dir: Path,
    file_name: str = "cover.jpg",
    dimension: int = 1280,
) -> Optional[Path]:
    """Given a UUID that corresponds to a (JPEG) image on Tidal's servers,
    download the image file and write it as 'cover.jpeg' or 'cover.png'
    in the directory `path_to_output_dir`. Returns path to downloaded file"""
    cover_url_part: str = cover_uuid.replace("-", "/")
    _url: str = IMAGE_URL % f"{cover_url_part}/{dimension}x{dimension}"

    with session.get(url=_url, headers={"Accept": "image/jpeg"}) as r:
        if not r.ok:
            logger.warning(
                "Could not retrieve data from Tidal resources/images URL "
                f"due to error code: {r.status_code}"
            )
            logger.debug(r.reason)
            return
        else:
            bytes_to_write = BytesIO(r.content)

    if bytes_to_write is not None:
        output_file: Path = output_dir / file_name
        bytes_to_write.seek(0)
        output_file.write_bytes(bytes_to_write.read())
        bytes_to_write.close()
        return output_file


def download_artist_image(
    session: Session, artist: Artist, output_dir: Path, dimension: int = 320
) -> Optional[Path]:
    """Given a UUID that corresponds to a (JPEG) image on Tidal's servers,
    download the image file and write it as '{artist name}.jpeg'
    in the directory `output_dir`. Returns path to downloaded file"""
    _url: str = artist.picture_url(dimension)
    if _url is None:
        logger.info(
            f"Cannot download image for artist '{artist}', "
            "as Tidal supplied no URL for this artist's image."
        )
        return

    with session.get(url=_url, headers={"Accept": "image/jpeg"}) as r:
        if not r.ok:
            logger.warning(
                "Could not retrieve data from Tidal resources/images URL "
                f"for artist {artist} due to error code: {r.status_code}"
            )
            logger.debug(r.reason)
            return
        else:
            bytes_to_write = BytesIO(r.content)

    file_name: str = f"{artist.name}.jpg"
    if bytes_to_write is not None:
        output_file: Path = output_dir / file_name
        bytes_to_write.seek(0)
        output_file.write_bytes(bytes_to_write.read())
        bytes_to_write.close()
        logger.info(
            f"Wrote artist image JPEG for {artist} to "
            f"'{str(output_file.absolute())}'"
        )
        return output_file


def download_artist_bio(
    session: Session, artist: Artist, output_dir: Path
) -> Optional[Path]:
    """Given a UUID that corresponds to a (JPEG) image on Tidal's servers,
    download the image file and write it as '{artist name}.jpeg'
    in the directory `output_dir`. Returns path to downloaded file"""
    artist_bio: Optional[ArtistsBioResponseJSON] = request_
    with session.get(url=_url, headers={"Accept": "image/jpeg"}) as r:
        if not r.ok:
            logger.warning(
                "Could not retrieve data from Tidal resources/images URL "
                f"for artist {artist} due to error code: {r.status_code}"
            )
            logger.debug(r.reason)
            return
        else:
            bytes_to_write = BytesIO(r.content)

    file_name: str = f"{artist.name}.jpg"
    if bytes_to_write is not None:
        output_file: Path = output_dir / file_name
        bytes_to_write.seek(0)
        output_file.write_bytes(bytes_to_write.read())
        bytes_to_write.close()
        logger.info(
            f"Wrote artist image JPEG for {artist} to "
            f"'{str(output_file.absolute())}'"
        )
        return output_file


@contextmanager
def temporary_file():
    file_name: str = os.path.join(tempfile.gettempdir(), os.urandom(24).hex())
    # Code to acquire resource, e.g.:
    if not os.path.exists(file_name):
        open(file=file_name, mode="x").close()
    tf = open(file=file_name, mode="wb")
    try:
        yield tf
    finally:
        # Code to release resource, e.g.:
        tf.close()
        os.unlink(tf.name)
