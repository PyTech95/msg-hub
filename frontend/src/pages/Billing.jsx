import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { CheckCircle2, Sparkles, CreditCard, Receipt, Percent, Building2, Check, X, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const fmtINR = (paise) => `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—");

const FEATURE_LABELS = {
  single_number: "1 WhatsApp number",
  multi_number: "Multiple WA numbers",
  team_rbac: "Team & RBAC",
  ai_features: "AI bot & auto-reply",
  priority_support: "Priority support",
  dedicated_support: "Dedicated CSM",
  email_support: "Email support",
  webhooks: "Webhooks & API",
  campaigns: "Broadcast campaigns",
  analytics: "Advanced analytics",
  sla: "99.9% SLA",
  sso: "SSO / SAML",
  custom_integrations: "Custom integrations",
};

export default function Billing() {
  const { user } = useAuth();
  const [plans, setPlans] = useState([]);
  const [current, setCurrent] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [gstProfile, setGstProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [subscribing, setSubscribing] = useState(false);

  // Subscribe dialog
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [cycle, setCycle] = useState("monthly");
  const [couponCode, setCouponCode] = useState("");
  const [couponPreview, setCouponPreview] = useState(null);
  const [validatingCoupon, setValidatingCoupon] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [p, c, i, g] = await Promise.all([
        api.get("/plans"),
        api.get("/subscriptions/current").catch(() => ({ data: { subscription: null, plan: null } })),
        api.get("/invoices-v2").catch(() => ({ data: [] })),
        api.get("/company/billing").catch(() => ({ data: {} })),
      ]);
      setPlans(p.data);
      setCurrent(c.data);
      setInvoices(i.data);
      setGstProfile(g.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const openSubscribe = (plan) => {
    setSelectedPlan(plan);
    setCycle("monthly");
    setCouponCode("");
    setCouponPreview(null);
  };

  const validateCoupon = async () => {
    if (!couponCode.trim() || !selectedPlan) return;
    setValidatingCoupon(true);
    try {
      const price = cycle === "annual" ? selectedPlan.annual_paise : selectedPlan.monthly_paise;
      const { data } = await api.post("/coupons/validate", {
        code: couponCode.trim().toUpperCase(),
        amount_paise: price,
        context: "subscription",
        plan_code: selectedPlan.code,
      });
      setCouponPreview(data);
      toast.success(`Coupon applied — save ${fmtINR(data.discount_paise)}`);
    } catch (e) {
      setCouponPreview(null);
      toast.error(e.response?.data?.detail || "Invalid coupon");
    } finally { setValidatingCoupon(false); }
  };

  const subscribe = async () => {
    if (!selectedPlan) return;
    setSubscribing(true);
    try {
      await api.post("/subscriptions/subscribe", {
        plan_code: selectedPlan.code,
        billing_cycle: cycle,
        coupon_code: couponCode.trim() ? couponCode.trim().toUpperCase() : undefined,
      });
      toast.success(`Subscribed to ${selectedPlan.name} plan!`);
      setSelectedPlan(null);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Subscription failed"); }
    finally { setSubscribing(false); }
  };

  if (loading) return <div className="p-6 text-sm text-muted-foreground" data-testid="billing-loading">Loading billing…</div>;

  const isSA = !user?.company_id;
  const sub = current?.subscription;
  const currentPlan = current?.plan;

  const priceFor = (plan) => {
    if (plan.custom_pricing) return "Contact us";
    const p = cycle === "annual" ? plan.annual_paise : plan.monthly_paise;
    return p > 0 ? fmtINR(p) : "Free";
  };
  const savingsFor = (plan) => {
    if (!plan.monthly_paise || !plan.annual_paise) return null;
    const yearly = plan.monthly_paise * 12;
    const save = yearly - plan.annual_paise;
    return save > 0 ? save : null;
  };

  return (
    <div className="space-y-6" data-testid="billing-page">
      <div>
        <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Billing</div>
        <h1 className="text-3xl font-black tracking-tighter flex items-center gap-3">
          <CreditCard className="h-7 w-7 text-blue-500" /> Plans & Invoices
        </h1>
        <p className="text-xs text-muted-foreground mt-1">
          {isSA ? "Super Admin billing overview" : "Choose a plan, apply coupons, and download GST invoices"}
        </p>
      </div>

      {/* Current Subscription */}
      {!isSA && (
        <Card className="rounded-sm shadow-none border-blue-200 bg-blue-50/30 dark:bg-blue-900/10" data-testid="current-sub-card">
          <CardContent className="p-4">
            {sub && currentPlan ? (
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                  <div className="text-[10px] uppercase text-muted-foreground">Active subscription</div>
                  <div className="text-xl font-black tracking-tight flex items-center gap-2">
                    {currentPlan.name}
                    <Badge className="rounded-sm text-[10px] bg-emerald-500 hover:bg-emerald-500">{sub.billing_cycle}</Badge>
                    {sub.auto_renew ? <Badge variant="outline" className="rounded-sm text-[10px]">auto-renew</Badge> : <Badge variant="outline" className="rounded-sm text-[10px] text-amber-600 border-amber-300">cancelling</Badge>}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {fmtINR(sub.final_paise)} paid · Expires {fmtDate(sub.expires_at)}
                    {sub.coupon_code && <> · Coupon: <span className="font-mono">{sub.coupon_code}</span> (-{fmtINR(sub.discount_paise)})</>}
                  </div>
                </div>
                {sub.auto_renew && (
                  <Button variant="outline" size="sm" className="rounded-sm text-xs" onClick={async () => {
                    if (!window.confirm("Disable auto-renew? Your subscription will remain active until expiry.")) return;
                    try { await api.post("/subscriptions/cancel"); toast.success("Auto-renew disabled"); load(); }
                    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
                  }} data-testid="cancel-sub-button">Cancel auto-renew</Button>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                  <div className="text-sm font-semibold">No active subscription</div>
                  <div className="text-xs text-muted-foreground">You&apos;re on pay-per-message. Subscribe for included credits + premium features.</div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Cycle toggle */}
      <div className="flex items-center justify-center gap-2">
        <button onClick={() => setCycle("monthly")}
          className={`px-3 py-1.5 rounded-sm text-xs font-medium transition ${cycle === "monthly" ? "bg-foreground text-background" : "border border-muted-foreground/30 text-muted-foreground"}`}
          data-testid="cycle-monthly">Monthly</button>
        <button onClick={() => setCycle("annual")}
          className={`px-3 py-1.5 rounded-sm text-xs font-medium transition ${cycle === "annual" ? "bg-foreground text-background" : "border border-muted-foreground/30 text-muted-foreground"}`}
          data-testid="cycle-annual">Annual <span className="text-emerald-500 ml-1">save ~17%</span></button>
      </div>

      {/* Plans grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3" data-testid="plans-grid">
        {plans.map(plan => {
          const isCurrent = sub && sub.plan_code === plan.code && sub.billing_cycle === cycle;
          const savings = cycle === "annual" && savingsFor(plan);
          return (
            <Card key={plan.code}
              className={`rounded-sm shadow-none relative ${plan.recommended ? "border-blue-500 ring-2 ring-blue-500/20" : ""}`}
              data-testid={`plan-card-${plan.code}`}>
              {plan.recommended && (
                <div className="absolute -top-3 left-4 bg-blue-500 text-white text-[9px] uppercase tracking-wider px-2 py-0.5 rounded-sm">
                  Recommended
                </div>
              )}
              <CardContent className="p-4 space-y-3">
                <div>
                  <div className="text-sm font-black tracking-tight">{plan.name}</div>
                  <div className="text-[11px] text-muted-foreground min-h-[32px]">{plan.description}</div>
                </div>
                <div>
                  <div className="text-2xl font-black tracking-tighter">{priceFor(plan)}</div>
                  <div className="text-[10px] text-muted-foreground">
                    {plan.custom_pricing ? "Custom quote" : `per ${cycle === "annual" ? "year" : "month"}`}
                    {savings ? <span className="ml-1 text-emerald-600">· save {fmtINR(savings)}</span> : null}
                  </div>
                </div>
                {plan.message_credits_monthly > 0 && (
                  <div className="text-[11px] p-1.5 rounded-sm bg-emerald-50 dark:bg-emerald-950/30 text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                    <Sparkles className="h-3 w-3 inline mr-1" />{plan.message_credits_monthly.toLocaleString("en-IN")} messages/mo included
                  </div>
                )}
                <ul className="space-y-1 text-[11px]">
                  {(plan.features || []).map(f => (
                    <li key={f} className="flex items-center gap-1.5">
                      <Check className="h-3 w-3 text-emerald-500 shrink-0" />
                      <span>{FEATURE_LABELS[f] || f}</span>
                    </li>
                  ))}
                </ul>
                {!isSA && (
                  isCurrent ? (
                    <Button disabled className="w-full rounded-sm h-8 text-xs" variant="outline">
                      <CheckCircle2 className="h-3.5 w-3.5 mr-1 text-emerald-500" /> Current plan
                    </Button>
                  ) : plan.custom_pricing ? (
                    <a href="mailto:sales@tezsandesh.digital" className="block">
                      <Button variant="outline" className="w-full rounded-sm h-8 text-xs">Contact sales</Button>
                    </a>
                  ) : (
                    <Button onClick={() => openSubscribe(plan)} className="w-full rounded-sm h-8 text-xs"
                      data-testid={`subscribe-${plan.code}`}>
                      {sub ? "Switch to this plan" : "Subscribe"}
                    </Button>
                  )
                )}
              </CardContent>
            </Card>);
        })}
      </div>

      {/* GST Profile — tenant only */}
      {!isSA && (
        <Card className="rounded-sm shadow-none" data-testid="gst-profile-card">
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-muted-foreground" />
              <div className="text-xs uppercase tracking-wider text-muted-foreground">GST Billing Profile</div>
            </div>
            <div className="text-[11px] text-muted-foreground">
              Enter your GSTIN and billing state so we can issue GST-compliant invoices (CGST+SGST for same-state, IGST for interstate).
            </div>
            <GstProfileForm profile={gstProfile} onSaved={load} />
          </CardContent>
        </Card>
      )}

      {/* Invoices */}
      {!isSA && (
        <Card className="rounded-sm shadow-none" data-testid="invoices-list">
          <CardContent className="p-0">
            <div className="p-3 border-b flex items-center gap-2">
              <Receipt className="h-4 w-4 text-muted-foreground" />
              <div className="text-sm font-semibold">Invoices</div>
              <span className="text-[10px] text-muted-foreground">({invoices.length})</span>
            </div>
            <table className="w-full text-xs">
              <thead className="bg-muted/30">
                <tr>
                  <th className="text-left p-3">#</th>
                  <th className="text-left p-3">Date</th>
                  <th className="text-left p-3">Description</th>
                  <th className="text-right p-3">Subtotal</th>
                  <th className="text-right p-3">GST</th>
                  <th className="text-right p-3">Total</th>
                  <th className="text-left p-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map(inv => (
                  <tr key={inv.id} className="border-t" data-testid={`invoice-row-${inv.invoice_number}`}>
                    <td className="p-3 font-mono">{inv.invoice_number}</td>
                    <td className="p-3">{fmtDate(inv.issued_at)}</td>
                    <td className="p-3">
                      {inv.description}
                      {inv.coupon_code && <span className="ml-1 text-[10px] text-emerald-600">({inv.coupon_code})</span>}
                    </td>
                    <td className="p-3 text-right">{fmtINR(inv.subtotal_paise)}</td>
                    <td className="p-3 text-right text-muted-foreground">
                      {inv.igst_paise > 0
                        ? `IGST ${inv.gst_rate_pct}% · ${fmtINR(inv.igst_paise)}`
                        : `CGST+SGST · ${fmtINR(inv.tax_paise)}`}
                    </td>
                    <td className="p-3 text-right font-semibold">{fmtINR(inv.total_paise)}</td>
                    <td className="p-3">
                      <Badge className={`rounded-sm text-[10px] ${inv.status === "paid" ? "bg-emerald-500 hover:bg-emerald-500" : "bg-amber-500"}`}>
                        {inv.status.toUpperCase()}
                      </Badge>
                    </td>
                  </tr>
                ))}
                {invoices.length === 0 && (
                  <tr><td colSpan={7} className="p-6 text-center text-muted-foreground">No invoices yet. Subscribe to a plan to receive your first invoice.</td></tr>
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* Subscribe dialog */}
      <Dialog open={!!selectedPlan} onOpenChange={(o) => !o && setSelectedPlan(null)}>
        <DialogContent data-testid="subscribe-dialog">
          <DialogHeader><DialogTitle>Subscribe to {selectedPlan?.name}</DialogTitle></DialogHeader>
          {selectedPlan && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <button onClick={() => { setCycle("monthly"); setCouponPreview(null); }}
                  className={`p-2.5 rounded-sm border text-left transition ${cycle === "monthly" ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30" : "border-muted-foreground/20"}`}>
                  <div className="text-[10px] text-muted-foreground">Monthly</div>
                  <div className="text-sm font-black">{fmtINR(selectedPlan.monthly_paise)}</div>
                </button>
                <button onClick={() => { setCycle("annual"); setCouponPreview(null); }}
                  className={`p-2.5 rounded-sm border text-left transition ${cycle === "annual" ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30" : "border-muted-foreground/20"}`}>
                  <div className="text-[10px] text-muted-foreground">Annual <span className="text-emerald-500">-17%</span></div>
                  <div className="text-sm font-black">{fmtINR(selectedPlan.annual_paise)}</div>
                </button>
              </div>
              <div>
                <Label className="text-xs">Coupon code (optional)</Label>
                <div className="flex gap-1.5">
                  <Input value={couponCode} onChange={e => { setCouponCode(e.target.value.toUpperCase()); setCouponPreview(null); }}
                    placeholder="WELCOME20" className="rounded-sm font-mono text-xs" data-testid="coupon-input" />
                  <Button variant="outline" size="sm" onClick={validateCoupon}
                    disabled={!couponCode.trim() || validatingCoupon} className="rounded-sm text-xs" data-testid="apply-coupon">
                    {validatingCoupon ? <Loader2 className="h-3 w-3 animate-spin" /> : "Apply"}
                  </Button>
                </div>
                {couponPreview && (
                  <div className="mt-1 text-[11px] text-emerald-600 flex items-center gap-1" data-testid="coupon-applied">
                    <Percent className="h-3 w-3" /> Discount: -{fmtINR(couponPreview.discount_paise)}
                  </div>
                )}
              </div>
              <div className="p-3 rounded-sm border bg-muted/30 text-xs space-y-1">
                <div className="flex justify-between"><span>Plan price</span><span>{fmtINR(cycle === "annual" ? selectedPlan.annual_paise : selectedPlan.monthly_paise)}</span></div>
                {couponPreview && <div className="flex justify-between text-emerald-600"><span>Coupon ({couponPreview.code})</span><span>-{fmtINR(couponPreview.discount_paise)}</span></div>}
                <div className="flex justify-between text-muted-foreground text-[10px]"><span>Wallet will be debited</span><span>{fmtINR(couponPreview ? couponPreview.final_paise : (cycle === "annual" ? selectedPlan.annual_paise : selectedPlan.monthly_paise))}</span></div>
                <div className="text-[10px] text-muted-foreground pt-1 border-t mt-1">GST invoice (18%) auto-generated after subscription.</div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setSelectedPlan(null)}>Cancel</Button>
            <Button onClick={subscribe} disabled={subscribing} data-testid="confirm-subscribe">
              {subscribing ? "Processing…" : "Confirm & Pay"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>);
}


