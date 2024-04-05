import base64
from contextlib import closing, contextmanager
from io import BytesIO
import logging
import os
from pathlib import Path
import socket
import tempfile
from typing import Optional, Tuple, Union

from Crypto.Cipher import AES
from requests import Session

TIDAL_API_URL: str = "https://api.tidal.com/v1"
IMAGE_URL: str = "https://resources.tidal.com/images/%s.jpg"

logger = logging.getLogger(__name__)


def replace_illegal_characters(input_str: str) -> str:
    """Some characters are illegal for use as file names on Windows
    and on Unix-like systems. This function replaces any of the
    forbidden characters found in input_str with a replacement;
    mostly the empty string."""
    s = (
        input_str.replace("/", "_")
        .replace("|", "_")
        .replace(":", " -")
        .replace('"', "")
        .replace(">", "")
        .replace("<", "")
        .replace("/", "")
        .replace("\\", "")
        .replace("?", "")
        .replace(" ?", "")
        .replace("? ", "")
        .replace("*", "")
        .replace("\0", "")  # ASCII null character
    )
    return s


def download_cover_image(
    session: Session,
    cover_uuid: str,
    output_dir: Path,
    file_name: str = "cover.jpg",
    dimension: Union[int, Tuple[int]] = 1280,
) -> Optional[Path]:
    """Given a UUID that corresponds to a (JPEG) image on Tidal's servers,
    download the image file and write it as 'cover.jpeg' or 'cover.png'
    in the directory `path_to_output_dir`. Returns path to downloaded file"""
    cover_url_part: str = cover_uuid.replace("-", "/")
    if isinstance(dimension, int):
        _url: str = IMAGE_URL % f"{cover_url_part}/{dimension}x{dimension}"
    elif isinstance(dimension, tuple):
        _url: str = IMAGE_URL % f"{cover_url_part}/{dimension[0]}x{dimension[1]}"

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


@contextmanager
def temporary_file(suffix: str = ".mka"):
    """This context-managed function is a stand-in for
    tempfile.NamedTemporaryFile as that stdlib object experiences
    errors on Windows."""
    file_name: str = os.path.join(
        tempfile.gettempdir(), f"{os.urandom(24).hex()}{suffix}"
    )
    if not os.path.exists(file_name):
        open(file=file_name, mode="x").close()

    tf = open(file=file_name, mode="wb")
    try:
        yield tf
    finally:
        tf.close()
        os.unlink(tf.name)


def decrypt_manifest_key_id(manifest_key_id: str) -> Tuple[bytes, bytes]:
    """Given a 'keyId' value from the TIDAL API manifest response, use the
    master_key gleaned from previous projects and decrypt the audio bytes.
    This will work if the manifest specifies encryption type 'OLD_AES'.
    Returns a tuple of bytes, representing the key and nonce to use to
    decrypt the audio data."""

    # https://github.com/yaronzz/Tidal-Media-Downloader/blob/master/TIDALDL-PY/tidal_dl/decryption.py#L25
    master_key: str = "UIlTTEMmmLfGowo/UC60x2H45W6MdGgTRfo/umg4754="

    # Decode the base64 strings to ascii strings
    master_key_bytes: bytes = base64.b64decode(master_key)
    manifest_key_bytes: bytes = base64.b64decode(manifest_key_id)

    # Get the IV from the first 16 bytes of the manifest's keyId
    iv: bytes = manifest_key_bytes[:16]
    encrypted_manifest_key_bytes: bytes = manifest_key_bytes[16:]

    decryptor = AES.new(master_key_bytes, AES.MODE_CBC, iv)
    decrypted_manifest_key_bytes: bytes = decryptor.decrypt(
        encrypted_manifest_key_bytes
    )

    key, nonce = decrypted_manifest_key_bytes[:16], decrypted_manifest_key_bytes[16:24]
    return key, nonce


def is_tidal_api_reachable(hostname: str = "api.tidal.com") -> bool:
    """Using stdlib 'socket' library, test if a few conditions are all
    met: whether the user has a connection to the larger Internet;
    whether the user can resolve the primary URL for this service,
    api.tidal.com, and whether api.tidal.com is responding to requests"""
    try:
        s = closing(socket.create_connection((hostname, 80)))
    except ConnectionRefusedError:
        logger.critical("It seems that 'api.tidal.com' is unreachable!")
        return False
    except socket.gaierror as g:
        logger.critical(
            f"tidal-wave is unable to find the IP address of {hostname}: "
            "Please ensure that Internet connectivity is established, "
            "particularly DNS resolution"
        )
        return False
    except OSError as ose:
        if "[Errno 101] Network is unreachable" in ose.msg:
            logger.critical(
                "tidal-wave appears to be unable to reach the Internet. "
                "Please ensure that connectivity to (at least) api.tidal.com "
                "is possible"
            )
            return False
    except Exception as e:
        logger.exception(e)
        return False
    else:
        return True
