import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { ChannelBadge } from "@/components/Badges";
import { FileText, Plus, Send, Trash2, Pencil, Eye, Loader2, ScrollText } from "lucide-react";
import { toast } from "sonner";

const DEFAULT_HTML = `<!doctype html>
<html><body style="font-family: Georgia, serif; padding: 60px; color:#111; max-width: 720px; margin: 0 auto;">
  <div style="border-bottom: 4px solid #000; padding-bottom: 8px; margin-bottom: 32px;">
    <div style="text-transform: uppercase; letter-spacing: 0.2em; font-size: 11px;">Property Tax Department</div>
    <h1 style="margin: 4px 0 0; font-size: 28px;">FORMAL NOTICE OF OUTSTANDING DUES</h1>
  </div>

  <p>Dear <b>{{name}}</b>,</p>

  <p>This is a formal notice regarding outstanding property tax dues for property
  <b>{{property_id}}</b> located at <b>{{address}}</b>.</p>

  <table style="width:100%; margin: 24px 0; border-collapse: collapse;">
    <tr><td style="padding: 8px; background:#f3f3f3;"><b>Owner</b></td><td style="padding: 8px;">{{name}}</td></tr>
    <tr><td style="padding: 8px; background:#f3f3f3;"><b>Property ID</b></td><td style="padding: 8px;">{{property_id}}</td></tr>
    <tr><td style="padding: 8px; background:#f3f3f3;"><b>Amount Due</b></td><td style="padding: 8px;">INR {{amount}}</td></tr>
    <tr><td style="padding: 8px; background:#f3f3f3;"><b>Due Date</b></td><td style="padding: 8px;">{{due_date}}</td></tr>
  </table>

  <p>Please ensure that the dues are cleared within <b>7 days</b> of receipt of this notice
  to avoid penal action under applicable property tax laws.</p>

  <p style="margin-top: 48px;">Yours sincerely,</p>
  <p><b>Property Tax Department</b><br/>
  Reference: {{property_id}}</p>
</body></html>`;

