import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { ChannelBadge } from "@/components/Badges";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function Providers() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", channel: "sms", provider_key: "mock", config: "{}", is_active: true, mock: true });

  const load = () => api.get("/providers").then(r => setItems(r.data));
  useEffect(() => { load(); }, []);

  const save = async (e) => {
    e.preventDefault();
    let cfg = {};
    try { cfg = JSON.parse(form.config || "{}"); } catch { toast.error("Invalid JSON config"); return; }
    await api.post("/providers", { ...form, config: cfg });
    toast.success("Provider added");
    setOpen(false);
    setForm({ name: "", channel: "sms", provider_key: "mock", config: "{}", is_active: true, mock: true });
    load();
  };

  const del = async (id) => {
    if (!window.confirm("Delete provider?")) return;
    await api.delete(`/providers/${id}`);
    toast.success("Deleted"); load();
  };

  return (
    <div className="space-y-4" data-testid="providers-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Integrations</div>
          <h1 className="text-3xl font-black tracking-tighter">Provider Settings</h1>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button className="rounded-sm gap-2" data-testid="new-provider-button"><Plus className="h-4 w-4" /> Add Provider</Button>
          </DialogTrigger>
          <DialogContent className="rounded-sm">
            <DialogHeader><DialogTitle>Add Provider Account</DialogTitle></DialogHeader>
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
                  <Label>Provider key</Label>
                  <select value={form.provider_key} onChange={e=>setForm({...form,provider_key:e.target.value})}
                    className="h-9 w-full px-3 rounded-sm border border-border bg-background text-sm">
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
                <Label>Config (JSON)</Label>
                <textarea value={form.config} onChange={e=>setForm({...form,config:e.target.value})}
                  rows={4} className="w-full font-mono text-xs p-2 rounded-sm border border-border bg-background" data-testid="provider-config-input" />
              </div>
              <DialogFooter><Button type="submit" className="rounded-sm" data-testid="save-provider-button">Save</Button></DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {items.map(p => (
          <Card key={p.id} className="rounded-sm shadow-none" data-testid={`provider-card-${p.id}`}>
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center justify-between">
                <ChannelBadge channel={p.channel} />
                {p.mock && <Badge variant="outline" className="rounded-sm text-[10px] border-amber-300 text-amber-700">MOCK</Badge>}
              </div>
              <div className="font-semibold">{p.name}</div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">{p.provider_key}</div>
              <pre className="text-xs p-2 rounded-sm bg-muted/40 border border-border overflow-x-auto">{JSON.stringify(p.config, null, 2)}</pre>
              <div className="flex justify-end">
                <Button variant="ghost" size="sm" className="text-red-600 rounded-sm gap-1" onClick={() => del(p.id)} data-testid={`delete-provider-${p.id}`}>
                  <Trash2 className="h-3 w-3" /> Delete
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
