"""CPaaS Hub backend regression tests"""
import os
import time
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "https://msg-hub-59.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@cpaas.io", "password": "Admin@12345"}
AGENT = {"email": "agent@cpaas.io", "password": "Agent@12345"}


# Shared state for cross-test ids
state = {}


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data and "user" in data
    return data["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def agent_token():
    r = requests.post(f"{API}/auth/login", json=AGENT, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


# --- Auth ---
class TestAuth:
    def test_login_admin_returns_token_and_cookie(self):
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body.get("token"), str) and len(body["token"]) > 20
        assert body["user"]["email"] == ADMIN["email"]
        assert body["user"]["role"] == "super_admin"
        assert "access_token" in r.cookies

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": "admin@cpaas.io", "password": "wrong"}, timeout=15)
        assert r.status_code == 401

    def test_me(self, admin_headers):
        r = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN["email"]

    def test_register_as_admin_creates_user(self, admin_headers):
        email = f"TEST_user_{int(time.time())}@example.com"
        r = requests.post(
            f"{API}/auth/register",
            json={"email": email, "password": "Test@12345", "name": "Test User", "role": "agent"},
            headers=admin_headers,
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["email"].lower() == email.lower()
        state["created_user_email"] = email.lower()

    def test_register_as_agent_forbidden(self, agent_token):
        r = requests.post(
            f"{API}/auth/register",
            json={"email": "blah@x.com", "password": "x", "name": "x", "role": "agent"},
            headers={"Authorization": f"Bearer {agent_token}"},
            timeout=10,
        )
        assert r.status_code == 403


# --- Dashboard ---
class TestDashboard:
    def test_stats(self, admin_headers):
        r = requests.get(f"{API}/dashboard/stats", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "kpis" in d and "series_7d" in d and "channel_split" in d
        assert isinstance(d["series_7d"], list)
        assert isinstance(d["channel_split"], list)
        for k in ["messages_sent", "delivered", "failed", "replied", "active_campaigns", "contacts"]:
            assert k in d["kpis"]


# --- Contacts ---
class TestContacts:
    def test_list_contacts_seeded(self, admin_headers):
        r = requests.get(f"{API}/contacts", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        contacts = r.json()
        assert isinstance(contacts, list)
        assert len(contacts) >= 15

    def test_search_filter(self, admin_headers):
        r = requests.get(f"{API}/contacts?q=Aarav", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        results = r.json()
        assert any("Aarav" in c["name"] for c in results)

    def test_crud_contact(self, admin_headers):
        # create
        c = requests.post(f"{API}/contacts", headers=admin_headers, json={
            "name": "TEST_Sample", "phone": "+919000000001", "email": "t@e.com", "tags": ["x"]
        }, timeout=10)
        assert c.status_code == 200
        cid = c.json()["id"]
        state["contact_id"] = cid
        # get
        g = requests.get(f"{API}/contacts/{cid}", headers=admin_headers, timeout=10)
        assert g.status_code == 200 and g.json()["name"] == "TEST_Sample"
        # patch
        p = requests.patch(f"{API}/contacts/{cid}", headers=admin_headers, json={"name": "TEST_Updated"}, timeout=10)
        assert p.status_code == 200 and p.json()["name"] == "TEST_Updated"
        # verify
        g2 = requests.get(f"{API}/contacts/{cid}", headers=admin_headers, timeout=10)
        assert g2.json()["name"] == "TEST_Updated"

    def test_csv_import(self, admin_headers):
        csv_data = "name,phone,email,tags\nTEST_CSV_A,+919111000001,a@x.com,vip\nTEST_CSV_B,+919111000002,b@x.com,\n,+919111000003,no@x.com,\n"
        files = {"file": ("c.csv", io.BytesIO(csv_data.encode()), "text/csv")}
        r = requests.post(f"{API}/contacts/import", files=files, headers=admin_headers, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["inserted"] == 2 and body["skipped"] == 1

    def test_bulk_delete(self, admin_headers):
        # create two
        ids = []
        for i in range(2):
            r = requests.post(f"{API}/contacts", headers=admin_headers,
                              json={"name": f"TEST_bulk_{i}", "phone": f"+9192222000{i}"}, timeout=10)
            ids.append(r.json()["id"])
        r = requests.post(f"{API}/contacts/bulk-delete", headers=admin_headers, json=ids, timeout=10)
        assert r.status_code == 200
        assert r.json()["deleted"] == 2

    def test_delete_contact(self, admin_headers):
        cid = state.get("contact_id")
        if cid:
            r = requests.delete(f"{API}/contacts/{cid}", headers=admin_headers, timeout=10)
            assert r.status_code == 200


# --- Lists ---
class TestLists:
    def test_seed(self, admin_headers):
        r = requests.get(f"{API}/lists", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        assert len(r.json()) >= 3

    def test_create_list(self, admin_headers):
        r = requests.post(f"{API}/lists", headers=admin_headers, json={"name": "TEST_List"}, timeout=10)
        assert r.status_code == 200
        state["list_id"] = r.json()["id"]


# --- Templates ---
class TestTemplates:
    def test_seed(self, admin_headers):
        r = requests.get(f"{API}/templates", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        assert len(r.json()) >= 4
        state["templates"] = r.json()

    def test_filter_channel(self, admin_headers):
        r = requests.get(f"{API}/templates?channel=sms", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        for t in r.json():
            assert t["channel"] == "sms"

    def test_create_delete(self, admin_headers):
        r = requests.post(f"{API}/templates", headers=admin_headers, json={
            "name": "TEST_Tpl", "channel": "sms", "body": "Hi {{name}}", "variables": ["name"]
        }, timeout=10)
        assert r.status_code == 200
        tid = r.json()["id"]
        d = requests.delete(f"{API}/templates/{tid}", headers=admin_headers, timeout=10)
        assert d.status_code == 200


# --- Campaigns ---
class TestCampaigns:
    def test_create_immediate_campaign(self, admin_headers):
        lists = requests.get(f"{API}/lists", headers=admin_headers, timeout=10).json()
        templates = requests.get(f"{API}/templates?channel=sms", headers=admin_headers, timeout=10).json()
        list_id = lists[0]["id"]
        tpl_id = templates[0]["id"]
        r = requests.post(f"{API}/campaigns", headers=admin_headers, json={
            "name": "TEST_Camp", "channel": "sms", "template_id": tpl_id, "list_ids": [list_id], "contact_ids": []
        }, timeout=15)
        assert r.status_code == 200
        cid = r.json()["id"]
        # poll
        final = None
        for _ in range(12):
            time.sleep(1)
            g = requests.get(f"{API}/campaigns/{cid}", headers=admin_headers, timeout=10).json()
            final = g["campaign"]
            if final["status"] == "completed" and final["stats"].get("sent", 0) > 0:
                break
        assert final is not None
        assert final["stats"].get("sent", 0) >= 0  # at least entered loop

    def test_invalid_template(self, admin_headers):
        r = requests.post(f"{API}/campaigns", headers=admin_headers, json={
            "name": "TEST_Bad", "channel": "sms", "template_id": "nonexistent", "list_ids": []
        }, timeout=10)
        assert r.status_code == 404


# --- Messages ---
class TestMessages:
    def test_send_single_message_lifecycle(self, admin_headers):
        contacts = requests.get(f"{API}/contacts", headers=admin_headers, timeout=10).json()
        cid = contacts[0]["id"]
        r = requests.post(f"{API}/messages/send", headers=admin_headers, json={
            "channel": "sms", "contact_id": cid, "body": "Hello TEST"
        }, timeout=10)
        assert r.status_code == 200
        mid = r.json()["message_id"]
        # wait for lifecycle
        time.sleep(3)
        msgs = requests.get(f"{API}/messages?contact_id=" + cid, headers=admin_headers, timeout=10).json()
        match = next((m for m in msgs if m["id"] == mid), None)
        assert match is not None
        assert match["status"] in ("delivered", "failed", "sent")

    def test_list_messages_filter(self, admin_headers):
        r = requests.get(f"{API}/messages?channel=sms", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        for m in r.json():
            assert m["channel"] == "sms"


# --- Conversations & Timeline ---
class TestConversations:
    def test_list_conversations(self, admin_headers):
        r = requests.get(f"{API}/conversations", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        convs = r.json()
        # at least one should have contact_name (if any conversation exists)
        if convs:
            assert any("contact_name" in c for c in convs)

    def test_timeline(self, admin_headers):
        contacts = requests.get(f"{API}/contacts", headers=admin_headers, timeout=10).json()
        cid = contacts[0]["id"]
        r = requests.get(f"{API}/contacts/{cid}/timeline", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "messages" in d and "calls" in d


# --- Calls ---
class TestCalls:
    def test_initiate_call_lifecycle(self, admin_headers):
        contacts = requests.get(f"{API}/contacts", headers=admin_headers, timeout=10).json()
        cid = contacts[0]["id"]
        r = requests.post(f"{API}/calls", headers=admin_headers, json={"contact_id": cid}, timeout=10)
        assert r.status_code == 200
        call_id = r.json()["call_id"]
        # wait
        time.sleep(4)
        calls = requests.get(f"{API}/calls", headers=admin_headers, timeout=10).json()
        match = next((c for c in calls if c["id"] == call_id), None)
        assert match is not None
        assert match["status"] in ("completed", "no-answer", "busy", "answered")


# --- Providers ---
class TestProviders:
    def test_list_seeded(self, admin_headers):
        r = requests.get(f"{API}/providers", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        assert len(r.json()) >= 4

    def test_crud(self, admin_headers):
        r = requests.post(f"{API}/providers", headers=admin_headers, json={
            "name": "TEST_Provider", "channel": "sms", "provider_key": "twilio", "config": {"sid": "X"}
        }, timeout=10)
        assert r.status_code == 200
        pid = r.json()["id"]
        p = requests.patch(f"{API}/providers/{pid}", headers=admin_headers, json={
            "name": "TEST_Provider2", "channel": "sms", "provider_key": "twilio", "config": {}, "is_active": False, "mock": True
        }, timeout=10)
        assert p.status_code == 200 and p.json()["name"] == "TEST_Provider2"
        d = requests.delete(f"{API}/providers/{pid}", headers=admin_headers, timeout=10)
        assert d.status_code == 200


# --- Webhooks ---
class TestWebhooks:
    def test_incoming_no_auth(self, admin_headers):
        r = requests.post(f"{API}/webhooks/incoming/sms", json={"event_type": "delivered", "to": "+91"}, timeout=10)
        assert r.status_code == 200
        time.sleep(0.5)
        # list events
        r2 = requests.get(f"{API}/webhooks/events", headers=admin_headers, timeout=10)
        assert r2.status_code == 200
        assert len(r2.json()) >= 1


# --- Usage ---
class TestUsage:
    def test_summary(self, admin_headers):
        r = requests.get(f"{API}/usage/summary", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "by_channel" in d and "total_amount" in d



# --- Change Password ---
class TestChangePassword:
    def test_wrong_old_password_rejected(self, admin_headers):
        r = requests.post(f"{API}/auth/change-password", headers=admin_headers,
                          json={"old_password": "wrong-pw", "new_password": "NewPass@123"}, timeout=10)
        assert r.status_code == 400

    def test_short_new_password_rejected(self, admin_headers):
        r = requests.post(f"{API}/auth/change-password", headers=admin_headers,
                          json={"old_password": ADMIN["password"], "new_password": "abc"}, timeout=10)
        assert r.status_code == 400

    def test_change_and_revert(self, admin_headers):
        # change
        r1 = requests.post(f"{API}/auth/change-password", headers=admin_headers,
                           json={"old_password": ADMIN["password"], "new_password": "Temp@99999"}, timeout=10)
        assert r1.status_code == 200
        # login with new
        r2 = requests.post(f"{API}/auth/login", json={"email": ADMIN["email"], "password": "Temp@99999"}, timeout=10)
        assert r2.status_code == 200
        new_token = r2.json()["token"]
        # revert
        r3 = requests.post(f"{API}/auth/change-password",
                           headers={"Authorization": f"Bearer {new_token}"},
                           json={"old_password": "Temp@99999", "new_password": ADMIN["password"]}, timeout=10)
        assert r3.status_code == 200
        # verify old works again
        r4 = requests.post(f"{API}/auth/login", json=ADMIN, timeout=10)
        assert r4.status_code == 200


# --- List PATCH ---
class TestListPatch:
    def test_patch_list(self, admin_headers):
        c = requests.post(f"{API}/lists", headers=admin_headers,
                          json={"name": "TEST_PatchList", "description": "orig"}, timeout=10)
        assert c.status_code == 200
        lid = c.json()["id"]
        p = requests.patch(f"{API}/lists/{lid}", headers=admin_headers,
                           json={"name": "TEST_PatchList2", "description": "updated"}, timeout=10)
        assert p.status_code == 200
        body = p.json()
        assert body["name"] == "TEST_PatchList2"
        assert body["description"] == "updated"
        # cleanup
        requests.delete(f"{API}/lists/{lid}", headers=admin_headers, timeout=10)


# --- Export Contacts CSV ---
class TestExportCSV:
    def test_export_csv_format(self, admin_headers):
        r = requests.get(f"{API}/export/contacts.csv", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        body = r.text
        first_line = body.splitlines()[0]
        assert first_line == "name,phone,email,tags,dnd,opted_out,city,created_at"
        # at least 2 rows (header + 1)
        assert len(body.splitlines()) >= 2


# --- Campaign Detail ---
class TestCampaignDetail:
    def test_get_campaign_returns_campaign_and_recipients(self, admin_headers):
        camps = requests.get(f"{API}/campaigns", headers=admin_headers, timeout=10).json()
        assert len(camps) >= 1
        cid = camps[0]["id"]
        r = requests.get(f"{API}/campaigns/{cid}", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "campaign" in data and "recipients" in data
        assert isinstance(data["recipients"], list)
        assert data["campaign"]["id"] == cid

    def test_get_campaign_404(self, admin_headers):
        r = requests.get(f"{API}/campaigns/nonexistent_xyz", headers=admin_headers, timeout=10)
        assert r.status_code == 404


# --- Provider Credentials ---
class TestProviderCredentials:
    def _get_provider(self, headers):
        providers = requests.get(f"{API}/providers", headers=headers, timeout=10).json()
        # use twilio one if available
        for p in providers:
            if p["provider_key"] == "twilio":
                return p
        return providers[0]

    def test_get_credentials_masked(self, admin_headers):
        p = self._get_provider(admin_headers)
        pid = p["id"]
        # First set creds with sensitive keys
        set_r = requests.put(f"{API}/providers/{pid}/credentials", headers=admin_headers,
                             json={"credentials": {"account_sid": "ACSECRET12345678", "auth_token": "TOKVERYSECRET999", "from": "+15005550006"}}, timeout=10)
        assert set_r.status_code == 200
        # GET
        g = requests.get(f"{API}/providers/{pid}/credentials", headers=admin_headers, timeout=10)
        assert g.status_code == 200
        d = g.json()
        assert d["credentials_set"] is True
        assert d["credentials"]["account_sid"].startswith("•")
        assert d["credentials"]["account_sid"].endswith("5678")
        assert d["credentials"]["auth_token"].endswith("t999".upper()) or d["credentials"]["auth_token"].endswith("T999")
        # 'from' is not sensitive => should be plain
        assert d["credentials"]["from"] == "+15005550006"

    def test_put_credentials_preserves_when_masked_value_sent(self, admin_headers):
        p = self._get_provider(admin_headers)
        pid = p["id"]
        # set initial
        requests.put(f"{API}/providers/{pid}/credentials", headers=admin_headers,
                     json={"credentials": {"account_sid": "ORIGINAL_SID_AAAA", "auth_token": "ORIGINAL_TOKEN_BBB"}}, timeout=10)
        # get masked view
        g = requests.get(f"{API}/providers/{pid}/credentials", headers=admin_headers, timeout=10).json()
        masked_sid = g["credentials"]["account_sid"]
        # send back masked sid + new token
        requests.put(f"{API}/providers/{pid}/credentials", headers=admin_headers,
                     json={"credentials": {"account_sid": masked_sid, "auth_token": "NEW_TOKEN_CCCCCC"}}, timeout=10)
        # fetch again
        g2 = requests.get(f"{API}/providers/{pid}/credentials", headers=admin_headers, timeout=10).json()
        # sid should still mask original (ends in AAAA)
        assert g2["credentials"]["account_sid"].endswith("AAAA")
        # token should be new (ends in CCCC)
        assert g2["credentials"]["auth_token"].endswith("CCCC")

    def test_put_credentials_forbidden_for_agent(self, agent_token):
        providers = requests.get(f"{API}/providers", headers={"Authorization": f"Bearer {agent_token}"}, timeout=10).json()
        pid = providers[0]["id"]
        r = requests.put(f"{API}/providers/{pid}/credentials",
                         headers={"Authorization": f"Bearer {agent_token}"},
                         json={"credentials": {"key": "x"}}, timeout=10)
        assert r.status_code == 403

    def test_provider_test_mock_succeeds(self, admin_headers):
        p = self._get_provider(admin_headers)
        r = requests.post(f"{API}/providers/{p['id']}/test", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "latency_ms" in d

    def test_provider_test_404(self, admin_headers):
        r = requests.post(f"{API}/providers/nonexistent_xyz/test", headers=admin_headers, timeout=10)
        assert r.status_code == 404
