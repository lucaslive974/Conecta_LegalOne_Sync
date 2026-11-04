import re
from typing import Any

# CNJ Mask regex: NNNNNNN-DD.AAAA.J.TR.OOOO or 20 digits raw
CNJ_PATTERN = re.compile(
    r"^\s*(\d{7})[-.]?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})\s*$"
)

JUSTICA_RAMOS: dict[str, str] = {
    "1": "Supremo Tribunal Federal",
    "2": "Conselho Nacional de Justiça",
    "3": "Superior Tribunal de Justiça",
    "4": "Justiça Federal",
    "5": "Justiça do Trabalho",
    "6": "Justiça Eleitoral",
    "7": "Justiça Militar da União",
    "8": "Justiça Estadual",
    "9": "Justiça Militar Estadual",
}

# Tribunais de Justiça Estaduais (J = 8)
TRIBUNAIS_ESTADUAIS: dict[str, tuple[str, str]] = {
    "01": ("TJAC", "Tribunal de Justiça do Acre"),
    "02": ("TJAL", "Tribunal de Justiça de Alagoas"),
    "03": ("TJAP", "Tribunal de Justiça do Amapá"),
    "04": ("TJAM", "Tribunal de Justiça do Amazonas"),
    "05": ("TJBA", "Tribunal de Justiça da Bahia"),
    "06": ("TJCE", "Tribunal de Justiça do Ceará"),
    "07": ("TJDFT", "Tribunal de Justiça do Distrito Federal e Territórios"),
    "08": ("TJES", "Tribunal de Justiça do Espírito Santo"),
    "09": ("TJGO", "Tribunal de Justiça de Goiás"),
    "10": ("TJMA", "Tribunal de Justiça do Maranhão"),
    "11": ("TJMT", "Tribunal de Justiça de Mato Grosso"),
    "12": ("TJMS", "Tribunal de Justiça de Mato Grosso do Sul"),
    "13": ("TJMG", "Tribunal de Justiça de Minas Gerais"),
    "14": ("TJPA", "Tribunal de Justiça do Pará"),
    "15": ("TJPB", "Tribunal de Justiça da Paraíba"),
    "16": ("TJPR", "Tribunal de Justiça do Paraná"),
    "17": ("TJPE", "Tribunal de Justiça de Pernambuco"),
    "18": ("TJPI", "Tribunal de Justiça do Piauí"),
    "19": ("TJRJ", "Tribunal de Justiça do Rio de Janeiro"),
    "20": ("TJRN", "Tribunal de Justiça do Rio Grande do Norte"),
    "21": ("TJRS", "Tribunal de Justiça do Rio Grande do Sul"),
    "22": ("TJRO", "Tribunal de Justiça de Rondônia"),
    "23": ("TJRR", "Tribunal de Justiça de Roraima"),
    "24": ("TJSC", "Tribunal de Justiça de Santa Catarina"),
    "25": ("TJSE", "Tribunal de Justiça de Sergipe"),
    "26": ("TJSP", "Tribunal de Justiça de São Paulo"),
    "27": ("TJTO", "Tribunal de Justiça do Tocantins"),
}

# Tribunais Regionais do Trabalho (J = 5)
TRIBUNAIS_TRABALHO: dict[str, tuple[str, str]] = {
    "01": ("TRT-1", "Tribunal Regional do Trabalho da 1ª Região (RJ)"),
    "02": ("TRT-2", "Tribunal Regional do Trabalho da 2ª Região (SP Capital)"),
    "03": ("TRT-3", "Tribunal Regional do Trabalho da 3ª Região (MG)"),
    "04": ("TRT-4", "Tribunal Regional do Trabalho da 4ª Região (RS)"),
    "05": ("TRT-5", "Tribunal Regional do Trabalho da 5ª Região (BA)"),
    "06": ("TRT-6", "Tribunal Regional do Trabalho da 6ª Região (PE)"),
    "07": ("TRT-7", "Tribunal Regional do Trabalho da 7ª Região (CE)"),
    "08": ("TRT-8", "Tribunal Regional do Trabalho da 8ª Região (PA/AP)"),
    "09": ("TRT-9", "Tribunal Regional do Trabalho da 9ª Região (PR)"),
    "10": ("TRT-10", "Tribunal Regional do Trabalho da 10ª Região (DF/TO)"),
    "11": ("TRT-11", "Tribunal Regional do Trabalho da 11ª Região (AM/RR)"),
    "12": ("TRT-12", "Tribunal Regional do Trabalho da 12ª Região (SC)"),
    "13": ("TRT-13", "Tribunal Regional do Trabalho da 13ª Região (PB)"),
    "14": ("TRT-14", "Tribunal Regional do Trabalho da 14ª Região (RO/AC)"),
    "15": ("TRT-15", "Tribunal Regional do Trabalho da 15ª Região (Campinas/SP)"),
    "16": ("TRT-16", "Tribunal Regional do Trabalho da 16ª Região (MA)"),
    "17": ("TRT-17", "Tribunal Regional do Trabalho da 17ª Região (ES)"),
    "18": ("TRT-18", "Tribunal Regional do Trabalho da 18ª Região (GO)"),
    "19": ("TRT-19", "Tribunal Regional do Trabalho da 19ª Região (AL)"),
    "20": ("TRT-20", "Tribunal Regional do Trabalho da 20ª Região (SE)"),
    "21": ("TRT-21", "Tribunal Regional do Trabalho da 21ª Região (RN)"),
    "22": ("TRT-22", "Tribunal Regional do Trabalho da 22ª Região (PI)"),
    "23": ("TRT-23", "Tribunal Regional do Trabalho da 23ª Região (MT)"),
    "24": ("TRT-24", "Tribunal Regional do Trabalho da 24ª Região (MS)"),
}

