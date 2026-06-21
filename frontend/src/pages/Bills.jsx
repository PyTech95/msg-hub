import React, { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { ChannelBadge } from "@/components/Badges";
import { Upload, FileText, Send, Mail, MessageCircle, MessageSquare, Trash2, Loader2, Sparkles, AlarmClock, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

const DEFAULT_TPL = "Dear {{name}}, your property bill #{{property_id}} for INR {{amount}} is due {{due_date}}. Please pay at the earliest.";
const DEFAULT_SUBJECT = "Property Bill Reminder — {{property_id}}";

export default function Bills() {
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [batches, setBatches] = useState([]);
  const [bills, setBills] = useState([]);
  const [batchFilter, setBatchFilter] = useState("");
  const [selected, setSelected] = useState(new Set());

  const [sendOpen, setSendOpen] = useState(false);
  const [sendChannel, setSendChannel] = useState("whatsapp");
  const [tpl, setTpl] = useState(DEFAULT_TPL);
  const [subj, setSubj] = useState(DEFAULT_SUBJECT);
  const [sending, setSending] = useState(false);

  const loadAll = async () => {
    const [b, bs] = await Promise.all([
      api.get("/bills/batches"),
      api.get("/bills", { params: { batch_id: batchFilter || undefined } }),
    ]);
    setBatches(b.data);
    setBills(bs.data);
  };
  useEffect(() => { loadAll(); }, [batchFilter]);

  const onPick = async (file) => {
    setUploading(true);
    const fd = new FormData(); fd.append("file", file);
    try {
      const { data } = await api.post("/bills/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      if (data.warning) {
        toast.warning(`Partial parse: ${data.warning.slice(0, 120)}`);
      } else {
        toast.success(`PDF parsed: ${data.bill_count} bills extracted from ${data.page_count} pages`);
      }
      setBatchFilter(data.batch_id);
      loadAll();
    } catch (err) {
      const detail = err.response?.data?.detail || "Upload failed";
      toast.error(typeof detail === "string" ? detail.slice(0, 200) : "Upload failed");
    } finally { setUploading(false); }
  };

  const allSelected = bills.length > 0 && selected.size === bills.length;
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(bills.map(b => b.id)));
  const toggle = (id) => setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const deleteBatch = async (bid) => {
    if (!window.confirm("Delete this batch and all its bills?")) return;
    await api.delete(`/bills/batches/${bid}`);
    toast.success("Batch deleted");
    if (batchFilter === bid) setBatchFilter("");
    loadAll();
  };

  const send = async () => {
    if (selected.size === 0) return toast.error("Select bills first");
    setSending(true);
    try {
      const { data } = await api.post("/bills/send", {
        channel: sendChannel,
        bill_ids: Array.from(selected),
        message_template: tpl,
        subject: sendChannel === "email" ? subj : undefined,
      });
      toast.success(`Sent ${data.sent} via ${sendChannel.toUpperCase()}${data.skipped ? `, skipped ${data.skipped}` : ""}`);
      setSendOpen(false);
      setSelected(new Set());
      loadAll();
    } catch (err) { toast.error(err.response?.data?.detail || "Send failed"); }
    finally { setSending(false); }
  };

  const enableReminders = async () => {
    if (selected.size === 0) return toast.error("Select bills first");
    if (!window.confirm(`Enable auto-reminders for ${selected.size} bill(s)?\n\n• T-7 days → SMS\n• T-3 days → WhatsApp\n• T-1 day → AI Voice call`)) return;
    try {
      const { data } = await api.post("/bills/enable-reminders", { bill_ids: Array.from(selected) });
      toast.success(`Auto-reminders enabled on ${data.bills_enabled} bill(s) · ${data.created} schedule(s) created${data.skipped ? ` · ${data.skipped} skipped (no due date)` : ""}`);
      setSelected(new Set());
      loadAll();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed to enable reminders"); }
  };

  const markPaid = async (billId) => {
    if (!window.confirm("Mark this bill as paid and cancel any pending reminders?")) return;
    try {
      const { data } = await api.post(`/bills/${billId}/mark-paid`);
      toast.success(`Bill paid · cancelled ${data.cancelled} pending reminder(s)`);
      loadAll();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed to mark paid"); }
  };

  return (
    <div className="space-y-4" data-testid="bills-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">AI-powered</div>
          <h1 className="text-3xl font-black tracking-tighter flex items-center gap-2"><Sparkles className="h-6 w-6" /> Bill Splitter</h1>
          <p className="text-xs text-muted-foreground mt-1">Upload a multi-bill PDF — Claude extracts each bill, then send personalized SMS/WhatsApp/Email.</p>
        </div>
        <div className="flex items-center gap-2">
          <input ref={fileRef} type="file" accept="application/pdf" className="hidden" onChange={e => e.target.files?.[0] && onPick(e.target.files[0])} data-testid="bill-file-input" />
          <Button onClick={() => fileRef.current?.click()} disabled={uploading} className="rounded-sm gap-2" data-testid="upload-bill-pdf-button">
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            {uploading ? "Parsing with Claude…" : "Upload PDF"}
          </Button>
        </div>
      </div>

      {batches.length > 0 && (
        <Card className="rounded-sm shadow-none">
          <CardContent className="p-3 flex items-center gap-2 flex-wrap">
            <Badge
              variant={batchFilter === "" ? "default" : "outline"}
              className="rounded-sm cursor-pointer"
              onClick={() => setBatchFilter("")}
              data-testid="batch-filter-all">All batches</Badge>
            {batches.map(b => (
              <Badge key={b.id}
                variant={batchFilter === b.id ? "default" : "outline"}
                className="rounded-sm cursor-pointer gap-2 group"
                onClick={() => setBatchFilter(b.id)}
                data-testid={`batch-filter-${b.id}`}>
                <FileText className="h-3 w-3" />
                {b.filename} <span className="font-mono opacity-70">({b.bill_count})</span>
                <Trash2 className="h-3 w-3 opacity-0 group-hover:opacity-100 hover:text-red-500" onClick={(e) => { e.stopPropagation(); deleteBatch(b.id); }} />
              </Badge>
            ))}
          </CardContent>
        </Card>
      )}

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-3 flex items-center gap-2 border-b border-border">
          <div className="text-xs text-muted-foreground">{bills.length} bills · {selected.size} selected</div>
          <div className="ml-auto flex items-center gap-2">
            <Button variant="outline" disabled={selected.size === 0} className="rounded-sm gap-2"
              onClick={() => { setSendChannel("sms"); setSendOpen(true); }} data-testid="bills-send-sms-button">
              <MessageSquare className="h-4 w-4 text-blue-600" /> SMS ({selected.size})
            </Button>
            <Button variant="outline" disabled={selected.size === 0} className="rounded-sm gap-2"
              onClick={() => { setSendChannel("whatsapp"); setSendOpen(true); }} data-testid="bills-send-whatsapp-button">
              <MessageCircle className="h-4 w-4 text-green-600" /> WhatsApp ({selected.size})
            </Button>
            <Button variant="outline" disabled={selected.size === 0} className="rounded-sm gap-2"
              onClick={() => { setSendChannel("email"); setSendOpen(true); }} data-testid="bills-send-email-button">
              <Mail className="h-4 w-4 text-amber-600" /> Email ({selected.size})
            </Button>
            <Button variant="outline" disabled={selected.size === 0} className="rounded-sm gap-2"
              onClick={enableReminders} data-testid="bills-enable-reminders-button">
              <AlarmClock className="h-4 w-4 text-violet-600" /> Auto-Remind ({selected.size})
            </Button>
          </div>
        </CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 sticky top-0">
              <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2 w-10"><Checkbox checked={allSelected} onCheckedChange={toggleAll} data-testid="bills-select-all" /></th>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Property</th>
                <th className="px-3 py-2 text-right">Amount</th>
                <th className="px-3 py-2">Due</th>
                <th className="px-3 py-2">Phone / Email</th>
                <th className="px-3 py-2">Sent</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {bills.map(b => (
                <tr key={b.id} className="border-t border-border hover:bg-accent/40" data-testid={`bill-row-${b.id}`}>
                  <td className="px-3 py-2"><Checkbox checked={selected.has(b.id)} onCheckedChange={() => toggle(b.id)} /></td>
                  <td className="px-3 py-2 font-medium">{b.name || "—"}</td>
                  <td className="px-3 py-2"><div className="text-xs font-mono">{b.property_id}</div><div className="text-[10px] text-muted-foreground">{b.address}</div></td>
                  <td className="px-3 py-2 text-right font-mono">{b.amount ? `₹${b.amount.toLocaleString()}` : "—"}</td>
                  <td className="px-3 py-2 text-xs font-mono">{b.due_date || "—"}</td>
                  <td className="px-3 py-2 text-xs">
                    {b.phone && <div className="font-mono">{b.phone}</div>}
                    {b.email && <div className="text-muted-foreground">{b.email}</div>}
                  </td>
                  <td className="px-3 py-2 space-x-1">
                    {b.sent?.sms && <Badge variant="outline" className="rounded-sm text-[10px] border-blue-300 text-blue-700">SMS</Badge>}
                    {b.sent?.whatsapp && <Badge variant="outline" className="rounded-sm text-[10px] border-green-300 text-green-700">WA</Badge>}
                    {b.sent?.email && <Badge variant="outline" className="rounded-sm text-[10px] border-amber-300 text-amber-700">EMAIL</Badge>}
                  </td>
                  <td className="px-3 py-2">
                    {b.paid
                      ? <Badge variant="outline" className="rounded-sm text-[10px] border-emerald-300 text-emerald-700">PAID</Badge>
                      : b.auto_remind
                        ? <Badge variant="outline" className="rounded-sm text-[10px] border-violet-300 text-violet-700">AUTO-REMIND</Badge>
                        : <span className="text-[10px] text-muted-foreground">—</span>
                    }
                  </td>
                  <td className="px-3 py-2 text-right">
                    {!b.paid && (
                      <Button size="sm" variant="ghost" className="rounded-sm h-7 px-2 gap-1 text-emerald-700 hover:text-emerald-800"
                        onClick={() => markPaid(b.id)} data-testid={`bill-mark-paid-${b.id}`}>
                        <CheckCircle2 className="h-3 w-3" /> Paid
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
              {bills.length === 0 && <tr><td colSpan={9} className="text-center text-muted-foreground py-10">No bills yet. Upload a PDF to extract them.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <Dialog open={sendOpen} onOpenChange={setSendOpen}>
        <DialogContent className="rounded-sm max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ChannelBadge channel={sendChannel} /> Send to {selected.size} {selected.size === 1 ? "bill" : "bills"}
            </DialogTitle>
            <DialogDescription>Variables: {`{{name}} {{phone}} {{email}} {{property_id}} {{address}} {{amount}} {{due_date}}`}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            {sendChannel === "email" && (
              <div>
                <Label>Subject</Label>
                <Input value={subj} onChange={e => setSubj(e.target.value)} className="rounded-sm" data-testid="bills-send-subject" />
              </div>
            )}
            <div>
              <Label>Message template</Label>
              <Textarea rows={5} value={tpl} onChange={e => setTpl(e.target.value)} className="rounded-sm font-mono text-xs" data-testid="bills-send-template" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setSendOpen(false)}>Cancel</Button>
            <Button onClick={send} disabled={sending} className="rounded-sm gap-2" data-testid="bills-confirm-send">
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Send {selected.size}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
