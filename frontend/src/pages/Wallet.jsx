import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Wallet as WalletIcon, IndianRupee, TrendingUp, TrendingDown, PlusCircle, AlertTriangle, CreditCard } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

function fmt(ts) { return new Date(ts).toLocaleString(); }
const paiseToINR = (p) => (p / 100).toFixed(2);

export default function Wallet() {
  const { user } = useAuth();
  const [wallet, setWallet] = useState(null);
  const [wallets, setWallets] = useState(null);      // SA view of all tenants
  const [rzpCfg, setRzpCfg] = useState(null);
  const [showRecharge, setShowRecharge] = useState(false);
  const [rechargeAmount, setRechargeAmount] = useState("500");
  const [processing, setProcessing] = useState(false);
  const [showAdjust, setShowAdjust] = useState(null); // {company_id, name}
  const [adjAmount, setAdjAmount] = useState("");
  const [adjReason, setAdjReason] = useState("");

  const load = async () => {
    if (user?.company_id) {
      try {
        const [{ data: w }, { data: c }] = await Promise.all([
          api.get("/wallet"), api.get("/wallet/recharge/config"),
        ]);
        setWallet(w); setRzpCfg(c);
      } catch (err) { toast.error(err.response?.data?.detail || "Failed to load wallet"); }
    } else {
      try {
        const { data } = await api.get("/wallets");
        setWallets(data);
      } catch (err) { toast.error(err.response?.data?.detail || "Failed to load wallets"); }
    }
  };
  useEffect(() => { load(); }, [user?.company_id]);

  const openRazorpay = async () => {
    const inr = parseFloat(rechargeAmount);
    if (isNaN(inr) || inr < 100) { toast.error("Minimum recharge is ₹100"); return; }
    setProcessing(true);
    try {
      const { data } = await api.post("/wallet/recharge/order", { amount_paise: Math.round(inr * 100) });
      // Load Razorpay checkout script if not present
      if (!window.Razorpay) {
        await new Promise((res, rej) => {
          const s = document.createElement("script");
          s.src = "https://checkout.razorpay.com/v1/checkout.js";
          s.onload = res; s.onerror = () => rej(new Error("Razorpay script failed to load"));
          document.body.appendChild(s);
        });
      }
      const rzp = new window.Razorpay({
        key: data.key_id, amount: data.amount_paise, currency: data.currency,
        name: "tezsandesh.digital", description: "Wallet recharge",
        order_id: data.order_id,
        handler: async (resp) => {
          try {
            const { data: v } = await api.post("/wallet/recharge/verify", {
              razorpay_order_id: resp.razorpay_order_id,
              razorpay_payment_id: resp.razorpay_payment_id,
              razorpay_signature: resp.razorpay_signature,
            });
            toast.success(`Recharge successful! New balance: ₹${paiseToINR(v.balance_paise)}`);
            setShowRecharge(false); load();
          } catch (err) { toast.error(err.response?.data?.detail || "Verification failed"); }
        },
        prefill: { email: user?.email, name: user?.name },
        theme: { color: "#f97316" },
      });
      rzp.open();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Razorpay order failed");
    } finally { setProcessing(false); }
  };

  const submitAdjust = async () => {
    const paise = Math.round(parseFloat(adjAmount) * 100);
    if (isNaN(paise) || paise === 0) { toast.error("Enter a non-zero amount"); return; }
    if (!adjReason.trim()) { toast.error("Reason required"); return; }
    try {
      const { data } = await api.post("/wallet/adjust", {
        company_id: showAdjust.company_id, amount_paise: paise, reason: adjReason.trim(),
      });
      toast.success(`Balance updated: ₹${paiseToINR(data.balance_paise)}`);
      setShowAdjust(null); setAdjAmount(""); setAdjReason(""); load();
    } catch (err) { toast.error(err.response?.data?.detail || "Adjust failed"); }
  };

  // Super Admin view
  if (!user?.company_id) {
    if (!wallets) return <div className="p-6 text-sm text-muted-foreground" data-testid="wallets-loading">Loading…</div>;
    const total = wallets.reduce((s, w) => s + w.balance_paise, 0);
    return (
      <div className="space-y-4" data-testid="wallets-sa-view">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Billing</div>
          <h1 className="text-3xl font-black tracking-tighter flex items-center gap-3">
            <WalletIcon className="h-7 w-7 text-orange-500" /> Tenant Wallets
          </h1>
          <p className="text-xs text-muted-foreground mt-1">
            Total across {wallets.length} tenant{wallets.length !== 1 ? "s" : ""}: <strong>₹{paiseToINR(total)}</strong>
          </p>
        </div>
        <Card className="rounded-sm shadow-none">
          <CardContent className="p-0">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-muted/40">
                  <th className="text-left p-3">Company</th>
                  <th className="text-left p-3">Admin Email</th>
                  <th className="text-right p-3">Balance</th>
                  <th className="text-left p-3">Updated</th>
                  <th className="text-left p-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {wallets.map(w => (
                  <tr key={w.company_id} className="border-t" data-testid={`wallet-row-${w.company_id}`}>
                    <td className="p-3">{w.company_name}</td>
                    <td className="p-3 font-mono text-muted-foreground">{w.admin_email}</td>
                    <td className={`p-3 text-right font-mono font-semibold ${w.balance_paise < w.low_balance_threshold_paise ? "text-red-600" : ""}`}>
                      ₹{paiseToINR(w.balance_paise)}
                    </td>
                    <td className="p-3 text-muted-foreground">{w.updated_at?.slice(0, 19)?.replace("T", " ")}</td>
                    <td className="p-3">
                      <Button size="sm" variant="outline" className="rounded-sm h-7 text-xs gap-1"
                        onClick={() => { setShowAdjust({ company_id: w.company_id, name: w.company_name }); setAdjAmount(""); setAdjReason(""); }}
                        data-testid={`adjust-wallet-${w.company_id}`}>
                        <PlusCircle className="h-3 w-3" /> Adjust
                      </Button>
                    </td>
                  </tr>
                ))}
                {wallets.length === 0 && (
                  <tr><td colSpan={5} className="p-6 text-center text-muted-foreground text-xs">No tenant wallets yet.</td></tr>
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>

        <Dialog open={!!showAdjust} onOpenChange={(o) => { if (!o) setShowAdjust(null); }}>
          <DialogContent data-testid="adjust-wallet-dialog">
            <DialogHeader><DialogTitle>Adjust Wallet — {showAdjust?.name}</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div>
                <Label className="text-xs">Amount (₹) <span className="text-muted-foreground">— use negative to debit</span></Label>
                <Input type="number" step="0.01" value={adjAmount} onChange={e => setAdjAmount(e.target.value)} placeholder="100" className="rounded-sm" data-testid="adjust-amount-input" />
              </div>
              <div>
                <Label className="text-xs">Reason</Label>
                <Input value={adjReason} onChange={e => setAdjReason(e.target.value)} placeholder="Manual credit / correction / refund" className="rounded-sm" data-testid="adjust-reason-input" />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowAdjust(null)}>Cancel</Button>
              <Button onClick={submitAdjust} data-testid="adjust-submit">Apply</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // Company Admin view
  if (!wallet) return <div className="p-6 text-sm text-muted-foreground" data-testid="wallet-loading">Loading…</div>;
  return (
    <div className="space-y-4" data-testid="wallet-tenant-view">
      <div>
        <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Billing</div>
        <h1 className="text-3xl font-black tracking-tighter flex items-center gap-3">
          <WalletIcon className="h-7 w-7 text-orange-500" /> My Wallet
        </h1>
      </div>

      {wallet.low_balance && (
        <div className="p-3 rounded-sm border border-amber-300 bg-amber-50 dark:bg-amber-900/20 text-xs flex items-center gap-2" data-testid="low-balance-warning">
          <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
          <div>Low balance — sends will be blocked when balance reaches ₹0. Please recharge to continue messaging.</div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card className="rounded-sm shadow-none md:col-span-2">
          <CardContent className="p-5">
            <div className="flex items-end justify-between flex-wrap gap-3">
              <div>
                <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Current balance</div>
                <div className={`text-5xl font-black tracking-tighter flex items-center ${wallet.low_balance ? "text-red-600" : ""}`} data-testid="wallet-balance">
                  <IndianRupee className="h-8 w-8" />{paiseToINR(wallet.balance_paise)}
                </div>
                <div className="text-xs text-muted-foreground mt-1 font-mono">= {wallet.balance_paise} paise</div>
              </div>
              <Button onClick={() => setShowRecharge(true)} className="rounded-sm gap-2" data-testid="recharge-button" disabled={!rzpCfg?.configured}>
                <CreditCard className="h-4 w-4" /> {rzpCfg?.configured ? "Recharge" : "Recharge (unavailable)"}
              </Button>
            </div>
            {!rzpCfg?.configured && (
              <div className="text-[11px] text-muted-foreground mt-3 p-2 border border-dashed rounded-sm">
                Online recharge is not yet available. Contact your platform admin to top up your wallet manually.
              </div>
            )}
          </CardContent>
        </Card>
        <Card className="rounded-sm shadow-none">
          <CardContent className="p-5">
            <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground mb-2">Cost per message</div>
            <div className="space-y-1 text-sm">
              {Object.entries(wallet.pricing_paise).map(([ch, p]) => (
                <div key={ch} className="flex justify-between border-b pb-1 last:border-0">
                  <span className="capitalize">{ch}</span>
                  <span className="font-mono text-muted-foreground">₹{paiseToINR(p)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-0">
          <div className="p-4 border-b flex items-center justify-between">
            <div className="font-semibold text-sm">Recent transactions</div>
            <Badge variant="outline" className="rounded-sm text-[10px]">{wallet.transactions.length}</Badge>
          </div>
          <table className="w-full text-xs" data-testid="wallet-transactions">
            <thead>
              <tr className="bg-muted/40">
                <th className="text-left p-3">When</th>
                <th className="text-left p-3">Type</th>
                <th className="text-right p-3">Amount</th>
                <th className="text-right p-3">Balance after</th>
                <th className="text-left p-3">Reason</th>
              </tr>
            </thead>
            <tbody>
              {wallet.transactions.map(t => (
                <tr key={t.id} className="border-t">
                  <td className="p-3 text-muted-foreground">{fmt(t.created_at)}</td>
                  <td className="p-3">
                    {t.type === "credit"
                      ? <span className="text-emerald-600 flex items-center gap-1"><TrendingUp className="h-3 w-3" /> credit</span>
                      : <span className="text-red-600 flex items-center gap-1"><TrendingDown className="h-3 w-3" /> debit</span>}
                  </td>
                  <td className={`p-3 text-right font-mono font-semibold ${t.type === "credit" ? "text-emerald-600" : "text-red-600"}`}>
                    {t.type === "credit" ? "+" : "-"}₹{paiseToINR(t.amount_paise)}
                  </td>
                  <td className="p-3 text-right font-mono">₹{paiseToINR(t.balance_paise_after || 0)}</td>
                  <td className="p-3 text-muted-foreground text-[11px] max-w-xs truncate">
                    {t.meta?.reason || t.meta?.source || t.meta?.channel || "—"}
                  </td>
                </tr>
              ))}
              {wallet.transactions.length === 0 && (
                <tr><td colSpan={5} className="p-6 text-center text-muted-foreground">No transactions yet.</td></tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Dialog open={showRecharge} onOpenChange={setShowRecharge}>
        <DialogContent data-testid="recharge-dialog">
          <DialogHeader><DialogTitle>Recharge Wallet</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Amount (₹) <span className="text-muted-foreground">— minimum ₹100</span></Label>
              <Input type="number" step="1" min="100" value={rechargeAmount} onChange={e => setRechargeAmount(e.target.value)} className="rounded-sm" data-testid="recharge-amount-input" />
            </div>
            <div className="flex gap-2">
              {[100, 500, 1000, 5000].map(v => (
                <Button key={v} type="button" size="sm" variant="outline" className="rounded-sm text-xs" onClick={() => setRechargeAmount(String(v))}>
                  ₹{v}
                </Button>
              ))}
            </div>
            <div className="text-[11px] text-muted-foreground">Powered by Razorpay · Test/Live via your admin&apos;s key</div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowRecharge(false)}>Cancel</Button>
            <Button onClick={openRazorpay} disabled={processing} data-testid="recharge-pay-button">{processing ? "Opening…" : "Pay with Razorpay"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
