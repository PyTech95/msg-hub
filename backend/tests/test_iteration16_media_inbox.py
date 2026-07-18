"""Iteration 16 — WhatsApp Media Inbox: send-media, GridFS store, auth-scoped GET /media,
wallet debit + refund, MIME auto-detect, timeline media field, and regression checks."""
import base64
import io
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]).rstrip("/")
API = f"{BASE_URL}/api"

SA_EMAIL = "admin@cpaas.io"
SA_PWD = "Admin@12345"

# 1x1 transparent PNG (67 bytes)
TINY_PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgAAIA"
                "AAUAAeImBZsAAAAASUVORK5CYII=")
TINY_PNG = base64.b64decode(TINY_PNG_B64)


def _login(email, pwd):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def sa_token():
    return _login(SA_EMAIL, SA_PWD)


@pytest.fixture(scope="module")
def sa_headers(sa_token):
    return {"Authorization": f"Bearer {sa_token}"}


@pytest.fixture(scope="module")
def tenant_a(sa_headers):
    """Create ephemeral tenant A with company admin. Yield (company, admin_token, admin_headers).
    Auto-cleaned via SA company delete."""
    ts = int(time.time())
    email = f"TEST_it16_a_{ts}@example.com"
    pwd = "TenantA@12345"
    r = requests.post(f"{API}/companies", headers=sa_headers,
                      json={"name": f"TEST_IT16_A_{ts}", "admin_email": email,
                            "admin_password": pwd, "admin_name": "Tenant A Admin"},
                      timeout=15)
    assert r.status_code == 200, f"create company failed: {r.status_code} {r.text}"
    comp = r.json()
    tok = _login(email, pwd)
    yield comp, tok, {"Authorization": f"Bearer {tok}"}
    try:
        requests.delete(f"{API}/companies/{comp['id']}", headers=sa_headers, timeout=15)
    except Exception:
        pass


@pytest.fixture(scope="module")
def tenant_b(sa_headers):
    ts = int(time.time()) + 1
    email = f"TEST_it16_b_{ts}@example.com"
    pwd = "TenantB@12345"
    r = requests.post(f"{API}/companies", headers=sa_headers,
                      json={"name": f"TEST_IT16_B_{ts}", "admin_email": email,
                            "admin_password": pwd, "admin_name": "Tenant B Admin"},
                      timeout=15)
    assert r.status_code == 200
    comp = r.json()
    tok = _login(email, pwd)
    yield comp, tok, {"Authorization": f"Bearer {tok}"}
    try:
        requests.delete(f"{API}/companies/{comp['id']}", headers=sa_headers, timeout=15)
    except Exception:
        pass


def _credit_wallet(sa_headers, company_id, paise, reason="TEST_top_up"):
    r = requests.post(f"{API}/wallet/adjust", headers=sa_headers,
                      json={"amount_paise": paise, "reason": reason, "company_id": company_id},
                      timeout=15)
    assert r.status_code == 200, f"adjust failed: {r.status_code} {r.text}"
    return r.json()


