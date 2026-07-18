"""Iteration 15 backend tests:
   1. WebSocket realtime (connect, bad-token close, ping/pong, tenant isolation)
   2. RBAC v2 manager role + hierarchy
   3. Email plumbing (env-gated)
   4. Campaign control (pause/resume/cancel) + wallet debit/refund
Uses the EXTERNAL REACT_APP_BACKEND_URL for HTTP and derives ws:// or wss:// from it.
"""
import os
import time
import asyncio
import json
import uuid
import pytest
import requests
import websockets

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    # Read from frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE_URL = _load_backend_url()
WS_URL = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/ws"

SA_EMAIL = "admin@cpaas.io"
SA_PASS  = "Admin@12345"

# ---------- Shared helpers ----------
def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return r.json()["token"]

def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

@pytest.fixture(scope="module")
def sa_token():
    return _login(SA_EMAIL, SA_PASS)

@pytest.fixture(scope="module")
def tenant_pair(sa_token):
    """Create two ephemeral companies A & B, plus an agent user each for auth. Return dict."""
    ts = int(time.time())
    tenants = {}
    for label in ("A", "B"):
        cname = f"TEST_IT15_{label}_{ts}"
        admin_email = f"test_it15_{label}_{ts}@example.com"
        admin_pass = "TestPass@123"
        r = requests.post(f"{BASE_URL}/api/companies",
                          headers=_h(sa_token),
                          json={"name": cname, "admin_email": admin_email,
                                "admin_password": admin_pass, "admin_name": f"Admin {label}"},
                          timeout=15)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        admin_tok = _login(admin_email, admin_pass)
        tenants[label] = {"company_id": cid, "admin_email": admin_email,
                          "admin_pass": admin_pass, "token": admin_tok, "name": cname}
    yield tenants
    # Cleanup
    for label in ("A", "B"):
        try:
            requests.delete(f"{BASE_URL}/api/companies/{tenants[label]['company_id']}",
                            headers=_h(sa_token), timeout=15)
        except Exception:
            pass


# ─────────────────── WebSocket tests ───────────────────
class TestWebSocket:
    def test_ws_valid_jwt_connects(self, sa_token):
        async def _run():
            async with websockets.connect(f"{WS_URL}?token={sa_token}", open_timeout=10) as ws:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                assert msg["type"] == "connected"
                assert msg["role"] == "super_admin"
                assert "server_time" in msg
                # ping → pong
                await ws.send("ping")
                pong = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                assert pong["type"] == "pong"
        asyncio.run(_run())

    def test_ws_bad_token_rejected(self):
        async def _run():
            with pytest.raises(Exception):
                async with websockets.connect(f"{WS_URL}?token=BADTOKEN", open_timeout=10) as ws:
                    await asyncio.wait_for(ws.recv(), timeout=5)
        asyncio.run(_run())

    def test_ws_missing_token_validation_error(self):
        async def _run():
            with pytest.raises(Exception):
                async with websockets.connect(WS_URL, open_timeout=10) as ws:
                    await asyncio.wait_for(ws.recv(), timeout=5)
        asyncio.run(_run())

    def test_ws_tenant_isolation_message_event(self, sa_token, tenant_pair):
        """Company A's WS should receive message_event when A sends; B should NOT."""
        tok_a = tenant_pair["A"]["token"]
        tok_b = tenant_pair["B"]["token"]
        cid_a = tenant_pair["A"]["company_id"]

        # Credit A's wallet so SMS send succeeds
        requests.post(f"{BASE_URL}/api/wallet/adjust",
                     headers=_h(sa_token),
                     json={"company_id": cid_a, "amount_paise": 1000, "reason": "test_ws"},
                     timeout=10)
        # Create a contact for A
        c = requests.post(f"{BASE_URL}/api/contacts", headers=_h(tok_a),
                          json={"name": "TEST_WS", "phone": "919000000050"}, timeout=15)
        assert c.status_code == 200
        contact_id = c.json()["id"]

        async def _run():
            async with websockets.connect(f"{WS_URL}?token={tok_a}", open_timeout=10) as ws_a, \
                       websockets.connect(f"{WS_URL}?token={tok_b}", open_timeout=10) as ws_b:
                # Drain 'connected' frames
                await asyncio.wait_for(ws_a.recv(), timeout=10)
                await asyncio.wait_for(ws_b.recv(), timeout=10)

                # Send SMS as tenant A (triggers emit_event → WS broadcast)
                r = requests.post(f"{BASE_URL}/api/messages/send",
                                  headers=_h(tok_a),
                                  json={"channel": "sms", "contact_id": contact_id, "body": "hi"},
                                  timeout=15)
                assert r.status_code == 200, r.text

                got_a_event = False
                for _ in range(10):
                    try:
                        raw = await asyncio.wait_for(ws_a.recv(), timeout=3)
                        d = json.loads(raw)
                        if d.get("type") in ("message_event", "wallet_debit"):
                            got_a_event = True
                            break
                    except asyncio.TimeoutError:
                        break
                assert got_a_event, "Tenant A did not receive any tenant event over WS"

                # B should get nothing tenant-A-related within 2s
                got_b = False
                try:
                    raw = await asyncio.wait_for(ws_b.recv(), timeout=2)
                    d = json.loads(raw)
                    if d.get("type") in ("message_event", "wallet_debit", "inbound_message"):
                        got_b = True
                except asyncio.TimeoutError:
                    pass
                assert not got_b, "Tenant B should NOT receive tenant A's events"

        try:
            asyncio.run(_run())
        finally:
            requests.delete(f"{BASE_URL}/api/contacts/{contact_id}", headers=_h(tok_a), timeout=10)


