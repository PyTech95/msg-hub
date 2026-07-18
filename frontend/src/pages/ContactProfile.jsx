import React, { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ChannelBadge, StatusBadge } from "@/components/Badges";
import { Phone, ArrowLeft, Send, MessageSquare, MessageCircle, Smartphone, AlertTriangle, Info, Paperclip, X, FileText, Video, Music, MapPin, Loader2 } from "lucide-react";
import { toast } from "sonner";

// GET media as blob so we can include the Authorization header, then convert to object URL
async function fetchMediaBlob(id) {
  const r = await api.get(`/media/${id}`, { responseType: "blob" });
  return URL.createObjectURL(r.data);
}

function MediaPreview({ media }) {
  const [blobUrl, setBlobUrl] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    if (!media?.gridfs_id || media.type === "location") return;
    fetchMediaBlob(media.gridfs_id)
      .then(url => { if (alive) setBlobUrl(url); })
      .catch(() => { if (alive) setFailed(true); });
    return () => {
      alive = false;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [media?.gridfs_id]);

  if (!media) return null;
  if (media.type === "location") {
    const url = `https://www.google.com/maps?q=${media.latitude},${media.longitude}`;
    return (
      <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-sm text-blue-600 hover:underline" data-testid="media-location">
        <MapPin className="h-4 w-4" /> {media.name || `${media.latitude}, ${media.longitude}`}
      </a>
    );
  }
  if (media.download_status === "pending") {
    return <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" /> Downloading {media.type}…</div>;
  }
  if (media.download_status === "failed" || failed) {
    return <div className="text-xs text-red-600" data-testid="media-failed">Media unavailable {media.error ? `— ${media.error}` : ""}</div>;
  }
  if (!blobUrl) return <div className="text-xs text-muted-foreground"><Loader2 className="h-3 w-3 inline animate-spin mr-1" /> Loading…</div>;
  if (media.type === "image" || media.type === "sticker") {
    return <img src={blobUrl} alt={media.filename || "image"} className="max-w-xs max-h-64 rounded-sm object-contain border" data-testid="media-image" />;
  }
  if (media.type === "video") {
    return <video src={blobUrl} controls className="max-w-xs max-h-64 rounded-sm border" data-testid="media-video" />;
  }
  if (media.type === "audio" || media.type === "voice") {
    return <audio src={blobUrl} controls className="w-full max-w-xs" data-testid="media-audio" />;
  }
  return (
    <a href={blobUrl} download={media.filename || "document"} className="flex items-center gap-2 text-sm text-blue-600 hover:underline" data-testid="media-document">
      <FileText className="h-4 w-4" /> {media.filename || "Document"}
      {media.size ? <span className="text-xs text-muted-foreground">({Math.round(media.size / 1024)} KB)</span> : null}
    </a>
  );
}

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

  // WhatsApp-specific send mode
  const [waMode, setWaMode] = useState("freeform"); // "freeform" | "template"
  const [tplName, setTplName] = useState("hello_world");
  const [tplLang, setTplLang] = useState("en_US");
  const [tplList, setTplList] = useState(null);       // null=not-loaded, []=loaded-empty, [...]=loaded
  const [tplLoading, setTplLoading] = useState(false);

  // WhatsApp Media Inbox (outbound)
  const fileInputRef = useRef(null);
  const [pendingFile, setPendingFile] = useState(null);
  const [pendingPreview, setPendingPreview] = useState(null); // object URL for image preview

  const load = async () => {
    const c = await api.get(`/contacts/${id}`);
    setContact(c.data);
    const t = await api.get(`/contacts/${id}/timeline`);
    setTimeline(t.data);
  };
  useEffect(() => { load(); }, [id]);

  // Auto-load approved templates when user switches WhatsApp tab to Template mode
  useEffect(() => {
    if (channel !== "whatsapp" || waMode !== "template" || tplList !== null) return;
    setTplLoading(true);
    api.get("/whatsapp/templates?status=APPROVED")
      .then(r => {
        const list = r.data.ok ? (r.data.templates || []) : [];
        setTplList(list);
        // Pre-select first template if current selection isn't available
        if (list.length > 0 && !list.find(t => t.name === tplName && t.language === tplLang)) {
          setTplName(list[0].name); setTplLang(list[0].language);
        }
      })
      .catch(() => setTplList([]))
      .finally(() => setTplLoading(false));
  }, [channel, waMode, tplList, tplName, tplLang]);

  const pickFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 25 * 1024 * 1024) { toast.error("File too large (max 25 MB)"); return; }
    setPendingFile(f);
    if (pendingPreview) URL.revokeObjectURL(pendingPreview);
    setPendingPreview(f.type.startsWith("image/") ? URL.createObjectURL(f) : null);
  };

  const clearPendingFile = () => {
    setPendingFile(null);
    if (pendingPreview) URL.revokeObjectURL(pendingPreview);
    setPendingPreview(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const send = async (e) => {
    e.preventDefault();
    const isTemplate = channel === "whatsapp" && waMode === "template";
    const isMedia = channel === "whatsapp" && waMode === "freeform" && pendingFile;
    if (!isTemplate && !isMedia && !body.trim()) return;
    if (isTemplate && !tplName.trim()) { toast.error("Template name required"); return; }
    setSending(true);
    try {
      if (isMedia) {
        const fd = new FormData();
        fd.append("to", contact.phone);
        fd.append("caption", body || "");
        fd.append("file", pendingFile);
        await api.post("/whatsapp/send-media", fd, { headers: { "Content-Type": "multipart/form-data" } });
        toast.success(`${pendingFile.type.split("/")[0] || "Media"} sent via WhatsApp`);
        setBody("");
        clearPendingFile();
      } else {
        const payload = { channel, contact_id: id, body: isTemplate ? "" : body };
        if (isTemplate) {
          payload.template_name = tplName.trim();
          payload.template_language = tplLang.trim() || "en_US";
        }
        await api.post("/messages/send", payload);
        toast.success(isTemplate
          ? `Template "${tplName}" queued — this always delivers when the template is approved by Meta.`
          : "Message queued");
        setBody("");
      }
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

  // Has the contact sent an inbound WhatsApp in the last 24h? (indicates open service window)
  const now = Date.now();
  const has24hInbound = (timeline.messages || []).some(m =>
    m.channel === "whatsapp" && m.direction === "inbound" &&
    (now - new Date(m.created_at).getTime()) <= 24 * 3600 * 1000
  );

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

            {channel === "whatsapp" && !has24hInbound && waMode === "freeform" && (
              <div className="flex items-start gap-2 p-3 rounded-sm border border-amber-300 bg-amber-50 dark:bg-amber-900/20 text-xs" data-testid="wa-window-warning">
                <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <div className="font-semibold text-amber-900 dark:text-amber-200">Meta 24-hour window is not open for this contact</div>
                  <div className="text-amber-800 dark:text-amber-300">
                    Meta will silently drop free-form text if the customer hasn&apos;t messaged your business in the last 24 hours (or if your phone number is still in Meta&apos;s dev-mode allowlist). Use an <strong>approved template</strong> instead — it always delivers.
                  </div>
                  <Button type="button" size="sm" variant="outline" className="rounded-sm h-7 mt-1 border-amber-400" onClick={() => setWaMode("template")} data-testid="switch-to-template-mode">
                    Switch to Template
                  </Button>
                </div>
              </div>
            )}

            {channel === "whatsapp" && (
              <div className="flex items-center gap-2" data-testid="wa-mode-toggle">
                <Button type="button" size="sm" variant={waMode === "freeform" ? "default" : "outline"} className="rounded-sm h-7 text-xs" onClick={() => setWaMode("freeform")} data-testid="wa-mode-freeform">
                  Free-form text
                </Button>
                <Button type="button" size="sm" variant={waMode === "template" ? "default" : "outline"} className="rounded-sm h-7 text-xs" onClick={() => setWaMode("template")} data-testid="wa-mode-template">
                  Approved template
                </Button>
                {has24hInbound && waMode === "freeform" && (
                  <span className="text-[11px] text-emerald-700 flex items-center gap-1 ml-2"><Info className="h-3 w-3" /> 24h window open</span>
                )}
              </div>
            )}

            <form onSubmit={send} className="space-y-2">
              {channel === "whatsapp" && waMode === "template" ? (
                <div className="space-y-2">
                  <div className="space-y-1">
                    <Label className="text-xs">Approved template</Label>
                    {tplLoading ? (
                      <div className="text-xs text-muted-foreground p-2">Loading approved templates from Meta…</div>
                    ) : (tplList && tplList.length > 0) ? (
                      <>
                        <select
                          value={`${tplName}|${tplLang}`}
                          onChange={e => {
                            const [n, l] = e.target.value.split("|");
                            setTplName(n); setTplLang(l);
                          }}
                          className="w-full rounded-sm border bg-background px-3 h-9 text-sm font-mono"
                          data-testid="wa-template-select"
                        >
                          {tplList.map(t => (
                            <option key={`${t.name}_${t.language}`} value={`${t.name}|${t.language}`}>
                              {t.name} · {t.language} · [{t.category}]{t.variable_count > 0 ? ` · ${t.variable_count} var${t.variable_count > 1 ? "s" : ""}` : ""}
                            </option>
                          ))}
                        </select>
                        {(() => {
                          const preview = (tplList.find(t => t.name === tplName && t.language === tplLang) || {}).body_preview;
                          return preview ? (
                            <div className="text-[11px] text-muted-foreground p-2 border rounded-sm bg-muted/30 whitespace-pre-wrap" data-testid="wa-template-preview">
                              <span className="font-semibold text-foreground">Preview: </span>{preview}
                            </div>
                          ) : null;
                        })()}
                      </>
                    ) : (
                      <>
                        <Input value={tplName} onChange={e => setTplName(e.target.value)} placeholder="hello_world" className="rounded-sm font-mono" data-testid="wa-template-name-input" />
                        <div className="text-[10px] text-muted-foreground">No approved templates found. Type manually or create one in <a className="underline" href="https://business.facebook.com/wa/manage/message-templates/" target="_blank" rel="noreferrer">Meta Business Manager</a>.</div>
                      </>
                    )}
                  </div>
                </div>
              ) : (
                <>
                  <Textarea value={body} onChange={e => setBody(e.target.value)} rows={3}
                    placeholder={pendingFile ? "Add a caption (optional)…" : `Write a ${channel} message…`} className="rounded-sm" data-testid="compose-message-input" />
                  {channel === "whatsapp" && (
                    <>
                      <input ref={fileInputRef} type="file" className="hidden"
                        accept="image/*,video/*,audio/*,application/pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv"
                        onChange={pickFile} data-testid="wa-media-file-input" />
                      {pendingFile ? (
                        <div className="flex items-center gap-3 p-2 border border-dashed rounded-sm bg-muted/30" data-testid="wa-media-pending">
                          {pendingPreview ? (
                            <img src={pendingPreview} alt="preview" className="h-14 w-14 object-cover rounded-sm border" />
                          ) : (
                            <div className="h-14 w-14 flex items-center justify-center border rounded-sm bg-background">
                              {pendingFile.type.startsWith("video/") ? <Video className="h-6 w-6 text-muted-foreground" /> :
                               pendingFile.type.startsWith("audio/") ? <Music className="h-6 w-6 text-muted-foreground" /> :
                               <FileText className="h-6 w-6 text-muted-foreground" />}
                            </div>
                          )}
                          <div className="flex-1 min-w-0 text-xs">
                            <div className="font-mono truncate">{pendingFile.name}</div>
                            <div className="text-muted-foreground">{Math.round(pendingFile.size / 1024)} KB · {pendingFile.type || "file"}</div>
                          </div>
                          <Button type="button" size="sm" variant="ghost" className="rounded-sm h-7 w-7 p-0" onClick={clearPendingFile} data-testid="wa-media-clear">
                            <X className="h-4 w-4" />
                          </Button>
                        </div>
                      ) : (
                        <Button type="button" size="sm" variant="outline" className="rounded-sm h-8 text-xs gap-1"
                          onClick={() => fileInputRef.current?.click()} data-testid="wa-attach-media-button">
                          <Paperclip className="h-3.5 w-3.5" /> Attach image / video / document
                        </Button>
                      )}
                    </>
                  )}
                </>
              )}
              <div className="flex justify-end">
                <Button type="submit" disabled={sending || (channel === "whatsapp" && waMode === "template" ? !tplName.trim() : (!body.trim() && !pendingFile))} className="rounded-sm gap-2" data-testid="send-message-button">
                  <Send className="h-4 w-4" /> {sending ? "Sending…" : (pendingFile ? "Send media" : "Send")}
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
                    <div className={`text-sm p-3 rounded-sm bg-card border border-border max-w-2xl row-${ev.channel} space-y-2`}>
                      {ev.media ? <MediaPreview media={ev.media} /> : null}
                      {ev.body ? <div className="whitespace-pre-wrap">{ev.body}</div> : null}
                    </div>
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
