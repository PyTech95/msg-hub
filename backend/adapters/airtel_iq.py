"""
Airtel IQ adapter — SMS / WhatsApp / Voice.

Design goals:
- Zero-config default: if any credential is missing the adapter transparently
  falls back to mock behaviour so the app keeps working in dev/preview.
- Live mode is enabled only when AIRTEL_IQ_LIVE=1 AND all required creds present.
- OAuth2 client-credentials token flow with 60s leeway caching.
- DLT-compliant SMS payload (customerId + dltHeaderId + dltTemplateId + variables).
- HMAC signature helper for inbound DLR / status webhooks.

Endpoint paths and payload keys follow Airtel IQ's public docs and are
overridable via env in case Airtel bumps versions.
"""
from __future__ import annotations
import os
import hmac
import asyncio
import hashlib
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger("tezsandesh.airtel_iq")


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class AirtelIQConfig:
    """Reads Airtel IQ settings from environment. Immutable at instance level."""
    def __init__(self) -> None:
        self.live = _env("AIRTEL_IQ_LIVE", "0") == "1"
        # OAuth
        self.oauth_url  = _env("AIRTEL_IQ_OAUTH_TOKEN_URL")
        self.client_id  = _env("AIRTEL_IQ_CLIENT_ID")
        self.client_sec = _env("AIRTEL_IQ_CLIENT_SECRET")
        self.scope      = _env("AIRTEL_IQ_TOKEN_SCOPE")  # optional
        # Account
        self.customer_id = _env("AIRTEL_IQ_CUSTOMER_ID")
        # Base URLs (product-level)
        self.sms_base_url      = _env("AIRTEL_IQ_SMS_BASE_URL")
        self.whatsapp_base_url = _env("AIRTEL_IQ_WHATSAPP_BASE_URL")
        self.voice_base_url    = _env("AIRTEL_IQ_VOICE_BASE_URL")
        # DLT defaults (per-message overrides possible via meta)
        self.default_header_id   = _env("AIRTEL_IQ_DEFAULT_HEADER_ID")
        self.default_template_id = _env("AIRTEL_IQ_DEFAULT_TEMPLATE_ID")
        # Endpoint paths (override if Airtel bumps versions)
        self.sms_send_path       = _env("AIRTEL_IQ_SMS_SEND_PATH", "/api/v1/send-sms")
        self.whatsapp_send_path  = _env("AIRTEL_IQ_WHATSAPP_SEND_PATH", "/api/v1/whatsapp/messages/template")
        self.voice_call_path     = _env("AIRTEL_IQ_VOICE_CALL_PATH", "/api/v1/voice/calls")
        # Webhook shared secret (for HMAC verify)
        self.webhook_secret = _env("AIRTEL_WEBHOOK_SECRET")

    def sms_ready(self) -> bool:
        return self.live and all([self.oauth_url, self.client_id, self.client_sec,
                                  self.customer_id, self.sms_base_url,
                                  self.default_header_id, self.default_template_id])

    def whatsapp_ready(self) -> bool:
        return self.live and all([self.oauth_url, self.client_id, self.client_sec,
                                  self.whatsapp_base_url])

    def voice_ready(self) -> bool:
        return self.live and all([self.oauth_url, self.client_id, self.client_sec,
                                  self.voice_base_url])


class AirtelIQAuth:
    """OAuth2 client-credentials token cache."""
    def __init__(self, cfg: AirtelIQConfig) -> None:
        self._cfg = cfg
        self._token: Optional[str] = None
        self._expires_at: datetime = datetime.now(timezone.utc)
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        async with self._lock:
            if self._token and self._expires_at > datetime.now(timezone.utc):
                return self._token
            await self._refresh()
            return self._token or ""

    async def _refresh(self) -> None:
        data: Dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": self._cfg.client_id,
            "client_secret": self._cfg.client_sec,
        }
        if self._cfg.scope:
            data["scope"] = self._cfg.scope
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self._cfg.oauth_url, data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            payload = resp.json()
        self._token = str(payload.get("access_token") or "")
        ttl = int(payload.get("expires_in") or 3600)
        # 60s leeway so we refresh slightly before real expiry
        self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(60, ttl - 60))
        log.info("Airtel IQ OAuth token refreshed (ttl=%ss)", ttl)


