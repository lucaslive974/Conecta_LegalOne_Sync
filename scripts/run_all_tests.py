#!/usr/bin/env python3
"""
Suíte unificada de testes e diagnósticos do Conecta LegalOne Sync.
Executa todos os testes unitários e de integração em sequência.

Uso:
    python scripts/run_all_tests.py
"""
import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def run_subtest(title: str, script_name: str, args: list = None) -> bool:
    print(f"\n▶ Executando: {title}...")
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, script_name)] + (args or [])
    res = subprocess.run(cmd)
    return res.returncode == 0


def main():
    print("==================================================")
    print("   SUÍTE UNIFICADA DE TESTES DO CONECTA LEGALONE  ")
    print("==================================================")

    results = {}

    # 1. Teste SMTP
    results["1. Conexão SMTP (Porta 465 SSL)"] = run_subtest(
        "Teste de Conexão e Autenticação SMTP", "test_smtp.py"
    )

    # 2. Teste Nextcloud WebDAV + Magic Links
    results["2. Nextcloud WebDAV & Magic Links"] = run_subtest(
        "Teste de WebDAV e Magic Links do Nextcloud", "test_nextcloud.py", ["--full-crud"]
    )

    # 3. Teste Geração DOCX + PDF
    results["3. Renderização DOCX e PDF (LibreOffice)"] = run_subtest(
        "Teste de Formatação DOCX e PDF", "test_document_generation.py"
    )

    # 4. Teste Templates de E-mail
    results["4. Templates HTML Jinja2"] = run_subtest(
        "Teste de Templates de E-mail (Preview)", "test_email_templates.py", ["--preview"]
    )

    # Resumo Final
    print("\n" + "=" * 50)
    print("                 RESUMO DOS TESTES                ")
    print("=" * 50)
    all_passed = True
    for name, passed in results.items():
        status = "[✓] APROVADO" if passed else "[✕] FALHOU"
        if not passed:
            all_passed = False
        print(f" {name:<40} {status}")
    print("=" * 50)

    if all_passed:
        print("🎉 TODOS OS MÓDULOS FORAM TESTADOS E VALIDADOS COM SUCESSO!")
        sys.exit(0)
    else:
        print("⚠️ ALGUNS TESTES FALHARAM. VERIFIQUE AS MENSAGENS ACIMA.")
        sys.exit(1)


if __name__ == "__main__":
    main()
