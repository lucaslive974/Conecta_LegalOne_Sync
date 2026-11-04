import sys
import logging
import argparse
from source.config import config
from source.notifier import test_smtp_connection, send_admin_alert
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


def bootstrap_checks():
    """
    Executa os testes obrigatórios de inicialização.
    Falha a aplicação se os testes essenciais não passarem.
    """
    logging.info("--> Executando validação de inicialização (Bootstrap Checks)...")
    
    # 1. Validação de variáveis obrigatórias
    try:
        config.validate_essential_configs()
    except ValueError as ve:
        logging.critical("✕ Erro nas variáveis de ambiente:\n%s", ve)
        sys.exit(1)

    # 2. Teste mandatário de SMTP
    try:
        test_smtp_connection(config)
    except Exception as e:
        logging.critical("✕ FATAL: O teste de SMTP falhou. A aplicação não inicializará.\nErro: %s", e)
        sys.exit(1)

    logging.info("✓ Bootstrap concluído com sucesso.")


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="LegalOne Sync - Sincronizador Automático de Processos")
    parser.add_argument("--test-smtp", action="store_true", help="Executa apenas o teste de conectividade SMTP")
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

    # Executa validações de bootstrap (incluindo o teste de SMTP obrigatório)
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
        # Modo Padrão: Rodar e parar (ideal para chamadas via crontab / docker run / docker exec)
        try:
            service.run_sync()
            logging.info("Rotina finalizada com sucesso. Encerrando execução.")
            sys.exit(0)
        except Exception as e:
            logging.critical("✕ A rotina foi abortada devido a uma falha crítica: %s", e)
            sys.exit(1)


if __name__ == "__main__":
    main()
