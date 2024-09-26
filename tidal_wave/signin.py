"""Interact with the TIDAL API in order to authenticate tidal-wave as a client."""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import TYPE_CHECKING, Literal

import httpx  # Client, HTTPStatusError, RequestError, Response
from platformdirs import user_config_path
from pydantic import (
    UUID4,
    BaseModel,
    Field,
    PositiveInt,
    ValidationError,
)

from .oauth2 import AmazonFireTVDevice, AndroidAutoDevice

# from .utils import TIDAL_API_URL

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)
CONFIG_PATH: Path = user_config_path("tidal-wave", ensure_exists=True)
AMAZON_FIRE_TV_PATH: Path = CONFIG_PATH / "AmazonFireTVDevice.json"
ANDROID_AUTOMOTIVE_PATH: Path = CONFIG_PATH / "AndroidAutoDevice.json"
TIDAL_API_URL: str = "https://api.tidal.com/v1"


class AudioFormat(str, Enum):
    """Represent TIDAL's music quality levels as an enumerated type."""

    dolby_atmos = "Atmos"
    hi_res = "HiRes"
    lossless = "Lossless"
    high = "High"
    low = "Low"


class LoginError(Exception):
    """Error raised when logging in to TIDAL API session is unsuccessful."""


class SessionClient(BaseModel):
    """Sub-object in TIDAL API response from /sessions endpoint."""

    id: PositiveInt = Field(frozen=True)
    name: str = Field(frozen=True)
    authorized_for_offline: bool = Field(alias="authorizedForOffline", frozen=True)


class SessionsEndpointResponseJSON(BaseModel):
    """Represent the response from the TIDAL API endpoint /sessions."""

    session_id: UUID4 = Field(alias="sessionId", frozen=True)
    user_id: PositiveInt = Field(alias="userId", frozen=True)
    country_code: str = Field(alias="countryCode", frozen=True, pattern=r"[A-Z]{2}")
    session_client: SessionClient = Field(alias="client", frozen=True)


def request_tidal_session(
    client: httpx.Client,
    device: Literal[AmazonFireTVDevice, AndroidAutoDevice],
) -> httpx.Client:
    """Initiate a TIDAL API 'session' by sending requests with 'client'.

    This is so that parameters expected by all subsequent TIDAL API
    queries are expected: notably, the countryCode. Thus, this function
    returns the `client` object passed in, with params and headers set.
    """
    headers: dict[str, str] = {
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "application/json;charset=UTF-8",
        "User-Agent": "TIDAL_ANDROID/2.38.0",
        # "Authorization": f"Bearer {device.access_token}",
        # Unnecessary, I believe, because client will have this header set
    }
    sessions_response: httpx.Response = client.get(
        url=f"{TIDAL_API_URL}/sessions",
        headers=headers,
    )

    try:
        sessions_response.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.critical(
            "Unable to validate or begin TIDAL API session due to HTTP request error",
        )
        raise LoginError from e

    try:
        sessions_response_json: SessionsEndpointResponseJSON = (
            SessionsEndpointResponseJSON.validate(sessions_response.json())
        )
    except ValidationError:
        logger.critical("Unable to parse response from TIDAL API, /sessions endpoint.")
        logger.debug(sessions_response.json())
        raise LoginError from None

    # TODO: find out the deviceType of Android Automotive client
    if type(device).__name__ == "AmazonFireTVDevice":
        client.params = client.params.set("deviceType", "TV")

    if sessions_response_json.country_code == "US":
        client.params = client.params.set("locale", "en_US")
        client.headers["Accept-Language"] = "en-US"
    client.params = client.params.set(
        "countryCode",
        sessions_response_json.country_code,
    )
    return client


def prepare_client_for_audio_format(
    client: httpx.Client,
    audio_format: AudioFormat,
) -> httpx.Client:
    """Load a TIDAL device from JSON file on disk and return a prepared httpx.Client.

    If the audio_format is AudioFormat.hi_res, use the Android Automotive
    device; else the Amazon Fire TV device. If exception arises, return None:
    otherwise, return httpx.Client with the params and headers needed for interaction
    with TIDAL API.
    """
    if audio_format == AudioFormat.hi_res:
        path_to_device_file: Path = ANDROID_AUTOMOTIVE_PATH
        device_model: AndroidAutoDevice = AndroidAutoDevice()
    else:
        path_to_device_file: Path = AMAZON_FIRE_TV_PATH
        device_model: AmazonFireTVDevice = AmazonFireTVDevice()

    try:
        device_json: str | None = json.load(path_to_device_file.open("rb"))
    except json.JSONDecodeError as jde:
        raise LoginError from None
    except FileNotFoundError:
        log_msg: str = (
            "No existing credentials for TIDAL device of type "
            f"{type(device_model).__name__} found on disk."
        )
        logger.warning(log_msg)
        device_json: str | None = None

    try:
        tidal_device: Literal[AmazonFireTVDevice, AndroidAutoDevice] = (
            device_model.model_validate(device_json)
        )
    except ValidationError as ve:
        if any(error["input"] is None for error in ve.errors()):
            log_msg: str = (
                "Instantiating TIDAL device of type "
                f"{type(device_model).__name__} now"
            )
            logger.info(log_msg)
            tidal_device = device_model
        else:
            raise LoginError from None

    if tidal_device.access_expired:
        if tidal_device.refresh_token is None:
            tidal_device.do_device_authorization_grant(client)
        tidal_device.do_refresh_access_token(client)

    client.headers["Authorization"] = f"Bearer {tidal_device.access_token}"
    path_to_device_file.write_text(
        tidal_device.model_dump_json(
            include=("access_token", "expiration", "refresh_token"),
        ),
    )
    return client