function GstProfileForm({ profile, onSaved }) {
  const [form, setForm] = useState({
    gstin: profile?.gstin || "",
    billing_address: profile?.billing_address || "",
    billing_state: profile?.billing_state || "",
    billing_email: profile?.billing_email || "",
  });
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    try {
      await api.patch("/company/billing", form);
      toast.success("Billing profile saved");
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div>
          <Label className="text-[10px] uppercase text-muted-foreground">GSTIN</Label>
          <Input value={form.gstin} onChange={e => setForm({ ...form, gstin: e.target.value.toUpperCase() })}
            placeholder="27ABCDE1234F1Z5" className="rounded-sm font-mono text-xs" maxLength={15} data-testid="gstin-input" />
        </div>
        <div>
          <Label className="text-[10px] uppercase text-muted-foreground">State code (2 letters)</Label>
          <Input value={form.billing_state} onChange={e => setForm({ ...form, billing_state: e.target.value.toUpperCase() })}
            placeholder="MH · DL · KA · TN …" className="rounded-sm text-xs" maxLength={2} data-testid="billing-state-input" />
        </div>
      </div>
      <div>
        <Label className="text-[10px] uppercase text-muted-foreground">Billing address</Label>
        <Input value={form.billing_address} onChange={e => setForm({ ...form, billing_address: e.target.value })}
          placeholder="Registered office address for invoicing" className="rounded-sm text-xs" data-testid="billing-address-input" />
      </div>
      <div>
        <Label className="text-[10px] uppercase text-muted-foreground">Billing email (optional)</Label>
        <Input value={form.billing_email} onChange={e => setForm({ ...form, billing_email: e.target.value })}
          placeholder="finance@yourcompany.com" className="rounded-sm text-xs" type="email" data-testid="billing-email-input" />
      </div>
      <div className="flex justify-end">
        <Button size="sm" onClick={save} disabled={saving} className="rounded-sm text-xs" data-testid="save-billing-profile">
          {saving ? "Saving…" : "Save"}
        </Button>
      </div>
    </div>);
}
