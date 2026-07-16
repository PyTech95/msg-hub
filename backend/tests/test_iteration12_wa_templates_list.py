"""Iteration 12 — WhatsApp Templates Listing (Meta Graph API integration)."""
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


@pytest.fixture(scope="module")
def sa_tok():
    return _login(SA_EMAIL, SA_PASS)


@pytest.fixture(scope="module")
def new_tenant(sa_tok):
    email = f"watpl12+{TS}@t.com"
    r = requests.post(f"{API}/companies", headers=_h(sa_tok),
                      json={"name": f"TEST_WATPL12_{TS}", "admin_email": email,
                            "admin_password": "Test@12345", "admin_name": "T12"}, timeout=15)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    tok = _login(email, "Test@12345")
    yield {"tok": tok, "cid": cid, "email": email}
    try:
        requests.delete(f"{API}/companies/{cid}", headers=_h(sa_tok), timeout=15)
    except Exception:
        pass


class TestTemplatesEndpoint:
    def test_sa_lists_templates_via_env_fallback(self, sa_tok):
        r = requests.get(f"{API}/whatsapp/templates", headers=_h(sa_tok), timeout=45)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True, j
        assert j["waba_id"] == "831164916601218"
        assert isinstance(j["templates"], list)
        assert j["count"] == len(j["templates"])
        assert j["count"] >= 2
        names = [t["name"] for t in j["templates"]]
        assert "hello_world" in names
        # each template shape
        for t in j["templates"]:
            for k in ("name", "language", "status", "category", "variable_count", "body_preview", "components"):
                assert k in t, f"missing key {k} in {t}"
            assert isinstance(t["variable_count"], int)
        # Sort: APPROVED first
        statuses = [t["status"] for t in j["templates"]]
        approved_idx = [i for i, s in enumerate(statuses) if s == "APPROVED"]
        other_idx = [i for i, s in enumerate(statuses) if s != "APPROVED"]
        if approved_idx and other_idx:
            assert max(approved_idx) < min(other_idx), f"APPROVED should come first: {statuses}"

    def test_status_filter_approved(self, sa_tok):
        r = requests.get(f"{API}/whatsapp/templates?status=APPROVED", headers=_h(sa_tok), timeout=45)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert all(t["status"] == "APPROVED" for t in j["templates"])
        names = [t["name"] for t in j["templates"]]
        assert "hello_world" in names
        assert "hello" not in names  # hello is PENDING

    def test_body_preview_and_variable_count_helpers(self, sa_tok):
        r = requests.get(f"{API}/whatsapp/templates", headers=_h(sa_tok), timeout=45).json()
        hw = next((t for t in r["templates"] if t["name"] == "hello_world"), None)
        assert hw is not None
        # hello_world body: "Hello World"
        assert hw["body_preview"], "body_preview should not be empty"
        assert isinstance(hw["variable_count"], int)
        assert hw["variable_count"] == 0  # hello_world has no {{1}} placeholders

    def test_company_admin_no_waba_returns_error_no_crash(self, new_tenant):
        r = requests.get(f"{API}/whatsapp/templates", headers=_h(new_tenant["tok"]), timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is False
        assert j["templates"] == []
        assert "error" in j and j["error"]
        # message should mention WABA or credentials
        assert ("WhatsApp" in j["error"] or "WABA" in j["error"] or "credentials" in j["error"].lower())

    def test_company_admin_with_valid_waba_returns_templates(self, new_tenant):
        # Configure tenant with env creds + waba_id
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
        if not at or not pnid:
            pytest.skip("no env creds")
        r = requests.put(f"{API}/whatsapp/config", headers=_h(new_tenant["tok"]),
                         json={"access_token": at, "phone_number_id": pnid,
                               "waba_id": "831164916601218", "graph_version": "v22.0", "mock": False},
                         timeout=20)
        assert r.status_code == 200, r.text
        cfg = r.json()
        assert cfg.get("waba_id") == "831164916601218", cfg
        # now list
        r2 = requests.get(f"{API}/whatsapp/templates", headers=_h(new_tenant["tok"]), timeout=45)
        assert r2.status_code == 200
        j2 = r2.json()
        assert j2["ok"] is True, j2
        assert j2["count"] >= 1


class TestWhatsAppConfigWabaId:
    def test_put_config_accepts_waba_id_and_mask_returns_it(self, sa_tok, new_tenant):
        # Use tenant B path — set waba_id on tenant and read back
        tok = new_tenant["tok"]
        r = requests.put(f"{API}/whatsapp/config", headers=_h(tok),
                         json={"access_token": "TK", "phone_number_id": "PID",
                               "waba_id": "999888777", "mock": True}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("waba_id") == "999888777"
        # GET config returns waba_id
        r2 = requests.get(f"{API}/whatsapp/config", headers=_h(tok), timeout=15)
        assert r2.status_code == 200
        assert r2.json().get("waba_id") == "999888777"


class TestRegressionIteration11:
    def test_sa_login_still_ok(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": SA_EMAIL, "password": SA_PASS}, timeout=15)
        assert r.status_code == 200
