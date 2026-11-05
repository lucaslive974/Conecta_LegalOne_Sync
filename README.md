# ⚖️ Conecta LegalOne Sync (Enterprise Edition)

Enterprise service for automated synchronization, judicial monitoring, structured report generation (**DOCX** and **PDF**), and private cloud mirroring (**Nextcloud via WebDAV**), featuring real-time critical alerts and daily summary emails (**SMTP**).

---

## 🚀 Daily Operational Workflow (07:00 AM)

```
[ Host Linux / Crontab (07:00) ]
               │
               ▼
[ Docker: Bootstrap & SMTP Test ] ──(SMTP Failure)──> [ Abort Startup ]
               │ (Success)
               ▼
   [ LegalOne Authentication ] ──(Login Failure)──> [ Send Alert Email to ADMIN ]
               │ (Success)
               ▼
   [ Nextcloud WebDAV Check ] ──(Server Failure)──> [ Send Alert Email to ADMIN ]
               │ (Success)
               ▼
[ Incremental Lawsuits Scan ]
               │
       ┌───────┴────────────────────────┐
       ▼                                ▼
[ Unchanged ]                  [ New or Updated ]
       │                                │
 (Verifies Local Disk           (Fetch Detailed Progress)
 and Nextcloud Mirror)                  │
       │                                ▼
       │                    [ Save to SQLite Database ]
       │                                │
       │                                ▼
       │                    [ Generate DOCX Report ]
       │                                │
       │                                ▼
       │                    [ Render PDF via LibreOffice ]
       │                                │
       └───────┬────────────────────────┘
               ▼
[ Automatic Nextcloud Mirroring ] (Auto-heals missing remote files)
               │
               ▼
[ Send Daily Summary Email with Magic Links to Stakeholders ]
               │
               ▼
          [ Finished ]
```

---

## 📁 Project Structure

```text
Conecta_LegalOne_Sync/
├── Dockerfile                  <- Production Docker image with LibreOffice and Python 3.12+
├── docker-compose.yml          <- Service orchestration with persistent data volumes
├── pyproject.toml              <- Build system, dependencies, ruff lint and pytest-cov configuration
├── requirements.txt            <- Core Python dependencies
├── .env.example                <- Environment variables template with comprehensive documentation
├── .gitignore                  <- Protection for secrets, local databases, and temporary files
├── .venv/                      <- Local virtual environment
├── data/                       <- SQLite database persistence (legalone_sync.db)
├── storage/                    <- Permanent local backup organized by party (Processos/<Party>/)
├── temp/                       <- Temporary render workspace
├── tests/                      <- Comprehensive test suite (87+ unit tests, 92% coverage)
│   ├── test_auth.py
│   ├── test_client.py
│   ├── test_cnj_parser.py
│   ├── test_config.py
│   ├── test_database.py
│   ├── test_document_generator.py
│   ├── test_http_client.py
│   ├── test_main.py
│   ├── test_nextcloud_client.py
│   ├── test_notifier.py
│   ├── test_smtp_client.py
│   └── test_sync_service.py
└── source/                     <- Modularized clean-architecture codebase
    ├── __init__.py
    ├── config.py               <- Environment variable loading and validation
    ├── auth.py                 <- Basic Auth and JWT tenantId extraction for LegalOne
    ├── client.py               <- LegalOne API client with pluggable HTTP transport
    ├── cnj_parser.py           <- CNJ lawsuit number parser (Court, Judicial Branch, Year)
    ├── database.py             <- SQLite incremental state management with external SQL files
    ├── document_generator.py   <- Apple-style minimalist DOCX and LibreOffice headless PDF renderer
    ├── http_client.py          <- Abstract HTTPClient protocol & Requests implementation
    ├── nextcloud_client.py     <- WebDAV & OCS Share API client for Nextcloud
    ├── notifier.py             <- Email notifications & Jinja2 template rendering
    ├── smtp_client.py          <- Abstract SMTPClient protocol & Standard smtplib implementation
    ├── sync_service.py         <- Core orchestration service for incremental sync & mirroring
    ├── main.py                 <- CLI entrypoint with single-run and daemon scheduling modes
    ├── sql/                    <- Decoupled SQL schemas and queries
    │   ├── schema.sql
    │   ├── get_process_sync_info.sql
    │   ├── upsert_process.sql
    │   ├── upsert_contact.sql
    │   └── upsert_progress.sql
    └── templates/              <- Dark-mode compatible HTML email templates
        └── emails/
            ├── admin_alert.html
            └── daily_summary.html
```

