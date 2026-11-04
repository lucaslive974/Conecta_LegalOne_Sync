import logging
import os
import shutil
from datetime import datetime
from typing import Any

from source.auth import login_legalone
from source.client import LegalOneClient
from source.config import AppConfig
from source.database import Database
from source.document_generator import DocumentGenerator, sanitize_filename
from source.nextcloud_client import NextcloudClient
from source.notifier import send_admin_alert, send_daily_summary

logger = logging.getLogger(__name__)


def extract_party_names(proc: dict[str, Any]) -> list[str]:
    """
    Extract main plaintiff and defendant party names.
    Deliberately ignores 'Responsável' or 'Advogado' contacts to prevent
    office-wide lawsuits from being duplicated under internal lawyer folders.
    """
    contatos = proc.get("contatos") or []
    parties = set()
    for c in contatos:
        pos = (c.get("posicaoEnvolvido") or {}).get("descricao", "").lower()
        agn = c.get("agnContato") or {}
        nome = agn.get("nome")
        if not nome:
            continue
        # Do not add internal lawyers or representatives as a main dispute party
        if any(ign in pos for ign in ["responsável", "responsavel", "advogado", "patrono"]):
            continue
        if any(p in pos for p in ["autor", "réu", "reu", "exequente", "executado", "embargante", "embargado", "parte"]):
            parties.add(nome)

    if not parties:
        return ["Partes_Nao_Identificadas"]
    return sorted(parties)


