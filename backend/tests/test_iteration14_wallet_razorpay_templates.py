"""Iteration 14 — Wallet + Razorpay + Template Builder.

Covers:
- Wallet CRUD (GET wallet, list wallets, adjust)
- Send-block on low balance (402)
- Send-debit (SMS 25 paise per message)
- Razorpay config/order gates (503/400)
- Meta Template create + delete (as SA using env WABA)
- CA without WA config: template create 400
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
SA_EMAIL, SA_PASS = "admin@cpaas.io", "Admin@12345"
TS = int(time.time())


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def sa_tok():
    return _login(SA_EMAIL, SA_PASS)


@pytest.fixture(scope="module")
def tenant(sa_tok):
    email = f"wal14+{TS}@t.com"
    r = requests.post(
        f"{API}/companies",
        headers=_h(sa_tok),
        json={
            "name": f"TEST_WAL14_{TS}",
            "admin_email": email,
            "admin_password": "Test@12345",
            "admin_name": "W14",
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    tok = _login(email, "Test@12345")
    yield {"tok": tok, "cid": cid, "email": email}
    try:
        requests.delete(f"{API}/companies/{cid}", headers=_h(sa_tok), timeout=15)
    except Exception:
        pass


# ────────── Wallet ──────────
class TestWallet:
    def test_ca_get_wallet_fresh_zero(self, tenant):
        r = requests.get(f"{API}/wallet", headers=_h(tenant["tok"]), timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["balance_paise"] == 0
        assert j["balance_inr"] == 0.0
        assert j["low_balance"] is True  # 0 < 5000
        assert j["transactions"] == []
        pp = j["pricing_paise"]
        assert pp["sms"] == 25
        assert pp["whatsapp"] == 40
        assert pp["rcs"] == 50
        assert pp["voice"] == 120
        assert pp["email"] == 10

    def test_sa_get_wallet_400(self, sa_tok):
        r = requests.get(f"{API}/wallet", headers=_h(sa_tok), timeout=15)
        assert r.status_code == 400
        assert "Super Admin" in r.json().get("detail", "")

    def test_sa_list_all_wallets_enriched(self, sa_tok, tenant):
        r = requests.get(f"{API}/wallets", headers=_h(sa_tok), timeout=15)
        assert r.status_code == 200, r.text
        arr = r.json()
        assert isinstance(arr, list)
        # Our tenant should appear
        ours = [w for w in arr if w["company_id"] == tenant["cid"]]
        assert len(ours) == 1
        w = ours[0]
        assert w["company_name"].startswith("TEST_WAL14_")
        assert w["admin_email"] == tenant["email"]

    def test_ca_cannot_list_all_wallets(self, tenant):
        r = requests.get(f"{API}/wallets", headers=_h(tenant["tok"]), timeout=15)
        assert r.status_code == 403

    def test_ca_cannot_adjust(self, tenant):
        r = requests.post(
            f"{API}/wallet/adjust",
            headers=_h(tenant["tok"]),
            json={"company_id": tenant["cid"], "amount_paise": 10000, "reason": "hack"},
            timeout=15,
        )
        assert r.status_code == 403

    def test_sa_credit_100_rupees(self, sa_tok, tenant):
        r = requests.post(
            f"{API}/wallet/adjust",
            headers=_h(sa_tok),
            json={"company_id": tenant["cid"], "amount_paise": 10000, "reason": "iteration14 test seed"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["balance_paise"] == 10000
        # Confirm via GET
        w = requests.get(f"{API}/wallet", headers=_h(tenant["tok"]), timeout=15).json()
        assert w["balance_paise"] == 10000
        assert w["balance_inr"] == 100.0
        assert w["low_balance"] is False
        assert any(t["type"] == "credit" and t["amount_paise"] == 10000 for t in w["transactions"])

    def test_sa_debit_more_than_balance_rejected_and_restored(self, sa_tok, tenant):
        before = requests.get(f"{API}/wallets", headers=_h(sa_tok), timeout=15).json()
        bp = next(w["balance_paise"] for w in before if w["company_id"] == tenant["cid"])
        r = requests.post(
            f"{API}/wallet/adjust",
            headers=_h(sa_tok),
            json={"company_id": tenant["cid"], "amount_paise": -(bp + 10000), "reason": "overdraw"},
            timeout=15,
        )
        assert r.status_code == 400
        assert "negative" in r.json().get("detail", "").lower()
        after = requests.get(f"{API}/wallets", headers=_h(sa_tok), timeout=15).json()
        bp2 = next(w["balance_paise"] for w in after if w["company_id"] == tenant["cid"])
        assert bp2 == bp, f"balance not restored: {bp} → {bp2}"


# ────────── Send debit / block ──────────
class TestSendDebitBlock:
    def _create_contact(self, tenant):
        r = requests.post(
            f"{API}/contacts",
            headers=_h(tenant["tok"]),
            json={"name": "Test C", "phone": "+911234567890", "email": "c@t.com"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def test_debit_25p_on_sms_send(self, sa_tok, tenant):
        # Ensure balance
        requests.post(
            f"{API}/wallet/adjust",
            headers=_h(sa_tok),
            json={"company_id": tenant["cid"], "amount_paise": 500, "reason": "top-up for send"},
            timeout=15,
        )
        before = requests.get(f"{API}/wallet", headers=_h(tenant["tok"]), timeout=15).json()["balance_paise"]
        contact_id = self._create_contact(tenant)
        r = requests.post(
            f"{API}/messages/send",
            headers=_h(tenant["tok"]),
            json={"channel": "sms", "contact_id": contact_id, "body": "hello test"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        time.sleep(0.5)
        after = requests.get(f"{API}/wallet", headers=_h(tenant["tok"]), timeout=15).json()["balance_paise"]
        assert after == before - 25, f"expected debit 25 paise; before={before} after={after}"
        # Latest txn is a debit of 25 with channel=sms in meta
        w = requests.get(f"{API}/wallet", headers=_h(tenant["tok"]), timeout=15).json()
        latest_debit = next((t for t in w["transactions"] if t["type"] == "debit"), None)
        assert latest_debit is not None and latest_debit["amount_paise"] == 25

    def test_send_blocked_when_insufficient_402(self, sa_tok, tenant):
        # Zero out the balance
        w = requests.get(f"{API}/wallet", headers=_h(tenant["tok"]), timeout=15).json()
        bal = w["balance_paise"]
        if bal > 0:
            requests.post(
                f"{API}/wallet/adjust",
                headers=_h(sa_tok),
                json={"company_id": tenant["cid"], "amount_paise": -bal, "reason": "drain for block test"},
                timeout=15,
            )
        # Reuse contact
        contact_id = self._create_contact(tenant)
        r = requests.post(
            f"{API}/messages/send",
            headers=_h(tenant["tok"]),
            json={"channel": "sms", "contact_id": contact_id, "body": "hello block"},
            timeout=20,
        )
        assert r.status_code == 402, r.text
        assert "recharge" in r.json().get("detail", "").lower()


# ────────── Razorpay plumbing ──────────
class TestRazorpay:
    def test_config_returns_unconfigured(self, tenant):
        r = requests.get(f"{API}/wallet/recharge/config", headers=_h(tenant["tok"]), timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["configured"] is False
        assert j["key_id"] is None
        assert j["currency"] == "INR"
        assert j["min_amount_paise"] == 10000

    def test_order_below_min_400(self, tenant):
        r = requests.post(
            f"{API}/wallet/recharge/order",
            headers=_h(tenant["tok"]),
            json={"amount_paise": 5000},
            timeout=15,
        )
        assert r.status_code == 400
        assert "Minimum" in r.json().get("detail", "")

    def test_order_without_keys_503(self, tenant):
        r = requests.post(
            f"{API}/wallet/recharge/order",
            headers=_h(tenant["tok"]),
            json={"amount_paise": 10000},
            timeout=15,
        )
        assert r.status_code == 503
        assert "not configured" in r.json().get("detail", "").lower()

    def test_sa_order_400(self, sa_tok):
        r = requests.post(
            f"{API}/wallet/recharge/order",
            headers=_h(sa_tok),
            json={"amount_paise": 10000},
            timeout=15,
        )
        assert r.status_code == 400
        assert "Super Admin" in r.json().get("detail", "")


# ────────── Template Builder (SA — real Meta) ──────────
class TestTemplateBuilder:
    _created_name = None

    def test_sa_create_template_utility_pending(self, sa_tok):
        name = f"tzs_test_{TS}"
        r = requests.post(
            f"{API}/whatsapp/templates",
            headers=_h(sa_tok),
            json={
                "name": name,
                "category": "UTILITY",
                "language": "en_US",
                "body_text": "Hello world, this is a test message from iteration 14.",
            },
            timeout=45,
        )
        if r.status_code == 400 and ("already exists" in r.text.lower() or "cooldown" in r.text.lower()):
            pytest.skip(f"Template {name} conflict on Meta: {r.text}")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert j.get("id")
        assert j["name"] == name.lower()
        assert j["language"] == "en_US"
        assert j["status"] in ("PENDING", "APPROVED", "IN_APPEAL", "REJECTED")
        TestTemplateBuilder._created_name = name.lower()

    def test_invalid_category_400(self, sa_tok):
        r = requests.post(
            f"{API}/whatsapp/templates",
            headers=_h(sa_tok),
            json={"name": f"tzs_bad_{TS}", "category": "PROMO",
                  "language": "en_US", "body_text": "hello"},
            timeout=20,
        )
        assert r.status_code == 400
        assert "category" in r.json().get("detail", "").lower()

    def test_empty_body_text_422(self, sa_tok):
        # body_text absent — pydantic validation error (422)
        r = requests.post(
            f"{API}/whatsapp/templates",
            headers=_h(sa_tok),
            json={"name": f"tzs_bad2_{TS}", "category": "UTILITY", "language": "en_US"},
            timeout=15,
        )
        assert r.status_code in (400, 422), r.text

    def test_delete_created_template(self, sa_tok):
        name = TestTemplateBuilder._created_name
        if not name:
            pytest.skip("template creation skipped/failed")
        r = requests.delete(f"{API}/whatsapp/templates/{name}", headers=_h(sa_tok), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

    def test_ca_without_wa_config_400(self, tenant):
        r = requests.post(
            f"{API}/whatsapp/templates",
            headers=_h(tenant["tok"]),
            json={"name": f"tzs_ca_{TS}", "category": "UTILITY",
                  "language": "en_US", "body_text": "hello world"},
            timeout=20,
        )
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "not configured" in detail.lower(), detail
