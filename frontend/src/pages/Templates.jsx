import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { ChannelBadge, StatusBadge } from "@/components/Badges";
import { Plus, Trash2, Pencil } from "lucide-react";
import { toast } from "sonner";

const CHANNELS = ["sms", "whatsapp", "rcs", "voice"];
const blank = { name: "", channel: "sms", body: "", category: "utility", status: "approved" };

export default function Templates() {
  const [tpls, setTpls] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(blank);

  const load = () => api.get("/templates").then(r => setTpls(r.data));
  useEffect(() => { load(); }, []);

  const extractVars = (b) => Array.from(new Set([...b.matchAll(/\{\{(\w+)\}\}/g)].map(m => m[1])));

  const openCreate = () => { setEditing(null); setForm(blank); setOpen(true); };
  const openEdit = (t) => {
    setEditing(t);
    setForm({ name: t.name, channel: t.channel, body: t.body, category: t.category || "utility", status: t.status || "approved" });
    setOpen(true);
  };

  const save = async (e) => {
    e.preventDefault();
    const payload = { ...form, variables: extractVars(form.body) };
    try {
      if (editing) {
        await api.patch(`/templates/${editing.id}`, payload);
        toast.success("Template updated");
      } else {
        await api.post("/templates", payload);
        toast.success("Template created");
      }
      setOpen(false); setForm(blank); setEditing(null);
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete template?")) return;
    await api.delete(`/templates/${id}`);
    toast.success("Deleted"); load();
  };

  return (
    <div className="space-y-4" data-testid="templates-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Content</div>
          <h1 className="text-3xl font-black tracking-tighter">Templates</h1>
        </div>
        <Button className="rounded-sm gap-2" onClick={openCreate} data-testid="new-template-button"><Plus className="h-4 w-4" /> New Template</Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {tpls.map(t => (
          <Card key={t.id} className="rounded-sm shadow-none" data-testid={`template-card-${t.id}`}>
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center justify-between">
                <ChannelBadge channel={t.channel} />
                <StatusBadge status={t.status} />
              </div>
              <div className="font-semibold">{t.name}</div>
              <div className="text-xs text-muted-foreground uppercase tracking-wider">{t.category}</div>
              <div className="text-sm p-3 rounded-sm bg-muted/40 border border-border font-mono whitespace-pre-wrap">{t.body}</div>
              {t.variables?.length > 0 && (
                <div className="text-xs"><span className="text-muted-foreground">Vars: </span>
                  <span className="font-mono">{t.variables.join(", ")}</span>
                </div>
              )}
              <div className="flex justify-end gap-1 pt-1">
                <Button variant="ghost" size="sm" className="rounded-sm gap-1" onClick={() => openEdit(t)} data-testid={`edit-template-${t.id}`}>
                  <Pencil className="h-3 w-3" /> Edit
                </Button>
                <Button variant="ghost" size="sm" className="text-red-600 rounded-sm gap-1" onClick={() => del(t.id)} data-testid={`delete-template-${t.id}`}>
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
        {tpls.length === 0 && <div className="text-sm text-muted-foreground">No templates.</div>}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="rounded-sm max-w-2xl">
          <DialogHeader><DialogTitle>{editing ? "Edit Template" : "Create Template"}</DialogTitle></DialogHeader>
          <form onSubmit={save} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Name</Label><Input required value={form.name} onChange={e=>setForm({...form,name:e.target.value})} className="rounded-sm" data-testid="template-name-input" /></div>
              <div>
                <Label>Channel</Label>
                <select value={form.channel} onChange={e=>setForm({...form,channel:e.target.value})}
                  className="h-9 w-full px-3 rounded-sm border border-border bg-background text-sm" data-testid="template-channel-select">
                  {CHANNELS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <Label>Category</Label>
                <select value={form.category} onChange={e=>setForm({...form,category:e.target.value})}
                  className="h-9 w-full px-3 rounded-sm border border-border bg-background text-sm">
                  <option value="utility">utility</option>
                  <option value="marketing">marketing</option>
                  <option value="authentication">authentication</option>
                </select>
              </div>
              <div>
                <Label>Status</Label>
                <select value={form.status} onChange={e=>setForm({...form,status:e.target.value})}
                  className="h-9 w-full px-3 rounded-sm border border-border bg-background text-sm">
                  <option value="approved">approved</option>
                  <option value="pending">pending</option>
                  <option value="rejected">rejected</option>
                </select>
              </div>
            </div>
            <div>
              <Label>Body (use {`{{name}}`}, {`{{order_id}}`} etc)</Label>
              <Textarea required rows={4} value={form.body} onChange={e=>setForm({...form,body:e.target.value})} className="rounded-sm" data-testid="template-body-input" />
              <div className="text-xs text-muted-foreground mt-1">Detected variables: {extractVars(form.body).join(", ") || "—"}</div>
            </div>
            <DialogFooter><Button type="submit" className="rounded-sm" data-testid="save-template-button">{editing ? "Save" : "Create"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
