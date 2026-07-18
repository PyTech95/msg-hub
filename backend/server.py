"""
NSTU - FastAPI backend
Multi-channel communications platform (SMS, WhatsApp, RCS, Voice).
Mock provider adapters allow full end-to-end demo without live credentials.
"""
from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import io
import csv
import uuid
import json
import random
import asyncio
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Literal

import bcrypt
import jwt
import pyotp
import qrcode
import qrcode.image.svg
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict

# ───────────────────────────── Setup ─────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger("cpaas")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"
ACCESS_TTL_MIN = 60 * 24  # 1 day for demo convenience

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="tezsandesh.digital API", version="1.0.0")
api = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ───────────────────────── Helpers ─────────────────────────
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()

def new_id() -> str:
    return str(uuid.uuid4())

def hash_pw(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

def verify_pw(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except Exception:
        return False

def make_token(user: dict) -> str:
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "role": user["role"],
        "tv": user.get("token_version", 1),
        "exp": now_utc() + timedelta(minutes=ACCESS_TTL_MIN),
        "iat": now_utc(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def clean(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    doc.pop("_id", None)
    doc.pop("password_hash", None)
    return doc

async def audit(action: str, target_type: str = "", target_id: str = "",
                actor: Optional[dict] = None, meta: Optional[dict] = None) -> None:
    """Record a structured audit event. Best-effort; never raises."""
    try:
        await db.audit_logs.insert_one({
            "id": new_id(),
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "actor_id": (actor or {}).get("id"),
            "actor_email": (actor or {}).get("email"),
            "actor_role": (actor or {}).get("role"),
            "company_id": (actor or {}).get("company_id"),
            "meta": meta or {},
            "created_at": iso(now_utc()),
        })
    except Exception as e:
        log.warning(f"audit failed: {e}")

# ───────────────────────── Auth Dependencies ─────────────────────────
async def current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(401, "User not found")
    if payload.get("tv", 1) != user.get("token_version", 1):
        raise HTTPException(401, "Token revoked. Please log in again.")
    return user

def require_roles(*roles: str):
    async def _dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles and user["role"] != "super_admin":
            raise HTTPException(403, f"Requires role: {roles}")
        return user
    return _dep

def platform_only(*roles: str):
    """Role check + must be a platform user (no company_id). Blocks company-scoped users."""
    async def _dep(user: dict = Depends(require_roles(*roles))) -> dict:
        if user.get("company_id"):
            raise HTTPException(403, "Platform-level access required")
        return user
    return _dep

# ───────────────────────── Multi-tenant helpers ─────────────────────────
def cflt(user: dict, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Tenant filter: company users see only their company's data; platform super admin sees all."""
    flt: Dict[str, Any] = dict(extra or {})
    if user.get("company_id"):
        flt["company_id"] = user["company_id"]
    return flt

async def with_company(user: dict) -> dict:
    if user.get("company_id"):
        comp = await db.companies.find_one({"id": user["company_id"]}, {"_id": 0, "name": 1})
        user["company_name"] = (comp or {}).get("name")
    return user

# ───────────────────────── Pydantic Models ─────────────────────────
Channel = Literal["sms", "whatsapp", "rcs", "voice"]
Role = Literal["super_admin", "admin", "agent"]

class LoginIn(BaseModel):
    email: EmailStr
    password: str
    otp: Optional[str] = None

class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Role = "agent"

class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    created_at: str

class ContactIn(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    tags: List[str] = []
    list_ids: List[str] = []
    dnd: bool = False
    notes: Optional[str] = None
    custom_fields: Dict[str, Any] = {}

class ContactUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    tags: Optional[List[str]] = None
    list_ids: Optional[List[str]] = None
    dnd: Optional[bool] = None
    opted_out: Optional[bool] = None
    notes: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None

class ListIn(BaseModel):
    name: str
    description: Optional[str] = None

class TemplateIn(BaseModel):
    name: str
    channel: Channel
    body: str
    variables: List[str] = []
    media_url: Optional[str] = None
    category: Optional[str] = None  # marketing, utility, authentication
    status: str = "approved"  # approved | pending | rejected

class CampaignIn(BaseModel):
    name: str
    channel: Channel
    template_id: str
    list_ids: List[str] = []
    contact_ids: List[str] = []
    schedule_at: Optional[str] = None  # ISO; None = send now
    variables_map: Dict[str, Any] = {}

class SendMessageIn(BaseModel):
    channel: Channel
    contact_id: str
    body: str = ""
    media_url: Optional[str] = None
    # WhatsApp-only: send an approved Meta template instead of free-form text.
    # Free-form text only delivers when the recipient messaged the business in the last 24h.
    # Templates (e.g. "hello_world") always deliver regardless.
    template_name: Optional[str] = None
    template_language: Optional[str] = "en_US"
    template_components: Optional[List[Dict[str, Any]]] = None

class CallIn(BaseModel):
    contact_id: str
    notes: Optional[str] = None

class ProviderIn(BaseModel):
    name: str
    channel: Channel
    provider_key: str  # twilio | gupshup | exotel | rbm | mock
    config: Dict[str, Any] = {}
    is_active: bool = True
    mock: bool = True

class WebhookIn(BaseModel):
    channel: Channel
    payload: Dict[str, Any]

# ───────────────────────── Mock Provider Layer ─────────────────────────
# A unified adapter interface. Real provider adapters can subclass & swap.
class BaseAdapter:
    channel: Channel = "sms"
    provider_key: str = "mock"

    async def send(self, to: str, body: str, media_url: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        # Simulate provider response
        return {"provider_message_id": f"mock_{secrets.token_hex(8)}", "accepted": True}

    async def simulate_lifecycle(self, message_id: str):
        """Emit queued → sent → delivered (and maybe replied) events."""
        await asyncio.sleep(0.4)
        await emit_event(message_id, "sent")
        await asyncio.sleep(0.8)
        # 90% delivered, 10% failed
        if random.random() < 0.9:
            await emit_event(message_id, "delivered")
            # 25% chance of inbound reply for messaging channels
            if self.channel in ("sms", "whatsapp", "rcs") and random.random() < 0.25:
                await asyncio.sleep(1.2)
                await emit_inbound_reply(message_id)
        else:
            await emit_event(message_id, "failed", reason="carrier_rejected")

class SMSAdapter(BaseAdapter):
    channel = "sms"

class WhatsAppAdapter(BaseAdapter):
    channel = "whatsapp"

class RCSAdapter(BaseAdapter):
    channel = "rcs"

class VoiceAdapter(BaseAdapter):
    channel = "voice"

    async def simulate_lifecycle(self, message_id: str):
        # Voice: ringing → answered → completed | no-answer
        await asyncio.sleep(0.5)
        await emit_event(message_id, "ringing")
        await asyncio.sleep(1.0)
        outcomes = ["answered", "no-answer", "busy"]
        result = random.choices(outcomes, weights=[0.7, 0.2, 0.1])[0]
        if result == "answered":
            await emit_event(message_id, "answered")
            await asyncio.sleep(1.5)
            duration = random.randint(20, 240)
            recording = f"https://mock-recordings.cpaas.io/{message_id}.mp3"
            await db.call_logs.update_one(
                {"id": message_id},
                {"$set": {"status": "completed", "duration_sec": duration, "recording_url": recording, "ended_at": iso(now_utc())}},
            )
            await emit_event(message_id, "completed", duration=duration, recording_url=recording)
        else:
            await db.call_logs.update_one({"id": message_id}, {"$set": {"status": result, "ended_at": iso(now_utc())}})
            await emit_event(message_id, result)

class EmailAdapter(BaseAdapter):
    """Mock email adapter; swap with Resend/SendGrid later (creds via Providers UI)."""
    channel = "email"  # type: ignore
    async def send(self, to: str, body: str, media_url=None, **kwargs):
        log.info(f"[mock email] to={to} body={(body or '')[:80]} attachment={media_url}")
        return {"provider_message_id": f"email_{secrets.token_hex(8)}", "accepted": True}

ADAPTERS: Dict[str, BaseAdapter] = {
    "sms": SMSAdapter(),
    "whatsapp": WhatsAppAdapter(),
    "rcs": RCSAdapter(),
    "voice": VoiceAdapter(),
    "email": EmailAdapter(),
}

# ── Airtel IQ live adapters (transparent mock fallback when creds absent) ────
try:
    from adapters.airtel_iq import build_adapters as _aiq_build, AirtelIQConfig as _AIQCfg
    _aiq = _aiq_build(BaseAdapter)
    ADAPTERS["sms"] = _aiq["sms"]
    ADAPTERS["whatsapp"] = _aiq["whatsapp"]
    ADAPTERS["voice"] = _aiq["voice"]
    AIRTEL_IQ_CFG: Optional[_AIQCfg] = _aiq["cfg"]
    log.info("Airtel IQ adapters wired (live=%s)", AIRTEL_IQ_CFG.live)
except Exception as _e:
    log.warning("Airtel IQ adapter init skipped: %s", _e)
    AIRTEL_IQ_CFG = None

# ── Meta WhatsApp Cloud API adapter (per-tenant → vault → env; mock fallback) ──
from adapters import meta_whatsapp as meta_wa

async def meta_wa_credentials(company_id: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Resolve live credentials:
    1) Per-tenant config in `company_whatsapp_configs`
    2) Global Provider Vault (`provider_accounts` where provider_key='meta_whatsapp')
    3) Environment variables (WHATSAPP_ACCESS_TOKEN + WHATSAPP_PHONE_NUMBER_ID)
    Returns None → adapter runs in mock (demo) or hard-fails (production).
    """
    # 1) Per-tenant
    if company_id:
        cfg = await db.company_whatsapp_configs.find_one(
            {"company_id": company_id, "is_active": True}, {"_id": 0})
        if (cfg and not cfg.get("mock", True)
                and cfg.get("access_token") and cfg.get("phone_number_id")):
            return {
                "access_token": cfg["access_token"],
                "phone_number_id": cfg["phone_number_id"],
                "graph_version": cfg.get("graph_version") or os.environ.get("GRAPH_API_VERSION") or "v22.0",
                "waba_id": cfg.get("waba_id") or "",
            }
    # 2) Global vault
    p = await db.provider_accounts.find_one({"provider_key": "meta_whatsapp", "is_active": True}, {"_id": 0})
    creds = (p or {}).get("credentials") or {}
    if p and not p.get("mock", True) and creds.get("access_token") and creds.get("phone_number_id"):
        return {
            "access_token": creds["access_token"],
            "phone_number_id": creds["phone_number_id"],
            "graph_version": creds.get("graph_version") or os.environ.get("GRAPH_API_VERSION") or "v22.0",
            "waba_id": creds.get("waba_id") or os.environ.get("WHATSAPP_WABA_ID") or "",
        }
    # 3) Env fallback
    env = meta_wa.env_config()
    if env:
        env["waba_id"] = os.environ.get("WHATSAPP_WABA_ID") or ""
    return env

ADAPTERS["whatsapp"] = meta_wa.build_adapter(BaseAdapter, meta_wa_credentials)
log.info("Meta WhatsApp Cloud adapter wired (env_live=%s, multi-tenant capable)", bool(meta_wa.env_config()))

PRICING = {"sms": 0.25, "whatsapp": 0.40, "rcs": 0.50, "voice": 1.20, "email": 0.10}  # INR per unit (msg or min)

async def emit_event(message_id: str, event_type: str, **extra):
    evt = {
        "id": new_id(),
        "message_id": message_id,
        "type": event_type,
        "payload": extra,
        "created_at": iso(now_utc()),
    }
    await db.message_events.insert_one(evt)
    # update message status (or call status above already handles voice)
    msg = await db.messages.find_one({"id": message_id}, {"_id": 0})
    if msg:
        await db.messages.update_one({"id": message_id}, {"$set": {"status": event_type, "updated_at": iso(now_utc())}})
    # campaign stat increment
    if msg and msg.get("campaign_id"):
        field = f"stats.{event_type}"
        await db.campaigns.update_one({"id": msg["campaign_id"]}, {"$inc": {field: 1}})

async def emit_inbound_reply(message_id: str):
    msg = await db.messages.find_one({"id": message_id}, {"_id": 0})
    if not msg:
        return
    sample_replies = ["Thanks!", "Tell me more.", "STOP", "Yes please", "Not interested", "Call me back"]
    body = random.choice(sample_replies)
    inbound = {
        "id": new_id(),
        "channel": msg["channel"],
        "contact_id": msg["contact_id"],
        "direction": "inbound",
        "body": body,
        "status": "received",
        "provider_message_id": f"mock_in_{secrets.token_hex(6)}",
        "campaign_id": None,
        "company_id": msg.get("company_id"),
        "created_at": iso(now_utc()),
        "updated_at": iso(now_utc()),
    }
    await db.messages.insert_one(inbound)
    await db.message_events.insert_one({
        "id": new_id(),
        "message_id": inbound["id"],
        "type": "received",
        "payload": {"body": body},
        "created_at": iso(now_utc()),
    })
    await db.campaigns.update_one({"id": msg.get("campaign_id") or "_"}, {"$inc": {"stats.replied": 1}})
    await db.conversations.update_one(
        {"contact_id": msg["contact_id"], "channel": msg["channel"]},
        {"$set": {"last_message_at": iso(now_utc()), "last_message": body, "unread": True, "company_id": msg.get("company_id")}},
        upsert=True,
    )
    if body.strip().upper() == "STOP":
        await db.contacts.update_one({"id": msg["contact_id"]}, {"$set": {"opted_out": True}})

async def deliver_message(message_id: str, channel: Channel):
    adapter = ADAPTERS[channel]
    await adapter.simulate_lifecycle(message_id)
    # usage accounting
    msg = await db.messages.find_one({"id": message_id}, {"_id": 0, "company_id": 1})
    await db.usage_records.insert_one({
        "id": new_id(),
        "channel": channel,
        "message_id": message_id,
        "units": 1,
        "amount": PRICING[channel],
        "currency": "INR",
        "company_id": (msg or {}).get("company_id"),
        "created_at": iso(now_utc()),
    })

# ───────────────────────── Startup: indexes + seed ─────────────────────────
@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.contacts.create_index("phone")
    await db.messages.create_index([("contact_id", 1), ("created_at", -1)])
    await db.message_events.create_index([("message_id", 1), ("created_at", -1)])
    await db.conversations.create_index([("contact_id", 1), ("channel", 1)], unique=True)
    await db.call_logs.create_index([("contact_id", 1), ("created_at", -1)])
    await db.webhook_events.create_index([("created_at", -1)])
    await db.audit_logs.create_index([("created_at", -1)])
    await db.password_reset_tokens.create_index("token", unique=True)
    await db.system_settings.create_index("key", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.company_whatsapp_configs.create_index("company_id", unique=True)
    await db.wallets.create_index("company_id", unique=True)
    await db.wallet_transactions.create_index([("company_id", 1), ("created_at", -1)])
    await db.wallet_recharge_orders.create_index("razorpay_order_id", unique=True)
    await seed()
    asyncio.create_task(campaign_scheduler_loop())
    log.info("CPaaS backend ready.")

@app.on_event("shutdown")
async def on_shutdown():
    client.close()


async def seed():
    # Users
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@cpaas.io")
    admin_pw = os.environ.get("ADMIN_PASSWORD", "Admin@12345")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "id": new_id(), "email": admin_email, "password_hash": hash_pw(admin_pw),
            "name": "Super Admin", "role": "super_admin", "token_version": 1,
            "created_at": iso(now_utc()),
        })
    else:
        upd = {}
        if not verify_pw(admin_pw, existing["password_hash"]):
            upd["password_hash"] = hash_pw(admin_pw)
        if "token_version" not in existing:
            upd["token_version"] = 1
        if upd:
            await db.users.update_one({"email": admin_email}, {"$set": upd})

    agent_email = "agent@cpaas.io"
    if not await db.users.find_one({"email": agent_email}):
        await db.users.insert_one({
            "id": new_id(), "email": agent_email, "password_hash": hash_pw("Agent@12345"),
            "name": "Ravi Sharma", "role": "agent", "token_version": 1,
            "created_at": iso(now_utc()),
        })
    # Backfill token_version on legacy users
    await db.users.update_many({"token_version": {"$exists": False}}, {"$set": {"token_version": 1}})

    # Seed default markup config (super admin can change later)
    if not await db.system_settings.find_one({"key": "markup_pct"}):
        await db.system_settings.insert_one({
            "key": "markup_pct",
            "value": {"sms": 20, "whatsapp": 25, "rcs": 30, "voice": 15},
            "updated_at": iso(now_utc()),
        })

    # Meta WhatsApp Cloud provider entry (idempotent)
    if not await db.provider_accounts.find_one({"provider_key": "meta_whatsapp"}):
        await db.provider_accounts.insert_one({
            "id": new_id(), "name": "Meta WhatsApp Cloud", "channel": "whatsapp",
            "provider_key": "meta_whatsapp",
            "config": {"docs": "https://developers.facebook.com/docs/whatsapp/cloud-api",
                       "webhook_path": "/api/webhook/whatsapp"},
            "credentials": {}, "is_active": True, "mock": True, "created_at": iso(now_utc()),
        })

    # Demo sample data — only in demo mode, and only once
    if (os.environ.get("DEMO_MODE") or "true").strip().lower() != "true":
        return
    if await db.contacts.count_documents({}) > 0:
        return

    # Lists
    list_promo_id, list_vip_id, list_new_id = new_id(), new_id(), new_id()
    await db.contact_lists.insert_many([
        {"id": list_promo_id, "name": "Diwali Promo", "description": "Festive campaign audience", "created_at": iso(now_utc())},
        {"id": list_vip_id, "name": "VIP Customers", "description": "Top tier", "created_at": iso(now_utc())},
        {"id": list_new_id, "name": "New Signups", "description": "Last 30 days", "created_at": iso(now_utc())},
    ])

    sample_names = [
        ("Aarav Mehta", "+919876543210"), ("Priya Iyer", "+919812345678"), ("Rohan Kapoor", "+919998877665"),
        ("Sneha Reddy", "+919812340099"), ("Vikram Singh", "+918765432109"), ("Ananya Joshi", "+917654321098"),
        ("Karan Verma", "+916543210987"), ("Isha Banerjee", "+919900112233"), ("Manish Gupta", "+919800123456"),
        ("Neha Pillai", "+918800123456"), ("Arjun Nair", "+917700123456"), ("Riya Malhotra", "+916600123456"),
        ("Dev Patel", "+919955667788"), ("Tara Bhatt", "+919844556677"), ("Sahil Chawla", "+919733445566"),
    ]
    contacts = []
    for i, (nm, ph) in enumerate(sample_names):
        cid = new_id()
        lists = []
        if i % 3 == 0: lists.append(list_promo_id)
        if i % 5 == 0: lists.append(list_vip_id)
        if i < 6: lists.append(list_new_id)
        contacts.append({
            "id": cid, "name": nm, "phone": ph,
            "email": nm.lower().replace(" ", ".") + "@example.com",
            "tags": ["customer"] + (["vip"] if list_vip_id in lists else []),
            "list_ids": lists, "dnd": False, "opted_out": False,
            "notes": "", "custom_fields": {"city": random.choice(["Mumbai","Delhi","Bangalore","Pune","Chennai"])},
            "created_at": iso(now_utc()),
        })
    await db.contacts.insert_many(contacts)

    # Templates
    templates = [
        {"id": new_id(), "name": "Welcome SMS", "channel": "sms", "body": "Hi {{name}}, welcome to tezsandesh.digital!", "variables": ["name"], "status": "approved", "category": "utility", "created_at": iso(now_utc())},
        {"id": new_id(), "name": "WA Order Update", "channel": "whatsapp", "body": "Hello {{name}}, your order #{{order_id}} has shipped.", "variables": ["name","order_id"], "status": "approved", "category": "utility", "created_at": iso(now_utc())},
        {"id": new_id(), "name": "RCS Diwali Offer", "channel": "rcs", "body": "🪔 {{name}}, enjoy 30% off this Diwali!", "variables": ["name"], "status": "approved", "category": "marketing", "created_at": iso(now_utc())},
        {"id": new_id(), "name": "Voice OTP Verify", "channel": "voice", "body": "Your verification code is {{code}}", "variables": ["code"], "status": "approved", "category": "authentication", "created_at": iso(now_utc())},
    ]
    await db.templates.insert_many(templates)

    # Providers
    providers = [
        {"id": new_id(), "name": "Airtel IQ SMS", "channel": "sms", "provider_key": "airtel_iq",
         "config": {"docs": "https://www.airtel.in/business/b2b/airtel-iq/api-docs/sms/sms-utility"},
         "credentials": {}, "is_active": True, "mock": True, "created_at": iso(now_utc())},
        {"id": new_id(), "name": "Airtel IQ WhatsApp", "channel": "whatsapp", "provider_key": "airtel_iq",
         "config": {"docs": "https://www.airtel.in/b2b/whatsapp-api"},
         "credentials": {}, "is_active": True, "mock": True, "created_at": iso(now_utc())},
        {"id": new_id(), "name": "Airtel IQ Voice", "channel": "voice", "provider_key": "airtel_iq",
         "config": {"docs": "https://www.airtel.in/business/b2b/airtel-iq/api-docs/voice/callflow-api"},
         "credentials": {}, "is_active": True, "mock": True, "created_at": iso(now_utc())},
        {"id": new_id(), "name": "Twilio SMS (Mock)", "channel": "sms", "provider_key": "twilio", "config": {"sid": "ACxxx", "from": "+15005550006"}, "is_active": True, "mock": True, "created_at": iso(now_utc())},
        {"id": new_id(), "name": "Gupshup WhatsApp (Mock)", "channel": "whatsapp", "provider_key": "gupshup", "config": {"app_name": "demo"}, "is_active": True, "mock": True, "created_at": iso(now_utc())},
        {"id": new_id(), "name": "Google RBM (Mock)", "channel": "rcs", "provider_key": "rbm", "config": {"agent_id": "demo-agent"}, "is_active": True, "mock": True, "created_at": iso(now_utc())},
        {"id": new_id(), "name": "Exotel Voice (Mock)", "channel": "voice", "provider_key": "exotel", "config": {"sid": "exo-demo"}, "is_active": True, "mock": True, "created_at": iso(now_utc())},
    ]
    await db.provider_accounts.insert_many(providers)

    # Sample campaign + messages + events for charts
    sample_campaign = {
        "id": new_id(),
        "name": "Diwali Promo Blast",
        "channel": "whatsapp",
        "template_id": templates[1]["id"],
        "list_ids": [list_promo_id],
        "contact_ids": [],
        "schedule_at": None,
        "status": "completed",
        "stats": {"queued": 0, "sent": 12, "delivered": 11, "failed": 1, "replied": 3},
        "created_by": admin_email,
        "created_at": iso(now_utc() - timedelta(days=2)),
        "completed_at": iso(now_utc() - timedelta(days=2, hours=-1)),
    }
    camp2 = {
        "id": new_id(), "name": "OTP Voice Verify", "channel": "voice",
        "template_id": templates[3]["id"], "list_ids": [], "contact_ids": [c["id"] for c in contacts[:5]],
        "schedule_at": None, "status": "completed",
        "stats": {"queued": 0, "sent": 5, "answered": 4, "completed": 4, "no-answer": 1, "failed": 0, "replied": 0},
        "created_by": admin_email, "created_at": iso(now_utc() - timedelta(days=1)),
    }
    camp3 = {
        "id": new_id(), "name": "New Signup SMS", "channel": "sms",
        "template_id": templates[0]["id"], "list_ids": [list_new_id], "contact_ids": [],
        "schedule_at": iso(now_utc() + timedelta(hours=12)), "status": "scheduled",
        "stats": {"queued": 6, "sent": 0, "delivered": 0, "failed": 0, "replied": 0},
        "created_by": admin_email, "created_at": iso(now_utc()),
    }
    await db.campaigns.insert_many([sample_campaign, camp2, camp3])

    # historical messages for charts (mix of channels, last 7 days)
    hist_msgs = []
    hist_events = []
    statuses_msg = ["delivered"] * 8 + ["failed"] * 1 + ["sent"] * 1
    for day_offset in range(7):
        day = now_utc() - timedelta(days=day_offset)
        for _ in range(random.randint(8, 18)):
            ch: Channel = random.choices(["sms","whatsapp","rcs","voice"], weights=[0.4,0.35,0.15,0.1])[0]
            c = random.choice(contacts)
            mid = new_id()
            st = random.choice(statuses_msg)
            hist_msgs.append({
                "id": mid, "channel": ch, "contact_id": c["id"], "direction": "outbound",
                "body": f"Sample {ch} message", "status": st,
                "provider_message_id": f"mock_{secrets.token_hex(6)}",
                "campaign_id": sample_campaign["id"] if ch == "whatsapp" else None,
                "created_at": iso(day - timedelta(minutes=random.randint(0, 1400))),
                "updated_at": iso(day),
            })
            hist_events.append({"id": new_id(), "message_id": mid, "type": st, "payload": {}, "created_at": iso(day)})
    if hist_msgs:
        await db.messages.insert_many(hist_msgs)
        await db.message_events.insert_many(hist_events)

    # sample voice calls
    calls = []
    for c in contacts[:10]:
        cid = new_id()
        status = random.choice(["completed", "no-answer", "busy", "completed"])
        calls.append({
            "id": cid, "contact_id": c["id"], "direction": "outbound",
            "status": status,
            "duration_sec": random.randint(15, 240) if status == "completed" else 0,
            "recording_url": f"https://mock-recordings.cpaas.io/{cid}.mp3" if status == "completed" else None,
            "provider_call_id": f"mock_{secrets.token_hex(6)}",
            "notes": "Welcome call",
            "started_at": iso(now_utc() - timedelta(hours=random.randint(1, 70))),
            "ended_at": iso(now_utc() - timedelta(hours=random.randint(0, 1))),
            "created_at": iso(now_utc() - timedelta(hours=random.randint(1, 70))),
        })
    if calls:
        await db.call_logs.insert_many(calls)

    # webhook events sample
    whs = []
    for _ in range(8):
        ch = random.choice(["sms","whatsapp","rcs","voice"])
        whs.append({
            "id": new_id(), "channel": ch,
            "event_type": random.choice(["delivered","failed","received","status_update"]),
            "payload": {"to": "+9198xxxx", "from": "BRAND", "status": "delivered"},
            "signature_valid": True,
            "processed": True,
            "created_at": iso(now_utc() - timedelta(minutes=random.randint(1, 1000))),
        })
    if whs:
        await db.webhook_events.insert_many(whs)

    # usage records snapshot
    usage = []
    for m in hist_msgs:
        usage.append({"id": new_id(), "channel": m["channel"], "message_id": m["id"], "units": 1, "amount": PRICING[m["channel"]], "currency": "INR", "created_at": m["created_at"]})
    if usage:
        await db.usage_records.insert_many(usage)

    log.info("Seed complete.")


# ───────────────────────── Auth routes ─────────────────────────
@api.post("/auth/login")
async def login(body: LoginIn, response: Response, request: Request):
    email = body.email.lower()
    ip = request.client.host if request.client else "unknown"
    # Use email-only identifier (K8s ingress IP is unreliable behind proxy)
    ident = email

    # Brute-force lockout: 5 fails / 15 min
    attempt = await db.login_attempts.find_one({"identifier": ident})
    if attempt and attempt.get("fails", 0) >= 5:
        try:
            locked_until = datetime.fromisoformat(attempt["locked_until"].replace("Z","+00:00"))
            if locked_until > now_utc():
                raise HTTPException(429, f"Too many failed attempts. Try again in {int((locked_until - now_utc()).total_seconds())}s")
        except HTTPException:
            raise
        except Exception:
            pass

    user = await db.users.find_one({"email": email})
    if not user or not verify_pw(body.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": ident},
            {"$inc": {"fails": 1},
             "$set": {"locked_until": iso(now_utc() + timedelta(minutes=15)), "last_fail_at": iso(now_utc())}},
            upsert=True,
        )
        await audit("login_failed", "user", "", None, {"email": email, "ip": ip})
        raise HTTPException(401, "Invalid credentials")

    # Company gating: users of a deactivated company cannot log in
    if user.get("company_id"):
        comp = await db.companies.find_one({"id": user["company_id"]}, {"_id": 0})
        if not comp or comp.get("is_active") is False:
            raise HTTPException(403, "Your company account is deactivated. Contact tezsandesh support.")

    # 2FA challenge: if user has 2FA enabled and no otp provided, ask for it
    if user.get("totp_enabled") and not body.otp:
        return {"otp_required": True, "message": "Enter the 6-digit code from your authenticator"}
    if user.get("totp_enabled"):
        totp = pyotp.TOTP(user["totp_secret"])
        if not totp.verify(body.otp or "", valid_window=1):
            await db.login_attempts.update_one(
                {"identifier": ident},
                {"$inc": {"fails": 1}, "$set": {"locked_until": iso(now_utc() + timedelta(minutes=15))}},
                upsert=True,
            )
            await audit("login_failed_otp", "user", user["id"], None, {"email": email})
            raise HTTPException(401, "Invalid OTP")

    # Success: clear attempts
    await db.login_attempts.delete_one({"identifier": ident})
    token = make_token({"id": user["id"], "email": user["email"], "role": user["role"], "token_version": user.get("token_version", 1)})
    response.set_cookie("access_token", token, httponly=True, samesite="lax", max_age=ACCESS_TTL_MIN*60, path="/")
    await audit("login", "user", user["id"], user, {"ip": ip})
    return {"token": token, "user": await with_company(clean(user))}

@api.post("/auth/register")
async def register(body: RegisterIn, user: dict = Depends(require_roles("super_admin","admin"))):
    if await db.users.find_one({"email": body.email.lower()}):
        raise HTTPException(409, "Email already exists")
    if user.get("company_id") and body.role == "super_admin":
        raise HTTPException(403, "Company admins cannot create super admins")
    doc = {
        "id": new_id(), "email": body.email.lower(), "password_hash": hash_pw(body.password),
        "name": body.name, "role": body.role, "company_id": user.get("company_id"),
        "token_version": 1, "created_at": iso(now_utc()),
    }
    await db.users.insert_one(doc)
    await audit("user_created", "user", doc["id"], user, {"email": doc["email"], "role": doc["role"]})
    return clean(doc)

@api.post("/auth/logout")
async def logout(response: Response, _: dict = Depends(current_user)):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}

@api.get("/auth/me")
async def me(user: dict = Depends(current_user)):
    return await with_company(user)

class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str

@api.post("/auth/change-password")
async def change_password(body: ChangePasswordIn, response: Response, user: dict = Depends(current_user)):
    full = await db.users.find_one({"id": user["id"]})
    if not full or not verify_pw(body.old_password, full["password_hash"]):
        raise HTTPException(400, "Current password is incorrect")
    if len(body.new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    new_tv = full.get("token_version", 1) + 1
    await db.users.update_one({"id": user["id"]}, {"$set": {
        "password_hash": hash_pw(body.new_password),
        "token_version": new_tv,
    }})
    new_token = make_token({"id": user["id"], "email": user["email"], "role": user["role"], "token_version": new_tv})
    response.set_cookie("access_token", new_token, httponly=True, samesite="lax", max_age=ACCESS_TTL_MIN*60, path="/")
    await audit("password_changed", "user", user["id"], user)
    return {"ok": True, "token": new_token}

# ───────── 2FA TOTP ─────────
class TOTPEnableIn(BaseModel):
    code: str

class TOTPDisableIn(BaseModel):
    password: str

@api.post("/auth/2fa/setup")
async def totp_setup(user: dict = Depends(current_user)):
    """Generate a TOTP secret + provisioning URI. Does NOT enable until verified."""
    full = await db.users.find_one({"id": user["id"]})
    if full and full.get("totp_enabled"):
        raise HTTPException(400, "2FA already enabled. Disable first to rotate.")
    secret = pyotp.random_base32()
    await db.users.update_one({"id": user["id"]}, {"$set": {"totp_secret_pending": secret}})
    uri = pyotp.TOTP(secret).provisioning_uri(name=user["email"], issuer_name="tezsandesh.digital")
    # Render QR as data-URI SVG for inline display
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgImage)
    buf = io.BytesIO(); img.save(buf)
    svg = buf.getvalue().decode("utf-8")
    qr_data_uri = "data:image/svg+xml;base64," + __import__("base64").b64encode(svg.encode()).decode()
    return {"secret": secret, "provisioning_uri": uri, "qr_data_uri": qr_data_uri}

@api.post("/auth/2fa/enable")
async def totp_enable(body: TOTPEnableIn, user: dict = Depends(current_user)):
    full = await db.users.find_one({"id": user["id"]})
    secret = (full or {}).get("totp_secret_pending")
    if not secret:
        raise HTTPException(400, "Run /auth/2fa/setup first")
    if not pyotp.TOTP(secret).verify(body.code, valid_window=1):
        raise HTTPException(400, "Invalid code")
    await db.users.update_one({"id": user["id"]}, {
        "$set": {"totp_secret": secret, "totp_enabled": True},
        "$unset": {"totp_secret_pending": ""},
    })
    await audit("2fa_enabled", "user", user["id"], user)
    return {"ok": True}

@api.post("/auth/2fa/disable")
async def totp_disable(body: TOTPDisableIn, user: dict = Depends(current_user)):
    full = await db.users.find_one({"id": user["id"]})
    if not full or not verify_pw(body.password, full["password_hash"]):
        raise HTTPException(400, "Password incorrect")
    await db.users.update_one({"id": user["id"]}, {
        "$set": {"totp_enabled": False},
        "$unset": {"totp_secret": "", "totp_secret_pending": ""},
    })
    await audit("2fa_disabled", "user", user["id"], user)
    return {"ok": True}

@api.get("/auth/2fa/status")
async def totp_status(user: dict = Depends(current_user)):
    full = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {"enabled": bool((full or {}).get("totp_enabled"))}
class ForgotPasswordIn(BaseModel):
    email: EmailStr

class ResetPasswordIn(BaseModel):
    token: str
    new_password: str

@api.post("/auth/forgot-password")
async def forgot_password(body: ForgotPasswordIn):
    user = await db.users.find_one({"email": body.email.lower()})
    if user:
        recent = await db.password_reset_tokens.find_one(
            {"user_id": user["id"], "used": False},
            sort=[("created_at", -1)],
        )
        if recent:
            try:
                created = datetime.fromisoformat(recent["created_at"].replace("Z","+00:00"))
                if (now_utc() - created).total_seconds() < 60:
                    return {"ok": True, "message": "If the email exists, a reset link has been generated."}
            except Exception:
                pass
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({
            "id": new_id(),
            "user_id": user["id"],
            "token": token,
            "used": False,
            "expires_at": iso(now_utc() + timedelta(hours=1)),
            "created_at": iso(now_utc()),
        })
        reset_link = f"/reset-password?token={token}"
        log.info(f"PASSWORD RESET for {user['email']} → {reset_link}")
        await audit("password_reset_requested", "user", user["id"], None, {"email": user["email"]})
    return {"ok": True, "message": "If the email exists, a reset link has been generated. Check server logs (demo mode)."}

@api.post("/auth/reset-password")
async def reset_password(body: ResetPasswordIn):
    if len(body.new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    rec = await db.password_reset_tokens.find_one({"token": body.token, "used": False})
    if not rec:
        raise HTTPException(400, "Invalid or used token")
    try:
        exp = datetime.fromisoformat(rec["expires_at"].replace("Z","+00:00"))
        if exp < now_utc():
            raise HTTPException(400, "Token expired")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Invalid token")
    user = await db.users.find_one({"id": rec["user_id"]})
    if not user:
        raise HTTPException(400, "User not found")
    new_tv = user.get("token_version", 1) + 1
    await db.users.update_one({"id": user["id"]}, {"$set": {
        "password_hash": hash_pw(body.new_password),
        "token_version": new_tv,
    }})
    await db.password_reset_tokens.update_one({"id": rec["id"]}, {"$set": {"used": True}})
    await audit("password_reset_completed", "user", user["id"])
    return {"ok": True}

# ───────────────────────── Users / Team ─────────────────────────
@api.get("/users")
async def list_users(user: dict = Depends(current_user)):
    return await db.users.find(cflt(user), {"_id": 0, "password_hash": 0}).to_list(500)

@api.delete("/users/{user_id}")
async def delete_user(user_id: str, actor: dict = Depends(require_roles("super_admin","admin"))):
    if user_id == actor["id"]:
        raise HTTPException(400, "Cannot delete yourself")
    target = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not target:
        raise HTTPException(404, "User not found")
    if actor.get("company_id") and target.get("company_id") != actor["company_id"]:
        raise HTTPException(403, "Cannot delete users outside your company")
    await db.users.delete_one({"id": user_id})
    await audit("user_deleted", "user", user_id, actor, {"target_email": target.get("email")})
    return {"ok": True}

# ───────────────────────── Companies (multi-tenant SaaS) ─────────────────────────
class CompanyIn(BaseModel):
    name: str
    admin_email: EmailStr
    admin_password: str
    admin_name: Optional[str] = None

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

TENANT_COLLECTIONS = [
    "contacts", "contact_lists", "templates", "campaigns", "campaign_recipients",
    "messages", "conversations", "call_logs", "bills", "bill_batches",
    "notice_templates", "notice_pdfs", "voice_campaigns", "reminder_schedules",
    "usage_records", "audit_logs", "company_whatsapp_configs",
    "wallets", "wallet_transactions", "wallet_recharge_orders",
]

@api.get("/companies")
async def list_companies(_: dict = Depends(require_roles("super_admin"))):
    comps = await db.companies.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    for c in comps:
        cid = c["id"]
        c["stats"] = {
            "users": await db.users.count_documents({"company_id": cid}),
            "contacts": await db.contacts.count_documents({"company_id": cid}),
            "messages": await db.messages.count_documents({"company_id": cid}),
            "campaigns": await db.campaigns.count_documents({"company_id": cid}),
        }
        wa = await db.company_whatsapp_configs.find_one({"company_id": cid}, {"_id": 0, "phone_number_id": 1, "mock": 1, "is_active": 1})
        c["whatsapp"] = {
            "configured": bool(wa),
            "live": bool(wa and not wa.get("mock", True) and wa.get("is_active", True)),
            "phone_number_id": (wa or {}).get("phone_number_id", ""),
        }
        agg = await db.usage_records.aggregate([
            {"$match": {"company_id": cid}},
            {"$group": {"_id": None, "amount": {"$sum": "$amount"}, "units": {"$sum": "$units"}}},
        ]).to_list(1)
        c["usage"] = {"amount": round(agg[0]["amount"], 2) if agg else 0, "units": agg[0]["units"] if agg else 0}
    return comps

@api.post("/companies")
async def create_company(body: CompanyIn, actor: dict = Depends(require_roles("super_admin"))):
    if await db.users.find_one({"email": body.admin_email.lower()}):
        raise HTTPException(409, "Admin email already exists")
    if len(body.admin_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    comp = {"id": new_id(), "name": body.name.strip(), "is_active": True,
            "admin_email": body.admin_email.lower(), "created_at": iso(now_utc())}
    await db.companies.insert_one(comp)
    admin_user = {
        "id": new_id(), "email": body.admin_email.lower(), "password_hash": hash_pw(body.admin_password),
        "name": body.admin_name or f"{body.name.strip()} Admin", "role": "admin",
        "company_id": comp["id"], "token_version": 1, "created_at": iso(now_utc()),
    }
    await db.users.insert_one(admin_user)
    await audit("company_created", "company", comp["id"], actor, {"name": comp["name"], "admin_email": admin_user["email"]})
    return clean(comp)

@api.patch("/companies/{company_id}")
async def update_company(company_id: str, body: CompanyUpdate, actor: dict = Depends(require_roles("super_admin"))):
    upd = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not upd:
        raise HTTPException(400, "No fields")
    await db.companies.update_one({"id": company_id}, {"$set": upd})
    await audit("company_updated", "company", company_id, actor, upd)
    return await db.companies.find_one({"id": company_id}, {"_id": 0})

@api.delete("/companies/{company_id}")
async def delete_company(company_id: str, actor: dict = Depends(require_roles("super_admin"))):
    comp = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not comp:
        raise HTTPException(404, "Not found")
    msg_ids = [m["id"] for m in await db.messages.find({"company_id": company_id}, {"_id": 0, "id": 1}).to_list(100000)]
    if msg_ids:
        await db.message_events.delete_many({"message_id": {"$in": msg_ids}})
    for coll in TENANT_COLLECTIONS:
        await db[coll].delete_many({"company_id": company_id})
    await db.users.delete_many({"company_id": company_id})
    await db.companies.delete_one({"id": company_id})
    await audit("company_deleted", "company", company_id, actor, {"name": comp.get("name")})
    return {"ok": True}

# ───────────────────────── Contacts ─────────────────────────
@api.get("/contacts")
async def list_contacts(q: Optional[str] = None, list_id: Optional[str] = None, user: dict = Depends(current_user)):
    flt: Dict[str, Any] = cflt(user)
    if q:
        flt["$or"] = [{"name": {"$regex": q, "$options": "i"}}, {"phone": {"$regex": q}}, {"email": {"$regex": q, "$options": "i"}}]
    if list_id:
        flt["list_ids"] = list_id
    docs = await db.contacts.find(flt, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs

@api.post("/contacts")
async def create_contact(body: ContactIn, user: dict = Depends(current_user)):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["opted_out"] = False
    doc["company_id"] = user.get("company_id")
    doc["created_at"] = iso(now_utc())
    await db.contacts.insert_one(doc)
    return clean(doc)

@api.get("/contacts/{contact_id}")
async def get_contact(contact_id: str, user: dict = Depends(current_user)):
    c = await db.contacts.find_one(cflt(user, {"id": contact_id}), {"_id": 0})
    if not c:
        raise HTTPException(404, "Contact not found")
    return c

@api.patch("/contacts/{contact_id}")
async def update_contact(contact_id: str, body: ContactUpdate, user: dict = Depends(current_user)):
    upd = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not upd:
        raise HTTPException(400, "No fields")
    res = await db.contacts.update_one(cflt(user, {"id": contact_id}), {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Contact not found")
    return await db.contacts.find_one(cflt(user, {"id": contact_id}), {"_id": 0})

@api.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str, user: dict = Depends(require_roles("super_admin","admin"))):
    await db.contacts.delete_one(cflt(user, {"id": contact_id}))
    return {"ok": True}

@api.post("/contacts/bulk-delete")
async def bulk_delete_contacts(ids: List[str], user: dict = Depends(require_roles("super_admin","admin"))):
    res = await db.contacts.delete_many(cflt(user, {"id": {"$in": ids}}))
    return {"deleted": res.deleted_count}

@api.post("/contacts/import")
async def import_contacts_csv(file: UploadFile = File(...), user: dict = Depends(current_user)):
    raw = (await file.read()).decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(raw))
    inserted = 0
    skipped = 0
    docs = []
    for row in reader:
        phone = (row.get("phone") or row.get("mobile") or "").strip()
        name = (row.get("name") or row.get("full_name") or "").strip()
        if not phone or not name:
            skipped += 1
            continue
        docs.append({
            "id": new_id(), "name": name, "phone": phone,
            "email": (row.get("email") or "").strip() or None,
            "tags": [t.strip() for t in (row.get("tags") or "").split(",") if t.strip()],
            "list_ids": [], "dnd": False, "opted_out": False, "notes": "",
            "custom_fields": {}, "company_id": user.get("company_id"), "created_at": iso(now_utc()),
        })
    if docs:
        await db.contacts.insert_many(docs)
        inserted = len(docs)
    return {"inserted": inserted, "skipped": skipped}

# ───────────────────────── Lists ─────────────────────────
@api.get("/lists")
async def list_lists(user: dict = Depends(current_user)):
    return await db.contact_lists.find(cflt(user), {"_id": 0}).sort("created_at", -1).to_list(500)

@api.post("/lists")
async def create_list(body: ListIn, user: dict = Depends(current_user)):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["company_id"] = user.get("company_id")
    doc["created_at"] = iso(now_utc())
    await db.contact_lists.insert_one(doc)
    return clean(doc)

@api.delete("/lists/{list_id}")
async def delete_list(list_id: str, user: dict = Depends(require_roles("super_admin","admin"))):
    await db.contact_lists.delete_one(cflt(user, {"id": list_id}))
    return {"ok": True}

@api.patch("/lists/{list_id}")
async def update_list(list_id: str, body: ListIn, user: dict = Depends(require_roles("super_admin","admin"))):
    await db.contact_lists.update_one(cflt(user, {"id": list_id}), {"$set": body.model_dump()})
    return await db.contact_lists.find_one(cflt(user, {"id": list_id}), {"_id": 0})

@api.get("/export/contacts.csv")
async def export_contacts_csv(user: dict = Depends(current_user)):
    from fastapi.responses import Response as FastResponse
    docs = await db.contacts.find(cflt(user), {"_id": 0}).to_list(10000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "phone", "email", "tags", "dnd", "opted_out", "city", "created_at"])
    for c in docs:
        w.writerow([
            c.get("name",""), c.get("phone",""), c.get("email",""),
            ",".join(c.get("tags") or []), c.get("dnd", False), c.get("opted_out", False),
            (c.get("custom_fields") or {}).get("city",""), c.get("created_at",""),
        ])
    return FastResponse(content=buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=contacts.csv"})

# ───────────────────────── Templates ─────────────────────────
@api.get("/templates")
async def list_templates(channel: Optional[Channel] = None, user: dict = Depends(current_user)):
    flt = cflt(user, {"channel": channel} if channel else {})
    return await db.templates.find(flt, {"_id": 0}).sort("created_at", -1).to_list(500)

@api.post("/templates")
async def create_template(body: TemplateIn, user: dict = Depends(current_user)):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["company_id"] = user.get("company_id")
    doc["created_at"] = iso(now_utc())
    await db.templates.insert_one(doc)
    return clean(doc)

@api.patch("/templates/{template_id}")
async def update_template(template_id: str, body: TemplateIn, user: dict = Depends(current_user)):
    await db.templates.update_one(cflt(user, {"id": template_id}), {"$set": body.model_dump()})
    t = await db.templates.find_one(cflt(user, {"id": template_id}), {"_id": 0})
    return t

@api.delete("/templates/{template_id}")
async def delete_template(template_id: str, user: dict = Depends(require_roles("super_admin","admin"))):
    await db.templates.delete_one(cflt(user, {"id": template_id}))
    return {"ok": True}

# ───────────────────────── Campaigns ─────────────────────────
def render_body(tpl_body: str, contact: dict, variables_map: Dict[str, Any]) -> str:
    body = tpl_body
    merged = {"name": contact.get("name",""), "phone": contact.get("phone","")}
    merged.update(variables_map or {})
    for k, v in merged.items():
        body = body.replace("{{" + k + "}}", str(v))
    return body

async def resolve_audience(user: dict, list_ids: List[str], contact_ids: List[str]) -> List[dict]:
    flt: Dict[str, Any] = cflt(user, {"opted_out": {"$ne": True}, "dnd": {"$ne": True}})
    or_clauses = []
    if list_ids:
        or_clauses.append({"list_ids": {"$in": list_ids}})
    if contact_ids:
        or_clauses.append({"id": {"$in": contact_ids}})
    if or_clauses:
        flt["$or"] = or_clauses
    return await db.contacts.find(flt, {"_id": 0}).to_list(10000)

@api.get("/campaigns")
async def list_campaigns(user: dict = Depends(current_user)):
    return await db.campaigns.find(cflt(user), {"_id": 0}).sort("created_at", -1).to_list(500)

@api.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, user: dict = Depends(current_user)):
    c = await db.campaigns.find_one(cflt(user, {"id": campaign_id}), {"_id": 0})
    if not c:
        raise HTTPException(404, "Not found")
    recipients = await db.campaign_recipients.find(cflt(user, {"campaign_id": campaign_id}), {"_id": 0}).limit(500).to_list(500)
    return {"campaign": c, "recipients": recipients}

@api.post("/campaigns")
async def create_campaign(body: CampaignIn, background: BackgroundTasks, user: dict = Depends(current_user)):
    tpl = await db.templates.find_one(cflt(user, {"id": body.template_id}), {"_id": 0})
    if not tpl:
        raise HTTPException(404, "Template not found")
    audience = await resolve_audience(user, body.list_ids, body.contact_ids)
    schedule_dt = None
    if body.schedule_at:
        try:
            schedule_dt = datetime.fromisoformat(body.schedule_at.replace("Z","+00:00"))
        except Exception:
            schedule_dt = None
    status = "scheduled" if schedule_dt and schedule_dt > now_utc() else "running"
    camp = {
        "id": new_id(), "name": body.name, "channel": body.channel,
        "template_id": body.template_id, "list_ids": body.list_ids, "contact_ids": body.contact_ids,
        "schedule_at": body.schedule_at, "status": status,
        "stats": {"queued": len(audience), "sent": 0, "delivered": 0, "failed": 0, "replied": 0},
        "company_id": user.get("company_id"),
        "created_by": user["email"], "created_at": iso(now_utc()),
    }
    await db.campaigns.insert_one(camp)
    recipients = [{"id": new_id(), "campaign_id": camp["id"], "contact_id": c["id"], "status": "queued", "company_id": user.get("company_id"), "created_at": iso(now_utc())} for c in audience]
    if recipients:
        await db.campaign_recipients.insert_many(recipients)
    await audit("campaign_created", "campaign", camp["id"], user, {"name": camp["name"], "channel": camp["channel"], "audience_size": len(audience), "status": status})
    if status == "running":
        background.add_task(run_campaign, camp["id"], body.channel, tpl, audience, body.variables_map, user.get("company_id"))
    return clean(camp)

async def run_campaign(campaign_id: str, channel: Channel, tpl: dict, audience: List[dict], variables_map: Dict[str, Any], company_id: Optional[str] = None):
    adapter = ADAPTERS[channel]
    for c in audience:
        body = render_body(tpl["body"], c, variables_map)
        mid = new_id()
        msg = {
            "id": mid, "channel": channel, "contact_id": c["id"], "direction": "outbound",
            "body": body, "media_url": tpl.get("media_url"),
            "status": "queued", "provider_message_id": None,
            "campaign_id": campaign_id, "company_id": company_id,
            "created_at": iso(now_utc()), "updated_at": iso(now_utc()),
        }
        await db.messages.insert_one(msg)
        try:
            resp = await adapter.send(c["phone"], body, tpl.get("media_url"), company_id=company_id)
            await db.messages.update_one({"id": mid}, {"$set": {"provider_message_id": resp.get("provider_message_id"), "status": "queued"}})
        except Exception as e:
            await emit_event(mid, "failed", reason=str(e))
            continue
        await db.campaign_recipients.update_one({"campaign_id": campaign_id, "contact_id": c["id"]}, {"$set": {"status": "sent"}})
        await db.conversations.update_one(
            {"contact_id": c["id"], "channel": channel},
            {"$set": {"last_message_at": iso(now_utc()), "last_message": body, "company_id": company_id}}, upsert=True,
        )
        if resp.get("mode") == "live":
            await emit_event(mid, "sent", source=getattr(adapter, "provider_key", "live"))
            await db.usage_records.insert_one({
                "id": new_id(), "channel": channel, "message_id": mid, "units": 1,
                "amount": PRICING[channel], "currency": "INR", "company_id": company_id, "created_at": iso(now_utc()),
            })
        else:
            asyncio.create_task(deliver_message(mid, channel))
        await asyncio.sleep(0.05)
    await db.campaigns.update_one({"id": campaign_id}, {"$set": {"status": "completed", "completed_at": iso(now_utc())}})

@api.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, user: dict = Depends(require_roles("super_admin","admin"))):
    await db.campaigns.delete_one(cflt(user, {"id": campaign_id}))
    await db.campaign_recipients.delete_many(cflt(user, {"campaign_id": campaign_id}))
    return {"ok": True}

# ───────────────────────── Messages (single send + logs) ─────────────────────────
@api.post("/messages/send")
async def send_message(body: SendMessageIn, background: BackgroundTasks, user: dict = Depends(current_user)):
    contact = await db.contacts.find_one(cflt(user, {"id": body.contact_id}), {"_id": 0})
    if not contact:
        raise HTTPException(404, "Contact not found")
    if contact.get("opted_out"):
        raise HTTPException(400, "Contact has opted out")
    is_wa_template = (body.channel == "whatsapp" and (body.template_name or "").strip() != "")
    mid = new_id()
    msg = {
        "id": mid, "channel": body.channel, "contact_id": body.contact_id, "direction": "outbound",
        "body": body.body, "media_url": body.media_url, "status": "queued",
        "provider_message_id": None, "campaign_id": None, "company_id": user.get("company_id"),
        "created_at": iso(now_utc()), "updated_at": iso(now_utc()),
    }
    if is_wa_template:
        msg["meta"] = {
            "template_name": body.template_name.strip(),
            "template_language": (body.template_language or "en_US").strip(),
            "template_components": body.template_components or [],
        }
    await db.messages.insert_one(msg)
    # Wallet check + debit (skipped for Super Admin / no-company sends)
    price_paise = _price_paise(body.channel)
    if user.get("company_id") and price_paise > 0:
        ok = await _debit_wallet(user["company_id"], price_paise,
                                 {"message_id": mid, "channel": body.channel, "contact_id": body.contact_id})
        if not ok:
            await db.messages.update_one({"id": mid}, {"$set": {"status": "failed"}})
            await emit_event(mid, "failed", reason="Insufficient wallet balance")
            raise HTTPException(402, "Insufficient wallet balance. Please recharge your wallet to send messages.")
    adapter = ADAPTERS[body.channel]
    try:
        if is_wa_template:
            resp = await adapter.send_template(
                contact["phone"], body.template_name.strip(),
                language_code=(body.template_language or "en_US").strip(),
                components=body.template_components or None,
                company_id=user.get("company_id"),
            )
        else:
            resp = await adapter.send(contact["phone"], body.body, body.media_url, company_id=user.get("company_id"))
    except Exception as e:
        # Refund the wallet — send failed at provider level
        if user.get("company_id") and price_paise > 0:
            await db.wallets.update_one({"company_id": user["company_id"]},
                                        {"$inc": {"balance_paise": price_paise},
                                         "$set": {"updated_at": iso(now_utc())}})
            await db.wallet_transactions.insert_one({
                "id": new_id(), "company_id": user["company_id"], "type": "credit",
                "amount_paise": price_paise, "meta": {"reason": "send_failed_refund", "message_id": mid},
                "created_at": iso(now_utc()),
            })
        await emit_event(mid, "failed", reason=str(e))
        # Return 400 (not 502) so Cloudflare doesn't swallow the JSON body with its own 5xx page.
        raise HTTPException(400, f"Send failed: {e}")
    await db.messages.update_one({"id": mid}, {"$set": {"provider_message_id": resp["provider_message_id"]}})
    await db.conversations.update_one(
        {"contact_id": body.contact_id, "channel": body.channel},
        {"$set": {"last_message_at": iso(now_utc()), "last_message": body.body, "company_id": user.get("company_id")}}, upsert=True,
    )
    if resp.get("mode") == "live":
        await emit_event(mid, "sent", source=getattr(adapter, "provider_key", "live"))
        await db.usage_records.insert_one({
            "id": new_id(), "channel": body.channel, "message_id": mid, "units": 1,
            "amount": PRICING[body.channel], "currency": "INR", "company_id": user.get("company_id"), "created_at": iso(now_utc()),
        })
    else:
        background.add_task(deliver_message, mid, body.channel)
    return {"message_id": mid, "status": "sent" if resp.get("mode") == "live" else "queued", "mode": resp.get("mode")}

@api.get("/messages")
async def list_messages(channel: Optional[Channel] = None, contact_id: Optional[str] = None, status: Optional[str] = None, limit: int = 200, user: dict = Depends(current_user)):
    flt: Dict[str, Any] = cflt(user)
    if channel: flt["channel"] = channel
    if contact_id: flt["contact_id"] = contact_id
    if status: flt["status"] = status
    msgs = await db.messages.find(flt, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return msgs

@api.get("/messages/{message_id}/events")
async def message_events(message_id: str, user: dict = Depends(current_user)):
    msg = await db.messages.find_one(cflt(user, {"id": message_id}), {"_id": 0, "id": 1})
    if not msg:
        raise HTTPException(404, "Message not found")
    return await db.message_events.find({"message_id": message_id}, {"_id": 0}).sort("created_at", 1).to_list(200)

# ───────────────────────── Conversations ─────────────────────────
@api.get("/conversations")
async def list_conversations(user: dict = Depends(current_user)):
    convs = await db.conversations.find(cflt(user), {"_id": 0}).sort("last_message_at", -1).to_list(500)
    # enrich with contact name
    for c in convs:
        contact = await db.contacts.find_one({"id": c["contact_id"]}, {"_id": 0, "name": 1, "phone": 1})
        if contact:
            c["contact_name"] = contact["name"]
            c["contact_phone"] = contact["phone"]
    return convs

@api.get("/contacts/{contact_id}/timeline")
async def contact_timeline(contact_id: str, user: dict = Depends(current_user)):
    msgs = await db.messages.find(cflt(user, {"contact_id": contact_id}), {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    calls = await db.call_logs.find(cflt(user, {"contact_id": contact_id}), {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"messages": msgs, "calls": calls}

# ───────────────────────── Voice Calls ─────────────────────────
@api.post("/calls")
async def initiate_call(body: CallIn, background: BackgroundTasks, user: dict = Depends(current_user)):
    contact = await db.contacts.find_one(cflt(user, {"id": body.contact_id}), {"_id": 0})
    if not contact:
        raise HTTPException(404, "Contact not found")
    cid = new_id()
    call = {
        "id": cid, "contact_id": body.contact_id, "direction": "outbound", "status": "initiated",
        "duration_sec": 0, "recording_url": None,
        "provider_call_id": f"mock_{secrets.token_hex(6)}",
        "notes": body.notes or "",
        "company_id": user.get("company_id"),
        "started_at": iso(now_utc()), "ended_at": None,
        "created_at": iso(now_utc()),
    }
    await db.call_logs.insert_one(call)
    background.add_task(ADAPTERS["voice"].simulate_lifecycle, cid)
    # usage
    await db.usage_records.insert_one({
        "id": new_id(), "channel": "voice", "message_id": cid, "units": 1, "amount": PRICING["voice"],
        "currency": "INR", "company_id": user.get("company_id"), "created_at": iso(now_utc())
    })
    return {"call_id": cid, "status": "initiated"}

@api.get("/calls")
async def list_calls(user: dict = Depends(current_user)):
    return await db.call_logs.find(cflt(user), {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)

# ───────────────────────── Providers ─────────────────────────
@api.get("/providers")
async def list_providers(_: dict = Depends(platform_only("super_admin","admin"))):
    return await db.provider_accounts.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)

@api.post("/providers")
async def create_provider(body: ProviderIn, _: dict = Depends(platform_only("super_admin","admin"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = iso(now_utc())
    await db.provider_accounts.insert_one(doc)
    return clean(doc)

@api.patch("/providers/{provider_id}")
async def update_provider(provider_id: str, body: ProviderIn, _: dict = Depends(platform_only("super_admin","admin"))):
    await db.provider_accounts.update_one({"id": provider_id}, {"$set": body.model_dump()})
    p = await db.provider_accounts.find_one({"id": provider_id}, {"_id": 0})
    return p

@api.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str, _: dict = Depends(platform_only("super_admin"))):
    await db.provider_accounts.delete_one({"id": provider_id})
    return {"ok": True}

class ProviderCredentialsIn(BaseModel):
    credentials: Dict[str, Any]
    mock: Optional[bool] = None

# Sensitive credential field names that get masked when read back
SENSITIVE_KEYS = ("key", "secret", "token", "password", "sid", "auth")

def mask_credentials(cred: Dict[str, Any]) -> Dict[str, Any]:
    masked = {}
    for k, v in (cred or {}).items():
        if isinstance(v, str) and any(s in k.lower() for s in SENSITIVE_KEYS) and len(v) > 4:
            masked[k] = "•" * max(0, len(v) - 4) + v[-4:]
        else:
            masked[k] = v
    return masked

@api.get("/providers/{provider_id}/credentials")
async def get_provider_credentials(provider_id: str, _: dict = Depends(platform_only("super_admin","admin"))):
    p = await db.provider_accounts.find_one({"id": provider_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Not found")
    return {
        "id": p["id"], "name": p["name"], "provider_key": p["provider_key"], "channel": p["channel"],
        "mock": p.get("mock", True),
        "credentials": mask_credentials(p.get("credentials") or {}),
        "credentials_set": bool(p.get("credentials")),
    }

@api.put("/providers/{provider_id}/credentials")
async def set_provider_credentials(provider_id: str, body: ProviderCredentialsIn, user: dict = Depends(platform_only("super_admin"))):
    p = await db.provider_accounts.find_one({"id": provider_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Not found")
    existing = p.get("credentials") or {}
    merged = dict(existing)
    masked_view = mask_credentials(existing)
    for k, v in (body.credentials or {}).items():
        if isinstance(v, str) and v == masked_view.get(k):
            continue
        merged[k] = v
    upd = {"credentials": merged}
    if body.mock is not None:
        upd["mock"] = body.mock
    await db.provider_accounts.update_one({"id": provider_id}, {"$set": upd})
    await audit("provider_credentials_updated", "provider", provider_id, user,
                {"keys_set": sorted(list(merged.keys())), "mock": upd.get("mock")})
    return {"ok": True}

@api.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str, _: dict = Depends(platform_only("super_admin","admin"))):
    p = await db.provider_accounts.find_one({"id": provider_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Not found")
    if p["provider_key"] == "meta_whatsapp":
        creds_resolved = await meta_wa_credentials()
        if not creds_resolved:
            return {"ok": False, "mode": "mock",
                    "message": "No Meta credentials found. Add access_token + phone_number_id in the vault (turn Mock OFF) or set WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID in backend .env."}
        result = await meta_wa.health_check(creds_resolved)
        return {"ok": result["ok"], "mode": "live", "latency_ms": random.randint(80, 320), "message": result["message"]}
    # In mock mode we always succeed; in live mode we would attempt a real handshake.
    if p.get("mock", True):
        return {"ok": True, "mode": "mock", "latency_ms": random.randint(40, 180),
                "message": "Mock adapter handshake successful."}
    creds = p.get("credentials") or {}
    if not creds:
        return {"ok": False, "mode": "live", "message": "No credentials configured. Add API keys first."}
    # Real handshake stub — in production each adapter would implement a real ping/verify.
    return {"ok": True, "mode": "live", "latency_ms": random.randint(80, 320),
            "message": f"{p['provider_key']} credentials present. Replace adapter stub to verify against the live API."}

# ───────────────────────── Webhooks ─────────────────────────
@api.post("/webhooks/incoming/{channel}")
async def webhook_incoming(channel: Channel, body: Dict[str, Any]):
    """Idempotent inbound webhook. Real providers post here; signature placeholder."""
    evt = {
        "id": new_id(), "channel": channel,
        "event_type": body.get("event_type") or body.get("status") or "received",
        "payload": body,
        "signature_valid": True,  # placeholder for signature verification
        "processed": True,
        "created_at": iso(now_utc()),
    }
    await db.webhook_events.insert_one(evt)
    # If payload contains message_id, append event
    if body.get("message_id"):
        await emit_event(body["message_id"], body.get("event_type", "delivered"), **body)
    return {"ok": True, "id": evt["id"]}

@api.get("/webhooks/events")
async def list_webhook_events(limit: int = 100, _: dict = Depends(platform_only("super_admin","admin"))):
    return await db.webhook_events.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)

# ─────────── Airtel IQ webhook endpoints (DLR / inbound / voice status) ─────
from fastapi import Request as _FRequest
try:
    from adapters.airtel_iq import (
        verify_signature as _aiq_verify,
        AIRTEL_SMS_STATUS_MAP as _AIQ_SMS_MAP,
        AIRTEL_VOICE_STATUS_MAP as _AIQ_VOICE_MAP,
    )
except Exception:
    _aiq_verify = None
    _AIQ_SMS_MAP = {}
    _AIQ_VOICE_MAP = {}

def _aiq_signature_ok(req: _FRequest, raw: bytes) -> bool:
    """Verify Airtel-provided HMAC signature; in demo (mock) mode accept all."""
    if not AIRTEL_IQ_CFG or not AIRTEL_IQ_CFG.live or not AIRTEL_IQ_CFG.webhook_secret:
        return True
    sig = req.headers.get("X-Airtel-Signature") or req.headers.get("x-airtel-signature") or ""
    return bool(_aiq_verify and _aiq_verify(AIRTEL_IQ_CFG.webhook_secret, raw, sig))

@api.post("/webhooks/airtel/sms/dlr")
async def airtel_sms_dlr(request: _FRequest):
    """Airtel IQ SMS Delivery Report — updates message status."""
    raw = await request.body()
    sig_ok = _aiq_signature_ok(request, raw)
    payload = await request.json() if raw else {}
    ev = {
        "id": new_id(), "channel": "sms",
        "event_type": (payload.get("status") or "delivered").lower(),
        "payload": payload, "signature_valid": sig_ok, "processed": sig_ok,
        "created_at": iso(now_utc()),
    }
    await db.webhook_events.insert_one(ev)
    if not sig_ok:
        raise HTTPException(401, "Invalid signature")
    airtel_id = payload.get("messageId") or payload.get("message_id")
    status_raw = (payload.get("status") or "").upper()
    internal = _AIQ_SMS_MAP.get(status_raw, "sent")  # unknown → 'sent' (safe intermediate), not 'delivered'
    if airtel_id:
        msg = await db.messages.find_one({"provider_message_id": str(airtel_id)}, {"_id": 0})
        if msg:
            await emit_event(msg["id"], internal, source="airtel_iq", raw_status=status_raw,
                             description=payload.get("statusDescription"))
    return {"ok": True}

@api.post("/webhooks/airtel/whatsapp/inbound")
async def airtel_whatsapp_inbound(request: _FRequest):
    """Airtel IQ WhatsApp inbound message OR status update."""
    raw = await request.body()
    sig_ok = _aiq_signature_ok(request, raw)
    payload = await request.json() if raw else {}
    await db.webhook_events.insert_one({
        "id": new_id(), "channel": "whatsapp",
        "event_type": payload.get("event") or payload.get("type") or "received",
        "payload": payload, "signature_valid": sig_ok, "processed": sig_ok,
        "created_at": iso(now_utc()),
    })
    if not sig_ok:
        raise HTTPException(401, "Invalid signature")
    # Case 1: outbound status update
    airtel_id = payload.get("messageId") or payload.get("wa_message_id")
    status_raw = (payload.get("status") or "").upper()
    if airtel_id and status_raw:
        msg = await db.messages.find_one({"provider_message_id": str(airtel_id)}, {"_id": 0})
        if msg:
            await emit_event(msg["id"], _AIQ_SMS_MAP.get(status_raw, "sent"),
                             source="airtel_iq_whatsapp", raw_status=status_raw)
            return {"ok": True}
    # Case 2: inbound customer message
    frm = payload.get("from") or payload.get("mobileNumber")
    body_txt = (payload.get("text") or {}).get("body") if isinstance(payload.get("text"), dict) else payload.get("body")
    if frm and body_txt:
        contact = await db.contacts.find_one({"phone": frm}, {"_id": 0})
        cid = contact["id"] if contact else None
        if not cid:
            cid = new_id()
            await db.contacts.insert_one({
                "id": cid, "name": frm, "phone": frm, "email": None, "tags": ["wa-inbound"],
                "opted_out": False, "created_at": iso(now_utc()),
            })
        inbound = {
            "id": new_id(), "channel": "whatsapp", "contact_id": cid, "direction": "inbound",
            "body": body_txt, "status": "received",
            "provider_message_id": f"aq_in_{secrets.token_hex(6)}",
            "campaign_id": None,
            "created_at": iso(now_utc()), "updated_at": iso(now_utc()),
        }
        await db.messages.insert_one(inbound)
        await db.conversations.update_one(
            {"contact_id": cid, "channel": "whatsapp"},
            {"$set": {"last_message_at": iso(now_utc()), "last_message": body_txt, "unread": True}},
            upsert=True,
        )
    return {"ok": True}

@api.post("/webhooks/airtel/voice/status")
async def airtel_voice_status(request: _FRequest):
    """Airtel IQ Voice call status update."""
    raw = await request.body()
    sig_ok = _aiq_signature_ok(request, raw)
    payload = await request.json() if raw else {}
    await db.webhook_events.insert_one({
        "id": new_id(), "channel": "voice",
        "event_type": (payload.get("status") or "completed").lower(),
        "payload": payload, "signature_valid": sig_ok, "processed": sig_ok,
        "created_at": iso(now_utc()),
    })
    if not sig_ok:
        raise HTTPException(401, "Invalid signature")
    airtel_call_id = payload.get("callId") or payload.get("call_id")
    status_raw = (payload.get("status") or "").upper()
    internal = _AIQ_VOICE_MAP.get(status_raw, "completed")
    if airtel_call_id:
        call = await db.call_logs.find_one({"provider_call_id": str(airtel_call_id)}, {"_id": 0})
        if call:
            upd: Dict[str, Any] = {"status": internal, "ended_at": iso(now_utc())}
            if payload.get("duration"):
                try: upd["duration_sec"] = int(payload["duration"])
                except Exception: pass
            if payload.get("recordingUrl"):
                upd["recording_url"] = payload["recordingUrl"]
            await db.call_logs.update_one({"id": call["id"]}, {"$set": upd})
    return {"ok": True}


# ─────────── Meta WhatsApp Cloud API — webhooks + direct send ───────────
from fastapi.responses import PlainTextResponse

@api.get("/webhook/whatsapp")
async def meta_whatsapp_verify(request: _FRequest):
    """Meta webhook verification handshake (hub.challenge)."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    expected = (os.environ.get("WHATSAPP_VERIFY_TOKEN") or "").strip()
    if mode == "subscribe" and expected and token == expected and challenge:
        return PlainTextResponse(content=challenge, status_code=200)
    raise HTTPException(403, "Webhook verification failed")

async def _meta_handle_status(st: Dict[str, Any]):
    pid = st.get("id")
    if not pid:
        return
    raw_status = (st.get("status") or "").lower()
    internal = meta_wa.META_STATUS_MAP.get(raw_status, "sent")
    msg = await db.messages.find_one({"provider_message_id": str(pid)}, {"_id": 0})
    if msg:
        extra: Dict[str, Any] = {"source": "meta_whatsapp", "raw_status": raw_status}
        if st.get("errors"):
            extra["errors"] = st["errors"]
        await emit_event(msg["id"], internal, **extra)

async def _meta_handle_inbound(m: Dict[str, Any], contacts_info: List[dict], company_id: Optional[str] = None):
    pid = m.get("id")
    if pid and await db.messages.find_one({"provider_message_id": str(pid)}):
        return  # already processed (Meta retries webhooks)
    frm = m.get("from") or ""
    phone = frm if frm.startswith("+") else f"+{frm}"
    msg_type = m.get("type")
    if msg_type == "text":
        body_txt = (m.get("text") or {}).get("body") or ""
    elif msg_type == "button":
        body_txt = (m.get("button") or {}).get("text") or ""
    elif msg_type == "interactive":
        inter = m.get("interactive") or {}
        body_txt = ((inter.get("button_reply") or inter.get("list_reply") or {}).get("title")) or "[interactive reply]"
    else:
        body_txt = f"[{msg_type} message]"
    profile_name = ""
    for c in contacts_info:
        if c.get("wa_id") == frm:
            profile_name = (c.get("profile") or {}).get("name") or ""
    # If tenant webhook supplied company_id, prefer contacts inside that company.
    contact_query: Dict[str, Any] = {"phone": {"$in": [phone, frm]}}
    if company_id:
        contact_query["company_id"] = company_id
    candidates = await db.contacts.find(contact_query, {"_id": 0}).to_list(20)
    contact = None
    if len(candidates) == 1:
        contact = candidates[0]
    elif candidates:
        conv = await db.conversations.find(
            {"contact_id": {"$in": [c["id"] for c in candidates]}, "channel": "whatsapp"},
            {"_id": 0, "contact_id": 1},
        ).sort("last_message_at", -1).to_list(1)
        match_id = conv[0]["contact_id"] if conv else candidates[0]["id"]
        contact = next((c for c in candidates if c["id"] == match_id), candidates[0])
    if contact:
        cid = contact["id"]
        resolved_company_id = contact.get("company_id") or company_id
    else:
        cid = new_id()
        resolved_company_id = company_id
        await db.contacts.insert_one({
            "id": cid, "name": profile_name or phone, "phone": phone, "email": None,
            "tags": ["wa-inbound"], "list_ids": [], "dnd": False, "opted_out": False,
            "notes": "", "custom_fields": {}, "company_id": resolved_company_id, "created_at": iso(now_utc()),
        })
    inbound = {
        "id": new_id(), "channel": "whatsapp", "contact_id": cid, "direction": "inbound",
        "body": body_txt, "status": "received",
        "provider_message_id": str(pid) if pid else f"meta_in_{secrets.token_hex(6)}",
        "campaign_id": None, "company_id": resolved_company_id,
        "created_at": iso(now_utc()), "updated_at": iso(now_utc()),
    }
    await db.messages.insert_one(inbound)
    await db.message_events.insert_one({
        "id": new_id(), "message_id": inbound["id"], "type": "received",
        "payload": {"body": body_txt, "source": "meta_whatsapp"}, "created_at": iso(now_utc()),
    })
    await db.conversations.update_one(
        {"contact_id": cid, "channel": "whatsapp"},
        {"$set": {"last_message_at": iso(now_utc()), "last_message": body_txt, "unread": True, "company_id": resolved_company_id}},
        upsert=True,
    )
    if body_txt.strip().upper() == "STOP":
        await db.contacts.update_one({"id": cid}, {"$set": {"opted_out": True}})

@api.post("/webhook/whatsapp")
async def meta_whatsapp_webhook(request: _FRequest):
    """Receives Meta Cloud API events: inbound messages + delivery statuses."""
    raw = await request.body()
    app_secret = (os.environ.get("WHATSAPP_APP_SECRET") or "").strip()
    sig_ok = meta_wa.verify_meta_signature(app_secret, raw, request.headers.get("X-Hub-Signature-256") or "")
    payload = await request.json() if raw else {}
    await db.webhook_events.insert_one({
        "id": new_id(), "channel": "whatsapp", "provider": "meta_whatsapp",
        "event_type": "meta_webhook", "payload": payload,
        "signature_valid": sig_ok, "processed": sig_ok, "created_at": iso(now_utc()),
    })
    if not sig_ok:
        log.warning("Meta WA webhook: invalid X-Hub-Signature-256, rejecting")
        raise HTTPException(401, "Invalid signature")
    if payload.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}
    n_status, n_inbound = 0, 0
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            if change.get("field") != "messages":
                continue
            value = change.get("value", {}) or {}
            for st in value.get("statuses", []) or []:
                await _meta_handle_status(st)
                n_status += 1
            for m in value.get("messages", []) or []:
                await _meta_handle_inbound(m, value.get("contacts", []) or [])
                n_inbound += 1
    log.info("Meta WA webhook processed: %s status update(s), %s inbound message(s)", n_status, n_inbound)
    return {"status": "received"}

class WhatsAppSendIn(BaseModel):
    to: str
    message: str = ""
    media_url: Optional[str] = None
    template_name: Optional[str] = None
    template_language: Optional[str] = "en_US"
    template_components: Optional[List[Dict[str, Any]]] = None

@api.post("/whatsapp/send-message")
async def whatsapp_send_message(body: WhatsAppSendIn, background: BackgroundTasks, user: dict = Depends(current_user)):
    phone = body.to.strip()
    if not phone.startswith("+"):
        phone = f"+{phone}"
    contact = await db.contacts.find_one(cflt(user, {"phone": {"$in": [phone, phone.lstrip('+')]}}), {"_id": 0})
    if contact and contact.get("opted_out"):
        raise HTTPException(400, "Contact has opted out")
    if contact:
        cid = contact["id"]
    else:
        cid = new_id()
        await db.contacts.insert_one({
            "id": cid, "name": phone, "phone": phone, "email": None, "tags": ["wa-direct"],
            "list_ids": [], "dnd": False, "opted_out": False, "notes": "", "custom_fields": {},
            "company_id": user.get("company_id"), "created_at": iso(now_utc()),
        })
    is_template = (body.template_name or "").strip() != ""
    mid = new_id()
    msg_doc: Dict[str, Any] = {
        "id": mid, "channel": "whatsapp", "contact_id": cid, "direction": "outbound",
        "body": body.message, "media_url": body.media_url, "status": "queued",
        "provider_message_id": None, "campaign_id": None, "company_id": user.get("company_id"),
        "created_at": iso(now_utc()), "updated_at": iso(now_utc()),
    }
    if is_template:
        msg_doc["meta"] = {
            "template_name": body.template_name.strip(),
            "template_language": (body.template_language or "en_US").strip(),
            "template_components": body.template_components or [],
        }
    await db.messages.insert_one(msg_doc)
    # Wallet check + debit
    price_paise = _price_paise("whatsapp")
    if user.get("company_id") and price_paise > 0:
        ok = await _debit_wallet(user["company_id"], price_paise,
                                 {"message_id": mid, "channel": "whatsapp", "to": phone})
        if not ok:
            await db.messages.update_one({"id": mid}, {"$set": {"status": "failed"}})
            await emit_event(mid, "failed", reason="Insufficient wallet balance", source="wallet")
            raise HTTPException(402, "Insufficient wallet balance. Please recharge your wallet to send messages.")
    try:
        if is_template:
            resp = await ADAPTERS["whatsapp"].send_template(
                phone, body.template_name.strip(),
                language_code=(body.template_language or "en_US").strip(),
                components=body.template_components or None,
                company_id=user.get("company_id"),
            )
        else:
            resp = await ADAPTERS["whatsapp"].send(phone, body.message, body.media_url, company_id=user.get("company_id"))
    except Exception as e:
        # Refund the wallet on provider failure
        if user.get("company_id") and price_paise > 0:
            await db.wallets.update_one({"company_id": user["company_id"]},
                                        {"$inc": {"balance_paise": price_paise},
                                         "$set": {"updated_at": iso(now_utc())}})
            await db.wallet_transactions.insert_one({
                "id": new_id(), "company_id": user["company_id"], "type": "credit",
                "amount_paise": price_paise, "meta": {"reason": "send_failed_refund", "message_id": mid},
                "created_at": iso(now_utc()),
            })
        await emit_event(mid, "failed", reason=str(e), source="meta_whatsapp")
        # Return 400 (not 502) so Cloudflare passes the JSON error body through to the UI.
        raise HTTPException(400, f"WhatsApp send failed: {e}")
    await db.messages.update_one({"id": mid}, {"$set": {"provider_message_id": resp["provider_message_id"]}})
    await db.conversations.update_one(
        {"contact_id": cid, "channel": "whatsapp"},
        {"$set": {"last_message_at": iso(now_utc()), "last_message": body.message, "company_id": user.get("company_id")}}, upsert=True,
    )
    if resp.get("mode") == "live":
        await emit_event(mid, "sent", source="meta_whatsapp")
        await db.usage_records.insert_one({
            "id": new_id(), "channel": "whatsapp", "message_id": mid, "units": 1,
            "amount": PRICING["whatsapp"], "currency": "INR", "company_id": user.get("company_id"), "created_at": iso(now_utc()),
        })
    else:
        background.add_task(deliver_message, mid, "whatsapp")
    return {"message_id": mid, "provider_message_id": resp["provider_message_id"],
            "mode": resp.get("mode"), "status": "sent" if resp.get("mode") == "live" else "queued"}

@api.get("/whatsapp/setup")
async def whatsapp_setup(_: dict = Depends(platform_only("super_admin", "admin"))):
    """Setup info for configuring the Callback URL + Verify Token in the Meta dashboard."""
    creds = await meta_wa_credentials()
    return {
        "webhook_path": "/api/webhook/whatsapp",
        "verify_token": (os.environ.get("WHATSAPP_VERIFY_TOKEN") or "").strip(),
        "graph_version": os.environ.get("GRAPH_API_VERSION") or "v22.0",
        "env_configured": bool(meta_wa.env_config()),
        "live": bool(creds),
        "phone_number_id": (creds or {}).get("phone_number_id", ""),
        "signature_check_enabled": bool((os.environ.get("WHATSAPP_APP_SECRET") or "").strip()),
    }


# ─────────── Per-tenant WhatsApp configuration (Company Admin) ───────────
def _mask_wa(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return a safe view of a company WA config (masks token / app_secret)."""
    out: Dict[str, Any] = {
        "company_id": cfg.get("company_id"),
        "phone_number_id": cfg.get("phone_number_id") or "",
        "waba_id": cfg.get("waba_id") or "",
        "graph_version": cfg.get("graph_version") or "v22.0",
        "verify_token": cfg.get("verify_token") or "",
        "is_active": cfg.get("is_active", True),
        "mock": cfg.get("mock", True),
        "access_token_set": bool(cfg.get("access_token")),
        "app_secret_set": bool(cfg.get("app_secret")),
        "updated_at": cfg.get("updated_at"),
        "updated_by": cfg.get("updated_by"),
    }
    tok = cfg.get("access_token") or ""
    out["access_token_preview"] = ("•" * max(0, len(tok) - 4) + tok[-4:]) if tok else ""
    sec = cfg.get("app_secret") or ""
    out["app_secret_preview"] = ("•" * max(0, len(sec) - 4) + sec[-4:]) if sec else ""
    return out


class WhatsAppConfigIn(BaseModel):
    access_token: Optional[str] = None
    phone_number_id: Optional[str] = None
    waba_id: Optional[str] = None
    app_secret: Optional[str] = None
    graph_version: Optional[str] = None
    is_active: Optional[bool] = None
    mock: Optional[bool] = None


@api.get("/whatsapp/config")
async def get_wa_config(user: dict = Depends(current_user)):
    """Company Admin/Agent: view own tenant WhatsApp config (masked).
    Super Admin (no company_id): returns platform env/vault info + a summary of tenants."""
    if user.get("company_id"):
        cfg = await db.company_whatsapp_configs.find_one({"company_id": user["company_id"]}, {"_id": 0})
        if not cfg:
            return {
                "configured": False, "company_id": user["company_id"],
                "webhook_path": None, "verify_token": None,
                "hint": "Call PUT /api/whatsapp/config to set your Meta Cloud API credentials.",
            }
        base_url = (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")
        webhook_path = f"/api/webhook/whatsapp/{user['company_id']}"
        return {
            "configured": True,
            **_mask_wa(cfg),
            "webhook_path": webhook_path,
            "webhook_url": (base_url + webhook_path) if base_url else webhook_path,
            "graph_api_version_env": os.environ.get("GRAPH_API_VERSION") or "v22.0",
        }
    # Super Admin
    tenants = await db.company_whatsapp_configs.find({}, {"_id": 0}).to_list(500)
    return {
        "configured": bool(meta_wa.env_config()),
        "platform_env_configured": bool(meta_wa.env_config()),
        "verify_token": (os.environ.get("WHATSAPP_VERIFY_TOKEN") or "").strip(),
        "webhook_path": "/api/webhook/whatsapp",
        "tenant_count": len(tenants),
        "tenants": [_mask_wa(t) for t in tenants],
    }


@api.put("/whatsapp/config")
async def put_wa_config(body: WhatsAppConfigIn, user: dict = Depends(require_roles("super_admin","admin"))):
    """Company Admin only: create/update the tenant's WhatsApp credentials.
    A per-tenant `verify_token` is auto-generated on first create."""
    if not user.get("company_id"):
        raise HTTPException(400, "Super Admin does not have a per-tenant WhatsApp config. Use the global Provider Vault instead.")
    existing = await db.company_whatsapp_configs.find_one({"company_id": user["company_id"]}, {"_id": 0})
    now = iso(now_utc())
    upd: Dict[str, Any] = {"updated_at": now, "updated_by": user.get("email")}
    for k in ("access_token", "phone_number_id", "waba_id", "app_secret", "graph_version"):
        v = getattr(body, k, None)
        if v is None:
            continue
        if isinstance(v, str):
            v = v.strip()
            # Empty string = "leave unchanged" for secrets/identifiers
            if not v:
                continue
        upd[k] = v
    if body.is_active is not None: upd["is_active"] = bool(body.is_active)
    if body.mock is not None: upd["mock"] = bool(body.mock)
    if not existing:
        upd.update({
            "id": new_id(), "company_id": user["company_id"],
            "verify_token": f"tzs_{secrets.token_urlsafe(24)}",
            "is_active": upd.get("is_active", True),
            "mock": upd.get("mock", False),
            "created_at": now, "created_by": user.get("email"),
        })
        await db.company_whatsapp_configs.insert_one(upd)
        await audit("wa_config_created", "wa_config", user["company_id"], user,
                    {"phone_number_id": upd.get("phone_number_id", ""), "mock": upd.get("mock")})
    else:
        await db.company_whatsapp_configs.update_one(
            {"company_id": user["company_id"]}, {"$set": upd})
        await audit("wa_config_updated", "wa_config", user["company_id"], user,
                    {"fields": sorted([k for k in upd.keys() if k not in ("updated_at","updated_by")])})
    cfg = await db.company_whatsapp_configs.find_one({"company_id": user["company_id"]}, {"_id": 0})
    base_url = (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")
    webhook_path = f"/api/webhook/whatsapp/{user['company_id']}"
    return {
        "ok": True, "configured": True,
        **_mask_wa(cfg),
        "webhook_path": webhook_path,
        "webhook_url": (base_url + webhook_path) if base_url else webhook_path,
    }


@api.delete("/whatsapp/config")
async def delete_wa_config(user: dict = Depends(require_roles("super_admin","admin"))):
    if not user.get("company_id"):
        raise HTTPException(400, "Super Admin does not have a per-tenant WhatsApp config.")
    res = await db.company_whatsapp_configs.delete_one({"company_id": user["company_id"]})
    await audit("wa_config_deleted", "wa_config", user["company_id"], user)
    return {"ok": True, "deleted": res.deleted_count}


@api.post("/whatsapp/config/test")
async def test_wa_config(user: dict = Depends(require_roles("super_admin","admin"))):
    """Live Meta Graph handshake using the tenant's own credentials."""
    if not user.get("company_id"):
        raise HTTPException(400, "Use POST /api/providers/{id}/test for the platform-level provider.")
    creds = await meta_wa_credentials(user["company_id"])
    if not creds:
        return {"ok": False, "mode": "mock",
                "message": "No live credentials configured for this tenant. Add access_token + phone_number_id and set mock=false."}
    result = await meta_wa.health_check(creds)
    return {"ok": result["ok"], "mode": "live", "message": result["message"], "phone_number_id": creds.get("phone_number_id")}


def _template_body_preview(components: List[Dict[str, Any]]) -> str:
    """Extract the BODY text from a Meta template's components array (for UI preview)."""
    for c in components or []:
        if (c.get("type") or "").upper() == "BODY":
            return (c.get("text") or "").strip()
    return ""


def _template_variable_count(components: List[Dict[str, Any]]) -> int:
    """Count {{1}} {{2}} etc. placeholders in the BODY text."""
    import re
    body = _template_body_preview(components)
    return len(set(re.findall(r"\{\{(\d+)\}\}", body)))


@api.get("/whatsapp/templates")
async def list_wa_templates(status: Optional[str] = None, limit: int = 100,
                            user: dict = Depends(current_user)):
    """Fetch approved WhatsApp message templates from Meta Graph API.
    Filter by status (APPROVED / PENDING / REJECTED) — default returns all.
    Requires WABA ID configured:
      - Company Admin: must be set on the tenant's own WhatsApp config (per-tenant isolation).
      - Super Admin: falls back to env WHATSAPP_WABA_ID.
    """
    is_tenant_user = bool(user.get("company_id"))
    if is_tenant_user:
        # Strict per-tenant scoping: do NOT inherit env/global creds
        cfg = await db.company_whatsapp_configs.find_one(
            {"company_id": user["company_id"], "is_active": True}, {"_id": 0})
        if not cfg or cfg.get("mock", True) or not cfg.get("access_token") or not cfg.get("phone_number_id"):
            return {"ok": False, "templates": [],
                    "error": "No live WhatsApp credentials configured for this tenant. Save your access_token + phone_number_id in Step 2 (and set Mock mode off)."}
        if not (cfg.get("waba_id") or "").strip():
            return {"ok": False, "templates": [],
                    "error": "WhatsApp Business Account (WABA) ID is not configured. Add it in Step 2 to fetch approved templates."}
        access_token = cfg["access_token"]
        waba_id = cfg["waba_id"].strip()
        graph_version = cfg.get("graph_version") or "v22.0"
    else:
        creds = await meta_wa_credentials(None)  # SA: env/vault only
        if not creds:
            return {"ok": False, "templates": [],
                    "error": "No live WhatsApp credentials configured at platform level."}
        waba_id = (creds.get("waba_id") or "").strip()
        if not waba_id:
            return {"ok": False, "templates": [],
                    "error": "Platform WABA ID (WHATSAPP_WABA_ID) is not configured."}
        access_token = creds["access_token"]
        graph_version = creds.get("graph_version") or "v22.0"
    result = await meta_wa.list_message_templates(
        access_token, waba_id, graph_version=graph_version, limit=limit)
    if not result["ok"]:
        return {"ok": False, "templates": [], "error": result["error"]}
    # Enrich each template with body preview + variable count so the UI can render dropdowns cleanly.
    templates = []
    for t in result["templates"]:
        st = (t.get("status") or "").upper()
        if status and st != status.upper():
            continue
        components = t.get("components") or []
        templates.append({
            "name": t.get("name"),
            "language": t.get("language"),
            "status": st,
            "category": (t.get("category") or "").upper(),
            "quality_score": (t.get("quality_score") or {}).get("score"),
            "rejected_reason": t.get("rejected_reason") if st == "REJECTED" else None,
            "body_preview": _template_body_preview(components),
            "variable_count": _template_variable_count(components),
            "components": components,
        })
    templates.sort(key=lambda t: (0 if t["status"] == "APPROVED" else 1, t["name"] or ""))
    return {"ok": True, "templates": templates, "count": len(templates), "waba_id": waba_id}


# ─────────── WhatsApp Template Builder (create + delete via Meta) ───────────
class WATemplateButton(BaseModel):
    type: str  # URL / PHONE_NUMBER / QUICK_REPLY
    text: str
    url: Optional[str] = None
    phone_number: Optional[str] = None

class WATemplateIn(BaseModel):
    name: str
    category: str  # MARKETING / UTILITY / AUTHENTICATION
    language: str = "en_US"
    header_format: Optional[str] = None  # NONE / TEXT / IMAGE / VIDEO / DOCUMENT
    header_text: Optional[str] = None
    header_example: Optional[str] = None
    body_text: str = Field(min_length=1)
    body_examples: Optional[List[str]] = None
    footer_text: Optional[str] = None
    buttons: Optional[List[WATemplateButton]] = None


async def _resolve_wa_creds_for_template_write(user: dict) -> Dict[str, str]:
    """Get access_token + waba_id for template CREATE/DELETE (strict tenant isolation for CA)."""
    if user.get("company_id"):
        cfg = await db.company_whatsapp_configs.find_one(
            {"company_id": user["company_id"], "is_active": True}, {"_id": 0})
        if not cfg or not cfg.get("access_token") or not cfg.get("phone_number_id"):
            raise HTTPException(400, "Tenant WhatsApp is not configured. Add access_token + phone_number_id in Step 2.")
        if not (cfg.get("waba_id") or "").strip():
            raise HTTPException(400, "WABA ID is not configured for this tenant.")
        return {"access_token": cfg["access_token"], "waba_id": cfg["waba_id"].strip(),
                "graph_version": cfg.get("graph_version") or "v22.0"}
    creds = await meta_wa_credentials(None)
    if not creds or not (creds.get("waba_id") or "").strip():
        raise HTTPException(400, "Platform WABA_ID not configured.")
    return {"access_token": creds["access_token"], "waba_id": creds["waba_id"].strip(),
            "graph_version": creds.get("graph_version") or "v22.0"}


def _build_template_components(body: WATemplateIn) -> List[Dict[str, Any]]:
    """Build the Meta components array from the flat form input."""
    import re
    comps: List[Dict[str, Any]] = []
    # HEADER
    hf = (body.header_format or "").upper()
    if hf == "TEXT" and (body.header_text or "").strip():
        hcomp: Dict[str, Any] = {"type": "HEADER", "format": "TEXT", "text": body.header_text.strip()}
        if body.header_example:
            hcomp["example"] = {"header_text": [body.header_example]}
        comps.append(hcomp)
    elif hf in ("IMAGE", "VIDEO", "DOCUMENT") and body.header_example:
        # header_example is a public sample media URL for these formats
        comps.append({"type": "HEADER", "format": hf,
                      "example": {"header_handle": [body.header_example]}})
    # BODY (required)
    body_comp: Dict[str, Any] = {"type": "BODY", "text": body.body_text.strip()}
    vars_in_body = sorted(set(int(v) for v in re.findall(r"\{\{(\d+)\}\}", body.body_text)))
    if vars_in_body:
        examples = body.body_examples or []
        # Pad examples with placeholder samples
        while len(examples) < len(vars_in_body):
            examples.append(f"sample{len(examples)+1}")
        body_comp["example"] = {"body_text": [examples[: len(vars_in_body)]]}
    comps.append(body_comp)
    # FOOTER
    if (body.footer_text or "").strip():
        comps.append({"type": "FOOTER", "text": body.footer_text.strip()})
    # BUTTONS
    if body.buttons:
        buttons: List[Dict[str, Any]] = []
        for b in body.buttons[:3]:
            btype = b.type.upper()
            if btype == "URL" and b.url:
                buttons.append({"type": "URL", "text": b.text, "url": b.url})
            elif btype == "PHONE_NUMBER" and b.phone_number:
                buttons.append({"type": "PHONE_NUMBER", "text": b.text, "phone_number": b.phone_number})
            elif btype == "QUICK_REPLY":
                buttons.append({"type": "QUICK_REPLY", "text": b.text})
        if buttons:
            comps.append({"type": "BUTTONS", "buttons": buttons})
    return comps


@api.post("/whatsapp/templates")
async def create_wa_template(body: WATemplateIn,
                             user: dict = Depends(require_roles("super_admin", "admin"))):
    """Create a new WhatsApp template and submit it to Meta for approval."""
    creds = await _resolve_wa_creds_for_template_write(user)
    if body.category.upper() not in ("MARKETING", "UTILITY", "AUTHENTICATION"):
        raise HTTPException(400, "category must be MARKETING, UTILITY or AUTHENTICATION")
    components = _build_template_components(body)
    payload = {
        "name": body.name.strip().lower(),
        "category": body.category.upper(),
        "language": body.language.strip() or "en_US",
        "components": components,
    }
    result = await meta_wa.create_message_template(
        creds["access_token"], creds["waba_id"], payload, creds["graph_version"])
    if not result["ok"]:
        raise HTTPException(400, f"Meta rejected template: {result['error']}")
    await audit("wa_template_created", "wa_template", result.get("id") or payload["name"], user,
                {"name": payload["name"], "category": payload["category"], "language": payload["language"]})
    return {"ok": True, "id": result.get("id"), "status": result.get("status", "PENDING"),
            "name": payload["name"], "language": payload["language"]}


@api.delete("/whatsapp/templates/{name}")
async def delete_wa_template(name: str,
                             user: dict = Depends(require_roles("super_admin", "admin"))):
    creds = await _resolve_wa_creds_for_template_write(user)
    result = await meta_wa.delete_message_template(
        creds["access_token"], creds["waba_id"], name.strip(), creds["graph_version"])
    if not result["ok"]:
        raise HTTPException(400, result["error"])
    await audit("wa_template_deleted", "wa_template", name, user)
    return {"ok": True}


# ─────────── Wallet + Billing (per-tenant balance, send-blocking, admin adjust) ───────────
async def _get_or_create_wallet(company_id: str) -> Dict[str, Any]:
    w = await db.wallets.find_one({"company_id": company_id}, {"_id": 0})
    if not w:
        w = {"id": new_id(), "company_id": company_id, "balance_paise": 0, "currency": "INR",
             "low_balance_threshold_paise": 5000,  # ₹50 default
             "created_at": iso(now_utc()), "updated_at": iso(now_utc())}
        await db.wallets.insert_one(w)
    return w


async def _debit_wallet(company_id: Optional[str], amount_paise: int, meta_info: Dict[str, Any]) -> bool:
    """Atomically deduct from wallet. Returns True if debited or SA (no company), False if insufficient."""
    if not company_id:
        return True  # SA / platform sends bypass wallet
    if amount_paise <= 0:
        return True
    res = await db.wallets.find_one_and_update(
        {"company_id": company_id, "balance_paise": {"$gte": amount_paise}},
        {"$inc": {"balance_paise": -amount_paise}, "$set": {"updated_at": iso(now_utc())}},
        return_document=True,
    )
    if not res:
        return False
    await db.wallet_transactions.insert_one({
        "id": new_id(), "company_id": company_id, "type": "debit",
        "amount_paise": amount_paise, "balance_paise_after": res["balance_paise"],
        "meta": meta_info, "created_at": iso(now_utc()),
    })
    return True


def _price_paise(channel: str) -> int:
    """Convert channel price (₹) to paise (int)."""
    p = PRICING.get(channel) or 0.0
    return int(round(p * 100))


class WalletAdjustIn(BaseModel):
    amount_paise: int  # positive = credit, negative = debit
    reason: str
    company_id: Optional[str] = None  # SA targeting a specific company


@api.get("/wallet")
async def get_wallet(user: dict = Depends(current_user)):
    """Company Admin: own tenant balance + last 50 transactions. Super Admin: 400."""
    if not user.get("company_id"):
        raise HTTPException(400, "Super Admin has no wallet. See /api/wallets for the platform view.")
    w = await _get_or_create_wallet(user["company_id"])
    txns = await db.wallet_transactions.find({"company_id": user["company_id"]}, {"_id": 0}
                                              ).sort("created_at", -1).limit(50).to_list(50)
    return {
        "company_id": user["company_id"], "currency": "INR",
        "balance_paise": w["balance_paise"], "balance_inr": w["balance_paise"] / 100.0,
        "low_balance_threshold_paise": w.get("low_balance_threshold_paise", 5000),
        "low_balance": w["balance_paise"] < w.get("low_balance_threshold_paise", 5000),
        "transactions": txns,
        "pricing_paise": {ch: _price_paise(ch) for ch in ("sms", "whatsapp", "rcs", "voice", "email")},
    }


@api.get("/wallets")
async def list_all_wallets(_: dict = Depends(require_roles("super_admin"))):
    """Super Admin: overview of all tenant wallets."""
    ws = await db.wallets.find({}, {"_id": 0}).sort("balance_paise", -1).to_list(500)
    for w in ws:
        c = await db.companies.find_one({"id": w["company_id"]}, {"_id": 0, "name": 1, "admin_email": 1})
        w["company_name"] = (c or {}).get("name", "—")
        w["admin_email"] = (c or {}).get("admin_email", "")
    return ws


@api.post("/wallet/adjust")
async def adjust_wallet(body: WalletAdjustIn, user: dict = Depends(require_roles("super_admin"))):
    """Super Admin: manually credit/debit any tenant's wallet."""
    target_company_id = body.company_id
    if not target_company_id:
        raise HTTPException(400, "company_id is required")
    await _get_or_create_wallet(target_company_id)
    res = await db.wallets.find_one_and_update(
        {"company_id": target_company_id},
        {"$inc": {"balance_paise": body.amount_paise},
         "$set": {"updated_at": iso(now_utc())}},
        return_document=True,
    )
    if res["balance_paise"] < 0:
        # Roll back — we don't want negative balances
        await db.wallets.update_one({"company_id": target_company_id},
                                    {"$inc": {"balance_paise": -body.amount_paise}})
        raise HTTPException(400, "This adjustment would make the balance negative")
    await db.wallet_transactions.insert_one({
        "id": new_id(), "company_id": target_company_id,
        "type": "credit" if body.amount_paise > 0 else "debit",
        "amount_paise": abs(body.amount_paise),
        "balance_paise_after": res["balance_paise"],
        "meta": {"reason": body.reason, "manual": True, "by": user.get("email")},
        "created_at": iso(now_utc()),
    })
    await audit("wallet_adjusted", "wallet", target_company_id, user,
                {"amount_paise": body.amount_paise, "reason": body.reason})
    return {"ok": True, "balance_paise": res["balance_paise"]}


# ─────────── Razorpay recharge (plumbing; activates when SA sets keys) ───────────
def _razorpay_client():
    """Return a razorpay.Client if keys are configured, else None."""
    key_id = (os.environ.get("RAZORPAY_KEY_ID") or "").strip()
    key_secret = (os.environ.get("RAZORPAY_KEY_SECRET") or "").strip()
    if not (key_id and key_secret):
        return None
    try:
        import razorpay
        return razorpay.Client(auth=(key_id, key_secret))
    except Exception as e:
        log.error(f"Razorpay init failed: {e}")
        return None


class RechargeOrderIn(BaseModel):
    amount_paise: int  # minimum 10000 (₹100)


class RechargeVerifyIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@api.get("/wallet/recharge/config")
async def recharge_config(user: dict = Depends(current_user)):
    """Tenant checks if Razorpay is available before rendering the pay button."""
    key_id = (os.environ.get("RAZORPAY_KEY_ID") or "").strip()
    return {"configured": bool(key_id), "key_id": key_id if key_id else None,
            "currency": "INR", "min_amount_paise": 10000}


@api.post("/wallet/recharge/order")
async def create_recharge_order(body: RechargeOrderIn, user: dict = Depends(current_user)):
    if not user.get("company_id"):
        raise HTTPException(400, "Super Admin does not have a wallet.")
    if body.amount_paise < 10000:
        raise HTTPException(400, "Minimum recharge is ₹100 (10000 paise).")
    client = _razorpay_client()
    if not client:
        raise HTTPException(503, "Razorpay is not configured. Please contact your platform admin.")
    try:
        order = client.order.create({
            "amount": body.amount_paise, "currency": "INR",
            "notes": {"company_id": user["company_id"], "purpose": "wallet_recharge",
                      "created_by": user.get("email", "")},
        })
    except Exception as e:
        raise HTTPException(502, f"Razorpay order creation failed: {e}")
    await db.wallet_recharge_orders.insert_one({
        "id": new_id(), "company_id": user["company_id"],
        "razorpay_order_id": order["id"], "amount_paise": body.amount_paise,
        "status": "created", "created_at": iso(now_utc()),
        "created_by": user.get("email"),
    })
    return {"order_id": order["id"], "amount_paise": body.amount_paise, "currency": "INR",
            "key_id": (os.environ.get("RAZORPAY_KEY_ID") or "").strip()}


@api.post("/wallet/recharge/verify")
async def verify_recharge(body: RechargeVerifyIn, user: dict = Depends(current_user)):
    if not user.get("company_id"):
        raise HTTPException(400, "Super Admin does not have a wallet.")
    client = _razorpay_client()
    if not client:
        raise HTTPException(503, "Razorpay is not configured.")
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": body.razorpay_order_id,
            "razorpay_payment_id": body.razorpay_payment_id,
            "razorpay_signature": body.razorpay_signature,
        })
    except Exception as e:
        raise HTTPException(400, f"Signature verification failed: {e}")
    # Atomic CAS: only credit if the order is still in 'created' state (prevents race with webhook).
    order = await db.wallet_recharge_orders.find_one_and_update(
        {"razorpay_order_id": body.razorpay_order_id, "company_id": user["company_id"], "status": "created"},
        {"$set": {"status": "paid", "paid_at": iso(now_utc()),
                  "razorpay_payment_id": body.razorpay_payment_id}},
        return_document=True,
    )
    if not order:
        # Already paid (race) — return current balance idempotently
        existing = await db.wallet_recharge_orders.find_one(
            {"razorpay_order_id": body.razorpay_order_id, "company_id": user["company_id"]}, {"_id": 0})
        if not existing:
            raise HTTPException(404, "Recharge order not found for this tenant.")
        w = await db.wallets.find_one({"company_id": user["company_id"]}, {"_id": 0})
        return {"ok": True, "already_paid": True, "balance_paise": (w or {}).get("balance_paise", 0)}
    await _get_or_create_wallet(user["company_id"])
    res = await db.wallets.find_one_and_update(
        {"company_id": user["company_id"]},
        {"$inc": {"balance_paise": order["amount_paise"]}, "$set": {"updated_at": iso(now_utc())}},
        return_document=True,
    )
    await db.wallet_transactions.insert_one({
        "id": new_id(), "company_id": user["company_id"], "type": "credit",
        "amount_paise": order["amount_paise"],
        "balance_paise_after": res["balance_paise"],
        "meta": {"source": "razorpay", "order_id": body.razorpay_order_id,
                 "payment_id": body.razorpay_payment_id},
        "created_at": iso(now_utc()),
    })
    await audit("wallet_recharged", "wallet", user["company_id"], user,
                {"amount_paise": order["amount_paise"], "razorpay_order_id": body.razorpay_order_id})
    return {"ok": True, "balance_paise": res["balance_paise"]}


# ─────────── Per-tenant Meta WhatsApp webhook ───────────
@api.get("/webhook/whatsapp/{company_id}")
async def meta_whatsapp_verify_tenant(company_id: str, request: _FRequest):
    """Meta webhook verification handshake using the tenant's own verify_token."""
    cfg = await db.company_whatsapp_configs.find_one({"company_id": company_id}, {"_id": 0})
    if not cfg:
        raise HTTPException(404, "Tenant WhatsApp config not found")
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    expected = (cfg.get("verify_token") or "").strip()
    if mode == "subscribe" and expected and token == expected and challenge:
        return PlainTextResponse(content=challenge, status_code=200)
    raise HTTPException(403, "Webhook verification failed")


@api.post("/webhook/whatsapp/{company_id}")
async def meta_whatsapp_webhook_tenant(company_id: str, request: _FRequest):
    """Receives Meta Cloud API events for a specific tenant."""
    cfg = await db.company_whatsapp_configs.find_one({"company_id": company_id}, {"_id": 0})
    if not cfg:
        raise HTTPException(404, "Tenant WhatsApp config not found")
    raw = await request.body()
    app_secret = (cfg.get("app_secret") or "").strip()
    sig_ok = meta_wa.verify_meta_signature(app_secret, raw, request.headers.get("X-Hub-Signature-256") or "")
    payload = await request.json() if raw else {}
    await db.webhook_events.insert_one({
        "id": new_id(), "channel": "whatsapp", "provider": "meta_whatsapp",
        "event_type": "meta_webhook", "payload": payload,
        "signature_valid": sig_ok, "processed": sig_ok,
        "company_id": company_id,
        "created_at": iso(now_utc()),
    })
    if not sig_ok:
        log.warning("Meta WA tenant webhook (%s): invalid X-Hub-Signature-256, rejecting", company_id)
        raise HTTPException(401, "Invalid signature")
    if payload.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}
    n_status, n_inbound = 0, 0
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            if change.get("field") != "messages":
                continue
            value = change.get("value", {}) or {}
            for st in value.get("statuses", []) or []:
                await _meta_handle_status(st)
                n_status += 1
            for m in value.get("messages", []) or []:
                await _meta_handle_inbound(m, value.get("contacts", []) or [], company_id=company_id)
                n_inbound += 1
    log.info("Meta WA tenant %s webhook: %s status update(s), %s inbound message(s)", company_id, n_status, n_inbound)
    return {"status": "received"}


# ───────────────────────── Usage / Billing ─────────────────────────
@api.get("/usage/summary")
async def usage_summary(user: dict = Depends(current_user)):
    pipeline = [{"$match": cflt(user)}, {"$group": {"_id": "$channel", "units": {"$sum": "$units"}, "amount": {"$sum": "$amount"}}}]
    rows = await db.usage_records.aggregate(pipeline).to_list(100)
    total_amount = sum(r["amount"] for r in rows)
    total_units = sum(r["units"] for r in rows)
    return {
        "by_channel": [{"channel": r["_id"], "units": r["units"], "amount": round(r["amount"], 2)} for r in rows],
        "total_amount": round(total_amount, 2),
        "total_units": total_units,
        "currency": "INR",
    }

@api.get("/usage/records")
async def usage_records(limit: int = 200, user: dict = Depends(current_user)):
    return await db.usage_records.find(cflt(user), {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)

# ───────────────────────── Dashboard / Analytics ─────────────────────────
@api.get("/dashboard/stats")
async def dashboard_stats(user: dict = Depends(current_user)):
    base = cflt(user)
    total_msgs = await db.messages.count_documents(base)
    delivered = await db.messages.count_documents(cflt(user, {"status": "delivered"}))
    failed = await db.messages.count_documents(cflt(user, {"status": "failed"}))
    replied = await db.messages.count_documents(cflt(user, {"direction": "inbound"}))
    active_campaigns = await db.campaigns.count_documents(cflt(user, {"status": {"$in": ["running","scheduled"]}}))
    contacts_count = await db.contacts.count_documents(base)

    # last 7 days bar series by channel
    since = now_utc() - timedelta(days=7)
    pipeline = [
        {"$match": cflt(user, {"created_at": {"$gte": iso(since)}})},
        {"$group": {"_id": {"day": {"$substr": ["$created_at", 0, 10]}, "channel": "$channel"}, "count": {"$sum": 1}}},
    ]
    rows = await db.messages.aggregate(pipeline).to_list(1000)
    series_map: Dict[str, Dict[str, int]] = {}
    for r in rows:
        d = r["_id"]["day"]; ch = r["_id"]["channel"]
        series_map.setdefault(d, {"sms":0,"whatsapp":0,"rcs":0,"voice":0})
        series_map[d][ch] = r["count"]
    series = [{"date": d, **vals} for d, vals in sorted(series_map.items())]

    # channel split (pie)
    pipeline2 = [{"$match": base}, {"$group": {"_id": "$channel", "count": {"$sum": 1}}}]
    by_channel = await db.messages.aggregate(pipeline2).to_list(20)
    channel_split = [{"channel": r["_id"], "count": r["count"]} for r in by_channel]

    # status split for delivery donut
    pipeline3 = [{"$match": base}, {"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    by_status = await db.messages.aggregate(pipeline3).to_list(20)

    return {
        "kpis": {
            "messages_sent": total_msgs,
            "delivered": delivered,
            "failed": failed,
            "replied": replied,
            "active_campaigns": active_campaigns,
            "contacts": contacts_count,
        },
        "series_7d": series,
        "channel_split": channel_split,
        "status_split": [{"status": r["_id"], "count": r["count"]} for r in by_status],
    }

# ───────────────────────── Audit Logs ─────────────────────────
@api.get("/audit-logs")
async def list_audit_logs(limit: int = 200, action: Optional[str] = None,
                          user: dict = Depends(require_roles("super_admin","admin"))):
    flt: Dict[str, Any] = cflt(user)
    if action:
        flt["action"] = action
    return await db.audit_logs.find(flt, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)

# ───────────────────────── Settings (markup config) ─────────────────────────
class MarkupIn(BaseModel):
    sms: float = 0
    whatsapp: float = 0
    rcs: float = 0
    voice: float = 0

@api.get("/settings/markup")
async def get_markup(_: dict = Depends(current_user)):
    row = await db.system_settings.find_one({"key": "markup_pct"}, {"_id": 0})
    return (row or {}).get("value", {"sms": 0, "whatsapp": 0, "rcs": 0, "voice": 0})

@api.put("/settings/markup")
async def set_markup(body: MarkupIn, user: dict = Depends(require_roles("super_admin"))):
    v = body.model_dump()
    await db.system_settings.update_one(
        {"key": "markup_pct"},
        {"$set": {"value": v, "updated_at": iso(now_utc())}},
        upsert=True,
    )
    await audit("markup_updated", "setting", "markup_pct", user, {"value": v})
    return v

# ───────────────────────── Invoices ─────────────────────────
@api.get("/invoices")
async def list_invoices(user: dict = Depends(require_roles("super_admin","admin"))):
    """Return monthly invoice summaries (last 6 months that have usage)."""
    markup_row = await db.system_settings.find_one({"key": "markup_pct"}, {"_id": 0})
    markup = (markup_row or {}).get("value", {}) or {}
    pipeline = [
        {"$match": cflt(user)},
        {"$group": {
            "_id": {"month": {"$substr": ["$created_at", 0, 7]}, "channel": "$channel"},
            "units": {"$sum": "$units"},
            "base": {"$sum": "$amount"},
        }},
        {"$sort": {"_id.month": -1}},
    ]
    rows = await db.usage_records.aggregate(pipeline).to_list(2000)
    by_month: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        m = r["_id"]["month"]; ch = r["_id"]["channel"]
        bm = by_month.setdefault(m, {"month": m, "channels": [], "base_total": 0, "billable_total": 0, "units_total": 0})
        mk = float(markup.get(ch, 0))
        billable = round(r["base"] * (1 + mk / 100.0), 2)
        bm["channels"].append({"channel": ch, "units": r["units"], "base": round(r["base"], 2), "markup_pct": mk, "billable": billable})
        bm["base_total"] = round(bm["base_total"] + r["base"], 2)
        bm["billable_total"] = round(bm["billable_total"] + billable, 2)
        bm["units_total"] += r["units"]
    invoices = sorted(by_month.values(), key=lambda x: x["month"], reverse=True)
    return {"invoices": invoices, "markup_pct": markup, "currency": "INR"}

@api.get("/invoices/{month}")
async def invoice_detail(month: str, user: dict = Depends(require_roles("super_admin","admin"))):
    """month = YYYY-MM"""
    markup_row = await db.system_settings.find_one({"key": "markup_pct"}, {"_id": 0})
    markup = (markup_row or {}).get("value", {}) or {}
    records = await db.usage_records.find(
        cflt(user, {"created_at": {"$regex": f"^{month}"}}), {"_id": 0}
    ).sort("created_at", -1).limit(2000).to_list(2000)
    by_ch: Dict[str, Dict[str, Any]] = {}
    for r in records:
        ch = r["channel"]
        bm = by_ch.setdefault(ch, {"channel": ch, "units": 0, "base": 0, "markup_pct": float(markup.get(ch, 0))})
        bm["units"] += r["units"]
        bm["base"] = round(bm["base"] + r["amount"], 2)
        bm["billable"] = round(bm["base"] * (1 + bm["markup_pct"] / 100.0), 2)
    return {
        "month": month,
        "channels": list(by_ch.values()),
        "base_total": round(sum(c["base"] for c in by_ch.values()), 2),
        "billable_total": round(sum(c["billable"] for c in by_ch.values()), 2),
        "units_total": sum(c["units"] for c in by_ch.values()),
        "currency": "INR",
        "record_count": len(records),
    }

# ───────────────────────── Messages CSV export ─────────────────────────
@api.get("/export/messages.csv")
async def export_messages_csv(channel: Optional[Channel] = None, status: Optional[str] = None,
                              user: dict = Depends(current_user)):
    from fastapi.responses import StreamingResponse
    flt: Dict[str, Any] = cflt(user)
    if channel: flt["channel"] = channel
    if status: flt["status"] = status

    async def row_generator():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["created_at", "channel", "direction", "contact_id", "body", "status", "provider_message_id", "campaign_id"])
        yield buf.getvalue()
        cursor = db.messages.find(flt, {"_id": 0}).sort("created_at", -1)
        async for m in cursor:
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([
                m.get("created_at",""), m.get("channel",""), m.get("direction",""),
                m.get("contact_id",""), (m.get("body","") or "")[:500],
                m.get("status",""), m.get("provider_message_id",""), m.get("campaign_id","") or "",
            ])
            yield buf.getvalue()

    return StreamingResponse(row_generator(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=messages.csv"})

@api.get("/export/invoice/{month}.csv")
async def export_invoice_csv(month: str, user: dict = Depends(require_roles("super_admin","admin"))):
    from fastapi.responses import Response as FastResponse
    markup_row = await db.system_settings.find_one({"key": "markup_pct"}, {"_id": 0})
    markup = (markup_row or {}).get("value", {}) or {}
    records = await db.usage_records.find(
        cflt(user, {"created_at": {"$regex": f"^{month}"}}), {"_id": 0}
    ).sort("created_at", -1).limit(20000).to_list(20000)
    by_ch: Dict[str, Dict[str, Any]] = {}
    for r in records:
        ch = r["channel"]
        bm = by_ch.setdefault(ch, {"channel": ch, "units": 0, "base": 0, "markup_pct": float(markup.get(ch, 0))})
        bm["units"] += r["units"]
        bm["base"] = round(bm["base"] + r["amount"], 2)
        bm["billable"] = round(bm["base"] * (1 + bm["markup_pct"] / 100.0), 2)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"tezsandesh.digital Invoice — {month}"])
    w.writerow([])
    w.writerow(["channel", "units", "base_INR", "markup_pct", "billable_INR"])
    total_base, total_bill = 0, 0
    for c in by_ch.values():
        w.writerow([c["channel"], c["units"], f"{c['base']:.2f}", c["markup_pct"], f"{c['billable']:.2f}"])
        total_base += c["base"]; total_bill += c["billable"]
    w.writerow([])
    w.writerow(["TOTAL", "", f"{total_base:.2f}", "", f"{total_bill:.2f}"])
    return FastResponse(content=buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=invoice-{month}.csv"})

# ───────────────────────── Campaign scheduler loop ─────────────────────────
async def campaign_scheduler_loop():
    """Background task: every 30s, run any 'scheduled' campaigns whose schedule_at has passed."""
    log.info("campaign scheduler started")
    while True:
        try:
            scheduled = await db.campaigns.find({"status": "scheduled"}, {"_id": 0}).to_list(50)
            for c in scheduled:
                sat = c.get("schedule_at")
                if not sat:
                    continue
                try:
                    dt = datetime.fromisoformat(sat.replace("Z","+00:00"))
                except Exception:
                    continue
                if dt <= now_utc():
                    tpl = await db.templates.find_one({"id": c.get("template_id")}, {"_id": 0})
                    if not tpl:
                        await db.campaigns.update_one({"id": c["id"]}, {"$set": {"status": "failed", "error": "template missing"}})
                        await audit("campaign_failed", "campaign", c["id"], None, {"reason": "template missing"})
                        continue
                    audience = await resolve_audience({"company_id": c.get("company_id"), "role": "admin"}, c.get("list_ids", []) or [], c.get("contact_ids", []) or [])
                    await db.campaigns.update_one({"id": c["id"]}, {"$set": {"status": "running"}})
                    await audit("campaign_auto_started", "campaign", c["id"], None, {"name": c.get("name"), "audience_size": len(audience)})

                    async def safe_run(cid=c["id"], ch=c["channel"], t=tpl, aud=audience, comp=c.get("company_id")):
                        try:
                            await run_campaign(cid, ch, t, aud, {}, comp)
                        except Exception as e:
                            log.error(f"run_campaign crashed for {cid}: {e}")
                            await db.campaigns.update_one({"id": cid}, {"$set": {"status": "failed", "error": str(e)[:300]}})
                            await audit("campaign_failed", "campaign", cid, None, {"reason": str(e)[:300]})
                    asyncio.create_task(safe_run())
        except Exception as e:
            log.error(f"scheduler loop error: {e}")
        await asyncio.sleep(30)

# ───────────────────────── Mount ─────────────────────────
@api.get("/")
async def root():
    return {"name": "tezsandesh.digital API", "version": "1.0.0", "status": "ok"}

app.include_router(api)

# ───────────────────────── Extended features (PDF bills, Notices, AI Voice) ──────────
from features import build_features_router
app.include_router(build_features_router(
    db=db, current_user=current_user, require_roles=require_roles,
    audit=audit, emit_event=emit_event, ADAPTERS=ADAPTERS, cflt=cflt,
))
