import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/Badges";
import { Phone, Plus, Send, Loader2, Mic, BotMessageSquare } from "lucide-react";
import { toast } from "sonner";

const DEFAULT_SCRIPT = "Hello {{name}}, this is an automated reminder from the property tax department. Your bill of INR {{amount}} for property {{property_id}} at {{address}} is due on {{due_date}}. Please pay within 7 days to avoid penalty. Thank you.";

const VOICES = [
  { id: "female", label: "Female (en-IN)" },
  { id: "male", label: "Male (en-IN)" },
  { id: "neutral", label: "Neutral" },
];

export default function VoiceCampaigns() {
  const [campaigns, setCampaigns] = useState([]);
  const [bills, setBills] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", script: DEFAULT_SCRIPT, voice: "female" });
  const [audience, setAudience] = useState("bills"); // bills | contacts
  const [selected, setSelected] = useState(new Set());
  const [creating, setCreating] = useState(false);

  const load = async () => {
    const [c, b, ct] = await Promise.all([
      api.get("/voice-campaigns"),
      api.get("/bills"),
      api.get("/contacts"),
    ]);
    setCampaigns(c.data); setBills(b.data); setContacts(ct.data);
  };
  useEffect(() => { load(); const t = setInterval(load, 4000); return () => clearInterval(t); }, []);

  const openCreate = () => {
    setForm({ name: "", script: DEFAULT_SCRIPT, voice: "female" });
    setSelected(new Set()); setAudience("bills"); setOpen(true);
  };

  const launch = async (e) => {
    e.preventDefault();
    if (selected.size === 0) return toast.error("Select at least one target");
    setCreating(true);
    try {
      const { data } = await api.post("/voice-campaigns", {
        name: form.name, script: form.script, voice: form.voice,
        bill_ids: audience === "bills" ? Array.from(selected) : undefined,
        contact_ids: audience === "contacts" ? Array.from(selected) : undefined,
      });
      toast.success(`Voice campaign launched · ${data.queued} calls dispatching`);
      setOpen(false);
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setCreating(false); }
  };

  const targets = audience === "bills" ? bills : contacts;
  const allSel = targets.length > 0 && selected.size === targets.length;
  const toggleAll = () => setSelected(allSel ? new Set() : new Set(targets.map(t => t.id)));
  const toggle = (id) => setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  return (
    <div className="space-y-4" data-testid="voice-campaigns-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">AI Voice</div>
          <h1 className="text-3xl font-black tracking-tighter flex items-center gap-2"><BotMessageSquare className="h-6 w-6" /> Voice Campaigns</h1>
          <p className="text-xs text-muted-foreground mt-1">Script-based AI voice calls with variables — dispatched to bills or contacts.</p>
        </div>
        <Button onClick={openCreate} className="rounded-sm gap-2" data-testid="new-voice-campaign-button"><Plus className="h-4 w-4" /> New Voice Campaign</Button>
      </div>

      <Card className="rounded-sm shadow-none">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Voice</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Targets</th>
                <th className="px-3 py-2 text-right">Initiated</th>
                <th className="px-3 py-2 text-right">Completed</th>
                <th className="px-3 py-2 text-right">No-answer</th>
                <th className="px-3 py-2 text-right">When</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map(c => (
                <tr key={c.id} className="border-t border-border hover:bg-accent/40 row-voice" data-testid={`voice-campaign-row-${c.id}`}>
                  <td className="px-3 py-2 font-medium">{c.name}</td>
                  <td className="px-3 py-2 text-xs"><Mic className="h-3 w-3 inline mr-1" />{c.voice}</td>
                  <td className="px-3 py-2"><StatusBadge status={c.status} /></td>
                  <td className="px-3 py-2 text-right font-mono">{c.target_count}</td>
                  <td className="px-3 py-2 text-right font-mono">{c.stats?.initiated ?? 0}</td>
                  <td className="px-3 py-2 text-right font-mono">{c.stats?.completed ?? 0}</td>
                  <td className="px-3 py-2 text-right font-mono">{c.stats?.["no-answer"] ?? 0}</td>
                  <td className="px-3 py-2 text-right text-xs font-mono">{new Date(c.created_at).toLocaleString()}</td>
                </tr>
              ))}
              {campaigns.length === 0 && <tr><td colSpan={8} className="text-center text-muted-foreground py-10">No voice campaigns yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="rounded-sm max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><BotMessageSquare className="h-5 w-5" /> New AI Voice Campaign</DialogTitle>
            <DialogDescription>Variables: {`{{name}} {{phone}} {{property_id}} {{address}} {{amount}} {{due_date}}`}</DialogDescription>
          </DialogHeader>
          <form onSubmit={launch} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Campaign name</Label><Input required value={form.name} onChange={e=>setForm({...form,name:e.target.value})} className="rounded-sm" data-testid="voice-camp-name-input" /></div>
              <div>
                <Label>Voice</Label>
                <select value={form.voice} onChange={e=>setForm({...form,voice:e.target.value})}
                  className="h-9 w-full px-3 rounded-sm border border-border bg-background text-sm" data-testid="voice-camp-voice-select">
                  {VOICES.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
                </select>
              </div>
            </div>
            <div>
              <Label>Script <span className="text-muted-foreground text-xs">(spoken to each recipient with variables substituted)</span></Label>
              <Textarea required rows={5} value={form.script} onChange={e=>setForm({...form,script:e.target.value})} className="rounded-sm" data-testid="voice-camp-script-input" />
            </div>
            <div>
              <Label>Audience</Label>
              <div className="flex gap-2 mt-1">
                <Button type="button" variant={audience === "bills" ? "default" : "outline"} size="sm" className="rounded-sm" onClick={() => { setAudience("bills"); setSelected(new Set()); }} data-testid="voice-audience-bills">Bills ({bills.length})</Button>
                <Button type="button" variant={audience === "contacts" ? "default" : "outline"} size="sm" className="rounded-sm" onClick={() => { setAudience("contacts"); setSelected(new Set()); }} data-testid="voice-audience-contacts">Contacts ({contacts.length})</Button>
              </div>
            </div>
            <div className="border border-border rounded-sm max-h-64 overflow-y-auto">
              <div className="flex items-center justify-between p-2 border-b border-border bg-muted/40 text-xs">
                <span>{selected.size} of {targets.length} selected</span>
                <button type="button" onClick={toggleAll} className="text-xs underline" data-testid="voice-select-all">{allSel ? "Clear" : "Select all"}</button>
              </div>
              {targets.map(t => (
                <label key={t.id} className="flex items-center gap-3 p-2 border-b border-border text-xs cursor-pointer hover:bg-accent/40" data-testid={`voice-target-${t.id}`}>
                  <Checkbox checked={selected.has(t.id)} onCheckedChange={() => toggle(t.id)} />
                  <div className="flex-1">
                    <div className="font-medium">{t.name || "—"} {t.property_id && <span className="font-mono text-muted-foreground">{t.property_id}</span>}</div>
                    <div className="text-muted-foreground font-mono">{t.phone || "no phone"}</div>
                  </div>
                </label>
              ))}
              {targets.length === 0 && <div className="text-sm text-muted-foreground p-4 text-center">No {audience} available.</div>}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={creating || selected.size === 0} className="rounded-sm gap-2" data-testid="voice-camp-launch">
                {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Phone className="h-4 w-4" />}
                Launch {selected.size} {selected.size === 1 ? "call" : "calls"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
