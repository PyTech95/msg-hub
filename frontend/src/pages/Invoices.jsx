import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChannelBadge } from "@/components/Badges";
import { FileText, Download, ReceiptText, FileDown } from "lucide-react";

function downloadJson(name, obj) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = name + ".json";
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}

async function downloadInvoiceCSV(month) {
  const res = await api.get(`/export/invoice/${month}.csv`, { responseType: "blob" });
  const url = URL.createObjectURL(new Blob([res.data]));
  const a = document.createElement("a"); a.href = url; a.download = `invoice-${month}.csv`;
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}

async function downloadInvoicePDF(month) {
  const res = await api.get(`/export/invoice/${month}.pdf`, { responseType: "blob" });
  const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
  const a = document.createElement("a"); a.href = url; a.download = `invoice-${month}.pdf`;
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}

export default function Invoices() {
  const [data, setData] = useState(null);
  const [detail, setDetail] = useState(null);

  useEffect(() => { api.get("/invoices").then(r => setData(r.data)); }, []);

  const openDetail = async (month) => {
    const { data } = await api.get(`/invoices/${month}`);
    setDetail(data);
  };

  if (!data) return <div className="text-sm text-muted-foreground">Loading invoices…</div>;

  return (
    <div className="space-y-4" data-testid="invoices-page">
      <div>
        <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Billing</div>
        <h1 className="text-3xl font-black tracking-tighter flex items-center gap-2">
          <ReceiptText className="h-6 w-6" /> Invoices
        </h1>
        <p className="text-xs text-muted-foreground mt-1">Monthly usage billed at your per-channel markup. Configure markup in <strong>Settings</strong>.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {Object.entries(data.markup_pct || {}).map(([ch, pct]) => (
          <Card key={ch} className="rounded-sm shadow-none">
            <CardContent className="p-3">
              <div className="flex items-center justify-between">
                <ChannelBadge channel={ch} />
                <span className="text-xs uppercase tracking-wider text-muted-foreground">Markup</span>
              </div>
              <div className="text-2xl font-black font-mono mt-1">{pct}%</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-4">
          <h3 className="text-lg font-bold mb-3">Monthly invoices</h3>
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2">Month</th>
                <th className="px-3 py-2 text-right">Units</th>
                <th className="px-3 py-2 text-right">Base (INR)</th>
                <th className="px-3 py-2 text-right">Billable (INR)</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.invoices.map(inv => (
                <tr key={inv.month} className="border-t border-border hover:bg-accent/40" data-testid={`invoice-row-${inv.month}`}>
                  <td className="px-3 py-2 font-mono">{inv.month}</td>
                  <td className="px-3 py-2 text-right font-mono">{inv.units_total}</td>
                  <td className="px-3 py-2 text-right font-mono">₹{inv.base_total.toFixed(2)}</td>
                  <td className="px-3 py-2 text-right font-mono font-bold">₹{inv.billable_total.toFixed(2)}</td>
                  <td className="px-3 py-2 text-right space-x-1">
                    <Button variant="outline" size="sm" className="rounded-sm gap-1" onClick={() => openDetail(inv.month)} data-testid={`view-invoice-${inv.month}`}>
                      <FileText className="h-3 w-3" /> View
                    </Button>
                    <Button variant="outline" size="sm" className="rounded-sm gap-1" onClick={() => downloadInvoiceCSV(inv.month)} data-testid={`csv-invoice-${inv.month}`}>
                      <FileDown className="h-3 w-3" /> CSV
                    </Button>
                    <Button variant="outline" size="sm" className="rounded-sm gap-1" onClick={() => downloadInvoicePDF(inv.month)} data-testid={`pdf-invoice-${inv.month}`}>
                      <FileText className="h-3 w-3" /> PDF
                    </Button>
                    <Button variant="outline" size="sm" className="rounded-sm gap-1" onClick={() => downloadJson(`invoice-${inv.month}`, inv)} data-testid={`download-invoice-${inv.month}`}>
                      <Download className="h-3 w-3" /> JSON
                    </Button>
                  </td>
                </tr>
              ))}
              {data.invoices.length === 0 && <tr><td colSpan={5} className="text-center text-muted-foreground py-10">No invoice data yet — send some messages first.</td></tr>}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {detail && (
        <Card className="rounded-sm shadow-none" data-testid="invoice-detail">
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold">Invoice {detail.month}</h3>
              <Button variant="ghost" size="sm" className="rounded-sm" onClick={() => setDetail(null)}>Close</Button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <div className="p-3 rounded-sm border border-border"><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Units</div><div className="font-black font-mono text-xl">{detail.units_total}</div></div>
              <div className="p-3 rounded-sm border border-border"><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Base</div><div className="font-black font-mono text-xl">₹{detail.base_total.toFixed(2)}</div></div>
              <div className="p-3 rounded-sm border border-border"><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Billable</div><div className="font-black font-mono text-xl">₹{detail.billable_total.toFixed(2)}</div></div>
              <div className="p-3 rounded-sm border border-border"><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Records</div><div className="font-black font-mono text-xl">{detail.record_count}</div></div>
            </div>
            <table className="w-full text-sm">
              <thead className="bg-muted/40"><tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2">Channel</th>
                <th className="px-3 py-2 text-right">Units</th>
                <th className="px-3 py-2 text-right">Base</th>
                <th className="px-3 py-2 text-right">Markup</th>
                <th className="px-3 py-2 text-right">Billable</th>
              </tr></thead>
              <tbody>
                {detail.channels.map(c => (
                  <tr key={c.channel} className="border-t border-border">
                    <td className="px-3 py-2"><ChannelBadge channel={c.channel} /></td>
                    <td className="px-3 py-2 text-right font-mono">{c.units}</td>
                    <td className="px-3 py-2 text-right font-mono">₹{c.base.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right font-mono">{c.markup_pct}%</td>
                    <td className="px-3 py-2 text-right font-mono font-bold">₹{c.billable.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
