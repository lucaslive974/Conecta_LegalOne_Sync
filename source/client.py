import logging
import requests
from typing import Dict, Any, Optional
from source.auth import extract_tenant_id_from_jwt

logger = logging.getLogger(__name__)


class LegalOneClient:
    """HTTP client for Conecta LegalOne API."""

    def __init__(self, token: str, tenant_id: Optional[str] = None, base_url: str = "https://conecta-api.legalone.com.br"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

        clean_token = token.strip()
        if clean_token.lower().startswith("bearer "):
            clean_token = clean_token[7:].strip()

        t_id = tenant_id or extract_tenant_id_from_jwt(clean_token) or "166725"

        self.session.headers.update({
            "Authorization": f"Bearer {clean_token}",
            "x-tenant-id": t_id,
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        })

    def get_processes_page(self, page: int = 1, limit: int = 18, search_filter: str = "") -> Dict[str, Any]:
        """Fetch a paginated list of lawsuits from Conecta LegalOne API."""
        url = f"{self.base_url}/api/process"
        params = {"page": page, "limit": limit, "filter": search_filter}
        res = self.session.get(url, params=params, timeout=35)
        res.raise_for_status()
        return res.json()

    def get_process_by_publication(self, pub_id: Any) -> Dict[str, Any]:
        """Fetch detailed lawsuit information and publications by publication ID."""
        url = f"{self.base_url}/api/process/{pub_id}"
        res = self.session.get(url, timeout=35)
        res.raise_for_status()
        return res.json()
