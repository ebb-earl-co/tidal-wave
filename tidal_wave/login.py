import base64
from enum import Enum
import json
import logging
from pathlib import Path
import platform
import sys
from typing import Dict, Optional, Set, Tuple

from .models import BearerAuth, SessionsEndpointResponseJSON
from .oauth import (
    PROJECT_NAME,
    TOKEN_DIR_PATH,
    BearerToken,
    TidalOauth,
    TokenException,
)
from .utils import TIDAL_API_URL

from platformdirs import user_config_path
import requests
import typer

COMMON_HEADERS: Dict[str, str] = {"Accept-Encoding": "gzip, deflate, br"}

logger = logging.getLogger(__name__)


class AudioFormat(str, Enum):
    sony_360_reality_audio = "360"
    dolby_atmos = "Atmos"
    hi_res = "HiRes"
    mqa = "MQA"
    lossless = "Lossless"
    high = "High"
    low = "Low"


class LogLevel(str, Enum):
    debug = "DEBUG"  # 10
    info = "INFO"  # 20
    warning = "WARNING"  # 30
    error = "ERROR"  # 40
    critical = "CRITICAL"  # 50


def load_token_from_disk(
    token_path: Path = TOKEN_DIR_PATH / "android-tidal.token",
) -> Optional[str]:
    if not token_path.exists():
        logger.error(f"FileNotFoundError: {str(token_path.absolute())}")
        return
    token_file_contents: str = token_path.read_bytes()
    decoded_token_file_contents: str = base64.b64decode(token_file_contents).decode(
        "utf-8"
    )

    try:
        bearer_token_json: dict = json.loads(decoded_token_file_contents)
    except json.decoder.JSONDecodeError:
        logger.error(f"File '{path_to_token_file.absolute()}' cannot be parsed as JSON")
        return
    else:
        return bearer_token_json.get("access_token")


def validate_token(
    token: str, headers: Dict[str, str] = COMMON_HEADERS
) -> Optional[requests.Session]:
    """Send a GET request to the /sessions endpoint of Tidal's API.
    If `token` is valid, use the `SessionsEndpointResponseJSON` object
    that was returned from the API to create a requests.Session object with
    some additional attributes. Otherwise, return None"""
    auth_headers: Dict[str, str] = {**headers, "Authorization": f"Bearer {token}"}
    sess: Optional[requests.Session] = None

    with requests.get(url=f"{TIDAL_API_URL}/sessions", headers=auth_headers) as r:
        try:
            r.raise_for_status()
        except requests.HTTPError as h:
            if r.status_code == 401:
                logger.error("Token is not authorized")
                return sess
            else:
                logger.exception(h)
                return sess

        serj = SessionsEndpointResponseJSON.from_dict(r.json())
        logger.debug("Adding data from API reponse to session object:")
        logger.debug(serj)

    sess: requests.Session = requests.Session()
    sess.headers: Dict[str, str] = headers
    sess.auth: BearerAuth = BearerAuth(token=token)
    sess.user_id: str = serj.user_id
    sess.session_id: str = serj.session_id
    sess.client_id: str = serj.client.id
    sess.client_name: str = serj.client.name
    if serj.country_code == "US":
        sess.params["countryCode"] = "US"
        sess.params["locale"] = "en_US"
        sess.headers["Accept-Language"] = "en-US"
    elif (len(serj.country_code) == 2) and (serj.country_code.isupper()):
        sess.params["countryCode"] = serj.country_code
    return sess


def login_fire_tv(
    token_path: Path = TOKEN_DIR_PATH / "fire_tv-tidal.token",
) -> Optional[requests.Session]:
    # new approach so that FileNotFoundError, which is handled,
    # does not explode on the STDERR output:
    bearer_token = BearerToken.load(p=token_path)
    if bearer_token is not None:
        bearer_token.save(p=token_path)
    else:
        to = TidalOauth()
        bearer_token = to.authorization_code_flow()
        logger.info("Successfully loaded token from disk.")
        bearer_token.save(p=token_path)

    # check if access needs refreshed
    if bearer_token.is_expired:
        logger.warning("TIDAL access token needs refreshing: Attempting now.")
        try:
            bearer_token.refresh()
        except TokenException as te:
            sys.exit(te.args[0])
        else:
            logger.info("Successfully refreshed TIDAL access token")

    s: Optional[requests.Session] = validate_token(bearer_token.access_token)
    if s is None:
        logger.critical("Access token is not valid: exiting now.")
    else:
        s.params["deviceType"] = "TV"
        s.headers["User-Agent"] = "TIDAL_ANDROID/2.38.0"
        bearer_token.save()
    return s


