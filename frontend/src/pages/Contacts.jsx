import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Plus, Search, Upload, Trash2, Phone, Mail, BanIcon } from "lucide-react";

export default function Contacts() {
  const [contacts, setContacts] = useState([]);
  const [lists, setLists] = useState([]);
  const [q, setQ] = useState("");
  const [listFilter, setListFilter] = useState("");
  const [selected, setSelected] = useState(new Set());
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", phone: "", email: "", tags: "" });
  const fileRef = useRef(null);

  const load = async () => {
    const { data } = await api.get("/contacts", { params: { q: q || undefined, list_id: listFilter || undefined } });
    setContacts(data);
  };
  useEffect(() => { load(); }, [q, listFilter]);
  useEffect(() => { api.get("/lists").then(r => setLists(r.data)); }, []);

  const allSelected = contacts.length > 0 && selected.size === contacts.length;
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(contacts.map(c => c.id)));
  const toggleOne = (id) => setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const createContact = async (e) => {
    e.preventDefault();
    await api.post("/contacts", {
      name: form.name, phone: form.phone, email: form.email || null,
      tags: form.tags.split(",").map(s => s.trim()).filter(Boolean),
    });
    toast.success("Contact added");
    setOpen(false); setForm({ name: "", phone: "", email: "", tags: "" });
    load();
  };

  const bulkDelete = async () => {
    if (selected.size === 0) return;
    if (!window.confirm(`Delete ${selected.size} contact(s)?`)) return;
    await api.post("/contacts/bulk-delete", Array.from(selected));
    toast.success(`Deleted ${selected.size}`);
    setSelected(new Set());
    load();
  };

  const importCSV = async (file) => {
    const fd = new FormData(); fd.append("file", file);
    const { data } = await api.post("/contacts/import", fd, { headers: { "Content-Type": "multipart/form-data" } });
    toast.success(`Imported ${data.inserted}, skipped ${data.skipped}`);
    load();
  };

  return (
    <div className="space-y-4" data-testid="contacts-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Audience</div>
          <h1 className="text-3xl font-black tracking-tighter">Contacts</h1>
        </div>
        <div className="flex items-center gap-2">
          <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={e => e.target.files?.[0] && importCSV(e.target.files[0])} />
          <Button variant="outline" className="rounded-sm gap-2" onClick={() => fileRef.current?.click()} data-testid="import-contacts-button">
            <Upload className="h-4 w-4" /> Import CSV
          </Button>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="rounded-sm gap-2" data-testid="add-contact-button"><Plus className="h-4 w-4" /> New Contact</Button>
            </DialogTrigger>
            <DialogContent className="rounded-sm">
              <DialogHeader><DialogTitle>Add Contact</DialogTitle></DialogHeader>
              <form onSubmit={createContact} className="space-y-3">
                <div><Label>Name</Label><Input required value={form.name} onChange={e => setForm({...form, name: e.target.value})} className="rounded-sm" data-testid="contact-name-input" /></div>
                <div><Label>Phone</Label><Input required value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} className="rounded-sm" data-testid="contact-phone-input" placeholder="+91..." /></div>
                <div><Label>Email</Label><Input type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} className="rounded-sm" data-testid="contact-email-input" /></div>
                <div><Label>Tags (comma)</Label><Input value={form.tags} onChange={e => setForm({...form, tags: e.target.value})} className="rounded-sm" placeholder="vip, customer" data-testid="contact-tags-input" /></div>
                <DialogFooter><Button type="submit" className="rounded-sm" data-testid="save-contact-button">Save</Button></DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-3 flex flex-wrap items-center gap-2 border-b border-border">
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input placeholder="Search name, phone or email" value={q} onChange={e => setQ(e.target.value)}
              className="pl-8 w-72 rounded-sm" data-testid="contacts-search-input" />
          </div>
          <select value={listFilter} onChange={e => setListFilter(e.target.value)}
            className="h-9 px-3 rounded-sm border border-border bg-background text-sm" data-testid="list-filter-select">
            <option value="">All lists</option>
            {lists.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
          {selected.size > 0 && (
            <div className="ml-auto flex items-center gap-2">
              <span className="text-xs text-muted-foreground">{selected.size} selected</span>
              <Button variant="destructive" size="sm" className="rounded-sm gap-1" onClick={bulkDelete} data-testid="bulk-delete-button">
                <Trash2 className="h-3.5 w-3.5" /> Delete
              </Button>
            </div>
          )}
        </CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 sticky top-0">
              <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2 w-10"><Checkbox checked={allSelected} onCheckedChange={toggleAll} data-testid="select-all-contacts" /></th>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Phone</th>
                <th className="px-3 py-2">Email</th>
                <th className="px-3 py-2">Tags</th>
                <th className="px-3 py-2">Flags</th>
              </tr>
            </thead>
            <tbody>
              {contacts.map(c => (
                <tr key={c.id} className="border-t border-border hover:bg-accent/40" data-testid={`contact-row-${c.id}`}>
                  <td className="px-3 py-2"><Checkbox checked={selected.has(c.id)} onCheckedChange={() => toggleOne(c.id)} /></td>
                  <td className="px-3 py-2"><Link to={`/contacts/${c.id}`} className="font-medium hover:underline" data-testid={`contact-link-${c.id}`}>{c.name}</Link></td>
                  <td className="px-3 py-2 font-mono text-xs flex items-center gap-1"><Phone className="h-3 w-3 text-muted-foreground" />{c.phone}</td>
                  <td className="px-3 py-2 text-xs"><span className="flex items-center gap-1"><Mail className="h-3 w-3 text-muted-foreground" />{c.email || "—"}</span></td>
                  <td className="px-3 py-2 space-x-1">
                    {(c.tags || []).map(t => <Badge key={t} variant="secondary" className="rounded-sm text-[10px]">{t}</Badge>)}
                  </td>
                  <td className="px-3 py-2 space-x-1">
                    {c.dnd && <Badge variant="outline" className="rounded-sm text-[10px] border-amber-300 text-amber-700">DND</Badge>}
                    {c.opted_out && <Badge variant="outline" className="rounded-sm text-[10px] border-red-300 text-red-700 gap-1"><BanIcon className="h-3 w-3" />Opted Out</Badge>}
                  </td>
                </tr>
              ))}
              {contacts.length === 0 && (
                <tr><td colSpan={6} className="text-center text-muted-foreground py-10">No contacts.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
