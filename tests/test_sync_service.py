import os

import pytest

from source.sync_service import (
    NextcloudStorageContext,
    SyncService,
    build_process_summary_entry,
    extract_party_names,
    format_last_progress_summary,
    format_parties_label,
)


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


def test_format_parties_label():
    assert format_parties_label(["Autor", "Réu"]) == "Autor x Réu"
    assert format_parties_label(["Autor Único"]) == "Autor Único"
    assert format_parties_label([]) == "Processo"


def test_format_last_progress_summary():
    # Empty case
    assert format_last_progress_summary({}) == "Sem andamento recente registrado"

    # Valid progress case
    proc = {
        "recentProgresses": [
            {
                "strData": "15/10/2026",
                "source": "DJEN",
                "descricao": "Despacho proferido pelo magistrado intimando as partes para alegações.",
            }
        ]
    }
    summary = format_last_progress_summary(proc)
    assert "[15/10/2026 - DJEN]" in summary
    assert "Despacho proferido" in summary


def test_build_process_summary_entry():
    proc = {
        "recentProgresses": [
            {"strData": "01/01/2026", "source": "Diário", "descricao": "Publicação de sentença"}
        ]
    }
    cnj = "5003140-58.2023.8.13.0439"
    parties = ["Autor Teste", "Réu Teste"]

    item = build_process_summary_entry(proc, cnj, parties)
    assert item["cnj"] == cnj
    assert item["tribunal"] == "TJMG"
    assert item["partes"] == "Autor Teste, Réu Teste"
    assert "Publicação de sentença" in item["ultimo_andamento"]


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


def test_init_nextcloud_storage(mock_config, tmp_path, mocker):
    mock_config.db_path = str(tmp_path / "storage_test.db")
    mock_nc = mocker.MagicMock()
    mock_nc.get_or_create_public_share.side_effect = ["https://cloud/daily", "https://cloud/archive"]

    service = SyncService(config=mock_config, nextcloud_client=mock_nc)
    storage = service._init_nextcloud_storage(mock_nc)

    assert isinstance(storage, NextcloudStorageContext)
    assert storage.magic_link_daily == "https://cloud/daily"
    assert storage.magic_link_archive == "https://cloud/archive"
    assert mock_nc.ensure_directory.call_count == 2
    mock_nc.archive_previous_daily_updates.assert_called_once()
    service.db.close()


def test_fetch_process_details(mock_config, tmp_path, mocker):
    mock_config.db_path = str(tmp_path / "details_test.db")
    service = SyncService(config=mock_config)

    # Without pub_id: returns item as-is
    assert service._fetch_process_details(mocker.MagicMock(), {"id": 1}) == {"id": 1}

    # With pub_id: calls get_process_by_publication
    mock_client = mocker.MagicMock()
    mock_client.get_process_by_publication.return_value = {"data": {"id": 2, "details": True}}
    res = service._fetch_process_details(mock_client, {"id": 2, "id_adv_publication": 999})
    assert res == {"id": 2, "details": True}
    service.db.close()


def test_is_process_up_to_date(mock_config, tmp_path, mocker):
    mock_config.db_path = str(tmp_path / "uptodate_test.db")
    service = SyncService(config=mock_config)
    service.local_storage_dir = str(tmp_path / "storage")

    # 1. Not in DB -> Not up to date
    mock_nc = mocker.MagicMock()
    item = {"id": 10, "dtHrUltimaAtualizacaoDc": "2026-01-01", "id_adv_publication": 100}
    assert service._is_process_up_to_date(item, "ParteA", "CNJ10", "/archive", mock_nc) is False

    # 2. In DB with same timestamps and files exist locally and remotely -> Up to date
    service.db.save_process(item, pub_id=100)
    party_folder = tmp_path / "storage" / "ParteA"
    os.makedirs(party_folder, exist_ok=True)
    local_pdf = party_folder / "CNJ10_Relatorio.pdf"
    local_pdf.write_text("dummy")

    mock_nc.exists.return_value = True
    assert service._is_process_up_to_date(item, "ParteA", "CNJ10", "/archive", mock_nc) is True

    # 3. In DB with same timestamp, local file exists, but remote missing -> uploads and heals
    mock_nc.exists.return_value = False
    assert service._is_process_up_to_date(item, "ParteA", "CNJ10", "/archive", mock_nc) is True
    mock_nc.upload_file.assert_called_once()

    service.db.close()