class AirtelIQClient:
    """Shared HTTP + auth used by SMS / WhatsApp / Voice adapters."""
    def __init__(self, cfg: AirtelIQConfig) -> None:
        self.cfg = cfg
        self.auth = AirtelIQAuth(cfg)

    async def post_json(self, base_url: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        token = await self.auth.token()
        async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=15.0) as client:
            resp = await client.post(
                path,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json() if resp.content else {}


# ─── Public adapter classes wired into ADAPTERS in server.py ──────────────────
# They all inherit from server.BaseAdapter to preserve `.simulate_lifecycle`.
# To avoid an import cycle we accept the base class at runtime (mixin style).

def build_adapters(BaseAdapter):
    cfg = AirtelIQConfig()
    client = AirtelIQClient(cfg) if cfg.live else None

    class AirtelIQSMSAdapter(BaseAdapter):
        channel = "sms"
        provider_key = "airtel_iq"

        async def send(self, to: str, body: str, media_url: Optional[str] = None, **kwargs) -> Dict[str, Any]:
            if not (client and cfg.sms_ready()):
                # Fallback: mock response so app keeps working.
                return {"provider_message_id": f"mock_{secrets.token_hex(8)}", "accepted": True, "mode": "mock"}
            payload = {
                "sendSmsRequestVos": [{
                    "customerId": cfg.customer_id,
                    "destination": to,
                    "dltHeaderId": cfg.default_header_id,
                    "dltTemplateId": cfg.default_template_id,
                    # For DLT-approved messages Airtel expects the rendered body;
                    # variable-substitution can be done at template level too.
                    "message": body,
                }]
            }
            try:
                res = await client.post_json(cfg.sms_base_url, cfg.sms_send_path, payload)
                # Try common id fields Airtel uses
                pid = (res.get("messageId")
                       or (res.get("result") or {}).get("messageId")
                       or f"aq_{secrets.token_hex(8)}")
                return {"provider_message_id": str(pid), "accepted": True, "mode": "live", "raw": res}
            except Exception as e:
                log.error("Airtel IQ SMS send failed, falling back to mock: %s", e)
                return {"provider_message_id": f"mock_{secrets.token_hex(8)}", "accepted": True, "mode": "mock_fallback"}

    class AirtelIQWhatsAppAdapter(BaseAdapter):
        channel = "whatsapp"
        provider_key = "airtel_iq"

        async def send(self, to: str, body: str, media_url: Optional[str] = None, **kwargs) -> Dict[str, Any]:
            if not (client and cfg.whatsapp_ready()):
                return {"provider_message_id": f"mock_{secrets.token_hex(8)}", "accepted": True, "mode": "mock"}
            payload = {
                "to": to,
                "type": "text",
                "text": {"body": body},
            }
            try:
                res = await client.post_json(cfg.whatsapp_base_url, cfg.whatsapp_send_path, payload)
                pid = res.get("wa_message_id") or res.get("messageId") or f"aqw_{secrets.token_hex(8)}"
                return {"provider_message_id": str(pid), "accepted": True, "mode": "live", "raw": res}
            except Exception as e:
                log.error("Airtel IQ WhatsApp send failed, falling back to mock: %s", e)
                return {"provider_message_id": f"mock_{secrets.token_hex(8)}", "accepted": True, "mode": "mock_fallback"}

    class AirtelIQVoiceAdapter(BaseAdapter):
        channel = "voice"
        provider_key = "airtel_iq"

        async def send(self, to: str, body: str, media_url: Optional[str] = None, **kwargs) -> Dict[str, Any]:
            # `body` is treated as TTS script; `media_url` (if set) can be hosted audio.
            if not (client and cfg.voice_ready()):
                return {"provider_message_id": f"mock_{secrets.token_hex(8)}", "accepted": True, "mode": "mock"}
            payload: Dict[str, Any] = {
                "to": to,
                "correlationId": secrets.token_hex(8),
            }
            if media_url:
                payload["audioUrl"] = media_url
            else:
                payload["tts"] = {"text": body, "language": "en-IN"}
            try:
                res = await client.post_json(cfg.voice_base_url, cfg.voice_call_path, payload)
                pid = res.get("callId") or res.get("id") or f"aqv_{secrets.token_hex(8)}"
                return {"provider_message_id": str(pid), "accepted": True, "mode": "live", "raw": res}
            except Exception as e:
                log.error("Airtel IQ Voice initiate failed, falling back to mock: %s", e)
                return {"provider_message_id": f"mock_{secrets.token_hex(8)}", "accepted": True, "mode": "mock_fallback"}

    return {
        "cfg": cfg,
        "sms": AirtelIQSMSAdapter(),
        "whatsapp": AirtelIQWhatsAppAdapter(),
        "voice": AirtelIQVoiceAdapter(),
    }


# ─── Webhook signature helper ─────────────────────────────────────────────────
def verify_signature(secret: str, raw_body: bytes, signature: str) -> bool:
    """Constant-time HMAC-SHA256 verification of Airtel-signed webhook bodies."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    # Accept both hex and 'sha256=<hex>' formats
    if signature.startswith("sha256="):
        signature = signature.split("=", 1)[1]
    try:
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


# Airtel IQ status → internal status mapping
AIRTEL_SMS_STATUS_MAP = {
    "QUEUED": "queued",
    "SUBMITTED": "sent",
    "SENT": "sent",
    "DELIVERED": "delivered",
    "READ": "delivered",
    "FAILED": "failed",
    "UNDELIVERED": "failed",
    "REJECTED": "failed",
    "EXPIRED": "failed",
}

AIRTEL_VOICE_STATUS_MAP = {
    "INITIATED": "initiated",
    "RINGING": "ringing",
    "ANSWERED": "answered",
    "IN_PROGRESS": "answered",
    "COMPLETED": "completed",
    "NO_ANSWER": "no-answer",
    "BUSY": "busy",
    "FAILED": "failed",
    "CANCELED": "failed",
}
