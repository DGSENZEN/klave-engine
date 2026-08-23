"""Transactional mail with an honest fallback.

Providers resolve from settings: Resend (HTTPS API), SMTP (stdlib), or the
local *outbox* — JSON files under ``data/outbox`` written when nothing is
configured. A message is only reported as delivered when a real provider
accepted it; the outbox never pretends. Routes use ``MailResult.delivered``
to decide whether the UI may say "te enviamos un correo" or must hand the
link to an administrator instead.
"""

import json
import smtplib
import ssl
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from html import escape
from pathlib import Path

import httpx
from klave_engine.common.config import Settings
from klave_engine.common.logging import get_logger, log_stage, redact_email

logger = get_logger(__name__)

RESEND_URL = "https://api.resend.com/emails"


@dataclass(frozen=True)
class MailResult:
    delivered: bool
    provider: str
    error: str | None = None


@dataclass(frozen=True)
class MailContent:
    subject: str
    text: str
    html: str


def render(
    *,
    subject: str,
    greeting: str,
    lines: list[str],
    action_label: str | None = None,
    action_url: str | None = None,
    footer: str = "Si no esperabas este correo, puedes ignorarlo.",
) -> MailContent:
    """Plain text first; the HTML is a restrained, single-column echo of it."""
    text_parts = [greeting, ""] + lines
    if action_url:
        text_parts += ["", f"{action_label or 'Abrir'}: {action_url}"]
    text_parts += ["", footer, "— Klave"]
    paragraphs = "".join(
        '<p style="margin:0 0 12px;font-size:15px;line-height:1.5;color:#1a1a1c">'
        f"{escape(line)}</p>"
        for line in lines
    )
    button = (
        f'<p style="margin:20px 0"><a href="{escape(action_url)}" '
        'style="display:inline-block;padding:10px 16px;border-radius:8px;background:#111114;'
        'color:#fff;text-decoration:none;font-weight:600;font-size:14px">'
        f"{escape(action_label or 'Abrir')}</a></p>"
        f'<p style="margin:0 0 12px;font-size:12px;color:#6b6b72;word-break:break-all">'
        f"{escape(action_url)}</p>"
        if action_url
        else ""
    )
    html = (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        'max-width:520px;margin:0 auto;padding:28px 20px">'
        '<p style="margin:0 0 18px;font-size:13px;letter-spacing:.08em;text-transform:uppercase;'
        'color:#6b6b72;font-weight:600">Klave</p>'
        f'<p style="margin:0 0 12px;font-size:15px;color:#1a1a1c">{escape(greeting)}</p>'
        f"{paragraphs}{button}"
        f'<p style="margin:24px 0 0;font-size:12px;color:#6b6b72">{escape(footer)}</p>'
        "</div>"
    )
    return MailContent(subject=subject, text="\n".join(text_parts), html=html)


OUTBOX_TTL_DAYS = 7


class Mailer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def provider(self) -> str:
        configured = (self.settings.mail_provider or "auto").lower()
        if configured != "auto":
            return configured
        if self.settings.resend_api_key:
            return "resend"
        if self.settings.smtp_host:
            return "smtp"
        return "outbox"

    @property
    def enabled(self) -> bool:
        """Whether messages actually leave the server."""
        return self.provider in ("resend", "smtp")

    def send(self, to: str, content: MailContent) -> MailResult:
        provider = self.provider
        try:
            if provider == "resend":
                self._send_resend(to, content)
            elif provider == "smtp":
                self._send_smtp(to, content)
            else:
                self._write_outbox(to, content)
                log_stage(logger, "mail_outboxed", to=redact_email(to), subject=content.subject)
                return MailResult(delivered=False, provider="outbox")
        except Exception as exc:  # provider failures must never 500 the request
            logger.warning(
                "mail_failed provider=%s to=%s error=%s", provider, redact_email(to), exc
            )
            self._write_outbox(to, content, error=str(exc))
            return MailResult(delivered=False, provider=provider, error=str(exc))
        log_stage(
            logger, "mail_sent", provider=provider, to=redact_email(to),
            subject=content.subject,
        )
        return MailResult(delivered=True, provider=provider)

    # ---------------------------------------------------------- providers

    def _send_resend(self, to: str, content: MailContent) -> None:
        response = httpx.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {self.settings.resend_api_key}"},
            json={
                "from": self.settings.mail_from,
                "to": [to],
                "subject": content.subject,
                "text": content.text,
                "html": content.html,
            },
            timeout=15,
        )
        if response.status_code >= 300:
            raise RuntimeError(f"Resend {response.status_code}: {response.text[:200]}")

    def _send_smtp(self, to: str, content: MailContent) -> None:
        message = EmailMessage()
        message["From"] = self.settings.mail_from
        message["To"] = to
        message["Subject"] = content.subject
        message.set_content(content.text)
        message.add_alternative(content.html, subtype="html")
        assert self.settings.smtp_host is not None
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as smtp:
            if self.settings.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if self.settings.smtp_user:
                smtp.login(self.settings.smtp_user, self.settings.smtp_password or "")
            smtp.send_message(message)

    def _write_outbox(self, to: str, content: MailContent, error: str | None = None) -> Path:
        """The letters nobody could deliver, for the operator to hand over.

        They carry live links (recovery, verification), so the copies are
        kept lean and short-lived: text only (no second copy in HTML),
        owner-only permissions, and anything older than the outbox TTL is
        swept on each write — the tokens inside expire sooner anyway."""
        outbox = self.settings.data_dir / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        outbox.chmod(0o700)
        self._sweep_expired(outbox)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        path = outbox / f"{stamp}_{uuid.uuid4().hex[:8]}.json"
        path.write_text(
            json.dumps(
                {
                    "to": to,
                    "subject": content.subject,
                    "text": content.text,
                    "error": error,
                    "created_at": datetime.now(UTC).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        path.chmod(0o600)
        return path

    @staticmethod
    def _sweep_expired(outbox: Path) -> None:
        cutoff = datetime.now(UTC).timestamp() - OUTBOX_TTL_DAYS * 86400
        for old in outbox.glob("*.json"):
            try:
                if old.stat().st_mtime < cutoff:
                    old.unlink()
            except OSError:
                continue


def get_mailer(settings: Settings) -> Mailer:
    return Mailer(settings)
