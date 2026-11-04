import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Any, Optional

import jinja2
from source.config import AppConfig

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "emails")
jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATES_DIR),
    autoescape=jinja2.select_autoescape(["html", "xml"])
)


def test_smtp_connection(config: AppConfig) -> bool:
    """
    Testa a conexão e autenticação com o servidor SMTP no bootstrap.
    Falha e levanta exceção se não conseguir conectar ou autenticar.
    """
    if not config.smtp_host:
        raise ValueError("SMTP_HOST não foi configurado.")

    logger.info("Testando conexão SMTP com %s:%s...", config.smtp_host, config.smtp_port)
    try:
        if config.smtp_use_ssl:
            server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15)

        server.ehlo()
        if config.smtp_use_tls and not config.smtp_use_ssl:
            server.starttls()
            server.ehlo()

        if config.smtp_user and config.smtp_password:
            server.login(config.smtp_user, config.smtp_password)

        server.quit()
        logger.info("✓ Teste de SMTP concluído com sucesso!")
        return True
    except Exception as e:
        logger.critical("✕ FALHA NO TESTE DE SMTP: Não foi possível conectar ao servidor de e-mail: %s", e)
        raise ConnectionError(f"Falha de conexão SMTP no bootstrap: {e}") from e


def send_email(config: AppConfig, to_addresses: List[str], subject: str, html_content: str, text_content: Optional[str] = None):
    """Envia um e-mail HTML/texto via SMTP para a lista de destinatários informada."""
    if not to_addresses:
        logger.warning("Nenhum destinatário informado para envio de e-mail.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.smtp_from
    msg["To"] = ", ".join(to_addresses)

    plain_text = text_content or "Este e-mail contém formatação HTML. Por favor, visualize em um cliente de e-mail compatível."
    part1 = MIMEText(plain_text, "plain", "utf-8")
    part2 = MIMEText(html_content, "html", "utf-8")

    msg.attach(part1)
    msg.attach(part2)

    try:
        if config.smtp_use_ssl:
            server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=20)
        else:
            server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20)

        server.ehlo()
        if config.smtp_use_tls and not config.smtp_use_ssl:
            server.starttls()
            server.ehlo()

        if config.smtp_user and config.smtp_password:
            server.login(config.smtp_user, config.smtp_password)

        server.sendmail(config.smtp_from, to_addresses, msg.as_string())
        server.quit()
        logger.info("E-mail enviado com sucesso para: %s (Assunto: '%s')", to_addresses, subject)
    except Exception as e:
        logger.error("Erro ao enviar e-mail via SMTP: %s", e)
        raise


def send_admin_alert(config: AppConfig, subject_title: str, error_message: str, context_details: str = ""):
    """
    Renderiza o template admin_alert.html e envia alerta crítico ao administrador.
    """
    if not config.admin_email:
        logger.warning("ADMIN_EMAIL não definido. Alerta de erro não pôde ser enviado por e-mail: %s", error_message)
        return

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    subject = f"⚠️ [ALERTA CRÍTICO] LegalOne Sync - {subject_title}"

    template = jinja_env.get_template("admin_alert.html")
    html = template.render(
        subject_title=subject_title,
        now_str=now_str,
        error_message=error_message,
        context_details=context_details
    )

    send_email(config, [config.admin_email], subject, html)


def send_daily_summary(
    config: AppConfig,
    stats: Dict[str, Any],
    updated_items: List[Dict[str, Any]],
    nextcloud_folder: str,
    magic_link_daily: Optional[str] = None,
    magic_link_archive: Optional[str] = None
):
    """
    Renderiza o template daily_summary.html e envia relatório executivo aos destinatários
    com os Magic Links públicos para a pasta do dia e para o acervo geral completo.
    """
    recipients = config.notification_emails
    if not recipients:
        logger.info("Nenhum e-mail configurado em NOTIFICATION_EMAILS. O resumo diário não será enviado.")
        return

    now_str = datetime.now().strftime("%d/%m/%Y às %H:%M")
    total_synced = stats.get("synced", 0)

    template = jinja_env.get_template("daily_summary.html")
    html = template.render(
        now_str=now_str,
        stats=stats,
        updated_items=updated_items,
        nextcloud_folder=nextcloud_folder,
        magic_link_daily=magic_link_daily,
        magic_link_archive=magic_link_archive
    )

    date_label = now_str.split(" às ")[0]
    subject = f"⚖️ Relatório Diário LegalOne - {total_synced} processos atualizados ({date_label})"
    send_email(config, recipients, subject, html)
