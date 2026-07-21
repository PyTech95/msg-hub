import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useSearchParams, Link } from "react-router-dom";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Send, Search, MessageCircle, User, Paperclip, X, FileText, Video, Music, MapPin, Loader2, Users, Filter, StickyNote, ChevronLeft, SmilePlus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const REACTION_EMOJIS = ["👍", "❤️", "😂", "😮", "😢", "🙏"];

// Blob fetch with auth header for media
async function fetchMediaBlob(id) {
  const r = await api.get(`/media/${id}`, { responseType: "blob" });
  return URL.createObjectURL(r.data);
}

function MediaBubble({ media }) {
  const [url, setUrl] = useState(null);
  const [failed, setFailed] = useState(false);
  const urlRef = useRef(null);
  useEffect(() => {
    let alive = true;
    if (!media?.gridfs_id || media.type === "location") return;
    fetchMediaBlob(media.gridfs_id).then(u => {
      if (alive) { urlRef.current = u; setUrl(u); }
      else URL.revokeObjectURL(u);
    }).catch(() => { if (alive) setFailed(true); });
    return () => {
      alive = false;
      if (urlRef.current) { URL.revokeObjectURL(urlRef.current); urlRef.current = null; }
    };
  }, [media?.gridfs_id, media?.type]);
  if (!media) return null;
  if (media.type === "location") {
    return (
      <a href={`https://www.google.com/maps?q=${media.latitude},${media.longitude}`} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-xs underline text-blue-600">
        <MapPin className="h-3.5 w-3.5" /> {media.name || `${media.latitude}, ${media.longitude}`}
      </a>);
  }
  if (media.download_status === "pending") return <div className="text-[11px] text-muted-foreground flex items-center gap-1"><Loader2 className="h-3 w-3 animate-spin" /> downloading…</div>;
  if (failed || media.download_status === "failed") return <div className="text-[11px] text-red-600">Media unavailable</div>;
  if (!url) return <div className="text-[11px] text-muted-foreground flex items-center gap-1"><Loader2 className="h-3 w-3 animate-spin" /> loading</div>;
  if (media.type === "image" || media.type === "sticker") return <img src={url} alt="" className="max-w-[280px] max-h-[240px] rounded object-contain" data-testid="chat-media-image" />;
  if (media.type === "video") return <video src={url} controls className="max-w-[280px] max-h-[240px] rounded" data-testid="chat-media-video" />;
  if (media.type === "audio" || media.type === "voice") return <audio src={url} controls className="w-full max-w-[280px]" data-testid="chat-media-audio" />;
  return (
    <a href={url} download={media.filename || "document"} className="flex items-center gap-1.5 text-xs underline text-blue-600" data-testid="chat-media-document">
      <FileText className="h-3.5 w-3.5" /> {media.filename || "Document"}
    </a>);
}

const statusTick = (m) => {
  if (m.direction !== "outbound") return "";
  if (m.status === "read") return <span className="text-blue-500">✓✓</span>;
  if (m.status === "delivered") return "✓✓";
  if (m.status === "sent") return "✓";
  if (m.status === "failed") return <span className="text-red-500">✗</span>;
  return "";
};

const initials = (name) => (name || "?").split(/\s+/).map(s => s[0]).slice(0, 2).join("").toUpperCase();
const timeShort = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
  if (isToday) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  const daysAgo = Math.floor((now - d) / 86400000);
  if (daysAgo < 7) return d.toLocaleDateString([], { weekday: "short" });
  return d.toLocaleDateString([], { day: "2-digit", month: "2-digit" });
};

const dayLabel = (iso) => {
  const d = new Date(iso);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) return "Today";
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" });
};

