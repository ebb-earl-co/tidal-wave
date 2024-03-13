import base64
from enum import Enum
import json
import logging
from pathlib import Path
import sys
from typing import Dict, Optional, Set, Tuple

from .models import SessionsEndpointResponseJSON
from .oauth import (
    TOKEN_DIR_PATH,
    BearerToken,
    TidalOauth,
    TokenException,
)
from .utils import TIDAL_API_URL

import httpx
import typer

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
) -> Optional[dict]:
    """Attempt to read `token_path` from disk and decoded its contents
    as JSON"""
    if not token_path.exists():
        logger.warning(f"FileNotFoundError: {str(token_path.absolute())}")
        return
    token_file_contents: str = token_path.read_bytes()
    decoded_token_file_contents: str = base64.b64decode(token_file_contents).decode(
        "utf-8"
    )

    try:
        bearer_token_json: dict = json.loads(decoded_token_file_contents)
    except json.decoder.JSONDecodeError:
        logger.warning(f"File '{token_path.absolute()}' cannot be parsed as JSON")
        return
    else:
        return bearer_token_json


def validate_token_for_client(token: str, user_agent: str) -> Optional[httpx.Client]:
    """Send a GET request to the /sessions endpoint of Tidal's API.
    If `token` is valid, use the SessionsEndpointResponseJSON object
    that was returned from the API to create a httpx.Client object with
    some additional attributes. Otherwise, return None"""
    http_client: Optional[httpx.Client] = None
    headers: Dict[str, str] = {
        "Accept-Encoding": "gzip, deflate, br",
        "Authorization": f"Bearer {token}",
        "User-Agent": user_agent,
    }

    try:
        r: httpx.Response = httpx.get(
            url=f"{TIDAL_API_URL}/sessions", headers=headers
        ).raise_for_status()
    except httpx.HTTPError as h:
        if r.status_code == 401:
            logger.error("Token is not authorized")
            return http_client
        else:
            logger.exception(h)
            return http_client

    serj = SessionsEndpointResponseJSON.from_dict(r.json())
    logger.debug("Adding data from API reponse to client object:")
    logger.debug(serj)

    http_client: httpx.Client = httpx.Client(
        http2=True, follow_redirects=True, max_redirects=2
    )
    http_client.headers: Dict[str, str] = headers
    http_client.user_id: str = serj.user_id
    http_client.session_id: str = serj.session_id
    http_client.client_id: str = serj.client.id
    http_client.client_name: str = serj.client.name

    if serj.country_code == "US":
        http_client.headers["Accept-Language"] = "en-US"
        http_client.params = http_client.params.set("countryCode", "US").set(
            "locale", "en_US"
        )
    elif (len(serj.country_code) == 2) and (serj.country_code.isupper()):
        http_client.params = http_client.params.set("countryCode", serj.country_code)
    return http_client


def login_fire_tv(
    token_path: Path = TOKEN_DIR_PATH / "fire_tv-tidal.token",
) -> Optional[httpx.Client]:
    """Load `token_path` from disk, initializing a BearerToken from its
    contents. If successful, return a httpx.Client object with
    extra attributes set
    """
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

    c: Optional[httpx.Client] = validate_token_for_client(
        token=bearer_token.access_token, user_agent="TIDAL_ANDROID/2.38.0"
    )
    if c is None:
        logger.critical("Access token is not valid: exiting now.")
    else:
        c.params = c.params.set("deviceType", "TV")
        bearer_token.save()
    return c


def login_android(
    token_path: Path = TOKEN_DIR_PATH / "android-tidal.token",
) -> Optional[httpx.Client]:
    logger.info(f"Loading TIDAL access token from '{str(token_path.absolute())}'")
    _token: Optional[dict] = load_token_from_disk(token_path=token_path)
    access_token: Optional[str] = None if _token is None else _token.get("access_token")
    device_type: Optional[str] = None if _token is None else _token.get("device_type")

    if access_token is None:
        logger.warning("Could not load access token from disk")
        access_token: str = typer.prompt(
            "Enter TIDAL access token from an Android (the part after 'Bearer ')"
        )
        dt_input: str = typer.prompt(
            "Is this from device type: phone, tablet, or other? "
        )
        if dt_input.lower() == "phone":
            device_type = "PHONE"
        elif dt_input.lower() == "tablet":
            device_type = "TABLET"

    c: Optional[httpx.Client] = validate_token_for_client(
        token=access_token, user_agent="TIDAL_ANDROID/1136 okhttp 4.3.0"
    )
    if c is None:
        logger.critical("Access token is not valid: exiting now.")
        if token_path.exists():
            token_path.unlink()
    else:
        logger.info(f"Access token is valid: saving to '{str(token_path.absolute())}'")
        if device_type is not None:
            c.params["deviceType"] = device_type

        c.params = c.params.set("platform", "ANDROID")
        to_write: dict = {
            "access_token": c.auth.token,
            "session_id": c.session_id,
            "client_id": c.client_id,
            "client_name": c.client_name,
            "country_code": c.params["countryCode"],
            "device_type": device_type,
        }
        logger.debug(f"Writing this bearer token to '{str(token_path.absolute())}'")
        token_path.write_bytes(base64.b64encode(bytes(json.dumps(to_write), "UTF-8")))
    return c


def login_windows(
    token_path: Path = TOKEN_DIR_PATH / "windows-tidal.token",
) -> Optional[httpx.Client]:
    _token: Optional[dict] = load_token_from_disk(token_path=token_path)
    access_token: Optional[str] = None if _token is None else _token.get("access_token")
    if access_token is None:
        access_token: str = typer.prompt(
            "Enter Tidal API access token (the part after 'Bearer ')"
        )

    c: Optional[httpx.Client] = validate_token_for_client(
        token=access_token,
        user_agent="Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) TIDAL/2.36.2 Chrome/116.0.5845.228 Electron/26.6.1 Safari/537.36",
    )
    if c is None:
        logger.critical("Access token is not valid: exiting now.")
        if token_path.exists():
            token_path.unlink()
    else:
        logger.debug(f"Writing this access token to '{str(token_path.absolute())}'")
        c.params = c.params.set("deviceType", "DESKTOP")
        to_write: dict = {
            "access_token": c.auth.token,
            "session_id": c.session_id,
            "client_id": c.client_id,
            "client_name": c.client_name,
            "country_code": c.params["countryCode"],
        }
        token_path.write_bytes(base64.b64encode(bytes(json.dumps(to_write), "UTF-8")))
    return c


def login_mac_os(
    token_path: Path = TOKEN_DIR_PATH / "mac_os-tidal.token",
) -> Optional[httpx.Client]:
    raise NotImplementedError


def login(
    audio_format: AudioFormat,
) -> Tuple[Optional[httpx.Client], Optional[AudioFormat]]:
    """Given a selected audio_format, either log in "automatically"
    via the Fire TV OAuth 2.0 flow, or ask for an Android-/Windows-/MacOS-
    gleaned API token; the latter to be able to access HiRes fLaC audio.
    Returns a tuple of a httpx.Client object, if no error, and the
    AudioFormat instance passed in; or (None, "") in the event of error.
    """
    high_quality_formats: Set[AudioFormat] = {
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
    elif audio_format in high_quality_formats:
        if (TOKEN_DIR_PATH / "android-tidal.token").exists():
            return (login_android(), audio_format)

        options: set = {"android", "a", "windows", "w"}
        _input: str = ""
        while _input not in options:
            _input = typer.prompt(
                "For which of Android [a] or Windows [w] would you like to provide an API token?"
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
