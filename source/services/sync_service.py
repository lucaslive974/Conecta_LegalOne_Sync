from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
from typing import Any

from source.config import AppConfig
from source.domain.cnj import parse_cnj
from source.domain.models import (
    Lawsuit,
    ProcessSummaryEntry,
    StorageContext,
)
from source.infrastructure.database.repository import Database
from source.infrastructure.documents.generator import DocumentGenerator, sanitize_filename
from source.infrastructure.email.notifier import send_admin_alert, send_daily_summary
from source.infrastructure.email.smtp_client import SMTPClient
from source.infrastructure.legalone.auth import login_legalone
from source.infrastructure.legalone.client import LegalOneClient
from source.infrastructure.network.http_client import HTTPClient
from source.infrastructure.nextcloud.client import NextcloudClient

logger = logging.getLogger(__name__)

# Alias for backward compatibility
NextcloudStorageContext = StorageContext


def extract_party_names(proc: Lawsuit | dict[str, Any]) -> list[str]:
    """
    Extract main plaintiff and defendant party names.
    Deliberately ignores 'Responsável' or 'Advogado' contacts to prevent
    office-wide lawsuits from being duplicated under internal lawyer folders.
    """
    if isinstance(proc, Lawsuit):
        return proc.main_parties

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


def format_parties_label(parties: list[str] | Lawsuit) -> str:
    """Format short summary parties string for daily files and summaries."""
    if isinstance(parties, Lawsuit):
        return parties.parties_label
    if len(parties) >= 2:
        return f"{parties[0]} x {parties[1]}"
    if parties:
        return parties[0]
    return "Processo"


def format_last_progress_summary(proc: Lawsuit | dict[str, Any]) -> str:
    """Extract and format the most recent progress entry into a concise text."""
    if isinstance(proc, Lawsuit):
        return proc.last_progress_summary

    andamentos = proc.get("recentProgresses") or proc.get("progresses") or []
    if not andamentos:
        return "Sem andamento recente registrado"

    last_a = andamentos[0]
    d = last_a.get("strData") or (last_a.get("dtHrAndamento") or "")[:10]
    orig = last_a.get("source") or "Diário"
    desc = (last_a.get("descricao") or "").strip()[:140]
    return f"[{d} - {orig}] {desc}..."


