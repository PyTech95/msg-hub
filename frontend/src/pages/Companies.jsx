import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Plus, Building2, Trash2, Users, MessageSquare, Megaphone, IndianRupee } from "lucide-react";
import { toast } from "sonner";

const blank = { name: "", admin_email: "", admin_password: "", admin_name: "" };

export default function Companies() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [saving, setSaving] = useState(false);

  const load = () => api.get("/companies").then(r => setItems(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/companies", form);
      toast.success(`Company "${form.name}" created — admin can log in now`);
      setOpen(false); setForm(blank); load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setSaving(false); }
  };

  const toggleActive = async (c) => {
    try {
      await api.patch(`/companies/${c.id}`, { is_active: !c.is_active });
      toast.success(c.is_active ? "Company deactivated (logins blocked)" : "Company activated");
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const del = async (c) => {
    if (!window.confirm(`Delete "${c.name}" and ALL its data (users, contacts, messages, bills)? This cannot be undone.`)) return;
    try { await api.delete(`/companies/${c.id}`); toast.success("Company deleted"); load(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="space-y-4" data-testid="companies-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">SaaS Tenants</div>
          <h1 className="text-3xl font-black tracking-tighter">Companies</h1>
          <p className="text-xs text-muted-foreground mt-1">Each company gets a fresh, isolated workspace — own contacts, templates, campaigns and billing. They can never see other tenants' data.</p>
        </div>
        <Button className="rounded-sm gap-2" onClick={() => setOpen(true)} data-testid="add-company-button"><Plus className="h-4 w-4" /> Add Company</Button>
      </div>

      {items.length === 0 && (
        <div className="border border-dashed border-border rounded-sm p-10 text-center text-sm text-muted-foreground" data-testid="companies-empty">
          <Building2 className="h-8 w-8 mx-auto mb-2 opacity-40" />
          No companies yet. Add your first client company to start selling tezsandesh as a service.
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {items.map(c => (
          <Card key={c.id} className="rounded-sm shadow-none" data-testid={`company-card-${c.id}`}>
            <CardContent className="p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Building2 className="h-4 w-4 text-orange-500" />
                  <span className="font-semibold">{c.name}</span>
                </div>
                {c.is_active !== false
                  ? <Badge variant="outline" className="rounded-sm text-[10px] border-emerald-300 text-emerald-700">ACTIVE</Badge>
                  : <Badge variant="outline" className="rounded-sm text-[10px] border-red-300 text-red-700">DEACTIVATED</Badge>}
              </div>
              <div className="text-xs text-muted-foreground font-mono">{c.admin_email}</div>
              <div className="grid grid-cols-4 gap-2 text-center">
                <div className="border border-border rounded-sm p-2">
                  <Users className="h-3 w-3 mx-auto text-muted-foreground" />
                  <div className="text-sm font-bold" data-testid={`company-users-${c.id}`}>{c.stats?.users ?? 0}</div>
                  <div className="text-[9px] uppercase text-muted-foreground">Users</div>
                </div>
                <div className="border border-border rounded-sm p-2">
                  <Users className="h-3 w-3 mx-auto text-muted-foreground" />
                  <div className="text-sm font-bold">{c.stats?.contacts ?? 0}</div>
                  <div className="text-[9px] uppercase text-muted-foreground">Contacts</div>
                </div>
                <div className="border border-border rounded-sm p-2">
                  <MessageSquare className="h-3 w-3 mx-auto text-muted-foreground" />
                  <div className="text-sm font-bold">{c.stats?.messages ?? 0}</div>
                  <div className="text-[9px] uppercase text-muted-foreground">Msgs</div>
                </div>
                <div className="border border-border rounded-sm p-2">
                  <IndianRupee className="h-3 w-3 mx-auto text-muted-foreground" />
                  <div className="text-sm font-bold" data-testid={`company-usage-${c.id}`}>₹{c.usage?.amount ?? 0}</div>
                  <div className="text-[9px] uppercase text-muted-foreground">Usage</div>
                </div>
              </div>
              <div className="flex items-center justify-between pt-1">
                <div className="flex items-center gap-2">
                  <Switch checked={c.is_active !== false} onCheckedChange={() => toggleActive(c)} data-testid={`company-active-switch-${c.id}`} />
                  <span className="text-xs text-muted-foreground">Login access</span>
                </div>
                <Button variant="ghost" size="sm" className="text-red-600 rounded-sm" onClick={() => del(c)} data-testid={`delete-company-${c.id}`}>
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="rounded-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Building2 className="h-4 w-4" /> Add Company</DialogTitle>
            <DialogDescription>Creates a fresh isolated workspace + a company admin login. Share the credentials with your client.</DialogDescription>
          </DialogHeader>
          <form onSubmit={save} className="space-y-3">
            <div><Label>Company Name</Label><Input required value={form.name} onChange={e=>setForm({...form,name:e.target.value})} className="rounded-sm" placeholder="e.g. Sharma Traders" data-testid="company-name-input" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Admin Name</Label><Input value={form.admin_name} onChange={e=>setForm({...form,admin_name:e.target.value})} className="rounded-sm" placeholder="Optional" data-testid="company-admin-name-input" /></div>
              <div><Label>Admin Email</Label><Input required type="email" value={form.admin_email} onChange={e=>setForm({...form,admin_email:e.target.value})} className="rounded-sm" data-testid="company-admin-email-input" /></div>
            </div>
            <div><Label>Admin Password</Label><Input required type="text" minLength={6} value={form.admin_password} onChange={e=>setForm({...form,admin_password:e.target.value})} className="rounded-sm font-mono" placeholder="Min 6 characters" data-testid="company-admin-password-input" /></div>
            <DialogFooter>
              <Button type="submit" disabled={saving} className="rounded-sm" data-testid="save-company-button">{saving ? "Creating…" : "Create Company"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
