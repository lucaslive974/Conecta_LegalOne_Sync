import argparse
import logging
import sys

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from source.config import AppConfig, config
from source.infrastructure.email.notifier import send_admin_alert, test_smtp_connection
from source.infrastructure.nextcloud.client import NextcloudClient
from source.services.sync_service import SyncService


def setup_logging():
    """Configure standard application logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def parse_schedule_time(schedule_time: str) -> tuple[int, int]:
    """
    Parse an 'HH:MM' time string into an (hour, minute) tuple.
    Raises ValueError on invalid formats.
    """
    clean = schedule_time.strip()
    parts = clean.split(":")
    if len(parts) < 2:
        raise ValueError(f"Formato de horário inválido: '{schedule_time}'. Esperado 'HH:MM'.")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Horário fora dos limites válidos (00:00 - 23:59): '{schedule_time}'")
        return hour, minute
    except ValueError as e:
        if "invalid literal" in str(e):
            raise ValueError(f"Valores não numéricos no horário: '{schedule_time}'") from e
        raise


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI command line arguments."""
    parser = argparse.ArgumentParser(
        description="LegalOne Sync - Sincronizador Automático de Processos"
    )
    parser.add_argument(
        "--test-smtp",
        action="store_true",
        help="Executa apenas o teste de conectividade SMTP",
    )
    parser.add_argument(
        "--test-nextcloud",
        action="store_true",
        help="Executa apenas o teste de conectividade com o Nextcloud",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Executa em modo agendado contínuo (daemon)",
    )
    return parser.parse_args(args)


def verify_nextcloud_bootstrap(app_config: AppConfig) -> NextcloudClient:
    """
    Test connectivity and authentication with Nextcloud at bootstrap.
    Raises an exception if unable to authenticate or reach the WebDAV endpoint.
    """
    logging.info(
        "Testando conexão WebDAV com Nextcloud em %s (usuário: %s)...",
        app_config.nextcloud_url,
        app_config.nextcloud_user,
    )
    client = NextcloudClient(
        base_url=app_config.nextcloud_url,
        user=app_config.nextcloud_user,
        password=app_config.nextcloud_password,
        verify_ssl=app_config.nextcloud_verify_ssl,
    )
    client.test_connection()
    logging.info("✓ Teste de Nextcloud concluído com sucesso!")
    return client


def bootstrap_checks(app_config: AppConfig) -> None:
    """
    Execute mandatory bootstrap checks prior to any interaction with LegalOne:
    1. Essential configuration validation
    2. Mandatory SMTP connectivity test (aborts on failure)
    3. Mandatory Nextcloud WebDAV test (alerts admin and aborts on failure)
    """
    logging.info("--> Executando validação de inicialização (Bootstrap Checks)...")

    # 1. Essential environment variable validation
    app_config.validate_essential_configs()

    # 2. Mandatory SMTP check
    try:
        test_smtp_connection(app_config)
    except Exception as e:
        logging.critical("✕ FATAL: O teste de SMTP falhou. A aplicação não inicializará.\nErro: %s", e)
        raise ConnectionError(f"Falha de conexão SMTP no bootstrap: {e}") from e

    # 3. Mandatory Nextcloud check
    try:
        verify_nextcloud_bootstrap(app_config)
    except Exception as e:
        logging.critical("✕ FATAL: O teste de conexão com o Nextcloud falhou. A aplicação não inicializará.\nErro: %s", e)
        try:
            send_admin_alert(
                config=app_config,
                subject_title="Falha no Nextcloud (Bootstrap)",
                error_message=str(e),
                context_details=(
                    f"A aplicação abortou antes de consultar o LegalOne porque o Nextcloud não está acessível ou as credenciais falharam.\n"
                    f"Servidor: {app_config.nextcloud_url} | Usuário: {app_config.nextcloud_user}"
                ),
            )
        except Exception as mail_err:
            logging.error("Falha ao enviar e-mail de alerta para o admin: %s", mail_err)
        raise ConnectionError(f"Falha de conexão Nextcloud no bootstrap: {e}") from e

    logging.info("✓ Todos os testes de Bootstrap (SMTP e Nextcloud) foram validados com sucesso.")


def run_single_mode(service: SyncService) -> int:
    """
    Execute a single synchronization cycle and return process exit code.
    Returns 0 on success, 1 on critical failure.
    """
    try:
        service.run_sync()
        logging.info("Rotina finalizada com sucesso. Encerrando execução.")
        return 0
    except Exception as e:
        logging.critical("✕ A rotina foi abortada devido a uma falha crítica: %s", e)
        return 1


def create_daemon_scheduler(
    service: SyncService,
    schedule_time: str,
    timezone_name: str,
) -> BlockingScheduler:
    """
    Build and configure BlockingScheduler with daily cron trigger for LegalOne sync.
    """
    hour, minute = parse_schedule_time(schedule_time)
    tz = pytz.timezone(timezone_name)

    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        service.run_sync,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
        id="daily_legalone_sync",
        name="Sincronização Diária LegalOne",
        replace_existing=True,
    )
    return scheduler


def run_daemon_mode(
    service: SyncService,
    schedule_time: str,
    timezone_name: str,
) -> int:
    """
    Execute daemon mode with BlockingScheduler.
    """
    scheduler = create_daemon_scheduler(service, schedule_time, timezone_name)
    logging.info(
        "Modo daemon ativo. Próxima execução agendada para todos os dias às %s (%s).",
        schedule_time,
        timezone_name,
    )
    try:
        scheduler.start()
        return 0
    except (KeyboardInterrupt, SystemExit):
        logging.info("Serviço daemon finalizado.")
        return 0


def main(args_list: list[str] | None = None) -> int:
    """Application CLI entrypoint orchestrating execution modes."""
    setup_logging()
    args = parse_args(args_list)

    if args.test_smtp:
        logging.info("Executando teste exclusivo de SMTP...")
        try:
            test_smtp_connection(config)
            print("[✓] SMTP validado com sucesso!")
            return 0
        except Exception as e:
            print(f"[✕] Falha no teste de SMTP: {e}")
            return 1

    if args.test_nextcloud:
        logging.info("Executando teste exclusivo de Nextcloud...")
        try:
            verify_nextcloud_bootstrap(config)
            print("[✓] Nextcloud validado com sucesso!")
            return 0
        except Exception as e:
            print(f"[✕] Falha no teste de Nextcloud: {e}")
            return 1

    try:
        bootstrap_checks(config)
    except Exception as e:
        logging.critical("Falha nos testes de inicialização: %s", e)
        return 1

    service = SyncService(config)

    if args.daemon:
        return run_daemon_mode(service, config.schedule_time, config.timezone)

    return run_single_mode(service)


if __name__ == "__main__":
    sys.exit(main())
