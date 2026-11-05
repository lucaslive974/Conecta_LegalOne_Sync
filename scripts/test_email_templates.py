#!/usr/bin/env python3
"""
Test script for rendering and dispatching transactional system emails:
1. Critical Administrator Alert (Login failure / Nextcloud failure)
2. Daily Morning Report with Magic Links and KPIs

Usage:
    python scripts/test_email_templates.py --preview              (Generates HTML files for local inspection)
    python scripts/test_email_templates.py --send-admin-alert     (Dispatches real failure alert email)
    python scripts/test_email_templates.py --send-daily-summary   (Dispatches real daily report email)
    python scripts/test_email_templates.py --send-all             (Dispatches both test emails)
"""

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from source.config import config
from source.infrastructure.email.notifier import jinja_env, send_admin_alert, send_daily_summary


def get_mock_data():
    now_str = datetime.now().strftime("%d/%m/%Y às %H:%M")
    mock_stats = {"synced": 4, "skipped": 168, "total": 172}
    mock_items = [
        {
            "cnj": "0000001-00.2026.8.00.0000",
            "partes": "Empresa Exemplo S.A. vs Estado Exemplo",
            "ultimo_andamento": f"[{now_str.split(' às ')[0]} - Diário Oficial] Publicação de despacho saneador deferindo prova pericial requerida pelas partes...",
        },
        {
            "cnj": "0000002-00.2026.5.00.0000",
            "partes": "Sindicato Exemplo vs Empresa Exemplo S.A.",
            "ultimo_andamento": f"[{now_str.split(' às ')[0]} - PJe / JT] Conclusos os autos para prolação de sentença pelo magistrado titular...",
        },
        {
            "cnj": "0000003-00.2026.8.00.0000",
            "partes": "Seguradora Exemplo vs Empresa Exemplo S.A.",
            "ultimo_andamento": f"[{now_str.split(' às ')[0]} - Sistema Judicial] Juntada de petição de acordo com quitação integral de verba indenizatória...",
        },
    ]
    magic_link_daily = "https://cloud.empresaexemplo.com.br/s/DEMO_MAGIC_LINK_1"
    magic_link_archive = "https://cloud.empresaexemplo.com.br/s/DEMO_MAGIC_LINK_2"
    return now_str, mock_stats, mock_items, magic_link_daily, magic_link_archive


def main():
    parser = argparse.ArgumentParser(description="Teste dos Templates de E-mail")
    parser.add_argument("--preview", action="store_true", help="Salva os HTMLs na pasta temp/ para inspeção local")
    parser.add_argument("--send-admin-alert", action="store_true", help="Envia e-mail real de alerta crítico de erro")
    parser.add_argument("--send-daily-summary", action="store_true", help="Envia e-mail real do relatório matinal")
    parser.add_argument("--send-all", action="store_true", help="Envia ambos os e-mails para validação na caixa postal")
    args = parser.parse_args()

    print("==================================================")
    print("      TESTE DE TEMPLATES E NOTIFICAÇÃO POR E-MAIL ")
    print("==================================================")
    print(f"Destinatário Alertas:    {config.admin_email}")
    print(f"Destinatários Relatório: {config.notification_emails}")
    print("--------------------------------------------------")

    now_str, mock_stats, mock_items, link_daily, link_archive = get_mock_data()

    if args.preview or (not args.send_admin_alert and not args.send_daily_summary and not args.send_all):
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")
        os.makedirs(out_dir, exist_ok=True)

        # 1. Render alert template
        t_alert = jinja_env.get_template("admin_alert.html")
        html_alert = t_alert.render(
            subject_title="Simulação de Falha de Login LegalOne",
            now_str=now_str,
            error_message="HTTP 401: Invalid credentials provided. Please check user or accessCode.",
            context_details="Teste de verificação do layout de emergência disparado via script de diagnóstico.",
        )
        p1 = os.path.join(out_dir, "preview_admin_alert.html")
        with open(p1, "w", encoding="utf-8") as f:
            f.write(html_alert)

        # 2. Render daily summary template
        t_summary = jinja_env.get_template("daily_summary.html")
        html_summary = t_summary.render(
            now_str=now_str,
            stats=mock_stats,
            updated_items=mock_items,
            nextcloud_folder=config.nextcloud_remote_dir,
            magic_link_daily=link_daily,
            magic_link_archive=link_archive,
        )
        p2 = os.path.join(out_dir, "preview_daily_summary.html")
        with open(p2, "w", encoding="utf-8") as f:
            f.write(html_summary)

        print("[✓] Arquivos HTML gerados para pré-visualização no navegador:")
        print(f"    - Alerta:    {p1}")
        print(f"    - Relatório: {p2}")

    if args.send_admin_alert or args.send_all:
        print("[*] Disparando e-mail de teste: ALERTA CRÍTICO DE ERRO...")
        try:
            send_admin_alert(
                config=config,
                subject_title="Simulação de Erro de Conexão",
                error_message="Erro simulado de teste: Falha temporária de comunicação com LegalOne.",
                context_details="Este é um disparo manual de verificação do sistema de alertas de emergência.",
            )
            print(f"[✓] Alerta crítico entregue com sucesso em {config.admin_email}!")
        except Exception as e:
            print(f"[✕] Falha ao enviar alerta: {e}")

    if args.send_daily_summary or args.send_all:
        print("[*] Disparando e-mail de teste: RELATÓRIO DIÁRIO EXECUTIVO...")
        try:
            send_daily_summary(
                config=config,
                stats=mock_stats,
                updated_items=mock_items,
                nextcloud_folder=config.nextcloud_remote_dir,
                magic_link_daily=link_daily,
                magic_link_archive=link_archive,
            )
            print(f"[✓] Relatório diário entregue com sucesso em {config.notification_emails}!")
        except Exception as e:
            print(f"[✕] Falha ao enviar relatório diário: {e}")

    print("\nComandos disponíveis:")
    print("  python scripts/test_email_templates.py --send-admin-alert")
    print("  python scripts/test_email_templates.py --send-daily-summary")
    print("  python scripts/test_email_templates.py --send-all")


if __name__ == "__main__":
    main()
