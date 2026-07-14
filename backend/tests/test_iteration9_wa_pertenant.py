"""
Iteration 9 — Per-tenant WhatsApp credentials tests.
Covers: GET/PUT/DELETE /api/whatsapp/config, POST /api/whatsapp/config/test,
GET/POST /api/webhook/whatsapp/{company_id}, cross-tenant isolation,
X-Hub-Signature-256 enforcement, secret masking, cascade on company delete.
"""
import os
import hmac
import json
import time
import hashlib
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://msg-hub-59.preview.emergentagent.com"
API = f"{BASE_URL}/api"

SA_EMAIL = "admin@cpaas.io"
SA_PASS = "Admin@12345"
TENANT_PW = "Test@12345"
TS = int(time.time())
A_EMAIL = f"watest_A+{TS}@test.com"
B_EMAIL = f"watest_B+{TS}@test.com"


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
def companies(sa_tok):
    h = _auth(sa_tok)
    a = requests.post(f"{API}/companies", headers=h,
                      json={"name": f"TEST_WA_A_{TS}", "admin_email": A_EMAIL,
                            "admin_password": TENANT_PW, "admin_name": "WA A"}, timeout=15)
    assert a.status_code == 200, a.text
    b = requests.post(f"{API}/companies", headers=h,
                      json={"name": f"TEST_WA_B_{TS}", "admin_email": B_EMAIL,
                            "admin_password": TENANT_PW, "admin_name": "WA B"}, timeout=15)
    assert b.status_code == 200, b.text
    ca, cb = a.json(), b.json()
    yield {"A": ca, "B": cb}
    for c in (ca, cb):
        try:
            requests.delete(f"{API}/companies/{c['id']}", headers=h, timeout=15)
        except Exception:
            pass


@pytest.fixture(scope="module")
def toks(companies):
    return {"A": _login(A_EMAIL, TENANT_PW), "B": _login(B_EMAIL, TENANT_PW)}


