from source.sync_service import SyncService, extract_party_names


def test_extract_party_names():
    proc = {
        "contatos": [
            {
                "posicaoEnvolvido": {"descricao": "Autor"},
                "agnContato": {"nome": "Empresa Alfa"},
            },
            {
                "posicaoEnvolvido": {"descricao": "Réu"},
                "agnContato": {"nome": "Empresa Beta"},
            },
            {
                "posicaoEnvolvido": {"descricao": "Advogado"},
                "agnContato": {"nome": "Dr. Advogado"},
            },
            {
                "posicaoEnvolvido": {"descricao": "Responsável"},
                "agnContato": {"nome": "Responsável Interno"},
            },
        ]
    }

    parties = extract_party_names(proc)
    assert parties == ["Empresa Alfa", "Empresa Beta"]
    assert "Dr. Advogado" not in parties
    assert "Responsável Interno" not in parties


def test_extract_party_names_fallback():
    proc = {"contatos": []}
    assert extract_party_names(proc) == ["Partes_Nao_Identificadas"]


def test_sync_service_dependency_injection(mock_config, tmp_path, mocker):
    mock_config.db_path = str(tmp_path / "sync_test.db")
    mock_config.temp_dir = str(tmp_path / "temp")

    mock_legalone = mocker.MagicMock()
    mock_legalone.get_processes_page.return_value = {
        "data": {
            "data": [],
            "total": 0,
        }
    }

    mock_nextcloud = mocker.MagicMock()
    mock_nextcloud.get_or_create_public_share.return_value = "https://cloud.test/s/link"

    mock_smtp = mocker.MagicMock()

    service = SyncService(
        config=mock_config,
        legalone_client=mock_legalone,
        nextcloud_client=mock_nextcloud,
        smtp_client=mock_smtp,
    )

    result = service.run_sync()

    assert result["synced"] == 0
    assert result["total"] == 0
    mock_nextcloud.ensure_directory.assert_called()
    mock_nextcloud.archive_previous_daily_updates.assert_called_once()
    mock_smtp.send_email.assert_called_once()
    service.db.close()

