import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ChannelBadge, StatusBadge } from "@/components/Badges";
import { Download } from "lucide-react";

export default function MessageLogs() {
  const [msgs, setMsgs] = useState([]);
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    api.get("/messages", { params: { channel: channel || undefined, status: status || undefined, limit: 300 } }).then(r => setMsgs(r.data));
  }, [channel, status]);

  const exportCSV = async () => {
    const res = await api.get("/export/messages.csv", {
      params: { channel: channel || undefined, status: status || undefined },
      responseType: "blob",
    });
    const url = window.URL.createObjectURL(new Blob([res.data]));
    const a = document.createElement("a"); a.href = url; a.download = "messages.csv";
    document.body.appendChild(a); a.click(); a.remove();
    window.URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4" data-testid="messages-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Audit</div>
          <h1 className="text-3xl font-black tracking-tighter">Message Logs</h1>
        </div>
        <div className="flex items-center gap-2">
          <select value={channel} onChange={e=>setChannel(e.target.value)}
            className="h-9 px-3 rounded-sm border border-border bg-background text-sm" data-testid="filter-channel-select">
            <option value="">All channels</option>
            <option value="sms">SMS</option><option value="whatsapp">WhatsApp</option>
            <option value="rcs">RCS</option><option value="voice">Voice</option>
          </select>
          <select value={status} onChange={e=>setStatus(e.target.value)}
            className="h-9 px-3 rounded-sm border border-border bg-background text-sm" data-testid="filter-status-select">
            <option value="">All status</option>
            <option value="queued">queued</option><option value="sent">sent</option>
            <option value="delivered">delivered</option><option value="failed">failed</option>
            <option value="received">received</option>
          </select>
          <Button variant="outline" className="rounded-sm gap-2" onClick={exportCSV} data-testid="export-messages-button">
            <Download className="h-4 w-4" /> Export
          </Button>
        </div>
      </div>

      <Card className="rounded-sm shadow-none">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2">Channel</th>
                <th className="px-3 py-2">Direction</th>
                <th className="px-3 py-2">Body</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Provider ID</th>
                <th className="px-3 py-2 text-right">When</th>
              </tr>
            </thead>
            <tbody>
              {msgs.map(m => (
                <tr key={m.id} className={`border-t border-border hover:bg-accent/40 row-${m.channel}`} data-testid={`message-row-${m.id}`}>
                  <td className="px-3 py-2"><ChannelBadge channel={m.channel} /></td>
                  <td className="px-3 py-2 text-xs uppercase">{m.direction}</td>
                  <td className="px-3 py-2 max-w-md truncate">{m.body}</td>
                  <td className="px-3 py-2"><StatusBadge status={m.status} /></td>
                  <td className="px-3 py-2 font-mono text-[11px]">{m.provider_message_id || "—"}</td>
                  <td className="px-3 py-2 text-right text-xs font-mono">{new Date(m.created_at).toLocaleString()}</td>
                </tr>
              ))}
              {msgs.length === 0 && <tr><td colSpan={6} className="text-center text-muted-foreground py-10">No messages.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