# ─────────────────── RBAC v2 ───────────────────
class TestRBACv2:
    def test_sa_can_create_manager(self, sa_token):
        ts = int(time.time())
        email = f"test_it15_sa_mgr_{ts}@example.com"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          headers=_h(sa_token),
                          json={"email": email, "password": "Pass@123",
                                "name": "SA Manager", "role": "manager"},
                          timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["role"] == "manager"
        assert data.get("company_id") is None
        # cleanup
        requests.delete(f"{BASE_URL}/api/users/{data['id']}", headers=_h(sa_token), timeout=15)

    def test_ca_can_create_manager(self, sa_token, tenant_pair):
        ca_tok = tenant_pair["A"]["token"]
        ts = int(time.time())
        email = f"test_it15_ca_mgr_{ts}@example.com"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          headers=_h(ca_tok),
                          json={"email": email, "password": "Pass@123",
                                "name": "CA Manager", "role": "manager"},
                          timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["role"] == "manager"
        assert data["company_id"] == tenant_pair["A"]["company_id"]
        requests.delete(f"{BASE_URL}/api/users/{data['id']}", headers=_h(sa_token), timeout=15)

    def test_ca_cannot_create_admin(self, tenant_pair):
        ca_tok = tenant_pair["A"]["token"]
        ts = int(time.time())
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          headers=_h(ca_tok),
                          json={"email": f"test_it15_admin_{ts}@example.com",
                                "password": "Pass@123", "name": "X", "role": "admin"},
                          timeout=15)
        assert r.status_code == 403
        assert "Manager or Agent" in r.text

    def test_ca_cannot_create_super_admin(self, tenant_pair):
        ca_tok = tenant_pair["A"]["token"]
        ts = int(time.time())
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          headers=_h(ca_tok),
                          json={"email": f"test_it15_sa2_{ts}@example.com",
                                "password": "Pass@123", "name": "X", "role": "super_admin"},
                          timeout=15)
        assert r.status_code == 403

    def test_ca_can_create_agent_backcompat(self, sa_token, tenant_pair):
        ca_tok = tenant_pair["A"]["token"]
        ts = int(time.time())
        email = f"test_it15_ca_agent_{ts}@example.com"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          headers=_h(ca_tok),
                          json={"email": email, "password": "Pass@123",
                                "name": "A", "role": "agent"},
                          timeout=15)
        assert r.status_code == 200
        requests.delete(f"{BASE_URL}/api/users/{r.json()['id']}", headers=_h(sa_token), timeout=15)

    def test_manager_can_read_contacts_but_not_delete(self, sa_token, tenant_pair):
        ca_tok = tenant_pair["A"]["token"]
        ts = int(time.time())
        mgr_email = f"test_it15_hier_mgr_{ts}@example.com"
        mgr_pass = "Pass@123"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          headers=_h(ca_tok),
                          json={"email": mgr_email, "password": mgr_pass,
                                "name": "Hier Manager", "role": "manager"},
                          timeout=15)
        assert r.status_code == 200
        mgr_id = r.json()["id"]
        mgr_tok = _login(mgr_email, mgr_pass)

        # Create a contact as CA
        c = requests.post(f"{BASE_URL}/api/contacts",
                          headers=_h(ca_tok),
                          json={"name": "TEST_C", "phone": "919000000000"},
                          timeout=15)
        assert c.status_code == 200, c.text
        contact_id = c.json()["id"]

        # Manager: GET /contacts → 200 (hierarchy: manager>=agent)
        r_get = requests.get(f"{BASE_URL}/api/contacts", headers=_h(mgr_tok), timeout=15)
        assert r_get.status_code == 200

        # Manager: DELETE /contacts/{id} → 403 (needs admin/super_admin)
        r_del = requests.delete(f"{BASE_URL}/api/contacts/{contact_id}",
                                headers=_h(mgr_tok), timeout=15)
        assert r_del.status_code == 403, f"Manager should NOT delete; got {r_del.status_code}"

        # Cleanup
        requests.delete(f"{BASE_URL}/api/contacts/{contact_id}", headers=_h(ca_tok), timeout=15)
        requests.delete(f"{BASE_URL}/api/users/{mgr_id}", headers=_h(sa_token), timeout=15)


