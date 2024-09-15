"""Interact with TIDAL API using OAuth 2.0 to register tidal-wave as a client."""

from __future__ import annotations

import base64
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING

import dataclass_wizard
import requests
from platformdirs import user_config_path

if TYPE_CHECKING:
    from pathlib import Path


PROJECT_NAME: str = "tidal-wave"
TOKEN_DIR_PATH: Path = user_config_path() / PROJECT_NAME
TOKEN_DIR_PATH.mkdir(exist_ok=True, parents=True)
OAUTH2_URL: str = "https://auth.tidal.com/v1/oauth2"
OAUTH2_HEADERS: dict[str, str] = {
    "User-Agent": "TIDAL_ANDROID/2.38.0",
    "Accept": "application/json",
}

logger = logging.getLogger(__name__)


class AuthorizationError(Exception):
    """Exception that is raised upon unsuccessful interaction with TIDAL API."""


class TokenError(Exception):
    """Exception that is raised upon unsuccessful interaction with TIDAL API."""


@dataclass
class DeviceAuthorizationEndpointResponseJSON(dataclass_wizard.JSONSerializable):
    """Model the JSON response from TIDAL API /device_authorization endpoint."""

    device_code: str
    user_code: str
    verification_uri_complete: str
    expires_in: int
    interval: int


@dataclass
class User:
    """Model the User object of JSON response from /device_authorization endpoint."""

    user_id: int
    email: str | None
    country_code: str
    full_name: str | None
    first_name: str | None
    last_name: str | None
    nickname: str | None
    username: str
    address: str | None
    city: str | None
    postalcode: str | None
    us_state: str | None
    phone_number: str | None
    birthday: str | None
    channel_id: int
    parent_id: int
    accepted_eula: bool
    created: int
    updated: int
    facebook_uid: int
    apple_uid: str | None
    google_uid: str | None
    account_link_created: bool
    email_verified: bool
    new_user: bool


@dataclass
class TokenEndpointResponseJSON(dataclass_wizard.JSONSerializable):
    """Model the JSON response from TIDAL API /token endpoint."""

    scope: str
    user: User
    client_name: str
    token_type: str
    access_token: str
    refresh_token: str
    expires_in: int
    user_id: int

    def __post_init__(self) -> None:
        """Set self.expiration attribute based on self.expires_in."""
        # Shave off 5 minutes from the expiration time. The API usually
        # gives 1-week expiration timeline, but depending on network latency
        # etc., want to refresh early.
        _timedelta = timedelta(seconds=self.expires_in - 300)
        self.expiration: datetime = datetime.now(tz=timezone.utc) + _timedelta


@dataclass
class BearerToken:
    """Model a JWT access token of type Bearer.

    See more at (https://swagger.io/docs/specification/authentication/bearer-authentication/).
    """

    access_token: str = field(repr=False)
    client_name: str  # "TIDAL_Android_2.38.0_Fire_TV_Atmos"
    expiration: str | datetime = field(repr=False)
    refresh_token: str = field(repr=False)
    user_id: int
    user_name: str

    def __post_init__(self) -> None:
        """Set attributes self.client_id, self.client_secret."""
        self.client_id, self.client_secret = (
            TidalOauth().client_id,
            TidalOauth().client_secret,
        )
        if isinstance(self.expiration, str):
            try:
                self.expiration = datetime.fromisoformat(self.expiration)
            except ValueError as ve:
                _msg: str = "Expiration must be a datetime or datetime-like str"
                raise TokenError(_msg) from ve

    @property
    def is_expired(self) -> bool:
        """Return whether self.expiration is in the past.

        This is done by comparing self.expiration with
        datetime.datetime.now(tz=datetime.timezone.utc).
        """
        return not (datetime.now(tz=timezone.utc) < self.expiration)

    def save(self, p: Path = TOKEN_DIR_PATH / "fire_tv-tidal.token") -> None:
        """Write some attributes as base64-encoded JSON to path on disk, p."""
        d: dict[str, str] = {
            "access_token": self.access_token,
            "client_name": self.client_name,
            "expiration": self.expiration.isoformat(),
            "refresh_token": self.refresh_token,
            "user_id": self.user_id,
            "user_name": self.user_name,
        }
        outdata: bytes = base64.b64encode(json.dumps(d).encode("UTF-8"))
        p.write_bytes(outdata)

    @classmethod
    def load(
        cls,
        p: Path = TOKEN_DIR_PATH / "fire_tv-tidal.token",
    ) -> BearerToken | None:
        """Read base64-encoded JSON object from disk.

        If no error arises, return a BearerToken instance; else, return None.
        """
        try:
            token_path_bytes = p.read_bytes()
        except FileNotFoundError:
            logger.exception(
                TokenError(f"File '{p.absolute()}' does not exist"),
            )
            return None

        try:
            data = json.loads(base64.b64decode(token_path_bytes))
        except json.JSONDecodeError:
            logger.exception(
                TokenError(f"Could not parse JSON data from '{p.absolute()}'"),
            )
            return None
        except UnicodeDecodeError:
            logger.exception(
                TokenError(
                    f"File '{p.absolute()}' does not appear to be base64-encoded",
                ),
            )
            return None

        data_args: tuple[str, str, datetime, str, int, str] = (
            data.get(a)
            for a in (
                "access_token",
                "client_name",
                "expiration",
                "refresh_token",
                "user_id",
                "user_name",
            )
        )

        _token: BearerToken = cls(*data_args)
        return _token

    def refresh(self) -> None:
        """If self.access_token is expired, go through the token refresh process.

        I.e., https://oauth.net/2/refresh-tokens/. If successful, various attributes of
        self are overwritten: most importantly, self.expiration & self.access_token
        """
        _data = {
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
            "scope": "r_usr+w_usr+w_sub",
        }
        _auth = (self.client_id, self.client_secret)
        with requests.post(
            url=f"{OAUTH2_URL}/token",
            data=_data,
            auth=_auth,
            headers=OAUTH2_HEADERS,
            timeout=5,
        ) as resp:
            try:
                resp.raise_for_status()
            except requests.HTTPError as he:
                _msg: str = (
                    f"Could not refresh bearer token: HTTP error {resp.status_code}"
                )
                raise TokenError(_msg) from he
            else:
                token_json = resp.json()

            self.access_token = token_json.get("access_token")
            if token_json.get("clientName", token_json.get("client_name")) is not None:
                self.client_name = token_json.get(
                    "clientName", token_json.get("client_name"),
                )
            if token_json.get("userId", token_json.get("user_id")) is not None:
                self.user_id = token_json.get("userId", token_json.get("user_id"))
            if token_json.get("userName", token_json.get("user_name")) is not None:
                self.user_name = token_json.get("userName", token_json.get("user_name"))

            _timedelta = timedelta(seconds=token_json.get("expires_in") - 300)
            self.expiration = datetime.now(tz=timezone.utc) + _timedelta


