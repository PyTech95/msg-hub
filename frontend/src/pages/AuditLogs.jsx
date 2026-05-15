import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { RefreshCw, ScrollText, Search } from "lucide-react";

const ACTION_TONE = {
  login: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  login_failed: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
  user_created: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  user_deleted: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
  password_changed: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  password_reset_requested: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  password_reset_completed: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  campaign_created: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300",
  campaign_auto_started: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300",
  provider_credentials_updated: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
  markup_updated: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
};

export default function AuditLogs() {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");
  const [action, setAction] = useState("");

  const load = () => api.get("/audit-logs", { params: { limit: 300, action: action || undefined } }).then(r => setRows(r.data));
  useEffect(() => { load(); }, [action]);

  const filtered = rows.filter(r => {
    if (!q) return true;
    const s = q.toLowerCase();
    return (r.action || "").toLowerCase().includes(s)
      || (r.actor_email || "").toLowerCase().includes(s)
      || (r.target_type || "").toLowerCase().includes(s)
      || JSON.stringify(r.meta || {}).toLowerCase().includes(s);
  });

  const uniqueActions = Array.from(new Set(rows.map(r => r.action))).sort();

  return (
    <div className="space-y-4" data-testid="audit-logs-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Security</div>
          <h1 className="text-3xl font-black tracking-tighter flex items-center gap-2">
            <ScrollText className="h-6 w-6" /> Audit Logs
          </h1>
          <p className="text-xs text-muted-foreground mt-1">Every privileged action, signed by user identity and timestamp.</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={action} onChange={e=>setAction(e.target.value)}
            className="h-9 px-3 rounded-sm border border-border bg-background text-sm" data-testid="audit-action-filter">
            <option value="">All actions</option>
            {uniqueActions.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input placeholder="Search audit logs" value={q} onChange={e=>setQ(e.target.value)} className="pl-8 w-64 rounded-sm" data-testid="audit-search-input" />
          </div>
          <Button variant="outline" className="rounded-sm gap-1" onClick={load} data-testid="refresh-audit">
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <Card className="rounded-sm shadow-none">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 sticky top-0">
              <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2">Action</th>
                <th className="px-3 py-2">Actor</th>
                <th className="px-3 py-2">Target</th>
                <th className="px-3 py-2">Details</th>
                <th className="px-3 py-2 text-right">When</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(r => (
                <tr key={r.id} className="border-t border-border hover:bg-accent/40" data-testid={`audit-row-${r.id}`}>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className={`rounded-sm border-transparent text-[10px] font-mono ${ACTION_TONE[r.action] || "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"}`}>{r.action}</Badge>
                  </td>
                  <td className="px-3 py-2">
                    <div className="text-xs font-mono">{r.actor_email || "—"}</div>
                    {r.actor_role && <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{r.actor_role}</div>}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    <div>{r.target_type || "—"}</div>
                    {r.target_id && <div className="font-mono text-[10px] text-muted-foreground">{r.target_id.slice(0, 8)}…</div>}
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px] max-w-md truncate">{r.meta && Object.keys(r.meta).length ? JSON.stringify(r.meta) : "—"}</td>
                  <td className="px-3 py-2 text-right text-xs font-mono">{new Date(r.created_at).toLocaleString()}</td>
                </tr>
              ))}
              {filtered.length === 0 && <tr><td colSpan={5} className="text-center text-muted-foreground py-10">No audit entries.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
