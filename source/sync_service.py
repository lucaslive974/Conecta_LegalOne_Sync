import os
import json
import shutil
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

from source.config import AppConfig
from source.auth import login_legalone
from source.client import LegalOneClient
from source.database import Database
from source.document_generator import DocumentGenerator, sanitize_filename
from source.nextcloud_client import NextcloudClient
from source.notifier import send_admin_alert, send_daily_summary

logger = logging.getLogger(__name__)


def extract_party_names(proc: Dict[str, Any]) -> List[str]:
    """Extrai os nomes dos autores/réus principais ou retorna padrão."""
    contatos = proc.get("contatos") or []
    parties = set()
    for c in contatos:
        pos = (c.get("posicaoEnvolvido") or {}).get("descricao", "").lower()
        agn = c.get("agnContato") or {}
        nome = agn.get("nome")
        if nome and any(p in pos for p in ["autor", "réu", "reu", "exequente", "executado", "embargante", "embargado"]):
            parties.add(nome)

    if not parties:
        return ["Partes_Nao_Identificadas"]
    return sorted(list(parties))


class SyncService:
    """Orquestrador do ciclo completo de sincronização, geração de relatórios e espelhamento."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.db = Database(config.db_path)
        self.doc_generator = DocumentGenerator(config.temp_dir)
        self.local_storage_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "Processos"
        )
        os.makedirs(self.local_storage_dir, exist_ok=True)

    def run_sync(self) -> Dict[str, Any]:
        """
        Executa o fluxo completo diário:
        1. Login no LegalOne (com alerta em caso de falha)
        2. Inicialização do Nextcloud (preparação de pastas rotativas e arquivo permanente)
        3. Rotação diária: Move itens anteriores de 'Novos_e_Atualizados' para 'Arquivo_Geral'
        4. Geração/Obtenção do Magic Link público para a pasta rotativa do dia
        5. Varredura incremental dos processos
        6. Geração de DOCX + PDF
        7. Salvamento na cópia local e upload para Arquivo Geral + Pasta do Dia
        8. Envio de e-mail com relatório diário e Magic Link público
        """
        logger.info("==================================================")
        logger.info("Iniciando rotina de sincronização Conecta LegalOne")
        logger.info("Data/Hora: %s", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        logger.info("==================================================")

        # 1. Login no LegalOne
        try:
            logger.info("Autenticando no Conecta LegalOne com e-mail: %s...", self.config.legalone_email)
            auth_data = login_legalone(
                email=self.config.legalone_email,
                password=self.config.legalone_password,
                access_code=self.config.legalone_access_code,
                base_url=self.config.legalone_base_url
            )
            token = auth_data.get("token") or auth_data.get("accessToken") or auth_data.get("access_token")
            if not token:
                raise ValueError("Nenhum token retornado pela API do LegalOne.")
        except Exception as e:
            err_msg = f"Falha ao realizar login no LegalOne:\n{str(e)}"
            logger.error(err_msg)
            try:
                send_admin_alert(
                    config=self.config,
                    subject_title="Falha de Autenticação LegalOne",
                    error_message=str(e),
                    context_details="O processo não pôde iniciar porque as credenciais foram rejeitadas ou o serviço está inacessível."
                )
            except Exception as mail_err:
                logger.error("Falha secundária ao enviar e-mail de alerta: %s", mail_err)
            raise

        # 2. Inicialização Nextcloud
        nc_client = NextcloudClient(
            base_url=self.config.nextcloud_url,
            user=self.config.nextcloud_user,
            password=self.config.nextcloud_password,
            verify_ssl=self.config.nextcloud_verify_ssl
        )

        daily_folder = f"{self.config.nextcloud_remote_dir}/Novos_e_Atualizados"
        archive_folder = f"{self.config.nextcloud_remote_dir}/Arquivo_Geral"

        nc_client.ensure_directory(daily_folder)
        nc_client.ensure_directory(archive_folder)

        # 3. Rotação: arquiva os itens da execução anterior e limpa a pasta rotativa
        logger.info("Verificando rotação da pasta diária '%s'...", daily_folder)
        try:
            nc_client.archive_previous_daily_updates(daily_folder, archive_folder)
        except Exception as rot_err:
            logger.warning("Aviso na rotação de arquivos do Nextcloud: %s", rot_err)

        # 4. Obtém ou cria o Magic Link público para a pasta rotativa diária
        magic_link = None
        try:
            magic_link = nc_client.get_or_create_public_share(daily_folder)
            logger.info("Magic Link público do Nextcloud: %s", magic_link)
        except Exception as link_err:
            logger.warning("Não foi possível gerar Magic Link público: %s", link_err)

        # 5. Inicializa cliente LegalOne
        client = LegalOneClient(
            token=token,
            tenant_id=self.config.legalone_tenant_id,
            base_url=self.config.legalone_base_url
        )

        page = 1
        limit = self.config.page_limit
        max_pages = self.config.max_pages
        total_synced = 0
        total_skipped = 0
        processed_count = 0
        total_items = 0
        updated_processes_summary = []

        logger.info("Iniciando consulta paginada de processos...")

        while True:
            if max_pages and page > max_pages:
                logger.info("Limite de %s páginas atingido.", max_pages)
                break

            logger.info("Buscando página %s (limite por página: %s)...", page, limit)
            try:
                res = client.get_processes_page(page=page, limit=limit)
            except Exception as e:
                logger.error("Erro na busca da página %s: %s", page, e)
                break

            data_field = res.get("data") or {}
            process_list = data_field.get("data") or []
            total_items = data_field.get("total", len(process_list))

            if not process_list:
                logger.info("Fim da paginação de processos.")
                break

            logger.info("Página %s: %s processos encontrados (Total geral: %s)", page, len(process_list), total_items)

            for item in process_list:
                processed_count += 1
                p_id = item.get("id")
                pub_id = item.get("id_adv_publication")
                cnj = item.get("numeroCNJ") or f"ID_{p_id}"
                api_updated_at = item.get("dtHrUltimaAtualizacaoDc")

                db_info = self.db.get_process_sync_info(p_id)
                is_changed = True

                if db_info and db_info["dt_hr_ultima_atualizacao"] == api_updated_at and db_info["id_adv_publication"] == pub_id:
                    is_changed = False

                if not is_changed:
                    # Verifica integridade da cópia local e do arquivo permanente no Nextcloud
                    safe_cnj = sanitize_filename(cnj)
                    parties = extract_party_names(item)
                    first_party = sanitize_filename(parties[0])
                    local_proc_folder = os.path.join(self.local_storage_dir, first_party, f"Processo Numero {safe_cnj}")
                    local_docx = os.path.join(local_proc_folder, f"{safe_cnj}_Relatorio.docx")
                    local_pdf = os.path.join(local_proc_folder, f"{safe_cnj}_Relatorio.pdf")
                    remote_archive_proc_folder = f"{archive_folder}/{first_party}/Processo Numero {safe_cnj}"

                    local_ok = os.path.exists(local_docx) and os.path.exists(local_pdf)
                    remote_ok = nc_client.exists(remote_archive_proc_folder) if local_ok else False

                    if local_ok and remote_ok:
                        total_skipped += 1
                        logger.debug("(%s/%s) Sem alterações e espelhamento íntegro no Nextcloud: %s", processed_count, total_items, cnj)
                        continue
                    elif local_ok and not remote_ok:
                        logger.info("Detectada remoção remota no Nextcloud para o processo %s. Reenviando cópia local...", cnj)
                        try:
                            nc_client.upload_file(local_docx, f"{remote_archive_proc_folder}/{safe_cnj}_Relatorio.docx")
                            if os.path.exists(local_pdf):
                                nc_client.upload_file(local_pdf, f"{remote_archive_proc_folder}/{safe_cnj}_Relatorio.pdf")
                            total_skipped += 1
                            continue
                        except Exception as sync_err:
                            logger.error("Erro ao restabelecer arquivos no Nextcloud para %s: %s", cnj, sync_err)
                    else:
                        logger.info("Processo sem alteração na API mas com cópia ausente em disco. Recriando: %s", cnj)

                # Busca detalhes com publicações e andamentos atualizados
                proc_full = item
                if pub_id:
                    try:
                        logger.debug("Baixando andamentos detalhados da publicação %s...", pub_id)
                        det = client.get_process_by_publication(pub_id)
                        proc_full = det.get("data", det)
                    except Exception as e:
                        logger.warning("Não foi possível obter detalhes da pub %s: %s", pub_id, e)

                # Salva no banco SQLite interno
                self.db.save_process(proc_full, pub_id=pub_id)

                # Gera documentos (DOCX + PDF)
                safe_cnj = sanitize_filename(cnj)
                docx_tmp, pdf_tmp = self.doc_generator.render_process_documents(proc_full, base_name=f"{safe_cnj}_Relatorio")

                # Salva na cópia local e espelha no Nextcloud (Arquivo Geral + Pasta Rotativa Diária)
                parties = extract_party_names(proc_full)
                for party in parties:
                    safe_party = sanitize_filename(party)
                    local_folder = os.path.join(self.local_storage_dir, safe_party, f"Processo Numero {safe_cnj}")
                    os.makedirs(local_folder, exist_ok=True)

                    local_docx = os.path.join(local_folder, f"{safe_cnj}_Relatorio.docx")
                    shutil.copy2(docx_tmp, local_docx)

                    local_pdf = None
                    if pdf_tmp and os.path.exists(pdf_tmp):
                        local_pdf = os.path.join(local_folder, f"{safe_cnj}_Relatorio.pdf")
                        shutil.copy2(pdf_tmp, local_pdf)

                    try:
                        # 1. Envia para o Arquivo Geral permanente
                        remote_archive = f"{archive_folder}/{safe_party}/Processo Numero {safe_cnj}"
                        nc_client.upload_file(local_docx, f"{remote_archive}/{safe_cnj}_Relatorio.docx")
                        if local_pdf and os.path.exists(local_pdf):
                            nc_client.upload_file(local_pdf, f"{remote_archive}/{safe_cnj}_Relatorio.pdf")

                        # 2. Envia para a Pasta Rotativa Diária (alimentando o Magic Link)
                        remote_daily = f"{daily_folder}/{safe_party} - Processo {safe_cnj}"
                        nc_client.upload_file(local_docx, f"{remote_daily}/{safe_cnj}_Relatorio.docx")
                        if local_pdf and os.path.exists(local_pdf):
                            nc_client.upload_file(local_pdf, f"{remote_daily}/{safe_cnj}_Relatorio.pdf")
                    except Exception as upload_err:
                        logger.error("Erro no espelhamento do processo %s para o Nextcloud: %s", cnj, upload_err)
                        try:
                            send_admin_alert(
                                config=self.config,
                                subject_title="Erro de Upload no Nextcloud",
                                error_message=f"Falha ao enviar arquivos do processo {cnj} para o Nextcloud:\n{upload_err}",
                                context_details=f"Destino remoto: {daily_folder}"
                            )
                        except Exception:
                            pass

                # Remove temporários
                try:
                    if os.path.exists(docx_tmp):
                        os.remove(docx_tmp)
                    if pdf_tmp and os.path.exists(pdf_tmp):
                        os.remove(pdf_tmp)
                except Exception:
                    pass

                total_synced += 1

                # Coleta resumo para o e-mail diário
                andamentos = proc_full.get("recentProgresses") or proc_full.get("progresses") or []
                ultimo_txt = "Sem andamento recente registrado"
                if andamentos:
                    last_a = andamentos[0]
                    d = last_a.get("strData") or (last_a.get("dtHrAndamento") or "")[:10]
                    orig = last_a.get("source") or "Diário"
                    desc = (last_a.get("descricao") or "")[:140]
                    ultimo_txt = f"[{d} - {orig}] {desc}..."

                updated_processes_summary.append({
                    "cnj": cnj,
                    "partes": ", ".join(parties[:2]),
                    "ultimo_andamento": ultimo_txt
                })

            if page * limit >= total_items:
                logger.info("Todos os registros do LegalOne foram percorridos.")
                break

            page += 1

        stats = {
            "synced": total_synced,
            "skipped": total_skipped,
            "total": total_items
        }

        logger.info("Sincronização concluída com sucesso! Atualizados: %s | Inalterados: %s | Total: %s", total_synced, total_skipped, total_items)

        # 8. Notifica os usuários via e-mail com o Magic Link
        try:
            logger.info("Enviando relatório diário por e-mail para: %s...", self.config.notification_emails)
            send_daily_summary(
                config=self.config,
                stats=stats,
                updated_items=updated_processes_summary,
                nextcloud_folder=self.config.nextcloud_remote_dir,
                magic_link=magic_link
            )
        except Exception as mail_err:
            logger.error("Erro ao enviar e-mail diário de resumo: %s", mail_err)

        return stats
