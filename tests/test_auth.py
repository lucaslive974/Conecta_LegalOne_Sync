import base64
import json

import pytest
import requests

from source.infrastructure.legalone.auth import extract_tenant_id_from_jwt, login_legalone
from source.infrastructure.network.http_client import HTTPClient, RequestsHTTPClient


def test_extract_tenant_id_valid():
    payload = {"tenantId": "12345", "sub": "test_user"}
    payload_b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    jwt_token = f"header.{payload_b64}.signature"

    assert extract_tenant_id_from_jwt(jwt_token) == "12345"
    assert extract_tenant_id_from_jwt(f"Bearer {jwt_token}") == "12345"


def test_extract_tenant_id_invalid():
    assert extract_tenant_id_from_jwt("invalid_token") is None
    assert extract_tenant_id_from_jwt("") is None


def test_login_legalone_success(mocker):
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"token": "jwt_token_123"}'
    mock_resp.json.return_value = {"token": "jwt_token_123"}

    mock_client = mocker.MagicMock(spec=HTTPClient)
    mock_client.post.return_value = mock_resp

    res = login_legalone("user@test.com", "pass", "ACC123", http_client=mock_client)
    assert res.get("token") == "jwt_token_123"
    mock_client.post.assert_called_once()


def test_login_legalone_default_client_fallback(mocker):
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"token": "jwt_default_456"}'
    mock_resp.json.return_value = {"token": "jwt_default_456"}

    mocker.patch.object(RequestsHTTPClient, "post", return_value=mock_resp)

    res = login_legalone("user@test.com", "pass", "ACC123")
    assert res.get("token") == "jwt_default_456"


def test_login_legalone_nested_token(mocker):
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"data": {"token": "nested_jwt_abc"}}'
    mock_resp.json.return_value = {"data": {"token": "nested_jwt_abc"}}

    mock_client = mocker.MagicMock(spec=HTTPClient)
    mock_client.post.return_value = mock_resp

    res = login_legalone("user@test.com", "pass", "ACC123", http_client=mock_client)
    assert res.get("token") == "nested_jwt_abc"


def test_login_legalone_http_error(mocker):
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 401
    mock_resp.content = b'{"message": "Credenciais invalidas"}'
    mock_resp.json.return_value = {"message": "Credenciais invalidas"}

    mock_client = mocker.MagicMock(spec=HTTPClient)
    mock_client.post.return_value = mock_resp

    with pytest.raises(ValueError) as excinfo:
        login_legalone("user@test.com", "wrong", "ACC123", http_client=mock_client)

    assert "Credenciais invalidas" in str(excinfo.value)


def test_login_legalone_connection_error(mocker):
    mock_client = mocker.MagicMock(spec=HTTPClient)
    mock_client.post.side_effect = requests.RequestException("Network unreachable")

    with pytest.raises(ConnectionError) as excinfo:
        login_legalone("user@test.com", "pass", "ACC123", http_client=mock_client)

    assert "Falha de rede" in str(excinfo.value)
