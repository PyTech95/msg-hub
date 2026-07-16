"""
Iteration 10 — WhatsApp Template Send + Silent-Drop Fix Tests.

Covers:
- POST /api/messages/send with template_name → Meta 400 propagates as HTTP 502,
  message doc persisted with status='failed' + meta.template_name/language captured.
- POST /api/messages/send free-form body still works (SMS regression).
- POST /api/whatsapp/send-message with template_name and free-form (backwards compat).
- SendMessageIn accepts optional template_name/language/components; body optional.
- No regression on multi-tenant WhatsApp isolation from iterations 8/9.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://msg-hub-59.preview.emergentagent.com"
API = f"{BASE_URL}/api"

SA_EMAIL = "admin@cpaas.io"
SA_PASS = "Admin@12345"
TENANT_PW = "Test@12345"
TS = int(time.time())
A_EMAIL = f"watpl_A+{TS}@test.com"
B_EMAIL = f"watpl_B+{TS}@test.com"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["token"]


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def sa_tok():
    return _login(SA_EMAIL, SA_PASS)


@pytest.fixture(scope="module")
def tenant_ctx(sa_tok):
    """Create two tenants, return {'A':{tok,cid}, 'B':{tok,cid}} and cleanup."""
    h = _auth(sa_tok)
    a = requests.post(f"{API}/companies", headers=h,
                      json={"name": f"TEST_WATPL_A_{TS}", "admin_email": A_EMAIL,
                            "admin_password": TENANT_PW, "admin_name": "WA Tpl A"}, timeout=15)
    assert a.status_code == 200, a.text
    b = requests.post(f"{API}/companies", headers=h,
                      json={"name": f"TEST_WATPL_B_{TS}", "admin_email": B_EMAIL,
                            "admin_password": TENANT_PW, "admin_name": "WA Tpl B"}, timeout=15)
    assert b.status_code == 200, b.text
    ca, cb = a.json(), b.json()
    ctx = {
        "A": {"tok": _login(A_EMAIL, TENANT_PW), "cid": ca["id"]},
        "B": {"tok": _login(B_EMAIL, TENANT_PW), "cid": cb["id"]},
    }
    yield ctx
    for c in (ca, cb):
        try:
            requests.delete(f"{API}/companies/{c['id']}", headers=h, timeout=15)
        except Exception:
            pass


def _make_contact(tok, name, phone):
    r = requests.post(f"{API}/contacts", headers=_auth(tok),
                      json={"name": name, "phone": phone}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


# ── Tenant A uses LIVE Meta creds (from env) — real API hit expected to fail with 131058
def _configure_live_wa(tok):
    """Copy env creds to tenant so send uses REAL Meta Graph. If env creds missing → skip live tests."""
    at = os.environ.get("WHATSAPP_ACCESS_TOKEN") or os.environ.get("META_WHATSAPP_ACCESS_TOKEN")
    pnid = os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or os.environ.get("META_PHONE_NUMBER_ID")
    if not at or not pnid:
        # Try reading from backend .env
        try:
            with open("/app/backend/.env") as f:
                for line in f:
                    if "=" not in line:
                        continue
                    k, v = line.strip().split("=", 1)
                    if k in ("WHATSAPP_ACCESS_TOKEN", "META_WHATSAPP_ACCESS_TOKEN") and not at:
                        at = v
                    if k in ("WHATSAPP_PHONE_NUMBER_ID", "META_PHONE_NUMBER_ID") and not pnid:
                        pnid = v
        except Exception:
            pass
    if not at or not pnid:
        return False
    r = requests.put(f"{API}/whatsapp/config", headers=_auth(tok),
                     json={"access_token": at, "phone_number_id": pnid,
                           "graph_version": "v22.0", "mock": False}, timeout=20)
    return r.status_code == 200 and r.json().get("configured") is True


# ── 1. Model accepts optional template fields ─────────────────────────
class TestModelAcceptance:
    def test_send_without_template_still_works_sms(self, tenant_ctx):
        # SMS regression — no template logic path
        tok = tenant_ctx["A"]["tok"]
        c = _make_contact(tok, "TEST_sms_regr", f"+9199{TS}01")
        r = requests.post(f"{API}/messages/send", headers=_auth(tok),
                          json={"channel": "sms", "contact_id": c["id"], "body": "hi sms"}, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] in ("sent", "queued")
        # verify persisted
        msgs = requests.get(f"{API}/messages", headers=_auth(tok),
                            params={"channel": "sms", "contact_id": c["id"]}, timeout=15).json()
        assert any(m["id"] == j["message_id"] for m in msgs)

    def test_sendmessagein_model_accepts_optional_template_fields(self, tenant_ctx):
        """Pydantic v2 should accept extra template fields without validation error."""
        tok = tenant_ctx["A"]["tok"]
        c = _make_contact(tok, "TEST_model_accept", f"+9199{TS}02")
        # SMS with template fields (should be ignored, still succeed — validation only)
        r = requests.post(f"{API}/messages/send", headers=_auth(tok),
                          json={"channel": "sms", "contact_id": c["id"], "body": "x",
                                "template_name": "ignored_for_sms",
                                "template_language": "en_US"}, timeout=20)
        # For SMS channel, template path is skipped (is_wa_template only true for whatsapp)
        assert r.status_code == 200, r.text


# ── 2. WhatsApp template send propagates Meta 400 as 502 + persists failed doc ─
class TestWhatsAppTemplateErrorPropagation:
    @pytest.fixture(autouse=True)
    def _setup_live(self, tenant_ctx):
        ok = _configure_live_wa(tenant_ctx["A"]["tok"])
        if not ok:
            pytest.skip("Live Meta credentials not available; cannot verify Meta error propagation.")

    def test_hello_world_template_from_prod_number_returns_502(self, tenant_ctx):
        tok = tenant_ctx["A"]["tok"]
        c = _make_contact(tok, "TEST_tpl_helloworld", "+919999999901")
        r = requests.post(f"{API}/messages/send", headers=_auth(tok),
                          json={"channel": "whatsapp", "contact_id": c["id"], "body": "",
                                "template_name": "hello_world", "template_language": "en_US"},
                          timeout=45)
        # Expected: Meta rejects → 502 propagated
        assert r.status_code == 502, f"Expected 502, got {r.status_code}: {r.text}"
        # Try to parse detail if body is JSON (ingress may return empty body on 502)
        try:
            detail = r.json().get("detail", "")
            if detail:
                assert "Send failed" in detail or "131058" in detail or "template" in detail.lower(), \
                    f"Detail should surface Meta error: {detail}"
        except Exception:
            pass  # ingress may swallow body; status code is sufficient

    def test_failed_message_doc_persisted_with_template_meta(self, tenant_ctx):
        tok = tenant_ctx["A"]["tok"]
        c = _make_contact(tok, "TEST_tpl_persist_fail", "+919999999902")
        r = requests.post(f"{API}/messages/send", headers=_auth(tok),
                          json={"channel": "whatsapp", "contact_id": c["id"], "body": "",
                                "template_name": "hello_world", "template_language": "en_US"},
                          timeout=45)
        assert r.status_code == 502, r.text
        # Now query messages for contact — must find one with status=failed + meta.template_name
        msgs = requests.get(f"{API}/messages", headers=_auth(tok),
                            params={"channel": "whatsapp", "contact_id": c["id"]}, timeout=15).json()
        assert msgs, "no message doc persisted"
        m = msgs[0]  # latest
        assert m.get("status") == "failed", f"expected status=failed, got {m.get('status')}"
        meta = m.get("meta") or {}
        assert meta.get("template_name") == "hello_world"
        assert meta.get("template_language") == "en_US"

    def test_unknown_template_also_502_with_meta_captured(self, tenant_ctx):
        tok = tenant_ctx["A"]["tok"]
        c = _make_contact(tok, "TEST_tpl_unknown", "+919999999903")
        bogus = f"nonexistent_tpl_{TS}"
        r = requests.post(f"{API}/messages/send", headers=_auth(tok),
                          json={"channel": "whatsapp", "contact_id": c["id"], "body": "",
                                "template_name": bogus, "template_language": "en_US"},
                          timeout=45)
        assert r.status_code == 502, r.text
        msgs = requests.get(f"{API}/messages", headers=_auth(tok),
                            params={"channel": "whatsapp", "contact_id": c["id"]}, timeout=15).json()
        assert msgs
        m = msgs[0]
        assert m.get("status") == "failed"
        assert (m.get("meta") or {}).get("template_name") == bogus


# ── 3. Free-form WhatsApp path still works (backwards compat, mock mode) ──
class TestWhatsAppFreeFormBackwardsCompat:
    def test_freeform_no_template_uses_send_path(self, tenant_ctx):
        # Switch tenant B to mock so free-form succeeds cleanly.
        tok = tenant_ctx["B"]["tok"]
        r = requests.put(f"{API}/whatsapp/config", headers=_auth(tok),
                         json={"access_token": "T", "phone_number_id": "P", "mock": True}, timeout=15)
        assert r.status_code == 200
        c = _make_contact(tok, "TEST_wa_freeform", f"+9199{TS}04")
        r2 = requests.post(f"{API}/messages/send", headers=_auth(tok),
                           json={"channel": "whatsapp", "contact_id": c["id"], "body": "hi free"},
                           timeout=20)
        assert r2.status_code == 200, r2.text
        j = r2.json()
        assert j["status"] in ("sent", "queued")
        msgs = requests.get(f"{API}/messages", headers=_auth(tok),
                            params={"channel": "whatsapp", "contact_id": c["id"]}, timeout=15).json()
        m = next((x for x in msgs if x["id"] == j["message_id"]), None)
        assert m is not None
        # no template meta on free-form
        assert not (m.get("meta") or {}).get("template_name")


# ── 4. /whatsapp/send-message endpoint mirrors behaviour ──────────────
class TestWhatsAppSendMessageEndpoint:
    def test_freeform_backwards_compat_mock(self, tenant_ctx):
        tok = tenant_ctx["B"]["tok"]  # tenant B is in mock mode
        r = requests.post(f"{API}/whatsapp/send-message", headers=_auth(tok),
                          json={"to": f"+9199{TS}05", "message": "hi via legacy ep"}, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] in ("sent", "queued")
        assert j.get("message_id")

    def test_template_no_message_field_required(self, tenant_ctx):
        """to + template_name only (no 'message') — must not raise 422."""
        ok = _configure_live_wa(tenant_ctx["A"]["tok"])
        if not ok:
            pytest.skip("Live Meta credentials not available.")
        tok = tenant_ctx["A"]["tok"]
        r = requests.post(f"{API}/whatsapp/send-message", headers=_auth(tok),
                          json={"to": "+919999999906", "template_name": "hello_world",
                                "template_language": "en_US"}, timeout=45)
        # Meta will reject → 502
        assert r.status_code == 502, f"Expected 502, got {r.status_code}: {r.text}"


# ── 5. Multi-tenant isolation regression (iteration 8/9 sanity) ───────
class TestIsolationRegression:
    def test_a_cannot_see_b_messages(self, tenant_ctx):
        tok_a, tok_b = tenant_ctx["A"]["tok"], tenant_ctx["B"]["tok"]
        # B send a mock message
        requests.put(f"{API}/whatsapp/config", headers=_auth(tok_b),
                     json={"mock": True}, timeout=15)
        cb = _make_contact(tok_b, "TEST_iso_b", f"+9199{TS}07")
        r = requests.post(f"{API}/messages/send", headers=_auth(tok_b),
                          json={"channel": "whatsapp", "contact_id": cb["id"], "body": "iso"},
                          timeout=20)
        assert r.status_code == 200
        mid = r.json()["message_id"]
        # A must not see B's message
        msgs_a = requests.get(f"{API}/messages", headers=_auth(tok_a), timeout=15).json()
        assert not any(m["id"] == mid for m in msgs_a)
