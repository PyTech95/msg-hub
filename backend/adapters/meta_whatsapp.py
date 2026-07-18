"""Meta WhatsApp Cloud API adapter (Graph API)."""
from __future__ import annotations
import os
import hmac
import hashlib
import logging
import secrets
from typing import Any, Awaitable, Callable, Dict, Optional

import httpx

log = logging.getLogger("tezsandesh.meta_whatsapp")

GRAPH_BASE = "https://graph.facebook.com"

# Meta webhook status → internal status ("read" implies delivered per Meta docs)
META_STATUS_MAP = {
    "sent": "sent",
    "delivered": "delivered",
    "read": "delivered",
    "failed": "failed",
    "deleted": "failed",
}


def env_config() -> Optional[Dict[str, str]]:
    """Live config from env vars; None means run in mock mode."""
    token = (os.environ.get("WHATSAPP_ACCESS_TOKEN") or "").strip()
    phone_id = (os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or "").strip()
    if token and phone_id:
        return {
            "access_token": token,
            "phone_number_id": phone_id,
            "graph_version": (os.environ.get("GRAPH_API_VERSION") or "v22.0").strip() or "v22.0",
        }
    return None


def _clean_number(to: str) -> str:
    return to.strip().lstrip("+").replace(" ", "").replace("-", "")


def _demo_mode() -> bool:
    return (os.environ.get("DEMO_MODE") or "true").strip().lower() == "true"


def _mock_or_fail() -> Dict[str, Any]:
    """Mock fallback in demo mode; hard failure in production (DEMO_MODE=false)."""
    if not _demo_mode():
        raise RuntimeError(
            "WhatsApp Cloud API credentials not configured — set WHATSAPP_ACCESS_TOKEN "
            "and WHATSAPP_PHONE_NUMBER_ID in .env (or vault credentials with Mock OFF)"
        )
    return {"provider_message_id": f"mock_{secrets.token_hex(8)}", "accepted": True, "mode": "mock"}


async def graph_post_message(creds: Dict[str, str], payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{GRAPH_BASE}/{creds.get('graph_version', 'v22.0')}/{creds['phone_number_id']}/messages"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers={
            "Authorization": f"Bearer {creds['access_token']}",
            "Content-Type": "application/json",
        })
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        err = (data.get("error") or {}).get("message") or resp.text
        raise RuntimeError(f"Meta API {resp.status_code}: {err}")
    return data


async def health_check(creds: Dict[str, str]) -> Dict[str, Any]:
    """Verify token + phone number id by fetching the phone number resource."""
    url = f"{GRAPH_BASE}/{creds.get('graph_version', 'v22.0')}/{creds['phone_number_id']}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {creds['access_token']}"})
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            return {"ok": False, "message": (data.get("error") or {}).get("message") or resp.text}
        label = data.get("display_phone_number") or data.get("verified_name") or creds["phone_number_id"]
        return {"ok": True, "message": f"Connected to Meta Cloud API: {label}"}
    except Exception as e:
        return {"ok": False, "message": f"Handshake failed: {e}"}


async def list_message_templates(access_token: str, waba_id: str,
                                 graph_version: str = "v22.0", limit: int = 100) -> Dict[str, Any]:
    """Fetch message templates from a WhatsApp Business Account.
    Returns {ok, templates, error}. templates: [{name, language, status, category, components}]"""
    url = f"{GRAPH_BASE}/{graph_version}/{waba_id}/message_templates"
    params = {"fields": "name,language,status,category,components,quality_score,rejected_reason",
              "limit": min(max(limit, 1), 200)}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params,
                                    headers={"Authorization": f"Bearer {access_token}"})
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            return {"ok": False, "templates": [],
                    "error": (data.get("error") or {}).get("message") or resp.text}
        return {"ok": True, "templates": data.get("data") or [], "error": None,
                "paging": data.get("paging") or {}}
    except Exception as e:
        return {"ok": False, "templates": [], "error": str(e)}


async def create_message_template(access_token: str, waba_id: str, payload: Dict[str, Any],
                                  graph_version: str = "v22.0") -> Dict[str, Any]:
    """Submit a new WhatsApp template for approval.
    payload: {name, category, language, components: [...]}"""
    url = f"{GRAPH_BASE}/{graph_version}/{waba_id}/message_templates"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url,
                                     headers={"Authorization": f"Bearer {access_token}",
                                              "Content-Type": "application/json"},
                                     json=payload)
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            return {"ok": False, "error": (data.get("error") or {}).get("message") or resp.text}
        return {"ok": True, "id": data.get("id"), "status": data.get("status") or "PENDING",
                "category": data.get("category")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def upload_media(creds: Dict[str, str], file_bytes: bytes,
                      filename: str, mime_type: str) -> Dict[str, Any]:
    """Upload media to Meta Cloud API. Returns {ok, media_id, error}.
    Meta caches uploaded media for ~30 days; media_id is then used in send_media_message."""
    url = f"{GRAPH_BASE}/{creds.get('graph_version', 'v22.0')}/{creds['phone_number_id']}/media"
    try:
        files = {
            "file": (filename, file_bytes, mime_type),
            "type": (None, mime_type),
            "messaging_product": (None, "whatsapp"),
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, files=files,
                                     headers={"Authorization": f"Bearer {creds['access_token']}"})
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            return {"ok": False, "media_id": None,
                    "error": (data.get("error") or {}).get("message") or resp.text}
        return {"ok": True, "media_id": str(data.get("id")), "error": None}
    except Exception as e:
        return {"ok": False, "media_id": None, "error": str(e)}


async def get_media_url(access_token: str, media_id: str,
                        graph_version: str = "v22.0") -> Dict[str, Any]:
    """Resolve a Meta media_id to a temporary download URL (~5 min TTL)."""
    url = f"{GRAPH_BASE}/{graph_version}/{media_id}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            return {"ok": False, "url": None, "mime_type": None,
                    "error": (data.get("error") or {}).get("message") or resp.text}
        return {"ok": True, "url": data.get("url"),
                "mime_type": data.get("mime_type"),
                "file_size": data.get("file_size"),
                "sha256": data.get("sha256"), "error": None}
    except Exception as e:
        return {"ok": False, "url": None, "mime_type": None, "error": str(e)}


