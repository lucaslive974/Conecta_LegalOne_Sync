#!/usr/bin/env python3
"""
Script de teste de conectividade, WebDAV, Magic Links e rotação no Nextcloud.
Permite validar o fluxo WebDAV completo ou simular falhas de autenticação.

Uso:
    python scripts/test_nextcloud.py
    python scripts/test_nextcloud.py --full-crud
    python scripts/test_nextcloud.py --simulate-failure
"""
import sys
import os
import argparse
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from source.config import config
from source.nextcloud_client import NextcloudClient


def main():
    parser = argparse.ArgumentParser(description="Teste de Integração com Nextcloud")
    parser.add_argument("--full-crud", action="store_true", help="Executa ciclo completo: upload, link, move e deleção de teste")
    parser.add_argument("--simulate-failure", action="store_true", help="Simula falha de autenticação com credenciais incorretas")
    args = parser.parse_args()

    print("==================================================")
    print("      DIAGNÓSTICO E TESTE DE CONEXÃO NEXTCLOUD    ")
    print("==================================================")

    url = config.nextcloud_url
    user = config.nextcloud_user
    pwd = config.nextcloud_password
    ssl_verify = config.nextcloud_verify_ssl

    if args.simulate_failure:
        print("[!] MODO SIMULAÇÃO DE FALHA ATIVADO:")
        pwd = "senha_completamente_incorreta_123"
        print("    Simulando com senha incorreta para o usuário:", user)

    print(f"Servidor:    {url}")
    print(f"Usuário:     {user}")
    print(f"Verificar SSL: {ssl_verify}")
    print(f"Pasta Raiz:  {config.nextcloud_remote_dir}")
    print("--------------------------------------------------")

    nc = NextcloudClient(url, user, pwd, ssl_verify)

    print("[*] 1. Testando autenticação WebDAV (PROPFIND)...")
    try:
        nc.test_connection()
        print("[✓] Autenticação WebDAV aprovada com sucesso!")
    except Exception as e:
        print(f"[✕] FALHA NA CONEXÃO: {e}")
        if args.simulate_failure:
            print("[✓] A simulação de falha foi detectada corretamente pelo sistema.")
            sys.exit(0)
        sys.exit(1)

    # 2. Teste de pastas e Magic Links
    print("[*] 2. Validando estrutura de pastas e Magic Links...")
    daily_folder = f"{config.nextcloud_remote_dir}/Novos_e_Atualizados"
    archive_folder = f"{config.nextcloud_remote_dir}/Arquivo_Geral"

    try:
        nc.ensure_directory(daily_folder)
        nc.ensure_directory(archive_folder)
        print(f"[✓] Pastas garantidas: '{daily_folder}' e '{archive_folder}'")

        link_daily = nc.get_or_create_public_share(daily_folder)
        link_archive = nc.get_or_create_public_share(archive_folder)
        print(f"[✓] Magic Link (Processos do Dia): {link_daily}")
        print(f"[✓] Magic Link (Acervo Geral):    {link_archive}")
    except Exception as e:
        print(f"[✕] Falha ao criar/obter Magic Links: {e}")
        sys.exit(1)

    # 3. Teste completo de CRUD se solicitado
    if args.full_crud:
        print("[*] 3. Executando teste prático de Upload, Move e Remoção...")
        test_file = os.path.join(tempfile.gettempdir(), "nc_test_sample.txt")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("Arquivo temporário para teste automatizado do Nextcloud.")

        try:
            rel_src = f"{daily_folder}/teste_crud.txt"
            rel_dst = f"{archive_folder}/teste_crud_arquivado.txt"

            # Upload
            print(f"    - Enviando arquivo de teste para {rel_src}...")
            nc.upload_file(test_file, rel_src)
            assert nc.exists(rel_src), "O arquivo não foi localizado após upload."
            print("    [✓] Upload WebDAV concluído.")

            # Move
            print(f"    - Movendo para {rel_dst}...")
            moved = nc.move_item(rel_src, rel_dst)
            assert moved, "Comando MOVE falhou."
            assert nc.exists(rel_dst), "Arquivo de destino não existe após MOVE."
            print("    [✓] Movimentação WebDAV MOVE concluída.")

            # Delete
            print(f"    - Limpando arquivo de teste {rel_dst}...")
            deleted = nc.delete_item(rel_dst)
            assert deleted, "Comando DELETE falhou."
            print("    [✓] Deleção de limpeza concluída.")

            print("[✓] Ciclo completo de operações WebDAV aprovado!")
        except Exception as e:
            print(f"[✕] Falha nas operações CRUD: {e}")
            sys.exit(1)
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    print("\nPara executar o ciclo completo de Upload/Move/Delete: python scripts/test_nextcloud.py --full-crud")
    print("Para simular uma falha de autenticação:             python scripts/test_nextcloud.py --simulate-failure")


if __name__ == "__main__":
    main()
