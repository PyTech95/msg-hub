import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  MessageCircle, CheckCircle2, AlertTriangle, Copy, Check,
  Save, Trash2, PlugZap, Eye, EyeOff, Send, RefreshCw, FileText, Plus,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import TemplateBuilderDialog from "@/components/TemplateBuilderDialog";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || window.location.origin;

function CopyField({ label, value, testId }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    if (!value) return;
    await navigator.clipboard.writeText(value);
    setCopied(true);
    toast.success(`${label} copied`);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <div className="flex gap-2">
        <Input readOnly value={value || ""} className="rounded-sm font-mono text-xs bg-muted/40" data-testid={testId} />
        <Button type="button" variant="outline" size="icon" className="rounded-sm h-9 w-9 shrink-0" onClick={copy} data-testid={`${testId}-copy`}>
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
        </Button>
      </div>
    </div>
  );
}

export default function WhatsAppSettings() {
  const { user } = useAuth();
  const [cfg, setCfg] = useState(null);
  const [form, setForm] = useState({
    access_token: "", phone_number_id: "", waba_id: "", app_secret: "",
    graph_version: "v22.0", mock: false, is_active: true,
  });
  const [reveal, setReveal] = useState({ token: false, secret: false });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  // Templates catalog
  const [templates, setTemplates] = useState(null);
  const [tplLoading, setTplLoading] = useState(false);
  const [tplError, setTplError] = useState("");
  const [showBuilder, setShowBuilder] = useState(false);

  const deleteTpl = async (name) => {
    if (!window.confirm(`Delete template "${name}" from Meta? This cannot be undone.`)) return;
    try {
      await api.delete(`/whatsapp/templates/${encodeURIComponent(name)}`);
      toast.success(`Template "${name}" deleted`);
      loadTemplates();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Delete failed");
    }
  };

  // Quick send-test
  const [to, setTo] = useState("");
  const [msg, setMsg] = useState("Hello from tezsandesh.digital 👋");
  const [quickMode, setQuickMode] = useState("template");  // template is safer default
  const [quickTpl, setQuickTpl] = useState("hello_world");
  const [quickLang, setQuickLang] = useState("en_US");
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState(null);

  // Meta Embedded Signup config (loaded once on mount)
  const [signupCfg, setSignupCfg] = useState(null);
  const [signupBusy, setSignupBusy] = useState(false);
  useEffect(() => {
    api.get("/whatsapp/embedded-signup/config")
      .then(r => setSignupCfg(r.data))
      .catch(() => setSignupCfg({ enabled: false, reason: "Failed to load signup config" }));
  }, []);

  // Load FB JS SDK once, only when signup is enabled and user is a company admin
  useEffect(() => {
    if (!signupCfg?.enabled || !user?.company_id) return;
    if (window.FB || document.getElementById("fb-jssdk-loader")) return;
    const s = document.createElement("script");
    s.id = "fb-jssdk-loader";
    s.async = true; s.defer = true; s.crossOrigin = "anonymous";
    s.src = `https://connect.facebook.net/en_US/sdk.js`;
    s.onload = () => {
      window.fbAsyncInit = () => {
        window.FB.init({ appId: signupCfg.app_id, cookie: true, xfbml: true, version: signupCfg.graph_version });
      };
      window.fbAsyncInit();
    };
    document.body.appendChild(s);
  }, [signupCfg, user?.company_id]);

  const startEmbeddedSignup = () => {
    if (!window.FB) { toast.error("Facebook SDK not loaded yet — retry in a moment."); return; }
    setSignupBusy(true);
    window.FB.login(
      (response) => {
        setSignupBusy(false);
        if (response.status !== "connected" || !response.authResponse?.code) {
          toast.error("Meta signup cancelled or failed");
          return;
        }
        const code = response.authResponse.code;
        const evtWaba = window.__lastWabaEvent || {};
        api.post("/whatsapp/embedded-signup/exchange", {
          code, waba_id: evtWaba.waba_id || "", phone_number_id: evtWaba.phone_number_id || "",
          business_id: evtWaba.business_id, display_phone_number: evtWaba.display_phone_number,
          verified_name: evtWaba.verified_name,
        }).then(() => {
          toast.success("WhatsApp connected via Meta! Refreshing…");
          setTimeout(load, 500);
        }).catch(err => toast.error(err.response?.data?.detail || "Exchange failed"));
      },
      {
        config_id: signupCfg.config_id,
        response_type: "code",
        override_default_response_type: true,
        extras: { setup: {}, featureType: "whatsapp_business_app_onboarding", sessionInfoVersion: 3 },
      },
    );
  };

  // Capture WABA/phone-number-id from Meta's postMessage during signup
  useEffect(() => {
    const onMsg = (e) => {
      if (e.origin !== "https://www.facebook.com" && e.origin !== "https://web.facebook.com") return;
      try {
        const data = typeof e.data === "string" ? JSON.parse(e.data) : e.data;
        if (data?.type === "WA_EMBEDDED_SIGNUP") {
          window.__lastWabaEvent = { ...(window.__lastWabaEvent || {}), ...(data.data || {}) };
        }
      } catch (_) { /* not our message */ }
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  const load = async () => {
    try {
      const { data } = await api.get("/whatsapp/config");
      setCfg(data);
      if (data.configured) {
        setForm(f => ({
          ...f,
          phone_number_id: data.phone_number_id || "",
          waba_id: data.waba_id || "",
          graph_version: data.graph_version || "v22.0",
          mock: !!data.mock,
          is_active: data.is_active !== false,
        }));
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to load config");
    }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    // Auto-load templates when: (a) company admin has waba_id configured, OR (b) super admin has platform env live
    const canLoad = cfg && templates === null && !tplLoading && (
      (cfg.configured && cfg.waba_id) ||
      (!user?.company_id && cfg.platform_env_configured)
    );
    if (canLoad) loadTemplates();
  }, [cfg, templates, user?.company_id, tplLoading]);

  const loadTemplates = async () => {
    setTplLoading(true); setTplError("");
    try {
      const { data } = await api.get("/whatsapp/templates");
      if (data.ok) {
        const list = data.templates || [];
        setTemplates(list);
        // Pre-select first APPROVED template so the dropdown shows something valid
        const firstApproved = list.find(t => t.status === "APPROVED");
        if (firstApproved) { setQuickTpl(firstApproved.name); setQuickLang(firstApproved.language); }
      } else {
        setTemplates([]);
        setTplError(data.error || "Failed to load templates");
      }
    } catch (err) {
      setTemplates([]);
      setTplError(err.response?.data?.detail || err.message || "Failed to load templates");
    } finally { setTplLoading(false); }
  };

  const templatesCard = (
    <Card className="rounded-sm shadow-none" data-testid="wa-templates-card">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
              <FileText className="h-3.5 w-3.5" /> Approved Templates
            </div>
            <div className="text-[11px] text-muted-foreground mt-0.5">Fetched live from Meta Graph API. Templates must be <strong>APPROVED</strong> before you can send them.</div>
          </div>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={loadTemplates} disabled={tplLoading} className="rounded-sm gap-1" data-testid="wa-templates-refresh">
              <RefreshCw className={`h-3.5 w-3.5 ${tplLoading ? "animate-spin" : ""}`} /> {tplLoading ? "Loading…" : (templates === null ? "Load templates" : "Refresh")}
            </Button>
            <Button type="button" size="sm" onClick={() => setShowBuilder(true)} className="rounded-sm gap-1" data-testid="wa-templates-create">
              <Plus className="h-3.5 w-3.5" /> New template
            </Button>
          </div>
        </div>
        {tplError && (
          <div className="p-2 rounded-sm border border-red-300 bg-red-50 dark:bg-red-900/20 text-xs flex items-start gap-2" data-testid="wa-templates-error">
            <AlertTriangle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
            <div>{tplError}</div>
          </div>
        )}
        {templates && templates.length === 0 && !tplError && (
          <div className="text-xs text-muted-foreground p-3 border border-dashed rounded-sm text-center" data-testid="wa-templates-empty">
            No templates found. Create one in <a className="underline" href="https://business.facebook.com/wa/manage/message-templates/" target="_blank" rel="noreferrer">Meta Business Manager → Message Templates</a>.
          </div>
        )}
        {templates && templates.length > 0 && (
          <div className="border rounded-sm overflow-hidden" data-testid="wa-templates-list">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-muted/40">
                  <th className="text-left p-2 font-medium">Name</th>
                  <th className="text-left p-2 font-medium">Language</th>
                  <th className="text-left p-2 font-medium">Category</th>
                  <th className="text-left p-2 font-medium">Status</th>
                  <th className="text-left p-2 font-medium">Vars</th>
                  <th className="text-left p-2 font-medium">Body preview</th>
                  <th className="text-left p-2 font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {templates.map(t => (
                  <tr key={`${t.name}_${t.language}`} className="border-t hover:bg-muted/20" data-testid={`wa-template-row-${t.name}`}>
                    <td className="p-2 font-mono">{t.name}</td>
                    <td className="p-2 font-mono text-muted-foreground">{t.language}</td>
                    <td className="p-2"><Badge variant="outline" className="rounded-sm text-[10px]">{t.category || "—"}</Badge></td>
                    <td className="p-2">
                      {t.status === "APPROVED"
                        ? <Badge variant="outline" className="rounded-sm text-[10px] border-emerald-300 text-emerald-700">APPROVED</Badge>
                        : t.status === "PENDING"
                          ? <Badge variant="outline" className="rounded-sm text-[10px] border-amber-300 text-amber-700">PENDING</Badge>
                          : <Badge variant="outline" className="rounded-sm text-[10px] border-red-300 text-red-700">{t.status}</Badge>}
                    </td>
                    <td className="p-2 font-mono">{t.variable_count}</td>
                    <td className="p-2 text-muted-foreground max-w-xs truncate" title={t.body_preview}>{t.body_preview || "—"}</td>
                    <td className="p-2">
                      <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => deleteTpl(t.name)} data-testid={`wa-template-delete-${t.name}`}>
                        <Trash2 className="h-3 w-3 text-red-600" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      // Only send secrets if user typed something; empty string means "leave unchanged"
      const payload = {
        phone_number_id: form.phone_number_id?.trim(),
        waba_id: form.waba_id?.trim(),
        graph_version: form.graph_version?.trim() || "v22.0",
        mock: form.mock,
        is_active: form.is_active,
      };
      if (form.access_token?.trim()) payload.access_token = form.access_token.trim();
      if (form.app_secret?.trim()) payload.app_secret = form.app_secret.trim();
      const { data } = await api.put("/whatsapp/config", payload);
      toast.success(cfg?.configured ? "Configuration updated" : "WhatsApp configuration saved");
      setCfg({ configured: true, ...data });
      setForm(f => ({ ...f, access_token: "", app_secret: "" }));  // clear secrets from form after save
    } catch (err) {
      toast.error(err.response?.data?.detail || "Save failed");
    } finally { setSaving(false); }
  };

  const remove = async () => {
    if (!window.confirm("Remove your WhatsApp credentials? Outgoing messages will fall back to platform default (or mock mode).")) return;
    try {
      await api.delete("/whatsapp/config");
      toast.success("Configuration removed");
      setCfg({ configured: false });
      setForm({ access_token: "", phone_number_id: "", waba_id: "", app_secret: "", graph_version: "v22.0", mock: false, is_active: true });
    } catch (err) {
      toast.error(err.response?.data?.detail || "Delete failed");
    }
  };

  const runTest = async () => {
    setTesting(true); setTestResult(null);
    try {
      const { data } = await api.post("/whatsapp/config/test");
      setTestResult(data);
      if (data.ok) toast.success(data.message);
      else toast.error(data.message || "Test failed");
    } catch (err) {
      const detail = err.response?.data?.detail || "Test failed";
      setTestResult({ ok: false, message: detail });
      toast.error(detail);
    } finally { setTesting(false); }
  };

  const quickSend = async (e) => {
    e.preventDefault();
    setSending(true); setSendResult(null);
    try {
      const payload = { to };
      if (quickMode === "template") {
        payload.template_name = quickTpl.trim();
        payload.template_language = quickLang.trim() || "en_US";
      } else {
        payload.message = msg;
      }
      const { data } = await api.post("/whatsapp/send-message", payload);
      setSendResult({ ok: true, ...data });
      toast.success(data.mode === "live" ? "Sent via Meta Cloud API!" : "Sent in MOCK mode");
    } catch (err) {
      const detail = err.response?.data?.detail || "Send failed";
      setSendResult({ ok: false, message: detail });
      toast.error(detail);
    } finally { setSending(false); }
  };

  if (!cfg) return <div className="p-6 text-sm text-muted-foreground" data-testid="wa-settings-loading">Loading…</div>;

  // Super Admin fallback view (this page is really for company admins; SA sees a summary + hint)
  if (!user?.company_id) {
    return (
      <div className="space-y-4" data-testid="wa-settings-sa">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">WhatsApp</div>
          <h1 className="text-3xl font-black tracking-tighter">Platform WhatsApp Overview</h1>
          <p className="text-xs text-muted-foreground mt-1">Per-tenant WhatsApp credentials are managed by each Company Admin. This page shows the platform-level status and configured tenants.</p>
        </div>
        <Card className="rounded-sm shadow-none">
          <CardContent className="p-4 space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Platform env:</span>
              {cfg.platform_env_configured
                ? <Badge variant="outline" className="rounded-sm text-[10px] border-emerald-300 text-emerald-700">LIVE (env)</Badge>
                : <Badge variant="outline" className="rounded-sm text-[10px] border-amber-300 text-amber-700">Not configured</Badge>}
            </div>
            <div className="text-xs text-muted-foreground">Tenants with WhatsApp configured: <strong>{cfg.tenant_count || 0}</strong></div>
          </CardContent>
        </Card>
        {cfg.tenants?.length > 0 && (
          <Card className="rounded-sm shadow-none">
            <CardContent className="p-0">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-muted/40">
                    <th className="text-left p-3">Company ID</th>
                    <th className="text-left p-3">Phone Number ID</th>
                    <th className="text-left p-3">Mode</th>
                    <th className="text-left p-3">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {cfg.tenants.map(t => (
                    <tr key={t.company_id} className="border-t" data-testid={`wa-tenant-row-${t.company_id}`}>
                      <td className="p-3 font-mono">{t.company_id}</td>
                      <td className="p-3 font-mono">{t.phone_number_id || "—"}</td>
                      <td className="p-3">
                        {t.mock
                          ? <Badge variant="outline" className="rounded-sm text-[10px] border-amber-300 text-amber-700">MOCK</Badge>
                          : <Badge variant="outline" className="rounded-sm text-[10px] border-emerald-300 text-emerald-700">LIVE</Badge>}
                      </td>
                      <td className="p-3 text-muted-foreground">{t.updated_at?.slice(0, 19)?.replace("T", " ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}
        {/* Platform-level templates from env WABA */}
        {cfg.platform_env_configured && templatesCard}
        <TemplateBuilderDialog open={showBuilder} onOpenChange={setShowBuilder} onCreated={loadTemplates} />
      </div>
    );
  }

  const isConfigured = !!cfg.configured;
  const isLive = isConfigured && !cfg.mock && cfg.access_token_set && cfg.phone_number_id;

  return (
    <div className="space-y-4 max-w-4xl" data-testid="wa-settings-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Channel Setup</div>
          <h1 className="text-3xl font-black tracking-tighter flex items-center gap-3">
            <MessageCircle className="h-7 w-7 text-orange-500" />
            WhatsApp Cloud API
          </h1>
          <p className="text-xs text-muted-foreground mt-1">Connect your own Meta WhatsApp Business Account. Your credentials stay isolated from other tenants.</p>
        </div>
        {isLive
          ? <Badge variant="outline" className="rounded-sm text-[10px] border-emerald-300 text-emerald-700 gap-1"><CheckCircle2 className="h-3 w-3" />LIVE</Badge>
          : <Badge variant="outline" className="rounded-sm text-[10px] border-amber-300 text-amber-700">{isConfigured ? "MOCK" : "Not configured"}</Badge>}
      </div>

      {/* Meta Embedded Signup — one-click WhatsApp onboarding (tenant admins only) */}
      {user?.company_id && (
        <Card className="rounded-sm shadow-none border-blue-200 dark:border-blue-900/50 bg-blue-50/30 dark:bg-blue-900/10" data-testid="wa-embedded-signup-card">
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <PlugZap className="h-4 w-4 text-blue-600" />
              <div className="text-xs font-semibold uppercase tracking-wider text-blue-900 dark:text-blue-200">Recommended · Meta Embedded Signup</div>
            </div>
            <div className="text-xs text-muted-foreground">
              Connect your WhatsApp Business Account with one click via Meta&apos;s official signup dialog. No manual token copy-paste — we exchange the code server-side and store your credentials securely.
            </div>
            {signupCfg?.enabled ? (
              <Button type="button" onClick={startEmbeddedSignup} disabled={signupBusy}
                className="rounded-sm gap-2 bg-blue-600 hover:bg-blue-700 text-white" data-testid="wa-embedded-signup-button">
                <MessageCircle className="h-3.5 w-3.5" /> {signupBusy ? "Opening Meta dialog…" : "Connect WhatsApp with Facebook"}
              </Button>
            ) : (
              <div className="p-2 rounded-sm border border-dashed border-blue-300 bg-white/50 dark:bg-black/20 text-[11px] text-muted-foreground">
                Embedded Signup is not yet configured on this platform. Your Super Admin can enable it by setting <code className="bg-muted px-1 rounded">FB_APP_ID</code>, <code className="bg-muted px-1 rounded">FB_APP_SECRET</code>, and <code className="bg-muted px-1 rounded">FB_CONFIG_ID</code> in the backend env, then restart. Until then, use manual credential setup below.
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Step 1: webhook info shown only after config exists (verify_token is generated) */}
      {isConfigured && (
        <Card className="rounded-sm shadow-none border-orange-200 dark:border-orange-900/50">
          <CardContent className="p-4 space-y-3">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Step 1 · Configure webhook in Meta Dashboard</div>
            <div className="text-xs text-muted-foreground">
              In your <strong>Meta App → WhatsApp → Configuration → Webhook</strong>, paste these values and subscribe the <code className="bg-muted px-1 rounded">messages</code> field.
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <CopyField label="Callback URL" value={cfg.webhook_url || (BACKEND_URL + cfg.webhook_path)} testId="wa-callback-url" />
              <CopyField label="Verify Token (unique to your company)" value={cfg.verify_token} testId="wa-verify-token" />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 2: credential form */}
      <Card className="rounded-sm shadow-none">
        <CardContent className="p-4 space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Step {isConfigured ? "2" : "1"} · Your Meta credentials</div>
          <form onSubmit={save} className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="space-y-1 md:col-span-2">
                <Label className="text-xs">Access Token {isConfigured && <span className="text-muted-foreground">(leave blank to keep existing)</span>}</Label>
                <div className="flex gap-2">
                  <Input
                    type={reveal.token ? "text" : "password"}
                    placeholder={cfg.access_token_preview || "EAAG..."}
                    value={form.access_token}
                    onChange={e => setForm(f => ({ ...f, access_token: e.target.value }))}
                    className="rounded-sm font-mono"
                    data-testid="wa-access-token-input"
                  />
                  <Button type="button" variant="outline" size="icon" className="rounded-sm h-9 w-9 shrink-0" onClick={() => setReveal(r => ({ ...r, token: !r.token }))} data-testid="wa-toggle-token-visibility">
                    {reveal.token ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </Button>
                </div>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Phone Number ID</Label>
                <Input
                  required
                  placeholder="123456789012345"
                  value={form.phone_number_id}
                  onChange={e => setForm(f => ({ ...f, phone_number_id: e.target.value }))}
                  className="rounded-sm font-mono"
                  data-testid="wa-phone-id-input"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">WhatsApp Business Account (WABA) ID <span className="text-muted-foreground">— required to list templates</span></Label>
                <Input
                  placeholder="831164916601218"
                  value={form.waba_id}
                  onChange={e => setForm(f => ({ ...f, waba_id: e.target.value }))}
                  className="rounded-sm font-mono"
                  data-testid="wa-waba-id-input"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Graph API Version</Label>
                <Input
                  placeholder="v22.0"
                  value={form.graph_version}
                  onChange={e => setForm(f => ({ ...f, graph_version: e.target.value }))}
                  className="rounded-sm font-mono"
                  data-testid="wa-graph-version-input"
                />
              </div>
              <div className="space-y-1 md:col-span-2">
                <Label className="text-xs">App Secret <span className="text-muted-foreground">(optional · enables X-Hub-Signature-256 webhook signing)</span></Label>
                <div className="flex gap-2">
                  <Input
                    type={reveal.secret ? "text" : "password"}
                    placeholder={cfg.app_secret_preview || "not configured"}
                    value={form.app_secret}
                    onChange={e => setForm(f => ({ ...f, app_secret: e.target.value }))}
                    className="rounded-sm font-mono"
                    data-testid="wa-app-secret-input"
                  />
                  <Button type="button" variant="outline" size="icon" className="rounded-sm h-9 w-9 shrink-0" onClick={() => setReveal(r => ({ ...r, secret: !r.secret }))} data-testid="wa-toggle-secret-visibility">
                    {reveal.secret ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </Button>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-6 pt-1">
              <div className="flex items-center gap-2">
                <Switch id="wa-mock-toggle" checked={form.mock} onCheckedChange={v => setForm(f => ({ ...f, mock: v }))} data-testid="wa-mock-toggle" />
                <Label htmlFor="wa-mock-toggle" className="text-xs cursor-pointer">Mock mode (skip live Meta calls)</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch id="wa-active-toggle" checked={form.is_active} onCheckedChange={v => setForm(f => ({ ...f, is_active: v }))} data-testid="wa-active-toggle" />
                <Label htmlFor="wa-active-toggle" className="text-xs cursor-pointer">Active</Label>
              </div>
            </div>

            <div className="flex flex-wrap gap-2 pt-2">
              <Button type="submit" disabled={saving} className="rounded-sm gap-1" data-testid="wa-save-button">
                <Save className="h-3.5 w-3.5" /> {saving ? "Saving…" : isConfigured ? "Update credentials" : "Save credentials"}
              </Button>
              {isConfigured && (
                <>
                  <Button type="button" variant="outline" disabled={testing} onClick={runTest} className="rounded-sm gap-1" data-testid="wa-test-button">
                    <PlugZap className="h-3.5 w-3.5" /> {testing ? "Testing…" : "Test connection"}
                  </Button>
                  <Button type="button" variant="outline" onClick={remove} className="rounded-sm gap-1 text-red-600 hover:text-red-700" data-testid="wa-delete-button">
                    <Trash2 className="h-3.5 w-3.5" /> Remove
                  </Button>
                </>
              )}
            </div>

            {testResult && (
              <div className={`p-2 rounded-sm border text-xs flex items-start gap-2 ${testResult.ok ? "border-emerald-300 bg-emerald-50 dark:bg-emerald-900/20" : "border-red-300 bg-red-50 dark:bg-red-900/20"}`} data-testid="wa-test-result">
                {testResult.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" /> : <AlertTriangle className="h-4 w-4 text-red-600 shrink-0" />}
                <div>
                  <strong>{testResult.ok ? "Success" : "Failed"}</strong> · {testResult.message}
                  {testResult.phone_number_id && <div className="text-muted-foreground mt-0.5">Phone Number ID: <span className="font-mono">{testResult.phone_number_id}</span></div>}
                </div>
              </div>
            )}
          </form>
        </CardContent>
      </Card>

      {/* Step 2.5: Templates catalog (auto-fetched from Meta) */}
      {isConfigured && templatesCard}

      {/* Step 3: quick send test */}
      {isConfigured && (
        <Card className="rounded-sm shadow-none">
          <CardContent className="p-4 space-y-3">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Step 3 · Send a test message</div>
            <div className="text-[11px] text-muted-foreground -mt-1">
              Free-form text is only delivered if the recipient messaged your business in the last 24h. Use an approved template that you&apos;ve created and gotten approved by Meta. <strong className="text-red-600">Note: <code className="bg-muted px-1 rounded">hello_world</code> only works from Meta&apos;s sandbox test number — not from real business numbers.</strong>
            </div>
            <div className="flex items-center gap-2">
              <Button type="button" size="sm" variant={quickMode === "freeform" ? "default" : "outline"} className="rounded-sm h-7 text-xs" onClick={() => setQuickMode("freeform")} data-testid="quick-mode-freeform">
                Free-form
              </Button>
              <Button type="button" size="sm" variant={quickMode === "template" ? "default" : "outline"} className="rounded-sm h-7 text-xs" onClick={() => setQuickMode("template")} data-testid="quick-mode-template">
                Template (recommended)
              </Button>
            </div>
            <form onSubmit={quickSend} className="space-y-2">
              {quickMode === "template" ? (
                <div className="grid grid-cols-1 md:grid-cols-[220px_1fr_auto] gap-2">
                  <Input required placeholder="+91XXXXXXXXXX" value={to} onChange={e => setTo(e.target.value)} className="rounded-sm" data-testid="wa-quicksend-to" />
                  <select
                    required
                    value={`${quickTpl}|${quickLang}`}
                    onChange={e => {
                      const [n, l] = e.target.value.split("|");
                      setQuickTpl(n); setQuickLang(l);
                    }}
                    className="rounded-sm border bg-background px-3 h-9 text-sm font-mono"
                    data-testid="wa-quicksend-template-select"
                  >
                    {(!templates || templates.length === 0) && (
                      <option value="hello_world|en_US">hello_world (en_US) — load templates for full list</option>
                    )}
                    {templates && templates.filter(t => t.status === "APPROVED").map(t => (
                      <option key={`${t.name}_${t.language}`} value={`${t.name}|${t.language}`}>
                        {t.name === "hello_world" ? "⚠ " : ""}{t.name} · {t.language} · [{t.category}]{t.variable_count > 0 ? ` · ${t.variable_count} var${t.variable_count > 1 ? "s" : ""}` : ""}{t.name === "hello_world" ? " · SANDBOX-ONLY" : ""}
                      </option>
                    ))}
                  </select>
                  <Button type="submit" disabled={sending} className="rounded-sm gap-1" data-testid="wa-quicksend-button">
                    <Send className="h-3.5 w-3.5" /> {sending ? "Sending…" : "Send"}
                  </Button>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-[220px_1fr_auto] gap-2">
                  <Input required placeholder="+91XXXXXXXXXX" value={to} onChange={e => setTo(e.target.value)} className="rounded-sm" data-testid="wa-quicksend-to" />
                  <Input required placeholder="Message" value={msg} onChange={e => setMsg(e.target.value)} className="rounded-sm" data-testid="wa-quicksend-message" />
                  <Button type="submit" disabled={sending} className="rounded-sm gap-1" data-testid="wa-quicksend-button">
                    <Send className="h-3.5 w-3.5" /> {sending ? "Sending…" : "Send"}
                  </Button>
                </div>
              )}
            </form>
            {sendResult && (
              <div className={`p-2 rounded-sm border text-xs flex items-start gap-2 ${sendResult.ok ? "border-emerald-300 bg-emerald-50 dark:bg-emerald-900/20" : "border-red-300 bg-red-50 dark:bg-red-900/20"}`} data-testid="wa-quicksend-result">
                {sendResult.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" /> : <AlertTriangle className="h-4 w-4 text-red-600 shrink-0" />}
                <div>
                  {sendResult.ok
                    ? <span>Sent in <strong>{(sendResult.mode || "").toUpperCase()}</strong> mode · id: <span className="font-mono">{sendResult.provider_message_id}</span></span>
                    : <span>{sendResult.message}</span>}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
      <TemplateBuilderDialog open={showBuilder} onOpenChange={setShowBuilder} onCreated={loadTemplates} />
    </div>
  );
}
