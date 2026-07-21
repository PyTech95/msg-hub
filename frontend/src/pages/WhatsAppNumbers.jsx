import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Smartphone, Plus, Trash2, Star, StarOff, RefreshCw, PlugZap, CheckCircle2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const fmt = (ts) => (ts ? new Date(ts).toLocaleString() : "—");

const qualityColor = (q) => {
  const s = (q || "").toUpperCase();
  if (s === "GREEN" || s === "HIGH") return "bg-emerald-100 text-emerald-700 border-emerald-300";
  if (s === "YELLOW" || s === "MEDIUM") return "bg-amber-100 text-amber-700 border-amber-300";
  if (s === "RED" || s === "LOW") return "bg-red-100 text-red-700 border-red-300";
  return "bg-muted text-muted-foreground";
};

export default function WhatsAppNumbers() {
  const { user } = useAuth();
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({
    phone_number_id: "", waba_id: "", access_token: "", app_secret: "",
    display_phone_number: "", verified_name: "",
    graph_version: "v22.0", mock: false, is_primary: false,
  });

  const load = async () => {
    try {
      const { data } = await api.get("/whatsapp/phone-numbers");
      setRows(data);
    } catch (err) { toast.error(err.response?.data?.detail || "Failed to load"); }
  };
  useEffect(() => { load(); }, []);

  const addNumber = async () => {
    if (!form.phone_number_id.trim() || !form.access_token.trim()) {
      toast.error("Phone Number ID and Access Token are required"); return;
    }
    setBusy(true);
    try {
      await api.post("/whatsapp/phone-numbers", form);
      toast.success("Number added");
      setShowAdd(false);
      setForm({ phone_number_id: "", waba_id: "", access_token: "", app_secret: "",
        display_phone_number: "", verified_name: "", graph_version: "v22.0", mock: false, is_primary: false });
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Add failed"); }
    finally { setBusy(false); }
  };

  const setPrimary = async (phoneNumberId) => {
    try {
      await api.patch(`/whatsapp/phone-numbers/${encodeURIComponent(phoneNumberId)}`, { is_primary: true });
      toast.success("Set as primary sender");
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Update failed"); }
  };

  const toggleActive = async (row) => {
    try {
      await api.patch(`/whatsapp/phone-numbers/${encodeURIComponent(row.phone_number_id)}`, { is_active: !row.is_active });
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Update failed"); }
  };

  const removeNumber = async (phoneNumberId) => {
    if (!window.confirm(`Remove phone number ${phoneNumberId} from this tenant?`)) return;
    try {
      await api.delete(`/whatsapp/phone-numbers/${encodeURIComponent(phoneNumberId)}`);
      toast.success("Number removed");
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Delete failed"); }
  };

  const testNumber = async (phoneNumberId) => {
    try {
      const { data } = await api.post(`/whatsapp/phone-numbers/${encodeURIComponent(phoneNumberId)}/test`);
      if (data.ok) toast.success(data.message);
      else toast.error(data.message);
    } catch (err) { toast.error(err.response?.data?.detail || "Test failed"); }
  };

  const syncNumber = async (phoneNumberId) => {
    try {
      const { data } = await api.post(`/whatsapp/phone-numbers/${encodeURIComponent(phoneNumberId)}/sync`);
      toast.success(`Synced — quality: ${data.quality_rating || "n/a"}, tier: ${data.messaging_limit || "n/a"}`);
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Sync failed"); }
  };

  if (!rows) return <div className="p-6 text-sm text-muted-foreground" data-testid="wa-numbers-loading">Loading…</div>;

  const isSA = !user?.company_id;

  return (
    <div className="space-y-4" data-testid="wa-numbers-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">WhatsApp</div>
          <h1 className="text-3xl font-black tracking-tighter flex items-center gap-3">
            <Smartphone className="h-7 w-7 text-orange-500" /> Phone Numbers
          </h1>
          <p className="text-xs text-muted-foreground mt-1">
            {isSA ? "All tenant numbers across the platform" : `Manage your WABA phone numbers. ${rows.length} number${rows.length !== 1 ? "s" : ""} connected.`}
          </p>
        </div>
        {!isSA && (
          <Button className="rounded-sm gap-2" onClick={() => setShowAdd(true)} data-testid="add-number-button">
            <Plus className="h-4 w-4" /> Add Number
          </Button>
        )}
      </div>

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-0">
          <table className="w-full text-xs" data-testid="wa-numbers-table">
            <thead>
              <tr className="bg-muted/40">
                {isSA && <th className="text-left p-3">Company</th>}
                <th className="text-left p-3">Display</th>
                <th className="text-left p-3">Phone Number ID</th>
                <th className="text-left p-3">WABA</th>
                <th className="text-left p-3">Quality</th>
                <th className="text-left p-3">Tier</th>
                <th className="text-left p-3">Status</th>
                <th className="text-left p-3">Synced</th>
                <th className="text-left p-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={`${r.company_id}_${r.phone_number_id}`} className="border-t" data-testid={`wa-row-${r.phone_number_id}`}>
                  {isSA && <td className="p-3 font-mono text-muted-foreground">{r.company_id?.slice(0, 8)}</td>}
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      {r.is_primary && <Star className="h-3 w-3 fill-orange-500 text-orange-500" />}
                      <span className="font-semibold">{r.display_phone_number || "—"}</span>
                    </div>
                    <div className="text-[10px] text-muted-foreground">{r.verified_name || ""}</div>
                  </td>
                  <td className="p-3 font-mono">{r.phone_number_id}</td>
                  <td className="p-3 font-mono text-muted-foreground">{r.waba_id?.slice(0, 12) || "—"}</td>
                  <td className="p-3">
                    {r.quality_rating ? <Badge variant="outline" className={`rounded-sm ${qualityColor(r.quality_rating)}`}>{r.quality_rating}</Badge> : <span className="text-muted-foreground">—</span>}
                  </td>
                  <td className="p-3 text-muted-foreground">{r.messaging_limit || "—"}</td>
                  <td className="p-3">
                    <div className="flex flex-col gap-1">
                      {r.mock
                        ? <Badge variant="outline" className="rounded-sm text-[10px] border-amber-300 text-amber-700">MOCK</Badge>
                        : r.is_active
                          ? <Badge className="rounded-sm text-[10px] bg-emerald-100 text-emerald-700 hover:bg-emerald-100">LIVE</Badge>
                          : <Badge variant="outline" className="rounded-sm text-[10px]">DISABLED</Badge>}
                      <div className="text-[10px] text-muted-foreground">via {r.onboarded_via || "manual"}</div>
                    </div>
                  </td>
                  <td className="p-3 text-muted-foreground">{fmt(r.last_synced_at)}</td>
                  <td className="p-3">
                    {!isSA && (
                      <div className="flex items-center gap-1">
                        {!r.is_primary && (
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setPrimary(r.phone_number_id)} title="Set as primary" data-testid={`set-primary-${r.phone_number_id}`}>
                            <StarOff className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => testNumber(r.phone_number_id)} title="Test connection" data-testid={`test-${r.phone_number_id}`}>
                          <PlugZap className="h-3.5 w-3.5" />
                        </Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => syncNumber(r.phone_number_id)} title="Sync from Meta" data-testid={`sync-${r.phone_number_id}`}>
                          <RefreshCw className="h-3.5 w-3.5" />
                        </Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => toggleActive(r)} title={r.is_active ? "Disable" : "Enable"} data-testid={`toggle-${r.phone_number_id}`}>
                          {r.is_active ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> : <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />}
                        </Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-red-600" onClick={() => removeNumber(r.phone_number_id)} title="Remove" data-testid={`delete-${r.phone_number_id}`}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={isSA ? 9 : 8} className="p-6 text-center text-muted-foreground">
                  {isSA ? "No tenant has connected a WhatsApp number yet." : "No numbers connected. Click 'Add Number' to connect your first WhatsApp Business number."}
                </td></tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent data-testid="add-number-dialog" className="max-w-lg">
          <DialogHeader><DialogTitle>Add WhatsApp Business Number</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Phone Number ID *</Label>
                <Input value={form.phone_number_id} onChange={e => setForm({ ...form, phone_number_id: e.target.value.trim() })} placeholder="1234567890" className="rounded-sm font-mono" data-testid="add-phone-id" />
              </div>
              <div>
                <Label className="text-xs">WABA ID</Label>
                <Input value={form.waba_id} onChange={e => setForm({ ...form, waba_id: e.target.value.trim() })} placeholder="1234567890" className="rounded-sm font-mono" data-testid="add-waba-id" />
              </div>
            </div>
            <div>
              <Label className="text-xs">Access Token *</Label>
              <Input value={form.access_token} onChange={e => setForm({ ...form, access_token: e.target.value.trim() })} type="password" className="rounded-sm font-mono" data-testid="add-access-token" />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Display Phone (optional)</Label>
                <Input value={form.display_phone_number} onChange={e => setForm({ ...form, display_phone_number: e.target.value })} placeholder="+91 88826 81195" className="rounded-sm" />
              </div>
              <div>
                <Label className="text-xs">Verified Name (optional)</Label>
                <Input value={form.verified_name} onChange={e => setForm({ ...form, verified_name: e.target.value })} placeholder="MyCompany Sales" className="rounded-sm" />
              </div>
            </div>
            <div className="flex items-center gap-6">
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <Switch checked={form.is_primary} onCheckedChange={(v) => setForm({ ...form, is_primary: v })} data-testid="add-is-primary" />
                Set as primary sender
              </label>
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <Switch checked={form.mock} onCheckedChange={(v) => setForm({ ...form, mock: v })} data-testid="add-mock" />
                Mock mode (skip Meta)
              </label>
            </div>
            <div className="text-[10px] text-muted-foreground">
              Tip: The first number added is automatically the primary sender. You can promote another number later.
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
            <Button onClick={addNumber} disabled={busy} data-testid="add-number-submit">{busy ? "Adding…" : "Add Number"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
