import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ChannelBadge } from "@/components/Badges";
import { AlarmClock, CheckCircle2, RefreshCcw, Loader2, Calendar, Clock } from "lucide-react";
import { toast } from "sonner";

function fmtDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}
function daysFromNow(iso) {
  if (!iso) return null;
  const diff = (new Date(iso).getTime() - Date.now()) / 86400000;
  if (diff < -0.5) return `${Math.abs(Math.round(diff))}d overdue`;
  if (diff < 0.5) return "today";
  if (diff < 1.5) return "tomorrow";
  return `in ${Math.round(diff)}d`;
}

const DEFAULT_STEPS = [
  { days_before: 7, channel: "sms",      label: "T-7 days · First reminder via SMS" },
  { days_before: 3, channel: "whatsapp", label: "T-3 days · Follow-up via WhatsApp" },
  { days_before: 1, channel: "voice",    label: "T-1 day · Final AI Voice call" },
];

export default function SmartReminders() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [marking, setMarking] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/reminders/upcoming");
      setRows(data || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load reminders");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const markPaid = async (billId) => {
    if (!window.confirm("Mark this bill as paid and cancel pending reminders?")) return;
    setMarking(billId);
    try {
      const { data } = await api.post(`/bills/${billId}/mark-paid`);
      toast.success(`Bill marked paid · cancelled ${data.cancelled} pending reminder(s)`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to mark paid");
    } finally { setMarking(null); }
  };

  const byBill = {};
  for (const r of rows) {
    const k = r.bill_id;
    byBill[k] = byBill[k] || { bill: r.bill, bill_id: k, steps: [] };
    byBill[k].steps.push(r);
  }
  const bills = Object.values(byBill);

  return (
    <div className="space-y-4" data-testid="smart-reminders-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Bill Collection Automation</div>
          <h1 className="text-3xl font-black tracking-tighter flex items-center gap-2">
            <AlarmClock className="h-6 w-6" /> Smart Reminders
          </h1>
          <p className="text-xs text-muted-foreground mt-1">
            Automatic multi-channel escalation for unpaid bills. Enable from <strong>Bills (AI)</strong> after upload.
          </p>
        </div>
        <Button variant="outline" className="rounded-sm gap-2" onClick={load} data-testid="reminders-refresh">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
          Refresh
        </Button>
      </div>

      {/* Escalation cadence preview */}
      <Card className="rounded-sm shadow-none" data-testid="reminders-cadence">
        <CardContent className="p-4">
          <div className="text-xs uppercase tracking-wider text-muted-foreground mb-3">Default escalation cadence</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {DEFAULT_STEPS.map((s) => (
              <div key={s.days_before} className="p-3 rounded-sm border border-border flex items-start gap-3">
                <div className="h-8 w-8 grid place-items-center rounded-sm bg-primary/10 text-primary">
                  <Clock className="h-4 w-4" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2"><ChannelBadge channel={s.channel} /></div>
                  <div className="text-xs text-muted-foreground mt-1">{s.label}</div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-3 border-b border-border flex items-center gap-2">
          <div className="text-xs text-muted-foreground">
            {bills.length} bill{bills.length === 1 ? "" : "s"} with pending reminders ·{" "}
            <span className="font-mono">{rows.length}</span> upcoming send{rows.length === 1 ? "" : "s"}
          </div>
        </CardContent>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2">Bill / Customer</th>
                <th className="px-3 py-2">Property</th>
                <th className="px-3 py-2 text-right">Amount</th>
                <th className="px-3 py-2">Upcoming reminders</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {bills.map((g) => (
                <tr key={g.bill_id} className="border-t border-border hover:bg-accent/40" data-testid={`reminder-bill-${g.bill_id}`}>
                  <td className="px-3 py-2">
                    <div className="font-medium">{g.bill?.name || "—"}</div>
                    <div className="text-[11px] text-muted-foreground font-mono">{g.bill?.phone || g.bill?.email || ""}</div>
                  </td>
                  <td className="px-3 py-2 text-xs font-mono">{g.bill?.property_id || "—"}</td>
                  <td className="px-3 py-2 text-right font-mono">
                    {g.bill?.amount ? `₹${Number(g.bill.amount).toLocaleString()}` : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1.5">
                      {g.steps
                        .sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at))
                        .map((s) => (
                        <div key={s.id} className="flex items-center gap-1 px-2 py-1 rounded-sm border border-border bg-card text-[11px]" data-testid={`reminder-step-${s.id}`}>
                          <ChannelBadge channel={s.channel} />
                          <Calendar className="h-3 w-3 ml-1 text-muted-foreground" />
                          <span className="font-mono">{fmtDate(s.scheduled_at)}</span>
                          <Badge variant="outline" className="rounded-sm text-[10px] ml-1">{daysFromNow(s.scheduled_at)}</Badge>
                        </div>
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      className="rounded-sm gap-1"
                      onClick={() => markPaid(g.bill_id)}
                      disabled={marking === g.bill_id || g.bill?.paid}
                      data-testid={`mark-paid-${g.bill_id}`}
                    >
                      {marking === g.bill_id ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
                      Mark Paid
                    </Button>
                  </td>
                </tr>
              ))}
              {bills.length === 0 && (
                <tr><td colSpan={5} className="text-center text-muted-foreground py-10">
                  {loading ? "Loading…" : "No pending reminders. Enable auto-reminders on bills to populate this list."}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
