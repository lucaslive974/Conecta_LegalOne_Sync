#!/usr/bin/env python3
"""
Script de teste de conectividade e envio SMTP.
Permite validar conexão, autenticação, simular falhas e enviar e-mail real de teste.

Uso:
    python scripts/test_smtp.py
    python scripts/test_smtp.py --send-test
    python scripts/test_smtp.py --simulate-failure
"""
import sys
import os
import argparse
from datetime import datetime

# Garante acesso aos módulos de source
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from source.config import config, AppConfig
from source.notifier import test_smtp_connection, send_email


def main():
    parser = argparse.ArgumentParser(description="Teste de Conectividade e Envio SMTP")
    parser.add_argument("--send-test", action="store_true", help="Envia um e-mail de teste real para ADMIN_EMAIL")
    parser.add_argument("--simulate-failure", action="store_true", help="Simula falha de conexão com host inválido")
    args = parser.parse_args()

    print("==================================================")
    print("      DIAGNÓSTICO E TESTE DE CONEXÃO SMTP         ")
    print("==================================================")

    target_config = config
    if args.simulate_failure:
        print("[!] MODO SIMULAÇÃO DE FALHA ATIVADO:")
        target_config = AppConfig(
            smtp_host="servidor-invalido-inexistente.com.br",
            smtp_port=587,
            smtp_user="usuario_falso",
            smtp_password="senha_errada"
        )
        print("    Simulando com host inválido:", target_config.smtp_host)

    print(f"Host:       {target_config.smtp_host}")
    print(f"Porta:      {target_config.smtp_port}")
    print(f"Usuário:    {target_config.smtp_user}")
    print(f"SSL Ativo:  {target_config.smtp_use_ssl}")
    print(f"TLS Ativo:  {target_config.smtp_use_tls}")
    print(f"Remetente:  {target_config.smtp_from}")
    print("--------------------------------------------------")

    print("[*] Iniciando teste de handshake e autenticação...")
    try:
        test_smtp_connection(target_config)
        print("[✓] SUCESSO: O servidor SMTP conectou e autenticou corretamente!")
    except Exception as e:
        print(f"[✕] FALHA IDENTIFICADA: {e}")
        if args.simulate_failure:
            print("[✓] A simulação de falha foi detectada corretamente pelo sistema.")
            sys.exit(0)
        sys.exit(1)

    if args.send_test:
        dest = config.admin_email
        if not dest:
            print("[!] Erro: ADMIN_EMAIL não está configurado no .env")
            sys.exit(1)

        print(f"[*] Enviando e-mail de teste real para: {dest}...")
        now_str = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
        subject = f"🧪 Teste de Envio SMTP - LegalOne Sync ({now_str})"
        html = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #cbd5e1; border-radius: 8px; max-width: 500px;">
            <h2 style="color: #059669; margin-top: 0;">✓ Teste SMTP Bem-Sucedido!</h2>
            <p>Este é um e-mail de teste manual disparado pelo script de diagnóstico.</p>
            <p><strong>Data/Hora do Teste:</strong> {now_str}</p>
            <p><strong>Servidor SMTP:</strong> {config.smtp_host}:{config.smtp_port}</p>
            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 16px 0;">
            <small style="color: #64748b;">Sistema Automatizado Conecta LegalOne Sync</small>
        </div>
        """
        try:
            send_email(config, [dest], subject, html, text_content=f"Teste SMTP concluído com sucesso em {now_str}")
            print(f"[✓] E-mail de teste entregue para {dest}!")
        except Exception as e:
            print(f"[✕] Falha no envio do e-mail de teste: {e}")
            sys.exit(1)

    print("\nPara enviar um e-mail real de teste, utilize: python scripts/test_smtp.py --send-test")
    print("Para simular um erro de conexão, utilize:     python scripts/test_smtp.py --simulate-failure")


if __name__ == "__main__":
    main()
