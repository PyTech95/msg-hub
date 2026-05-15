"""Iteration 4 tests: brute-force lockout, forgot-password rate-limit, 2FA TOTP, streaming CSV, invoice CSV.

NOTE: Auth tests intentionally clear `login_attempts` collection at start AND end to avoid 429 cascade.
"""
import os
import time
import asyncio
import pytest
import requests
import pyotp
from dotenv import load_dotenv

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://msg-hub-59.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@cpaas.io", "password": "Admin@12345"}


def _db():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c[os.environ["DB_NAME"]]


def _clear_login_attempts():
    async def go():
        db = _db()
        await db.login_attempts.delete_many({})
    asyncio.run(go())


def _reset_admin_totp():
    async def go():
        db = _db()
        await db.users.update_one(
            {"email": "admin@cpaas.io"},
            {"$set": {"totp_enabled": False},
             "$unset": {"totp_secret": "", "totp_secret_pending": ""}},
        )
    asyncio.run(go())


@pytest.fixture(autouse=True)
def _wipe_lockouts():
    _clear_login_attempts()
    yield
    _clear_login_attempts()


@pytest.fixture()
def admin_token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture()
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ───────────────────────── Brute-force lockout ─────────────────────────
class TestBruteForceLockout:
    def test_5_wrong_then_6th_returns_429(self):
        email = "admin@cpaas.io"
        # 5 wrong passwords → 401 each
        for i in range(5):
            r = requests.post(f"{API}/auth/login",
                              json={"email": email, "password": "WRONG_pw_x"},
                              timeout=15)
            assert r.status_code == 401, f"attempt {i+1} expected 401, got {r.status_code}"
        # 6th attempt → 429
        r = requests.post(f"{API}/auth/login",
                          json={"email": email, "password": "WRONG_pw_x"},
                          timeout=15)
        assert r.status_code == 429, f"6th expected 429, got {r.status_code} body={r.text}"

    def test_successful_login_clears_counter(self):
        # 4 wrong (still under threshold)
        for _ in range(4):
            requests.post(f"{API}/auth/login",
                          json={"email": "admin@cpaas.io", "password": "WRONG"}, timeout=15)
        # Correct login → success and clears
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
        assert r.status_code == 200
        # Another wrong should not 429 immediately
        r2 = requests.post(f"{API}/auth/login",
                           json={"email": "admin@cpaas.io", "password": "WRONG"}, timeout=15)
        assert r2.status_code == 401, f"counter not cleared, got {r2.status_code}"


# ───────────────────────── Forgot-password rate-limit ─────────────────────────
class TestForgotPasswordRateLimit:
    """Spec: 1 token per 60s per email. Second call within 60s should NOT insert a new row."""

    def _count_tokens(self, user_email):
        async def go():
            db = _db()
            user = await db.users.find_one({"email": user_email})
            if not user:
                return 0
            return await db.password_reset_tokens.count_documents({"user_id": user["id"]})
        return asyncio.run(go())

    def _clear_tokens(self):
        async def go():
            db = _db()
            await db.password_reset_tokens.delete_many({})
        asyncio.run(go())

    def test_second_call_within_60s_does_not_create_new_token(self):
        self._clear_tokens()
        email = "admin@cpaas.io"
        r1 = requests.post(f"{API}/auth/forgot-password", json={"email": email}, timeout=10)
        assert r1.status_code == 200
        c1 = self._count_tokens(email)
        assert c1 == 1, f"expected 1 token after first call, got {c1}"
        r2 = requests.post(f"{API}/auth/forgot-password", json={"email": email}, timeout=10)
        assert r2.status_code == 200, "second call must still return 200"
        c2 = self._count_tokens(email)
        assert c2 == 1, (f"RATE-LIMIT NOT ENFORCED: second forgot-password within 60s "
                         f"created another token (count {c1}→{c2}). Spec requires 1/60s.")
        self._clear_tokens()


# ───────────────────────── 2FA TOTP ─────────────────────────
class TestTwoFactorAuth:
    def setup_method(self):
        _reset_admin_totp()

    def teardown_method(self):
        _reset_admin_totp()

    def test_setup_returns_secret_and_qr(self, admin_headers):
        r = requests.post(f"{API}/auth/2fa/setup", headers=admin_headers, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "secret" in body and len(body["secret"]) >= 16
        assert body.get("provisioning_uri", "").startswith("otpauth://")
        qr = body.get("qr_data_uri", "")
        assert qr.startswith("data:image/svg+xml;base64,"), f"qr_data_uri prefix wrong: {qr[:60]}"

    def test_enable_with_valid_code(self, admin_headers):
        s = requests.post(f"{API}/auth/2fa/setup", headers=admin_headers, timeout=10).json()
        code = pyotp.TOTP(s["secret"]).now()
        r = requests.post(f"{API}/auth/2fa/enable", headers=admin_headers,
                          json={"code": code}, timeout=10)
        assert r.status_code == 200, r.text
        st = requests.get(f"{API}/auth/2fa/status", headers=admin_headers, timeout=10).json()
        assert st["enabled"] is True

    def test_login_otp_required_without_code(self, admin_headers):
        # enable
        s = requests.post(f"{API}/auth/2fa/setup", headers=admin_headers, timeout=10).json()
        code = pyotp.TOTP(s["secret"]).now()
        requests.post(f"{API}/auth/2fa/enable", headers=admin_headers, json={"code": code}, timeout=10)
        # login without otp
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=10)
        assert r.status_code == 200, f"got {r.status_code} body={r.text}"
        body = r.json()
        assert body.get("otp_required") is True, f"expected otp_required, got {body}"
        assert "token" not in body, "should not issue token without otp"
        # login WITH wrong otp → 401
        bad = requests.post(f"{API}/auth/login",
                            json={**ADMIN, "otp": "000000"}, timeout=10)
        assert bad.status_code == 401
        # login WITH correct otp → token
        good_code = pyotp.TOTP(s["secret"]).now()
        ok = requests.post(f"{API}/auth/login",
                           json={**ADMIN, "otp": good_code}, timeout=10)
        assert ok.status_code == 200
        assert "token" in ok.json()

    def test_disable_requires_correct_password(self, admin_headers):
        s = requests.post(f"{API}/auth/2fa/setup", headers=admin_headers, timeout=10).json()
        code = pyotp.TOTP(s["secret"]).now()
        requests.post(f"{API}/auth/2fa/enable", headers=admin_headers, json={"code": code}, timeout=10)
        bad = requests.post(f"{API}/auth/2fa/disable", headers=admin_headers,
                            json={"password": "WRONG"}, timeout=10)
        assert bad.status_code == 400
        ok = requests.post(f"{API}/auth/2fa/disable", headers=admin_headers,
                           json={"password": ADMIN["password"]}, timeout=10)
        assert ok.status_code == 200
        st = requests.get(f"{API}/auth/2fa/status", headers=admin_headers, timeout=10).json()
        assert st["enabled"] is False

    def test_status_unauth_returns_401(self):
        r = requests.get(f"{API}/auth/2fa/status", timeout=10)
        assert r.status_code in (401, 403)


