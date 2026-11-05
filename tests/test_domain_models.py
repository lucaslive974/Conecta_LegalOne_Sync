from source.domain.cnj import parse_cnj
from source.domain.models import (
    CNJDetails,
    Lawsuit,
    Party,
    ProcessSummaryEntry,
    ProcessSyncInfo,
    Progress,
    StorageContext,
    SyncStats,
)


def test_cnj_details_properties_and_dict_access():
    details = parse_cnj("5009876-54.2024.8.13.0024")
    assert details.is_valid is True
    assert details.ano == "2024"
    assert details.ramo == "Justiça Estadual"
    assert details.tribunal_sigla == "TJMG"
    assert details["tribunal_sigla"] == "TJMG"
    assert details.get("origem_codigo") == "0024"
    assert "TJMG" in details.resumo


def test_cnj_details_invalid():
    details = parse_cnj("INVALIDO-123")
    assert details.is_valid is False
    assert details.tribunal_sigla == "N/A"
    assert details["ramo"] == "Formato Especial / Antigo"

    empty_details = parse_cnj("")
    assert empty_details.is_valid is False
    assert empty_details["tribunal_sigla"] == "N/A"


def test_party_from_dict():
    # Regular party
    p1 = Party.from_dict({"agnContato": {"nome": "Empresa Alfa"}, "posicaoEnvolvido": {"descricao": "Autor"}})
    assert p1 is not None
    assert p1.nome == "Empresa Alfa"
    assert p1.is_main_party is True

    # Internal lawyer / responsible should not be main party
    p2 = Party.from_dict({"agnContato": {"nome": "Dr. Silva"}, "posicaoEnvolvido": {"descricao": "Advogado"}})
    assert p2 is not None
    assert p2.is_main_party is False

    # Empty contact
    p3 = Party.from_dict({"agnContato": {}})
    assert p3 is None


def test_progress_from_dict():
    pr = Progress.from_dict({
        "id": 99,
        "strData": "01/11/2026",
        "strHora": "10:30",
        "source": "Diário Oficial",
        "nomeCaderno": "Judicial 1",
        "descricao": "Publicação de sentença",
    })
    assert pr.id == 99
    assert pr.data == "01/11/2026"
    assert pr.origem == "Diário Oficial"
    assert pr.caderno == "Judicial 1"
    assert pr.descricao == "Publicação de sentença"


def test_lawsuit_from_api_dict():
    raw = {
        "id": 1234,
        "numeroCNJ": "5009876-54.2024.8.13.0024",
        "pasta": "PASTA-01",
        "valorCausa": 50000.0,
        "status": {"nome": "Em Andamento"},
        "contatos": [
            {"agnContato": {"nome": "Autor Teste"}, "posicaoEnvolvido": {"descricao": "Autor"}},
            {"agnContato": {"nome": "Réu Teste"}, "posicaoEnvolvido": {"descricao": "Réu"}},
            {"agnContato": {"nome": "Dr. Advogado"}, "posicaoEnvolvido": {"descricao": "Advogado"}},
        ],
        "recentProgresses": [
            {"strData": "05/11/2026", "source": "Tribunal", "descricao": "Despacho proferido"},
        ],
    }

    lawsuit = Lawsuit.from_api_dict(raw)
    assert lawsuit.id == 1234
    assert lawsuit.cnj == "5009876-54.2024.8.13.0024"
    assert lawsuit.safe_cnj == "5009876-54.2024.8.13.0024"
    assert lawsuit.status_nome == "Em Andamento"
    assert lawsuit.main_parties == ["Autor Teste", "Réu Teste"]
    assert lawsuit.parties_label == "Autor Teste x Réu Teste"
    assert lawsuit.last_progress is not None
    assert "Despacho proferido" in lawsuit.last_progress_summary


def test_process_sync_info_dict_access():
    info = ProcessSyncInfo(dt_hr_ultima_atualizacao="2026-11-05T08:00:00", id_adv_publication=888)
    assert info.dt_hr_ultima_atualizacao == "2026-11-05T08:00:00"
    assert info["dt_hr_ultima_atualizacao"] == "2026-11-05T08:00:00"
    assert info["id_adv_publication"] == 888
    assert info.get("inexistente", "padrao") == "padrao"


def test_process_summary_entry_and_stats():
    entry = ProcessSummaryEntry(
        cnj="123",
        tribunal="TJMG",
        partes="A x B",
        ultimo_andamento="Despacho",
    )
    assert entry.cnj == "123"
    assert entry["tribunal"] == "TJMG"
    assert entry.get("partes") == "A x B"

    stats = SyncStats(total_consultados=10, novos_ou_atualizados=2, inalterados=8, erros=0)
    assert stats.total_consultados == 10
    assert stats.novos_ou_atualizados == 2

    storage = StorageContext(daily_folder="/daily", archive_folder="/archive")
    assert storage.daily_folder == "/daily"
