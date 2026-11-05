from source.infrastructure.database.repository import Database


def test_database_lifecycle(tmp_path, sample_lawsuit_data):
    db_file = tmp_path / "test.db"
    db = Database(str(db_file))

    # Initial state: process does not exist
    info = db.get_process_sync_info(sample_lawsuit_data["id"])
    assert info is None

    # Save process
    db.save_process(sample_lawsuit_data, pub_id=sample_lawsuit_data["id_adv_publication"])

    # Query sync info
    info = db.get_process_sync_info(sample_lawsuit_data["id"])
    assert info is not None
    assert info["dt_hr_ultima_atualizacao"] == "2026-11-04 10:00:00"
    assert info["id_adv_publication"] == 555

    # Parties summary
    parties = db.get_process_parties_summary(sample_lawsuit_data["id"])
    assert "Empresa Alfa S.A." in parties["autores"]
    assert "Empresa Beta Ltda" in parties["reus"]
    assert "Dr. Advogado Interno" in parties["outros"]

    # Upsert test: update values and save again
    sample_lawsuit_data["dtHrUltimaAtualizacaoDc"] = "2026-11-05 15:30:00"
    db.save_process(sample_lawsuit_data, pub_id=777)

    updated_info = db.get_process_sync_info(sample_lawsuit_data["id"])
    assert updated_info["dt_hr_ultima_atualizacao"] == "2026-11-05 15:30:00"
    assert updated_info["id_adv_publication"] == 777

    db.close()
