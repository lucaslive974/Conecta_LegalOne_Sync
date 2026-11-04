import os
import json
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class Database:
    """Gerencia o controle incremental e histórico de processos em SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS processes (
                    id INTEGER PRIMARY KEY,
                    id_adv_publication INTEGER,
                    numero_cnj TEXT,
                    pasta TEXT,
                    valor_causa REAL,
                    status_nome TEXT,
                    dt_hr_ultima_atualizacao TEXT,
                    dt_hr_cadastro TEXT,
                    recent_activity_date TEXT,
                    json_data TEXT,
                    last_synced_at TEXT
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS progresses (
                    id INTEGER PRIMARY KEY,
                    process_id INTEGER,
                    dt_hr_andamento TEXT,
                    str_data TEXT,
                    str_hora TEXT,
                    tipo_origem INTEGER,
                    source TEXT,
                    descricao TEXT,
                    checksum TEXT,
                    caminho_pdf TEXT,
                    created_at TEXT,
                    FOREIGN KEY(process_id) REFERENCES processes(id)
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY,
                    process_id INTEGER,
                    nome TEXT,
                    cpf_cnpj TEXT,
                    posicao TEXT,
                    is_principal BOOLEAN,
                    FOREIGN KEY(process_id) REFERENCES processes(id)
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_proc_cnj ON processes(numero_cnj)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_prog_proc ON progresses(process_id)")

    def get_process_sync_info(self, process_id: int) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT dt_hr_ultima_atualizacao, id_adv_publication FROM processes WHERE id = ?", (process_id,))
        row = cur.fetchone()
        if row:
            return {"dt_hr_ultima_atualizacao": row["dt_hr_ultima_atualizacao"], "id_adv_publication": row["id_adv_publication"]}
        return None

    def save_process(self, proc_data: Dict[str, Any], pub_id: Optional[int] = None):
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
            self.conn.execute("""
                INSERT INTO processes (
                    id, id_adv_publication, numero_cnj, pasta, valor_causa, status_nome,
                    dt_hr_ultima_atualizacao, dt_hr_cadastro, recent_activity_date,
                    json_data, last_synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    id_adv_publication=excluded.id_adv_publication,
                    numero_cnj=excluded.numero_cnj,
                    pasta=excluded.pasta,
                    valor_causa=excluded.valor_causa,
                    status_nome=excluded.status_nome,
                    dt_hr_ultima_atualizacao=excluded.dt_hr_ultima_atualizacao,
                    recent_activity_date=excluded.recent_activity_date,
                    json_data=excluded.json_data,
                    last_synced_at=excluded.last_synced_at
            """, (
                p_id, adv_pub, cnj, pasta, valor, status_nome,
                dt_atualizacao, dt_cadastro, recent_act,
                json.dumps(proc_data, ensure_ascii=False), now
            ))

            contatos = proc_data.get("contatos") or []
            for c in contatos:
                cid = c.get("id")
                agn = c.get("agnContato") or {}
                pos = c.get("posicaoEnvolvido") or {}
                self.conn.execute("""
                    INSERT OR REPLACE INTO contacts (id, process_id, nome, cpf_cnpj, posicao, is_principal)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    cid, p_id, agn.get("nome"), agn.get("cpfCnpj"),
                    pos.get("descricao"), bool(c.get("isPrincipal"))
                ))

            andamentos = proc_data.get("recentProgresses") or proc_data.get("progresses") or []
            for andam in andamentos:
                aid = andam.get("id")
                self.conn.execute("""
                    INSERT OR REPLACE INTO progresses (
                        id, process_id, dt_hr_andamento, str_data, str_hora,
                        tipo_origem, source, descricao, checksum, caminho_pdf, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    aid, p_id, andam.get("dtHrAndamento"), andam.get("strData"), andam.get("strHora"),
                    andam.get("tipoOrigem"), andam.get("source"), andam.get("descricao"),
                    andam.get("checksum"), andam.get("caminhoPDF"), andam.get("dtHrCadastro")
                ))

    def get_process_parties_summary(self, process_id: int) -> Dict[str, List[str]]:
        cur = self.conn.cursor()
        cur.execute("SELECT nome, posicao FROM contacts WHERE process_id = ?", (process_id,))
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
