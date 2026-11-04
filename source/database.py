import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

SQL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql")


def _read_sql(filename: str) -> str:
    path = os.path.join(SQL_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return f.read()


SQL_SCHEMA = _read_sql("schema.sql")
SQL_GET_SYNC_INFO = _read_sql("get_process_sync_info.sql")
SQL_UPSERT_PROCESS = _read_sql("upsert_process.sql")
SQL_UPSERT_CONTACT = _read_sql("upsert_contact.sql")
SQL_UPSERT_PROGRESS = _read_sql("upsert_progress.sql")
SQL_GET_PARTIES_SUMMARY = _read_sql("get_parties_summary.sql")


class Database:
    """Manage incremental tracking and lawsuit history in SQLite using decoupled SQL files."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self):
        """Execute DDL script to create tables and indexes."""
        with self.conn:
            self.conn.executescript(SQL_SCHEMA)

    def get_process_sync_info(self, process_id: int) -> dict[str, Any] | None:
        cur = self.conn.cursor()
        cur.execute(SQL_GET_SYNC_INFO, (process_id,))
        row = cur.fetchone()
        if row:
            return {
                "dt_hr_ultima_atualizacao": row["dt_hr_ultima_atualizacao"],
                "id_adv_publication": row["id_adv_publication"]
            }
        return None

    def save_process(self, proc_data: dict[str, Any], pub_id: int | None = None):
        p_id = proc_data.get("id")
        adv_pub = pub_id or proc_data.get("id_adv_publication")
        cnj = proc_data.get("numeroCNJ")
        pasta = proc_data.get("pasta")
        valor = proc_data.get("valorCausa")
        status_info = proc_data.get("status") or {}
        status_nome = status_info.get("nome") if isinstance(status_info, dict) else str(status_info)
        dt_atualizacao = proc_data.get("dtHrUltimaAtualizacaoDc")
        dt_cadastro = proc_data.get("dtHrCadastro")
        recent_act = proc_data.get("recentActivityDate")
        now = datetime.now().isoformat()

        with self.conn:
            self.conn.execute(SQL_UPSERT_PROCESS, (
                p_id, adv_pub, cnj, pasta, valor, status_nome,
                dt_atualizacao, dt_cadastro, recent_act,
                json.dumps(proc_data, ensure_ascii=False), now
            ))

            contatos = proc_data.get("contatos") or []
            for c in contatos:
                cid = c.get("id")
                agn = c.get("agnContato") or {}
                pos = c.get("posicaoEnvolvido") or {}
                self.conn.execute(SQL_UPSERT_CONTACT, (
                    cid, p_id, agn.get("nome"), agn.get("cpfCnpj"),
                    pos.get("descricao"), bool(c.get("isPrincipal"))
                ))

            andamentos = proc_data.get("recentProgresses") or proc_data.get("progresses") or []
            for andam in andamentos:
                aid = andam.get("id")
                self.conn.execute(SQL_UPSERT_PROGRESS, (
                    aid, p_id, andam.get("dtHrAndamento"), andam.get("strData"), andam.get("strHora"),
                    andam.get("tipoOrigem"), andam.get("source"), andam.get("descricao"),
                    andam.get("checksum"), andam.get("caminhoPDF"), andam.get("dtHrCadastro")
                ))

    def get_process_parties_summary(self, process_id: int) -> dict[str, list[str]]:
        cur = self.conn.cursor()
        cur.execute(SQL_GET_PARTIES_SUMMARY, (process_id,))
        rows = cur.fetchall()
        autores = []
        reus = []
        outros = []
        for r in rows:
            pos = (r["posicao"] or "").lower()
            nome = r["nome"] or ""
            if any(p in pos for p in ["autor", "exequente", "embargante", "requerente"]):
                autores.append(nome)
            elif any(p in pos for p in ["réu", "reu", "executado", "embargado", "requerido"]):
                reus.append(nome)
            else:
                outros.append(nome)
        return {"autores": autores, "reus": reus, "outros": outros}

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