---

## ☁️ Connecting to Internal Nextcloud

Nextcloud natively supports the **WebDAV** protocol. To connect and mirror lawsuit reports to your organization's private cloud, only 4 parameters are required:

1. **`NEXTCLOUD_URL`**: Your internal Nextcloud base URL (e.g., `https://nextcloud.company.local` or `http://192.168.1.100:8080`).
2. **`NEXTCLOUD_USER`**: Nextcloud username for the service account.
3. **`NEXTCLOUD_PASSWORD`**: We strongly recommend generating an **App Password**:
   - In Nextcloud, click your profile icon -> **Personal Settings**;
   - On the left navigation menu, click **Security**;
   - Scroll down to the **Devices & Sessions** section;
   - Enter an app name (e.g., `LegalOne_Sync`) and click **Create new app password**;
   - Copy the generated password and set it in `NEXTCLOUD_PASSWORD`. *(This prevents expiration if personal passwords change or when 2FA is active)*.
4. **`NEXTCLOUD_VERIFY_SSL`**:
   - Set to `false` if your internal Nextcloud uses a self-signed certificate or custom internal CA.

---

## 📧 Mandatory Bootstrap Checks (SMTP & Nextcloud)

At application startup, the service **validates connectivity to both SMTP and Nextcloud BEFORE querying LegalOne**:
1. **SMTP Test**: If the mail server does not respond or authentication fails, the application aborts immediately to prevent running without alerting capability.
2. **Nextcloud WebDAV Test**: If Nextcloud is unreachable or credentials fail, a critical alert email is dispatched immediately to `ADMIN_EMAIL` and the application aborts before contacting LegalOne.

---

## 🛠️ Step-by-Step Setup

### 1. Create the `.env` configuration file
Copy the template and fill in your credentials:
```bash
cp .env.example .env
nano .env
```

### 2. Validate connections individually
You can test each remote integration directly from the CLI:
```bash
# Validate SMTP connection
./.venv/bin/legalone-sync --test-smtp

# Validate Nextcloud WebDAV connection
./.venv/bin/legalone-sync --test-nextcloud
```

---

## 🐳 Production Deployment via Docker & Cron

The application is designed following the **run-and-exit** pattern (executes daily synchronization and terminates the container), ideal for Linux crontab scheduling.

### Build Docker image
```bash
docker compose build
```

### Run manual test execution
```bash
docker compose run --rm legalone-sync
```

### Schedule in Linux Cron (Daily at 07:00 AM)
Edit server crontab:
```bash
crontab -e
```
Add the following line:
```cron
0 7 * * * cd /path/to/Conecta_LegalOne_Sync && docker compose run --rm legalone-sync >> /var/log/legalone_sync.log 2>&1
```

---

## 🛡️ Resilience, Storage & Mirroring

1. **Local Safe Backup**:
   - All generated DOCX and PDF reports are permanently saved in `./storage/Processos/<Party_Name>/` on the host, grouped by party.
2. **Auto-healing Mirror on Nextcloud**:
   - If a user inadvertently deletes a remote folder or file in Nextcloud, the next daily execution detects the remote absence and automatically restores the file from the local disk copy.
3. **Public Magic Links**:
   - Automatically generates read-only public shares for the rotating daily folder (`Novos_e_Atualizados`) and permanent archive (`Arquivo_Geral`), included directly in the daily summary email.
4. **Incident Notifications**:
   - LegalOne authentication/login failure -> Immediate alert email to `ADMIN_EMAIL`.
   - Nextcloud connectivity/permission error -> Immediate alert email to `ADMIN_EMAIL`.
   - Successful daily execution -> Executive summary email with KPIs, court identifiers, and recent progress to `NOTIFICATION_EMAILS`.

---

## 🧪 Testing & Code Quality

The project features a comprehensive unit test suite with 92% statement coverage and strict Ruff linting:

```bash
# Run all unit tests with coverage report
./.venv/bin/pytest

# Check code linting with Ruff
./.venv/bin/ruff check source/ tests/

# Test report generation locally
./.venv/bin/python scripts/test_document_generation.py

# Preview email templates in browser
./.venv/bin/python scripts/test_email_templates.py
```
