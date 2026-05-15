import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell, Legend } from "recharts";
import { ChannelBadge } from "@/components/Badges";

const COLORS = { sms: "#3B82F6", whatsapp: "#22C55E", rcs: "#F97316", voice: "#57534E" };

export default function Reports() {
  const [stats, setStats] = useState(null);
  const [usage, setUsage] = useState(null);
  useEffect(() => {
    api.get("/dashboard/stats").then(r => setStats(r.data));
    api.get("/usage/summary").then(r => setUsage(r.data));
  }, []);

  if (!stats || !usage) return <div className="text-sm text-muted-foreground">Loading…</div>;

  return (
    <div className="space-y-4" data-testid="reports-page">
      <div>
        <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Analytics</div>
        <h1 className="text-3xl font-black tracking-tighter">Reports & Usage</h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card className="rounded-sm shadow-none">
          <CardContent className="p-4">
            <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Total spend</div>
            <div className="text-3xl font-black font-mono mt-1">₹{usage.total_amount.toFixed(2)}</div>
            <div className="text-xs text-muted-foreground">{usage.total_units} units billed</div>
          </CardContent>
        </Card>
        <Card className="rounded-sm shadow-none">
          <CardContent className="p-4">
            <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Delivery rate</div>
            <div className="text-3xl font-black font-mono mt-1">
              {stats.kpis.messages_sent ? Math.round(stats.kpis.delivered / stats.kpis.messages_sent * 100) : 0}%
            </div>
            <div className="text-xs text-muted-foreground">{stats.kpis.delivered} of {stats.kpis.messages_sent} delivered</div>
          </CardContent>
        </Card>
        <Card className="rounded-sm shadow-none">
          <CardContent className="p-4">
            <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Failure rate</div>
            <div className="text-3xl font-black font-mono mt-1 text-red-600">
              {stats.kpis.messages_sent ? Math.round(stats.kpis.failed / stats.kpis.messages_sent * 100) : 0}%
            </div>
            <div className="text-xs text-muted-foreground">{stats.kpis.failed} failed</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2 rounded-sm shadow-none">
          <CardContent className="p-4">
            <h3 className="text-lg font-bold mb-3">Volume — last 7 days</h3>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stats.series_7d}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                  <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                  <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 2, fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="sms" fill={COLORS.sms} />
                  <Bar dataKey="whatsapp" fill={COLORS.whatsapp} />
                  <Bar dataKey="rcs" fill={COLORS.rcs} />
                  <Bar dataKey="voice" fill={COLORS.voice} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-sm shadow-none">
          <CardContent className="p-4">
            <h3 className="text-lg font-bold mb-3">Spend by channel</h3>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={usage.by_channel} dataKey="amount" nameKey="channel" cx="50%" cy="50%" innerRadius={50} outerRadius={90} paddingAngle={2}>
                    {usage.by_channel.map((e, i) => <Cell key={i} fill={COLORS[e.channel] || "#888"} />)}
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
          <h3 className="text-lg font-bold mb-3">Usage by channel</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground border-b border-border">
                <th className="px-3 py-2">Channel</th>
                <th className="px-3 py-2 text-right">Units</th>
                <th className="px-3 py-2 text-right">Amount (INR)</th>
              </tr>
            </thead>
            <tbody>
              {usage.by_channel.map(r => (
                <tr key={r.channel} className="border-b border-border">
                  <td className="px-3 py-2"><ChannelBadge channel={r.channel} /></td>
                  <td className="px-3 py-2 text-right font-mono">{r.units}</td>
                  <td className="px-3 py-2 text-right font-mono">₹{r.amount.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
