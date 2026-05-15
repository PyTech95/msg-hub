import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChannelBadge, StatusBadge } from "@/components/Badges";
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip, Legend } from "recharts";
import { ArrowLeft, RefreshCw } from "lucide-react";

const STATUS_COLORS = {
  queued: "#a1a1aa", sent: "#0ea5e9", delivered: "#22c55e",
  failed: "#ef4444", replied: "#6366f1",
};

export default function CampaignDetail() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [contacts, setContacts] = useState({});
  const [template, setTemplate] = useState(null);
  const [messages, setMessages] = useState([]);

  const load = async () => {
    const r = await api.get(`/campaigns/${id}`);
    setData(r.data);
    if (r.data.campaign.template_id) {
      try {
        const tpls = await api.get("/templates");
        setTemplate(tpls.data.find(t => t.id === r.data.campaign.template_id));
      } catch {}
    }
    const cs = await api.get("/contacts");
    const map = {};
    for (const c of cs.data) map[c.id] = c;
    setContacts(map);
    const m = await api.get("/messages", { params: { limit: 500 } });
    setMessages((m.data || []).filter(x => x.campaign_id === id));
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [id]);

  if (!data) return <div className="text-sm text-muted-foreground">Loading…</div>;
  const c = data.campaign;
  const stats = c.stats || {};
  const chartData = Object.entries(stats).filter(([, v]) => v > 0).map(([k, v]) => ({ name: k, value: v }));
  const total = (stats.queued || 0) + (stats.sent || 0);
  const progress = total ? Math.min(100, Math.round(((stats.delivered || 0) + (stats.failed || 0)) / total * 100)) : 0;

  return (
    <div className="space-y-4" data-testid="campaign-detail-page">
      <Link to="/campaigns" className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1" data-testid="back-to-campaigns">
        <ArrowLeft className="h-3 w-3" /> Back to Campaigns
      </Link>

      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Campaign</div>
          <h1 className="text-3xl font-black tracking-tighter flex items-center gap-3">
            {c.name} <ChannelBadge channel={c.channel} /> <StatusBadge status={c.status} />
          </h1>
          <div className="text-xs text-muted-foreground mt-1 font-mono">ID {c.id}</div>
        </div>
        <Button variant="outline" className="rounded-sm gap-1" onClick={load} data-testid="refresh-campaign">
          <RefreshCw className="h-3 w-3" /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2 rounded-sm shadow-none">
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold">Progress</h3>
              <span className="font-mono text-xs">{progress}%</span>
            </div>
            <div className="h-2 w-full bg-muted rounded-sm overflow-hidden">
              <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
            </div>
            <div className="grid grid-cols-3 md:grid-cols-5 gap-2 pt-2">
              {["queued","sent","delivered","failed","replied"].map(k => (
                <div key={k} className="p-3 rounded-sm border border-border">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{k}</div>
                  <div className="text-2xl font-black font-mono">{stats[k] ?? 0}</div>
                </div>
              ))}
            </div>
            {template && (
              <div className="p-3 mt-2 rounded-sm border border-border">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Template — {template.name}</div>
                <div className="font-mono text-xs whitespace-pre-wrap">{template.body}</div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="rounded-sm shadow-none">
          <CardContent className="p-4">
            <h3 className="text-lg font-bold mb-3">Status distribution</h3>
            <div className="h-60">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={chartData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={40} outerRadius={80} paddingAngle={2}>
                    {chartData.map((e, i) => <Cell key={i} fill={STATUS_COLORS[e.name] || "#888"} />)}
                  </Pie>
                  <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 2, fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-4">
          <h3 className="text-lg font-bold mb-3">Recipients ({data.recipients.length})</h3>
          <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 sticky top-0">
                <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2">Contact</th>
                  <th className="px-3 py-2">Phone</th>
                  <th className="px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.recipients.map(r => {
                  const ct = contacts[r.contact_id];
                  return (
                    <tr key={r.id} className="border-t border-border hover:bg-accent/40" data-testid={`recipient-${r.id}`}>
                      <td className="px-3 py-2">
                        {ct ? <Link to={`/contacts/${r.contact_id}`} className="hover:underline">{ct.name}</Link> : <span className="font-mono">{r.contact_id.slice(0, 10)}…</span>}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">{ct?.phone || "—"}</td>
                      <td className="px-3 py-2"><StatusBadge status={r.status} /></td>
                    </tr>
                  );
                })}
                {data.recipients.length === 0 && <tr><td colSpan={3} className="text-center text-muted-foreground py-6">No recipients (yet).</td></tr>}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-4">
          <h3 className="text-lg font-bold mb-3">Messages dispatched ({messages.length})</h3>
          <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 sticky top-0">
                <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2">Body</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Provider ID</th>
                  <th className="px-3 py-2 text-right">When</th>
                </tr>
              </thead>
              <tbody>
                {messages.map(m => (
                  <tr key={m.id} className={`border-t border-border hover:bg-accent/40 row-${m.channel}`}>
                    <td className="px-3 py-2 max-w-md truncate">{m.body}</td>
                    <td className="px-3 py-2"><StatusBadge status={m.status} /></td>
                    <td className="px-3 py-2 font-mono text-[11px]">{m.provider_message_id || "—"}</td>
                    <td className="px-3 py-2 text-right text-xs font-mono">{new Date(m.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
