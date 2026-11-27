"""Canais de comunicação empresarial: e-mail (SMTP) e webhook.

As credenciais ficam em seções opcionais do config/config.toml:

    [email]
    smtp_host = "smtp.gmail.com"
    smtp_port = 587
    username = "voce@empresa.com"
    password = "senha-de-app"
    from_addr = "voce@empresa.com"   # opcional (padrão: username)

    [webhook]
    url = "https://hooks.exemplo.com/..."   # Slack, WhatsApp gateway, n8n etc.
"""

import asyncio
import os
import smtplib
import time
import tomllib
from email.message import EmailMessage
from pathlib import Path

import httpx

from app.config import PROJECT_ROOT, config
from app.tool.base import BaseTool, ToolResult


def _extra_config(section: str) -> dict:
    """Lê seções extras do config.toml não mapeadas pelo Config tipado."""
    for name in ("config.toml", "config.example.toml"):
        p = Path(PROJECT_ROOT) / "config" / name
        if p.is_file():
            with p.open("rb") as f:
                data = tomllib.load(f)
            if section in data:
                return data[section]
    return {}


class SendEmail(BaseTool):
    name: str = "send_email"
    description: str = (
        "Sends an email via the configured SMTP server. IRREVERSIBLE, EXTERNAL ACTION: use "
        "only when the user explicitly asked to send it AND specified the "
        "recipient. Never invent recipients. When in doubt, ask with ask_human."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient (email address)"},
            "subject": {"type": "string", "description": "Subject"},
            "body": {"type": "string", "description": "Email body (text)"},
        },
        "required": ["to", "subject", "body"],
    }

    async def execute(self, to: str, subject: str, body: str, **kwargs) -> ToolResult:
        cfg = _extra_config("email")
        # Trava estrutural HITL (approval gate): em execução AUTÔNOMA (fila/cron),
        # e-mail vira rascunho aguardando aprovação humana — envio real só
        # interativo ou com allow_autonomous_send = true no [email].
        if os.getenv("MANGABA_AUTONOMO") == "1" and not cfg.get("allow_autonomous_send", False):
            rascunhos = config.workspace_root / "rascunhos"
            rascunhos.mkdir(parents=True, exist_ok=True)
            draft = rascunhos / f"{int(time.time())}-{to.replace('@', '_')}.eml"
            draft.write_text(
                f"To: {to}\nSubject: {subject}\n\n{body}", encoding="utf-8"
            )
            return ToolResult(
                output=(
                    f"AUTONOMOUS MODE: the email was NOT sent. Draft saved to {draft} "
                    "awaiting human approval. Consider this step done and move on."
                )
            )
        faltando = [k for k in ("smtp_host", "smtp_port", "username", "password") if k not in cfg]
        if faltando:
            return ToolResult(
                error=(
                    "Email not configured. Add an [email] section to config/config.toml "
                    f"with: {', '.join(faltando)}. Tell the user and continue without sending."
                )
            )

        def _send() -> None:
            msg = EmailMessage()
            msg["From"] = cfg.get("from_addr", cfg["username"])
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)
            port = int(cfg["smtp_port"])
            with smtplib.SMTP(cfg["smtp_host"], port, timeout=30) as s:
                if cfg.get("use_tls", port == 587):
                    s.starttls()
                if cfg.get("password"):
                    try:
                        s.login(cfg["username"], cfg["password"])
                    except smtplib.SMTPNotSupportedError:
                        pass  # servidores locais/relay sem auth
                s.send_message(msg)

        try:
            await asyncio.to_thread(_send)
        except Exception as e:
            return ToolResult(error=f"Send failed: {e}")
        return ToolResult(output=f"Email sent to {to} (subject: {subject})")


class NotifyWebhook(BaseTool):
    name: str = "notify_webhook"
    description: str = (
        "Sends a text notification to the company's configured webhook "
        "(Slack, WhatsApp gateway, n8n, etc.). Use to report task completion "
        "or alerts when the user asks for a notification."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Notification text"},
        },
        "required": ["message"],
    }

    async def execute(self, message: str, **kwargs) -> ToolResult:
        cfg = _extra_config("webhook")
        if "url" not in cfg:
            return ToolResult(
                error="Webhook not configured ([webhook] section with url in config/config.toml). Tell the user."
            )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(cfg["url"], json={"text": message})
                resp.raise_for_status()
        except Exception as e:
            return ToolResult(error=f"Webhook failed: {e}")
        return ToolResult(output="Notification sent successfully.")
