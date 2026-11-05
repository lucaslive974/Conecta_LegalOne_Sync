from source.domain.cnj import parse_cnj


def test_parse_cnj_state_court_tjmg():
    cnj = "5003140-58.2023.8.13.0439"
    info = parse_cnj(cnj)
    assert info["is_valid"] is True
    assert info["ano"] == "2023"
    assert info["ramo"] == "Justiça Estadual"
    assert info["tribunal_sigla"] == "TJMG"
    assert "Minas Gerais" in info["tribunal_nome"]
    assert info["origem_codigo"] == "0439"
    assert "TJMG" in info["resumo"]
    assert "2023" in info["resumo"]


def test_parse_cnj_state_court_tjsp():
    cnj = "1002345-67.2021.8.26.0100"
    info = parse_cnj(cnj)
    assert info["is_valid"] is True
    assert info["ano"] == "2021"
    assert info["ramo"] == "Justiça Estadual"
    assert info["tribunal_sigla"] == "TJSP"
    assert "São Paulo" in info["tribunal_nome"]


def test_parse_cnj_labor_court_trt3():
    cnj = "0010000-12.2024.5.03.0001"
    info = parse_cnj(cnj)
    assert info["is_valid"] is True
    assert info["ano"] == "2024"
    assert info["ramo"] == "Justiça do Trabalho"
    assert info["tribunal_sigla"] == "TRT-3"
    assert "3ª Região" in info["tribunal_nome"]


def test_parse_cnj_federal_court_trf6():
    cnj = "0001000-45.2023.4.06.0000"
    info = parse_cnj(cnj)
    assert info["is_valid"] is True
    assert info["ano"] == "2023"
    assert info["ramo"] == "Justiça Federal"
    assert info["tribunal_sigla"] == "TRF-6"
    assert "6ª Região" in info["tribunal_nome"]


def test_parse_cnj_superior_courts():
    # STJ (J=3)
    info_stj = parse_cnj("0000123-45.2022.3.00.0000")
    assert info_stj["is_valid"] is True
    assert info_stj["tribunal_sigla"] == "STJ"
    assert "Superior Tribunal de Justiça" in info_stj["tribunal_nome"]

    # STF (J=1)
    info_stf = parse_cnj("0000001-00.2020.1.00.0000")
    assert info_stf["is_valid"] is True
    assert info_stf["tribunal_sigla"] == "STF"
    assert "Supremo Tribunal Federal" in info_stf["tribunal_nome"]

    # CNJ (J=2)
    info_cnj = parse_cnj("0000001-00.2021.2.00.0000")
    assert info_cnj["is_valid"] is True
    assert info_cnj["tribunal_sigla"] == "CNJ"

    # TSE (J=6, TR=00)
    info_tse = parse_cnj("0000001-00.2022.6.00.0000")
    assert info_tse["is_valid"] is True
    assert info_tse["tribunal_sigla"] == "TSE"

    # STM (J=7)
    info_stm = parse_cnj("0000001-00.2023.7.00.0000")
    assert info_stm["is_valid"] is True
    assert info_stm["tribunal_sigla"] == "STM"


def test_parse_cnj_raw_digits():
    raw_cnj = "50031405820238130439"
    info = parse_cnj(raw_cnj)
    assert info["is_valid"] is True
    assert info["ano"] == "2023"
    assert info["tribunal_sigla"] == "TJMG"


def test_parse_cnj_invalid_and_empty():
    info_none = parse_cnj(None)
    assert info_none["is_valid"] is False
    assert info_none["tribunal_sigla"] == "N/A"
    assert info_none["ano"] == "Não informado"

    info_empty = parse_cnj("")
    assert info_empty["is_valid"] is False

    info_invalid = parse_cnj("12345/2020")
    assert info_invalid["is_valid"] is False
    assert info_invalid["ano"] == "Não identificado"
    assert info_invalid["tribunal_sigla"] == "N/A"
