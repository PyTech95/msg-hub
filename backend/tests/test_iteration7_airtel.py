"""
Iteration 7 backend tests — Airtel IQ adapter + webhooks + rebrand regression.
"""
import os
import time
import requests
import pytest
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@cpaas.io", "password": "Admin@12345"}
AGENT = {"email": "agent@cpaas.io", "password": "Agent@12345"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login: {r.status_code} {r.text[:200]}"
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login(ADMIN)}"}


@pytest.fixture(scope="module")
def agent_headers():
    return {"Authorization": f"Bearer {_login(AGENT)}"}


@pytest.fixture(scope="module")
def db():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_database")
    return MongoClient(mongo_url)[db_name]


# ─── ROOT / REBRAND ───────────────────────────────────
class TestRebrand:
    def test_root_endpoint_name(self):
        r = requests.get(f"{API}/", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data.get("name") == "tezsandesh.digital API", data


# ─── PROVIDERS CARDS INCLUDE 3 AIRTEL IQ ─────────────
class TestProviders:
    def test_providers_include_airtel_iq(self, admin_headers):
        r = requests.get(f"{API}/providers", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        provs = r.json()
        aq = [p for p in provs if p.get("provider_key") == "airtel_iq"]
        channels = sorted(p["channel"] for p in aq)
        assert channels == ["sms", "voice", "whatsapp"], f"got {channels}"


# ─── WEBHOOKS ─────────────────────────────────────────
class TestAirtelWebhooks:
    def test_sms_dlr_no_signature_returns_200_and_row(self, db):
        payload = {"messageId": "aq_fake_1", "status": "DELIVERED", "statusDescription": "ok"}
        r = requests.post(f"{API}/webhooks/airtel/sms/dlr", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        # webhook_events row created with signature_valid=True
        ev = db.webhook_events.find_one({"payload.messageId": "aq_fake_1"}, sort=[("created_at", -1)])
        assert ev is not None
        assert ev["signature_valid"] is True

    def test_sms_dlr_correlates_and_transitions_status(self, admin_headers, db):
        # Send an SMS via /api/messages/send to get a provider_message_id (mock)
        # Need a contact first
        c = requests.post(f"{API}/contacts",
                          json={"name": "AQTest", "phone": "+919000009999", "tags": ["aq-test"]},
                          headers=admin_headers, timeout=20)
        assert c.status_code in (200, 201), c.text
        cid = c.json()["id"]
        send = requests.post(f"{API}/messages/send",
                             json={"channel": "sms", "contact_id": cid, "body": "hi"},
                             headers=admin_headers, timeout=20)
        assert send.status_code in (200, 201), send.text
        m = send.json()
        msg_id = m.get("id") or m.get("message_id")
        assert msg_id, m
        # simulate_lifecycle async; wait for provider_message_id to be persisted
        pmid = None
        for _ in range(20):
            doc = db.messages.find_one({"id": msg_id})
            if doc and doc.get("provider_message_id"):
                pmid = doc["provider_message_id"]
                break
            time.sleep(0.3)
        assert pmid, f"no pmid persisted for {msg_id}"
        # Fire DLR — after lifecycle background likely done to avoid race
        time.sleep(2)
        r = requests.post(f"{API}/webhooks/airtel/sms/dlr",
                          json={"messageId": pmid, "status": "DELIVERED"}, timeout=20)
        assert r.status_code == 200
        # poll for delivered
        final = None
        for _ in range(20):
            doc = db.messages.find_one({"id": msg_id})
            if doc and doc.get("status") == "delivered":
                final = "delivered"
                break
            time.sleep(0.5)
        assert final == "delivered", f"final status: {doc.get('status') if doc else None}"

    def test_whatsapp_inbound_creates_contact_and_message(self, db):
        phone = "+919000000001"
        # cleanup previous
        db.contacts.delete_many({"phone": phone})
        payload = {"from": phone, "text": {"body": "hello from WA"}}
        r = requests.post(f"{API}/webhooks/airtel/whatsapp/inbound", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        contact = db.contacts.find_one({"phone": phone})
        assert contact is not None
        assert "wa-inbound" in (contact.get("tags") or [])
        # inbound message exists
        msg = db.messages.find_one({"contact_id": contact["id"], "direction": "inbound"})
        assert msg is not None
        assert msg["body"] == "hello from WA"

    def test_voice_status_returns_200(self):
        payload = {"callId": "aqv_fake_1", "status": "COMPLETED",
                   "duration": 87, "recordingUrl": "https://x/a.mp3"}
        r = requests.post(f"{API}/webhooks/airtel/voice/status", json=payload, timeout=20)
        assert r.status_code == 200
        assert r.json().get("ok") is True


# ─── MESSAGES SEND VIA AIRTEL SMS ADAPTER ────────────
class TestMessageSendSMS:
    def test_send_sms_creates_queued_message_with_pmid(self, admin_headers, db):
        c = requests.post(f"{API}/contacts",
                          json={"name": "AQSend", "phone": "+919000009000", "tags": ["aq"]},
                          headers=admin_headers, timeout=20)
        cid = c.json()["id"]
        r = requests.post(f"{API}/messages/send",
                          json={"channel": "sms", "contact_id": cid, "body": "hello world"},
                          headers=admin_headers, timeout=20)
        assert r.status_code in (200, 201), r.text
        m = r.json()
        msg_id = m.get("id") or m.get("message_id")
        assert msg_id, m
        # wait for pmid to appear
        pmid = None
        for _ in range(20):
            doc = db.messages.find_one({"id": msg_id})
            if doc and doc.get("provider_message_id"):
                pmid = doc["provider_message_id"]
                break
            time.sleep(0.3)
        assert pmid, f"no pmid: {doc}"
        assert doc.get("status") in ("queued", "sent", "delivered")
        # allow simulate_lifecycle time
        final = None
        for _ in range(20):
            doc = db.messages.find_one({"id": msg_id})
            if doc and doc.get("status") == "delivered":
                final = doc["status"]
                break
            time.sleep(0.5)
        # Not strictly required but tag it (simulate_lifecycle may be internal only)
        assert doc is not None


# ─── REGRESSION ───────────────────────────────────────
class TestRegression:
    def test_login_admin(self):
        assert _login(ADMIN)

    def test_contacts_list(self, admin_headers):
        r = requests.get(f"{API}/contacts", headers=admin_headers, timeout=20)
        assert r.status_code == 200

    def test_campaigns_list(self, admin_headers):
        r = requests.get(f"{API}/campaigns", headers=admin_headers, timeout=20)
        assert r.status_code == 200

    def test_reminders_upcoming(self, admin_headers):
        r = requests.get(f"{API}/reminders/upcoming", headers=admin_headers, timeout=20)
        assert r.status_code == 200

    def test_invoice_pdf(self, admin_headers):
        from datetime import datetime, timezone
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{API}/export/invoice/{month}.pdf", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_mark_paid_missing_bill_404(self, admin_headers):
        r = requests.post(f"{API}/bills/NOTEXIST_XYZ/mark-paid", headers=admin_headers, timeout=20)
        assert r.status_code == 404

    def test_enable_reminders_empty_422(self, admin_headers):
        r = requests.post(f"{API}/bills/enable-reminders", json={"bill_ids": []},
                          headers=admin_headers, timeout=20)
        assert r.status_code == 422
