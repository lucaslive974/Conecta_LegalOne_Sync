import json
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load environment variables from a .env file if present
load_dotenv()


def _str_to_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "sim", "s", "y")


def _parse_email_list(val: str | None) -> list[str]:
    if not val:
        return []
    val = val.strip()
    if val.startswith("[") and val.endswith("]"):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(e).strip() for e in parsed if str(e).strip()]
        except Exception:
            pass
    # Comma or semicolon separation
    return [e.strip() for e in val.replace(";", ",").split(",") if e.strip()]


def _parse_int_optional(val: str | None) -> int | None:
    if not val:
        return None
    try:
        return int(val.strip())
    except ValueError:
        return None


def _get_default_base_dir() -> str:
    """Determine reliable base directory for data, storage, and temp folders."""
    # Running inside Docker container with /app mount points
    if os.path.exists("/app/storage") and os.path.exists("/app/data"):
        return "/app"
    # Running in repository working directory
    cwd = os.getcwd()
    if os.path.exists(os.path.join(cwd, "source")):
        return cwd
    # Fallback to source parent directory
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class AppConfig:
    # LegalOne
    legalone_email: str = field(default_factory=lambda: os.getenv("LEGALONE_EMAIL", ""))
    legalone_password: str = field(default_factory=lambda: os.getenv("LEGALONE_PASSWORD", ""))
    legalone_access_code: str = field(default_factory=lambda: os.getenv("LEGALONE_ACCESS_CODE", ""))
    legalone_base_url: str = field(
        default_factory=lambda: os.getenv("LEGALONE_BASE_URL", "https://conecta-api.legalone.com.br")
    )
    legalone_tenant_id: str | None = field(default_factory=lambda: os.getenv("LEGALONE_TENANT_ID") or None)

    # Nextcloud
    nextcloud_url: str = field(default_factory=lambda: os.getenv("NEXTCLOUD_URL", "").rstrip("/"))
    nextcloud_user: str = field(default_factory=lambda: os.getenv("NEXTCLOUD_USER", ""))
    nextcloud_password: str = field(default_factory=lambda: os.getenv("NEXTCLOUD_PASSWORD", ""))
    nextcloud_remote_dir: str = field(
        default_factory=lambda: os.getenv("NEXTCLOUD_REMOTE_DIR", "Processos_LegalOne").strip("/")
    )
    nextcloud_verify_ssl: bool = field(
        default_factory=lambda: _str_to_bool(os.getenv("NEXTCLOUD_VERIFY_SSL"), default=True)
    )

    # SMTP Notifier
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    smtp_use_tls: bool = field(default_factory=lambda: _str_to_bool(os.getenv("SMTP_USE_TLS"), default=True))
    smtp_use_ssl: bool = field(default_factory=lambda: _str_to_bool(os.getenv("SMTP_USE_SSL"), default=False))
    smtp_from: str = field(default_factory=lambda: os.getenv("SMTP_FROM", "LegalOne Sync <noreply@empresa.com.br>"))
    admin_email: str = field(default_factory=lambda: os.getenv("ADMIN_EMAIL", ""))
    notification_emails: list[str] = field(
        default_factory=lambda: _parse_email_list(os.getenv("NOTIFICATION_EMAILS", ""))
    )

    # Scheduler & paths
    storage_dir: str = field(
        default_factory=lambda: os.getenv("STORAGE_DIR", os.path.join(_get_default_base_dir(), "storage"))
    )
    db_path: str = field(
        default_factory=lambda: os.getenv(
            "DB_PATH", os.path.join(_get_default_base_dir(), "data", "historico_processos.db")
        )
    )
    temp_dir: str = field(default_factory=lambda: os.getenv("TEMP_DIR", os.path.join(_get_default_base_dir(), "temp")))
    schedule_time: str = field(default_factory=lambda: os.getenv("SCHEDULE_TIME", "07:00"))
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "America/Sao_Paulo"))
    run_on_startup: bool = field(default_factory=lambda: _str_to_bool(os.getenv("RUN_ON_STARTUP"), default=False))
    page_limit: int = field(default_factory=lambda: int(os.getenv("PAGE_LIMIT", "50")))
    max_pages: int | None = field(default_factory=lambda: _parse_int_optional(os.getenv("MAX_PAGES")))

    def validate_essential_configs(self):
        """Validate that essential configurations required for operation are present."""
        errors = []
        if not self.legalone_email:
            errors.append("LEGALONE_EMAIL não configurado.")
        if not self.legalone_password:
            errors.append("LEGALONE_PASSWORD não configurado.")
        if not self.legalone_access_code:
            errors.append("LEGALONE_ACCESS_CODE não configurado.")

        if not self.nextcloud_url:
            errors.append("NEXTCLOUD_URL não configurado.")
        if not self.nextcloud_user:
            errors.append("NEXTCLOUD_USER não configurado.")
        if not self.nextcloud_password:
            errors.append("NEXTCLOUD_PASSWORD não configurado.")

        if not self.smtp_host:
            errors.append("SMTP_HOST não configurado.")
        if not self.admin_email:
            errors.append("ADMIN_EMAIL não configurado (necessário para alertas de falha).")

        if errors:
            raise ValueError("Erros de configuração de ambiente:\n - " + "\n - ".join(errors))


config = AppConfig()