def login_android(
    token_path: Path = TOKEN_DIR_PATH / "android-tidal.token",
) -> Optional[requests.Session]:
    logger.info(f"Loading TIDAL access token from '{str(token_path.absolute())}'")
    _token: Optional[str] = load_token_from_disk(token_path=token_path)
    device_type: Optional[str] = None

    if _token is None:
        logger.warning("Could not load access token from disk")
        _token: str = typer.prompt(
            "Enter TIDAL access token from an Android (the part after 'Bearer '): "
        )
        dt_input: str = typer.prompt(
            "Is this from device type: phone, tablet, or other? "
        )
        if dt_input.lower() == "phone":
            device_type = "PHONE"
        elif dt_input.lower() == "tablet":
            device_type = "TABLET"

    s: Optional[requests.Session] = validate_token(_token)
    if s is None:
        logger.critical("Access token is not valid: exiting now.")
        if token_path.exists():
            token_path.unlink()
    else:
        logger.info(f"Access token is valid: saving to {str(token_path.absolute())}")
        if device_type is not None:
            s.params["deviceType"] = device_type

        s.headers["User-Agent"] = "TIDAL_ANDROID/1136 okhttp 4.3.0"
        to_write: dict = {
            "access_token": s.auth.token,
            "session_id": s.session_id,
            "client_id": s.client_id,
            "client_name": s.client_name,
            "country_code": s.params["countryCode"],
        }
        logger.debug(f"Writing this bearer token to '{str(token_path.absolute())}'")
        token_path.write_bytes(base64.b64encode(bytes(json.dumps(to_write), "UTF-8")))
    return s


def login_windows(
    token_path: Path = TOKEN_DIR_PATH / "windows-tidal.token",
) -> Optional[requests.Session]:
    _token: Optional[str] = load_token_from_disk(token_path=token_path)
    if _token is None:
        _token: str = typer.prompt(
            "Enter Tidal API access token (the part after 'Bearer '): "
        )

    s: Optional[requests.Session] = validate_token(_token)
    if s is None:
        logger.critical("Access token is not valid: exiting now.")
    else:
        logger.debug(f"Writing this access token to '{str(token_path.absolute())}'")
        # s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) TIDAL/2.35.0 Chrome/108.0.5359.215 Electron/22.3.27 Safari/537.36"
        s.headers["User-Agent"] = "TIDAL_NATIVE_PLAYER/WIN/3.1.2.195"
        s.params["deviceType"] = "DESKTOP"
        to_write: dict = {
            "access_token": s.auth.token,
            "session_id": s.session_id,
            "client_id": s.client_id,
            "client_name": s.client_name,
            "country_code": s.params["country_code"],
        }
        token_path.write_bytes(base64.b64encode(bytes(json.dumps(to_write), "UTF-8")))
    return s


def login_mac_os(
    token_path: Path = TOKEN_DIR_PATH / "mac_os-tidal.token",
) -> Optional[requests.Session]:
    raise NotImplementedError


def login(
    audio_format: AudioFormat,
) -> Tuple[Optional[requests.Session], Optional[AudioFormat]]:
    """Given a selected audio_format, either log in "automatically"
    via the Fire TV OAuth 2.0 flow, or ask for an Android-/Windows-/MacOS-
    gleaned API token; the latter to be able to access HiRes fLaC audio.
    Returns a tuple of a requests.Session object, if no error, and the
    AudioFormat instance passed in; or (None, "") in the event of error.
    """
    android_formats: Set[AudioFormat] = {
        AudioFormat.sony_360_reality_audio,
        AudioFormat.hi_res,
    }
    fire_tv_formats: Set[AudioFormat] = {
        AudioFormat.dolby_atmos,
        AudioFormat.mqa,
        AudioFormat.lossless,
        AudioFormat.high,
        AudioFormat.low,
    }
    if audio_format in fire_tv_formats:
        return (login_fire_tv(), audio_format)
    elif audio_format in android_formats:
        options: set = {"android", "a", "windows", "w"}
        _input: str = ""
        while _input not in options:
            _input = typer.prompt(
                "For which of Android [a] or Windows [w] would you like to provide an API token? "
            ).lower()
        else:
            if _input in {"android", "a"}:
                return (login_android(), audio_format)
            elif _input in {"windows", "w"}:
                return (login_windows(), audio_format)
    else:
        logger.critical(
            "Please provide one of the following: "
            f"{', '.join(e.value for e in AudioFormat)}"
        )
        return (None, "")
