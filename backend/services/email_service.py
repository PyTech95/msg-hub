"""Simple Resend/SendGrid email service — activates when RESEND_API_KEY (or SENDGRID_API_KEY) is set.

Env:
  RESEND_API_KEY=...           # https://resend.com/api-keys
  EMAIL_FROM="Your App <no-reply@yourdomain.com>"

Usage:
  from services.email_service import email_service
  await email_service.send(to="user@example.com", subject="...", html="...")
"""
from __future__ import annotations
import logging, os
from typing import Optional
import httpx

log = logging.getLogger("cpaas.email")


class EmailService:
    def __init__(self) -> None:
        self.resend_key = (os.environ.get("RESEND_API_KEY") or "").strip()
        self.sendgrid_key = (os.environ.get("SENDGRID_API_KEY") or "").strip()
        self.email_from = (os.environ.get("EMAIL_FROM") or "no-reply@tezsandesh.digital").strip()

    @property
    def configured(self) -> bool:
        return bool(self.resend_key or self.sendgrid_key)

    @property
    def provider(self) -> str:
        if self.resend_key: return "resend"
        if self.sendgrid_key: return "sendgrid"
        return "none"

    async def send(self, to: str, subject: str, html: str,
                   text: Optional[str] = None, reply_to: Optional[str] = None) -> dict:
        """Send an email. Returns {ok, provider, id?, error?}. Never raises."""
        if not to or not subject: return {"ok": False, "error": "to/subject required"}
        if not self.configured:
            log.info(f"[email:mock] to={to} subject={subject!r} (no key set)")
            return {"ok": False, "error": "email service not configured", "provider": "none"}
        try:
            if self.resend_key:
                async with httpx.AsyncClient(timeout=15.0) as c:
                    payload = {"from": self.email_from, "to": [to],
                               "subject": subject, "html": html}
                    if text: payload["text"] = text
                    if reply_to: payload["reply_to"] = reply_to
                    r = await c.post("https://api.resend.com/emails",
                                     headers={"Authorization": f"Bearer {self.resend_key}",
                                              "Content-Type": "application/json"},
                                     json=payload)
                data = r.json() if r.content else {}
                if r.status_code >= 400:
                    return {"ok": False, "provider": "resend",
                            "error": (data.get("message") or data.get("error") or r.text)}
                return {"ok": True, "provider": "resend", "id": data.get("id")}
            # SendGrid fallback
            async with httpx.AsyncClient(timeout=15.0) as c:
                payload = {
                    "personalizations": [{"to": [{"email": to}], "subject": subject}],
                    "from": {"email": self.email_from},
                    "content": [{"type": "text/html", "value": html}],
                }
                if reply_to: payload["reply_to"] = {"email": reply_to}
                r = await c.post("https://api.sendgrid.com/v3/mail/send",
                                 headers={"Authorization": f"Bearer {self.sendgrid_key}",
                                          "Content-Type": "application/json"},
                                 json=payload)
            if r.status_code >= 400:
                return {"ok": False, "provider": "sendgrid",
                        "error": r.text[:300]}
            return {"ok": True, "provider": "sendgrid", "id": r.headers.get("X-Message-Id")}
        except Exception as e:
            log.warning(f"Email send failed: {e}")
            return {"ok": False, "error": str(e)}


email_service = EmailService()


def low_balance_email_html(company_name: str, balance_inr: float,
                           threshold_inr: float, recharge_url: str) -> str:
    return f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;line-height:1.5;padding:24px;max-width:560px;margin:auto">
  <h2 style="color:#ea580c;margin:0 0 12px">⚠️ Low Wallet Balance</h2>
  <p>Hi <strong>{company_name}</strong>,</p>
  <p>Your tezsandesh.digital wallet balance is <strong>₹{balance_inr:.2f}</strong>, which is below your alert threshold of ₹{threshold_inr:.2f}.</p>
  <p>Messages will be <strong>blocked</strong> when your balance reaches ₹0.</p>
  <p style="margin:24px 0"><a href="{recharge_url}" style="background:#ea580c;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;display:inline-block">Recharge now →</a></p>
  <p style="font-size:12px;color:#64748b;margin-top:32px">You received this because you're an admin on this workspace.</p>
</body></html>"""


def campaign_finished_email_html(campaign_name: str, stats: dict, url: str) -> str:
    total = stats.get("sent", 0) + stats.get("delivered", 0) + stats.get("read", 0) + stats.get("failed", 0)
    return f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;line-height:1.5;padding:24px;max-width:560px;margin:auto">
  <h2 style="color:#059669;margin:0 0 12px">✅ Campaign Complete: {campaign_name}</h2>
  <p>Your campaign has finished sending. Here's the summary:</p>
  <table style="border-collapse:collapse;width:100%;margin:16px 0">
    <tr><td style="padding:6px 0;border-bottom:1px solid #e2e8f0"><strong>Total</strong></td><td style="text-align:right;padding:6px 0;border-bottom:1px solid #e2e8f0">{total}</td></tr>
    <tr><td style="padding:6px 0">Delivered</td><td style="text-align:right;padding:6px 0">{stats.get('delivered', 0)}</td></tr>
    <tr><td style="padding:6px 0">Read</td><td style="text-align:right;padding:6px 0">{stats.get('read', 0)}</td></tr>
    <tr><td style="padding:6px 0">Failed</td><td style="text-align:right;padding:6px 0;color:#dc2626">{stats.get('failed', 0)}</td></tr>
  </table>
  <p><a href="{url}" style="color:#059669">View full report →</a></p>
</body></html>"""


def recharge_receipt_email_html(company_name: str, amount_inr: float,
                                balance_inr: float, order_id: str) -> str:
    return f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;line-height:1.5;padding:24px;max-width:560px;margin:auto">
  <h2 style="color:#059669;margin:0 0 12px">✅ Recharge Successful</h2>
  <p>Hi <strong>{company_name}</strong>,</p>
  <p>Your wallet has been credited with <strong>₹{amount_inr:.2f}</strong>.</p>
  <p><strong>New balance: ₹{balance_inr:.2f}</strong></p>
  <p style="font-size:12px;color:#64748b">Order ID: {order_id}</p>
</body></html>"""
