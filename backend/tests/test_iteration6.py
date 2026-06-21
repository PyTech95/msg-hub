"""
Iteration 6 backend tests:
- Smart Reminder Automation (T-7 SMS / T-3 WhatsApp / T-1 Voice)
- Invoice PDF download
- Regression on auth, bills list, notices list, voice-campaigns, invoices, CSV export
"""
import os
import uuid
import requests
from datetime import datetime, timezone, timedelta
import pytest
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@cpaas.io", "password": "Admin@12345"}
AGENT = {"email": "agent@cpaas.io", "password": "Agent@12345"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def agent_token():
    return _login(AGENT)


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def agent_headers(agent_token):
    return {"Authorization": f"Bearer {agent_token}"}


@pytest.fixture(scope="module")
def db():
    # Use same MONGO_URL / DB_NAME the backend uses
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_database")
    client = MongoClient(mongo_url)
    return client[db_name]


@pytest.fixture
def seeded_bill(db):
    """Insert a synthetic bill directly to bypass LLM budget."""
    bill_id = f"TEST_{uuid.uuid4()}"
    due = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%d")
    doc = {
        "id": bill_id,
        "batch_id": "TEST_BATCH",
        "name": "Iter6 Tester",
        "phone": "+919999000111",
        "email": "iter6@test.local",
        "property_id": "PROP-IT6",
        "address": "Test Addr",
        "amount": 1234.5,
        "due_date": due,
        "raw": "test bill",
        "sent": {"sms": False, "whatsapp": False, "email": False},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.bills.insert_one(doc)
    yield bill_id
    db.bills.delete_one({"id": bill_id})
    db.reminder_schedules.delete_many({"bill_id": bill_id})


# ---------------------- AUTH REGRESSION ----------------------
class TestAuth:
    def test_admin_login(self, admin_token):
        assert admin_token and isinstance(admin_token, str)

    def test_agent_login(self, agent_token):
        assert agent_token and isinstance(agent_token, str)


# ---------------------- SMART REMINDERS ----------------------
class TestSmartReminders:
    def test_enable_reminders_creates_three_schedules(self, admin_headers, seeded_bill, db):
        r = requests.post(f"{API}/bills/enable-reminders",
                          json={"bill_ids": [seeded_bill]}, headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created"] == 3
        assert data["bills_enabled"] == 1
        assert data["skipped"] == 0
        # Verify in DB
        scheds = list(db.reminder_schedules.find({"bill_id": seeded_bill}))
        assert len(scheds) == 3
        channels = sorted(s["channel"] for s in scheds)
        assert channels == ["sms", "voice", "whatsapp"]
        for s in scheds:
            assert s["status"] == "pending"
        # bill.auto_remind=true
        b = db.bills.find_one({"id": seeded_bill})
        assert b["auto_remind"] is True

    def test_enable_reminders_skips_without_due_date(self, admin_headers, db):
        bid = f"TEST_NODUE_{uuid.uuid4()}"
        db.bills.insert_one({
            "id": bid, "name": "NoDue", "phone": "+919000000001",
            "email": "n@t.io", "property_id": "P1", "amount": 10,
            "due_date": "", "created_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            r = requests.post(f"{API}/bills/enable-reminders",
                              json={"bill_ids": [bid]}, headers=admin_headers, timeout=20)
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["skipped"] == 1
            assert data["created"] == 0
            assert data["bills_enabled"] == 0
        finally:
            db.bills.delete_one({"id": bid})

    def test_get_bill_schedules(self, admin_headers, seeded_bill):
        # First enable
        requests.post(f"{API}/bills/enable-reminders",
                      json={"bill_ids": [seeded_bill]}, headers=admin_headers, timeout=20)
        r = requests.get(f"{API}/bills/{seeded_bill}/schedules", headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        scheds = r.json()
        assert isinstance(scheds, list)
        assert len(scheds) == 3
        days = sorted(s["days_before"] for s in scheds)
        assert days == [1, 3, 7]

    def test_upcoming_reminders_enriched(self, admin_headers, seeded_bill):
        requests.post(f"{API}/bills/enable-reminders",
                      json={"bill_ids": [seeded_bill]}, headers=admin_headers, timeout=20)
        r = requests.get(f"{API}/reminders/upcoming", headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        ours = [x for x in rows if x["bill_id"] == seeded_bill]
        assert len(ours) == 3
        # bill metadata enrichment
        b = ours[0]["bill"]
        assert b["name"] == "Iter6 Tester"
        assert b["property_id"] == "PROP-IT6"
        assert b["amount"] == 1234.5
        assert b["phone"] == "+919999000111"
        assert b["email"] == "iter6@test.local"

    def test_mark_paid_cancels_schedules(self, admin_headers, seeded_bill, db):
        # enable
        requests.post(f"{API}/bills/enable-reminders",
                      json={"bill_ids": [seeded_bill]}, headers=admin_headers, timeout=20)
        r = requests.post(f"{API}/bills/{seeded_bill}/mark-paid",
                         headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["cancelled"] == 3
        # Verify DB state
        b = db.bills.find_one({"id": seeded_bill})
        assert b["paid"] is True
        statuses = [s["status"] for s in db.reminder_schedules.find({"bill_id": seeded_bill})]
        assert all(s == "cancelled" for s in statuses)


# ---------------------- INVOICE PDF ----------------------
class TestInvoicePDF:
    def test_admin_can_download_pdf(self, admin_headers):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{API}/export/invoice/{month}.pdf", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert "application/pdf" in r.headers.get("Content-Type", "")
        # PDF magic bytes
        assert r.content[:4] == b"%PDF", f"Not a PDF, head={r.content[:8]!r}"
        assert len(r.content) > 1000

    def test_agent_forbidden(self, agent_headers):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{API}/export/invoice/{month}.pdf", headers=agent_headers, timeout=20)
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"

    def test_csv_export_still_works(self, admin_headers):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{API}/export/invoice/{month}.csv", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("Content-Type", "") or "csv" in r.headers.get("Content-Type", "")


# ---------------------- REGRESSION ----------------------
class TestRegression:
    def test_invoices_list(self, admin_headers):
        r = requests.get(f"{API}/invoices", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        assert "invoices" in r.json()

    def test_notice_templates_list(self, admin_headers):
        r = requests.get(f"{API}/notice-templates", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_voice_campaigns_list(self, admin_headers):
        r = requests.get(f"{API}/voice-campaigns", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_bills_list(self, admin_headers):
        r = requests.get(f"{API}/bills", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_bills_upload_endpoint_exists(self, admin_headers):
        # No file → expect 422 (validation error), proving the endpoint is mounted
        r = requests.post(f"{API}/bills/upload", headers=admin_headers, timeout=20)
        assert r.status_code in (400, 422), f"got {r.status_code}: {r.text[:120]}"
