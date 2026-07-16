"""Iteration 13 — WhatsApp templates per-tenant isolation + SA env fallback."""
import os, time, pytest, requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
SA_EMAIL, SA_PASS = "admin@cpaas.io", "Admin@12345"
TS = int(time.time())


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(t): return {"Authorization": f"Bearer {t}"}


def _env_creds():
    at = None; pnid = None
    try:
        with open("/app/backend/.env") as f:
            for line in f:
                if "=" not in line: continue
                k, v = line.strip().split("=", 1)
                if k in ("WHATSAPP_ACCESS_TOKEN", "META_WHATSAPP_ACCESS_TOKEN") and not at: at = v
                if k in ("WHATSAPP_PHONE_NUMBER_ID", "META_PHONE_NUMBER_ID") and not pnid: pnid = v
    except Exception:
        pass
    return at, pnid


@pytest.fixture(scope="module")
def sa_tok():
    return _login(SA_EMAIL, SA_PASS)


@pytest.fixture(scope="module")
def tenant(sa_tok):
    email = f"watpl13+{TS}@t.com"
    r = requests.post(f"{API}/companies", headers=_h(sa_tok),
                      json={"name": f"TEST_WATPL13_{TS}", "admin_email": email,
                            "admin_password": "Test@12345", "admin_name": "T13"}, timeout=15)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    tok = _login(email, "Test@12345")
    yield {"tok": tok, "cid": cid, "email": email}
    try:
        requests.delete(f"{API}/companies/{cid}", headers=_h(sa_tok), timeout=15)
    except Exception:
        pass


class TestTenantIsolationFix:
    def test_ca_without_any_wa_config_returns_ok_false_no_env_leak(self, tenant):
        """CA with NO tenant WA config MUST NOT inherit env WABA templates."""
        r = requests.get(f"{API}/whatsapp/templates", headers=_h(tenant["tok"]), timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is False, j
        assert j["templates"] == []
        assert "error" in j and j["error"]
        # Expected message contains 'No live WhatsApp credentials'
        assert "credentials" in j["error"].lower() or "no live" in j["error"].lower(), j["error"]
        # Must NOT have leaked env waba_id
        assert "waba_id" not in j or not j.get("waba_id")

    def test_ca_with_config_but_no_waba_id_returns_waba_error(self, tenant):
        """CA with access_token + phone_number_id set, mock=false, but no waba_id → error."""
        at, pnid = _env_creds()
        if not at or not pnid:
            pytest.skip("no env creds available")
        r = requests.put(f"{API}/whatsapp/config", headers=_h(tenant["tok"]),
                         json={"access_token": at, "phone_number_id": pnid,
                               "waba_id": "", "graph_version": "v22.0", "mock": False},
                         timeout=15)
        assert r.status_code == 200, r.text
        r2 = requests.get(f"{API}/whatsapp/templates", headers=_h(tenant["tok"]), timeout=20)
        assert r2.status_code == 200
        j = r2.json()
        assert j["ok"] is False, j
        assert j["templates"] == []
        err = j.get("error", "")
        assert "WABA" in err or "Business Account" in err, err

    def test_ca_with_full_config_uses_own_waba(self, tenant):
        """CA with full config (incl. waba_id) uses tenant's own WABA."""
        at, pnid = _env_creds()
        if not at or not pnid:
            pytest.skip("no env creds")
        r = requests.put(f"{API}/whatsapp/config", headers=_h(tenant["tok"]),
                         json={"access_token": at, "phone_number_id": pnid,
                               "waba_id": "831164916601218", "graph_version": "v22.0", "mock": False},
                         timeout=20)
        assert r.status_code == 200, r.text
        r2 = requests.get(f"{API}/whatsapp/templates", headers=_h(tenant["tok"]), timeout=45)
        assert r2.status_code == 200
        j = r2.json()
        assert j["ok"] is True, j
        assert j["waba_id"] == "831164916601218"
        assert j["count"] >= 1

    def test_sa_env_fallback_still_works(self, sa_tok):
        """SA (no company_id) must still get env-fallback templates."""
        r = requests.get(f"{API}/whatsapp/templates", headers=_h(sa_tok), timeout=45)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True, j
        assert j["waba_id"] == "831164916601218"
        assert isinstance(j["templates"], list)
        assert j["count"] >= 2
        names = [t["name"] for t in j["templates"]]
        assert "hello_world" in names

    def test_status_filter_approved_sa(self, sa_tok):
        r = requests.get(f"{API}/whatsapp/templates?status=APPROVED", headers=_h(sa_tok), timeout=45)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert all(t["status"] == "APPROVED" for t in j["templates"])

    def test_status_filter_approved_tenant(self, tenant):
        # tenant is now configured with waba_id from previous test
        r = requests.get(f"{API}/whatsapp/templates?status=APPROVED",
                         headers=_h(tenant["tok"]), timeout=45)
        assert r.status_code == 200
        j = r.json()
        if j["ok"]:
            assert all(t["status"] == "APPROVED" for t in j["templates"])


class TestRegression:
    def test_sa_login(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": SA_EMAIL, "password": SA_PASS}, timeout=15)
        assert r.status_code == 200

    def test_wa_config_get_still_works(self, sa_tok):
        r = requests.get(f"{API}/whatsapp/config", headers=_h(sa_tok), timeout=15)
        assert r.status_code == 200
