"""Emulate TIDAL client devices to authenticate with TIDAL API via OAuth 2.0.

Authentication is specified in RFC 8628: the OAuth 2.0 Device Authorization Grant.

The following is a short summary of the process, from IETF:
    1. Device Authorization Request:
    The client initiates the authorization flow by requesting a set of
    verification codes from the authorization server by making an HTTP
    "POST" request to the device authorization endpoint.
    2. Device Authorization Response:
    In response, the authorization server generates a unique device
    verification code and an end-user code that are valid for a limited
    time and includes them in the HTTP response body using the
    "application/json" format
    3. User Interaction:
    After receiving a successful authorization response, the client
    displays or otherwise communicates the "user_code" and the
    "verification_uri" to the end user and instructs them to visit the
    URI in a user agent on a secondary device (for example, in a browser
    on their mobile phone) and enter the user code.
    During the user interaction, the device continuously polls the token
    endpoint with the "device_code".
    4. Device Access Token Request:
    After displaying instructions to the user, the client creates an
    access token request and sends it to the token endpoint with a
    "grant_type" of "urn:ietf:params:oauth:grant-type:device_code".
    This is an extension grant type created by this specification.
    5. Device Access Token Response:
    If the user has approved the grant, the token endpoint responds with
    a success response.
The success response includes: a Bearer access token; the amount of
seconds until it expires; a refresh token to refresh said access token;
and other data about the user's TIDAL account.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import sleep
from typing import ClassVar, NamedTuple

import httpx
from pydantic import (
    UUID4,
    BaseModel,
    Field,
    PositiveInt,
    ValidationError,
    computed_field,
)

logger = logging.getLogger(__name__)


class AuthorizationError(Exception):
    """Inability to authenticate with TIDAL API."""


class AccessTokenError(Exception):
    """Malformed or empty response from TIDAL API, /token endpoint."""


class ClientCredentials(NamedTuple):
    """Encapsulate device credential pairs as instances of namedtuple."""

    client_id: str
    client_secret: str


class DeviceAuthorizationResponse(BaseModel):
    """Represent the JSON response from the TIDAL API /device_authorization endpoint."""

    device_code: UUID4 = Field(alias="deviceCode", frozen=True)
    user_code: str = Field(alias="userCode", frozen=True)
    verification_uri_complete: str = Field(alias="verificationUriComplete", frozen=True)
    expires_in: PositiveInt = Field(alias="expiresIn", frozen=True)
    interval: PositiveInt = Field(frozen=True)


class AccessTokenResponse(BaseModel):
    """Represent the JSON response from the TIDAL API /token endpoint."""

    client_name: str = Field(alias="clientName", frozen=True)
    access_token: str = Field(frozen=True)
    refresh_token: str = Field(frozen=True)
    expires_in: PositiveInt = Field(frozen=True)
    user_id: PositiveInt = Field(frozen=True)


class AccessTokenRefreshResponse(BaseModel):
    """Represent the JSON response from TIDAL API /token endpoint.

    In particular, the response to a request specifying 'refresh' grant type.
    It is identical to AccessTokenResponse but for the lack of the
    'refresh_token' key.
    """

    client_name: str = Field(alias="clientName", frozen=True)
    access_token: str = Field(frozen=True)
    expires_in: PositiveInt = Field(frozen=True)
    user_id: PositiveInt = Field(frozen=True)


class TidalDevice(BaseModel):
    """Encapsulate RFC 8628: the OAuth 2.0 Device Authorization Grant.

    The class is meant to be initialized without constructor arguments
    as the process for interacting with TIDAL API as an OAUTH 2.0 client
    is rigidly specified.
    """

    oauth2_url: str = Field(
        default="https://auth.tidal.com/v1/oauth2",
        exclude=True,
        frozen=True,
    )
    expiration: datetime = Field(
        default=datetime(1, 1, 1, tzinfo=timezone.utc),
        repr=False,
    )
    access_token: str | None = Field(default=None, repr=False)
    refresh_token: str | None = Field(default=None, repr=False)

    # To be overwritten by subclasses representing concrete
    # device types with known client credentials.
    client_credentials: ClientCredentials = Field(
        default=ClientCredentials("", ""),
        exclude=False,
        frozen=True,
        repr=False,
    )
    verification_expiration: datetime | None = Field(default=None, repr=False)

    @computed_field(repr=False)
    def access_expired(self) -> bool:
        """Return whether self.access_token is expired based on current datetime."""
        return datetime.now(tz=timezone.utc) >= self.expiration

    @computed_field(repr=False)
    def device_access_token_request_url(self) -> str:
        """The endpoint to which to POST OAuth 2.0 Device Access Token Request."""
        return f"{self.oauth2_url}/token"

    @computed_field(repr=False)
    def device_authorization_request_data(self) -> dict[str, str]:
        """The payload to be POSTed to the /token endpoint of TIDAL API."""
        return {
            "client_id": self.client_credentials.client_id,
            "scope": "r_usr+w_usr+w_sub",
        }

    @computed_field(repr=False)
    def device_authorization_request_url(self) -> str:
        """The endpoint to which to POST OAuth 2.0 Device Authorization Request."""
        return f"{self.oauth2_url}/device_authorization"

    @computed_field(repr=False)
    def device_refresh_token_request_data(self) -> dict[str, str | None]:
        """The payload to be POSTed to the /token endpoint of TIDAL API.

        See more here:
        https://www.oauth.com/oauth2-servers/access-tokens/refreshing-access-tokens/
        """
        return {
            "client_id": self.client_credentials.client_id,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
            "scope": "r_usr+w_usr+w_sub",
        }

    @computed_field(repr=False)
    def device_refresh_token_request_url(self) -> str:
        """Where to POST OAuth 2.0 Device Access Token Refresh Request."""
        return f"{self.oauth2_url}/token"

    @computed_field(repr=False)
    def headers(self) -> dict[str, str]:
        """The HTTP headers to be included in requests to self.oauth2_url."""
        return {
            "Accept": "application/json;charset=UTF-8",
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "TIDAL_ANDROID/2.38.0",
        }

    def _do_device_authorization_request(
        self,
        client: httpx.Client,
    ) -> DeviceAuthorizationResponse | None:
        """Execute the first part of the OAuth 2.0 Device Authorization Grant.

        This step is 'Device Authorization Request'; i.e. sending a POST
        request to self.device_authorization_endpoint_url. Upon HTTP error,
        warning is logged and device_authorization_endpoint_response takes
        the value None; otherwise, it takes as its value an instance of
        DeviceAuthorizationResponse.
        Data from the token request response, if not None, is set as attributes
        on self for ease of access in subsequent steps of the OAuth 2.0 process.
        """
        response: httpx.Response = client.post(
            url=self.device_authorization_request_url,
            headers=self.headers,
            data=self.device_authorization_request_data,
        )
        device_authorization_response: DeviceAuthorizationResponse | None = None
        try:
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError):
            logger.critical("Could not successfully POST device authorization request.")
            return device_authorization_response
        else:
            device_authorization_response = DeviceAuthorizationResponse.model_validate(
                response.json(),
            )

        # "Date" header is in the "%a, %d %b %Y %H:%M:%S %Z" format
        response_timestamp: datetime = parsedate_to_datetime(
            response.headers.get("Date"),
        )
        self.verification_expiration: datetime = response_timestamp + timedelta(
            seconds=device_authorization_response.expires_in,
        )
        return device_authorization_response

    def _do_device_access_token_request(
        self,
        client: httpx.Client,
        device_auth_resp: DeviceAuthorizationResponse | None,
    ) -> None:
        """Execute the 3rd and 4th parts of the OAuth 2.0 Device Authorization Grant.

        These steps are intertwined due to necessity of user interaction. First,
        the URL self.device_authorization_endpoint_response.verification_uri_complete
        is displayed to the user. The user must interact with this URL on a
        separate device (could be just the browser on the same machine). While that
        is occurring, this method is polling the Device Access Token service of the
        OAuth 2.0 API.
        This polling, i.e., sending POST requests to the TIDAL API /token endpoint,
        either times out, fails in any network-related way, or is successful. In the
        former two cases, the attribute self.device_access_token_response takes None
        as its value. Otherwise, it takes as its value an instance of
        DeviceAccessTokenResponse.
        Data from the request response, if it is not None, is set as attribute
        on self for writing to disk. Successful retrieval of this access token
        is necessary for any further execution of tidal-wave.
        """
        data: dict[str, str] = {
            "client_id": self.client_credentials.client_id,
            "device_code": device_auth_resp.device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "scope": "r_usr+w_usr+w_sub",
        }

        seconds_remaining: int = (
            self.verification_expiration - datetime.now(tz=timezone.utc)
        ).seconds
        print(  # noqa:T201
            "\nUse this URL to sign in to your TIDAL account in a browser.",
            f"The URL expires in {seconds_remaining} seconds.",
            f"\thttps://{device_auth_resp.verification_uri_complete}",
            "",
            file=sys.stderr,
            sep="\n",
        )
        to_return: dict | None = None

        while datetime.now(tz=timezone.utc) < self.verification_expiration:
            token_response: httpx.Response = client.post(
                url=self.device_access_token_request_url,
                data=data,
                headers=self.headers,
                auth=self.client_credentials,
            )
            if not token_response.is_success:
                sleep(device_auth_resp.interval + 0.01)
                continue
            to_return = token_response.json()
            logger.info("Successfully authenticated with TIDAL.")
            break
        else:
            logger.warning("OAuth login process has timed out.")
        return to_return

    def do_device_authorization_grant(self, client: httpx.Client) -> None:
        """Request device authorization and an access token from TIDAL API."""
        device_authorization_response: DeviceAuthorizationResponse | None = (
            self._do_device_authorization_request(client=client)
        )
        if device_authorization_response is None:
            raise AuthorizationError

        device_access_token_request_response: dict | None = (
            self._do_device_access_token_request(
                client=client,
                device_auth_resp=device_authorization_response,
            )
        )

        try:
            device_access_token_response: AccessTokenResponse = (
                AccessTokenResponse.model_validate(
                    device_access_token_request_response,
                )
            )
        except ValidationError as ve:
            if device_access_token_request_response is None:
                logger.critical("TIDAL API did not respond with an access token.")
                # raise AccessTokenError from ve
                # Don't need the above traceback
                raise AccessTokenError

            logger.critical(
                "Unable to complete Authorization Grant Flow with TIDAL API.",
            )
            raise AuthorizationError from ve
        else:
            self.access_token = device_access_token_response.access_token

        self.expiration: datetime = datetime.now(tz=timezone.utc) + timedelta(
            seconds=device_access_token_response.expires_in,
        )
        # save this to disk immediately, as it DOES NOT CHANGE for a given
        # device/deviceCode
        self.refresh_token = device_access_token_response.refresh_token

    def do_refresh_access_token(self, client: httpx.Client) -> None:
        """Send a POST request to TIDAL API to refresh OAuth 2.0 access token."""
        response: httpx.Response = client.post(
            url=self.device_refresh_token_request_url,
            headers=self.headers,
            auth=httpx.BasicAuth(*self.client_credentials),
            data=self.device_refresh_token_request_data,
        )
        try:
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.critical("Could not successfully POST access token refresh request.")
            raise AuthorizationError from e

        try:
            refresh_token_response: AccessTokenRefreshResponse = (
                AccessTokenRefreshResponse.model_validate(response.json())
            )
        except ValidationError as ve:
            raise AccessTokenError from ve

        self.access_token = refresh_token_response.access_token
        self.expiration: datetime = datetime.now(tz=timezone.utc) + timedelta(
            seconds=refresh_token_response.expires_in,
        )


class AmazonFireTVDevice(TidalDevice):
    """A TIDAL client identifying as an Amazon Fire TV to TIDAL API."""

    client_credentials: ClassVar[ClientCredentials] = ClientCredentials(
        "7m7Ap0JC9j1cOM3n",
        "vRAdA108tlvkJpTsGZS8rGZ7xTlbJ0qaZ2K9saEzsgY=",
    )


class AndroidAutoDevice(TidalDevice):
    """A TIDAL client identifying as an Amazon Automotive device to TIDAL API."""

    client_credentials: ClassVar[ClientCredentials] = ClientCredentials(
        "zU4XHVVkc2tDPo4t",
        "VJKhDFqJPqvsPVNBV6ukXTJmwlvbttP7wlMlrc72se4",
    )


def main(argv: list[str] | None = None):  # noqa:D103,ANN201
    from base64 import b64decode
    if argv is None:
        argv = sys.argv
    device: AmazonFireTVDevice = AmazonFireTVDevice()
    logging.getLogger("httpx").propagate = False

    logging.basicConfig(
        format="%(asctime)s,%(msecs)03d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d:%H:%M:%S",
        level=logging.getLevelName(logging.INFO),
    )
    logger = logging.getLogger(__name__)

    device_serialization_path: Path = Path(f"{type(device).__name__}.json")
    to_include: tuple[str] = ("access_token", "expiration", "refresh_token")
    try:
        device = AmazonFireTVDevice.model_validate_json(
            device_serialization_path.read_bytes(),
        )
    except Exception:
        raise
    else:
        jwt: str = b64decode(f"""{device.access_token.split(".")[1]}==""")
    
    sys.exit(jwt)

    with httpx.Client(http2=True) as client:
        if device.access_expired:
            if device.refresh_token is None:
                device.do_device_authorization_grant(client)
            device.do_refresh_access_token(client)
            device_serialization_path.write_text(device.model_dump_json(include=to_include))


if __name__ == "__main__":
    main()
