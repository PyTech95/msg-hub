import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { ChannelBadge } from "@/components/Badges";
import { Badge } from "@/components/ui/badge";

export default function Webhooks() {
  const [events, setEvents] = useState([]);
  useEffect(() => {
    const load = () => api.get("/webhooks/events", { params: { limit: 200 } }).then(r => setEvents(r.data));
    load(); const t = setInterval(load, 5000); return () => clearInterval(t);
  }, []);

  return (
    <div className="space-y-4" data-testid="webhooks-page">
      <div>
        <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Events</div>
        <h1 className="text-3xl font-black tracking-tighter">Webhook Monitor</h1>
        <p className="text-xs text-muted-foreground mt-1">Provider events stream to <span className="font-mono">/api/webhooks/incoming/{`{channel}`}</span></p>
      </div>

      <Card className="rounded-sm shadow-none">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2">Channel</th>
                <th className="px-3 py-2">Event</th>
                <th className="px-3 py-2">Signature</th>
                <th className="px-3 py-2">Payload</th>
                <th className="px-3 py-2 text-right">When</th>
              </tr>
            </thead>
            <tbody>
              {events.map(e => (
                <tr key={e.id} className={`border-t border-border hover:bg-accent/40 row-${e.channel}`} data-testid={`webhook-row-${e.id}`}>
                  <td className="px-3 py-2"><ChannelBadge channel={e.channel} /></td>
                  <td className="px-3 py-2 text-xs font-mono">{e.event_type}</td>
                  <td className="px-3 py-2"><Badge variant="outline" className={`rounded-sm text-[10px] ${e.signature_valid ? "border-emerald-300 text-emerald-700" : "border-red-300 text-red-700"}`}>{e.signature_valid ? "valid" : "invalid"}</Badge></td>
                  <td className="px-3 py-2 font-mono text-[11px] max-w-md truncate">{JSON.stringify(e.payload)}</td>
                  <td className="px-3 py-2 text-right text-xs font-mono">{new Date(e.created_at).toLocaleString()}</td>
                </tr>
              ))}
              {events.length === 0 && <tr><td colSpan={5} className="text-center text-muted-foreground py-10">No events yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
