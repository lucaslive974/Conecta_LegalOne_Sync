import logging
import os
import urllib.parse
import xml.etree.ElementTree as ET

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


class NextcloudClient:
    """WebDAV and OCS Share client for Nextcloud integration."""

    def __init__(self, base_url: str, user: str, password: str, verify_ssl: bool = True):
        self.base_url = base_url.rstrip("/")
        self.user = user
        self.password = password
        self.verify_ssl = verify_ssl
        self.auth = HTTPBasicAuth(self.user, self.password)

        # Default Nextcloud WebDAV endpoint
        self.dav_base_url = f"{self.base_url}/remote.php/dav/files/{urllib.parse.quote(self.user)}"
        # Nextcloud OCS Share API endpoint for Magic Links
        self.ocs_share_url = f"{self.base_url}/ocs/v2.php/apps/files_sharing/api/v1/shares"

        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.verify = self.verify_ssl

    def test_connection(self) -> bool:
        """
        Test connectivity with Nextcloud by sending a PROPFIND to the user root.
        Returns True on successful authentication or raises an explanatory exception.
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
        Check if a file or directory exists on Nextcloud via PROPFIND.
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
        Recursively ensure remote directory structure exists on Nextcloud.
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
                if res.status_code not in (201, 405):
                    logger.debug("MKCOL %s retornou status %s", folder_url, res.status_code)
            except Exception as e:
                logger.warning("Falha ao criar diretório remoto %s: %s", folder_url, e)

    def upload_file(self, local_path: str, remote_rel_path: str) -> str:
        """
        Upload a local file to the remote path on Nextcloud via PUT.
        Returns the remote destination URL.
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Arquivo local não encontrado: {local_path}")

        # Ensure parent remote directory exists
        remote_dir = os.path.dirname(remote_rel_path)
        if remote_dir:
            self.ensure_directory(remote_dir)

        remote_url = f"{self.dav_base_url}/{urllib.parse.quote(remote_rel_path)}"
        file_size = os.path.getsize(local_path)

        with open(local_path, "rb") as f:
            headers = {"Content-Type": "application/octet-stream"}
            res = self.session.put(remote_url, data=f, headers=headers, timeout=60)
            if res.status_code not in (200, 201, 204):
                raise OSError(f"Falha ao enviar arquivo para Nextcloud ({res.status_code}): {res.text[:200]}")

        logger.info("Upload concluído para Nextcloud: %s (%s bytes)", remote_rel_path, file_size)
        return remote_url

    def list_subitems(self, remote_rel_path: str) -> list[str]:
        """
        List relative paths of subitems (files and folders) within a remote directory.
        Excludes the parent directory itself.
        """
        clean_path = remote_rel_path.strip("/")
        folder_url = f"{self.dav_base_url}/{urllib.parse.quote(clean_path)}/"
        headers = {"Depth": "1"}

        try:
            res = self.session.request("PROPFIND", folder_url, headers=headers, timeout=15)
            if res.status_code not in (200, 207):
                return []

            root = ET.fromstring(res.content)
            ns = {"d": "DAV:"}
            prefix = f"/remote.php/dav/files/{self.user}/{clean_path}/".lower()

            items = []
            for resp in root.findall("d:response", ns):
                href_el = resp.find("d:href", ns)
                if href_el is None or not href_el.text:
                    continue
                raw_href = urllib.parse.unquote(href_el.text)
                if raw_href.rstrip("/").lower() != prefix.rstrip("/"):
                    # Extract relative path inside clean_path
                    idx = raw_href.lower().find(prefix)
                    if idx != -1:
                        rel = raw_href[idx + len(prefix):].strip("/")
                        if rel:
                            items.append(rel)
            return sorted(set(items))
        except Exception as e:
            logger.warning("Falha ao listar subitens de %s no Nextcloud: %s", remote_rel_path, e)
            return []

    def move_item(self, source_rel_path: str, dest_rel_path: str, overwrite: bool = True) -> bool:
        """Move or rename a file/folder on Nextcloud via WebDAV MOVE."""
        clean_src = source_rel_path.strip("/")
        clean_dst = dest_rel_path.strip("/")

        dest_dir = os.path.dirname(clean_dst)
        if dest_dir:
            self.ensure_directory(dest_dir)

        src_url = f"{self.dav_base_url}/{urllib.parse.quote(clean_src)}"
        dst_url = f"{self.dav_base_url}/{urllib.parse.quote(clean_dst)}"

        headers = {
            "Destination": dst_url,
            "Overwrite": "T" if overwrite else "F"
        }
        try:
            res = self.session.request("MOVE", src_url, headers=headers, timeout=30)
            if res.status_code in (201, 204):
                logger.debug("Movido com sucesso no Nextcloud: %s -> %s", clean_src, clean_dst)
                return True
            else:
                logger.warning("MOVE retornou status %s para %s -> %s", res.status_code, clean_src, clean_dst)
                return False
        except Exception as e:
            logger.error("Erro ao mover item %s para %s no Nextcloud: %s", clean_src, clean_dst, e)
            return False

    def delete_item(self, remote_rel_path: str) -> bool:
        """Delete a file or directory from Nextcloud via WebDAV DELETE."""
        clean_path = remote_rel_path.strip("/")
        url = f"{self.dav_base_url}/{urllib.parse.quote(clean_path)}"
        try:
            res = self.session.delete(url, timeout=20)
            return res.status_code in (200, 204)
        except Exception as e:
            logger.error("Erro ao deletar item %s no Nextcloud: %s", remote_rel_path, e)
            return False

    def get_or_create_public_share(self, remote_rel_path: str) -> str | None:
        """
        Get or create a public read-only Magic Link for a Nextcloud directory
        via Nextcloud OCS Share API.
        """
        clean_path = remote_rel_path.strip("/")
        self.ensure_directory(clean_path)

        headers = {
            "OCS-APIRequest": "true",
            "Accept": "application/json"
        }

        # 1. Check if an active public share already exists for this folder
        try:
            res = self.session.get(self.ocs_share_url, headers=headers, params={"path": f"/{clean_path}"}, timeout=15)
            if res.status_code == 200:
                shares = res.json().get("ocs", {}).get("data", [])
                for s in shares:
                    if s.get("share_type") == 3 or s.get("url"):
                        logger.info("Magic Link público existente reutilizado: %s", s.get("url"))
                        return s.get("url")
        except Exception as e:
            logger.warning("Erro ao consultar shares existentes para %s: %s", clean_path, e)

        # 2. Otherwise create a new public share (shareType: 3, permissions: 1 = read-only)
        try:
            payload = {
                "path": f"/{clean_path}",
                "shareType": 3,
                "permissions": 1
            }
            res = self.session.post(self.ocs_share_url, headers=headers, data=payload, timeout=15)
            if res.status_code == 200:
                data = res.json().get("ocs", {}).get("data", {})
                url = data.get("url")
                logger.info("Novo Magic Link público gerado com sucesso: %s", url)
                return url
            else:
                logger.warning("Falha ao criar Magic Link no Nextcloud (%s): %s", res.status_code, res.text[:200])
        except Exception as e:
            logger.error("Erro na criação de Magic Link no Nextcloud para %s: %s", clean_path, e)

        return None

    def archive_previous_daily_updates(self, daily_folder_rel: str, archive_folder_rel: str):
        """
        Clear the daily rotating folder 'Novos_e_Atualizados' by moving older items
        into permanent 'Arquivo_Geral', preserving the root folder and its public Magic Link.
        """
        clean_daily = daily_folder_rel.strip("/")
        clean_archive = archive_folder_rel.strip("/")

        subitems = self.list_subitems(clean_daily)
        if not subitems:
            logger.info("A pasta rotativa diária '%s' já está limpa para a nova rodada.", clean_daily)
            return

        logger.info("Movendo %s item(ns) da rodada anterior para o arquivo permanente...", len(subitems))
        for item in subitems:
            src = f"{clean_daily}/{item}"
            dst = f"{clean_archive}/{item}"
            # If it is a top-level item (e.g. process file/folder)
            if "/" not in item:
                self.move_item(src, dst)
            else:
                self.delete_item(src)
        logger.info("Pasta rotativa '%s' pronta e desocupada para os novos arquivos.", clean_daily)
