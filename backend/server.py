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

app = FastAPI(title="NSTU API", version="1.0.0")
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
    body: str
    media_url: Optional[str] = None

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

    async def send(self, to: str, body: str, media_url: Optional[str] = None) -> Dict[str, Any]:
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
    async def send(self, to: str, body: str, media_url=None):
        log.info(f"[mock email] to={to} body={(body or '')[:80]} attachment={media_url}")
        return {"provider_message_id": f"email_{secrets.token_hex(8)}", "accepted": True}

ADAPTERS: Dict[str, BaseAdapter] = {
    "sms": SMSAdapter(),
    "whatsapp": WhatsAppAdapter(),
    "rcs": RCSAdapter(),
    "voice": VoiceAdapter(),
    "email": EmailAdapter(),
}

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
        {"$set": {"last_message_at": iso(now_utc()), "last_message": body, "unread": True}},
        upsert=True,
    )
    if body.strip().upper() == "STOP":
        await db.contacts.update_one({"id": msg["contact_id"]}, {"$set": {"opted_out": True}})

async def deliver_message(message_id: str, channel: Channel):
    adapter = ADAPTERS[channel]
    await adapter.simulate_lifecycle(message_id)
    # usage accounting
    await db.usage_records.insert_one({
        "id": new_id(),
        "channel": channel,
        "message_id": message_id,
        "units": 1,
        "amount": PRICING[channel],
        "currency": "INR",
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

    # Only seed sample data once
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
        {"id": new_id(), "name": "Welcome SMS", "channel": "sms", "body": "Hi {{name}}, welcome to NSTU!", "variables": ["name"], "status": "approved", "category": "utility", "created_at": iso(now_utc())},
        {"id": new_id(), "name": "WA Order Update", "channel": "whatsapp", "body": "Hello {{name}}, your order #{{order_id}} has shipped.", "variables": ["name","order_id"], "status": "approved", "category": "utility", "created_at": iso(now_utc())},
        {"id": new_id(), "name": "RCS Diwali Offer", "channel": "rcs", "body": "🪔 {{name}}, enjoy 30% off this Diwali!", "variables": ["name"], "status": "approved", "category": "marketing", "created_at": iso(now_utc())},
        {"id": new_id(), "name": "Voice OTP Verify", "channel": "voice", "body": "Your verification code is {{code}}", "variables": ["code"], "status": "approved", "category": "authentication", "created_at": iso(now_utc())},
    ]
    await db.templates.insert_many(templates)

    # Providers
    providers = [
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
    return {"token": token, "user": clean(user)}

@api.post("/auth/register")
async def register(body: RegisterIn, user: dict = Depends(require_roles("super_admin","admin"))):
    if await db.users.find_one({"email": body.email.lower()}):
        raise HTTPException(409, "Email already exists")
    doc = {
        "id": new_id(), "email": body.email.lower(), "password_hash": hash_pw(body.password),
        "name": body.name, "role": body.role, "token_version": 1, "created_at": iso(now_utc()),
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
    return user

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
    uri = pyotp.TOTP(secret).provisioning_uri(name=user["email"], issuer_name="NSTU")
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
async def list_users(_: dict = Depends(current_user)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(500)
    return users

@api.delete("/users/{user_id}")
async def delete_user(user_id: str, actor: dict = Depends(require_roles("super_admin"))):
    if user_id == actor["id"]:
        raise HTTPException(400, "Cannot delete yourself")
    target = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    await db.users.delete_one({"id": user_id})
    await audit("user_deleted", "user", user_id, actor, {"target_email": (target or {}).get("email")})
    return {"ok": True}

# ───────────────────────── Contacts ─────────────────────────
@api.get("/contacts")
async def list_contacts(q: Optional[str] = None, list_id: Optional[str] = None, _: dict = Depends(current_user)):
    flt: Dict[str, Any] = {}
    if q:
        flt["$or"] = [{"name": {"$regex": q, "$options": "i"}}, {"phone": {"$regex": q}}, {"email": {"$regex": q, "$options": "i"}}]
    if list_id:
        flt["list_ids"] = list_id
    docs = await db.contacts.find(flt, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs

@api.post("/contacts")
async def create_contact(body: ContactIn, _: dict = Depends(current_user)):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["opted_out"] = False
    doc["created_at"] = iso(now_utc())
    await db.contacts.insert_one(doc)
    return clean(doc)

@api.get("/contacts/{contact_id}")
async def get_contact(contact_id: str, _: dict = Depends(current_user)):
    c = await db.contacts.find_one({"id": contact_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Contact not found")
    return c

@api.patch("/contacts/{contact_id}")
async def update_contact(contact_id: str, body: ContactUpdate, _: dict = Depends(current_user)):
    upd = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not upd:
        raise HTTPException(400, "No fields")
    await db.contacts.update_one({"id": contact_id}, {"$set": upd})
    c = await db.contacts.find_one({"id": contact_id}, {"_id": 0})
    return c

@api.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str, _: dict = Depends(require_roles("super_admin","admin"))):
    await db.contacts.delete_one({"id": contact_id})
    return {"ok": True}

@api.post("/contacts/bulk-delete")
async def bulk_delete_contacts(ids: List[str], _: dict = Depends(require_roles("super_admin","admin"))):
    res = await db.contacts.delete_many({"id": {"$in": ids}})
    return {"deleted": res.deleted_count}

@api.post("/contacts/import")
async def import_contacts_csv(file: UploadFile = File(...), _: dict = Depends(current_user)):
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
            "custom_fields": {}, "created_at": iso(now_utc()),
        })
    if docs:
        await db.contacts.insert_many(docs)
        inserted = len(docs)
    return {"inserted": inserted, "skipped": skipped}

# ───────────────────────── Lists ─────────────────────────
@api.get("/lists")
async def list_lists(_: dict = Depends(current_user)):
    return await db.contact_lists.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)

@api.post("/lists")
async def create_list(body: ListIn, _: dict = Depends(current_user)):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = iso(now_utc())
    await db.contact_lists.insert_one(doc)
    return clean(doc)

@api.delete("/lists/{list_id}")
async def delete_list(list_id: str, _: dict = Depends(require_roles("super_admin","admin"))):
    await db.contact_lists.delete_one({"id": list_id})
    return {"ok": True}

@api.patch("/lists/{list_id}")
async def update_list(list_id: str, body: ListIn, _: dict = Depends(require_roles("super_admin","admin"))):
    await db.contact_lists.update_one({"id": list_id}, {"$set": body.model_dump()})
    return await db.contact_lists.find_one({"id": list_id}, {"_id": 0})

@api.get("/export/contacts.csv")
async def export_contacts_csv(_: dict = Depends(current_user)):
    from fastapi.responses import Response as FastResponse
    docs = await db.contacts.find({}, {"_id": 0}).to_list(10000)
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
async def list_templates(channel: Optional[Channel] = None, _: dict = Depends(current_user)):
    flt = {"channel": channel} if channel else {}
    return await db.templates.find(flt, {"_id": 0}).sort("created_at", -1).to_list(500)

@api.post("/templates")
async def create_template(body: TemplateIn, _: dict = Depends(current_user)):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = iso(now_utc())
    await db.templates.insert_one(doc)
    return clean(doc)

@api.patch("/templates/{template_id}")
async def update_template(template_id: str, body: TemplateIn, _: dict = Depends(current_user)):
    await db.templates.update_one({"id": template_id}, {"$set": body.model_dump()})
    t = await db.templates.find_one({"id": template_id}, {"_id": 0})
    return t

@api.delete("/templates/{template_id}")
async def delete_template(template_id: str, _: dict = Depends(require_roles("super_admin","admin"))):
    await db.templates.delete_one({"id": template_id})
    return {"ok": True}

# ───────────────────────── Campaigns ─────────────────────────
def render_body(tpl_body: str, contact: dict, variables_map: Dict[str, Any]) -> str:
    body = tpl_body
    merged = {"name": contact.get("name",""), "phone": contact.get("phone","")}
    merged.update(variables_map or {})
    for k, v in merged.items():
        body = body.replace("{{" + k + "}}", str(v))
    return body

async def resolve_audience(list_ids: List[str], contact_ids: List[str]) -> List[dict]:
    flt: Dict[str, Any] = {"opted_out": {"$ne": True}, "dnd": {"$ne": True}}
    or_clauses = []
    if list_ids:
        or_clauses.append({"list_ids": {"$in": list_ids}})
    if contact_ids:
        or_clauses.append({"id": {"$in": contact_ids}})
    if or_clauses:
        flt["$or"] = or_clauses
    return await db.contacts.find(flt, {"_id": 0}).to_list(10000)

@api.get("/campaigns")
async def list_campaigns(_: dict = Depends(current_user)):
    return await db.campaigns.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)

@api.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, _: dict = Depends(current_user)):
    c = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Not found")
    recipients = await db.campaign_recipients.find({"campaign_id": campaign_id}, {"_id": 0}).limit(500).to_list(500)
    return {"campaign": c, "recipients": recipients}

@api.post("/campaigns")
async def create_campaign(body: CampaignIn, background: BackgroundTasks, user: dict = Depends(current_user)):
    tpl = await db.templates.find_one({"id": body.template_id}, {"_id": 0})
    if not tpl:
        raise HTTPException(404, "Template not found")
    audience = await resolve_audience(body.list_ids, body.contact_ids)
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
        "created_by": user["email"], "created_at": iso(now_utc()),
    }
    await db.campaigns.insert_one(camp)
    recipients = [{"id": new_id(), "campaign_id": camp["id"], "contact_id": c["id"], "status": "queued", "created_at": iso(now_utc())} for c in audience]
    if recipients:
        await db.campaign_recipients.insert_many(recipients)
    await audit("campaign_created", "campaign", camp["id"], user, {"name": camp["name"], "channel": camp["channel"], "audience_size": len(audience), "status": status})
    if status == "running":
        background.add_task(run_campaign, camp["id"], body.channel, tpl, audience, body.variables_map)
    return clean(camp)