# ── 1. SA platform view + before-config state ────────────────────────
class TestPlatformView:
    def test_sa_get_platform_view(self, sa_tok):
        r = requests.get(f"{API}/whatsapp/config", headers=_auth(sa_tok), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "platform_env_configured" in j
        assert j["webhook_path"] == "/api/webhook/whatsapp"
        assert "tenant_count" in j and isinstance(j["tenants"], list)

    def test_company_admin_get_before_save(self, toks, companies):
        r = requests.get(f"{API}/whatsapp/config", headers=_auth(toks["A"]), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["configured"] is False
        assert j["company_id"] == companies["A"]["id"]
        assert "hint" in j


# ── 2. PUT/GET create + masking + auto verify_token ──────────────────
class TestPutAndMasking:
    def test_put_creates_config_and_returns_masked(self, toks, companies):
        r = requests.put(f"{API}/whatsapp/config", headers=_auth(toks["A"]),
                         json={"access_token": "EAAG_FAKE_TOKEN_FULL_1234",
                               "phone_number_id": "111222333444555",
                               "graph_version": "v22.0",
                               "mock": True}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["configured"] is True
        assert j["company_id"] == companies["A"]["id"]
        # raw token MUST NOT be in body
        blob = json.dumps(j)
        assert "EAAG_FAKE_TOKEN_FULL_1234" not in blob, "raw access_token leaked!"
        assert j.get("access_token_set") is True
        assert j.get("access_token_preview", "").endswith("1234")
        vt = j["verify_token"]
        assert vt.startswith("tzs_") and len(vt) > 10
        assert j["webhook_path"] == f"/api/webhook/whatsapp/{companies['A']['id']}"

    def test_get_returns_masked_only(self, toks):
        r = requests.get(f"{API}/whatsapp/config", headers=_auth(toks["A"]), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["configured"] is True
        assert "access_token" not in j or j.get("access_token") is None
        assert "app_secret" not in j or j.get("app_secret") is None
        assert j["access_token_set"] is True
        assert j["access_token_preview"].endswith("1234")

    def test_partial_update_preserves_token(self, toks):
        r = requests.put(f"{API}/whatsapp/config", headers=_auth(toks["A"]),
                         json={"phone_number_id": "999888777666555", "mock": False}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["access_token_set"] is True  # preserved
        assert j["phone_number_id"] == "999888777666555"
        assert j["mock"] is False


# ── 3. Test-connection endpoint (real Graph handshake, does not crash) ─
class TestTestConnection:
    def test_test_connection_with_fake_token(self, toks):
        r = requests.post(f"{API}/whatsapp/config/test", headers=_auth(toks["A"]), timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        # mock=False now with fake creds → live mode, ok:false
        assert j["mode"] == "live"
        assert j["ok"] is False
        assert "message" in j


# ── 4. Cross-tenant isolation ────────────────────────────────────────
class TestCrossTenantIsolation:
    def test_b_sees_own_empty_config(self, toks, companies):
        r = requests.get(f"{API}/whatsapp/config", headers=_auth(toks["B"]), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["configured"] is False
        assert j["company_id"] == companies["B"]["id"]

    def test_b_can_create_own_and_verify_tokens_differ(self, toks, companies):
        r = requests.put(f"{API}/whatsapp/config", headers=_auth(toks["B"]),
                         json={"access_token": "EAAG_B_TOKEN_XYZ", "phone_number_id": "555",
                               "app_secret": "sekretB", "mock": True}, timeout=15)
        assert r.status_code == 200
        vtb = r.json()["verify_token"]
        # A's token
        ra = requests.get(f"{API}/whatsapp/config", headers=_auth(toks["A"]), timeout=15).json()
        vta = ra["verify_token"]
        assert vta and vtb and vta != vtb


# ── 5. SA role restrictions on tenant endpoints ──────────────────────
class TestSARestrictions:
    def test_sa_put_400(self, sa_tok):
        r = requests.put(f"{API}/whatsapp/config", headers=_auth(sa_tok),
                         json={"phone_number_id": "x"}, timeout=15)
        assert r.status_code == 400

    def test_sa_test_400(self, sa_tok):
        r = requests.post(f"{API}/whatsapp/config/test", headers=_auth(sa_tok), timeout=15)
        assert r.status_code == 400

    def test_sa_delete_400(self, sa_tok):
        r = requests.delete(f"{API}/whatsapp/config", headers=_auth(sa_tok), timeout=15)
        assert r.status_code == 400


# ── 6. Tenant webhook verify + inbound ────────────────────────────────
class TestTenantWebhook:
    def test_verify_correct_token_200(self, toks, companies):
        vt = requests.get(f"{API}/whatsapp/config", headers=_auth(toks["A"]), timeout=15).json()["verify_token"]
        r = requests.get(f"{API}/webhook/whatsapp/{companies['A']['id']}",
                         params={"hub.mode": "subscribe", "hub.verify_token": vt, "hub.challenge": "xyz"},
                         timeout=15)
        assert r.status_code == 200
        assert r.text.strip() == "xyz"

    def test_verify_wrong_tenant_token_403(self, toks, companies):
        vt_b = requests.get(f"{API}/whatsapp/config", headers=_auth(toks["B"]), timeout=15).json()["verify_token"]
        r = requests.get(f"{API}/webhook/whatsapp/{companies['A']['id']}",
                         params={"hub.mode": "subscribe", "hub.verify_token": vt_b, "hub.challenge": "xyz"},
                         timeout=15)
        assert r.status_code == 403

    def test_verify_unknown_company_404(self):
        r = requests.get(f"{API}/webhook/whatsapp/nonexistent-company-xyz",
                         params={"hub.mode": "subscribe", "hub.verify_token": "any", "hub.challenge": "xyz"},
                         timeout=15)
        assert r.status_code == 404

    def test_inbound_post_unknown_company_404(self):
        r = requests.post(f"{API}/webhook/whatsapp/nonexistent-company-xyz",
                         json={"object": "whatsapp_business_account", "entry": []}, timeout=15)
        assert r.status_code == 404

    def test_inbound_post_with_signature_required(self, toks, companies):
        """Company B has app_secret set — invalid signature → 401."""
        payload = {"object": "whatsapp_business_account", "entry": []}
        raw = json.dumps(payload).encode()
        r = requests.post(f"{API}/webhook/whatsapp/{companies['B']['id']}",
                          data=raw, headers={"Content-Type": "application/json",
                                             "X-Hub-Signature-256": "sha256=deadbeef"}, timeout=15)
        assert r.status_code == 401

    def test_inbound_post_with_valid_signature_accepts(self, toks, companies):
        """Company B has app_secret=sekretB — valid signature accepted and tags company_id."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "WBA_ID",
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "contacts": [{"profile": {"name": "TestUserB"}, "wa_id": f"9199{TS}77"}],
                        "messages": [{"from": f"9199{TS}77", "id": f"wamid.TEST_B_{TS}",
                                      "timestamp": str(int(time.time())), "text": {"body": "hi B"},
                                      "type": "text"}],
                    },
                }],
            }],
        }
        raw = json.dumps(payload).encode()
        sig = "sha256=" + hmac.new(b"sekretB", raw, hashlib.sha256).hexdigest()
        r = requests.post(f"{API}/webhook/whatsapp/{companies['B']['id']}",
                          data=raw, headers={"Content-Type": "application/json",
                                             "X-Hub-Signature-256": sig}, timeout=15)
        assert r.status_code == 200, r.text
        # Verify contact tagged company_id=B (via tenant B GET contacts)
        contacts = requests.get(f"{API}/contacts", headers=_auth(toks["B"]), timeout=15).json()
        assert any(c.get("phone", "").endswith(f"{TS}77") for c in contacts), "inbound contact not scoped to B"
        # A does not see it
        contacts_a = requests.get(f"{API}/contacts", headers=_auth(toks["A"]), timeout=15).json()
        assert not any(c.get("phone", "").endswith(f"{TS}77") for c in contacts_a)

    def test_inbound_post_a_no_app_secret_accepts_without_sig(self, toks, companies):
        """Company A has no app_secret — inbound accepted without X-Hub-Signature-256."""
        # A was created without app_secret. Ensure via GET.
        cfg = requests.get(f"{API}/whatsapp/config", headers=_auth(toks["A"]), timeout=15).json()
        if cfg.get("app_secret_set"):
            pytest.skip("A ended up with app_secret; skipping unsigned test")
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "contacts": [{"profile": {"name": "TestUserA"}, "wa_id": f"9199{TS}88"}],
                        "messages": [{"from": f"9199{TS}88", "id": f"wamid.TEST_A_{TS}",
                                      "timestamp": str(int(time.time())), "text": {"body": "hi A"},
                                      "type": "text"}],
                    },
                }],
            }],
        }
        r = requests.post(f"{API}/webhook/whatsapp/{companies['A']['id']}",
                          json=payload, timeout=15)
        assert r.status_code == 200


# ── 7. Send routing uses tenant creds + msg tagged with company_id ────
class TestSendRouting:
    def test_send_uses_tenant_company_id(self, toks, companies):
        # A is mock=False with fake token → send() will attempt live Graph and fail OR mock.
        # Simplest — set mock=True on A and confirm mode=mock and msg.company_id=A.
        r = requests.put(f"{API}/whatsapp/config", headers=_auth(toks["A"]),
                         json={"mock": True}, timeout=15)
        assert r.status_code == 200
        # create contact in A
        c = requests.post(f"{API}/contacts", headers=_auth(toks["A"]),
                          json={"name": "TEST_WA_send", "phone": f"+9199{TS}66"}, timeout=15).json()
        r2 = requests.post(f"{API}/whatsapp/send-message", headers=_auth(toks["A"]),
                           json={"to": c["phone"], "message": "hello"}, timeout=15)
        assert r2.status_code == 200, r2.text
        j = r2.json()
        # Verify via listing messages — company scoping ensures msg belongs to A
        msgs = requests.get(f"{API}/messages", headers=_auth(toks["A"]), timeout=15).json()
        assert any(m.get("id") == j["message_id"] for m in msgs)
        # B does NOT see it
        msgs_b = requests.get(f"{API}/messages", headers=_auth(toks["B"]), timeout=15).json()
        assert not any(m.get("id") == j["message_id"] for m in msgs_b)


# ── 8. Legacy global webhook still works ─────────────────────────────
class TestLegacyGlobalWebhook:
    def test_global_verify_still_reachable(self):
        # Just verify endpoint exists — may 403 if env verify_token doesn't match.
        r = requests.get(f"{API}/webhook/whatsapp",
                         params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "z"},
                         timeout=15)
        assert r.status_code in (200, 403)  # 404 would mean route missing


# ── 9. DELETE + cascade on company delete ─────────────────────────────
class TestDeleteAndCascade:
    def test_delete_own_config(self, toks):
        r = requests.delete(f"{API}/whatsapp/config", headers=_auth(toks["A"]), timeout=15)
        assert r.status_code == 200
        r2 = requests.get(f"{API}/whatsapp/config", headers=_auth(toks["A"]), timeout=15)
        assert r2.json()["configured"] is False

    def test_company_delete_cascade_removes_wa_config(self, sa_tok):
        ts2 = int(time.time()) + 55
        admin = f"watest_cascade+{ts2}@test.com"
        r = requests.post(f"{API}/companies", headers=_auth(sa_tok),
                          json={"name": f"TEST_CASC_{ts2}", "admin_email": admin,
                                "admin_password": TENANT_PW}, timeout=15)
        assert r.status_code == 200
        cid = r.json()["id"]
        tok = _login(admin, TENANT_PW)
        # add wa config
        rp = requests.put(f"{API}/whatsapp/config", headers=_auth(tok),
                          json={"access_token": "T", "phone_number_id": "P", "mock": True}, timeout=15)
        assert rp.status_code == 200
        # SA view count BEFORE delete
        before = requests.get(f"{API}/whatsapp/config", headers=_auth(sa_tok), timeout=15).json()["tenant_count"]
        # delete company
        rd = requests.delete(f"{API}/companies/{cid}", headers=_auth(sa_tok), timeout=15)
        assert rd.status_code == 200
        after = requests.get(f"{API}/whatsapp/config", headers=_auth(sa_tok), timeout=15).json()
        assert after["tenant_count"] == before - 1, f"cascade did not delete wa config: before={before} after={after['tenant_count']}"
        assert not any(t["company_id"] == cid for t in after["tenants"])
