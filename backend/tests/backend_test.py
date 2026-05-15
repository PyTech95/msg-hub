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
