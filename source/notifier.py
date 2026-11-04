import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Any, Optional

from source.config import AppConfig

logger = logging.getLogger(__name__)


def test_smtp_connection(config: AppConfig) -> bool:
    """
    Testa a conexão e autenticação com o servidor SMTP no bootstrap.
    Falha e levanta exceção se não conseguir conectar ou autenticar.
    """
    if not config.smtp_host:
        raise ValueError("SMTP_HOST não foi configurado.")

    logger.info("Testando conexão SMTP com %s:%s...", config.smtp_host, config.smtp_port)
    try:
        if config.smtp_use_ssl:
            server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15)

        server.ehlo()
        if config.smtp_use_tls and not config.smtp_use_ssl:
            server.starttls()
            server.ehlo()

        if config.smtp_user and config.smtp_password:
            server.login(config.smtp_user, config.smtp_password)

        server.quit()
        logger.info("✓ Teste de SMTP concluído com sucesso!")
        return True
    except Exception as e:
        logger.critical("✕ FALHA NO TESTE DE SMTP: Não foi possível conectar ao servidor de e-mail: %s", e)
        raise ConnectionError(f"Falha de conexão SMTP no bootstrap: {e}") from e


def send_email(config: AppConfig, to_addresses: List[str], subject: str, html_content: str, text_content: Optional[str] = None):
    """Envia um e-mail HTML/texto via SMTP para a lista de destinatários informada."""
    if not to_addresses:
        logger.warning("Nenhum destinatário informado para envio de e-mail.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.smtp_from
    msg["To"] = ", ".join(to_addresses)

    plain_text = text_content or "Este e-mail contém formatação HTML. Por favor, visualize em um cliente compatível."
    part1 = MIMEText(plain_text, "plain", "utf-8")
    part2 = MIMEText(html_content, "html", "utf-8")

    msg.attach(part1)
    msg.attach(part2)

    try:
        if config.smtp_use_ssl:
            server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=20)
        else:
            server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20)

        server.ehlo()
        if config.smtp_use_tls and not config.smtp_use_ssl:
            server.starttls()
            server.ehlo()

        if config.smtp_user and config.smtp_password:
            server.login(config.smtp_user, config.smtp_password)

        server.sendmail(config.smtp_from, to_addresses, msg.as_string())
        server.quit()
        logger.info("E-mail enviado com sucesso para: %s (Assunto: '%s')", to_addresses, subject)
    except Exception as e:
        logger.error("Erro ao enviar e-mail via SMTP: %s", e)
        raise