async def download_media_bytes(access_token: str, download_url: str) -> Dict[str, Any]:
    """Download raw bytes from the Meta media CDN URL (requires Bearer token)."""
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(download_url,
                                    headers={"Authorization": f"Bearer {access_token}"})
        if resp.status_code >= 400:
            return {"ok": False, "bytes": None, "error": f"CDN {resp.status_code}: {resp.text[:200]}"}
        return {"ok": True, "bytes": resp.content,
                "mime_type": resp.headers.get("content-type", "application/octet-stream"),
                "error": None}
    except Exception as e:
        return {"ok": False, "bytes": None, "error": str(e)}


async def send_media_message(creds: Dict[str, str], to: str, media_type: str,
                             media_id: Optional[str] = None,
                             link: Optional[str] = None,
                             caption: Optional[str] = None,
                             filename: Optional[str] = None) -> Dict[str, Any]:
    """Send a media message (image/video/audio/document/sticker) via Meta Cloud API.
    media_type: 'image' | 'video' | 'audio' | 'document' | 'sticker'
    Provide either media_id (preferred, from upload_media) or link (public URL)."""
    if media_type not in ("image", "video", "audio", "document", "sticker"):
        raise ValueError(f"Unsupported media type: {media_type}")
    payload_media: Dict[str, Any] = {}
    if media_id:
        payload_media["id"] = media_id
    elif link:
        payload_media["link"] = link
    else:
        raise ValueError("Either media_id or link is required")
    if caption and media_type in ("image", "video", "document"):
        payload_media["caption"] = caption
    if filename and media_type == "document":
        payload_media["filename"] = filename
    payload = {"messaging_product": "whatsapp", "to": _clean_number(to),
               "type": media_type, media_type: payload_media}
    data = await graph_post_message(creds, payload)
    pid = ((data.get("messages") or [{}])[0]).get("id") or f"meta_{secrets.token_hex(8)}"
    return {"provider_message_id": str(pid), "accepted": True, "mode": "live", "raw": data}


async def delete_message_template(access_token: str, waba_id: str, name: str,
                                  graph_version: str = "v22.0") -> Dict[str, Any]:
    """Delete a WhatsApp template by name (all languages)."""
    url = f"{GRAPH_BASE}/{graph_version}/{waba_id}/message_templates"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.delete(url,
                                       headers={"Authorization": f"Bearer {access_token}"},
                                       params={"name": name})
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            return {"ok": False, "error": (data.get("error") or {}).get("message") or resp.text}
        return {"ok": True, "success": data.get("success", True)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def build_adapter(BaseAdapter, creds_provider: Callable[..., Awaitable[Optional[Dict[str, str]]]]):
    class MetaWhatsAppAdapter(BaseAdapter):
        channel = "whatsapp"
        provider_key = "meta_whatsapp"

        async def send(self, to: str, body: str, media_url: Optional[str] = None, **kwargs) -> Dict[str, Any]:
            company_id = kwargs.get("company_id")
            creds = await creds_provider(company_id)
            if not creds:
                return _mock_or_fail()
            to_clean = _clean_number(to)
            if media_url:
                payload = {"messaging_product": "whatsapp", "to": to_clean, "type": "image",
                           "image": {"link": media_url, "caption": body or ""}}
            else:
                payload = {"messaging_product": "whatsapp", "to": to_clean, "type": "text",
                           "text": {"body": body, "preview_url": True}}
            log.info("Meta WA send → %s (type=%s, company=%s)", to_clean, "image" if media_url else "text", company_id or "-")
            data = await graph_post_message(creds, payload)
            pid = ((data.get("messages") or [{}])[0]).get("id") or f"meta_{secrets.token_hex(8)}"
            log.info("Meta WA accepted id=%s", pid)
            return {"provider_message_id": str(pid), "accepted": True, "mode": "live", "raw": data}

        async def send_template(self, to: str, template_name: str,
                                language_code: str = "en_US",
                                components: Optional[list] = None,
                                company_id: Optional[str] = None) -> Dict[str, Any]:
            creds = await creds_provider(company_id)
            if not creds:
                return _mock_or_fail()
            template: Dict[str, Any] = {"name": template_name, "language": {"code": language_code}}
            if components:
                template["components"] = components
            payload = {"messaging_product": "whatsapp", "to": _clean_number(to),
                       "type": "template", "template": template}
            data = await graph_post_message(creds, payload)
            pid = ((data.get("messages") or [{}])[0]).get("id") or f"meta_{secrets.token_hex(8)}"
            return {"provider_message_id": str(pid), "accepted": True, "mode": "live", "raw": data}

    return MetaWhatsAppAdapter()


def verify_meta_signature(app_secret: str, raw_body: bytes, signature_header: str) -> bool:
    """X-Hub-Signature-256 HMAC verification; disabled when no app secret configured."""
    if not app_secret:
        return True
    if not signature_header:
        return False
    sig = signature_header.split("=", 1)[1] if "=" in signature_header else signature_header
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(expected, sig)
    except Exception:
        return False
