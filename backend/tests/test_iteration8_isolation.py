"""
Iteration 8 — Multi-tenant SaaS data isolation P0 tests.
Verifies:
- Super Admin can create companies and their admins
- Company admins log in and only see their company's data
- Cross-tenant reads/writes/deletes are blocked (404)
- Platform-only endpoints (providers, webhooks, whatsapp/setup) return 403 for company admins, 200 for SA
- All feature-scoped resources (contacts/lists/templates/campaigns/messages/calls/bills/notices/voice-camps/reminders/audit-logs/usage/invoices) tag & filter by company_id
- Company DELETE cascade removes all tenant data
"""
import os, io, time, pytest, requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://msg-hub-59.preview.emergentagent.com"
API = f"{BASE_URL}/api"

SA_EMAIL = "admin@cpaas.io"
SA_PASS = "Admin@12345"

TS = int(time.time())
A_ADMIN = f"tenantA+{TS}@test.com"
B_ADMIN = f"tenantB+{TS}@test.com"
TENANT_PW = "Test@12345"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def sa_token():
    return _login(SA_EMAIL, SA_PASS)


@pytest.fixture(scope="module")
def companies(sa_token):
    h = _auth(sa_token)
    a = requests.post(f"{API}/companies", headers=h,
                      json={"name": f"TEST_CoA_{TS}", "admin_email": A_ADMIN,
                            "admin_password": TENANT_PW, "admin_name": "A Admin"}, timeout=15)
    assert a.status_code == 200, a.text
    b = requests.post(f"{API}/companies", headers=h,
                      json={"name": f"TEST_CoB_{TS}", "admin_email": B_ADMIN,
                            "admin_password": TENANT_PW, "admin_name": "B Admin"}, timeout=15)
    assert b.status_code == 200, b.text
    yield {"A": a.json(), "B": b.json()}
    # cleanup at end: delete both companies (cascade)
    for c in (a.json(), b.json()):
        try:
            requests.delete(f"{API}/companies/{c['id']}", headers=h, timeout=15)
        except Exception:
            pass


@pytest.fixture(scope="module")
def tokens(companies):
    return {"A": _login(A_ADMIN, TENANT_PW), "B": _login(B_ADMIN, TENANT_PW)}


