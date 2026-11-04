INSERT INTO processes (
    id, id_adv_publication, numero_cnj, pasta, valor_causa, status_nome,
    dt_hr_ultima_atualizacao, dt_hr_cadastro, recent_activity_date,
    json_data, last_synced_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    id_adv_publication = excluded.id_adv_publication,
    numero_cnj = excluded.numero_cnj,
    pasta = excluded.pasta,
    valor_causa = excluded.valor_causa,
    status_nome = excluded.status_nome,
    dt_hr_ultima_atualizacao = excluded.dt_hr_ultima_atualizacao,
    recent_activity_date = excluded.recent_activity_date,
    json_data = excluded.json_data,
    last_synced_at = excluded.last_synced_at;