async def run_campaign(campaign_id: str, channel: Channel, tpl: dict, audience: List[dict], variables_map: Dict[str, Any]):
    adapter = ADAPTERS[channel]
    for c in audience:
        body = render_body(tpl["body"], c, variables_map)
        mid = new_id()
        msg = {
            "id": mid, "channel": channel, "contact_id": c["id"], "direction": "outbound",
            "body": body, "media_url": tpl.get("media_url"),
            "status": "queued", "provider_message_id": None,
            "campaign_id": campaign_id, "created_at": iso(now_utc()), "updated_at": iso(now_utc()),
        }
        await db.messages.insert_one(msg)
        try:
            resp = await adapter.send(c["phone"], body, tpl.get("media_url"))
            await db.messages.update_one({"id": mid}, {"$set": {"provider_message_id": resp.get("provider_message_id"), "status": "queued"}})
        except Exception as e:
            await emit_event(mid, "failed", reason=str(e))
            continue
        await db.campaign_recipients.update_one({"campaign_id": campaign_id, "contact_id": c["id"]}, {"$set": {"status": "sent"}})
        await db.conversations.update_one(
            {"contact_id": c["id"], "channel": channel},
            {"$set": {"last_message_at": iso(now_utc()), "last_message": body}}, upsert=True,
        )
        asyncio.create_task(deliver_message(mid, channel))
        await asyncio.sleep(0.05)
    await db.campaigns.update_one({"id": campaign_id}, {"$set": {"status": "completed", "completed_at": iso(now_utc())}})

