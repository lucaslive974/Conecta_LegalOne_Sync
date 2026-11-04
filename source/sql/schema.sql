-- Tabela principal de processos jurídicos
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
);

-- Tabela de andamentos e publicações
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
);

-- Tabela de partes e envolvidos
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY,
    process_id INTEGER,
    nome TEXT,
    cpf_cnpj TEXT,
    posicao TEXT,
    is_principal BOOLEAN,
    FOREIGN KEY(process_id) REFERENCES processes(id)
);

-- Índices de performance
CREATE INDEX IF NOT EXISTS idx_proc_cnj ON processes(numero_cnj);
CREATE INDEX IF NOT EXISTS idx_prog_proc ON progresses(process_id);