def build_process_summary_entry(proc: Lawsuit | dict[str, Any], cnj: str, parties: list[str]) -> ProcessSummaryEntry:
    """Build summary domain item for the daily email notification."""
    cnj_info = proc.cnj_info if isinstance(proc, Lawsuit) else parse_cnj(cnj)
    tribunal = cnj_info.tribunal_sigla if cnj_info.is_valid else ""
    partes_str = ", ".join(parties[:2])
    last_prog = format_last_progress_summary(proc)

    pasta = proc.pasta if isinstance(proc, Lawsuit) else proc.get("pasta", "")
    ramo = cnj_info.ramo
    valor = str(proc.valor_causa) if isinstance(proc, Lawsuit) else str(proc.get("valorCausa", ""))
    status = proc.status_nome if isinstance(proc, Lawsuit) else str(proc.get("status", {}))

    return ProcessSummaryEntry(
        cnj=cnj,
        tribunal=tribunal,
        partes=partes_str,
        ultimo_andamento=last_prog,
        pasta=pasta or "",
        ramo_justica=ramo,
        valor_causa=valor,
        status=status,
    )


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

    def _init_nextcloud_storage(self, nc_client: NextcloudClient) -> StorageContext:
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

        return StorageContext(
            daily_folder=daily_folder,
            archive_folder=archive_folder,
            magic_link_daily=magic_link_daily,
            magic_link_archive=magic_link_archive,
        )

    def _is_process_up_to_date(
        self,
        item: Lawsuit | dict[str, Any],
        first_party: str,
        safe_cnj: str,
        archive_folder: str | None = None,
        nc_client: NextcloudClient | None = None,
    ) -> bool:
        """
        Verify if lawsuit is unchanged in SQLite database and has an intact
        PDF report on local disk. Zero network requests required.
        """
        p_id: int | str
        if isinstance(item, Lawsuit):
            p_id = item.id
            pub_id = item.id_adv_publication
            cnj = item.cnj
            api_updated_at = item.dt_hr_ultima_atualizacao
        else:
            p_id = item.get("id") or 0
            pub_id = item.get("id_adv_publication")
            cnj = item.get("numeroCNJ") or f"ID_{p_id}"
            api_updated_at = item.get("dtHrUltimaAtualizacaoDc") or item.get("dtHrUltimaAtualizacao")

        db_info = self.db.get_process_sync_info(p_id)
        is_changed = True
        if db_info and db_info.dt_hr_ultima_atualizacao == api_updated_at and db_info.id_adv_publication == pub_id:
            is_changed = False

        if is_changed:
            return False

        # Verify local disk PDF integrity (zero network requests)
        local_proc_folder = os.path.join(self.local_storage_dir, first_party)
        local_pdf = os.path.join(local_proc_folder, f"{safe_cnj}_Relatorio.pdf")

        if os.path.exists(local_pdf):
            return True

        logger.info("Processo sem alteração na API mas com PDF ausente em disco local. Recriando: %s", cnj)
        return False

    def heal_remote_storage(self, nc_client: NextcloudClient | None = None) -> dict[str, int]:
        """
        Dedicated health recovery routine.
        Scans local storage directories and reconciles with Nextcloud:
        ensures remote folders exist and re-uploads any missing PDF files.
        """
        client = nc_client or self._get_nextcloud_client()
        archive_folder = f"{self.config.nextcloud_remote_dir}/Arquivo_Geral"
        client.ensure_directory(archive_folder)

        logger.info("Iniciando rotina de Health Recovery do Nextcloud...")
        logger.info("Diretório local base: %s", self.local_storage_dir)
        logger.info("Pasta remota de acervo: %s", archive_folder)

        stats = {
            "total_local_files": 0,
            "already_present": 0,
            "restored": 0,
            "errors": 0,
        }

        if not os.path.exists(self.local_storage_dir):
            logger.warning("Diretório de armazenamento local não existe: %s", self.local_storage_dir)
            return stats

        for entry in os.scandir(self.local_storage_dir):
            if not entry.is_dir():
                continue

            party_folder_name = entry.name
            remote_party_dir = f"{archive_folder}/{party_folder_name}"

            pdf_files = [f for f in os.scandir(entry.path) if f.is_file() and f.name.lower().endswith(".pdf")]
            if not pdf_files:
                continue

            party_dir_ensured = False

            for pdf_entry in pdf_files:
                stats["total_local_files"] += 1
                remote_pdf_path = f"{remote_party_dir}/{pdf_entry.name}"

                try:
                    if client.exists(remote_pdf_path):
                        stats["already_present"] += 1
                        continue

                    if not party_dir_ensured:
                        client.ensure_directory(remote_party_dir)
                        party_dir_ensured = True

                    logger.info("Restaurando arquivo ausente no Nextcloud: %s", remote_pdf_path)
                    client.upload_file(pdf_entry.path, remote_pdf_path)
                    stats["restored"] += 1
                except Exception as err:
                    logger.error("Erro ao verificar/restaurar %s: %s", remote_pdf_path, err)
                    stats["errors"] += 1

        logger.info(
            "Health Recovery concluído. Total: %d, Já presentes: %d, Restaurados: %d, Erros: %d",
            stats["total_local_files"],
            stats["already_present"],
            stats["restored"],
            stats["errors"],
        )
        return stats

    def _fetch_process_details(
        self, client: LegalOneClient, item: Lawsuit | dict[str, Any]
    ) -> Lawsuit | dict[str, Any]:
        """Fetch detailed publication and progress history for a lawsuit."""
        pub_id = item.id_adv_publication if isinstance(item, Lawsuit) else item.get("id_adv_publication")
        if not pub_id:
            return item

        try:
            logger.debug("Baixando andamentos detalhados da publicação %s...", pub_id)
            det = client.get_process_by_publication(pub_id)
            raw = det.get("data", det)
            if isinstance(item, Lawsuit):
                return Lawsuit.from_api_dict(raw)
            return raw
        except Exception as e:
            logger.warning("Não foi possível obter detalhes da pub %s: %s", pub_id, e)
            return item

    def _generate_and_store_reports(
        self,
        proc_full: Lawsuit | dict[str, Any],
        safe_cnj: str,
        parties: list[str],
        daily_folder: str,
        archive_folder: str,
        nc_client: NextcloudClient,
    ) -> bool:
        """
        Generate DOCX/PDF reports, save local backups grouped by party,
        and upload PDF to Nextcloud archive and daily folders.
        """
        cnj = (
            proc_full.cnj
            if isinstance(proc_full, Lawsuit)
            else (proc_full.get("numeroCNJ") or f"ID_{proc_full.get('id')}")
        )
        docx_tmp, pdf_tmp = self.doc_generator.render_process_documents(proc_full, base_name=f"{safe_cnj}_Relatorio")

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
        item: Lawsuit | dict[str, Any],
        client: LegalOneClient,
        nc_client: NextcloudClient,
        storage: StorageContext,
    ) -> tuple[bool, ProcessSummaryEntry | None]:
        """
        Process a single lawsuit item:
        Returns (was_synced, summary_item_or_none).
        """
        p_id: int | str
        if isinstance(item, Lawsuit):
            p_id = item.id
            pub_id = item.id_adv_publication
            cnj = item.cnj
            safe_cnj = item.safe_cnj
            parties = item.main_parties
        else:
            p_id = item.get("id") or 0
            pub_id = item.get("id_adv_publication")
            cnj = item.get("numeroCNJ") or f"ID_{p_id}"
            safe_cnj = sanitize_filename(cnj)
            parties = extract_party_names(item)

        first_party = sanitize_filename(parties[0])

        if self._is_process_up_to_date(item, first_party, safe_cnj):
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
        storage: StorageContext,
    ) -> tuple[dict[str, Any], list[ProcessSummaryEntry]]:
        """Iterate over paginated lawsuits and process each item."""
        page = 1
        limit = self.config.page_limit
        max_pages = self.config.max_pages
        total_synced = 0
        total_skipped = 0
        total_items = 0
        updated_processes_summary: list[ProcessSummaryEntry] = []

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

            for raw_item in process_list:
                lawsuit = Lawsuit.from_api_dict(raw_item)
                was_synced, summary = self._process_single_lawsuit(lawsuit, client, nc_client, storage)
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
        updated_items: list[ProcessSummaryEntry],
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
