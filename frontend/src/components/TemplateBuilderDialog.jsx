import React, { useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, Trash2, PlusCircle } from "lucide-react";
import { toast } from "sonner";

const CATEGORIES = [
  { v: "UTILITY", label: "Utility — transactional (order status, reminders, receipts)" },
  { v: "MARKETING", label: "Marketing — promotional, offers" },
  { v: "AUTHENTICATION", label: "Authentication — OTP codes" },
];
const HEADER_FORMATS = [
  { v: "", label: "None" },
  { v: "TEXT", label: "Text header" },
  { v: "IMAGE", label: "Image header" },
  { v: "VIDEO", label: "Video header" },
  { v: "DOCUMENT", label: "Document header" },
];

export default function TemplateBuilderDialog({ open, onOpenChange, onCreated }) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("UTILITY");
  const [language, setLanguage] = useState("en_US");
  const [headerFormat, setHeaderFormat] = useState("");
  const [headerText, setHeaderText] = useState("");
  const [headerExample, setHeaderExample] = useState("");
  const [bodyText, setBodyText] = useState("");
  const [bodyExamples, setBodyExamples] = useState([]);
  const [footerText, setFooterText] = useState("");
  const [buttons, setButtons] = useState([]);
  const [saving, setSaving] = useState(false);

  // Variable count in body
  const varCount = useMemo(() => {
    const matches = bodyText.match(/\{\{(\d+)\}\}/g) || [];
    return new Set(matches).size;
  }, [bodyText]);

  // Sync bodyExamples length with varCount
  React.useEffect(() => {
    setBodyExamples(prev => {
      const next = [...prev];
      while (next.length < varCount) next.push("");
      return next.slice(0, varCount);
    });
  }, [varCount]);

  const addButton = (type) => {
    if (buttons.length >= 3) { toast.error("Max 3 buttons"); return; }
    setButtons([...buttons, { type, text: "", url: "", phone_number: "" }]);
  };
  const updateButton = (i, patch) => setButtons(buttons.map((b, j) => j === i ? { ...b, ...patch } : b));
  const removeButton = (i) => setButtons(buttons.filter((_, j) => j !== i));

  const reset = () => {
    setName(""); setCategory("UTILITY"); setLanguage("en_US");
    setHeaderFormat(""); setHeaderText(""); setHeaderExample("");
    setBodyText(""); setBodyExamples([]); setFooterText(""); setButtons([]);
  };

  const submit = async () => {
    const nm = name.trim().toLowerCase().replace(/[^a-z0-9_]/g, "_");
    if (!nm) { toast.error("Template name required (lowercase snake_case)"); return; }
    if (!bodyText.trim()) { toast.error("Body text required"); return; }
    setSaving(true);
    try {
      const payload = {
        name: nm, category, language,
        header_format: headerFormat || null,
        header_text: headerFormat === "TEXT" ? headerText : null,
        header_example: headerFormat ? headerExample : null,
        body_text: bodyText,
        body_examples: bodyExamples.length ? bodyExamples : null,
        footer_text: footerText || null,
        buttons: buttons.length ? buttons.map(b => ({ ...b })) : null,
      };
      const { data } = await api.post("/whatsapp/templates", payload);
      toast.success(`Template "${data.name}" submitted to Meta (status: ${data.status})`);
      reset();
      onOpenChange(false);
      onCreated?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Template creation failed");
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) reset(); onOpenChange(o); }}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="template-builder-dialog">
        <DialogHeader><DialogTitle>Create WhatsApp Template</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Name <span className="text-muted-foreground">(lowercase, snake_case)</span></Label>
              <Input value={name} onChange={e => setName(e.target.value)} placeholder="order_shipped" className="rounded-sm font-mono" data-testid="tb-name-input" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Category</Label>
              <select value={category} onChange={e => setCategory(e.target.value)} className="w-full h-9 rounded-sm border bg-background px-3 text-sm" data-testid="tb-category-select">
                {CATEGORIES.map(c => <option key={c.v} value={c.v}>{c.label}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Language</Label>
              <Input value={language} onChange={e => setLanguage(e.target.value)} placeholder="en_US" className="rounded-sm font-mono" data-testid="tb-language-input" />
            </div>
          </div>

          <div className="border-t pt-3 space-y-2">
            <Label className="text-xs font-semibold">HEADER (optional)</Label>
            <select value={headerFormat} onChange={e => setHeaderFormat(e.target.value)} className="w-full h-9 rounded-sm border bg-background px-3 text-sm" data-testid="tb-header-format-select">
              {HEADER_FORMATS.map(f => <option key={f.v} value={f.v}>{f.label}</option>)}
            </select>
            {headerFormat === "TEXT" && (
              <Input value={headerText} onChange={e => setHeaderText(e.target.value)} placeholder="Order Shipped" className="rounded-sm" data-testid="tb-header-text-input" />
            )}
            {headerFormat && (
              <Input value={headerExample} onChange={e => setHeaderExample(e.target.value)}
                placeholder={headerFormat === "TEXT" ? "Sample value for {{1}} in header (if any)" : "Public sample media URL"} className="rounded-sm" data-testid="tb-header-example-input" />
            )}
          </div>

          <div className="border-t pt-3 space-y-2">
            <Label className="text-xs font-semibold">BODY <span className="text-muted-foreground">— required · use {"{{1}} {{2}}"} for variables</span></Label>
            <Textarea value={bodyText} onChange={e => setBodyText(e.target.value)} rows={4}
              placeholder="Hi {{1}}, your order {{2}} has been shipped and will arrive by {{3}}. Thank you!" className="rounded-sm" data-testid="tb-body-input" />
            {varCount > 0 && (
              <div className="space-y-1">
                <Label className="text-[10px] uppercase text-muted-foreground">Sample values for {varCount} variable{varCount > 1 ? "s" : ""}</Label>
                {bodyExamples.map((v, i) => (
                  <Input key={i} value={v} onChange={e => {
                    const next = [...bodyExamples]; next[i] = e.target.value; setBodyExamples(next);
                  }} placeholder={`Sample for {{${i + 1}}}`} className="rounded-sm text-xs" data-testid={`tb-body-example-${i}`} />
                ))}
              </div>
            )}
          </div>

          <div className="border-t pt-3 space-y-2">
            <Label className="text-xs font-semibold">FOOTER (optional)</Label>
            <Input value={footerText} onChange={e => setFooterText(e.target.value)} placeholder="Powered by tezsandesh" className="rounded-sm" data-testid="tb-footer-input" />
          </div>

          <div className="border-t pt-3 space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-semibold">BUTTONS (optional, max 3)</Label>
              <div className="flex gap-1">
                <Button type="button" variant="outline" size="sm" className="rounded-sm h-7 text-[10px]" onClick={() => addButton("URL")} data-testid="tb-add-url-button">+ URL</Button>
                <Button type="button" variant="outline" size="sm" className="rounded-sm h-7 text-[10px]" onClick={() => addButton("PHONE_NUMBER")} data-testid="tb-add-phone-button">+ Phone</Button>
                <Button type="button" variant="outline" size="sm" className="rounded-sm h-7 text-[10px]" onClick={() => addButton("QUICK_REPLY")} data-testid="tb-add-qr-button">+ Quick Reply</Button>
              </div>
            </div>
            {buttons.map((b, i) => (
              <div key={i} className="flex gap-2 items-center" data-testid={`tb-button-row-${i}`}>
                <span className="text-[10px] uppercase w-20 text-muted-foreground">{b.type}</span>
                <Input value={b.text} onChange={e => updateButton(i, { text: e.target.value })} placeholder="Button label" className="rounded-sm flex-1" />
                {b.type === "URL" && (
                  <Input value={b.url} onChange={e => updateButton(i, { url: e.target.value })} placeholder="https://…" className="rounded-sm flex-1" />
                )}
                {b.type === "PHONE_NUMBER" && (
                  <Input value={b.phone_number} onChange={e => updateButton(i, { phone_number: e.target.value })} placeholder="+91…" className="rounded-sm flex-1" />
                )}
                <Button type="button" variant="ghost" size="icon" className="rounded-sm h-8 w-8" onClick={() => removeButton(i)}>
                  <Trash2 className="h-3.5 w-3.5 text-red-600" />
                </Button>
              </div>
            ))}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => { reset(); onOpenChange(false); }}>Cancel</Button>
          <Button onClick={submit} disabled={saving} className="gap-1" data-testid="tb-submit-button">
            <Plus className="h-3.5 w-3.5" /> {saving ? "Submitting…" : "Submit to Meta"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