@api.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, _: dict = Depends(require_roles("super_admin","admin"))):
    await db.campaigns.delete_one({"id": campaign_id})
    await db.campaign_recipients.delete_many({"campaign_id": campaign_id})
    return {"ok": True}

# ───────────────────────── Messages (single send + logs) ─────────────────────────
@api.post("/messages/send")
async def send_message(body: SendMessageIn, background: BackgroundTasks, user: dict = Depends(current_user)):
    contact = await db.contacts.find_one({"id": body.contact_id}, {"_id": 0})
    if not contact:
        raise HTTPException(404, "Contact not found")
    if contact.get("opted_out"):
        raise HTTPException(400, "Contact has opted out")
    mid = new_id()
    msg = {
        "id": mid, "channel": body.channel, "contact_id": body.contact_id, "direction": "outbound",
        "body": body.body, "media_url": body.media_url, "status": "queued",
        "provider_message_id": None, "campaign_id": None,
        "created_at": iso(now_utc()), "updated_at": iso(now_utc()),
    }
    await db.messages.insert_one(msg)
    adapter = ADAPTERS[body.channel]
    resp = await adapter.send(contact["phone"], body.body, body.media_url)
    await db.messages.update_one({"id": mid}, {"$set": {"provider_message_id": resp["provider_message_id"]}})
    await db.conversations.update_one(
        {"contact_id": body.contact_id, "channel": body.channel},
        {"$set": {"last_message_at": iso(now_utc()), "last_message": body.body}}, upsert=True,
    )
    background.add_task(deliver_message, mid, body.channel)
    return {"message_id": mid, "status": "queued"}

