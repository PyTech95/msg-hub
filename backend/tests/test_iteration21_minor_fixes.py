"""Iteration 21 — Targeted re-verification of 3 minor fixes flagged in iteration 20.

1. /api/whatsapp/send-contact-card: Meta 4xx surfaces as HTTP 400 (not 500) with
   detail + wallet refund on failure.
2. Razorpay refund idempotency: same refund_id via refund.created + refund.processed
   must debit wallet only once and second call returns duplicate_refund=true.
3. /api/auth/logout bumps users.token_version -> stale access_token cookie is 401.
"""
import os, json, hmac, hashlib, uuid, time
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
RAZORPAY_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "whsec_test_razor_1234")

DEMO_CREDS = {"email": "demo@demo.corp", "password": "DemoPass@123"}
DEMO_COMPANY_ID = "15bec8dc-48ac-488f-aff6-e4913010f0c0"

_mc = MongoClient(os.environ["MONGO_URL"])
mdb = _mc[os.environ["DB_NAME"]]


def _login_demo():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=DEMO_CREDS, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    if data.get("token"):
        s.headers.update({"Authorization": f"Bearer {data['token']}"})
    return s, data


def _wallet_bal(company_id):
    w = mdb.wallets.find_one({"company_id": company_id})
    return (w or {}).get("balance_paise", 0)


def _sig(body_bytes):
    return hmac.new(RAZORPAY_SECRET.encode(), body_bytes, hashlib.sha256).hexdigest()


# ─────────────────────────────────────────────────────────────
# FIX 1 — /whatsapp/send-contact-card try/except + wallet refund
# ─────────────────────────────────────────────────────────────
class TestSendContactCardErrorHandling:
    def test_meta_4xx_returns_400_not_500_and_refunds_wallet(self):
        s, _ = _login_demo()
        pre_bal = _wallet_bal(DEMO_COMPANY_ID)
        r = s.post(f"{BASE_URL}/api/whatsapp/send-contact-card",
                   json={"to": "+919876543211",
                         "name": "Test",
                         "phone": "+919111222333"}, timeout=30)
        assert r.status_code == 400, (
            f"Expected 400 (was 500 before fix), got {r.status_code}: {r.text[:400]}")
        body = r.text.lower()
        # Detail should mention WA send failed OR contain the tenant's own fake token
        assert ("whatsapp send failed" in body
                or "eaag_client_a_token_aaaa" in body), (
            f"Expected 'WhatsApp send failed' or tenant fake token in body: {body[:400]}")
        # Wallet must be refunded (net zero from before the call)
        post_bal = _wallet_bal(DEMO_COMPANY_ID)
        assert post_bal == pre_bal, (
            f"Wallet NOT refunded on send-contact-card failure. pre={pre_bal} post={post_bal}")


