import pytest
import requests

from source.nextcloud_client import NextcloudClient


def test_nextcloud_test_connection_success(mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200

    mocker.patch.object(nc.session, "request", return_value=mock_resp)
    assert nc.test_connection() is True


def test_nextcloud_test_connection_auth_error(mocker):
    nc = NextcloudClient("https://nc.test", "user", "wrong_pass")
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 401

    mocker.patch.object(nc.session, "request", return_value=mock_resp)
    with pytest.raises(PermissionError):
        nc.test_connection()


def test_nextcloud_test_connection_network_error(mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")
    mocker.patch.object(nc.session, "request", side_effect=requests.RequestException("Unreachable"))

    with pytest.raises(ConnectionError):
        nc.test_connection()


def test_nextcloud_exists(mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")

    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 207
    mocker.patch.object(nc.session, "request", return_value=mock_resp)
    assert nc.exists("pasta/arquivo.pdf") is True

    mock_resp.status_code = 404
    assert nc.exists("pasta/arquivo_inexistente.pdf") is False


def test_get_or_create_public_share_existing(mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")
    mocker.patch.object(nc, "ensure_directory")

    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "ocs": {"data": [{"share_type": 3, "url": "https://nc.test/s/ACTIVE_LINK"}]}
    }

    mocker.patch.object(nc.session, "get", return_value=mock_resp)

    link = nc.get_or_create_public_share("pasta_teste")
    assert link == "https://nc.test/s/ACTIVE_LINK"