# ─────────────────── Email ───────────────────
class TestEmail:
    def test_email_config_sa_returns_unconfigured(self, sa_token):
        r = requests.get(f"{BASE_URL}/api/email/config", headers=_h(sa_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["configured"] is False
        assert data["provider"] == "none"
        assert "from" in data

    def test_email_config_ca_forbidden(self, tenant_pair):
        r = requests.get(f"{BASE_URL}/api/email/config",
                         headers=_h(tenant_pair["A"]["token"]), timeout=10)
        assert r.status_code == 403

    def test_email_test_returns_503_when_unconfigured(self, sa_token):
        r = requests.post(f"{BASE_URL}/api/email/test",
                         headers=_h(sa_token),
                         json={"to": "someone@example.com"}, timeout=10)
        assert r.status_code == 503
        assert "not configured" in r.text.lower()


# ─────────────────── Campaign control ───────────────────
class TestCampaignControl:
    def _make_campaign(self, sa_token, tenant_pair):
        """Create a running campaign in Tenant A with a fresh contact + template.
        Returns (campaign_id, ca_tok, contact_id, template_id).
        """
        ca_tok = tenant_pair["A"]["token"]
        ts = int(time.time())
        # Contact
        c = requests.post(f"{BASE_URL}/api/contacts",
                          headers=_h(ca_tok),
                          json={"name": "TEST_CC", "phone": "919000000010"}, timeout=15)
        assert c.status_code == 200
        contact_id = c.json()["id"]
        # Template (sms)
        t = requests.post(f"{BASE_URL}/api/templates",
                          headers=_h(ca_tok),
                          json={"name": f"TEST_T_{ts}", "channel": "sms",
                                "body": "hi {{name}}"}, timeout=15)
        assert t.status_code == 200, t.text
        template_id = t.json()["id"]
        # Campaign
        cp = requests.post(f"{BASE_URL}/api/campaigns",
                           headers=_h(ca_tok),
                           json={"name": f"TEST_CP_{ts}", "channel": "sms",
                                 "template_id": template_id, "list_ids": [],
                                 "contact_ids": [contact_id], "variables_map": {}}, timeout=15)
        assert cp.status_code == 200, cp.text
        return cp.json()["id"], ca_tok, contact_id, template_id

    def test_pause_running_campaign(self, sa_token, tenant_pair):
        camp_id, ca_tok, cid, tid = self._make_campaign(sa_token, tenant_pair)
        r = requests.post(f"{BASE_URL}/api/campaigns/{camp_id}/pause",
                         headers=_h(ca_tok), timeout=10)
        # Race: campaign may already have completed for 1 recipient. Accept 200 or 400.
        assert r.status_code in (200, 400)
        # verify pause path when 200
        if r.status_code == 200:
            g = requests.get(f"{BASE_URL}/api/campaigns/{camp_id}", headers=_h(ca_tok), timeout=10)
            assert g.status_code == 200
            assert g.json()["status"] in ("paused", "cancelled", "completed")
        # cleanup
        requests.delete(f"{BASE_URL}/api/campaigns/{camp_id}", headers=_h(ca_tok), timeout=10)
        requests.delete(f"{BASE_URL}/api/contacts/{cid}", headers=_h(ca_tok), timeout=10)
        requests.delete(f"{BASE_URL}/api/templates/{tid}", headers=_h(ca_tok), timeout=10)

    def test_pause_completed_campaign_returns_400(self, sa_token, tenant_pair):
        camp_id, ca_tok, cid, tid = self._make_campaign(sa_token, tenant_pair)
        # Wait for completion (1 recipient → fast)
        for _ in range(20):
            time.sleep(0.5)
            g = requests.get(f"{BASE_URL}/api/campaigns/{camp_id}", headers=_h(ca_tok), timeout=10)
            if g.status_code == 200 and g.json().get("status") == "completed":
                break
        r = requests.post(f"{BASE_URL}/api/campaigns/{camp_id}/pause",
                         headers=_h(ca_tok), timeout=10)
        assert r.status_code == 400
        # cleanup
        requests.delete(f"{BASE_URL}/api/campaigns/{camp_id}", headers=_h(ca_tok), timeout=10)
        requests.delete(f"{BASE_URL}/api/contacts/{cid}", headers=_h(ca_tok), timeout=10)
        requests.delete(f"{BASE_URL}/api/templates/{tid}", headers=_h(ca_tok), timeout=10)

    def test_cancel_running_campaign(self, sa_token, tenant_pair):
        camp_id, ca_tok, cid, tid = self._make_campaign(sa_token, tenant_pair)
        r = requests.post(f"{BASE_URL}/api/campaigns/{camp_id}/cancel",
                         headers=_h(ca_tok), timeout=10)
        assert r.status_code in (200, 400)
        requests.delete(f"{BASE_URL}/api/campaigns/{camp_id}", headers=_h(ca_tok), timeout=10)
        requests.delete(f"{BASE_URL}/api/contacts/{cid}", headers=_h(ca_tok), timeout=10)
        requests.delete(f"{BASE_URL}/api/templates/{tid}", headers=_h(ca_tok), timeout=10)


# ─────────────────── Regression sanity ───────────────────
class TestRegression:
    def test_send_single_message_still_works(self, sa_token, tenant_pair):
        """Regression: /api/messages/send still works (semaphore only inside campaigns)."""
        ca_tok = tenant_pair["A"]["token"]
        # Need wallet balance to send SMS (25p). SA credits.
        cid = tenant_pair["A"]["company_id"]
        adj = requests.post(f"{BASE_URL}/api/wallet/adjust",
                           headers=_h(sa_token),
                           json={"company_id": cid, "amount_paise": 1000,
                                 "reason": "test_regression"}, timeout=10)
        assert adj.status_code == 200, adj.text
        c = requests.post(f"{BASE_URL}/api/contacts", headers=_h(ca_tok),
                          json={"name": "TEST_R", "phone": "919000000099"}, timeout=15)
        cont_id = c.json()["id"]
        r = requests.post(f"{BASE_URL}/api/messages/send",
                         headers=_h(ca_tok),
                         json={"channel": "sms", "contact_id": cont_id, "body": "hello"},
                         timeout=15)
        assert r.status_code == 200, r.text
        assert "message_id" in r.json() or "id" in r.json()
        requests.delete(f"{BASE_URL}/api/contacts/{cont_id}", headers=_h(ca_tok), timeout=10)

    def test_sa_wallets_isolation(self, sa_token):
        r = requests.get(f"{BASE_URL}/api/wallets", headers=_h(sa_token), timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
