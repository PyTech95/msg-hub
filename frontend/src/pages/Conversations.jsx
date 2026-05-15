import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { ChannelBadge } from "@/components/Badges";

export default function Conversations() {
  const [convs, setConvs] = useState([]);
  useEffect(() => { api.get("/conversations").then(r => setConvs(r.data)); }, []);

  return (
    <div className="space-y-4" data-testid="conversations-page">
      <div>
        <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Inbox</div>
        <h1 className="text-3xl font-black tracking-tighter">Conversations</h1>
      </div>

      <Card className="rounded-sm shadow-none">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2">Contact</th>
                <th className="px-3 py-2">Channel</th>
                <th className="px-3 py-2">Last message</th>
                <th className="px-3 py-2 text-right">When</th>
              </tr>
            </thead>
            <tbody>
              {convs.map((c, i) => (
                <tr key={i} className={`border-t border-border hover:bg-accent/40 row-${c.channel}`} data-testid={`conversation-row-${i}`}>
                  <td className="px-3 py-2">
                    <Link to={`/contacts/${c.contact_id}`} className="font-medium hover:underline">{c.contact_name || c.contact_id}</Link>
                    <div className="font-mono text-[11px] text-muted-foreground">{c.contact_phone}</div>
                  </td>
                  <td className="px-3 py-2"><ChannelBadge channel={c.channel} /></td>
                  <td className="px-3 py-2 max-w-md truncate">{c.last_message || "—"}</td>
                  <td className="px-3 py-2 text-right text-xs font-mono">{c.last_message_at ? new Date(c.last_message_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
              {convs.length === 0 && <tr><td colSpan={4} className="text-center text-muted-foreground py-10">No conversations yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
