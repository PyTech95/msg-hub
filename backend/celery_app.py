"""Celery app for background broadcast workers.

Runs alongside the FastAPI backend, connected to the same MongoDB.
Broadcast v2 replaces the in-process asyncio semaphore with a real distributed queue:
- Retry with exponential backoff (3 attempts)
- Dead-letter tracking (message.failed_permanent=True on final failure)
- Rate-limited per-channel (WhatsApp 20 msg/sec by default)
- Pause / resume (worker checks campaign.status before each send)
- Resume-on-fail (re-enqueue chunks safely — idempotency via message.id)
"""
from __future__ import annotations
import os
import asyncio
import logging
from datetime import timezone
from datetime import datetime as _dt
from pathlib import Path
from typing import Dict, Any, Optional

from celery import Celery
from celery.utils.log import get_task_logger
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

log = get_task_logger(__name__)

BROKER = os.environ.get("CELERY_BROKER_URL") or os.environ.get("REDIS_URL") or "redis://127.0.0.1:6379/0"
BACKEND = os.environ.get("CELERY_RESULT_BACKEND") or "redis://127.0.0.1:6379/1"

celery_app = Celery("cpaas_broadcast", broker=BROKER, backend=BACKEND, include=["celery_app"])
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=4,
    # Global rate limit for broadcast sends across all workers
    task_annotations={
        "celery_app.send_broadcast_message": {"rate_limit": os.environ.get("BROADCAST_RATE_LIMIT", "20/s")},
    },
    task_default_retry_delay=15,   # 15s between retries
    task_max_retries=3,
)

# ─────────── Lazy Mongo client (per worker process) ───────────
_client = None
_db = None
_wa_credentials_cache: Dict[str, Any] = {}


def _get_db():
    global _client, _db
    if _db is None:
        from motor.motor_asyncio import AsyncIOMotorClient
        _client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        _db = _client[os.environ["DB_NAME"]]
    return _db


def _now_iso() -> str:
    return _dt.now(timezone.utc).isoformat()


async def _resolve_creds(company_id: Optional[str], phone_number_id: Optional[str]):
    """Minimal creds resolver mirroring server.meta_wa_credentials() for the worker context."""
    db = _get_db()
    if company_id:
        if phone_number_id:
            cfg = await db.company_whatsapp_configs.find_one(
                {"company_id": company_id, "phone_number_id": phone_number_id, "is_active": True}, {"_id": 0})
        else:
            cfg = await db.company_whatsapp_configs.find_one(
                {"company_id": company_id, "is_active": True, "is_primary": True}, {"_id": 0}
            ) or await db.company_whatsapp_configs.find_one(
                {"company_id": company_id, "is_active": True}, {"_id": 0})
        if cfg and not cfg.get("mock", True) and cfg.get("access_token") and cfg.get("phone_number_id"):
            try:
                from services import crypto_service as _crypto
                _crypto.decrypt_dict(cfg, ["access_token", "app_secret"])
            except Exception:
                pass  # legacy plaintext or crypto disabled — use as-is
            return {"access_token": cfg["access_token"], "phone_number_id": cfg["phone_number_id"],
                    "graph_version": cfg.get("graph_version") or "v22.0",
                    "waba_id": cfg.get("waba_id") or ""}
    # Env fallback
    tok = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    pid = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    if tok and pid:
        return {"access_token": tok, "phone_number_id": pid,
                "graph_version": os.environ.get("GRAPH_API_VERSION") or "v22.0",
                "waba_id": os.environ.get("WHATSAPP_WABA_ID") or ""}
    return None


@celery_app.task(bind=True, name="celery_app.send_broadcast_message",
                 autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=120)
def send_broadcast_message(self, message_id: str, campaign_id: str, company_id: Optional[str],
                            channel: str, to_phone: str, body: str,
                            template_name: Optional[str] = None,
                            template_language: Optional[str] = None,
                            template_components: Optional[list] = None,
                            phone_number_id: Optional[str] = None):
    """Send a single broadcast recipient. Retried up to 3 times with exponential backoff."""
    async def _do():
        db = _get_db()
        # Idempotency: skip if already terminal
        msg = await db.messages.find_one({"id": message_id}, {"_id": 0, "status": 1, "campaign_id": 1})
        if not msg:
            log.warning("broadcast: message %s not found — skipping", message_id)
            return {"skipped": True, "reason": "not_found"}
        if msg.get("status") in ("sent", "delivered", "read", "failed_permanent"):
            return {"skipped": True, "reason": "already_terminal", "status": msg["status"]}

        # Respect campaign pause/cancel state
        camp = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0, "status": 1})
        if camp and camp.get("status") in ("paused", "cancelled"):
            log.info("broadcast: campaign %s is %s — deferring %s", campaign_id, camp["status"], message_id)
            return {"skipped": True, "reason": f"campaign_{camp['status']}"}

        if channel != "whatsapp":
            log.info("broadcast: only whatsapp supported currently, got %s", channel)
            await db.messages.update_one({"id": message_id},
                                          {"$set": {"status": "failed", "error": f"channel {channel} not supported by v2 worker"}})
            return {"ok": False}

        creds = await _resolve_creds(company_id, phone_number_id)
        if not creds:
            await db.messages.update_one({"id": message_id},
                                          {"$set": {"status": "failed", "error": "no_credentials"}})
            return {"ok": False}

        from adapters import meta_whatsapp as meta_wa
        try:
            if template_name:
                # Build Meta template payload and post directly
                template: Dict[str, Any] = {"name": template_name, "language": {"code": template_language or "en_US"}}
                if template_components:
                    template["components"] = template_components
                payload = {"messaging_product": "whatsapp", "to": to_phone.lstrip("+"),
                           "type": "template", "template": template}
            else:
                payload = {"messaging_product": "whatsapp", "to": to_phone.lstrip("+"),
                           "type": "text", "text": {"body": body, "preview_url": True}}
            data = await meta_wa.graph_post_message(creds, payload)
            import secrets
            pid = ((data.get("messages") or [{}])[0]).get("id") or f"meta_{secrets.token_hex(8)}"
            resp = {"provider_message_id": str(pid),
                    "phone_number_id_used": creds.get("phone_number_id")}
        except Exception as e:
            log.warning("broadcast send failed (retryable) %s: %s", message_id, e)
            # Let Celery retry via autoretry_for
            attempts = getattr(self.request, "retries", 0)
            if attempts >= self.max_retries:
                await db.messages.update_one({"id": message_id},
                                              {"$set": {"status": "failed_permanent",
                                                        "error": str(e)[:400],
                                                        "final_failed_at": _now_iso()}})
                await db.campaigns.update_one({"id": campaign_id}, {"$inc": {"stats.failed_permanent": 1}})
                return {"ok": False, "final": True, "error": str(e)}
            raise

        # Success
        await db.messages.update_one({"id": message_id},
                                      {"$set": {"provider_message_id": resp["provider_message_id"],
                                                "phone_number_id": resp.get("phone_number_id_used"),
                                                "status": "sent", "sent_at": _now_iso()}})
        await db.campaigns.update_one({"id": campaign_id}, {"$inc": {"stats.sent": 1, "stats.queued": -1}})
        return {"ok": True, "provider_message_id": resp["provider_message_id"]}

    return asyncio.run(_do())


if __name__ == "__main__":
    celery_app.start()
