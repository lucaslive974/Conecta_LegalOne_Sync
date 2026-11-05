from typing import Any

import requests

from source.infrastructure.legalone.client import LegalOneClient
from source.infrastructure.network.http_client import HTTPClient, HTTPResponse, RequestsHTTPClient
from source.infrastructure.nextcloud.client import NextcloudClient


class FakeResponse:
    def __init__(self, status_code: int = 200, json_data: Any = None, text: str = "", content: bytes = b""):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text
        self.content = content

    def json(self, **kwargs: Any) -> Any:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeHTTPClient:
    def __init__(self):
        self.headers: dict[str, str] = {}
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> HTTPResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return FakeResponse(status_code=200, json_data={"method": method, "url": url})

    def get(self, url: str, **kwargs: Any) -> HTTPResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> HTTPResponse:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> HTTPResponse:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> HTTPResponse:
        return self.request("DELETE", url, **kwargs)


def test_http_client_protocol_conformance():
    fake = FakeHTTPClient()
    assert isinstance(fake, HTTPClient)

    client = RequestsHTTPClient()
    assert isinstance(client, HTTPClient)


def test_requests_http_client_methods(mocker):
    client = RequestsHTTPClient()
    mock_session = mocker.MagicMock(spec=requests.Session)
    client._session = mock_session

    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_session.request.return_value = mock_resp

    # GET
    res_get = client.get("https://api.test/resource", params={"a": 1})
    assert res_get == mock_resp
    mock_session.request.assert_called_with("GET", "https://api.test/resource", params={"a": 1})

    # POST
    client.post("https://api.test/resource", json={"data": "val"})
    mock_session.request.assert_called_with("POST", "https://api.test/resource", json={"data": "val"})

    # PUT
    client.put("https://api.test/resource", data=b"raw")
    mock_session.request.assert_called_with("PUT", "https://api.test/resource", data=b"raw")

    # DELETE
    client.delete("https://api.test/resource")
    mock_session.request.assert_called_with("DELETE", "https://api.test/resource")


def test_requests_http_client_properties():
    client = RequestsHTTPClient(
        auth=("user", "pass"),
        verify=False,
        headers={"X-Test": "123"},
    )
    assert client.auth == ("user", "pass")
    assert client.verify is False
    assert client.headers["X-Test"] == "123"

    client.headers = {"X-New": "456"}
    assert client.headers["X-New"] == "456"

    client.auth = ("new_user", "new_pass")
    assert client.auth == ("new_user", "new_pass")

    client.verify = True
    assert client.verify is True
    assert isinstance(client.session, requests.Session)


def test_inject_fake_http_client_into_legalone():
    fake = FakeHTTPClient()
    client = LegalOneClient(token="Bearer dummy_token", tenant_id="1111", http_client=fake)

    assert client.session == fake
    assert fake.headers["Authorization"] == "Bearer dummy_token"
    assert fake.headers["x-tenant-id"] == "1111"

    client.get_processes_page(page=1, limit=10)
    assert len(fake.calls) == 1
    assert fake.calls[0]["method"] == "GET"
    assert "process" in fake.calls[0]["url"]
    assert fake.calls[0]["params"] == {"page": 1, "limit": 10, "filter": ""}


def test_inject_fake_http_client_into_nextcloud():
    fake = FakeHTTPClient()
    nc = NextcloudClient(
        base_url="https://cloud.test",
        user="test_user",
        password="app_password",
        http_client=fake,
    )

    assert nc.session == fake
    # test_connection via PROPFIND
    assert nc.test_connection() is True
    assert len(fake.calls) == 1
    assert fake.calls[0]["method"] == "PROPFIND"
