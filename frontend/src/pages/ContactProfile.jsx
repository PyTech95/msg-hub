import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ChannelBadge, StatusBadge } from "@/components/Badges";
import { Phone, ArrowLeft, Send, MessageSquare, MessageCircle, Smartphone } from "lucide-react";
import { toast } from "sonner";

const CHANNELS = [
  { key: "sms", label: "SMS", icon: MessageSquare },
  { key: "whatsapp", label: "WhatsApp", icon: MessageCircle },
  { key: "rcs", label: "RCS", icon: Smartphone },
];

function fmt(ts) { return new Date(ts).toLocaleString(); }

export default function ContactProfile() {
  const { id } = useParams();
  const [contact, setContact] = useState(null);
  const [timeline, setTimeline] = useState({ messages: [], calls: [] });
  const [channel, setChannel] = useState("sms");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);

  const load = async () => {
    const c = await api.get(`/contacts/${id}`);
    setContact(c.data);
    const t = await api.get(`/contacts/${id}/timeline`);
    setTimeline(t.data);
  };
  useEffect(() => { load(); }, [id]);

  const send = async (e) => {
    e.preventDefault();
    if (!body.trim()) return;
    setSending(true);
    try {
      await api.post("/messages/send", { channel, contact_id: id, body });
      toast.success("Message queued");
      setBody("");
      setTimeout(load, 700);
      setTimeout(load, 2200);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Send failed");
    } finally { setSending(false); }
  };

  const callNow = async () => {
    try {
      await api.post("/calls", { contact_id: id });
      toast.success("Call initiated");
      setTimeout(load, 1200);
      setTimeout(load, 3500);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Call failed");
    }
  };

  if (!contact) return <div className="text-sm text-muted-foreground">Loading…</div>;

  // Combined timeline events
  const events = [
    ...timeline.messages.map(m => ({ kind: "message", ts: m.created_at, ...m })),
    ...timeline.calls.map(c => ({ kind: "call", ts: c.created_at, ...c })),
  ].sort((a, b) => new Date(b.ts) - new Date(a.ts));

  return (
    <div className="space-y-4" data-testid="contact-profile-page">
      <Link to="/contacts" className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1" data-testid="back-to-contacts">
        <ArrowLeft className="h-3 w-3" /> Back to Contacts
      </Link>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="rounded-sm shadow-none">
          <CardContent className="p-5 space-y-4">
            <div>
              <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Contact</div>
              <h1 className="text-2xl font-black tracking-tighter">{contact.name}</h1>
              <div className="text-sm font-mono mt-1">{contact.phone}</div>
              <div className="text-xs text-muted-foreground">{contact.email || "—"}</div>
            </div>
            <div className="grid grid-cols-2 gap-2 pt-2">
              <Button onClick={callNow} variant="outline" className="rounded-sm gap-2" data-testid="click-to-call-button">
                <Phone className="h-4 w-4 text-emerald-600" /> Call now
              </Button>
            </div>
            <div className="space-y-2 pt-2 border-t border-border text-xs">
              <div><span className="text-muted-foreground">Tags: </span>{(contact.tags || []).join(", ") || "—"}</div>
              <div><span className="text-muted-foreground">City: </span>{contact.custom_fields?.city || "—"}</div>
              <div><span className="text-muted-foreground">DND: </span>{contact.dnd ? "Yes" : "No"}</div>
              <div><span className="text-muted-foreground">Opted out: </span>{contact.opted_out ? "Yes" : "No"}</div>
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2 rounded-sm shadow-none">
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center gap-2">
              {CHANNELS.map(c => (
                <Button key={c.key} type="button" variant={channel === c.key ? "default" : "outline"}
                  size="sm" className="rounded-sm gap-2" onClick={() => setChannel(c.key)}
                  data-testid={`channel-tab-${c.key}`}>
                  <c.icon className="h-3.5 w-3.5" /> {c.label}
                </Button>
              ))}
            </div>
            <form onSubmit={send} className="space-y-2">
              <Textarea value={body} onChange={e => setBody(e.target.value)} rows={3}
                placeholder={`Write a ${channel} message…`} className="rounded-sm" data-testid="compose-message-input" />
              <div className="flex justify-end">
                <Button type="submit" disabled={sending || !body.trim()} className="rounded-sm gap-2" data-testid="send-message-button">
                  <Send className="h-4 w-4" /> {sending ? "Sending…" : "Send"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-5">
          <div className="mb-4">
            <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Activity</div>
            <h3 className="text-lg font-bold">Communication Timeline</h3>
          </div>
          {events.length === 0 ? (
            <div className="text-sm text-muted-foreground py-6 text-center">No activity yet. Send a message or place a call.</div>
          ) : (
            <ul className="relative pl-6 border-l-2 border-border space-y-4" data-testid="contact-timeline">
              {events.map((ev, idx) => (
                <li key={idx} className="relative">
                  <span className={`absolute -left-[31px] top-1.5 h-3 w-3 rounded-full ring-4 ring-background ${
                    ev.kind === "call" ? "bg-stone-500" :
                    ev.channel === "sms" ? "bg-blue-500" :
                    ev.channel === "whatsapp" ? "bg-green-500" :
                    ev.channel === "rcs" ? "bg-orange-500" : "bg-zinc-500"
                  }`} />
                  <div className="flex items-center gap-2 mb-1">
                    {ev.kind === "call" ? (
                      <span className="text-xs font-semibold flex items-center gap-1"><Phone className="h-3 w-3" /> Voice Call ({ev.direction})</span>
                    ) : (
                      <>
                        <ChannelBadge channel={ev.channel} />
                        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{ev.direction}</span>
                      </>
                    )}
                    <StatusBadge status={ev.status} />
                    <span className="text-xs text-muted-foreground ml-auto">{fmt(ev.ts)}</span>
                  </div>
                  {ev.kind === "message" ? (
                    <div className={`text-sm p-3 rounded-sm bg-card border border-border max-w-2xl row-${ev.channel}`}>{ev.body}</div>
                  ) : (
                    <div className="text-sm p-3 rounded-sm bg-card border border-border max-w-2xl row-voice space-y-1">
                      <div>Duration: <span className="font-mono">{ev.duration_sec || 0}s</span></div>
                      {ev.recording_url && <div className="text-xs text-muted-foreground">Recording: <span className="font-mono">{ev.recording_url}</span></div>}
                      {ev.notes && <div className="text-xs">{ev.notes}</div>}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