# Tribunais Regionais Federais (J = 4)
TRIBUNAIS_FEDERAIS: dict[str, tuple[str, str]] = {
    "01": ("TRF-1", "Tribunal Regional Federal da 1ª Região (DF, GO, TO, MT, BA, etc.)"),
    "02": ("TRF-2", "Tribunal Regional Federal da 2ª Região (RJ/ES)"),
    "03": ("TRF-3", "Tribunal Regional Federal da 3ª Região (SP/MS)"),
    "04": ("TRF-4", "Tribunal Regional Federal da 4ª Região (RS/SC/PR)"),
    "05": ("TRF-5", "Tribunal Regional Federal da 5ª Região (PE/CE/AL/SE/RN/PB)"),
    "06": ("TRF-6", "Tribunal Regional Federal da 6ª Região (MG)"),
}


def parse_cnj(cnj_str: str | None) -> dict[str, Any]:
    """
    Decode standardized 20-digit CNJ lawsuit number (Resolution 65/2008 CNJ).

    Format: NNNNNNN-DD.AAAA.J.TR.OOOO
    Returns structured judicial metadata or graceful fallback for non-standard formats.
    """
    if not cnj_str:
        return {
            "is_valid": False,
            "ano": "Não informado",
            "ramo": "Não informado",
            "tribunal_sigla": "N/A",
            "tribunal_nome": "Não informado",
            "origem_codigo": "N/A",
            "resumo": "Processo sem numeração",
        }

    match = CNJ_PATTERN.match(str(cnj_str))
    if not match:
        return {
            "is_valid": False,
            "ano": "Não identificado",
            "ramo": "Formato Especial / Antigo",
            "tribunal_sigla": "N/A",
            "tribunal_nome": "Numeração anterior a 2010 ou administrativa",
            "origem_codigo": "N/A",
            "resumo": "Numeração não padronizada pelo CNJ",
        }

    _, _, ano, j, tr, oooo = match.groups()

    ramo = JUSTICA_RAMOS.get(j, f"Ramo {j}")
    tribunal_sigla = f"Tribunal {tr}"
    tribunal_nome = f"Órgão Judiciário {tr}"

    if j == "8":
        sigla, nome = TRIBUNAIS_ESTADUAIS.get(tr, (f"TJ-{tr}", f"Tribunal de Justiça ({tr})"))
        tribunal_sigla = sigla
        tribunal_nome = nome
    elif j == "5":
        sigla, nome = TRIBUNAIS_TRABALHO.get(tr, (f"TRT-{tr}", f"Tribunal Regional do Trabalho ({tr})"))
        tribunal_sigla = sigla
        tribunal_nome = nome
    elif j == "4":
        sigla, nome = TRIBUNAIS_FEDERAIS.get(tr, (f"TRF-{tr}", f"Tribunal Regional Federal ({tr})"))
        tribunal_sigla = sigla
        tribunal_nome = nome
    elif j == "3":
        tribunal_sigla = "STJ"
        tribunal_nome = "Superior Tribunal de Justiça"
    elif j == "1":
        tribunal_sigla = "STF"
        tribunal_nome = "Supremo Tribunal Federal"
    elif j == "2":
        tribunal_sigla = "CNJ"
        tribunal_nome = "Conselho Nacional de Justiça"
    elif j == "6":
        tribunal_sigla = "TSE" if tr == "00" else f"TRE-{tr}"
        tribunal_nome = "Tribunal Superior Eleitoral" if tr == "00" else f"Tribunal Regional Eleitoral ({tr})"
    elif j == "7":
        tribunal_sigla = "STM"
        tribunal_nome = "Superior Tribunal Militar"

    return {
        "is_valid": True,
        "ano": ano,
        "ramo": ramo,
        "tribunal_sigla": tribunal_sigla,
        "tribunal_nome": tribunal_nome,
        "origem_codigo": oooo,
        "resumo": f"{tribunal_sigla} • {ramo} • Ajuizado em {ano}",
    }
