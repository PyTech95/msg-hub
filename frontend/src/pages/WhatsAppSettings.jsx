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
  Save, Trash2, PlugZap, Eye, EyeOff, Send,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

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
    access_token: "", phone_number_id: "", app_secret: "",
    graph_version: "v22.0", mock: false, is_active: true,
  });
  const [reveal, setReveal] = useState({ token: false, secret: false });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  // Quick send-test
  const [to, setTo] = useState("");
  const [msg, setMsg] = useState("Hello from tezsandesh.digital 👋");
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState(null);

  const load = async () => {
    try {
      const { data } = await api.get("/whatsapp/config");
      setCfg(data);
      if (data.configured) {
        setForm(f => ({
          ...f,
          phone_number_id: data.phone_number_id || "",
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

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      // Only send secrets if user typed something; empty string means "leave unchanged"
      const payload = {
        phone_number_id: form.phone_number_id?.trim(),
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
      setForm({ access_token: "", phone_number_id: "", app_secret: "", graph_version: "v22.0", mock: false, is_active: true });
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
      const { data } = await api.post("/whatsapp/send-message", { to, message: msg });
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

      {/* Step 3: quick send test */}
      {isConfigured && (
        <Card className="rounded-sm shadow-none">
          <CardContent className="p-4 space-y-3">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Step 3 · Send a test message</div>
            <form onSubmit={quickSend} className="grid grid-cols-1 md:grid-cols-[220px_1fr_auto] gap-2">
              <Input required placeholder="+91XXXXXXXXXX" value={to} onChange={e => setTo(e.target.value)} className="rounded-sm" data-testid="wa-quicksend-to" />
              <Input required placeholder="Message" value={msg} onChange={e => setMsg(e.target.value)} className="rounded-sm" data-testid="wa-quicksend-message" />
              <Button type="submit" disabled={sending} className="rounded-sm gap-1" data-testid="wa-quicksend-button">
                <Send className="h-3.5 w-3.5" /> {sending ? "Sending…" : "Send"}
              </Button>
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
    </div>
  );
}