def test_init_legalone_client_failure(mock_config, tmp_path, mocker):
    mock_config.db_path = str(tmp_path / "fail_auth.db")
    mock_smtp = mocker.MagicMock()
    service = SyncService(config=mock_config, smtp_client=mock_smtp)

    mocker.patch("source.sync_service.login_legalone", side_effect=Exception("Auth rejected"))

    with pytest.raises(Exception) as excinfo:
        service._init_legalone_client()

    assert "Auth rejected" in str(excinfo.value)
    mock_smtp.send_email.assert_called_once()
    service.db.close()


def test_generate_and_store_reports(mock_config, tmp_path, mocker):
    mock_config.db_path = str(tmp_path / "reports_test.db")
    service = SyncService(config=mock_config)
    service.local_storage_dir = str(tmp_path / "storage")

    # Create dummy temp docx and pdf files
    temp_docx = tmp_path / "tmp.docx"
    temp_docx.write_text("docx content")
    temp_pdf = tmp_path / "tmp.pdf"
    temp_pdf.write_text("pdf content")

    mocker.patch.object(service.doc_generator, "render_process_documents", return_value=(str(temp_docx), str(temp_pdf)))
    mock_nc = mocker.MagicMock()

    proc = {"id": 123, "numeroCNJ": "5003140-58.2023.8.13.0439"}
    parties = ["Empresa Alfa", "Empresa Beta"]

    ok = service._generate_and_store_reports(
        proc_full=proc,
        safe_cnj="5003140_58_2023_8_13_0439",
        parties=parties,
        daily_folder="/Novos",
        archive_folder="/Arquivo",
        nc_client=mock_nc,
    )

    assert ok is True
    # Verify local files exist in both party folders
    for party in parties:
        party_folder = tmp_path / "storage" / party
        assert os.path.exists(party_folder / "5003140_58_2023_8_13_0439_Relatorio.pdf")
        assert os.path.exists(party_folder / "5003140_58_2023_8_13_0439_Relatorio.docx")

    # Uploads: 2 in archive (1 per party) + 1 in daily
    assert mock_nc.upload_file.call_count == 3
    service.db.close()


def test_scan_lawsuit_pages_with_updates(mock_config, tmp_path, mocker):
    mock_config.db_path = str(tmp_path / "scan_test.db")
    mock_config.page_limit = 2
    mock_config.max_pages = 1

    service = SyncService(config=mock_config)
    mock_client = mocker.MagicMock()
    mock_client.get_processes_page.return_value = {
        "data": {
            "data": [
                {
                    "id": 999,
                    "numeroCNJ": "5003140-58.2023.8.13.0439",
                    "id_adv_publication": 888,
                    "contatos": [{"posicaoEnvolvido": {"descricao": "Autor"}, "agnContato": {"nome": "Autor Teste"}}],
                }
            ],
            "total": 1,
        }
    }

    mock_nc = mocker.MagicMock()
    storage = NextcloudStorageContext(daily_folder="/daily", archive_folder="/archive")

    # Mock lawsuit generation
    mocker.patch.object(service, "_is_process_up_to_date", return_value=False)
    mocker.patch.object(service, "_fetch_process_details", return_value={
        "id": 999,
        "numeroCNJ": "5003140-58.2023.8.13.0439",
        "recentProgresses": [{"strData": "01/01/2026", "descricao": "Movimentacao"}],
        "contatos": [{"posicaoEnvolvido": {"descricao": "Autor"}, "agnContato": {"nome": "Autor Teste"}}],
    })
    mocker.patch.object(service, "_generate_and_store_reports", return_value=True)

    stats, summary_items = service._scan_lawsuit_pages(mock_client, mock_nc, storage)

    assert stats["synced"] == 1
    assert stats["skipped"] == 0
    assert stats["total"] == 1
    assert len(summary_items) == 1
    assert summary_items[0]["cnj"] == "5003140-58.2023.8.13.0439"
    service.db.close()