@dataclass
class TidalOauth:
    """This class encapsulates attributes and methods to do with authenticating
    with the Tidal OAuth API. In particular, the authorization_code_flow()
    method implements the authorization code flow part of the OAuth 2.0
    specification:
    https://auth0.com/docs/get-started/authentication-and-authorization-flow/authorization-code-flow
    The client_id and client_secret attributes are gleaned from other projects'
    work, especially
    https://github.com/Dniel97/RedSea/blob/4ba02b88cee33aeb735725cb854be6c66ff372d4/config/settings.example.py#L68
    """

    def __post_init__(self) -> None:
        """Set static attributes on self."""
        self._client_id: str = "7m7Ap0JC9j1cOM3n"
        self._client_secret: str = "vRAdA108tlvkJpTsGZS8rGZ7xTlbJ0qaZ2K9saEzsgY="
        self.token: BearerToken | None = None
        self.verification_url: str | None = None

    @property
    def client_id(self) -> str:
        """Return the instance's client ID."""
        return self._client_id

    @property
    def client_secret(self) -> str:
        """Return the instance's client secret."""
        return self._client_secret

    def post_device_authorization(self, headers: dict[str, str] = OAUTH2_HEADERS):
        """Send a POST request to the /device_authorization endpoint of Tidal's
        authentication API. If error, raises AuthorizationError. Else,
        return an DeviceAuthorizationEndpointResponseJSON instance with five
        attributes:
        device_code, user_code, verification_uri_complete, expires_in, interval
        """
        _url: str = f"{OAUTH2_URL}/device_authorization"
        _data: dict[str, str] = {
            "client_id": self.client_id,
            "scope": "r_usr+w_usr+w_sub",
        }
        with requests.post(url=_url, data=_data, headers=headers, timeout=5) as resp:
            try:
                resp.raise_for_status()
            except requests.HTTPError as he:
                raise AuthorizationError from he

            daerj = DeviceAuthorizationEndpointResponseJSON.from_dict(resp.json())

        self.device_authorization = daerj
        self.verification_url: str = f"http://{daerj.verification_uri_complete}"
        # "Date" header is in the "%a, %d %b %Y %H:%M:%S %Z" format:
        # e.g. "Wed, 06 Dec 2023 05:11:11 GMT".
        # So, parsedate_to_datetime converts the above into
        # datetime.datetime(2023, 12, 6, 5, 11, 11, tzinfo=datetime.timezone.utc)  # noqa:ERA001
        self.verification_expiration: datetime = parsedate_to_datetime(
            resp.headers.get("Date"),
        ) + timedelta(seconds=daerj.expires_in)

    def authorization_code_flow(
        self,
        headers: dict[str, str] = OAUTH2_HEADERS,
    ) -> BearerToken:
        """Return an instance of BearerToken or raise exception.

        Authenticate with the Tidal OAuth 2.0 API /token endpoint.
        Upon error, raise AuthorizationError.
        """
        _data = {
            "client_id": self.client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "scope": "r_usr+w_usr+w_sub",
        }
        if self.verification_url is None:
            self.post_device_authorization()

        _data["device_code"] = self.device_authorization.device_code
        _auth = (self.client_id, self.client_secret)

        print(  # noqa:T201
            "\nCopy this URL, then navigate to it in a browser: "
            f"{self.verification_url}\n",
            file=sys.stderr,
        )

        while datetime.now(tz=timezone.utc) < self.verification_expiration:
            with requests.post(
                url=f"{OAUTH2_URL}/token",
                headers=headers,
                data=_data,
                auth=_auth,
                timeout=5,
            ) as resp:
                if not resp.ok:
                    time.sleep(self.device_authorization.interval * 2)
                    continue
                break
        else:
            _msg: str = "OAuth login process has timed out. Please try again."
            raise AuthorizationError(_msg)

        logger.info("Successfully authenticated with Tidal API.")

        _token = TokenEndpointResponseJSON.from_dict(resp.json())
        if _token.token_type.lower() == "bearer":
            return BearerToken(
                access_token=_token.access_token,
                client_name=_token.client_name,
                expiration=_token.expiration,
                refresh_token=_token.refresh_token,
                user_id=_token.user_id,
                user_name=_token.user.username,
            )
        _msg: str = f"Expected a bearer token, but received type: {_token.token_type}"
        raise TokenError(_msg)
