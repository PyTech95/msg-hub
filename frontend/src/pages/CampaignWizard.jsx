import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ChannelBadge } from "@/components/Badges";
import { Check, ArrowRight, ArrowLeft } from "lucide-react";
import { toast } from "sonner";

const STEPS = ["Audience", "Channel", "Template", "Schedule", "Review"];

export default function CampaignWizard({ open, onOpenChange, onCreated }) {
  const [step, setStep] = useState(0);
  const [lists, setLists] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [data, setData] = useState({ name: "", channel: "sms", template_id: "", list_ids: [], schedule_at: "" });

  useEffect(() => {
    if (!open) return;
    setStep(0);
    setData({ name: "", channel: "sms", template_id: "", list_ids: [], schedule_at: "" });
    api.get("/lists").then(r => setLists(r.data));
    api.get("/templates").then(r => setTemplates(r.data));
  }, [open]);

  const availableTemplates = useMemo(() => templates.filter(t => t.channel === data.channel), [templates, data.channel]);
  const selectedTpl = templates.find(t => t.id === data.template_id);

  const canNext = () => {
    if (step === 0) return data.list_ids.length > 0 && data.name.trim();
    if (step === 1) return !!data.channel;
    if (step === 2) return !!data.template_id;
    return true;
  };

  const submit = async () => {
    try {
      await api.post("/campaigns", {
        name: data.name, channel: data.channel, template_id: data.template_id,
        list_ids: data.list_ids, contact_ids: [],
        schedule_at: data.schedule_at || null, variables_map: {},
      });
      toast.success("Campaign created");
      onCreated?.();
      onOpenChange(false);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Create failed");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-sm max-w-2xl" data-testid="campaign-wizard">
        <DialogHeader><DialogTitle>New Campaign</DialogTitle></DialogHeader>

        <div className="flex items-center gap-1 text-xs">
          {STEPS.map((s, i) => (
            <React.Fragment key={s}>
              <div className={`flex items-center gap-1.5 px-2 py-1 rounded-sm ${i === step ? "bg-primary text-primary-foreground" : i < step ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300" : "bg-muted text-muted-foreground"}`}>
                <span className="font-mono w-4 text-center">{i < step ? <Check className="h-3 w-3" /> : i + 1}</span>{s}
              </div>
              {i < STEPS.length - 1 && <div className="flex-1 h-px bg-border" />}
            </React.Fragment>
          ))}
        </div>

        <div className="py-4 min-h-[260px]">
          {step === 0 && (
            <div className="space-y-3">
              <div>
                <Label>Campaign name</Label>
                <Input value={data.name} onChange={e => setData({...data, name: e.target.value})} className="rounded-sm" data-testid="wizard-name-input" placeholder="e.g. Diwali Promo Blast" />
              </div>
              <div>
                <Label>Audience lists</Label>
                <div className="grid grid-cols-2 gap-2 mt-1">
                  {lists.map(l => {
                    const sel = data.list_ids.includes(l.id);
                    return (
                      <button key={l.id} type="button" onClick={() => setData({...data, list_ids: sel ? data.list_ids.filter(x=>x!==l.id) : [...data.list_ids, l.id]})}
                        className={`text-left p-3 rounded-sm border ${sel ? "border-primary bg-primary/5" : "border-border"}`}
                        data-testid={`wizard-list-${l.id}`}>
                        <div className="text-sm font-semibold">{l.name}</div>
                        <div className="text-xs text-muted-foreground">{l.description || "—"}</div>
                      </button>
                    );
                  })}
                  {lists.length === 0 && <div className="text-xs text-muted-foreground col-span-2">No lists yet. Create lists from the Contacts module first.</div>}
                </div>
              </div>
            </div>
          )}
          {step === 1 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {["sms","whatsapp","rcs","voice"].map(c => (
                <button key={c} type="button" onClick={() => setData({...data, channel: c, template_id: ""})}
                  className={`p-4 rounded-sm border text-left ${data.channel === c ? "border-primary bg-primary/5" : "border-border"}`}
                  data-testid={`wizard-channel-${c}`}>
                  <ChannelBadge channel={c} />
                  <div className="text-xs text-muted-foreground mt-2">Send via {c.toUpperCase()}</div>
                </button>
              ))}
            </div>
          )}
          {step === 2 && (
            <div className="space-y-2">
              {availableTemplates.map(t => (
                <button key={t.id} type="button" onClick={() => setData({...data, template_id: t.id})}
                  className={`w-full text-left p-3 rounded-sm border ${data.template_id === t.id ? "border-primary bg-primary/5" : "border-border"}`}
                  data-testid={`wizard-template-${t.id}`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-sm">{t.name}</span>
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{t.category}</span>
                  </div>
                  <div className="text-xs font-mono text-muted-foreground whitespace-pre-wrap">{t.body}</div>
                </button>
              ))}
              {availableTemplates.length === 0 && <div className="text-xs text-muted-foreground">No templates for this channel. Create one in Templates first.</div>}
            </div>
          )}
          {step === 3 && (
            <div className="space-y-3">
              <div>
                <Label>Schedule (leave blank to send now)</Label>
                <Input type="datetime-local" value={data.schedule_at} onChange={e => setData({...data, schedule_at: e.target.value ? new Date(e.target.value).toISOString() : ""})}
                  className="rounded-sm" data-testid="wizard-schedule-input" />
              </div>
              <div className="text-xs text-muted-foreground">If blank, the campaign is dispatched immediately via the mock provider.</div>
            </div>
          )}
          {step === 4 && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <div className="p-3 rounded-sm border border-border"><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Name</div>{data.name}</div>
                <div className="p-3 rounded-sm border border-border"><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Channel</div><ChannelBadge channel={data.channel} /></div>
                <div className="p-3 rounded-sm border border-border"><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Lists</div>{data.list_ids.length}</div>
                <div className="p-3 rounded-sm border border-border"><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Schedule</div>{data.schedule_at || "Now"}</div>
              </div>
              {selectedTpl && (
                <div className="p-3 rounded-sm border border-border">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Template — {selectedTpl.name}</div>
                  <div className="font-mono text-xs whitespace-pre-wrap">{selectedTpl.body}</div>
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter className="gap-2">
          {step > 0 && <Button variant="outline" className="rounded-sm gap-1" onClick={() => setStep(s => s - 1)} data-testid="wizard-prev"><ArrowLeft className="h-4 w-4" /> Back</Button>}
          {step < STEPS.length - 1 && <Button disabled={!canNext()} className="rounded-sm gap-1" onClick={() => setStep(s => s + 1)} data-testid="wizard-next">Next <ArrowRight className="h-4 w-4" /></Button>}
          {step === STEPS.length - 1 && <Button className="rounded-sm gap-1" onClick={submit} data-testid="wizard-submit">Launch <Check className="h-4 w-4" /></Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
