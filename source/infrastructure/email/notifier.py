import logging
import os
from datetime import datetime
from typing import Any

import jinja2

from source.config import AppConfig
from source.domain.models import ProcessSummaryEntry, SyncStats
from source.infrastructure.email.smtp_client import SMTPClient, StandardSMTPClient

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "emails")
jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATES_DIR), autoescape=jinja2.select_autoescape(["html", "xml"])
)


def test_smtp_connection(config: AppConfig, smtp_client: SMTPClient | None = None) -> bool:
    """
    Test connectivity and authentication with SMTP server at bootstrap.
    Fails and raises an exception if unable to connect or authenticate.
    """
    client = smtp_client or StandardSMTPClient(config)
    return client.test_connection()


def send_email(
    config: AppConfig,
    to_addresses: list[str],
    subject: str,
    html_content: str,
    text_content: str | None = None,
    smtp_client: SMTPClient | None = None,
) -> None:
    """Send an HTML/text email via SMTP to the provided recipient list."""
    client = smtp_client or StandardSMTPClient(config)
    client.send_email(to_addresses, subject, html_content, text_content)


def send_admin_alert(
    config: AppConfig,
    subject_title: str,
    error_message: str,
    context_details: str = "",
    smtp_client: SMTPClient | None = None,
) -> None:
    """
    Render admin_alert.html template and send critical alert to the administrator.
    """
    if not config.admin_email:
        logger.warning("ADMIN_EMAIL não definido. Alerta de erro não pôde ser enviado por e-mail: %s", error_message)
        return

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    subject = f"⚠️ [ALERTA CRÍTICO] LegalOne Sync - {subject_title}"

    template = jinja_env.get_template("admin_alert.html")
    html = template.render(
        subject_title=subject_title, now_str=now_str, error_message=error_message, context_details=context_details
    )

    send_email(config, [config.admin_email], subject, html, smtp_client=smtp_client)


def send_daily_summary(
    config: AppConfig,
    stats: SyncStats | dict[str, Any],
    updated_items: list[ProcessSummaryEntry | dict[str, Any]],
    nextcloud_folder: str,
    magic_link_daily: str | None = None,
    magic_link_archive: str | None = None,
    smtp_client: SMTPClient | None = None,
) -> None:
    """
    Render daily_summary.html template and send executive summary to recipients
    with public Magic Links to daily updates and the complete archive.
    """
    recipients = config.notification_emails
    if not recipients:
        logger.info("Nenhum e-mail configurado em NOTIFICATION_EMAILS. O resumo diário não será enviado.")
        return

    now_str = datetime.now().strftime("%d/%m/%Y às %H:%M")

    # Format stats for Jinja2 template
    if isinstance(stats, SyncStats):
        total_synced = stats.novos_ou_atualizados
        stats_dict = {
            "total": stats.total_consultados,
            "synced": stats.novos_ou_atualizados,
            "unchanged": stats.inalterados,
            "errors": stats.erros,
        }
    else:
        total_synced = stats.get("synced", 0)
        stats_dict = stats

    template = jinja_env.get_template("daily_summary.html")
    html = template.render(
        now_str=now_str,
        stats=stats_dict,
        updated_items=updated_items,
        nextcloud_folder=nextcloud_folder,
        magic_link_daily=magic_link_daily,
        magic_link_archive=magic_link_archive,
    )

    date_label = now_str.split(" às ")[0]
    subject = f"⚖️ Relatório Diário LegalOne - {total_synced} processos atualizados ({date_label})"
    send_email(config, recipients, subject, html, smtp_client=smtp_client)


class EmailNotifier:
    """High-level email notification service with template rendering and injected SMTP client."""

    def __init__(self, config: AppConfig, smtp_client: SMTPClient | None = None):
        self.config = config
        self.smtp_client = smtp_client or StandardSMTPClient(config)

    def test_connection(self) -> bool:
        """Test SMTP server connectivity and authentication."""
        return self.smtp_client.test_connection()

    def send_email(
        self,
        to_addresses: list[str],
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> None:
        """Send an email using the injected SMTP client."""
        self.smtp_client.send_email(to_addresses, subject, html_content, text_content)

    def send_admin_alert(
        self,
        subject_title: str,
        error_message: str,
        context_details: str = "",
    ) -> None:
        """Render and dispatch an admin alert email."""
        send_admin_alert(
            self.config,
            subject_title,
            error_message,
            context_details,
            smtp_client=self.smtp_client,
        )

    def send_daily_summary(
        self,
        stats: SyncStats | dict[str, Any],
        updated_items: list[ProcessSummaryEntry | dict[str, Any]],
        nextcloud_folder: str,
        magic_link_daily: str | None = None,
        magic_link_archive: str | None = None,
    ) -> None:
        """Render and dispatch the daily summary email."""
        send_daily_summary(
            self.config,
            stats,
            updated_items,
            nextcloud_folder,
            magic_link_daily,
            magic_link_archive,
            smtp_client=self.smtp_client,
        )
