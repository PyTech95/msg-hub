import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { ChannelBadge } from "@/components/Badges";
import { Plus, Trash2, KeyRound, Pencil, PlugZap, Eye, EyeOff, CheckCircle2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

// Suggested credential schemas per provider so super admins know what to fill
const CRED_SCHEMA = {
  twilio:  [{ key: "account_sid", label: "Account SID" }, { key: "auth_token", label: "Auth Token", secret: true }, { key: "from", label: "From number / Sender ID" }],
  gupshup: [{ key: "api_key",     label: "API Key", secret: true }, { key: "app_name", label: "App Name" }, { key: "source", label: "Source number" }],
  exotel:  [{ key: "account_sid", label: "Account SID" }, { key: "api_key", label: "API Key", secret: true }, { key: "api_token", label: "API Token", secret: true }, { key: "from", label: "Caller ID" }],
  rbm:     [{ key: "agent_id", label: "RBM Agent ID" }, { key: "service_account_json", label: "Service Account JSON", secret: true, textarea: true }],
  mock:    [{ key: "note", label: "Note (optional)" }],
};

const blank = { name: "", channel: "sms", provider_key: "twilio", config: "{}", is_active: true, mock: true };

export default function Providers() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(blank);

  const [credOpen, setCredOpen] = useState(false);
  const [credProvider, setCredProvider] = useState(null);
  const [creds, setCreds] = useState({});
  const [credMock, setCredMock] = useState(true);
  const [reveal, setReveal] = useState({});
  const [testResult, setTestResult] = useState(null);

  const load = () => api.get("/providers").then(r => setItems(r.data));
  useEffect(() => { load(); }, []);

  const openCreate = () => { setEditing(null); setForm(blank); setOpen(true); };
  const openEdit = (p) => {
    setEditing(p);
    setForm({
      name: p.name, channel: p.channel, provider_key: p.provider_key,
      config: JSON.stringify(p.config || {}, null, 2),
      is_active: p.is_active !== false, mock: !!p.mock,
    });
    setOpen(true);
  };

  const save = async (e) => {
    e.preventDefault();
    let cfg = {};
    try { cfg = JSON.parse(form.config || "{}"); } catch { toast.error("Invalid JSON config"); return; }
    const payload = { ...form, config: cfg };
    try {
      if (editing) {
        await api.patch(`/providers/${editing.id}`, payload);
        toast.success("Provider updated");
      } else {
        await api.post("/providers", payload);
        toast.success("Provider added");
      }
      setOpen(false); setForm(blank); setEditing(null); load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete provider?")) return;
    try { await api.delete(`/providers/${id}`); toast.success("Deleted"); load(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const openCredentials = async (p) => {
    setCredProvider(p);
    setReveal({});
    setTestResult(null);
    try {
      const { data } = await api.get(`/providers/${p.id}/credentials`);
      const schema = CRED_SCHEMA[p.provider_key] || [];
      const initial = {};
      for (const f of schema) initial[f.key] = data.credentials[f.key] || "";
      // include any extra existing keys not in the schema
      for (const k of Object.keys(data.credentials || {})) if (!(k in initial)) initial[k] = data.credentials[k];
      setCreds(initial);
      setCredMock(data.mock);
      setCredOpen(true);
    } catch (err) { toast.error(err.response?.data?.detail || "Failed to load credentials"); }
  };

  const saveCredentials = async () => {
    try {
      await api.put(`/providers/${credProvider.id}/credentials`, { credentials: creds, mock: credMock });
      toast.success("Credentials saved");
      setCredOpen(false);
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const testConnection = async (id) => {
    setTestResult({ loading: true });
    try {
      const { data } = await api.post(`/providers/${id}/test`);
      setTestResult(data);
      if (data.ok) toast.success(`${data.mode.toUpperCase()} test passed in ${data.latency_ms || 0}ms`);
      else toast.error(data.message || "Test failed");
    } catch (err) {
      setTestResult({ ok: false, message: err.response?.data?.detail || "Test failed" });
    }
  };

  const isSuperAdmin = user?.role === "super_admin";
  const schema = credProvider ? (CRED_SCHEMA[credProvider.provider_key] || []) : [];

  return (
    <div className="space-y-4" data-testid="providers-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Integrations</div>
          <h1 className="text-3xl font-black tracking-tighter">Provider Settings</h1>
          <p className="text-xs text-muted-foreground mt-1">Add API credentials when you're ready to go live. Until then every provider runs in <strong>Mock</strong> mode.</p>
        </div>
        <Button className="rounded-sm gap-2" onClick={openCreate} data-testid="new-provider-button"><Plus className="h-4 w-4" /> Add Provider</Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {items.map(p => (
          <Card key={p.id} className="rounded-sm shadow-none" data-testid={`provider-card-${p.id}`}>
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center justify-between">
                <ChannelBadge channel={p.channel} />
                {p.mock
                  ? <Badge variant="outline" className="rounded-sm text-[10px] border-amber-300 text-amber-700">MOCK</Badge>
                  : <Badge variant="outline" className="rounded-sm text-[10px] border-emerald-300 text-emerald-700 gap-1"><CheckCircle2 className="h-3 w-3" />LIVE</Badge>}
              </div>
              <div className="font-semibold">{p.name}</div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">{p.provider_key}</div>
              <div className="text-xs flex items-center gap-1">
                <KeyRound className="h-3 w-3 text-muted-foreground" />
                {p.credentials && Object.keys(p.credentials).length > 0 ? <span className="text-emerald-600">credentials set</span> : <span className="text-muted-foreground">no credentials</span>}
              </div>
              <div className="flex flex-wrap justify-end gap-1 pt-1">
                <Button variant="outline" size="sm" className="rounded-sm gap-1" onClick={() => testConnection(p.id)} data-testid={`test-provider-${p.id}`}>
                  <PlugZap className="h-3 w-3" /> Test
                </Button>
                {isSuperAdmin && (
                  <Button variant="outline" size="sm" className="rounded-sm gap-1" onClick={() => openCredentials(p)} data-testid={`credentials-provider-${p.id}`}>
                    <KeyRound className="h-3 w-3" /> Credentials
                  </Button>
                )}
                <Button variant="ghost" size="sm" className="rounded-sm gap-1" onClick={() => openEdit(p)} data-testid={`edit-provider-${p.id}`}>
                  <Pencil className="h-3 w-3" />
                </Button>
                {isSuperAdmin && (
                  <Button variant="ghost" size="sm" className="text-red-600 rounded-sm gap-1" onClick={() => del(p.id)} data-testid={`delete-provider-${p.id}`}>
                    <Trash2 className="h-3 w-3" />
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Create / Edit provider dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="rounded-sm">
          <DialogHeader><DialogTitle>{editing ? "Edit Provider" : "Add Provider Account"}</DialogTitle></DialogHeader>
          <form onSubmit={save} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Name</Label><Input required value={form.name} onChange={e=>setForm({...form,name:e.target.value})} className="rounded-sm" data-testid="provider-name-input" /></div>
              <div>
                <Label>Channel</Label>
                <select value={form.channel} onChange={e=>setForm({...form,channel:e.target.value})}
                  className="h-9 w-full px-3 rounded-sm border border-border bg-background text-sm">
                  <option value="sms">sms</option><option value="whatsapp">whatsapp</option>
                  <option value="rcs">rcs</option><option value="voice">voice</option>
                </select>
              </div>
              <div>
                <Label>Provider</Label>
                <select value={form.provider_key} onChange={e=>setForm({...form,provider_key:e.target.value})}
                  className="h-9 w-full px-3 rounded-sm border border-border bg-background text-sm" data-testid="provider-key-select">
                  <option value="twilio">twilio</option>
                  <option value="gupshup">gupshup</option>
                  <option value="exotel">exotel</option>
                  <option value="rbm">rbm</option>
                  <option value="mock">mock</option>
                </select>
              </div>
              <div className="flex items-end gap-2">
                <Switch checked={form.mock} onCheckedChange={v=>setForm({...form,mock:v})} data-testid="provider-mock-switch" />
                <span className="text-sm">Mock mode</span>
              </div>
            </div>
            <div>
              <Label>Config (non-sensitive JSON — e.g. webhook URLs, region)</Label>
              <textarea value={form.config} onChange={e=>setForm({...form,config:e.target.value})}
                rows={4} className="w-full font-mono text-xs p-2 rounded-sm border border-border bg-background" data-testid="provider-config-input" />
              <div className="text-xs text-muted-foreground mt-1">API keys live in the Credentials vault — open the provider card → <strong>Credentials</strong>.</div>
            </div>
            <DialogFooter><Button type="submit" className="rounded-sm" data-testid="save-provider-button">{editing ? "Save" : "Create"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Credentials manager dialog */}
      <Dialog open={credOpen} onOpenChange={setCredOpen}>
        <DialogContent className="rounded-sm max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><KeyRound className="h-4 w-4" /> {credProvider?.name} — Credentials</DialogTitle>
            <DialogDescription>API keys are masked when read back. Edit a value to rotate it; leave the masked placeholder untouched to keep the existing key.</DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 rounded-sm border border-border">
              <div>
                <div className="text-sm font-semibold">Mock mode</div>
                <div className="text-xs text-muted-foreground">When ON, the in-process mock adapter is used. Turn OFF only after adding real credentials.</div>
              </div>
              <Switch checked={credMock} onCheckedChange={setCredMock} data-testid="cred-mock-switch" />
            </div>

            {schema.length === 0 && (
              <div className="text-xs text-muted-foreground border border-dashed border-border rounded-sm p-3">
                No schema for <strong>{credProvider?.provider_key}</strong>. Add free-form keys below.
              </div>
            )}

            {schema.map(f => {
              const val = creds[f.key] || "";
              const show = reveal[f.key];
              const isMasked = f.secret && val && !show && val.includes("•");
              return (
                <div key={f.key} className="space-y-1">
                  <Label className="flex items-center gap-2">{f.label} {f.secret && <KeyRound className="h-3 w-3 text-muted-foreground" />}</Label>
                  <div className="flex gap-2">
                    {f.textarea ? (
                      <textarea value={val} onChange={e => setCreds({...creds, [f.key]: e.target.value})}
                        rows={4} className="w-full font-mono text-xs p-2 rounded-sm border border-border bg-background"
                        placeholder={f.secret ? "Paste secret JSON…" : ""} data-testid={`cred-${f.key}`} />
                    ) : (
                      <Input
                        type={f.secret && !show ? "password" : "text"}
                        value={val}
                        onChange={e => setCreds({...creds, [f.key]: e.target.value})}
                        className={`rounded-sm font-mono text-xs ${isMasked ? "text-muted-foreground" : ""}`}
                        placeholder={f.secret ? "Paste API key / secret…" : ""}
                        data-testid={`cred-${f.key}`}
                      />
                    )}
                    {f.secret && !f.textarea && (
                      <Button type="button" variant="outline" size="icon" className="rounded-sm h-9 w-9" onClick={() => setReveal({...reveal, [f.key]: !show})} data-testid={`reveal-${f.key}`}>
                        {show ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}

            {testResult && (
              <div className={`p-3 rounded-sm border text-xs flex items-start gap-2 ${testResult.ok ? "border-emerald-300 bg-emerald-50 dark:bg-emerald-900/20" : "border-red-300 bg-red-50 dark:bg-red-900/20"}`}>
                {testResult.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" /> : <AlertTriangle className="h-4 w-4 text-red-600 shrink-0" />}
                <div>
                  <div className="font-semibold">{testResult.loading ? "Testing…" : testResult.ok ? `${(testResult.mode || "").toUpperCase()} test passed` : "Test failed"}</div>
                  <div className="text-muted-foreground">{testResult.message || ""} {testResult.latency_ms ? `(${testResult.latency_ms}ms)` : ""}</div>
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="gap-2">
            <Button variant="outline" className="rounded-sm gap-1" onClick={() => testConnection(credProvider.id)} data-testid="cred-test-button">
              <PlugZap className="h-3.5 w-3.5" /> Test connection
            </Button>
            <Button className="rounded-sm" onClick={saveCredentials} data-testid="cred-save-button">Save credentials</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
