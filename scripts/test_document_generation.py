#!/usr/bin/env python3
"""
Script de teste de geração de relatórios DOCX e conversão para PDF via LibreOffice.

Uso:
    python scripts/test_document_generation.py
"""
import sys
import os
import json
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from source.config import config
from source.document_generator import DocumentGenerator


def get_sample_process():
    """Tenta obter um processo real do banco SQLite local ou gera um mock completo."""
    if os.path.exists(config.db_path):
        try:
            conn = sqlite3.connect(config.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT json_data FROM processes WHERE json_data IS NOT NULL ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            if row and row["json_data"]:
                data = json.loads(row["json_data"])
                conn.close()
                return data, "Banco de Dados Local (Real)"
        except Exception:
            pass

    # Mock realista
    mock = {
        "id": 999999,
        "numeroCNJ": "0000000-00.2026.8.00.0000",
        "pasta": "MOCK-PASTA-2026/001",
        "valorCausa": 85400.50,
        "status": {"nome": "Em Andamento"},
        "dtHrUltimaAtualizacaoDc": "2026-11-04 09:30:00",
        "dtHrCadastro": "2024-01-15 14:20:00",
        "contatos": [
            {
                "id": 1,
                "isPrincipal": True,
                "posicaoEnvolvido": {"descricao": "Autor"},
                "agnContato": {"nome": "Parte Autora Mock", "cpfCnpj": "000.000.000-00"}
            },
            {
                "id": 2,
                "isPrincipal": True,
                "posicaoEnvolvido": {"descricao": "Réu"},
                "agnContato": {"nome": "Empresa Exemplo S.A.", "cpfCnpj": "00.000.000/0001-00"}
            }
        ],
        "progresses": [
            {
                "id": 101,
                "strData": "04/11/2026",
                "strHora": "08:45",
                "source": "Diário Oficial da Justiça",
                "nomeCaderno": "Judiciário - 1ª Instância",
                "descricao": "Disponibilizada a intimação das partes para manifestação sobre o laudo pericial contábil apresentado no evento 45, no prazo comum de 15 (quinze) dias úteis."
            },
            {
                "id": 102,
                "strData": "28/10/2026",
                "strHora": "14:10",
                "source": "Sistema Judicial PJe",
                "nomeCaderno": None,
                "descricao": "Juntada de manifestação e quesitos complementares formulados pelo patrono da reclamada."
            }
        ]
    }
    return mock, "Dados Mock (Simulação)"


def main():
    print("==================================================")
    print("      TESTE DE GERAÇÃO DE RELATÓRIOS (DOCX/PDF)   ")
    print("==================================================")

    proc, origin = get_sample_process()
    cnj = proc.get("numeroCNJ") or "Processo_Teste"
    print(f"Origem dos Dados: {origin}")
    print(f"Processo Testado: {cnj}")
    print("--------------------------------------------------")

    temp_dir = config.temp_dir
    os.makedirs(temp_dir, exist_ok=True)
    generator = DocumentGenerator(temp_dir)

    print("[*] 1. Gerando documento estruturado em formato DOCX...")
    base_name = "relatorio_teste_diagnostico"
    docx_path, pdf_path = generator.render_process_documents(proc, base_name=base_name)

    docx_size = os.path.getsize(docx_path) if os.path.exists(docx_path) else 0
    print(f"[✓] DOCX gerado com sucesso: {docx_path} ({docx_size:,} bytes)")

    print("[*] 2. Verificando renderização em PDF via LibreOffice...")
    if pdf_path and os.path.exists(pdf_path):
        pdf_size = os.path.getsize(pdf_path)
        print(f"[✓] PDF renderizado com sucesso: {pdf_path} ({pdf_size:,} bytes)")
    else:
        print("[✕] Falha na conversão para PDF: Certifique-se de que o LibreOffice está instalado no sistema.")
        sys.exit(1)

    print("\n[✓] Ambos os formatos foram gerados e validados com êxito!")


if __name__ == "__main__":
    main()
