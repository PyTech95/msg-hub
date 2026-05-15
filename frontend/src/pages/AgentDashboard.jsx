import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { ChannelBadge, StatusBadge } from "@/components/Badges";
import { Inbox, Phone, MessageSquare, Send } from "lucide-react";

const fmt = (ts) => new Date(ts).toLocaleString();

export default function AgentDashboard({ user }) {
  const [convs, setConvs] = useState([]);
  const [calls, setCalls] = useState([]);
  const [msgs, setMsgs] = useState([]);

  useEffect(() => {
    api.get("/conversations").then(r => setConvs(r.data.slice(0, 8)));
    api.get("/calls").then(r => setCalls(r.data.slice(0, 6)));
    api.get("/messages", { params: { limit: 8 } }).then(r => setMsgs(r.data));
  }, []);

  const unreadCount = convs.filter(c => c.unread).length;

  return (
    <div className="space-y-6" data-testid="agent-dashboard-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Agent Workspace</div>
          <h1 className="text-3xl font-black tracking-tighter">Hi, {user?.name?.split(" ")[0] || "there"} 👋</h1>
          <p className="text-sm text-muted-foreground mt-1">Your inbox, recent calls and outgoing messages — everything you need to engage customers today.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card className="rounded-sm shadow-none" data-testid="kpi-unread">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-10 w-10 grid place-items-center rounded-sm border border-border"><Inbox className="h-4 w-4" /></div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Open conversations</div>
              <div className="text-2xl font-black font-mono">{convs.length}</div>
              <div className="text-xs text-muted-foreground">{unreadCount} unread</div>
            </div>
          </CardContent>
        </Card>
        <Card className="rounded-sm shadow-none" data-testid="kpi-recent-calls">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-10 w-10 grid place-items-center rounded-sm border border-border"><Phone className="h-4 w-4" /></div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Recent calls</div>
              <div className="text-2xl font-black font-mono">{calls.length}</div>
              <div className="text-xs text-muted-foreground">last 24h activity</div>
            </div>
          </CardContent>
        </Card>
        <Card className="rounded-sm shadow-none" data-testid="kpi-recent-msgs">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-10 w-10 grid place-items-center rounded-sm border border-border"><Send className="h-4 w-4" /></div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Recent messages</div>
              <div className="text-2xl font-black font-mono">{msgs.length}</div>
              <div className="text-xs text-muted-foreground">across all channels</div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2 rounded-sm shadow-none">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">My Inbox</div>
                <h3 className="text-lg font-bold flex items-center gap-2"><Inbox className="h-4 w-4" /> Conversations</h3>
              </div>
              <Link to="/conversations" className="text-xs text-primary hover:underline" data-testid="agent-view-all-conversations">View all →</Link>
            </div>
            <div className="space-y-2">
              {convs.map((c, i) => (
                <Link key={i} to={`/contacts/${c.contact_id}`}
                  className={`block p-3 rounded-sm border border-border hover:bg-accent/40 row-${c.channel}`}
                  data-testid={`agent-conv-${i}`}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-medium truncate">{c.contact_name || c.contact_id}</span>
                      <ChannelBadge channel={c.channel} />
                      {c.unread && <span className="h-2 w-2 rounded-full bg-primary" />}
                    </div>
                    <span className="text-[11px] font-mono text-muted-foreground shrink-0">{c.last_message_at ? fmt(c.last_message_at) : "—"}</span>
                  </div>
                  <div className="text-xs text-muted-foreground truncate mt-1">{c.last_message || "—"}</div>
                </Link>
              ))}
              {convs.length === 0 && <div className="text-sm text-muted-foreground py-6 text-center">No conversations yet.</div>}
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-sm shadow-none">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg font-bold flex items-center gap-2"><Phone className="h-4 w-4" /> Recent Calls</h3>
              <Link to="/calls" className="text-xs text-primary hover:underline" data-testid="agent-view-all-calls">All →</Link>
            </div>
            <div className="space-y-2">
              {calls.map(c => (
                <div key={c.id} className="p-3 rounded-sm border border-border row-voice" data-testid={`agent-call-${c.id}`}>
                  <div className="flex items-center justify-between text-xs">
                    <Link to={`/contacts/${c.contact_id}`} className="hover:underline font-mono">{c.contact_id.slice(0, 8)}…</Link>
                    <StatusBadge status={c.status} />
                  </div>
                  <div className="text-[11px] font-mono text-muted-foreground mt-1">{c.duration_sec || 0}s · {fmt(c.created_at)}</div>
                </div>
              ))}
              {calls.length === 0 && <div className="text-sm text-muted-foreground py-6 text-center">No calls yet.</div>}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-bold flex items-center gap-2"><MessageSquare className="h-4 w-4" /> Latest Messages</h3>
            <Link to="/messages" className="text-xs text-primary hover:underline" data-testid="agent-view-all-messages">All →</Link>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground border-b border-border">
                  <th className="px-3 py-2">Channel</th>
                  <th className="px-3 py-2">Direction</th>
                  <th className="px-3 py-2">Body</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2 text-right">When</th>
                </tr>
              </thead>
              <tbody>
                {msgs.map(m => (
                  <tr key={m.id} className={`border-b border-border row-${m.channel}`} data-testid={`agent-msg-${m.id}`}>
                    <td className="px-3 py-2"><ChannelBadge channel={m.channel} /></td>
                    <td className="px-3 py-2 text-xs uppercase">{m.direction}</td>
                    <td className="px-3 py-2 max-w-md truncate">{m.body}</td>
                    <td className="px-3 py-2"><StatusBadge status={m.status} /></td>
                    <td className="px-3 py-2 text-right text-xs font-mono">{fmt(m.created_at)}</td>
                  </tr>
                ))}
                {msgs.length === 0 && <tr><td colSpan={5} className="text-center text-muted-foreground py-6">No messages.</td></tr>}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
