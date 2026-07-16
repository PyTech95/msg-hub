"""
Iteration 11: Verify Cloudflare-502 → 400 fix for provider send failures.
Tests must run against the EXTERNAL URL (Cloudflare-fronted) to prove
that error responses come through as JSON 400 (not Cloudflare HTML 502).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")

SA_EMAIL = "admin@cpaas.io"
SA_PASS = "Admin@12345"


@pytest.fixture(scope="module")
def sa_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": SA_EMAIL, "password": SA_PASS}, timeout=30)
    assert r.status_code == 200, f"SA login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


@pytest.fixture(scope="module")
def a_contact_id(sa_session):
    r = sa_session.get(f"{BASE_URL}/api/contacts?limit=1", timeout=15)
    assert r.status_code == 200
    items = r.json()
    if items:
        return items[0]["id"]
    # create one
    r = sa_session.post(f"{BASE_URL}/api/contacts", json={
        "name": "TEST_it11", "phone": "+15551230011", "email": "t11@test.com"
    }, timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _assert_json_400(resp):
    """Not HTML 502 from Cloudflare, but JSON 400 with detail."""
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}. Body[:200]={resp.text[:200]}"
    ctype = resp.headers.get("content-type", "")
    assert "application/json" in ctype, f"Expected JSON, got {ctype}. Body[:200]={resp.text[:200]}"
    body = resp.json()
    assert "detail" in body, f"No detail in body: {body}"
    return body


class TestCloudflare502Fix:
    """The core fix: Meta provider failures return 400 JSON, not 502 HTML."""

    def test_messages_send_hello_world_returns_400_json(self, sa_session, a_contact_id):
        r = sa_session.post(f"{BASE_URL}/api/messages/send", json={
            "channel": "whatsapp",
            "contact_id": a_contact_id,
            "body": "",
            "template_name": "hello_world",
            "template_language": "en_US",
        }, timeout=45)
        body = _assert_json_400(r)
        # Should contain Meta API error text
        detail = str(body["detail"])
        assert "Send failed" in detail or "Meta" in detail or "template" in detail.lower(), \
            f"Detail did not contain expected error text: {detail}"
        print(f"[OK] /messages/send hello_world -> 400 JSON: {detail[:200]}")

    def test_whatsapp_send_message_hello_world_returns_400_json(self, sa_session, a_contact_id):
        # Grab contact phone
        c = sa_session.get(f"{BASE_URL}/api/contacts/{a_contact_id}", timeout=15).json()
        r = sa_session.post(f"{BASE_URL}/api/whatsapp/send-message", json={
            "contact_id": a_contact_id,
            "to": c.get("phone", "+15551230011"),
            "body": "",
            "template_name": "hello_world",
            "template_language": "en_US",
        }, timeout=45)
        body = _assert_json_400(r)
        print(f"[OK] /whatsapp/send-message hello_world -> 400 JSON: {str(body['detail'])[:200]}")

    def test_invalid_template_name_returns_400_json(self, sa_session, a_contact_id):
        r = sa_session.post(f"{BASE_URL}/api/messages/send", json={
            "channel": "whatsapp",
            "contact_id": a_contact_id,
            "body": "",
            "template_name": "this_template_does_not_exist_xyz_it11",
            "template_language": "en_US",
        }, timeout=45)
        body = _assert_json_400(r)
        print(f"[OK] invalid template -> 400 JSON: {str(body['detail'])[:200]}")


class TestRegression:
    """Ensure successful paths still work."""

    def test_sms_send_still_returns_200_mock(self, sa_session, a_contact_id):
        r = sa_session.post(f"{BASE_URL}/api/messages/send", json={
            "channel": "sms",
            "contact_id": a_contact_id,
            "body": "TEST_it11 regression sms",
        }, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("mode") == "mock"
        print(f"[OK] SMS send -> 200 mode=mock")

    def test_health_endpoint(self, sa_session):
        r = sa_session.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