class SyncService:
    """Orchestrator for synchronization lifecycle, report generation, and mirroring."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.db = Database(config.db_path)
        self.doc_generator = DocumentGenerator(config.temp_dir)
        self.local_storage_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "Processos"
        )
        os.makedirs(self.local_storage_dir, exist_ok=True)

    def run_sync(self) -> dict[str, Any]:
        """
        Execute full daily workflow:
        1. LegalOne login (with alert on failure)
        2. Nextcloud initialization (prepare rotating and permanent archive folders)
        3. Daily rotation: Move previous items from 'Novos_e_Atualizados' to 'Arquivo_Geral'
        4. Generate/obtain public Magic Links for rotating and archive folders
        5. Incremental scan of lawsuits
        6. Generate DOCX reports and render to PDF
        7. Save local backup and upload EXCLUSIVELY PDF to Nextcloud
        8. Send daily summary email with public Magic Links
        """
        logger.info("==================================================")
        logger.info("Iniciando rotina de sincronização Conecta LegalOne")
        logger.info("Data/Hora: %s", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        logger.info("==================================================")

        # 1. LegalOne login
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

        # 2. Nextcloud initialization
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

        # 3. Rotation: archive previous execution items and clear daily folder
        logger.info("Verificando rotação da pasta diária '%s'...", daily_folder)
        try:
            nc_client.archive_previous_daily_updates(daily_folder, archive_folder)
        except Exception as rot_err:
            logger.warning("Aviso na rotação de arquivos do Nextcloud: %s", rot_err)

        # 4. Obtain or create public Magic Links (Daily folder and General Archive)
        magic_link_daily = None
        magic_link_archive = None
        try:
            magic_link_daily = nc_client.get_or_create_public_share(daily_folder)
            magic_link_archive = nc_client.get_or_create_public_share(archive_folder)
            logger.info("Magic Link (Processos do Dia): %s", magic_link_daily)
            logger.info("Magic Link (Acervo Geral): %s", magic_link_archive)
        except Exception as link_err:
            logger.warning("Não foi possível gerar Magic Links públicos: %s", link_err)

        # 5. Initialize LegalOne client
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

                safe_cnj = sanitize_filename(cnj)
                parties = extract_party_names(item)
                first_party = sanitize_filename(parties[0])

                if not is_changed:
                    # Verify local file and remote Nextcloud PDF integrity
                    local_proc_folder = os.path.join(self.local_storage_dir, first_party)
                    local_pdf = os.path.join(local_proc_folder, f"{safe_cnj}_Relatorio.pdf")
                    remote_archive_pdf = f"{archive_folder}/{first_party}/{safe_cnj}_Relatorio.pdf"

                    local_ok = os.path.exists(local_pdf)
                    remote_ok = nc_client.exists(remote_archive_pdf) if local_ok else False

                    if local_ok and remote_ok:
                        total_skipped += 1
                        logger.debug("(%s/%s) Sem alterações e PDF íntegro no Nextcloud: %s", processed_count, total_items, cnj)
                        continue
                    elif local_ok and not remote_ok:
                        logger.info("Detectada ausência do PDF no Nextcloud para %s. Reenviando cópia local...", cnj)
                        try:
                            nc_client.upload_file(local_pdf, remote_archive_pdf)
                            total_skipped += 1
                            continue
                        except Exception as sync_err:
                            logger.error("Erro ao restabelecer PDF no Nextcloud para %s: %s", cnj, sync_err)
                    else:
                        logger.info("Processo sem alteração na API mas com PDF ausente em disco. Recriando: %s", cnj)

                # Fetch details including updated publications and progress history
                proc_full = item
                if pub_id:
                    try:
                        logger.debug("Baixando andamentos detalhados da publicação %s...", pub_id)
                        det = client.get_process_by_publication(pub_id)
                        proc_full = det.get("data", det)
                    except Exception as e:
                        logger.warning("Não foi possível obter detalhes da pub %s: %s", pub_id, e)

                # Persist in local SQLite database
                self.db.save_process(proc_full, pub_id=pub_id)

                # Generate documents (base DOCX and render PDF)
                docx_tmp, pdf_tmp = self.doc_generator.render_process_documents(proc_full, base_name=f"{safe_cnj}_Relatorio")

                if not pdf_tmp or not os.path.exists(pdf_tmp):
                    logger.error("Falha ao gerar PDF para o processo: %s", cnj)
                    continue

                # 1. Save local backup and group by Party:
                # Structure: Party A / {CNJ}_Relatorio.pdf
                parties = extract_party_names(proc_full)
                for party in parties:
                    safe_party = sanitize_filename(party)
                    local_folder = os.path.join(self.local_storage_dir, safe_party)
                    os.makedirs(local_folder, exist_ok=True)

                    local_docx = os.path.join(local_folder, f"{safe_cnj}_Relatorio.docx")
                    shutil.copy2(docx_tmp, local_docx)

                    local_pdf = os.path.join(local_folder, f"{safe_cnj}_Relatorio.pdf")
                    shutil.copy2(pdf_tmp, local_pdf)

                    # 2. Upload to Nextcloud: PDF ONLY into the Party folder inside General Archive
                    try:
                        remote_archive_pdf = f"{archive_folder}/{safe_party}/{safe_cnj}_Relatorio.pdf"
                        nc_client.upload_file(local_pdf, remote_archive_pdf)
                    except Exception as upload_err:
                        logger.error("Erro no upload do PDF do processo %s para Arquivo_Geral: %s", cnj, upload_err)

                # 3. Upload to Daily Rotating Folder (Daily Magic Link):
                # Uploaded EXACTLY ONCE per lawsuit to avoid duplicates
                try:
                    parties_label = " x ".join(parties[:2]) if len(parties) >= 2 else (parties[0] if parties else "Processo")
                    safe_label = sanitize_filename(parties_label)
                    daily_pdf_filename = f"{safe_cnj} - {safe_label}.pdf"
                    remote_daily_pdf = f"{daily_folder}/{daily_pdf_filename}"
                    nc_client.upload_file(pdf_tmp, remote_daily_pdf)
                except Exception as upload_daily_err:
                    logger.error("Erro no upload para pasta diária do processo %s: %s", cnj, upload_daily_err)

                # Remove temporary files
                try:
                    if os.path.exists(docx_tmp):
                        os.remove(docx_tmp)
                    if pdf_tmp and os.path.exists(pdf_tmp):
                        os.remove(pdf_tmp)
                except Exception:
                    pass

                total_synced += 1

                # Collect summary item for daily email
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

        # 8. Notify users via email with public Magic Links
        try:
            logger.info("Enviando relatório diário por e-mail para: %s...", self.config.notification_emails)
            send_daily_summary(
                config=self.config,
                stats=stats,
                updated_items=updated_processes_summary,
                nextcloud_folder=self.config.nextcloud_remote_dir,
                magic_link_daily=magic_link_daily,
                magic_link_archive=magic_link_archive
            )
        except Exception as mail_err:
            logger.error("Erro ao enviar e-mail diário de resumo: %s", mail_err)

        return stats
