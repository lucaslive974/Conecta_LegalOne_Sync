from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CNJDetails:
    """Informações decodificadas da numeração única de processo do CNJ."""

    numero_formatado: str
    ano: str
    ramo: str
    tribunal_sigla: str
    tribunal_nome: str
    origem_codigo: str = "N/A"
    resumo: str = ""
    is_valid: bool = True

    # Suporte a acesso estilo dicionário para compatibilidade com templates legados
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass(frozen=True)
class Party:
    """Envolvido ou interessado no processo judicial."""

    nome: str
    posicao: str = ""
    is_main_party: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Party | None:
        pos = (data.get("posicaoEnvolvido") or {}).get("descricao", "").strip()
        agn = data.get("agnContato") or {}
        nome = (agn.get("nome") or "").strip()
        if not nome:
            return None

        pos_lower = pos.lower()
        # Não classifica advogados ou responsáveis internos como polo principal do litígio
        is_internal = any(ign in pos_lower for ign in ["responsável", "responsavel", "advogado", "patrono"])
        is_dispute = any(
            p in pos_lower
            for p in ["autor", "réu", "reu", "exequente", "executado", "embargante", "embargado", "parte"]
        )

        is_main = is_dispute and not is_internal
        return cls(nome=nome, posicao=pos, is_main_party=is_main)

    @property
    def is_defendant(self) -> bool:
        """Indica se a parte pertence ao polo passivo (Réu, Executado, etc.)."""
        pos_lower = self.posicao.lower()
        return any(p in pos_lower for p in ["réu", "reu", "executado", "embargado", "recorrido", "parte adversa"])

    @property
    def is_plaintiff(self) -> bool:
        """Indica se a parte pertence ao polo ativo (Autor, Exequente, etc.)."""
        pos_lower = self.posicao.lower()
        return any(p in pos_lower for p in ["autor", "exequente", "embargante", "recorrente", "parte"])


@dataclass(frozen=True)
class Progress:
    """Andamento ou publicação registrado no histórico do processo."""

    id: int | None = None
    data: str = ""
    hora: str = ""
    origem: str = "Sistema Judicial"
    caderno: str | None = None
    descricao: str = ""
    tipo_origem: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Progress:
        d = data.get("strData") or (data.get("dtHrAndamento") or "")[:10]
        h = data.get("strHora") or ""
        tipo_orig = data.get("tipoOrigem")
        origem = data.get("source") or ("Diário Oficial" if tipo_orig == 1 else "Sistema Judicial")
        caderno = data.get("nomeCaderno")
        desc = (data.get("descricao") or "").strip()
        pid = data.get("id") or data.get("idAdvPublication")

        return cls(
            id=pid,
            data=d,
            hora=h,
            origem=origem,
            caderno=caderno,
            descricao=desc,
            tipo_origem=tipo_orig,
        )


@dataclass
class Lawsuit:
    """Entidade central do processo judicial (Conecta LegalOne)."""

    id: int
    cnj: str
    cnj_info: CNJDetails
    pasta: str | None = None
    valor_causa: float | None = None
    status_nome: str = "Ativo"
    data_distribuicao: str | None = None
    data_fechamento: str | None = None
    dt_hr_ultima_atualizacao: str | None = None
    id_adv_publication: int | None = None
    partes: list[Party] = field(default_factory=list)
    andamentos: list[Progress] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def safe_cnj(self) -> str:
        clean = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", self.cnj).strip()
        return clean or f"ID_{self.id}"

    @property
    def defendants(self) -> list[str]:
        """Nomes dos réus ou partes do polo passivo."""
        names = [p.nome for p in self.partes if p.is_main_party and p.is_defendant]
        if not names:
            names = [p.nome for p in self.partes if p.is_main_party and p.is_plaintiff]
        if not names:
            return ["Partes_Nao_Identificadas"]
        return sorted(set(names))

    @property
    def plaintiffs(self) -> list[str]:
        """Nomes dos autores ou partes do polo ativo."""
        return sorted({p.nome for p in self.partes if p.is_main_party and p.is_plaintiff})

    @property
    def main_parties(self) -> list[str]:
        """Partes utilizadas para organização de pastas (agrupa pelo Réu)."""
        return self.defendants

    @property
    def parties_label(self) -> str:
        plaintiffs = self.plaintiffs
        defendants = [p.nome for p in self.partes if p.is_main_party and p.is_defendant]
        if plaintiffs and defendants and plaintiffs[0] != defendants[0]:
            return f"{plaintiffs[0]} x {defendants[0]}"
        return self.defendants[0] if self.defendants else "Processo"

    @property
    def last_progress(self) -> Progress | None:
        return self.andamentos[0] if self.andamentos else None

    @property
    def last_progress_summary(self) -> str:
        last = self.last_progress
        if not last:
            return "Sem andamento recente registrado"
        d = last.data
        orig = last.origem
        desc = last.descricao[:140]
        return f"[{d} - {orig}] {desc}..."

    @classmethod
    def from_api_dict(cls, data: dict[str, Any], cnj_info: CNJDetails | None = None) -> Lawsuit:
        from source.domain.cnj import parse_cnj

        raw_id = data.get("id") or 0
        raw_cnj = data.get("numeroCNJ") or f"ID_{raw_id}"
        details = cnj_info or parse_cnj(raw_cnj)

        status_info = data.get("status") or {}
        status_nome = status_info.get("nome") if isinstance(status_info, dict) else str(status_info)

        contacts_raw = data.get("contatos") or []
        partes = []
        for c in contacts_raw:
            p = Party.from_dict(c)
            if p:
                partes.append(p)

        progresses_raw = data.get("recentProgresses") or data.get("progresses") or []
        andamentos = [Progress.from_dict(pr) for pr in progresses_raw]

        dt_atualizacao = (
            data.get("dtHrUltimaAtualizacaoDc")
            or data.get("dtHrUltimaAtualizacao")
            or data.get("dt_hr_ultima_atualizacao")
        )
        data_distribuicao = data.get("dtHrCadastro") or data.get("dataDistribuicao") or data.get("data_distribuicao")

        return cls(
            id=raw_id,
            cnj=raw_cnj,
            cnj_info=details,
            pasta=data.get("pasta"),
            valor_causa=data.get("valorCausa"),
            status_nome=status_nome or "Ativo",
            data_distribuicao=data_distribuicao,
            data_fechamento=data.get("dataFechamento"),
            dt_hr_ultima_atualizacao=dt_atualizacao,
            id_adv_publication=data.get("id_adv_publication"),
            partes=partes,
            andamentos=andamentos,
            raw_data=data,
        )


@dataclass(frozen=True)
class ProcessSyncInfo:
    """Informações para validação de sincronização incremental no banco de dados."""

    dt_hr_ultima_atualizacao: str | None
    id_adv_publication: int | None

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass(frozen=True)
class ProcessSummaryEntry:
    """Linha sumarizada de um processo para exibição no relatório diário."""

    cnj: str
    tribunal: str
    partes: str
    ultimo_andamento: str
    pasta: str = ""
    ramo_justica: str = ""
    valor_causa: str = ""
    status: str = ""
    data_atualizacao: str = ""

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass
class SyncStats:
    """Métricas consolidadas de uma rodada de sincronização."""

    total_consultados: int = 0
    novos_ou_atualizados: int = 0
    inalterados: int = 0
    erros: int = 0


@dataclass(frozen=True)
class StorageContext:
    """Caminhos de persistência e links públicos no Nextcloud."""

    daily_folder: str
    archive_folder: str
    magic_link_daily: str | None = None
    magic_link_archive: str | None = None
