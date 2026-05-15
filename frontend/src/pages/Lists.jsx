import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, Users } from "lucide-react";

const blank = { name: "", description: "" };

export default function Lists() {
  const [lists, setLists] = useState([]);
  const [counts, setCounts] = useState({});
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(blank);

  const load = async () => {
    const r = await api.get("/lists");
    setLists(r.data);
    const c = await api.get("/contacts");
    const m = {};
    for (const x of c.data) for (const id of (x.list_ids || [])) m[id] = (m[id] || 0) + 1;
    setCounts(m);
  };
  useEffect(() => { load(); }, []);

  const openCreate = () => { setEditing(null); setForm(blank); setOpen(true); };
  const openEdit = (l) => { setEditing(l); setForm({ name: l.name, description: l.description || "" }); setOpen(true); };

  const save = async (e) => {
    e.preventDefault();
    try {
      if (editing) {
        await api.patch(`/lists/${editing.id}`, form);
        toast.success("List updated");
      } else {
        await api.post("/lists", form);
        toast.success("List created");
      }
      setOpen(false); load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };

  const del = async (id) => {
    if (!window.confirm("Delete list? Contacts will remain.")) return;
    await api.delete(`/lists/${id}`);
    toast.success("Deleted"); load();
  };

  return (
    <div className="space-y-4" data-testid="lists-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Audience Segments</div>
          <h1 className="text-3xl font-black tracking-tighter">Contact Lists</h1>
        </div>
        <Button className="rounded-sm gap-2" onClick={openCreate} data-testid="new-list-button">
          <Plus className="h-4 w-4" /> New List
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {lists.map(l => (
          <Card key={l.id} className="rounded-sm shadow-none" data-testid={`list-card-${l.id}`}>
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Users className="h-4 w-4 text-muted-foreground" />
                  <span className="font-semibold">{l.name}</span>
                </div>
                <span className="font-mono text-xs text-muted-foreground">{counts[l.id] || 0} contacts</span>
              </div>
              <div className="text-xs text-muted-foreground min-h-[2.5rem]">{l.description || "—"}</div>
              <div className="flex justify-end gap-1 pt-1">
                <Button variant="ghost" size="sm" className="rounded-sm gap-1" onClick={() => openEdit(l)} data-testid={`edit-list-${l.id}`}>
                  <Pencil className="h-3 w-3" /> Edit
                </Button>
                <Button variant="ghost" size="sm" className="text-red-600 rounded-sm gap-1" onClick={() => del(l.id)} data-testid={`delete-list-${l.id}`}>
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
        {lists.length === 0 && <div className="text-sm text-muted-foreground">No lists yet.</div>}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="rounded-sm">
          <DialogHeader><DialogTitle>{editing ? "Edit List" : "New List"}</DialogTitle></DialogHeader>
          <form onSubmit={save} className="space-y-3">
            <div><Label>Name</Label><Input required value={form.name} onChange={e=>setForm({...form,name:e.target.value})} className="rounded-sm" data-testid="list-name-input" /></div>
            <div><Label>Description</Label><Textarea rows={3} value={form.description} onChange={e=>setForm({...form,description:e.target.value})} className="rounded-sm" data-testid="list-description-input" /></div>
            <DialogFooter><Button type="submit" className="rounded-sm" data-testid="save-list-button">{editing ? "Save" : "Create"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
