import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { Plus, Trash2 } from "lucide-react";

const ROLE_CLS = {
  super_admin: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
  admin: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  manager: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  agent: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
};

export default function Team() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "agent" });

  const load = () => api.get("/users").then(r => setUsers(r.data));
  useEffect(() => { load(); }, []);

  const save = async (e) => {
    e.preventDefault();
    try {
      await api.post("/auth/register", form);
      toast.success("Team member added");
      setOpen(false); setForm({ email: "", password: "", name: "", role: "agent" });
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };

  const del = async (id) => {
    if (!window.confirm("Remove member?")) return;
    try { await api.delete(`/users/${id}`); toast.success("Removed"); load(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="space-y-4" data-testid="team-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Access</div>
          <h1 className="text-3xl font-black tracking-tighter">Team</h1>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button className="rounded-sm gap-2" data-testid="add-member-button"><Plus className="h-4 w-4" /> Add Member</Button>
          </DialogTrigger>
          <DialogContent className="rounded-sm">
            <DialogHeader><DialogTitle>Add Team Member</DialogTitle></DialogHeader>
            <form onSubmit={save} className="space-y-3">
              <div><Label>Name</Label><Input required value={form.name} onChange={e=>setForm({...form,name:e.target.value})} className="rounded-sm" data-testid="member-name-input" /></div>
              <div><Label>Email</Label><Input required type="email" value={form.email} onChange={e=>setForm({...form,email:e.target.value})} className="rounded-sm" data-testid="member-email-input" /></div>
              <div><Label>Password</Label><Input required type="password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})} className="rounded-sm" data-testid="member-password-input" /></div>
              <div>
                <Label>Role</Label>
                <select value={form.role} onChange={e=>setForm({...form,role:e.target.value})}
                  className="h-9 w-full px-3 rounded-sm border border-border bg-background text-sm" data-testid="member-role-select">
                  <option value="agent">agent</option>
                  <option value="manager">manager</option>
                  {user?.role === "super_admin" && <option value="admin">admin</option>}
                  {user?.role === "super_admin" && <option value="super_admin">super_admin</option>}
                </select>
              </div>
              <DialogFooter><Button type="submit" className="rounded-sm" data-testid="save-member-button">Add</Button></DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <Card className="rounded-sm shadow-none">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Email</th>
                <th className="px-3 py-2">Role</th>
                <th className="px-3 py-2 text-right">Joined</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id} className="border-t border-border hover:bg-accent/40" data-testid={`team-row-${u.id}`}>
                  <td className="px-3 py-2 font-medium">{u.name}</td>
                  <td className="px-3 py-2 font-mono text-xs">{u.email}</td>
                  <td className="px-3 py-2"><Badge variant="outline" className={`rounded-sm text-[10px] border-transparent ${ROLE_CLS[u.role]}`}>{u.role}</Badge></td>
                  <td className="px-3 py-2 text-right text-xs font-mono">{u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}</td>
                  <td className="px-3 py-2 text-right">
                    {user?.role === "super_admin" && u.id !== user.id && (
                      <Button variant="ghost" size="sm" className="text-red-600 rounded-sm gap-1" onClick={() => del(u.id)} data-testid={`delete-member-${u.id}`}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
