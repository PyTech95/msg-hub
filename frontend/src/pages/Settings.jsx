import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";
import { Switch } from "@/components/ui/switch";
import { ChannelBadge } from "@/components/Badges";
import { KeyRound, Percent, ShieldCheck, ShieldAlert } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";

export default function Settings() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();
  const [pwd, setPwd] = useState({ old_password: "", new_password: "", confirm: "" });
  const [saving, setSaving] = useState(false);
  const [markup, setMarkup] = useState(null);
  const [savingMarkup, setSavingMarkup] = useState(false);

  const [twofa, setTwofa] = useState({ enabled: false });
  const [setupData, setSetupData] = useState(null);
  const [otpCode, setOtpCode] = useState("");
  const [disablePw, setDisablePw] = useState("");
  const [disableOpen, setDisableOpen] = useState(false);

  useEffect(() => {
    api.get("/settings/markup").then(r => setMarkup(r.data));
    api.get("/auth/2fa/status").then(r => setTwofa(r.data));
  }, []);

  const changePassword = async (e) => {
    e.preventDefault();
    if (pwd.new_password.length < 6) return toast.error("New password must be at least 6 characters");
    if (pwd.new_password !== pwd.confirm) return toast.error("Passwords do not match");
    setSaving(true);
    try {
      const _resp = await api.post("/auth/change-password", { old_password: pwd.old_password, new_password: pwd.new_password });
      toast.success("Password updated");
      setPwd({ old_password: "", new_password: "", confirm: "" });
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    } finally { setSaving(false); }
  };

  const saveMarkup = async (e) => {
    e.preventDefault();
    setSavingMarkup(true);
    try {
      await api.put("/settings/markup", markup);
      toast.success("Markup updated");
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setSavingMarkup(false); }
  };

  const start2FA = async () => {
    try {
      const { data } = await api.post("/auth/2fa/setup");
      setSetupData(data);
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const enable2FA = async () => {
    try {
      await api.post("/auth/2fa/enable", { code: otpCode });
      toast.success("2FA enabled. Keep your authenticator safe.");
      setSetupData(null); setOtpCode("");
      setTwofa({ enabled: true });
    } catch (err) { toast.error(err.response?.data?.detail || "Invalid code"); }
  };

  const disable2FA = async () => {
    try {
      await api.post("/auth/2fa/disable", { password: disablePw });
      toast.success("2FA disabled");
      setDisableOpen(false); setDisablePw("");
      setTwofa({ enabled: false });
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const isSuperAdmin = user?.role === "super_admin";

  return (
    <div className="space-y-4 max-w-3xl" data-testid="settings-page">
      <div>
        <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Account</div>
        <h1 className="text-3xl font-black tracking-tighter">Settings</h1>
      </div>

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-5 space-y-3">
          <h3 className="text-lg font-bold">Profile</h3>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Name</div>{user?.name}</div>
            <div><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Email</div><span className="font-mono">{user?.email}</span></div>
            <div><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Role</div>{user?.role}</div>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-5 space-y-3">
          <h3 className="text-lg font-bold flex items-center gap-2"><KeyRound className="h-4 w-4" /> Change password</h3>
          <form onSubmit={changePassword} className="space-y-3 max-w-md">
            <div><Label>Current password</Label><Input type="password" required value={pwd.old_password} onChange={e=>setPwd({...pwd,old_password:e.target.value})} className="rounded-sm" data-testid="old-password-input" /></div>
            <div><Label>New password</Label><Input type="password" required value={pwd.new_password} onChange={e=>setPwd({...pwd,new_password:e.target.value})} className="rounded-sm" data-testid="new-password-input" /></div>
            <div><Label>Confirm new password</Label><Input type="password" required value={pwd.confirm} onChange={e=>setPwd({...pwd,confirm:e.target.value})} className="rounded-sm" data-testid="confirm-password-input" /></div>
            <Button type="submit" disabled={saving} className="rounded-sm" data-testid="save-password-button">{saving ? "Saving…" : "Update password"}</Button>
          </form>
        </CardContent>
      </Card>

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-5 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <h3 className="text-lg font-bold flex items-center gap-2">
                {twofa.enabled ? <ShieldCheck className="h-4 w-4 text-emerald-600" /> : <ShieldAlert className="h-4 w-4 text-amber-600" />}
                Two-factor authentication
              </h3>
              <p className="text-xs text-muted-foreground">
                {twofa.enabled ? "Enabled. You'll be asked for a 6-digit code at every login." : "Add a TOTP authenticator (Google Authenticator, Authy, 1Password) for an extra login challenge."}
              </p>
            </div>
            {twofa.enabled ? (
              <Button variant="outline" className="rounded-sm" onClick={() => setDisableOpen(true)} data-testid="disable-2fa-button">Disable</Button>
            ) : !setupData ? (
              <Button className="rounded-sm" onClick={start2FA} data-testid="enable-2fa-button">Enable 2FA</Button>
            ) : null}
          </div>

          {setupData && !twofa.enabled && (
            <div className="space-y-3 border-t border-border pt-3">
              <div className="text-xs text-muted-foreground">1. Scan this QR with your authenticator app — or enter the secret manually.</div>
              <div className="flex flex-wrap items-start gap-4">
                <img src={setupData.qr_data_uri} alt="2FA QR" className="h-40 w-40 border border-border rounded-sm bg-white p-2" data-testid="2fa-qr-image" />
                <div className="space-y-2 min-w-[200px]">
                  <div>
                    <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Secret</Label>
                    <div className="font-mono text-xs p-2 rounded-sm border border-border bg-muted/40 break-all" data-testid="2fa-secret">{setupData.secret}</div>
                  </div>
                </div>
              </div>
              <div className="text-xs text-muted-foreground">2. Enter the 6-digit code from your app:</div>
              <div className="flex gap-2 max-w-xs">
                <Input value={otpCode} onChange={e=>setOtpCode(e.target.value.replace(/\D/g,"").slice(0,6))}
                  className="rounded-sm font-mono text-center text-lg" placeholder="000000" maxLength={6} data-testid="2fa-code-input" />
                <Button onClick={enable2FA} disabled={otpCode.length !== 6} className="rounded-sm" data-testid="verify-2fa-button">Verify</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={disableOpen} onOpenChange={setDisableOpen}>
        <DialogContent className="rounded-sm">
          <DialogHeader>
            <DialogTitle>Disable 2FA</DialogTitle>
            <DialogDescription>Confirm with your current password.</DialogDescription>
          </DialogHeader>
          <Input type="password" value={disablePw} onChange={e=>setDisablePw(e.target.value)} className="rounded-sm" placeholder="Password" data-testid="disable-2fa-password" />
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setDisableOpen(false)}>Cancel</Button>
            <Button variant="destructive" className="rounded-sm" onClick={disable2FA} data-testid="confirm-disable-2fa">Disable</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {isSuperAdmin && markup && (
        <Card className="rounded-sm shadow-none">
          <CardContent className="p-5 space-y-3">
            <div>
              <h3 className="text-lg font-bold flex items-center gap-2"><Percent className="h-4 w-4" /> Channel Markup</h3>
              <p className="text-xs text-muted-foreground">Reseller margin applied on top of provider cost when generating invoices.</p>
            </div>
            <form onSubmit={saveMarkup} className="space-y-3">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {["sms","whatsapp","rcs","voice"].map(ch => (
                  <div key={ch}>
                    <Label className="flex items-center gap-2"><ChannelBadge channel={ch} /></Label>
                    <div className="relative mt-1">
                      <Input type="number" min={0} max={500} step={1}
                        value={markup[ch] ?? 0}
                        onChange={e => setMarkup({...markup, [ch]: Number(e.target.value)})}
                        className="rounded-sm pr-7 font-mono"
                        data-testid={`markup-${ch}-input`} />
                      <span className="absolute right-2 top-2 text-xs text-muted-foreground">%</span>
                    </div>
                  </div>
                ))}
              </div>
              <Button type="submit" disabled={savingMarkup} className="rounded-sm" data-testid="save-markup-button">{savingMarkup ? "Saving…" : "Save markup"}</Button>
            </form>
          </CardContent>
        </Card>
      )}

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-5 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold">Appearance</h3>
            <div className="text-xs text-muted-foreground">Toggle dark / light theme</div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs">Light</span>
            <Switch checked={theme === "dark"} onCheckedChange={v => setTheme(v ? "dark" : "light")} data-testid="settings-theme-switch" />
            <span className="text-xs">Dark</span>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-sm shadow-none">
        <CardContent className="p-5 space-y-2">
          <h3 className="text-lg font-bold">Demo Mode</h3>
          <p className="text-sm text-muted-foreground">
            All provider integrations (Twilio, Gupshup, Exotel, Google RBM, Resend, ElevenLabs) run with <strong>mock adapters</strong>.
            Super Admin can plug in real API keys via <strong>Providers → Credentials</strong> and toggle Mock mode off when ready.
            Scheduled campaigns are auto-dispatched by the background scheduler (every 30s).
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
