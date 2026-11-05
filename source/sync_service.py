import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from source.auth import login_legalone
from source.client import LegalOneClient
from source.cnj_parser import parse_cnj
from source.config import AppConfig
from source.database import Database
from source.document_generator import DocumentGenerator, sanitize_filename
from source.http_client import HTTPClient
from source.nextcloud_client import NextcloudClient
from source.notifier import send_admin_alert, send_daily_summary
from source.smtp_client import SMTPClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NextcloudStorageContext:
    """Paths and public Magic Links for Nextcloud storage destinations."""

    daily_folder: str
    archive_folder: str
    magic_link_daily: str | None = None
    magic_link_archive: str | None = None


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


def format_parties_label(parties: list[str]) -> str:
    """Format short summary parties string for daily files and summaries."""
    if len(parties) >= 2:
        return f"{parties[0]} x {parties[1]}"
    if parties:
        return parties[0]
    return "Processo"


def format_last_progress_summary(proc: dict[str, Any]) -> str:
    """Extract and format the most recent progress entry into a concise text."""
    andamentos = proc.get("recentProgresses") or proc.get("progresses") or []
    if not andamentos:
        return "Sem andamento recente registrado"

    last_a = andamentos[0]
    d = last_a.get("strData") or (last_a.get("dtHrAndamento") or "")[:10]
    orig = last_a.get("source") or "Diário"
    desc = (last_a.get("descricao") or "").strip()[:140]
    return f"[{d} - {orig}] {desc}..."


def build_process_summary_entry(
    proc: dict[str, Any], cnj: str, parties: list[str]
) -> dict[str, Any]:
    """Build summary dictionary item for the daily email notification."""
    cnj_info = parse_cnj(cnj)
    return {
        "cnj": cnj,
        "tribunal": cnj_info["tribunal_sigla"] if cnj_info["is_valid"] else "",
        "partes": ", ".join(parties[:2]),
        "ultimo_andamento": format_last_progress_summary(proc),
    }


