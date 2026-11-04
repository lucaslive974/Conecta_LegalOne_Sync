import sys
import logging
import argparse
from source.config import config, AppConfig
from source.notifier import test_smtp_connection, send_admin_alert
from source.nextcloud_client import NextcloudClient
from source.sync_service import SyncService


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def test_nextcloud_bootstrap(app_config: AppConfig) -> NextcloudClient:
    """
    Test connectivity and authentication with Nextcloud at bootstrap.
    Raises an exception if unable to authenticate or reach the WebDAV endpoint.
    """
    logging.info("Testando conexão WebDAV com Nextcloud em %s (usuário: %s)...", app_config.nextcloud_url, app_config.nextcloud_user)
    client = NextcloudClient(
        base_url=app_config.nextcloud_url,
        user=app_config.nextcloud_user,
        password=app_config.nextcloud_password,
        verify_ssl=app_config.nextcloud_verify_ssl
    )
    client.test_connection()
    logging.info("✓ Teste de Nextcloud concluído com sucesso!")
    return client


def bootstrap_checks():
    """
    Execute mandatory bootstrap checks prior to any interaction with LegalOne:
    1. Essential configuration validation
    2. Mandatory SMTP connectivity test (aborts on failure)
    3. Mandatory Nextcloud WebDAV test (alerts admin and aborts on failure)
    """
    logging.info("--> Executando validação de inicialização (Bootstrap Checks)...")
    
    # 1. Essential environment variable validation
    try:
        config.validate_essential_configs()
    except ValueError as ve:
        logging.critical("✕ Erro nas variáveis de ambiente:\n%s", ve)
        sys.exit(1)

    # 2. Mandatory SMTP check
    try:
        test_smtp_connection(config)
    except Exception as e:
        logging.critical("✕ FATAL: O teste de SMTP falhou. A aplicação não inicializará.\nErro: %s", e)
        sys.exit(1)

    # 3. Mandatory Nextcloud check (executed before any LegalOne calls)
    try:
        test_nextcloud_bootstrap(config)
    except Exception as e:
        logging.critical("✕ FATAL: O teste de conexão com o Nextcloud falhou. A aplicação não inicializará.\nErro: %s", e)
        try:
            send_admin_alert(
                config=config,
                subject_title="Falha no Nextcloud (Bootstrap)",
                error_message=str(e),
                context_details=(
                    f"A aplicação abortou antes de consultar o LegalOne porque o Nextcloud não está acessível ou as credenciais falharam.\n"
                    f"Servidor: {config.nextcloud_url} | Usuário: {config.nextcloud_user}"
                )
            )
        except Exception as mail_err:
            logging.error("Falha ao enviar e-mail de alerta para o admin: %s", mail_err)
        sys.exit(1)

    logging.info("✓ Todos os testes de Bootstrap (SMTP e Nextcloud) foram validados com sucesso.")


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="LegalOne Sync - Sincronizador Automático de Processos")
    parser.add_argument("--test-smtp", action="store_true", help="Executa apenas o teste de conectividade SMTP")
    parser.add_argument("--test-nextcloud", action="store_true", help="Executa apenas o teste de conectividade com o Nextcloud")
    parser.add_argument("--daemon", action="store_true", help="Executa em modo agendado contínuo (daemon)")
    args = parser.parse_args()

    if args.test_smtp:
        logging.info("Executando teste exclusivo de SMTP...")
        try:
            test_smtp_connection(config)
            print("[✓] SMTP validado com sucesso!")
            sys.exit(0)
        except Exception as e:
            print(f"[✕] Falha no teste de SMTP: {e}")
            sys.exit(1)

    if args.test_nextcloud:
        logging.info("Executando teste exclusivo de Nextcloud...")
        try:
            test_nextcloud_bootstrap(config)
            print("[✓] Nextcloud validado com sucesso!")
            sys.exit(0)
        except Exception as e:
            print(f"[✕] Falha no teste de Nextcloud: {e}")
            sys.exit(1)

    # Run bootstrap checks (including SMTP and Nextcloud before starting process)
    bootstrap_checks()

    service = SyncService(config)

    if args.daemon:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
        import pytz

        hour, minute = [int(p) for p in config.schedule_time.split(":")[:2]]
        tz = pytz.timezone(config.timezone)

        scheduler = BlockingScheduler(timezone=tz)
        scheduler.add_job(
            service.run_sync,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
            id="daily_legalone_sync",
            name="Sincronização Diária LegalOne",
            replace_existing=True
        )

        logging.info("Modo daemon ativo. Próxima execução agendada para todos os dias às %s (%s).", config.schedule_time, config.timezone)
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logging.info("Serviço daemon finalizado.")
            sys.exit(0)
    else:
        # Default mode: Run and exit (ideal for crontab / docker run / docker exec)
        try:
            service.run_sync()
            logging.info("Rotina finalizada com sucesso. Encerrando execução.")
            sys.exit(0)
        except Exception as e:
            logging.critical("✕ A rotina foi abortada devido a uma falha crítica: %s", e)
            sys.exit(1)


if __name__ == "__main__":
    main()
