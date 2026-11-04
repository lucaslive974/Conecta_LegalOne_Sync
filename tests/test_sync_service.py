from source.sync_service import extract_party_names


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