export default function Notices() {
  const [tpls, setTpls] = useState([]);
  const [bills, setBills] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: "", subject: "", description: "", html: DEFAULT_HTML });

  const [sendOpen, setSendOpen] = useState(false);
  const [sendTpl, setSendTpl] = useState(null);
  const [sendChannel, setSendChannel] = useState("email");
  const [sendBills, setSendBills] = useState(new Set());
  const [sendMsg, setSendMsg] = useState("Please find your formal notice attached.");
  const [sending, setSending] = useState(false);

  const load = async () => {
    const [t, b] = await Promise.all([api.get("/notice-templates"), api.get("/bills")]);
    setTpls(t.data); setBills(b.data);
  };
  useEffect(() => { load(); }, []);

  const openCreate = () => { setEditing(null); setForm({ name: "", subject: "", description: "", html: DEFAULT_HTML }); setOpen(true); };
  const openEdit = (t) => { setEditing(t); setForm({ name: t.name, subject: t.subject || "", description: t.description || "", html: t.html }); setOpen(true); };

  const save = async (e) => {
    e.preventDefault();
    try {
      if (editing) {
        await api.patch(`/notice-templates/${editing.id}`, form);
        toast.success("Template updated");
      } else {
        await api.post("/notice-templates", form);
        toast.success("Template created");
      }
      setOpen(false); load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete template?")) return;
    await api.delete(`/notice-templates/${id}`);
    toast.success("Deleted"); load();
  };

  const preview = async (tpl, sampleBill) => {
    try {
      const res = await api.post("/notices/preview",
        { template_id: tpl.id, variables: sampleBill || (bills[0] || { name: "Sample Name", property_id: "PROP-001", address: "Sample Address", amount: 1000, due_date: "2026-12-31" }) },
        { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      window.open(url, "_blank");
    } catch (err) { toast.error("Preview failed"); }
  };

  const startSend = (t) => { setSendTpl(t); setSendBills(new Set()); setSendOpen(true); };

  const send = async () => {
    if (sendBills.size === 0) return toast.error("Pick at least one bill");
    setSending(true);
    try {
      const { data } = await api.post("/notices/send", {
        template_id: sendTpl.id,
        bill_ids: Array.from(sendBills),
        channel: sendChannel,
        message: sendMsg,
      });
      toast.success(`Sent ${data.sent} notices via ${sendChannel.toUpperCase()}${data.skipped ? `, skipped ${data.skipped}` : ""}`);
      setSendOpen(false);
    } catch (err) { toast.error(err.response?.data?.detail || "Send failed"); }
    finally { setSending(false); }
  };

  return (
    <div className="space-y-4" data-testid="notices-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Legal Comms</div>
          <h1 className="text-3xl font-black tracking-tighter flex items-center gap-2"><ScrollText className="h-6 w-6" /> Notice Templates</h1>
          <p className="text-xs text-muted-foreground mt-1">HTML template + variables → personalized PDFs → bulk-delivered to bills or contacts.</p>
        </div>
        <Button onClick={openCreate} className="rounded-sm gap-2" data-testid="new-notice-template-button"><Plus className="h-4 w-4" /> New Template</Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {tpls.map(t => (
          <Card key={t.id} className="rounded-sm shadow-none" data-testid={`notice-template-${t.id}`}>
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="font-semibold flex items-center gap-2"><FileText className="h-4 w-4" /> {t.name}</div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{(t.html || "").length} chars</div>
              </div>
              {t.subject && <div className="text-xs text-muted-foreground">Subject: {t.subject}</div>}
              {t.description && <div className="text-xs">{t.description}</div>}
              <div className="flex flex-wrap justify-end gap-1 pt-1">
                <Button variant="outline" size="sm" className="rounded-sm gap-1" onClick={() => preview(t)} data-testid={`preview-notice-${t.id}`}>
                  <Eye className="h-3 w-3" /> Preview
                </Button>
                <Button size="sm" className="rounded-sm gap-1" onClick={() => startSend(t)} data-testid={`send-notice-${t.id}`}>
                  <Send className="h-3 w-3" /> Bulk send
                </Button>
                <Button variant="ghost" size="sm" className="rounded-sm gap-1" onClick={() => openEdit(t)} data-testid={`edit-notice-${t.id}`}>
                  <Pencil className="h-3 w-3" />
                </Button>
                <Button variant="ghost" size="sm" className="text-red-600 rounded-sm gap-1" onClick={() => del(t.id)} data-testid={`delete-notice-${t.id}`}>
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
        {tpls.length === 0 && <div className="text-sm text-muted-foreground">No templates yet. Create one to start sending notices.</div>}
      </div>

      {/* Create / Edit */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="rounded-sm max-w-4xl">
          <DialogHeader>
            <DialogTitle>{editing ? "Edit Notice Template" : "New Notice Template"}</DialogTitle>
            <DialogDescription>Use {`{{name}} {{property_id}} {{address}} {{amount}} {{due_date}}`} placeholders. Will be rendered to PDF.</DialogDescription>
          </DialogHeader>
          <form onSubmit={save} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Name</Label><Input required value={form.name} onChange={e=>setForm({...form,name:e.target.value})} className="rounded-sm" data-testid="notice-name-input" /></div>
              <div><Label>Email subject</Label><Input value={form.subject} onChange={e=>setForm({...form,subject:e.target.value})} className="rounded-sm" data-testid="notice-subject-input" /></div>
            </div>
            <div><Label>Description</Label><Input value={form.description} onChange={e=>setForm({...form,description:e.target.value})} className="rounded-sm" /></div>
            <div>
              <Label>HTML body</Label>
              <Textarea required rows={14} value={form.html} onChange={e=>setForm({...form,html:e.target.value})}
                className="rounded-sm font-mono text-[11px]" data-testid="notice-html-input" />
            </div>
            <DialogFooter><Button type="submit" className="rounded-sm" data-testid="save-notice-button">{editing ? "Save" : "Create"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Bulk send */}
      <Dialog open={sendOpen} onOpenChange={setSendOpen}>
        <DialogContent className="rounded-sm max-w-3xl">
          <DialogHeader>
            <DialogTitle>Send "{sendTpl?.name}" to bills</DialogTitle>
            <DialogDescription>Each bill gets a personalized PDF + message via the selected channel.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="flex gap-2">
              <Button variant={sendChannel === "email" ? "default" : "outline"} className="rounded-sm gap-2" onClick={() => setSendChannel("email")} data-testid="notice-channel-email">📧 Email</Button>
              <Button variant={sendChannel === "whatsapp" ? "default" : "outline"} className="rounded-sm gap-2" onClick={() => setSendChannel("whatsapp")} data-testid="notice-channel-whatsapp">💬 WhatsApp</Button>
            </div>
            <div>
              <Label>Cover message</Label>
              <Input value={sendMsg} onChange={e=>setSendMsg(e.target.value)} className="rounded-sm" data-testid="notice-cover-msg" />
            </div>
            <div className="border border-border rounded-sm max-h-80 overflow-y-auto">
              <div className="flex items-center justify-between p-2 border-b border-border bg-muted/40 text-xs">
                <span>{sendBills.size} of {bills.length} selected</span>
                <Button variant="ghost" size="sm" className="h-6 rounded-sm text-xs"
                  onClick={() => setSendBills(sendBills.size === bills.length ? new Set() : new Set(bills.map(b => b.id)))}
                  data-testid="notice-select-all-bills">
                  {sendBills.size === bills.length ? "Clear" : "Select all"}
                </Button>
              </div>
              {bills.map(b => (
                <label key={b.id} className="flex items-center gap-3 p-2 border-b border-border text-xs cursor-pointer hover:bg-accent/40" data-testid={`notice-bill-${b.id}`}>
                  <Checkbox checked={sendBills.has(b.id)} onCheckedChange={() => setSendBills(s => { const n = new Set(s); n.has(b.id) ? n.delete(b.id) : n.add(b.id); return n; })} />
                  <div className="flex-1">
                    <div className="font-medium">{b.name || "—"} <span className="text-muted-foreground font-mono">{b.property_id}</span></div>
                    <div className="text-muted-foreground">{sendChannel === "email" ? (b.email || "no email") : (b.phone || "no phone")} · ₹{b.amount}</div>
                  </div>
                </label>
              ))}
              {bills.length === 0 && <div className="text-sm text-muted-foreground p-4 text-center">No bills uploaded.</div>}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setSendOpen(false)}>Cancel</Button>
            <Button onClick={send} disabled={sending || sendBills.size === 0} className="rounded-sm gap-2" data-testid="notice-confirm-send">
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Send {sendBills.size} {sendBills.size === 1 ? "notice" : "notices"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
