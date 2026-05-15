import { Badge } from "@/components/ui/badge";
import { MessageSquare, MessageCircle, Smartphone, Phone } from "lucide-react";

const META = {
  sms:      { label: "SMS",      cls: "bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800",        icon: MessageSquare },
  whatsapp: { label: "WhatsApp", cls: "bg-green-100 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800", icon: MessageCircle },
  rcs:      { label: "RCS",      cls: "bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-900/30 dark:text-orange-400 dark:border-orange-800", icon: Smartphone },
  voice:    { label: "Voice",    cls: "bg-stone-100 text-stone-700 border-stone-200 dark:bg-stone-800 dark:text-stone-300 dark:border-stone-700",     icon: Phone },
};

export function ChannelBadge({ channel, showIcon = true }) {
  const m = META[channel] || META.sms;
  const Icon = m.icon;
  return (
    <Badge variant="outline" className={`gap-1 rounded-sm font-medium ${m.cls}`} data-testid={`channel-badge-${channel}`}>
      {showIcon && <Icon className="h-3 w-3" strokeWidth={2} />}
      {m.label}
    </Badge>
  );
}

const STATUS_CLS = {
  queued:    "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  sent:      "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300",
  delivered: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  read:      "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  failed:    "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
  received:  "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300",
  scheduled: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  running:   "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  answered:  "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  ringing:   "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  busy:      "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
  "no-answer":"bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  initiated: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
};

export function StatusBadge({ status }) {
  const cls = STATUS_CLS[status] || "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
  return (
    <Badge variant="outline" className={`rounded-sm font-medium border-transparent ${cls}`} data-testid={`status-badge-${status}`}>
      {status}
    </Badge>
  );
}