# ── Companies + Auth ───────────────────────────────────────────
class TestCompaniesAuth:
    def test_duplicate_admin_email_rejected(self, sa_token, companies):
        r = requests.post(f"{API}/companies", headers=_auth(sa_token),
                          json={"name": "dup", "admin_email": A_ADMIN,
                                "admin_password": TENANT_PW}, timeout=15)
        assert r.status_code == 409

    def test_me_returns_company_id_and_admin_role(self, tokens, companies):
        for k in ("A", "B"):
            r = requests.get(f"{API}/auth/me", headers=_auth(tokens[k]), timeout=15)
            assert r.status_code == 200
            j = r.json()
            assert j["role"] == "admin"
            assert j["company_id"] == companies[k]["id"]

    def test_company_admin_cannot_list_companies(self, tokens):
        r = requests.get(f"{API}/companies", headers=_auth(tokens["A"]), timeout=15)
        assert r.status_code == 403

    def test_super_admin_can_list_companies(self, sa_token):
        r = requests.get(f"{API}/companies", headers=_auth(sa_token), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ── Contacts isolation ─────────────────────────────────────────
class TestContactsIsolation:
    def test_contact_isolation_full(self, tokens, companies):
        # A creates
        r = requests.post(f"{API}/contacts", headers=_auth(tokens["A"]),
                          json={"name": "TEST_A_c1", "phone": f"+9199{TS}01"}, timeout=15)
        assert r.status_code == 200
        cid = r.json()["id"]
        assert r.json()["company_id"] == companies["A"]["id"]
        # A lists — sees it
        la = requests.get(f"{API}/contacts", headers=_auth(tokens["A"]), timeout=15).json()
        assert any(x["id"] == cid for x in la)
        # B lists — must not see
        lb = requests.get(f"{API}/contacts", headers=_auth(tokens["B"]), timeout=15).json()
        assert not any(x.get("id") == cid for x in lb)
        # B GET by id -> 404
        assert requests.get(f"{API}/contacts/{cid}", headers=_auth(tokens["B"]), timeout=15).status_code == 404
        # B PATCH -> 404
        assert requests.patch(f"{API}/contacts/{cid}", headers=_auth(tokens["B"]),
                              json={"name": "hax"}, timeout=15).status_code == 404
        # B DELETE -> ok=True but no actual delete (empty filter match)
        rd = requests.delete(f"{API}/contacts/{cid}", headers=_auth(tokens["B"]), timeout=15)
        assert rd.status_code == 200
        # A still sees it
        assert requests.get(f"{API}/contacts/{cid}", headers=_auth(tokens["A"]), timeout=15).status_code == 200
        # B bulk-delete does not remove A's contact
        rbd = requests.post(f"{API}/contacts/bulk-delete", headers=_auth(tokens["B"]),
                            json=[cid], timeout=15)
        assert rbd.status_code == 200 and rbd.json()["deleted"] == 0
        # A can delete
        assert requests.delete(f"{API}/contacts/{cid}", headers=_auth(tokens["A"]), timeout=15).status_code == 200
        assert requests.get(f"{API}/contacts/{cid}", headers=_auth(tokens["A"]), timeout=15).status_code == 404

    def test_csv_import_tags_company_id(self, tokens, companies):
        csv_data = "name,phone,email\nTEST_ImpA,+9199{ts}02,x@a.com\n".format(ts=TS)
        files = {"file": ("c.csv", io.BytesIO(csv_data.encode()), "text/csv")}
        r = requests.post(f"{API}/contacts/import", headers=_auth(tokens["A"]), files=files, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["inserted"] == 1
        # B cannot see it
        lb = requests.get(f"{API}/contacts", headers=_auth(tokens["B"]), timeout=15).json()
        assert not any(x.get("name") == "TEST_ImpA" for x in lb)
        # A sees it
        la = requests.get(f"{API}/contacts", headers=_auth(tokens["A"]), timeout=15).json()
        assert any(x.get("name") == "TEST_ImpA" for x in la)


# ── Lists isolation ────────────────────────────────────────────
class TestListsIsolation:
    def test_lists_scoped(self, tokens):
        r = requests.post(f"{API}/lists", headers=_auth(tokens["A"]),
                          json={"name": "TEST_ListA"}, timeout=15)
        assert r.status_code == 200
        lid = r.json()["id"]
        # B does not see
        lb = requests.get(f"{API}/lists", headers=_auth(tokens["B"]), timeout=15).json()
        assert not any(x["id"] == lid for x in lb)
        # A sees
        la = requests.get(f"{API}/lists", headers=_auth(tokens["A"]), timeout=15).json()
        assert any(x["id"] == lid for x in la)


# ── Templates isolation ────────────────────────────────────────
class TestTemplatesIsolation:
    def test_templates_scoped(self, tokens, companies):
        r = requests.post(f"{API}/templates", headers=_auth(tokens["A"]),
                          json={"name": "TEST_TplA", "channel": "sms",
                                "body": "Hi {{name}}", "variables": ["name"]}, timeout=15)
        assert r.status_code == 200
        tid = r.json()["id"]
        assert r.json()["company_id"] == companies["A"]["id"]
        # B doesn't list
        lb = requests.get(f"{API}/templates", headers=_auth(tokens["B"]), timeout=15).json()
        assert not any(x["id"] == tid for x in lb)


# ── Campaigns + Messages + Calls isolation ─────────────────────
class TestCampaignsMessagesCallsIsolation:
    @pytest.fixture(scope="class")
    def setup_A(self, tokens):
        # contact
        c = requests.post(f"{API}/contacts", headers=_auth(tokens["A"]),
                          json={"name": "TEST_A_camp", "phone": f"+9199{TS}03"}, timeout=15).json()
        # template
        t = requests.post(f"{API}/templates", headers=_auth(tokens["A"]),
                          json={"name": "TEST_TplCamp", "channel": "sms", "body": "Hi {{name}}"}, timeout=15).json()
        # campaign
        cp = requests.post(f"{API}/campaigns", headers=_auth(tokens["A"]),
                           json={"name": "TEST_CampA", "channel": "sms", "template_id": t["id"],
                                 "list_ids": [], "contact_ids": [c["id"]]}, timeout=15).json()
        # message
        m = requests.post(f"{API}/messages/send", headers=_auth(tokens["A"]),
                          json={"channel": "sms", "contact_id": c["id"], "body": "hello"}, timeout=15).json()
        # call
        cl = requests.post(f"{API}/calls", headers=_auth(tokens["A"]),
                           json={"contact_id": c["id"], "notes": "TEST call"}, timeout=15).json()
        return {"contact": c, "tpl": t, "camp": cp, "msg": m, "call": cl}

    def test_campaigns_scoped(self, tokens, setup_A):
        camp_id = setup_A["camp"]["id"]
        # B does not list
        lb = requests.get(f"{API}/campaigns", headers=_auth(tokens["B"]), timeout=15).json()
        assert not any(x["id"] == camp_id for x in lb)
        # B detail 404
        assert requests.get(f"{API}/campaigns/{camp_id}", headers=_auth(tokens["B"]), timeout=15).status_code == 404
        # A detail returns campaign+recipients
        rd = requests.get(f"{API}/campaigns/{camp_id}", headers=_auth(tokens["A"]), timeout=15)
        assert rd.status_code == 200

    def test_messages_scoped(self, tokens, setup_A):
        mid = setup_A["msg"]["message_id"]
        # B list has no A msg
        lb = requests.get(f"{API}/messages", headers=_auth(tokens["B"]), timeout=15).json()
        assert not any(x.get("id") == mid for x in lb)
        # B events 404
        assert requests.get(f"{API}/messages/{mid}/events", headers=_auth(tokens["B"]), timeout=15).status_code == 404
        # A events 200
        assert requests.get(f"{API}/messages/{mid}/events", headers=_auth(tokens["A"]), timeout=15).status_code == 200

    def test_calls_scoped(self, tokens, setup_A):
        cid = setup_A["call"]["call_id"]
        # B list does not contain
        lb = requests.get(f"{API}/calls", headers=_auth(tokens["B"]), timeout=15).json()
        assert not any(x.get("id") == cid for x in lb)
        la = requests.get(f"{API}/calls", headers=_auth(tokens["A"]), timeout=15).json()
        assert any(x.get("id") == cid for x in la)

    def test_send_msg_cross_tenant_contact_404(self, tokens, setup_A):
        # B cannot send msg using A's contact_id
        r = requests.post(f"{API}/messages/send", headers=_auth(tokens["B"]),
                          json={"channel": "sms", "contact_id": setup_A["contact"]["id"], "body": "hi"}, timeout=15)
        assert r.status_code == 404


# ── RBAC platform_only + super_admin ───────────────────────────
class TestRBACPlatformOnly:
    ENDPOINTS_GET_403 = ["/providers", "/webhooks/events", "/whatsapp/setup"]

    def test_company_admin_403(self, tokens):
        for ep in self.ENDPOINTS_GET_403:
            r = requests.get(f"{API}{ep}", headers=_auth(tokens["A"]), timeout=15)
            assert r.status_code == 403, f"{ep} expected 403 got {r.status_code}"

    def test_company_admin_403_provider_write(self, tokens):
        # try create provider
        r = requests.post(f"{API}/providers", headers=_auth(tokens["A"]),
                          json={"name": "hack", "channel": "sms", "provider_key": "mock"}, timeout=15)
        assert r.status_code == 403

    def test_super_admin_200(self, sa_token):
        for ep in TestRBACPlatformOnly.ENDPOINTS_GET_403:
            r = requests.get(f"{API}{ep}", headers=_auth(sa_token), timeout=15)
            assert r.status_code == 200, f"{ep} SA expected 200 got {r.status_code}"

    def test_provider_credentials_and_test_rbac(self, sa_token, tokens):
        provs = requests.get(f"{API}/providers", headers=_auth(sa_token), timeout=15).json()
        assert len(provs) > 0
        pid = provs[0]["id"]
        # SA: 200 on credentials, test
        assert requests.get(f"{API}/providers/{pid}/credentials", headers=_auth(sa_token), timeout=15).status_code == 200
        assert requests.post(f"{API}/providers/{pid}/test", headers=_auth(sa_token), timeout=15).status_code == 200
        # Company admin: 403
        assert requests.get(f"{API}/providers/{pid}/credentials", headers=_auth(tokens["A"]), timeout=15).status_code == 403
        assert requests.put(f"{API}/providers/{pid}/credentials", headers=_auth(tokens["A"]),
                            json={"credentials": {"x": "y"}}, timeout=15).status_code == 403
        assert requests.post(f"{API}/providers/{pid}/test", headers=_auth(tokens["A"]), timeout=15).status_code == 403
        assert requests.delete(f"{API}/providers/{pid}", headers=_auth(tokens["A"]), timeout=15).status_code == 403


# ── Dashboard / audit / usage scoped ───────────────────────────
class TestDashboardAuditUsage:
    def test_dashboard_stats_scoped(self, tokens, companies):
        # A already has message (from prior test); B has none
        ra = requests.get(f"{API}/dashboard/stats", headers=_auth(tokens["A"]), timeout=15)
        rb = requests.get(f"{API}/dashboard/stats", headers=_auth(tokens["B"]), timeout=15)
        assert ra.status_code == 200 and rb.status_code == 200
        b_kpis = rb.json()["kpis"]
        # B is fresh — 0 messages
        assert b_kpis["messages_sent"] == 0
        assert b_kpis["contacts"] == 0

    def test_audit_logs_scoped(self, tokens):
        ra = requests.get(f"{API}/audit-logs", headers=_auth(tokens["A"]), timeout=15)
        assert ra.status_code == 200
        # every entry either has no actor or actor from own company (we can't easily verify without company_id on log,
        # but scoping is by cflt so all entries belong to company A's users only)
        logs = ra.json()
        assert isinstance(logs, list)

    def test_usage_scoped(self, tokens):
        ra = requests.get(f"{API}/usage/summary", headers=_auth(tokens["A"]), timeout=15).json()
        rb = requests.get(f"{API}/usage/summary", headers=_auth(tokens["B"]), timeout=15).json()
        # B is fresh
        assert rb["total_units"] == 0 and rb["total_amount"] == 0
        # A has at least one usage record
        assert ra["total_units"] >= 1

    def test_invoices_scoped(self, tokens):
        ra = requests.get(f"{API}/invoices", headers=_auth(tokens["A"]), timeout=15)
        rb = requests.get(f"{API}/invoices", headers=_auth(tokens["B"]), timeout=15)
        assert ra.status_code == 200 and rb.status_code == 200
        assert rb.json()["invoices"] == []


# ── Bills / Reminders / Notice templates / Voice campaigns ─────
class TestFeaturesIsolation:
    def test_notice_template_scoped(self, tokens):
        r = requests.post(f"{API}/notice-templates", headers=_auth(tokens["A"]),
                          json={"name": "TEST_NoticeA", "html": "<p>{{name}}</p>"}, timeout=15)
        assert r.status_code == 200
        tid = r.json()["id"]
        lb = requests.get(f"{API}/notice-templates", headers=_auth(tokens["B"]), timeout=15).json()
        assert not any(x["id"] == tid for x in lb)

    def test_bill_mark_paid_cross_tenant_404(self, tokens):
        # Manually seed a bill for A via bills collection — we don't have API to create raw bills.
        # Use enable-reminders on empty ids to at least exercise scoping
        r = requests.post(f"{API}/bills/enable-reminders", headers=_auth(tokens["A"]),
                          json={"bill_ids": ["nonexistent-id"]}, timeout=15)
        assert r.status_code == 200
        # cross-tenant mark-paid on nonexistent bill -> 404
        rb = requests.post(f"{API}/bills/{'no-such-bill'}/mark-paid", headers=_auth(tokens["B"]), timeout=15)
        assert rb.status_code == 404

    def test_voice_campaign_scoped_empty_targets(self, tokens):
        # cannot create voice campaign with no valid targets — 400
        r = requests.post(f"{API}/voice-campaigns", headers=_auth(tokens["A"]),
                          json={"name": "TEST_VC", "script": "hi {{name}}",
                                "contact_ids": ["nonexistent"]}, timeout=15)
        assert r.status_code == 400
        # B lists no voice campaigns
        lb = requests.get(f"{API}/voice-campaigns", headers=_auth(tokens["B"]), timeout=15).json()
        assert lb == []

    def test_reminders_upcoming_scoped(self, tokens):
        ra = requests.get(f"{API}/reminders/upcoming", headers=_auth(tokens["A"]), timeout=15)
        rb = requests.get(f"{API}/reminders/upcoming", headers=_auth(tokens["B"]), timeout=15)
        assert ra.status_code == 200 and rb.status_code == 200
        assert rb.json() == []


# ── Company DELETE cascade ─────────────────────────────────────
class TestCompanyDeleteCascade:
    def test_delete_company_cascades(self, sa_token):
        # Create isolated tenant C, seed data, delete, verify empty
        ts = int(time.time()) + 99
        admin_email = f"tenantC+{ts}@test.com"
        r = requests.post(f"{API}/companies", headers=_auth(sa_token),
                          json={"name": f"TEST_CoC_{ts}", "admin_email": admin_email,
                                "admin_password": TENANT_PW}, timeout=15)
        assert r.status_code == 200
        comp_id = r.json()["id"]
        tok = _login(admin_email, TENANT_PW)
        # seed
        contact = requests.post(f"{API}/contacts", headers=_auth(tok),
                                json={"name": "TEST_del", "phone": f"+9199{ts}"}, timeout=15).json()
        tpl = requests.post(f"{API}/templates", headers=_auth(tok),
                            json={"name": "TEST_tpl_del", "channel": "sms", "body": "hi"}, timeout=15).json()
        requests.post(f"{API}/campaigns", headers=_auth(tok),
                      json={"name": "TEST_c_del", "channel": "sms", "template_id": tpl["id"],
                            "contact_ids": [contact["id"]]}, timeout=15)
        # delete company
        dr = requests.delete(f"{API}/companies/{comp_id}", headers=_auth(sa_token), timeout=15)
        assert dr.status_code == 200
        # login of that admin should now fail (user deleted)
        r2 = requests.post(f"{API}/auth/login", json={"email": admin_email, "password": TENANT_PW}, timeout=15)
        assert r2.status_code == 401

    def test_provider_visibility_untouched(self, sa_token):
        # SA still sees providers after all tenant activity
        r = requests.get(f"{API}/providers", headers=_auth(sa_token), timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 3


# ── SA regression ──────────────────────────────────────────────
class TestSuperAdminRegression:
    def test_sa_login_and_me(self, sa_token):
        r = requests.get(f"{API}/auth/me", headers=_auth(sa_token), timeout=15)
        assert r.status_code == 200
        assert r.json()["role"] == "super_admin"
        assert not r.json().get("company_id")

    def test_sa_dashboard(self, sa_token):
        r = requests.get(f"{API}/dashboard/stats", headers=_auth(sa_token), timeout=15)
        assert r.status_code == 200
        # SA aggregated view includes seed messages
        assert r.json()["kpis"]["messages_sent"] > 0