class SyncService:
    """Orchestrator for synchronization lifecycle, report generation, and mirroring."""

    def __init__(
        self,
        config: AppConfig,
        db: Database | None = None,
        doc_generator: DocumentGenerator | None = None,
        legalone_client: LegalOneClient | None = None,
        nextcloud_client: NextcloudClient | None = None,
        smtp_client: SMTPClient | None = None,
        http_client: HTTPClient | None = None,
    ):
        self.config = config
        self.db = db or Database(config.db_path)
        self.doc_generator = doc_generator or DocumentGenerator(config.temp_dir)
        self.legalone_client = legalone_client
        self.nextcloud_client = nextcloud_client
        self.smtp_client = smtp_client
        self.http_client = http_client
        self.local_storage_dir = os.path.join(self.config.storage_dir, "Processos")
        os.makedirs(self.local_storage_dir, exist_ok=True)

    def _init_legalone_client(self) -> LegalOneClient:
        """Initialize or retrieve authenticated LegalOne API client."""
        if self.legalone_client is not None:
            return self.legalone_client

        try:
            logger.info("Autenticando no Conecta LegalOne com e-mail: %s...", self.config.legalone_email)
            auth_data = login_legalone(
                email=self.config.legalone_email,
                password=self.config.legalone_password,
                access_code=self.config.legalone_access_code,
                base_url=self.config.legalone_base_url,
                http_client=self.http_client,
            )
            token = auth_data.get("token") or auth_data.get("accessToken") or auth_data.get("access_token")
            if not token:
                raise ValueError("Nenhum token retornado pela API do LegalOne.")
            return LegalOneClient(
                token=token,
                tenant_id=self.config.legalone_tenant_id,
                base_url=self.config.legalone_base_url,
                http_client=self.http_client,
            )
        except Exception as e:
            err_msg = f"Falha ao realizar login no LegalOne:\n{str(e)}"
            logger.error(err_msg)
            try:
                send_admin_alert(
                    config=self.config,
                    subject_title="Falha de Autenticação LegalOne",
                    error_message=str(e),
                    context_details="O processo não pôde iniciar porque as credenciais foram rejeitadas ou o serviço está inacessível.",
                    smtp_client=self.smtp_client,
                )
            except Exception as mail_err:
                logger.error("Falha secundária ao enviar e-mail de alerta: %s", mail_err)
            raise

    def _get_nextcloud_client(self) -> NextcloudClient:
        """Initialize or retrieve Nextcloud client instance."""
        return self.nextcloud_client or NextcloudClient(
            base_url=self.config.nextcloud_url,
            user=self.config.nextcloud_user,
            password=self.config.nextcloud_password,
            verify_ssl=self.config.nextcloud_verify_ssl,
            http_client=self.http_client,
        )

    def _init_nextcloud_storage(self, nc_client: NextcloudClient) -> NextcloudStorageContext:
        """
        Ensure Nextcloud storage folders exist, rotate previous daily updates,
        and acquire public Magic Links.
        """
        daily_folder = f"{self.config.nextcloud_remote_dir}/Novos_e_Atualizados"
        archive_folder = f"{self.config.nextcloud_remote_dir}/Arquivo_Geral"

        nc_client.ensure_directory(daily_folder)
        nc_client.ensure_directory(archive_folder)

        logger.info("Verificando rotação da pasta diária '%s'...", daily_folder)
        try:
            nc_client.archive_previous_daily_updates(daily_folder, archive_folder)
        except Exception as rot_err:
            logger.warning("Aviso na rotação de arquivos do Nextcloud: %s", rot_err)

        magic_link_daily = None
        magic_link_archive = None
        try:
            magic_link_daily = nc_client.get_or_create_public_share(daily_folder)
            magic_link_archive = nc_client.get_or_create_public_share(archive_folder)
            logger.info("Magic Link (Processos do Dia): %s", magic_link_daily)
            logger.info("Magic Link (Acervo Geral): %s", magic_link_archive)
        except Exception as link_err:
            logger.warning("Não foi possível gerar Magic Links públicos: %s", link_err)

        return NextcloudStorageContext(
            daily_folder=daily_folder,
            archive_folder=archive_folder,
            magic_link_daily=magic_link_daily,
            magic_link_archive=magic_link_archive,
        )

    def _is_process_up_to_date(
        self,
        item: dict[str, Any],
        first_party: str,
        safe_cnj: str,
        archive_folder: str,
        nc_client: NextcloudClient,
    ) -> bool:
        """
        Verify if lawsuit is unchanged in SQLite database and retains intact
        PDF copies locally and on Nextcloud (auto-healing remote copy if missing).
        """
        p_id = item.get("id")
        pub_id = item.get("id_adv_publication")
        cnj = item.get("numeroCNJ") or f"ID_{p_id}"
        api_updated_at = item.get("dtHrUltimaAtualizacaoDc")

        db_info = self.db.get_process_sync_info(p_id)
        is_changed = True
        if db_info and db_info["dt_hr_ultima_atualizacao"] == api_updated_at and db_info["id_adv_publication"] == pub_id:
            is_changed = False

        if is_changed:
            return False

        # Verify local disk and remote Nextcloud PDF integrity
        local_proc_folder = os.path.join(self.local_storage_dir, first_party)
        local_pdf = os.path.join(local_proc_folder, f"{safe_cnj}_Relatorio.pdf")
        remote_archive_pdf = f"{archive_folder}/{first_party}/{safe_cnj}_Relatorio.pdf"

        local_ok = os.path.exists(local_pdf)
        remote_ok = nc_client.exists(remote_archive_pdf) if local_ok else False

        if local_ok and remote_ok:
            return True

        if local_ok and not remote_ok:
            logger.info("Detectada ausência do PDF no Nextcloud para %s. Reenviando cópia local...", cnj)
            try:
                nc_client.upload_file(local_pdf, remote_archive_pdf)
                return True
            except Exception as sync_err:
                logger.error("Erro ao restabelecer PDF no Nextcloud para %s: %s", cnj, sync_err)

        logger.info("Processo sem alteração na API mas com PDF ausente em disco. Recriando: %s", cnj)
        return False

    def _fetch_process_details(self, client: LegalOneClient, item: dict[str, Any]) -> dict[str, Any]:
        """Fetch detailed publication and progress history for a lawsuit."""
        pub_id = item.get("id_adv_publication")
        if not pub_id:
            return item

        try:
            logger.debug("Baixando andamentos detalhados da publicação %s...", pub_id)
            det = client.get_process_by_publication(pub_id)
            return det.get("data", det)
        except Exception as e:
            logger.warning("Não foi possível obter detalhes da pub %s: %s", pub_id, e)
            return item

    def _generate_and_store_reports(
        self,
        proc_full: dict[str, Any],
        safe_cnj: str,
        parties: list[str],
        daily_folder: str,
        archive_folder: str,
        nc_client: NextcloudClient,
    ) -> bool:
        """
        Generate DOCX/PDF reports, save local backups grouped by party,
        upload PDF exclusively to Nextcloud archive and daily folder, and cleanup temps.
        """
        cnj = proc_full.get("numeroCNJ") or f"ID_{proc_full.get('id')}"
        docx_tmp, pdf_tmp = self.doc_generator.render_process_documents(
            proc_full, base_name=f"{safe_cnj}_Relatorio"
        )

        if not pdf_tmp or not os.path.exists(pdf_tmp):
            logger.error("Falha ao gerar PDF para o processo: %s", cnj)
            return False

        try:
            # Save local backup and upload to Nextcloud Archive & Daily Folder (both grouped by Party)
            for party in parties:
                safe_party = sanitize_filename(party)
                local_folder = os.path.join(self.local_storage_dir, safe_party)
                os.makedirs(local_folder, exist_ok=True)

                local_docx = os.path.join(local_folder, f"{safe_cnj}_Relatorio.docx")
                shutil.copy2(docx_tmp, local_docx)

                local_pdf = os.path.join(local_folder, f"{safe_cnj}_Relatorio.pdf")
                shutil.copy2(pdf_tmp, local_pdf)

                # 1. Upload to Permanent Archive (grouped by Party)
                try:
                    remote_archive_pdf = f"{archive_folder}/{safe_party}/{safe_cnj}_Relatorio.pdf"
                    nc_client.upload_file(local_pdf, remote_archive_pdf)
                except Exception as upload_err:
                    logger.error("Erro no upload do PDF do processo %s para Arquivo_Geral: %s", cnj, upload_err)

                # 2. Upload to Daily Rotating Folder (also grouped by Party)
                try:
                    remote_daily_pdf = f"{daily_folder}/{safe_party}/{safe_cnj}_Relatorio.pdf"
                    nc_client.upload_file(local_pdf, remote_daily_pdf)
                except Exception as upload_daily_err:
                    logger.error("Erro no upload para pasta diária do processo %s: %s", cnj, upload_daily_err)

            return True
        finally:
            # Cleanup temporary files
            try:
                if os.path.exists(docx_tmp):
                    os.remove(docx_tmp)
                if pdf_tmp and os.path.exists(pdf_tmp):
                    os.remove(pdf_tmp)
            except Exception:
                pass

    def _process_single_lawsuit(
        self,
        item: dict[str, Any],
        client: LegalOneClient,
        nc_client: NextcloudClient,
        storage: NextcloudStorageContext,
    ) -> tuple[bool, dict[str, Any] | None]:
        """
        Process a single lawsuit item:
        Returns (was_synced, summary_item_or_none).
        """
        p_id = item.get("id")
        pub_id = item.get("id_adv_publication")
        cnj = item.get("numeroCNJ") or f"ID_{p_id}"
        safe_cnj = sanitize_filename(cnj)
        parties = extract_party_names(item)
        first_party = sanitize_filename(parties[0])

        if self._is_process_up_to_date(item, first_party, safe_cnj, storage.archive_folder, nc_client):
            return False, None

        proc_full = self._fetch_process_details(client, item)
        self.db.save_process(proc_full, pub_id=pub_id)

        all_parties = extract_party_names(proc_full)
        ok = self._generate_and_store_reports(
            proc_full=proc_full,
            safe_cnj=safe_cnj,
            parties=all_parties,
            daily_folder=storage.daily_folder,
            archive_folder=storage.archive_folder,
            nc_client=nc_client,
        )

        if not ok:
            return False, None

        summary_item = build_process_summary_entry(proc_full, cnj, all_parties)
        return True, summary_item

    def _scan_lawsuit_pages(
        self,
        client: LegalOneClient,
        nc_client: NextcloudClient,
        storage: NextcloudStorageContext,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Iterate over paginated lawsuits and process each item."""
        page = 1
        limit = self.config.page_limit
        max_pages = self.config.max_pages
        total_synced = 0
        total_skipped = 0
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
                was_synced, summary = self._process_single_lawsuit(item, client, nc_client, storage)
                if was_synced and summary:
                    total_synced += 1
                    updated_processes_summary.append(summary)
                else:
                    total_skipped += 1

            if page * limit >= total_items:
                logger.info("Todos os registros do LegalOne foram percorridos.")
                break

            page += 1

        stats = {
            "synced": total_synced,
            "skipped": total_skipped,
            "total": total_items,
        }
        return stats, updated_processes_summary

    def _send_completion_notification(
        self,
        stats: dict[str, Any],
        updated_items: list[dict[str, Any]],
        magic_link_daily: str | None,
        magic_link_archive: str | None,
    ) -> None:
        """Send daily summary email to stakeholders."""
        try:
            logger.info("Enviando relatório diário por e-mail para: %s...", self.config.notification_emails)
            send_daily_summary(
                config=self.config,
                stats=stats,
                updated_items=updated_items,
                nextcloud_folder=self.config.nextcloud_remote_dir,
                magic_link_daily=magic_link_daily,
                magic_link_archive=magic_link_archive,
                smtp_client=self.smtp_client,
            )
        except Exception as mail_err:
            logger.error("Erro ao enviar e-mail diário de resumo: %s", mail_err)

    def run_sync(self) -> dict[str, Any]:
        """Execute full daily synchronization workflow."""
        logger.info("==================================================")
        logger.info("Iniciando rotina de sincronização Conecta LegalOne")
        logger.info("Data/Hora: %s", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        logger.info("==================================================")

        client = self._init_legalone_client()
        nc_client = self._get_nextcloud_client()
        storage = self._init_nextcloud_storage(nc_client)

        stats, updated_summary = self._scan_lawsuit_pages(client, nc_client, storage)

        logger.info(
            "Sincronização concluída com sucesso! Atualizados: %s | Inalterados: %s | Total: %s",
            stats["synced"],
            stats["skipped"],
            stats["total"],
        )

        self._send_completion_notification(
            stats,
            updated_summary,
            storage.magic_link_daily,
            storage.magic_link_archive,
        )

        return stats
