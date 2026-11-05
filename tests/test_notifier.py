import pytest

from source.config import AppConfig
from source.infrastructure.email.notifier import (
    send_admin_alert,
    send_daily_summary,
    send_email,
)
from source.infrastructure.email.notifier import (
    test_smtp_connection as check_smtp_connection,
)


def test_test_smtp_connection_missing_host():
    cfg = AppConfig(smtp_host="")
    with pytest.raises(ValueError):
        check_smtp_connection(cfg)


def test_test_smtp_connection_success(mock_config, mocker):
    mock_server = mocker.MagicMock()
    mocker.patch("smtplib.SMTP", return_value=mock_server)

    assert check_smtp_connection(mock_config) is True
    mock_server.ehlo.assert_called()
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with(mock_config.smtp_user, mock_config.smtp_password)
    mock_server.quit.assert_called_once()


def test_send_email_no_recipients(mock_config, mocker):
    mock_smtp = mocker.patch("smtplib.SMTP")
    send_email(mock_config, [], "Subject", "<h1>Content</h1>")
    mock_smtp.assert_not_called()


def test_send_admin_alert(mock_config, mocker):
    mock_send = mocker.patch("source.notifier.send_email")

    send_admin_alert(
        config=mock_config,
        subject_title="Falha Teste",
        error_message="Erro simulado de banco",
        context_details="Detalhes operacionais",
    )

    mock_send.assert_called_once()
    args, _ = mock_send.call_args
    assert args[0] == mock_config
    assert args[1] == [mock_config.admin_email]
    assert "Falha Teste" in args[2]
    assert "Erro simulado de banco" in args[3]


def test_send_daily_summary(mock_config, mocker):
    mock_send = mocker.patch("source.notifier.send_email")

    stats = {"synced": 2, "skipped": 10, "total": 12}
    items = [{"cnj": "0001234", "partes": "Autor vs Reu", "ultimo_andamento": "Publicacao teste"}]

    send_daily_summary(
        config=mock_config,
        stats=stats,
        updated_items=items,
        nextcloud_folder="Processos_LegalOne",
        magic_link_daily="https://cloud.test/s/DAILY",
        magic_link_archive="https://cloud.test/s/ARCHIVE",
    )

    mock_send.assert_called_once()
    args, _ = mock_send.call_args
    assert args[1] == mock_config.notification_emails
    assert "2 processos atualizados" in args[2]
    assert "https://cloud.test/s/DAILY" in args[3]
