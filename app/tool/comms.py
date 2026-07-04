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
        "Envia um e-mail via SMTP configurado. AÇÃO IRREVERSÍVEL E EXTERNA: use "
        "somente quando o usuário pediu explicitamente o envio E definiu o "
        "destinatário. Nunca invente destinatários. Em dúvida, pergunte com ask_human."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Destinatário (e-mail)"},
            "subject": {"type": "string", "description": "Assunto"},
            "body": {"type": "string", "description": "Corpo do e-mail (texto)"},
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
                    f"MODO AUTÔNOMO: o e-mail NÃO foi enviado. Rascunho salvo em {draft} "
                    "aguardando aprovação humana. Considere esta etapa concluída e siga."
                )
            )
        faltando = [k for k in ("smtp_host", "smtp_port", "username", "password") if k not in cfg]
        if faltando:
            return ToolResult(
                error=(
                    "E-mail não configurado. Adicione a seção [email] no config/config.toml "
                    f"com: {', '.join(faltando)}. Informe isso ao usuário e siga sem enviar."
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
            return ToolResult(error=f"Falha no envio: {e}")
        return ToolResult(output=f"E-mail enviado para {to} (assunto: {subject})")


class NotifyWebhook(BaseTool):
    name: str = "notify_webhook"
    description: str = (
        "Envia uma notificação de texto pro webhook configurado da empresa "
        "(Slack, gateway de WhatsApp, n8n, etc.). Use para avisar conclusão de "
        "tarefas ou alertas quando o usuário pedir notificação."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Texto da notificação"},
        },
        "required": ["message"],
    }

    async def execute(self, message: str, **kwargs) -> ToolResult:
        cfg = _extra_config("webhook")
        if "url" not in cfg:
            return ToolResult(
                error="Webhook não configurado (seção [webhook] com url no config/config.toml). Informe ao usuário."
            )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(cfg["url"], json={"text": message})
                resp.raise_for_status()
        except Exception as e:
            return ToolResult(error=f"Falha no webhook: {e}")
        return ToolResult(output="Notificação enviada com sucesso.")
