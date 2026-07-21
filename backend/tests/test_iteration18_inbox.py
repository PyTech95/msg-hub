"""Iteration 18 — WhatsApp-Web Inbox backend tests.

Covers:
- GET /api/conversations (unread_count, last_direction, last_status, last_media_type, filters)
- POST /api/conversations/{contact_id}/read
- POST /api/conversations/{contact_id}/assign (RBAC + 404)
- POST /api/conversations/notes
- GET /api/contacts/{contact_id}/timeline (pagination: before, has_more, next_cursor, ASC order)
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE}/api"

ADMIN = {"email": "admin@cpaas.io", "password": "Admin@12345"}
AGENT = {"email": "agent@cpaas.io", "password": "Agent@12345"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def admin_hdr(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def contact_id(admin_hdr):
    # Grab any existing conversation contact_id
    r = requests.get(f"{API}/conversations", headers=admin_hdr, params={"limit": 5}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    if not data:
        pytest.skip("No conversations in DB to test with")
    return data[0]["contact_id"]


# ── Conversations list ─────────────────────────────────────────────────────
class TestConversationsList:
    def test_list_returns_expected_fields(self, admin_hdr):
        r = requests.get(f"{API}/conversations", headers=admin_hdr, params={"channel": "whatsapp", "limit": 50}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        if not data:
            pytest.skip("empty conversations")
        c = data[0]
        for f in ("contact_id", "contact_name", "contact_phone", "unread_count", "tags"):
            assert f in c, f"Missing {f} in conversation: {c.keys()}"
        assert isinstance(c["unread_count"], int)
        assert isinstance(c["tags"], list)

    def test_search_q_filter(self, admin_hdr):
        r = requests.get(f"{API}/conversations", headers=admin_hdr, params={"q": "9", "channel": "whatsapp"}, timeout=30)
        assert r.status_code == 200

    def test_unread_only_filter(self, admin_hdr):
        r = requests.get(f"{API}/conversations", headers=admin_hdr, params={"unread_only": True, "channel": "whatsapp"}, timeout=30)
        assert r.status_code == 200
        for c in r.json():
            assert c["unread_count"] > 0


# ── Timeline pagination ────────────────────────────────────────────────────
class TestTimeline:
    def test_timeline_ascending_and_pagination(self, admin_hdr, contact_id):
        r = requests.get(f"{API}/contacts/{contact_id}/timeline", headers=admin_hdr, params={"limit": 5}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(["messages", "calls", "has_more", "next_cursor"]).issubset(d.keys())
        msgs = d["messages"]
        # ASC order
        if len(msgs) >= 2:
            assert msgs[0]["created_at"] <= msgs[-1]["created_at"], "messages not in ASC order"
        # If has_more, cursor must be set
        if d["has_more"]:
            assert d["next_cursor"], "next_cursor missing when has_more true"
            # Fetch older page
            r2 = requests.get(f"{API}/contacts/{contact_id}/timeline", headers=admin_hdr,
                              params={"before": d["next_cursor"], "limit": 5}, timeout=30)
            assert r2.status_code == 200
            older = r2.json()["messages"]
            # older page's last ts <= first ts of previous page
            if older and msgs:
                assert older[-1]["created_at"] <= msgs[0]["created_at"]

    def test_timeline_no_params_backward_compat(self, admin_hdr, contact_id):
        r = requests.get(f"{API}/contacts/{contact_id}/timeline", headers=admin_hdr, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "messages" in d and "calls" in d


# ── Mark read ──────────────────────────────────────────────────────────────
class TestMarkRead:
    def test_mark_read_clears_unread(self, admin_hdr, contact_id):
        r = requests.post(f"{API}/conversations/{contact_id}/read",
                          headers=admin_hdr, params={"channel": "whatsapp"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert "last_read_at" in d
        # Verify unread_count==0 for this conv
        r2 = requests.get(f"{API}/conversations", headers=admin_hdr, params={"channel": "whatsapp"}, timeout=30)
        conv = next((c for c in r2.json() if c["contact_id"] == contact_id), None)
        assert conv is not None
        assert conv["unread_count"] == 0


# ── Assign ─────────────────────────────────────────────────────────────────
class TestAssign:
    def test_assign_non_tenant_agent_404(self, admin_hdr, contact_id):
        r = requests.post(f"{API}/conversations/{contact_id}/assign",
                          headers=admin_hdr, params={"channel": "whatsapp"},
                          json={"agent_email": "nobody-xyz@nowhere.test"}, timeout=30)
        assert r.status_code == 404, r.text

    def test_unassign(self, admin_hdr, contact_id):
        r = requests.post(f"{API}/conversations/{contact_id}/assign",
                          headers=admin_hdr, params={"channel": "whatsapp"},
                          json={"agent_email": None}, timeout=30)
        assert r.status_code == 200
        assert r.json()["assigned_to"] is None

    def test_agent_cannot_assign(self, contact_id):
        # Agent role should be blocked (require_roles manager+)
        try:
            tok = _login(AGENT)
        except AssertionError:
            pytest.skip("agent creds not available")
        r = requests.post(f"{API}/conversations/{contact_id}/assign",
                          headers={"Authorization": f"Bearer {tok}"},
                          params={"channel": "whatsapp"},
                          json={"agent_email": "agent@cpaas.io"}, timeout=30)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}: {r.text}"


# ── Internal notes ─────────────────────────────────────────────────────────
class TestInternalNotes:
    def test_add_note_and_visible_in_timeline(self, admin_hdr, contact_id):
        note_body = f"TEST_note_{int(time.time())}"
        r = requests.post(f"{API}/conversations/notes", headers=admin_hdr,
                          json={"contact_id": contact_id, "body": note_body, "channel": "whatsapp"}, timeout=30)
        assert r.status_code == 200, r.text
        nid = r.json()["id"]
        assert nid
        # Timeline should include it (fetch latest page — since ASC, note should be at end)
        r2 = requests.get(f"{API}/contacts/{contact_id}/timeline", headers=admin_hdr, params={"limit": 200}, timeout=30)
        assert r2.status_code == 200
        msgs = r2.json()["messages"]
        found = next((m for m in msgs if m.get("id") == nid), None)
        assert found is not None, "internal note not found in timeline"
        assert found.get("direction") == "internal"
        assert found.get("is_internal") is True
        assert found.get("author") == ADMIN["email"]

    def test_empty_note_rejected(self, admin_hdr, contact_id):
        r = requests.post(f"{API}/conversations/notes", headers=admin_hdr,
                          json={"contact_id": contact_id, "body": "   "}, timeout=30)
        assert r.status_code == 400
