import pytest

from source.config import AppConfig
from source.notifier import EmailNotifier
from source.smtp_client import SMTPClient, StandardSMTPClient


class FakeSMTPClient:
    def __init__(self):
        self.sent_emails: list[dict] = []
        self.connected: bool = True

    def test_connection(self) -> bool:
        return self.connected

    def send_email(
        self,
        to_addresses: list[str],
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> None:
        self.sent_emails.append({
            "to": to_addresses,
            "subject": subject,
            "html": html_content,
            "text": text_content,
        })


def test_smtp_client_protocol_conformance(mock_config):
    fake = FakeSMTPClient()
    assert isinstance(fake, SMTPClient)

    standard = StandardSMTPClient(mock_config)
    assert isinstance(standard, SMTPClient)


def test_standard_smtp_client_missing_host():
    cfg = AppConfig(smtp_host="")
    client = StandardSMTPClient(cfg)
    with pytest.raises(ValueError):
        client.test_connection()


def test_standard_smtp_client_test_connection_ssl(mocker):
    cfg = AppConfig(
        smtp_host="smtp.ssl.test",
        smtp_port=465,
        smtp_use_ssl=True,
        smtp_user="ssl_user",
        smtp_password="ssl_password",
    )
    mock_server = mocker.MagicMock()
    mocker.patch("smtplib.SMTP_SSL", return_value=mock_server)

    client = StandardSMTPClient(cfg)
    assert client.test_connection() is True
    mock_server.login.assert_called_once_with("ssl_user", "ssl_password")
    mock_server.quit.assert_called_once()


def test_standard_smtp_client_test_connection_failure(mocker, mock_config):
    mocker.patch("smtplib.SMTP", side_effect=Exception("Connection refused"))
    client = StandardSMTPClient(mock_config)

    with pytest.raises(ConnectionError) as excinfo:
        client.test_connection()

    assert "Connection refused" in str(excinfo.value)


def test_standard_smtp_client_send_email_success(mocker, mock_config):
    mock_server = mocker.MagicMock()
    mocker.patch("smtplib.SMTP", return_value=mock_server)

    client = StandardSMTPClient(mock_config)
    client.send_email(
        to_addresses=["dest@test.com"],
        subject="Assunto de Teste",
        html_content="<p>Olá</p>",
        text_content="Olá em texto",
    )

    mock_server.sendmail.assert_called_once()
    args, _ = mock_server.sendmail.call_args
    assert args[0] == mock_config.smtp_from
    assert args[1] == ["dest@test.com"]
    assert "Assunto de Teste" in args[2]


def test_standard_smtp_client_send_email_no_recipients(mocker, mock_config):
    mock_smtp = mocker.patch("smtplib.SMTP")
    client = StandardSMTPClient(mock_config)
    client.send_email(to_addresses=[], subject="Sem Destinatários", html_content="...")
    mock_smtp.assert_not_called()


def test_email_notifier_delegation(mock_config):
    fake_smtp = FakeSMTPClient()
    notifier = EmailNotifier(config=mock_config, smtp_client=fake_smtp)

    assert notifier.test_connection() is True

    # Send direct email
    notifier.send_email(["a@test.com"], "Titulo", "<b>Corpo</b>")
    assert len(fake_smtp.sent_emails) == 1
    assert fake_smtp.sent_emails[0]["to"] == ["a@test.com"]

    # Send admin alert
    notifier.send_admin_alert("Falha Servidor", "Erro inesperado 500")
    assert len(fake_smtp.sent_emails) == 2
    assert fake_smtp.sent_emails[1]["to"] == [mock_config.admin_email]
    assert "Falha Servidor" in fake_smtp.sent_emails[1]["subject"]

    # Send daily summary
    stats = {"synced": 5, "skipped": 15, "total": 20}
    notifier.send_daily_summary(stats, [], "Pasta_Remota")
    assert len(fake_smtp.sent_emails) == 3
    assert fake_smtp.sent_emails[2]["to"] == mock_config.notification_emails
    assert "5 processos atualizados" in fake_smtp.sent_emails[2]["subject"]