# ─────────────────────────────────────────────────────────────
# FIX 2 — Razorpay refund_id dedup across refund.created + refund.processed
# ─────────────────────────────────────────────────────────────
class TestRefundIdempotency:
    def _seed_paid_order(self, amount_paise=60000):
        order_id = f"order_iter21_{uuid.uuid4().hex[:10]}"
        payment_id = f"pay_iter21_{uuid.uuid4().hex[:10]}"
        mdb.wallet_recharge_orders.insert_one({
            "id": str(uuid.uuid4()),
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "company_id": DEMO_COMPANY_ID,
            "amount_paise": amount_paise,
            "currency": "INR",
            "status": "paid",
            "created_at": "2026-01-15T00:00:00+00:00",
        })
        mdb.wallets.update_one(
            {"company_id": DEMO_COMPANY_ID},
            {"$setOnInsert": {"balance_paise": 0, "company_id": DEMO_COMPANY_ID,
                              "updated_at": "2026-01-15T00:00:00+00:00"}}, upsert=True)
        return order_id, payment_id

    def _send(self, payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        return requests.post(f"{BASE_URL}/api/webhooks/razorpay", data=body,
                             headers={"X-Razorpay-Signature": _sig(body),
                                      "Content-Type": "application/json"}, timeout=30)

    def test_refund_dedup_by_refund_id(self):
        order_id, payment_id = self._seed_paid_order(amount_paise=60000)
        refund_id = f"rfnd_dedup_{uuid.uuid4().hex[:8]}"
        pre_bal = _wallet_bal(DEMO_COMPANY_ID)

        # 1st event: refund.processed
        evt1 = {"id": f"evt_{uuid.uuid4().hex[:12]}",
                "event": "refund.processed",
                "payload": {"refund": {"entity":
                    {"id": refund_id, "payment_id": payment_id, "amount": 30000}}}}
        r1 = self._send(evt1)
        assert r1.status_code == 200, r1.text
        mid_bal = _wallet_bal(DEMO_COMPANY_ID)
        assert mid_bal == pre_bal - 30000, (
            f"First refund did NOT debit correctly: pre={pre_bal} mid={mid_bal}")

        # 2nd event with DIFFERENT event id but SAME refund_id (refund.created)
        evt2 = {"id": f"evt_{uuid.uuid4().hex[:12]}",
                "event": "refund.created",
                "payload": {"refund": {"entity":
                    {"id": refund_id, "payment_id": payment_id, "amount": 30000}}}}
        r2 = self._send(evt2)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2.get("duplicate_refund") is True, (
            f"Expected duplicate_refund=true on same refund_id, got: {d2}")
        post_bal = _wallet_bal(DEMO_COMPANY_ID)
        assert post_bal == mid_bal, (
            f"DOUBLE-DEBIT detected on same refund_id: mid={mid_bal} post={post_bal}")

        # 3rd event: same refund_id again refund.processed - still dedup
        evt3 = {"id": f"evt_{uuid.uuid4().hex[:12]}",
                "event": "refund.processed",
                "payload": {"refund": {"entity":
                    {"id": refund_id, "payment_id": payment_id, "amount": 30000}}}}
        r3 = self._send(evt3)
        assert r3.status_code == 200
        assert r3.json().get("duplicate_refund") is True
        assert _wallet_bal(DEMO_COMPANY_ID) == mid_bal, "3rd replay double-debited"


# ─────────────────────────────────────────────────────────────
# FIX 3 — /auth/logout bumps token_version
# ─────────────────────────────────────────────────────────────
class TestLogoutBumpsTokenVersion:
    def test_stale_access_token_invalidated_after_logout(self):
        # Login fresh
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json=DEMO_CREDS, timeout=15)
        assert r.status_code == 200
        old_access_cookie = s.cookies.get("access_token")
        assert old_access_cookie, "No access_token cookie set on login"

        # Verify /me works with cookie
        s.headers.pop("Authorization", None)
        me = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert me.status_code == 200, me.text
        user_id = me.json()["id"]

        # DB: capture current token_version
        u_before = mdb.users.find_one({"id": user_id}, {"token_version": 1})
        tv_before = (u_before or {}).get("token_version", 1)

        # Logout
        lo = s.post(f"{BASE_URL}/api/auth/logout", timeout=15)
        assert lo.status_code == 200

        # DB: token_version must be incremented by exactly 1
        u_after = mdb.users.find_one({"id": user_id}, {"token_version": 1})
        tv_after = (u_after or {}).get("token_version", 1)
        assert tv_after == tv_before + 1, (
            f"token_version not bumped: before={tv_before} after={tv_after}")

        # Use ONLY the OLD access_token cookie (bypass session's cleared cookies)
        # to call /me — MUST be rejected as 401.
        me_stale = requests.get(f"{BASE_URL}/api/auth/me",
                                cookies={"access_token": old_access_cookie},
                                timeout=15)
        assert me_stale.status_code == 401, (
            f"STALE access_token still valid after logout — token_version bump not enforced! "
            f"Got {me_stale.status_code}: {me_stale.text[:300]}")
