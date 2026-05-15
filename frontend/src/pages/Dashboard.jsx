import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend,
  PieChart, Pie, Cell, LineChart, Line
} from "recharts";
import { Users, Send, CheckCircle2, XCircle, MessageSquareReply, Megaphone, TrendingUp, TrendingDown } from "lucide-react";

const KPI = ({ title, value, icon: Icon, delta, tone = "default", testid }) => (
  <Card className="rounded-sm shadow-none" data-testid={testid}>
    <CardContent className="p-4">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">{title}</div>
          <div className="text-3xl font-black font-mono mt-1 tracking-tight">{value}</div>
        </div>
        <div className={`h-9 w-9 grid place-items-center rounded-sm border border-border ${tone === "danger" ? "text-red-600" : tone === "success" ? "text-emerald-600" : "text-foreground"}`}>
          <Icon className="h-4 w-4" />
        </div>
      </div>
      {delta != null && (
        <div className="mt-3 flex items-center gap-1 text-xs text-muted-foreground">
          {delta >= 0 ? <TrendingUp className="h-3 w-3 text-emerald-600" /> : <TrendingDown className="h-3 w-3 text-red-600" />}
          <span className="font-mono">{delta >= 0 ? "+" : ""}{delta}%</span>
          <span>vs last week</span>
        </div>
      )}
    </CardContent>
  </Card>
);

const CHANNEL_COLORS = { sms: "#3B82F6", whatsapp: "#22C55E", rcs: "#F97316", voice: "#57534E" };

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [campaigns, setCampaigns] = useState([]);

  useEffect(() => {
    api.get("/dashboard/stats").then(r => setStats(r.data));
    api.get("/campaigns").then(r => setCampaigns(r.data.slice(0, 5)));
  }, []);

  if (!stats) return <div className="text-sm text-muted-foreground">Loading dashboard…</div>;
  const k = stats.kpis;
  const deliveryRate = k.messages_sent ? Math.round((k.delivered / k.messages_sent) * 100) : 0;

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Overview</div>
          <h1 className="text-3xl font-black tracking-tighter">Control Room</h1>
        </div>
        <div className="text-xs text-muted-foreground font-mono">Delivery rate: <span className="text-foreground font-semibold">{deliveryRate}%</span></div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KPI title="Sent"           value={k.messages_sent}    icon={Send}              delta={12} testid="kpi-sent" />
        <KPI title="Delivered"      value={k.delivered}        icon={CheckCircle2}      tone="success" delta={8} testid="kpi-delivered" />
        <KPI title="Failed"         value={k.failed}           icon={XCircle}           tone="danger"  delta={-3} testid="kpi-failed" />
        <KPI title="Replies"        value={k.replied}          icon={MessageSquareReply} delta={5} testid="kpi-replied" />
        <KPI title="Active Camps"   value={k.active_campaigns} icon={Megaphone}         testid="kpi-campaigns" />
        <KPI title="Contacts"       value={k.contacts}         icon={Users}             testid="kpi-contacts" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2 rounded-sm shadow-none">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Last 7 days</div>
                <h3 className="text-lg font-bold">Messages by Channel</h3>
              </div>
            </div>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stats.series_7d}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                  <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                  <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 2, fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="sms" stackId="a" fill={CHANNEL_COLORS.sms} />
                  <Bar dataKey="whatsapp" stackId="a" fill={CHANNEL_COLORS.whatsapp} />
                  <Bar dataKey="rcs" stackId="a" fill={CHANNEL_COLORS.rcs} />
                  <Bar dataKey="voice" stackId="a" fill={CHANNEL_COLORS.voice} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-sm shadow-none">
          <CardContent className="p-4">
            <div className="mb-4">
              <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Distribution</div>
              <h3 className="text-lg font-bold">Channel Mix</h3>
            </div>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={stats.channel_split} dataKey="count" nameKey="channel" cx="50%" cy="50%" innerRadius={50} outerRadius={90} paddingAngle={2}>
                    {stats.channel_split.map((entry, i) => (
                      <Cell key={i} fill={CHANNEL_COLORS[entry.channel] || "#888"} />
                    ))}
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
          <div className="mb-3">
            <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Recent</div>
            <h3 className="text-lg font-bold">Campaigns</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground border-b border-border">
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Channel</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2 text-right">Sent</th>
                  <th className="px-3 py-2 text-right">Delivered</th>
                  <th className="px-3 py-2 text-right">Failed</th>
                  <th className="px-3 py-2 text-right">Replies</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map(c => (
                  <tr key={c.id} className="border-b border-border hover:bg-accent/40" data-testid={`dashboard-campaign-row-${c.id}`}>
                    <td className="px-3 py-2 font-medium">{c.name}</td>
                    <td className="px-3 py-2 uppercase text-xs font-mono">{c.channel}</td>
                    <td className="px-3 py-2 text-xs">{c.status}</td>
                    <td className="px-3 py-2 text-right font-mono">{c.stats?.sent ?? 0}</td>
                    <td className="px-3 py-2 text-right font-mono">{c.stats?.delivered ?? 0}</td>
                    <td className="px-3 py-2 text-right font-mono">{c.stats?.failed ?? 0}</td>
                    <td className="px-3 py-2 text-right font-mono">{c.stats?.replied ?? 0}</td>
                  </tr>
                ))}
                {campaigns.length === 0 && (
                  <tr><td colSpan={7} className="text-center text-muted-foreground py-6">No campaigns yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
