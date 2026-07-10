import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Copy, Check, Send, MessageCircle, CheckCircle2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || window.location.origin;

function CopyField({ label, value, testId }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    toast.success(`${label} copied`);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <div className="flex gap-2">
        <Input readOnly value={value} className="rounded-sm font-mono text-xs bg-muted/40" data-testid={testId} />
        <Button type="button" variant="outline" size="icon" className="rounded-sm h-9 w-9 shrink-0" onClick={copy} data-testid={`${testId}-copy`}>
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
        </Button>
      </div>
    </div>
  );
}

export const MetaWhatsAppSetup = () => {
  const [setup, setSetup] = useState(null);
  const [to, setTo] = useState("");
  const [message, setMessage] = useState("Hello from tezsandesh.digital 👋");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    api.get("/whatsapp/setup").then(r => setSetup(r.data)).catch(() => {});
  }, []);

  if (!setup) return null;
  const callbackUrl = `${BACKEND_URL}${setup.webhook_path}`;

  const sendTest = async (e) => {
    e.preventDefault();
    setSending(true); setResult(null);
    try {
      const { data } = await api.post("/whatsapp/send-message", { to, message });
      setResult({ ok: true, ...data });
      toast.success(data.mode === "live" ? "Message sent via Meta Cloud API!" : "Sent in MOCK mode (add credentials to go live)");
    } catch (err) {
      const detail = err.response?.data?.detail || "Send failed";
      setResult({ ok: false, message: detail });
      toast.error(detail);
    } finally { setSending(false); }
  };

  return (
    <Card className="rounded-sm shadow-none border-orange-200 dark:border-orange-900/50" data-testid="meta-whatsapp-setup-card">
      <CardContent className="p-4 space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <MessageCircle className="h-4 w-4 text-orange-500" />
            <span className="font-semibold">Meta WhatsApp Cloud API — Setup</span>
          </div>
          {setup.live
            ? <Badge variant="outline" className="rounded-sm text-[10px] border-emerald-300 text-emerald-700 gap-1"><CheckCircle2 className="h-3 w-3" />LIVE</Badge>
            : <Badge variant="outline" className="rounded-sm text-[10px] border-amber-300 text-amber-700">MOCK — credentials pending</Badge>}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <CopyField label="Callback URL (paste in Meta dashboard → WhatsApp → Configuration)" value={callbackUrl} testId="meta-callback-url" />
          <CopyField label="Verify Token" value={setup.verify_token} testId="meta-verify-token" />
        </div>
        <div className="text-xs text-muted-foreground">
          Graph API {setup.graph_version} · Webhook field to subscribe: <strong>messages</strong> ·
          {setup.live ? ` Phone Number ID: ${setup.phone_number_id}` : " Add Access Token + Phone Number ID via the Meta WhatsApp Cloud provider card (Credentials → turn Mock OFF), or set WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID in backend .env."}
        </div>

        <form onSubmit={sendTest} className="border border-dashed border-border rounded-sm p-3 space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Quick test send</div>
          <div className="grid grid-cols-1 md:grid-cols-[220px_1fr_auto] gap-2">
            <Input required placeholder="+91XXXXXXXXXX" value={to} onChange={e => setTo(e.target.value)} className="rounded-sm" data-testid="meta-test-to-input" />
            <Input required placeholder="Message" value={message} onChange={e => setMessage(e.target.value)} className="rounded-sm" data-testid="meta-test-message-input" />
            <Button type="submit" disabled={sending} className="rounded-sm gap-1" data-testid="meta-test-send-button">
              <Send className="h-3.5 w-3.5" /> {sending ? "Sending…" : "Send"}
            </Button>
          </div>
          {result && (
            <div className={`p-2 rounded-sm border text-xs flex items-start gap-2 ${result.ok ? "border-emerald-300 bg-emerald-50 dark:bg-emerald-900/20" : "border-red-300 bg-red-50 dark:bg-red-900/20"}`} data-testid="meta-test-result">
              {result.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" /> : <AlertTriangle className="h-4 w-4 text-red-600 shrink-0" />}
              <div>
                {result.ok
                  ? <span>Sent in <strong>{(result.mode || "").toUpperCase()}</strong> mode · id: <span className="font-mono">{result.provider_message_id}</span></span>
                  : <span>{result.message}</span>}
              </div>
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
};
