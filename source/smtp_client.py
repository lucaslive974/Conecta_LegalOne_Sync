import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Protocol, runtime_checkable

from source.config import AppConfig

logger = logging.getLogger(__name__)


@runtime_checkable
class SMTPClient(Protocol):
    """Protocol defining the interface for SMTP clients."""

    def test_connection(self) -> bool:
        """Verify connection and credentials with the SMTP server."""
        ...

    def send_email(
        self,
        to_addresses: list[str],
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> None:
        """Send an HTML/text email to recipients."""
        ...


class StandardSMTPClient:
    """Default SMTP client implementation utilizing Python's smtplib."""

    def __init__(self, config: AppConfig):
        self.config = config

    def _create_server(self, timeout: float = 20) -> smtplib.SMTP:
        """Instantiate and authenticate an SMTP/SMTP_SSL connection."""
        if not self.config.smtp_host:
            raise ValueError("SMTP_HOST não foi configurado.")

        if self.config.smtp_use_ssl:
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                self.config.smtp_host, self.config.smtp_port, timeout=timeout
            )
        else:
            server = smtplib.SMTP(
                self.config.smtp_host, self.config.smtp_port, timeout=timeout
            )

        server.ehlo()
        if self.config.smtp_use_tls and not self.config.smtp_use_ssl:
            server.starttls()
            server.ehlo()

        if self.config.smtp_user and self.config.smtp_password:
            server.login(self.config.smtp_user, self.config.smtp_password)

        return server

    def test_connection(self) -> bool:
        """
        Test connectivity and authentication with SMTP server.
        Fails and raises ConnectionError if unable to connect or authenticate.
        """
        if not self.config.smtp_host:
            raise ValueError("SMTP_HOST não foi configurado.")

        logger.info(
            "Testando conexão SMTP com %s:%s...",
            self.config.smtp_host,
            self.config.smtp_port,
        )
        try:
            server = self._create_server(timeout=15)
            server.quit()
            logger.info("✓ Teste de SMTP concluído com sucesso!")
            return True
        except Exception as e:
            logger.critical(
                "✕ FALHA NO TESTE DE SMTP: Não foi possível conectar ao servidor de e-mail: %s",
                e,
            )
            raise ConnectionError(f"Falha de conexão SMTP no bootstrap: {e}") from e

    def send_email(
        self,
        to_addresses: list[str],
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> None:
        """Send an HTML/text email via SMTP to the provided recipient list."""
        if not to_addresses:
            logger.warning("Nenhum destinatário informado para envio de e-mail.")
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.config.smtp_from
        msg["To"] = ", ".join(to_addresses)

        plain_text = (
            text_content
            or "Este e-mail contém formatação HTML. Por favor, visualize em um cliente de e-mail compatível."
        )
        part1 = MIMEText(plain_text, "plain", "utf-8")
        part2 = MIMEText(html_content, "html", "utf-8")

        msg.attach(part1)
        msg.attach(part2)

        try:
            server = self._create_server(timeout=20)
            server.sendmail(self.config.smtp_from, to_addresses, msg.as_string())
            server.quit()
            logger.info(
                "E-mail enviado com sucesso para: %s (Assunto: '%s')",
                to_addresses,
                subject,
            )
        except Exception as e:
            logger.error("Erro ao enviar e-mail via SMTP: %s", e)
            raise
