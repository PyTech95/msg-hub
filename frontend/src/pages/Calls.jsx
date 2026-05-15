import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/Badges";
import { Phone } from "lucide-react";

export default function Calls() {
  const [calls, setCalls] = useState([]);
  useEffect(() => {
    const load = () => api.get("/calls").then(r => setCalls(r.data));
    load(); const t = setInterval(load, 4000); return () => clearInterval(t);
  }, []);

  return (
    <div className="space-y-4" data-testid="calls-page">
      <div>
        <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Voice</div>
        <h1 className="text-3xl font-black tracking-tighter">Call Logs</h1>
      </div>

      <Card className="rounded-sm shadow-none">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2">Contact</th>
                <th className="px-3 py-2">Direction</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Duration</th>
                <th className="px-3 py-2">Recording</th>
                <th className="px-3 py-2 text-right">When</th>
              </tr>
            </thead>
            <tbody>
              {calls.map(c => (
                <tr key={c.id} className="border-t border-border hover:bg-accent/40 row-voice" data-testid={`call-row-${c.id}`}>
                  <td className="px-3 py-2"><Link to={`/contacts/${c.contact_id}`} className="hover:underline flex items-center gap-2"><Phone className="h-3 w-3 text-muted-foreground" />{c.contact_id.slice(0, 8)}…</Link></td>
                  <td className="px-3 py-2 text-xs uppercase">{c.direction}</td>
                  <td className="px-3 py-2"><StatusBadge status={c.status} /></td>
                  <td className="px-3 py-2 text-right font-mono">{c.duration_sec || 0}s</td>
                  <td className="px-3 py-2 font-mono text-[11px] truncate max-w-[260px]">{c.recording_url || "—"}</td>
                  <td className="px-3 py-2 text-right text-xs font-mono">{new Date(c.created_at).toLocaleString()}</td>
                </tr>
              ))}
              {calls.length === 0 && <tr><td colSpan={6} className="text-center text-muted-foreground py-10">No calls yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
