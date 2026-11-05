import base64
import json
import logging
from typing import Any

from source.infrastructure.network.http_client import HTTPClient, RequestsHTTPClient

logger = logging.getLogger(__name__)

DEFAULT_LOGIN_URL = "https://conecta-api.legalone.com.br/api/auth/login"


def extract_tenant_id_from_jwt(token: str) -> str | None:
    """Automatically extract tenantId from JWT Bearer payload."""
    try:
        clean = token.strip()
        if clean.lower().startswith("bearer "):
            clean = clean[7:].strip()
        parts = clean.split(".")
        if len(parts) >= 2:
            padding = 4 - (len(parts[1]) % 4)
            if padding and padding != 4:
                parts[1] += "=" * padding
            decoded = base64.b64decode(parts[1]).decode("utf-8")
            data = json.loads(decoded)
            tenant = data.get("tenantId")
            if tenant:
                return str(tenant)
    except Exception as e:
        logger.debug("Falha ao extrair tenantId do JWT: %s", e)
    return None


def login_legalone(
    email: str,
    password: str,
    access_code: str,
    base_url: str | None = None,
    http_client: HTTPClient | None = None,
) -> dict[str, Any]:
    """
    Authenticate against the Conecta LegalOne API.

    Expected Header: Authorization: Basic <base64(email:password)>
    JSON Body: {"accessCode": "<access code>"}
    """
    user_pass = f"{email.strip()}:{password}".encode()
    basic_token = base64.b64encode(user_pass).decode("utf-8")

    login_url = f"{base_url.rstrip('/')}/api/auth/login" if base_url else DEFAULT_LOGIN_URL

    headers = {
        "Authorization": f"Basic {basic_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        ),
    }

    payload = {"accessCode": access_code.strip()}

    client = http_client or RequestsHTTPClient()
    try:
        res = client.post(login_url, headers=headers, json=payload, timeout=25)
    except Exception as exc:
        logger.error("Erro de conexão ao tentar autenticar no LegalOne: %s", exc)
        raise ConnectionError(f"Falha de rede ao acessar LegalOne: {exc}") from exc

    try:
        data = res.json() if res.content else {}
    except Exception:
        data = {}

    if res.status_code != 200:
        error_msg = data.get("message") or data.get("error") or f"Erro HTTP {res.status_code} na autenticação LegalOne."
        logger.error("Falha na autenticação LegalOne: %s (Status: %s)", error_msg, res.status_code)
        raise ValueError(error_msg)

    # Extract token from root or nested 'data' object
    token = data.get("token") or (data.get("data") if isinstance(data.get("data"), dict) else {}).get("token")
    if not token and isinstance(data, dict):
        for k in ("token", "jwt", "accessToken", "access_token"):
            if k in data:
                token = data[k]
                break

    if token and "token" not in data:
        data["token"] = token

    logger.info("Autenticação com LegalOne realizada com sucesso.")
    return data