@api.get("/messages")
async def list_messages(channel: Optional[Channel] = None, contact_id: Optional[str] = None, status: Optional[str] = None, limit: int = 200, _: dict = Depends(current_user)):
    flt: Dict[str, Any] = {}
    if channel: flt["channel"] = channel
    if contact_id: flt["contact_id"] = contact_id
    if status: flt["status"] = status
    msgs = await db.messages.find(flt, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return msgs

@api.get("/messages/{message_id}/events")
async def message_events(message_id: str, _: dict = Depends(current_user)):
    return await db.message_events.find({"message_id": message_id}, {"_id": 0}).sort("created_at", 1).to_list(200)

# ───────────────────────── Conversations ─────────────────────────
@api.get("/conversations")
async def list_conversations(_: dict = Depends(current_user)):
    convs = await db.conversations.find({}, {"_id": 0}).sort("last_message_at", -1).to_list(500)
    # enrich with contact name
    for c in convs:
        contact = await db.contacts.find_one({"id": c["contact_id"]}, {"_id": 0, "name": 1, "phone": 1})
        if contact:
            c["contact_name"] = contact["name"]
            c["contact_phone"] = contact["phone"]
    return convs

@api.get("/contacts/{contact_id}/timeline")
async def contact_timeline(contact_id: str, _: dict = Depends(current_user)):
    msgs = await db.messages.find({"contact_id": contact_id}, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    calls = await db.call_logs.find({"contact_id": contact_id}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"messages": msgs, "calls": calls}

# ───────────────────────── Voice Calls ─────────────────────────
@api.post("/calls")
async def initiate_call(body: CallIn, background: BackgroundTasks, user: dict = Depends(current_user)):
    contact = await db.contacts.find_one({"id": body.contact_id}, {"_id": 0})
    if not contact:
        raise HTTPException(404, "Contact not found")
    cid = new_id()
    call = {
        "id": cid, "contact_id": body.contact_id, "direction": "outbound", "status": "initiated",
        "duration_sec": 0, "recording_url": None,
        "provider_call_id": f"mock_{secrets.token_hex(6)}",
        "notes": body.notes or "",
        "started_at": iso(now_utc()), "ended_at": None,
        "created_at": iso(now_utc()),
    }
    await db.call_logs.insert_one(call)
    background.add_task(ADAPTERS["voice"].simulate_lifecycle, cid)
    # usage
    await db.usage_records.insert_one({
        "id": new_id(), "channel": "voice", "message_id": cid, "units": 1, "amount": PRICING["voice"],
        "currency": "INR", "created_at": iso(now_utc())
    })
    return {"call_id": cid, "status": "initiated"}

@api.get("/calls")
async def list_calls(_: dict = Depends(current_user)):
    return await db.call_logs.find({}, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)

# ───────────────────────── Providers ─────────────────────────
@api.get("/providers")
async def list_providers(_: dict = Depends(current_user)):
    return await db.provider_accounts.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)

@api.post("/providers")
async def create_provider(body: ProviderIn, _: dict = Depends(require_roles("super_admin","admin"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = iso(now_utc())
    await db.provider_accounts.insert_one(doc)
    return clean(doc)

@api.patch("/providers/{provider_id}")
async def update_provider(provider_id: str, body: ProviderIn, _: dict = Depends(require_roles("super_admin","admin"))):
    await db.provider_accounts.update_one({"id": provider_id}, {"$set": body.model_dump()})
    p = await db.provider_accounts.find_one({"id": provider_id}, {"_id": 0})
    return p

@api.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str, _: dict = Depends(require_roles("super_admin"))):
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
async def get_provider_credentials(provider_id: str, _: dict = Depends(require_roles("super_admin","admin"))):
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
async def set_provider_credentials(provider_id: str, body: ProviderCredentialsIn, user: dict = Depends(require_roles("super_admin"))):
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
async def test_provider(provider_id: str, _: dict = Depends(require_roles("super_admin","admin"))):
    p = await db.provider_accounts.find_one({"id": provider_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Not found")
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
async def list_webhook_events(limit: int = 100, _: dict = Depends(current_user)):
    return await db.webhook_events.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)

# ───────────────────────── Usage / Billing ─────────────────────────
@api.get("/usage/summary")
async def usage_summary(_: dict = Depends(current_user)):
    pipeline = [{"$group": {"_id": "$channel", "units": {"$sum": "$units"}, "amount": {"$sum": "$amount"}}}]
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
async def usage_records(limit: int = 200, _: dict = Depends(current_user)):
    return await db.usage_records.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)

# ───────────────────────── Dashboard / Analytics ─────────────────────────
@api.get("/dashboard/stats")
async def dashboard_stats(_: dict = Depends(current_user)):
    total_msgs = await db.messages.count_documents({})
    delivered = await db.messages.count_documents({"status": "delivered"})
    failed = await db.messages.count_documents({"status": "failed"})
    replied = await db.messages.count_documents({"direction": "inbound"})
    active_campaigns = await db.campaigns.count_documents({"status": {"$in": ["running","scheduled"]}})
    contacts_count = await db.contacts.count_documents({})

    # last 7 days bar series by channel
    since = now_utc() - timedelta(days=7)
    pipeline = [
        {"$match": {"created_at": {"$gte": iso(since)}}},
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
    pipeline2 = [{"$group": {"_id": "$channel", "count": {"$sum": 1}}}]
    by_channel = await db.messages.aggregate(pipeline2).to_list(20)
    channel_split = [{"channel": r["_id"], "count": r["count"]} for r in by_channel]

    # status split for delivery donut
    pipeline3 = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
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
                          _: dict = Depends(require_roles("super_admin","admin"))):
    flt: Dict[str, Any] = {}
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
async def list_invoices(_: dict = Depends(require_roles("super_admin","admin"))):
    """Return monthly invoice summaries (last 6 months that have usage)."""
    markup_row = await db.system_settings.find_one({"key": "markup_pct"}, {"_id": 0})
    markup = (markup_row or {}).get("value", {}) or {}
    pipeline = [
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
async def invoice_detail(month: str, _: dict = Depends(require_roles("super_admin","admin"))):
    """month = YYYY-MM"""
    markup_row = await db.system_settings.find_one({"key": "markup_pct"}, {"_id": 0})
    markup = (markup_row or {}).get("value", {}) or {}
    records = await db.usage_records.find(
        {"created_at": {"$regex": f"^{month}"}}, {"_id": 0}
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
                              _: dict = Depends(current_user)):
    from fastapi.responses import StreamingResponse
    flt: Dict[str, Any] = {}
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
async def export_invoice_csv(month: str, _: dict = Depends(require_roles("super_admin","admin"))):
    from fastapi.responses import Response as FastResponse
    markup_row = await db.system_settings.find_one({"key": "markup_pct"}, {"_id": 0})
    markup = (markup_row or {}).get("value", {}) or {}
    records = await db.usage_records.find(
        {"created_at": {"$regex": f"^{month}"}}, {"_id": 0}
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
    w.writerow([f"NSTU Invoice — {month}"])
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
                    audience = await resolve_audience(c.get("list_ids", []) or [], c.get("contact_ids", []) or [])
                    await db.campaigns.update_one({"id": c["id"]}, {"$set": {"status": "running"}})
                    await audit("campaign_auto_started", "campaign", c["id"], None, {"name": c.get("name"), "audience_size": len(audience)})

                    async def safe_run(cid=c["id"], ch=c["channel"], t=tpl, aud=audience):
                        try:
                            await run_campaign(cid, ch, t, aud, {})
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
    return {"name": "NSTU API", "version": "1.0.0", "status": "ok"}

app.include_router(api)

# ───────────────────────── Extended features (PDF bills, Notices, AI Voice) ──────────
from features import build_features_router
app.include_router(build_features_router(
    db=db, current_user=current_user, require_roles=require_roles,
    audit=audit, emit_event=emit_event, ADAPTERS=ADAPTERS,
))