# ───────────────────────── Streaming CSV exports ─────────────────────────
class TestExports:
    def test_messages_csv_streaming(self, admin_headers):
        r = requests.get(f"{API}/export/messages.csv", headers=admin_headers,
                         stream=True, timeout=20)
        assert r.status_code == 200
        ctype = r.headers.get("content-type", "")
        assert ctype.startswith("text/csv"), f"content-type={ctype}"
        disp = r.headers.get("content-disposition", "")
        assert "attachment" in disp and "messages.csv" in disp
        # first non-empty chunk should contain header
        first = next(r.iter_lines(decode_unicode=True))
        assert "created_at" in first and "channel" in first, f"header row missing: {first!r}"

    def test_invoice_csv_export(self, admin_headers):
        from datetime import datetime
        month = datetime.utcnow().strftime("%Y-%m")
        r = requests.get(f"{API}/export/invoice/{month}.csv", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("text/csv")
        body = r.text
        assert f"NSTU Invoice" in body and month in body, f"missing header line: {body[:200]}"
        # Per spec: TOTAL row at bottom
        lines = [ln for ln in body.strip().splitlines() if ln.strip()]
        assert lines[-1].startswith("TOTAL"), f"last line not TOTAL: {lines[-1]!r}"

    def test_invoice_csv_agent_forbidden(self):
        ag = requests.post(f"{API}/auth/login",
                          json={"email": "agent@cpaas.io", "password": "Agent@12345"}, timeout=10)
        assert ag.status_code == 200
        from datetime import datetime
        month = datetime.utcnow().strftime("%Y-%m")
        r = requests.get(f"{API}/export/invoice/{month}.csv",
                         headers={"Authorization": f"Bearer {ag.json()['token']}"}, timeout=10)
        assert r.status_code == 403


# ───────────────────────── Scheduler resilience ─────────────────────────
class TestSchedulerResilience:
    """Create a scheduled campaign, then delete its template before it fires.
    Expect status -> 'failed' and audit_log row action='campaign_failed'."""

    def test_campaign_failed_on_missing_template(self, admin_headers):
        # Create list
        lr = requests.post(f"{API}/lists", headers=admin_headers,
                           json={"name": "TEST_sched_fail_list", "contact_ids": []}, timeout=10)
        assert lr.status_code == 200
        list_id = lr.json()["id"]
        # Create template
        tr = requests.post(f"{API}/templates", headers=admin_headers, json={
            "name": "TEST_sched_fail_tpl", "channel": "sms",
            "body": "hi", "variables": [],
        }, timeout=10)
        assert tr.status_code == 200
        tpl_id = tr.json()["id"]
        # Schedule a campaign ~10s in the future
        from datetime import datetime, timedelta
        sched_at = (datetime.utcnow() + timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        cr = requests.post(f"{API}/campaigns", headers=admin_headers, json={
            "name": "TEST_sched_fail", "channel": "sms", "template_id": tpl_id,
            "list_ids": [list_id], "contact_ids": [], "schedule_at": sched_at,
        }, timeout=10)
        assert cr.status_code == 200
        cid = cr.json()["id"]
        # Delete the template so the scheduler hits the 'template missing' branch
        d = requests.delete(f"{API}/templates/{tpl_id}", headers=admin_headers, timeout=10)
        assert d.status_code in (200, 204)
        # Wait up to ~75s for scheduler tick (30s) + processing
        status = None
        for _ in range(75):
            time.sleep(1)
            g = requests.get(f"{API}/campaigns/{cid}", headers=admin_headers, timeout=10)
            if g.status_code == 200:
                status = g.json()["campaign"]["status"]
                if status == "failed":
                    break
        assert status == "failed", f"expected failed status, got {status}"
        # Verify audit log
        al = requests.get(f"{API}/audit-logs", headers=admin_headers,
                          params={"limit": 500}, timeout=10).json()
        items = al if isinstance(al, list) else al.get("items", [])
        actions = [r.get("action") for r in items]
        assert "campaign_failed" in actions, f"campaign_failed not in audit actions (sample): {actions[:20]}"
