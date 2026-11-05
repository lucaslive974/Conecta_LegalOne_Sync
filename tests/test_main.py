import pytest

from source.main import (
    bootstrap_checks,
    create_daemon_scheduler,
    main,
    parse_args,
    parse_schedule_time,
    run_daemon_mode,
    run_single_mode,
    verify_nextcloud_bootstrap,
)


def test_parse_schedule_time_valid():
    assert parse_schedule_time("07:30") == (7, 30)
    assert parse_schedule_time("00:00") == (0, 0)
    assert parse_schedule_time("23:59") == (23, 59)


def test_parse_schedule_time_invalid():
    with pytest.raises(ValueError):
        parse_schedule_time("invalid")

    with pytest.raises(ValueError):
        parse_schedule_time("25:00")

    with pytest.raises(ValueError):
        parse_schedule_time("12:65")

    with pytest.raises(ValueError):
        parse_schedule_time("ab:cd")


def test_parse_args():
    args_default = parse_args([])
    assert args_default.daemon is False
    assert args_default.test_smtp is False
    assert args_default.test_nextcloud is False

    args_daemon = parse_args(["--daemon"])
    assert args_daemon.daemon is True

    args_smtp = parse_args(["--test-smtp"])
    assert args_smtp.test_smtp is True

    args_nc = parse_args(["--test-nextcloud"])
    assert args_nc.test_nextcloud is True


def test_run_single_mode_success(mocker):
    mock_service = mocker.MagicMock()
    mock_service.run_sync.return_value = {"synced": 5}

    code = run_single_mode(mock_service)
    assert code == 0
    mock_service.run_sync.assert_called_once()


def test_run_single_mode_failure(mocker):
    mock_service = mocker.MagicMock()
    mock_service.run_sync.side_effect = RuntimeError("Fatal DB crash")

    code = run_single_mode(mock_service)
    assert code == 1


def test_create_daemon_scheduler(mocker):
    mock_service = mocker.MagicMock()
    scheduler = create_daemon_scheduler(mock_service, "08:15", "America/Sao_Paulo")

    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].id == "daily_legalone_sync"
    assert jobs[0].name == "Sincronização Diária LegalOne"


def test_run_daemon_mode_keyboard_interrupt(mocker):
    mock_service = mocker.MagicMock()
    mock_scheduler = mocker.MagicMock()
    mock_scheduler.start.side_effect = KeyboardInterrupt()

    mocker.patch("source.main.create_daemon_scheduler", return_value=mock_scheduler)

    code = run_daemon_mode(mock_service, "06:00", "UTC")
    assert code == 0
    mock_scheduler.start.assert_called_once()


def test_verify_nextcloud_bootstrap(mock_config, mocker):
    mock_nc = mocker.MagicMock()
    mocker.patch("source.main.NextcloudClient", return_value=mock_nc)

    client = verify_nextcloud_bootstrap(mock_config)
    assert client == mock_nc
    mock_nc.test_connection.assert_called_once()


def test_bootstrap_checks_success(mock_config, mocker):
    mocker.patch.object(mock_config, "validate_essential_configs")
    mocker.patch("source.main.test_smtp_connection", return_value=True)
    mocker.patch("source.main.verify_nextcloud_bootstrap")

    bootstrap_checks(mock_config)


def test_bootstrap_checks_smtp_failure(mock_config, mocker):
    mocker.patch.object(mock_config, "validate_essential_configs")
    mocker.patch("source.main.test_smtp_connection", side_effect=Exception("SMTP down"))

    with pytest.raises(ConnectionError):
        bootstrap_checks(mock_config)


def test_bootstrap_checks_nextcloud_failure(mock_config, mocker):
    mocker.patch.object(mock_config, "validate_essential_configs")
    mocker.patch("source.main.test_smtp_connection", return_value=True)
    mocker.patch("source.main.verify_nextcloud_bootstrap", side_effect=Exception("Nextcloud 503"))
    mock_alert = mocker.patch("source.main.send_admin_alert")

    with pytest.raises(ConnectionError):
        bootstrap_checks(mock_config)

    mock_alert.assert_called_once()


def test_main_test_smtp_flag(mocker):
    mocker.patch("source.main.test_smtp_connection", return_value=True)
    assert main(["--test-smtp"]) == 0

    mocker.patch("source.main.test_smtp_connection", side_effect=Exception("Failed"))
    assert main(["--test-smtp"]) == 1


def test_main_test_nextcloud_flag(mocker):
    mocker.patch("source.main.verify_nextcloud_bootstrap", return_value=mocker.MagicMock())
    assert main(["--test-nextcloud"]) == 0

    mocker.patch("source.main.verify_nextcloud_bootstrap", side_effect=Exception("Failed"))
    assert main(["--test-nextcloud"]) == 1


def test_main_heal_remote_flag(mocker):
    mocker.patch("source.main.verify_nextcloud_bootstrap")
    mock_service_cls = mocker.patch("source.main.SyncService")
    mock_service = mock_service_cls.return_value
    mock_service.heal_remote_storage.return_value = {
        "total_local_files": 10,
        "already_present": 8,
        "restored": 2,
        "errors": 0,
    }

    assert main(["--heal-remote"]) == 0
    mock_service.heal_remote_storage.assert_called_once()

    # When errors occur
    mock_service.heal_remote_storage.return_value = {
        "total_local_files": 10,
        "already_present": 5,
        "restored": 2,
        "errors": 3,
    }
    assert main(["--heal-remote"]) == 1


def test_main_bootstrap_failure(mocker):
    mocker.patch("source.main.bootstrap_checks", side_effect=Exception("Bootstrap failed"))
    assert main([]) == 1


def test_main_single_run_and_daemon(mocker):
    mocker.patch("source.main.bootstrap_checks")
    mocker.patch("source.main.SyncService")

    mock_single = mocker.patch("source.main.run_single_mode", return_value=0)
    assert main([]) == 0
    mock_single.assert_called_once()

    mock_daemon = mocker.patch("source.main.run_daemon_mode", return_value=0)
    assert main(["--daemon"]) == 0
    mock_daemon.assert_called_once()