def send_admin_alert(config: AppConfig, subject_title: str, error_message: str, context_details: str = ""):
    """
    Envia alerta de erro crítico imediato para o e-mail do administrador.
    Ex: falha de login no LegalOne ou falha no Nextcloud.
    """
    if not config.admin_email:
        logger.warning("ADMIN_EMAIL não definido. Alerta de erro não pôde ser enviado por e-mail: %s", error_message)
        return

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    subject = f"⚠️ [ALERTA CRÍTICO] LegalOne Sync - {subject_title}"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 20px; }}
  .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
  .header {{ background-color: #dc2626; color: #ffffff; padding: 20px 24px; }}
  .header h2 {{ margin: 0; font-size: 18px; font-weight: 700; }}
  .header p {{ margin: 4px 0 0 0; font-size: 13px; opacity: 0.9; }}
  .content {{ padding: 24px; }}
  .error-box {{ background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 14px; margin: 16px 0; border-radius: 4px; font-family: 'Consolas', monospace; font-size: 13px; color: #991b1b; white-space: pre-wrap; }}
  .meta-table {{ width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 13px; }}
  .meta-table td {{ padding: 8px 0; border-bottom: 1px solid #f1f5f9; }}
  .meta-label {{ color: #64748b; font-weight: 600; width: 35%; }}
  .footer {{ background-color: #f8fafc; padding: 16px 24px; font-size: 12px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; }}
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h2>Falha na Rotina de Sincronização</h2>
      <p>Ocorrência em: {now_str}</p>
    </div>
    <div class="content">
      <p>Prezado Administrador,</p>
      <p>A sincronização do <strong>Conecta LegalOne</strong> encontrou um problema crítico e necessita de atenção.</p>
      
      <div class="error-box"><strong>Detalhes do Erro:</strong><br>{error_message}</div>
      
      {f'<p><strong>Contexto Adicional:</strong><br>{context_details}</p>' if context_details else ''}

      <table class="meta-table">
        <tr>
          <td class="meta-label">Módulo Afetado:</td>
          <td>{subject_title}</td>
        </tr>
        <tr>
          <td class="meta-label">Data/Hora:</td>
          <td>{now_str}</td>
        </tr>
        <tr>
          <td class="meta-label">Ação Recomendada:</td>
          <td>Verifique as credenciais no arquivo <code>.env</code> ou a disponibilidade do serviço.</td>
        </tr>
      </table>
    </div>
    <div class="footer">
      Sistema Automatizado Conecta LegalOne Sync • Notificação de Emergência
    </div>
  </div>
</body>
</html>"""

    send_email(config, [config.admin_email], subject, html)


def send_daily_summary(
    config: AppConfig,
    stats: Dict[str, Any],
    updated_items: List[Dict[str, Any]],
    nextcloud_folder: str
):
    """
    Envia relatório diário estruturado para a lista de usuários configurada.
    """
    recipients = config.notification_emails
    if not recipients:
        logger.info("Nenhum e-mail configurado em NOTIFICATION_EMAILS. O resumo diário não será enviado.")
        return

    now_str = datetime.now().strftime("%d/%m/%Y às %H:%M")
    total_synced = stats.get("synced", 0)
    total_skipped = stats.get("skipped", 0)
    total_items = stats.get("total", 0)

    # Constrói itens da tabela
    rows_html = []
    if updated_items:
        for it in updated_items[:40]:  # Limita para não sobrecarregar o e-mail
            cnj = it.get("cnj", "Sem CNJ")
            partes = it.get("partes", "Não informadas")
            last_mov = it.get("ultimo_andamento", "Sem novos andamentos")
            rows_html.append(f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
              <td style="padding: 10px; font-weight: bold; color: #1e293b; font-size: 13px;">{cnj}</td>
              <td style="padding: 10px; font-size: 12px; color: #475569;">{partes}</td>
              <td style="padding: 10px; font-size: 12px; color: #334155;">{last_mov}</td>
            </tr>
            """)
    else:
        rows_html.append("""
        <tr>
          <td colspan="3" style="padding: 16px; text-align: center; color: #64748b; font-size: 13px;">
            Nenhum processo sofreu alteração desde a última sincronização.
          </td>
        </tr>
        """)

    table_body = "".join(rows_html)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; color: #1e293b; margin: 0; padding: 20px; }}
  .container {{ max-width: 720px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; border: 1px solid #cbd5e1; }}
  .header {{ background-color: #1e293b; color: #ffffff; padding: 24px; text-align: left; }}
  .header h1 {{ margin: 0; font-size: 20px; font-weight: 700; }}
  .header p {{ margin: 4px 0 0 0; font-size: 13px; color: #94a3b8; }}
  .kpi-container {{ display: flex; padding: 16px 24px; background-color: #f8fafc; border-bottom: 1px solid #e2e8f0; }}
  .kpi-box {{ flex: 1; text-align: center; padding: 10px; border-right: 1px solid #e2e8f0; }}
  .kpi-box:last-child {{ border-right: none; }}
  .kpi-val {{ font-size: 24px; font-weight: bold; color: #2563eb; }}
  .kpi-label {{ font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600; margin-top: 2px; }}
  .content {{ padding: 24px; }}
  .section-title {{ font-size: 15px; font-weight: 700; color: #0f172a; margin: 16px 0 10px 0; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; }}
  .table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  .table th {{ background-color: #f1f5f9; color: #475569; font-size: 11px; text-transform: uppercase; text-align: left; padding: 8px 10px; }}
  .alert-info {{ background-color: #eff6ff; border-left: 4px solid #2563eb; padding: 12px; margin: 16px 0; border-radius: 4px; font-size: 13px; color: #1e40af; }}
  .footer {{ background-color: #f8fafc; padding: 16px 24px; font-size: 12px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; }}
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>⚖️ Relatório Diário de Processos - LegalOne</h1>
      <p>Sincronização concluída com sucesso em {now_str}</p>
    </div>

    <table style="width: 100%; border-collapse: collapse; background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
      <tr>
        <td style="width: 33%; text-align: center; padding: 16px; border-right: 1px solid #e2e8f0;">
          <div style="font-size: 24px; font-weight: bold; color: #059669;">{total_synced}</div>
          <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: bold;">Atualizados / Novos</div>
        </td>
        <td style="width: 33%; text-align: center; padding: 16px; border-right: 1px solid #e2e8f0;">
          <div style="font-size: 24px; font-weight: bold; color: #64748b;">{total_skipped}</div>
          <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: bold;">Inalterados</div>
        </td>
        <td style="width: 33%; text-align: center; padding: 16px;">
          <div style="font-size: 24px; font-weight: bold; color: #2563eb;">{total_items}</div>
          <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: bold;">Total Geral</div>
        </td>
      </tr>
    </table>

    <div class="content">
      <div class="alert-info">
        📁 <strong>Documentos Atualizados:</strong> Os arquivos <strong>DOCX estruturados</strong> e relatórios em <strong>PDF</strong> foram gerados, armazenados localmente e espelhados na pasta remota do Nextcloud: <code>{nextcloud_folder}</code>.
      </div>

      <div class="section-title">Últimos Andamentos & Processos Atualizados</div>
      <table class="table">
        <thead>
          <tr>
            <th style="width: 30%;">Processo (CNJ)</th>
            <th style="width: 30%;">Partes</th>
            <th style="width: 40%;">Último Andamento / Publicação</th>
          </tr>
        </thead>
        <tbody>
          {table_body}
        </tbody>
      </table>
    </div>

    <div class="footer">
      Conecta LegalOne Sync Automatizado • Gerado às {now_str}
    </div>
  </div>
</body>
</html>"""

    subject = f"⚖️ Relatório Diário LegalOne - {total_synced} processos atualizados ({now_str.split(' às ')[0]})"
    send_email(config, recipients, subject, html)
