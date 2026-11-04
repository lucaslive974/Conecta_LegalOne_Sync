import os
import logging
import urllib.parse
from typing import Optional
import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


class NextcloudClient:
    """Cliente WebDAV para integração com Nextcloud."""

    def __init__(self, base_url: str, user: str, password: str, verify_ssl: bool = True):
        self.base_url = base_url.rstrip("/")
        self.user = user
        self.password = password
        self.verify_ssl = verify_ssl
        self.auth = HTTPBasicAuth(self.user, self.password)
        # Endpoint padrão WebDAV do Nextcloud
        self.dav_base_url = f"{self.base_url}/remote.php/dav/files/{urllib.parse.quote(self.user)}"
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.verify = self.verify_ssl

    def test_connection(self) -> bool:
        """
        Testa a conectividade com o Nextcloud enviando um PROPFIND para a raiz do usuário.
        Retorna True se autenticado com sucesso, ou levanta exceção explicativa.
        """
        headers = {"Depth": "0"}
        try:
            res = self.session.request("PROPFIND", self.dav_base_url + "/", headers=headers, timeout=15)
            if res.status_code in (200, 207):
                logger.info("Conexão WebDAV com Nextcloud validada com sucesso.")
                return True
            elif res.status_code in (401, 403):
                raise PermissionError(f"Falha de autenticação no Nextcloud ({res.status_code}): Verifique usuário ou senha de aplicativo (App Password).")
            else:
                raise ConnectionError(f"Nextcloud retornou código inesperado {res.status_code} no teste de conexão.")
        except requests.RequestException as e:
            logger.error("Erro de rede ao conectar no Nextcloud (%s): %s", self.base_url, e)
            raise ConnectionError(f"Não foi possível alcançar o servidor Nextcloud: {e}") from e

    def exists(self, remote_rel_path: str) -> bool:
        """
        Verifica se um arquivo ou diretório existe no Nextcloud via PROPFIND.
        """
        clean_path = remote_rel_path.strip("/")
        remote_url = f"{self.dav_base_url}/{urllib.parse.quote(clean_path)}"
        try:
            res = self.session.request("PROPFIND", remote_url, headers={"Depth": "0"}, timeout=12)
            return res.status_code in (200, 207)
        except Exception as e:
            logger.debug("Erro ao checar existência de %s no Nextcloud: %s", remote_rel_path, e)
            return False

    def ensure_directory(self, remote_dir: str):
        """
        Garante recursivamente que a estrutura de diretórios remotos existe no Nextcloud.
        """
        clean_path = remote_dir.strip("/")
        if not clean_path:
            return

        parts = clean_path.split("/")
        current = ""
        for p in parts:
            if not p:
                continue
            current = f"{current}/{p}" if current else p
            folder_url = f"{self.dav_base_url}/{urllib.parse.quote(current)}/"
            try:
                res = self.session.request("MKCOL", folder_url, timeout=20)
                # 201 = criado, 405 = já existe, 301/200 também aceitáveis
                if res.status_code not in (201, 405):
                    logger.debug("MKCOL %s retornou status %s", folder_url, res.status_code)
            except Exception as e:
                logger.warning("Falha ao criar diretório remoto %s: %s", folder_url, e)

    def upload_file(self, local_path: str, remote_rel_path: str) -> str:
        """
        Faz upload de um arquivo local para o caminho remoto no Nextcloud via PUT.
        Retorna a URL remota de destino.
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Arquivo local não encontrado: {local_path}")

        # Garante que o diretório pai remoto exista
        remote_dir = os.path.dirname(remote_rel_path)
        if remote_dir:
            self.ensure_directory(remote_dir)

        remote_url = f"{self.dav_base_url}/{urllib.parse.quote(remote_rel_path)}"
        file_size = os.path.getsize(local_path)

        with open(local_path, "rb") as f:
            headers = {"Content-Type": "application/octet-stream"}
            res = self.session.put(remote_url, data=f, headers=headers, timeout=60)
            if res.status_code not in (200, 201, 204):
                raise IOError(f"Falha ao enviar arquivo para Nextcloud ({res.status_code}): {res.text[:200]}")

        logger.info("Upload concluído para Nextcloud: %s (%s bytes)", remote_rel_path, file_size)
        return remote_url
