from source.infrastructure.legalone.client import LegalOneClient


def test_legalone_client_headers():
    client = LegalOneClient(token="Bearer test_token_xyz", tenant_id="8888")
    assert client.session.headers["Authorization"] == "Bearer test_token_xyz"
    assert client.session.headers["x-tenant-id"] == "8888"


def test_get_processes_page(mocker):
    client = LegalOneClient(token="token123", tenant_id="8888")

    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"data": [{"id": 1}], "total": 1}}

    mock_get = mocker.patch.object(client.session, "get", return_value=mock_resp)

    res = client.get_processes_page(page=2, limit=10, search_filter="filtro")
    assert res["data"]["total"] == 1
    mock_get.assert_called_once_with(
        "https://conecta-api.legalone.com.br/api/process",
        params={"page": 2, "limit": 10, "filter": "filtro"},
        timeout=35,
    )


def test_get_process_by_publication(mocker):
    client = LegalOneClient(token="token123", tenant_id="8888")

    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"id": 10, "progresses": []}}

    mock_get = mocker.patch.object(client.session, "get", return_value=mock_resp)

    res = client.get_process_by_publication(999)
    assert res["data"]["id"] == 10
    mock_get.assert_called_once_with(
        "https://conecta-api.legalone.com.br/api/process/999",
        timeout=35,
    )
