import pytest

from source.config import AppConfig


@pytest.fixture
def mock_config(tmp_path):
    """Provides a controlled AppConfig instance with isolated temporary paths."""
    db_file = tmp_path / "test_historico.db"
    temp_dir = tmp_path / "temp_scratch"
    temp_dir.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        legalone_email="usuario@empresa.com.br",
        legalone_password="senha_segura_123",
        legalone_access_code="CODIGO123",
        legalone_base_url="https://conecta-api.legalone.com.br",
        legalone_tenant_id="99999",
        nextcloud_url="https://nuvem.empresa.com.br",
        nextcloud_user="usuario_servico",
        nextcloud_password="app_password_xyz",
        nextcloud_remote_dir="Processos_LegalOne",
        nextcloud_verify_ssl=True,
        smtp_host="smtp.empresa.com.br",
        smtp_port=587,
        smtp_user="noreply@empresa.com.br",
        smtp_password="smtp_password_xyz",
        smtp_use_ssl=False,
        smtp_use_tls=True,
        admin_email="admin@empresa.com.br",
        notification_emails=["juridico@empresa.com.br", "diretoria@empresa.com.br"],
        db_path=str(db_file),
        temp_dir=str(temp_dir),
    )


@pytest.fixture
def sample_lawsuit_data():
    """Provides a realistic lawsuit dictionary mock."""
    return {
        "id": 1001,
        "id_adv_publication": 555,
        "numeroCNJ": "0001234-56.2026.8.13.0024",
        "pasta": "TEST-2026/001",
        "valorCausa": 50000.0,
        "status": {"nome": "Ativo"},
        "dtHrUltimaAtualizacaoDc": "2026-11-04 10:00:00",
        "dtHrCadastro": "2026-01-10 08:00:00",
        "recentActivityDate": "2026-11-04",
        "contatos": [
            {
                "id": 10,
                "isPrincipal": True,
                "posicaoEnvolvido": {"descricao": "Autor"},
                "agnContato": {"nome": "Empresa Alfa S.A.", "cpfCnpj": "00.000.000/0001-00"},
            },
            {
                "id": 20,
                "isPrincipal": True,
                "posicaoEnvolvido": {"descricao": "Réu"},
                "agnContato": {"nome": "Empresa Beta Ltda", "cpfCnpj": "11.111.111/0001-11"},
            },
            {
                "id": 30,
                "isPrincipal": False,
                "posicaoEnvolvido": {"descricao": "Advogado"},
                "agnContato": {"nome": "Dr. Advogado Interno", "cpfCnpj": "222.222.222-22"},
            },
        ],
        "recentProgresses": [
            {
                "id": 201,
                "dtHrAndamento": "2026-11-04 09:00:00",
                "strData": "04/11/2026",
                "strHora": "09:00",
                "tipoOrigem": 1,
                "source": "Diário Oficial",
                "descricao": "Publicação de despacho intimando as partes para manifestação.",
                "checksum": "chk_201",
                "caminhoPDF": None,
                "dtHrCadastro": "2026-11-04 09:05:00",
            }
        ],
    }