function MessageActions({ message, onReact, onDelete, showDelete = true }) {
  const [showPicker, setShowPicker] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setShowPicker(v => !v)}
        className="h-6 w-6 rounded-full bg-white dark:bg-slate-800 border shadow-sm flex items-center justify-center hover:scale-110 transition"
        title="React"
        data-testid={`react-btn-${message.id}`}
      >
        <SmilePlus className="h-3 w-3" />
      </button>
      {showPicker && (
        <div className="absolute bottom-full mb-1 right-0 bg-white dark:bg-slate-900 border rounded-full shadow-md flex gap-0.5 p-1 z-10" data-testid={`picker-${message.id}`}>
          {REACTION_EMOJIS.map(e => (
            <button key={e}
              onClick={() => { onReact(message.id, e); setShowPicker(false); }}
              className="text-base hover:scale-125 transition"
              data-testid={`emoji-${e}`}
            >{e}</button>
          ))}
        </div>
      )}
      {showDelete && (
        <button
          onClick={() => onDelete(message.id)}
          className="mt-0.5 h-6 w-6 rounded-full bg-white dark:bg-slate-800 border shadow-sm flex items-center justify-center hover:scale-110 transition text-red-500"
          title="Delete from inbox"
          data-testid={`delete-btn-${message.id}`}
        >
          <Trash2 className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}

export default function Inbox() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const activeId = params.get("c") || null;
  const [convs, setConvs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQ, setSearchQ] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);

  const [contact, setContact] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [nextCursor, setNextCursor] = useState(null);

  const [body, setBody] = useState("");
  const [isNote, setIsNote] = useState(false);
  const [sending, setSending] = useState(false);
  const [pendingFile, setPendingFile] = useState(null);
  const [pendingPreview, setPendingPreview] = useState(null);
  const fileInputRef = useRef(null);
  const scrollerRef = useRef(null);

  // Multi-number sender picker
  const [phoneNumbers, setPhoneNumbers] = useState([]);
  const [senderPhoneId, setSenderPhoneId] = useState("");

  const loadConversations = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/conversations", { params: { q: searchQ || undefined, unread_only: unreadOnly || undefined, channel: "whatsapp" } });
      setConvs(data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
    finally { setLoading(false); }
  }, [searchQ, unreadOnly]);

  useEffect(() => { loadConversations(); }, [loadConversations]);
  useEffect(() => {
    api.get("/whatsapp/phone-numbers").then(r => {
      const list = (r.data || []).filter(n => n.is_active !== false);
      setPhoneNumbers(list);
      const primary = list.find(n => n.is_primary) || list[0];
      if (primary) setSenderPhoneId(primary.phone_number_id);
    }).catch(() => setPhoneNumbers([]));
  }, []);

  const loadChat = useCallback(async (cid, cursor = null) => {
    if (!cid) return;
    if (cursor) setLoadingMore(true); else setChatLoading(true);
    try {
      const { data } = await api.get(`/contacts/${cid}/timeline`, { params: { before: cursor || undefined, limit: 100 } });
      if (cursor) {
        setMsgs(prev => [...data.messages, ...prev]);
      } else {
        setMsgs(data.messages);
        const c = await api.get(`/contacts/${cid}`);
        setContact(c.data);
        // Mark conversation as read
        api.post(`/conversations/${cid}/read`, {}, { params: { channel: "whatsapp" } }).catch(() => {});
      }
      setHasMore(data.has_more);
      setNextCursor(data.next_cursor);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load chat"); }
    finally { setChatLoading(false); setLoadingMore(false); }
  }, []);

  useEffect(() => { if (activeId) loadChat(activeId); else { setMsgs([]); setContact(null); } }, [activeId, loadChat]);
  useEffect(() => {
    // Auto scroll to bottom on new-chat or new-message
    if (scrollerRef.current && !loadingMore) {
      scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
    }
  }, [contact?.id, msgs.length, loadingMore]);

  // Realtime new-message listener
  useEffect(() => {
    const onNew = (e) => {
      const { detail } = e;
      if (!detail) return;
      if (activeId && detail.contact_id === activeId) {
        setMsgs(prev => [...prev, detail]);
      }
      loadConversations();
    };
    window.addEventListener("cpaas:new_message", onNew);
    return () => window.removeEventListener("cpaas:new_message", onNew);
  }, [activeId, loadConversations]);

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

  const send = async () => {
    if (!activeId || (!body.trim() && !pendingFile)) return;
    setSending(true);
    try {
      if (isNote) {
        await api.post("/conversations/notes", { contact_id: activeId, body, channel: "whatsapp" });
        setBody(""); setIsNote(false);
      } else if (pendingFile) {
        const fd = new FormData();
        fd.append("to", contact.phone);
        fd.append("caption", body || "");
        fd.append("file", pendingFile);
        if (senderPhoneId) fd.append("phone_number_id", senderPhoneId);
        await api.post("/whatsapp/send-media", fd, { headers: { "Content-Type": "multipart/form-data" } });
        setBody(""); clearPendingFile();
      } else {
        await api.post("/messages/send", {
          channel: "whatsapp", contact_id: activeId, body,
          ...(senderPhoneId ? { phone_number_id: senderPhoneId } : {}),
        });
        setBody("");
      }
      setTimeout(() => loadChat(activeId), 400);
      setTimeout(loadConversations, 800);
    } catch (e) { toast.error(e.response?.data?.detail || "Send failed"); }
    finally { setSending(false); }
  };

  const react = async (messageId, emoji) => {
    try {
      await api.post("/messages/reactions", { message_id: messageId, emoji });
      toast.success(emoji ? `Reacted ${emoji}` : "Reaction removed");
      loadChat(activeId);
    } catch (e) { toast.error(e.response?.data?.detail || "Reaction failed"); }
  };

  const deleteMessage = async (messageId) => {
    if (!window.confirm("Delete this message from your inbox? (Recipient's phone will still show it — Meta does not support server-side unsend.)")) return;
    try {
      await api.delete(`/messages/${messageId}`);
      setMsgs(prev => prev.filter(m => m.id !== messageId));
      toast.success("Message deleted from inbox");
    } catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  // Filter & group messages by day
  const grouped = useMemo(() => {
    const g = [];
    let currentDay = null;
    for (const m of msgs) {
      const day = dayLabel(m.created_at);
      if (day !== currentDay) { g.push({ __day: day }); currentDay = day; }
      g.push(m);
    }
    return g;
  }, [msgs]);

  const activeConv = convs.find(c => c.contact_id === activeId);

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]" data-testid="inbox-page">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">WhatsApp</div>
          <h1 className="text-2xl font-black tracking-tighter flex items-center gap-2">
            <MessageCircle className="h-6 w-6 text-green-500" /> Inbox
          </h1>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Users className="h-3.5 w-3.5" /> {convs.length} conversation{convs.length !== 1 ? "s" : ""}
        </div>
      </div>

      <Card className="rounded-sm shadow-none flex-1 overflow-hidden flex">
        {/* LEFT — Conversation list */}
        <aside className={`w-full md:w-[360px] border-r flex-col ${activeId ? "hidden md:flex" : "flex"}`} data-testid="conv-list">
          <div className="p-2 border-b space-y-2">
            <div className="relative">
              <Search className="h-3.5 w-3.5 absolute left-2 top-2.5 text-muted-foreground" />
              <Input
                placeholder="Search chats or numbers…"
                value={searchQ}
                onChange={e => setSearchQ(e.target.value)}
                className="h-8 pl-7 rounded-sm text-xs"
                data-testid="conv-search"
              />
            </div>
            <div className="flex items-center justify-between">
              <button
                onClick={() => setUnreadOnly(v => !v)}
                className={`text-[10px] px-2 py-1 rounded-sm border transition ${unreadOnly ? "bg-green-100 border-green-300 text-green-700" : "border-muted-foreground/30 text-muted-foreground"}`}
                data-testid="filter-unread"
              >
                <Filter className="h-3 w-3 inline mr-1" /> Unread only
              </button>
              {phoneNumbers.length > 1 && (
                <select value={senderPhoneId} onChange={e => setSenderPhoneId(e.target.value)}
                  className="h-6 text-[10px] rounded-sm border bg-background px-1" data-testid="inbox-sender-select" title="Sender number">
                  {phoneNumbers.map(n => (
                    <option key={n.phone_number_id} value={n.phone_number_id}>
                      {n.is_primary ? "★ " : ""}{n.display_phone_number || n.phone_number_id.slice(-6)}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {loading ? <div className="p-4 text-center text-xs text-muted-foreground">Loading…</div> :
              convs.length === 0 ? <div className="p-6 text-center text-xs text-muted-foreground">No conversations yet.</div> :
                convs.map(c => (
                  <button
                    key={`${c.contact_id}_${c.channel}`}
                    onClick={() => setParams({ c: c.contact_id })}
                    className={`w-full text-left p-3 border-b hover:bg-muted/50 transition ${activeId === c.contact_id ? "bg-muted" : ""}`}
                    data-testid={`conv-item-${c.contact_id}`}
                  >
                    <div className="flex items-start gap-2.5">
                      <div className="h-10 w-10 rounded-full bg-gradient-to-br from-green-400 to-emerald-600 text-white flex items-center justify-center text-xs font-bold shrink-0">
                        {initials(c.contact_name)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-sm font-semibold truncate">{c.contact_name || c.contact_phone}</div>
                          <div className="text-[10px] text-muted-foreground shrink-0">{timeShort(c.last_message_at)}</div>
                        </div>
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-[11px] text-muted-foreground truncate flex-1">
                            {c.last_direction === "outbound" ? <span className="mr-1">{statusTick({ direction: "outbound", status: c.last_status })}</span> : null}
                            {c.last_media_type ? <span className="italic">[{c.last_media_type}] </span> : null}
                            {c.last_message || "—"}
                          </div>
                          {c.unread_count > 0 && (
                            <Badge className="rounded-full h-4 min-w-[16px] px-1 text-[10px] bg-green-500 hover:bg-green-500" data-testid={`unread-${c.contact_id}`}>
                              {c.unread_count > 99 ? "99+" : c.unread_count}
                            </Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-1 mt-0.5">
                          {c.assigned_to && <Badge variant="outline" className="rounded-sm text-[9px] px-1 py-0 h-4">@{c.assigned_to.split("@")[0]}</Badge>}
                          {(c.tags || []).slice(0, 2).map(t => (
                            <Badge key={t} variant="outline" className="rounded-sm text-[9px] px-1 py-0 h-4">{t}</Badge>
                          ))}
                        </div>
                      </div>
                    </div>
                  </button>
                ))}
          </div>
        </aside>

        {/* RIGHT — Chat panel */}
        <section className={`flex-1 flex flex-col ${activeId ? "flex" : "hidden md:flex"}`} data-testid="chat-panel">
          {!activeId || !contact ? (
            <div className="flex-1 flex items-center justify-center text-center p-8">
              <div className="space-y-2 text-muted-foreground max-w-sm">
                <MessageCircle className="h-16 w-16 mx-auto text-muted-foreground/30" />
                <div className="text-sm">Select a conversation to start chatting</div>
                <div className="text-xs">Or search for a contact number to open a new one.</div>
              </div>
            </div>
          ) : (
            <>
              {/* Chat header */}
              <div className="p-3 border-b flex items-center gap-3 bg-muted/20">
                <Button variant="ghost" size="sm" className="md:hidden h-8 w-8 p-0" onClick={() => setParams({})} data-testid="back-to-list">
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <div className="h-10 w-10 rounded-full bg-gradient-to-br from-green-400 to-emerald-600 text-white flex items-center justify-center text-xs font-bold">
                  {initials(contact.name)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold truncate">{contact.name}</div>
                  <div className="text-[10px] text-muted-foreground font-mono">{contact.phone}</div>
                </div>
                {activeConv?.assigned_to && (
                  <Badge variant="outline" className="rounded-sm text-[10px]" data-testid="chat-assigned">
                    <User className="h-2.5 w-2.5 mr-0.5" /> {activeConv.assigned_to.split("@")[0]}
                  </Badge>
                )}
                <Link to={`/contacts/${activeId}`}>
                  <Button variant="outline" size="sm" className="rounded-sm h-7 text-xs" data-testid="open-profile">Profile</Button>
                </Link>
              </div>

              {/* Messages */}
              <div ref={scrollerRef} className="flex-1 overflow-y-auto p-4 space-y-1.5 bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2240%22 height=%2240%22><rect width=%2240%22 height=%2240%22 fill=%22%23f0f4f0%22/></svg>')]" data-testid="chat-messages">
                {hasMore && (
                  <div className="text-center">
                    <Button variant="ghost" size="sm" className="h-6 text-[10px]" disabled={loadingMore}
                      onClick={() => loadChat(activeId, nextCursor)} data-testid="load-older">
                      {loadingMore ? "Loading…" : "Load older messages"}
                    </Button>
                  </div>
                )}
                {chatLoading && msgs.length === 0 && <div className="text-center text-xs text-muted-foreground p-4">Loading messages…</div>}
                {grouped.map((it, i) => {
                  if (it.__day) return (
                    <div key={`d${i}`} className="text-center py-2">
                      <span className="text-[10px] bg-white/80 dark:bg-black/60 px-2 py-0.5 rounded shadow-sm text-muted-foreground">{it.__day}</span>
                    </div>);
                  const m = it;
                  const isOut = m.direction === "outbound";
                  const isInternalMsg = m.direction === "internal" || m.is_internal;
                  return (
                    <div key={m.id} className={`flex ${isOut ? "justify-end" : isInternalMsg ? "justify-center" : "justify-start"} group`} data-testid={`msg-${m.id}`}>
                      <div className="flex items-end gap-1 max-w-[75%]">
                        {isOut && (
                          <div className="opacity-0 group-hover:opacity-100 transition flex flex-col gap-0.5">
                            <MessageActions message={m} onReact={react} onDelete={deleteMessage} />
                          </div>
                        )}
                        <div className={`p-2 rounded-lg text-xs shadow-sm relative ${
                          isInternalMsg ? "bg-yellow-100 dark:bg-yellow-900/40 border border-yellow-300 dark:border-yellow-700 max-w-[85%]"
                          : isOut ? "bg-green-100 dark:bg-green-900/40" : "bg-white dark:bg-slate-800"}`}>
                          {isInternalMsg && (
                            <div className="text-[9px] uppercase tracking-wider text-yellow-700 dark:text-yellow-300 mb-1 flex items-center gap-1">
                              <StickyNote className="h-2.5 w-2.5" /> Internal note · {m.author}
                            </div>
                          )}
                          {m.media && <div className="mb-1"><MediaBubble media={m.media} /></div>}
                          {m.body && <div className="whitespace-pre-wrap">{m.body}</div>}
                          {(m.reactions || []).length > 0 && (
                            <div className="absolute -bottom-2 right-1 bg-white dark:bg-slate-900 border rounded-full px-1.5 py-0.5 text-[10px] shadow-sm flex gap-0.5" data-testid={`reactions-${m.id}`}>
                              {(m.reactions || []).map((r, i) => <span key={i}>{r.emoji}</span>)}
                            </div>
                          )}
                          <div className="text-[9px] text-muted-foreground mt-0.5 text-right flex items-center justify-end gap-1">
                            <span>{timeShort(m.created_at)}</span>
                            {statusTick(m)}
                          </div>
                        </div>
                        {!isOut && !isInternalMsg && (
                          <div className="opacity-0 group-hover:opacity-100 transition">
                            <MessageActions message={m} onReact={react} onDelete={deleteMessage} showDelete={false} />
                          </div>
                        )}
                      </div>
                    </div>);
                })}
              </div>

              {/* Compose */}
              <div className="p-2 border-t space-y-1.5 bg-background">
                <div className="flex items-center gap-2">
                  <button
                    type="button" onClick={() => setIsNote(v => !v)}
                    className={`text-[10px] px-2 py-1 rounded-sm border transition ${isNote ? "bg-yellow-100 border-yellow-400 text-yellow-800" : "border-muted-foreground/30 text-muted-foreground"}`}
                    data-testid="toggle-internal-note"
                  >
                    <StickyNote className="h-3 w-3 inline mr-0.5" /> {isNote ? "Internal note (not sent)" : "Add internal note"}
                  </button>
                  {phoneNumbers.length > 1 && !isNote && (
                    <span className="text-[10px] text-muted-foreground">
                      Sending from: <span className="font-mono">{(phoneNumbers.find(n => n.phone_number_id === senderPhoneId) || {}).display_phone_number || senderPhoneId.slice(-6)}</span>
                    </span>
                  )}
                </div>
                {pendingFile && !isNote && (
                  <div className="flex items-center gap-2 p-1.5 border border-dashed rounded-sm bg-muted/20" data-testid="compose-media-pending">
                    {pendingPreview ? <img src={pendingPreview} alt="" className="h-10 w-10 object-cover rounded" /> :
                      <div className="h-10 w-10 flex items-center justify-center border rounded bg-background">
                        {pendingFile.type.startsWith("video/") ? <Video className="h-4 w-4" /> : pendingFile.type.startsWith("audio/") ? <Music className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
                      </div>}
                    <div className="flex-1 min-w-0 text-[11px]">
                      <div className="font-mono truncate">{pendingFile.name}</div>
                      <div className="text-muted-foreground">{pendingFile.size < 1024 ? `${pendingFile.size} B` : `${Math.round(pendingFile.size / 1024)} KB`}</div>
                    </div>
                    <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={clearPendingFile}><X className="h-3.5 w-3.5" /></Button>
                  </div>
                )}
                <div className="flex items-end gap-1.5">
                  {!isNote && (
                    <>
                      <input ref={fileInputRef} type="file" className="hidden"
                        accept="image/*,video/*,audio/*,application/pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv"
                        onChange={pickFile} data-testid="compose-file-input" />
                      <Button variant="ghost" size="sm" className="h-9 w-9 p-0" onClick={() => fileInputRef.current?.click()} data-testid="compose-attach">
                        <Paperclip className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                  <Textarea
                    value={body} onChange={e => setBody(e.target.value)}
                    onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                    placeholder={isNote ? "Add a private team note — not sent to WhatsApp" : (pendingFile ? "Add a caption (optional)…" : "Type a message… (Enter to send)")}
                    rows={1}
                    className="rounded-sm text-xs min-h-[36px] max-h-32 resize-none flex-1"
                    data-testid="compose-input"
                  />
                  <Button onClick={send} disabled={sending || (!body.trim() && !pendingFile)} size="sm" className={`h-9 w-9 p-0 ${isNote ? "bg-yellow-500 hover:bg-yellow-600" : "bg-green-500 hover:bg-green-600"}`} data-testid="compose-send">
                    {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
            </>
          )}
        </section>
      </Card>
    </div>
  );
}