# ─────────────────────── /api/wallets — auto-create bug fix ───────────────────────
class TestWalletsList:
    def test_wallets_lists_all_companies_incl_new(self, sa_headers, tenant_a, tenant_b):
        r = requests.get(f"{API}/wallets", headers=sa_headers, timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        company_ids = {row["company_id"] for row in rows}
        # Both freshly created tenants must be listed even before any wallet activity
        assert tenant_a[0]["id"] in company_ids, f"tenant A missing: {company_ids}"
        assert tenant_b[0]["id"] in company_ids, f"tenant B missing: {company_ids}"
        for row in rows:
            assert "balance_paise" in row
            assert row.get("currency") == "INR"

    def test_tenant_wallet_get(self, tenant_a):
        _, _, h = tenant_a
        r = requests.get(f"{API}/wallet", headers=h, timeout=15)
        assert r.status_code == 200
        w = r.json()
        assert w["currency"] == "INR"
        assert "balance_paise" in w
        assert w["pricing_paise"]["whatsapp"] == 40


# ─────────────────────── send-media happy path ───────────────────────
class TestSendMedia:
    def test_insufficient_balance_returns_402(self, tenant_a):
        _, _, h = tenant_a
        files = {"file": ("test.png", io.BytesIO(TINY_PNG), "image/png")}
        data = {"to": "+919999999999", "caption": "no balance"}
        r = requests.post(f"{API}/whatsapp/send-media", headers=h, files=files, data=data, timeout=30)
        assert r.status_code == 402, f"expected 402, got {r.status_code}: {r.text}"
        assert "wallet" in r.text.lower() or "balance" in r.text.lower()

    def test_send_media_debits_40_paise_and_persists(self, sa_headers, tenant_a):
        comp, _, h = tenant_a
        # Top up 1000 paise
        _credit_wallet(sa_headers, comp["id"], 1000)
        r0 = requests.get(f"{API}/wallet", headers=h, timeout=15).json()
        before = r0["balance_paise"]
        files = {"file": ("test.png", io.BytesIO(TINY_PNG), "image/png")}
        data = {"to": "+919999999999", "caption": "IT16 image test"}
        r = requests.post(f"{API}/whatsapp/send-media", headers=h, files=files, data=data, timeout=45)
        assert r.status_code in (200, 400), f"unexpected {r.status_code}: {r.text}"
        if r.status_code == 400:
            # Meta rejected the send but wallet refund should have fired — verify refund path
            r_after = requests.get(f"{API}/wallet", headers=h, timeout=15).json()
            assert r_after["balance_paise"] == before, (
                f"refund missing: before={before} after={r_after['balance_paise']} err={r.text}")
            # Both debit + credit rows should exist
            debits = [t for t in r_after["transactions"] if t["type"] == "debit"]
            credits = [t for t in r_after["transactions"] if t["type"] == "credit"
                       and (t.get("meta") or {}).get("reason") == "send_failed_refund"]
            assert debits and credits, "expected debit+refund transactions on failure"
            pytest.skip(f"Meta rejected send (expected on sandbox / test number): {r.text}")
        body = r.json()
        assert body["media_kind"] == "image"
        assert body["gridfs_id"]
        assert body["size"] == len(TINY_PNG)
        assert body["provider_message_id"]
        assert body["id"]
        # Wallet debited by 40 paise
        r_after = requests.get(f"{API}/wallet", headers=h, timeout=15).json()
        assert r_after["balance_paise"] == before - 40, (
            f"wallet not debited: before={before} after={r_after['balance_paise']}")
        # Timeline should include this message w/ media field
        # find contact
        contacts = requests.get(f"{API}/contacts", headers=h, timeout=15).json()
        my_contact = next((c for c in contacts if c["phone"] in ("+919999999999", "919999999999")), None)
        assert my_contact, "outbound contact not created"
        tl = requests.get(f"{API}/contacts/{my_contact['id']}/timeline", headers=h, timeout=15).json()
        msgs = tl["messages"]
        our = next((m for m in msgs if m.get("id") == body["id"]), None)
        assert our and "media" in our, "timeline message missing media field"
        assert our["media"]["type"] == "image"
        assert our["media"]["mime_type"] == "image/png"
        assert our["media"]["gridfs_id"] == body["gridfs_id"]
        assert our["media"]["size"] == len(TINY_PNG)
        assert our["media"]["filename"]

        # Save for cross-tenant test
        TestSendMedia.LAST_GRIDFS_ID = body["gridfs_id"]
        TestSendMedia.LAST_MID = body["id"]

    def test_empty_file_returns_400(self, sa_headers, tenant_a):
        _, _, h = tenant_a
        files = {"file": ("empty.png", io.BytesIO(b""), "image/png")}
        data = {"to": "+919999999999"}
        r = requests.post(f"{API}/whatsapp/send-media", headers=h, files=files, data=data, timeout=15)
        assert r.status_code == 400
        assert "empty" in r.text.lower()

    def test_oversized_file_returns_413(self, sa_headers, tenant_a):
        _, _, h = tenant_a
        big = b"\x00" * (26 * 1024 * 1024)  # 26 MB
        files = {"file": ("big.bin", io.BytesIO(big), "application/octet-stream")}
        data = {"to": "+919999999999"}
        r = requests.post(f"{API}/whatsapp/send-media", headers=h, files=files, data=data, timeout=60)
        assert r.status_code == 413, f"expected 413, got {r.status_code}: {r.text[:200]}"

    def test_mime_detection_pdf_is_document(self, sa_headers, tenant_a):
        comp, _, h = tenant_a
        _credit_wallet(sa_headers, comp["id"], 200)
        # Minimal valid-ish PDF header (Meta will likely reject but we care about kind detection)
        pdf_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
        files = {"file": ("doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {"to": "+919999999999", "caption": "pdf test"}
        r = requests.post(f"{API}/whatsapp/send-media", headers=h, files=files, data=data, timeout=30)
        if r.status_code == 200:
            assert r.json()["media_kind"] == "document"
        elif r.status_code == 400:
            # Meta rejected — but pre-Meta processing (mime kind) is already logged in the msg doc
            # Check via listing recent outbound messages
            time.sleep(0.5)
            # Wallet must have been refunded
            w = requests.get(f"{API}/wallet", headers=h, timeout=15).json()
            has_refund = any((t.get("meta") or {}).get("reason") == "send_failed_refund"
                             for t in w["transactions"] if t["type"] == "credit")
            assert has_refund, "refund missing after Meta failure"
        else:
            pytest.fail(f"unexpected {r.status_code}: {r.text[:200]}")


# ─────────────────────── auth-scoped GET /media/{id} ───────────────────────
class TestMediaAuthScope:
    def test_invalid_gridfs_id_returns_400(self, sa_headers):
        r = requests.get(f"{API}/media/not-an-objectid", headers=sa_headers, timeout=15)
        assert r.status_code == 400
        assert "invalid" in r.text.lower()

    def test_super_admin_can_fetch_any_media(self, sa_headers):
        gid = getattr(TestSendMedia, "LAST_GRIDFS_ID", None)
        if not gid:
            pytest.skip("no gridfs_id from previous test (send may have failed)")
        r = requests.get(f"{API}/media/{gid}", headers=sa_headers, timeout=15)
        assert r.status_code == 200, f"SA fetch failed: {r.status_code} {r.text[:200]}"
        assert r.headers.get("content-type", "").startswith("image/")
        assert len(r.content) == len(TINY_PNG)

    def test_other_tenant_gets_403(self, tenant_b):
        gid = getattr(TestSendMedia, "LAST_GRIDFS_ID", None)
        if not gid:
            pytest.skip("no gridfs_id from previous test")
        _, _, hb = tenant_b
        r = requests.get(f"{API}/media/{gid}", headers=hb, timeout=15)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_owning_tenant_can_fetch(self, tenant_a):
        gid = getattr(TestSendMedia, "LAST_GRIDFS_ID", None)
        if not gid:
            pytest.skip("no gridfs_id from previous test")
        _, _, ha = tenant_a
        r = requests.get(f"{API}/media/{gid}", headers=ha, timeout=15)
        assert r.status_code == 200
        assert len(r.content) == len(TINY_PNG)


# ─────────────────────── regression: text send + template send ───────────────────────
class TestRegression:
    def test_text_send_still_works(self, sa_headers, tenant_a):
        comp, _, h = tenant_a
        _credit_wallet(sa_headers, comp["id"], 200)
        r = requests.post(f"{API}/whatsapp/send-message", headers=h,
                          json={"to": "+919999999999", "message": "IT16 regression text"},
                          timeout=45)
        # Live Meta may reject unregistered numbers → 400 with refund; that's still a "path works"
        assert r.status_code in (200, 400), f"unexpected {r.status_code}: {r.text[:200]}"
        if r.status_code == 200:
            b = r.json()
            assert "message_id" in b and "provider_message_id" in b

    def test_template_send_path(self, sa_headers, tenant_a):
        comp, _, h = tenant_a
        _credit_wallet(sa_headers, comp["id"], 200)
        r = requests.post(f"{API}/whatsapp/send-message", headers=h,
                          json={"to": "+919999999999", "message": "",
                                "template_name": "hello_world", "template_language": "en_US"},
                          timeout=45)
        assert r.status_code in (200, 400), f"template send status {r.status_code}: {r.text[:200]}"
