import pytest
import requests

from source.infrastructure.nextcloud.client import NextcloudClient


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


def test_ensure_directory(mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")
    mock_req = mocker.patch.object(nc.session, "request")
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 201
    mock_req.return_value = mock_resp

    # Empty path does nothing
    nc.ensure_directory("")
    mock_req.assert_not_called()

    # Nested path creates parents
    nc.ensure_directory("a/b/c")
    assert mock_req.call_count == 3


def test_upload_file_success(tmp_path, mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")
    local_file = tmp_path / "test.pdf"
    local_file.write_bytes(b"%PDF-1.4 test")

    mocker.patch.object(nc, "ensure_directory")
    mock_put = mocker.patch.object(nc.session, "put")
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 201
    mock_put.return_value = mock_resp

    res = nc.upload_file(str(local_file), "remote/test.pdf")
    assert "remote/test.pdf" in res
    mock_put.assert_called_once()


def test_upload_file_not_found():
    nc = NextcloudClient("https://nc.test", "user", "pass")
    with pytest.raises(FileNotFoundError):
        nc.upload_file("/non/existent/path/doc.pdf", "remote.pdf")


def test_upload_file_http_error(tmp_path, mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")
    local_file = tmp_path / "test.pdf"
    local_file.write_bytes(b"dummy")

    mocker.patch.object(nc, "ensure_directory")
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mocker.patch.object(nc.session, "put", return_value=mock_resp)

    with pytest.raises(OSError):
        nc.upload_file(str(local_file), "remote.pdf")


def test_list_subitems_success(mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")

    xml_content = b"""<?xml version="1.0" encoding="utf-8"?>
    <d:multistatus xmlns:d="DAV:">
        <d:response>
            <d:href>/remote.php/dav/files/user/pasta_alvo/</d:href>
        </d:response>
        <d:response>
            <d:href>/remote.php/dav/files/user/pasta_alvo/arquivo1.pdf</d:href>
        </d:response>
        <d:response>
            <d:href>/remote.php/dav/files/user/pasta_alvo/subpasta/</d:href>
        </d:response>
    </d:multistatus>"""

    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 207
    mock_resp.content = xml_content
    mocker.patch.object(nc.session, "request", return_value=mock_resp)

    items = nc.list_subitems("pasta_alvo")
    assert "arquivo1.pdf" in items
    assert "subpasta" in items


def test_list_subitems_error(mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 404
    mocker.patch.object(nc.session, "request", return_value=mock_resp)

    assert nc.list_subitems("inexistente") == []


def test_move_item(mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")
    mocker.patch.object(nc, "ensure_directory")

    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 201
    mocker.patch.object(nc.session, "request", return_value=mock_resp)

    assert nc.move_item("src/a.pdf", "dst/b.pdf") is True

    mock_resp.status_code = 404
    assert nc.move_item("src/a.pdf", "dst/b.pdf") is False


def test_delete_item(mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")

    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 204
    mocker.patch.object(nc.session, "delete", return_value=mock_resp)
    assert nc.delete_item("file.pdf") is True

    mock_resp.status_code = 404
    assert nc.delete_item("file.pdf") is False


def test_get_or_create_public_share_existing(mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")
    mocker.patch.object(nc, "ensure_directory")

    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ocs": {"data": [{"share_type": 3, "url": "https://nc.test/s/ACTIVE_LINK"}]}}

    mocker.patch.object(nc.session, "get", return_value=mock_resp)

    link = nc.get_or_create_public_share("pasta_teste")
    assert link == "https://nc.test/s/ACTIVE_LINK"


def test_get_or_create_public_share_creates_new(mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")
    mocker.patch.object(nc, "ensure_directory")

    # 1. GET returns no active shares
    mock_get = mocker.MagicMock()
    mock_get.status_code = 200
    mock_get.json.return_value = {"ocs": {"data": []}}
    mocker.patch.object(nc.session, "get", return_value=mock_get)

    # 2. POST creates new share
    mock_post = mocker.MagicMock()
    mock_post.status_code = 200
    mock_post.json.return_value = {"ocs": {"data": {"url": "https://nc.test/s/NEW_LINK"}}}
    mocker.patch.object(nc.session, "post", return_value=mock_post)

    link = nc.get_or_create_public_share("nova_pasta")
    assert link == "https://nc.test/s/NEW_LINK"


def test_archive_previous_daily_updates(mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")
    mocker.patch.object(nc, "list_subitems", return_value=["arquivo1.pdf", "pasta_parte"])
    mock_del = mocker.patch.object(nc, "delete_item", return_value=True)

    nc.archive_previous_daily_updates("Novos", "Arquivo")
    assert mock_del.call_count == 2
    mock_del.assert_any_call("Novos/arquivo1.pdf")
    mock_del.assert_any_call("Novos/pasta_parte")


def test_archive_previous_daily_updates_already_empty(mocker):
    nc = NextcloudClient("https://nc.test", "user", "pass")
    mocker.patch.object(nc, "list_subitems", return_value=[])
    mock_del = mocker.patch.object(nc, "delete_item", return_value=True)

    nc.archive_previous_daily_updates("Novos")
    mock_del.assert_not_called()
