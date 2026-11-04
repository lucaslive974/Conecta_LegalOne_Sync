INSERT OR REPLACE INTO progresses (
    id, process_id, dt_hr_andamento, str_data, str_hora,
    tipo_origem, source, descricao, checksum, caminho_pdf, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
