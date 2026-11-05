import logging
from typing import Any, Protocol, runtime_checkable

import requests

logger = logging.getLogger(__name__)


@runtime_checkable
class HTTPResponse(Protocol):
    """Protocol for HTTP response objects."""

    @property
    def status_code(self) -> int:
        """HTTP status code."""
        ...

    @property
    def content(self) -> bytes:
        """Raw response body bytes."""
        ...

    @property
    def text(self) -> str:
        """Decoded response body as text."""
        ...

    def json(self, **kwargs: Any) -> Any:
        """Parse response body as JSON."""
        ...

    def raise_for_status(self) -> None:
        """Raise an exception if status code indicates an HTTP error."""
        ...


@runtime_checkable
class HTTPClient(Protocol):
    """Protocol defining the interface for HTTP clients."""

    headers: Any

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        auth: Any = None,
        verify: bool | None = None,
        **kwargs: Any,
    ) -> HTTPResponse:
        """Send an HTTP request with arbitrary method."""
        ...

    def get(self, url: str, **kwargs: Any) -> HTTPResponse:
        """Send a GET request."""
        ...

    def post(self, url: str, **kwargs: Any) -> HTTPResponse:
        """Send a POST request."""
        ...

    def put(self, url: str, **kwargs: Any) -> HTTPResponse:
        """Send a PUT request."""
        ...

    def delete(self, url: str, **kwargs: Any) -> HTTPResponse:
        """Send a DELETE request."""
        ...


class RequestsHTTPClient:
    """Default HTTPClient implementation backed by a requests.Session."""

    def __init__(
        self,
        session: requests.Session | None = None,
        auth: Any = None,
        verify: bool | None = None,
        headers: dict[str, str] | None = None,
    ):
        self._session = session or requests.Session()
        if auth is not None:
            self._session.auth = auth
        if verify is not None:
            self._session.verify = verify
        if headers:
            self._session.headers.update(headers)

    @property
    def session(self) -> requests.Session:
        """Access underlying requests.Session instance."""
        return self._session

    @property
    def headers(self) -> Any:
        """HTTP headers applied to subsequent requests."""
        return self._session.headers

    @headers.setter
    def headers(self, value: Any) -> None:
        self._session.headers = value

    @property
    def auth(self) -> Any:
        """Authentication configuration."""
        return self._session.auth

    @auth.setter
    def auth(self, value: Any) -> None:
        self._session.auth = value

    @property
    def verify(self) -> bool | str | None:
        """SSL verification setting."""
        return self._session.verify

    @verify.setter
    def verify(self, value: bool | str | None) -> None:
        self._session.verify = value

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        auth: Any = None,
        verify: bool | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Send an HTTP request through the underlying session."""
        req_kwargs: dict[str, Any] = {**kwargs}
        if params is not None:
            req_kwargs["params"] = params
        if data is not None:
            req_kwargs["data"] = data
        if json is not None:
            req_kwargs["json"] = json
        if headers is not None:
            req_kwargs["headers"] = headers
        if timeout is not None:
            req_kwargs["timeout"] = timeout
        if auth is not None:
            req_kwargs["auth"] = auth
        if verify is not None:
            req_kwargs["verify"] = verify

        return self._session.request(method, url, **req_kwargs)

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        """Send a GET request."""
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        """Send a POST request."""
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> requests.Response:
        """Send a PUT request."""
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> requests.Response:
        """Send a DELETE request."""
        return self.request("DELETE", url, **kwargs)
