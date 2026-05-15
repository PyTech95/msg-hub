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
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

export default function Settings() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();
  const [pwd, setPwd] = useState({ old_password: "", new_password: "", confirm: "" });
  const [saving, setSaving] = useState(false);
  const [markup, setMarkup] = useState(null);
  const [savingMarkup, setSavingMarkup] = useState(false);

  // 2FA state
  const [twofa, setTwofa] = useState({ enabled: false });
  const [setupData, setSetupData] = useState(null);
  const [otpCode, setOtpCode] = useState("");
  const [disablePw, setDisablePw] = useState("");
  const [disableOpen, setDisableOpen] = useState(false);

  useEffect(() => {
    api.get("/settings/markup").then(r => setMarkup(r.data));
    api.get("/auth/2fa/status").then(r => setTwofa(r.data));
  }, []);

  const start2FA = async () => {
    try {
      const { data } = await api.post("/auth/2fa/setup");
      setSetupData(data);
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const enable2FA = async () => {
    try {
      await api.post("/auth/2fa/enable", { code: otpCode });
      toast.success("2FA enabled. Save your authenticator setup.");
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

  const changePassword = async (e) => {
    e.preventDefault();
    if (pwd.new_password.length < 6) return toast.error("New password must be at least 6 characters");
    if (pwd.new_password !== pwd.confirm) return toast.error("Passwords do not match");
    setSaving(true);
    try {
      const { data } = await api.post("/auth/change-password", { old_password: pwd.old_password, new_password: pwd.new_password });
      if (data.token) localStorage.setItem("cpaas_token", data.token);
      toast.success("Password updated — existing sessions on other devices have been signed out");
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
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    } finally { setSavingMarkup(false); }
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
            All provider integrations (Twilio, Gupshup, Exotel, Google RBM) run with <strong>mock adapters</strong>.
            Super Admin can plug in real API keys via <strong>Providers → Credentials</strong> and toggle Mock mode off when ready.
            Scheduled campaigns are auto-dispatched by the background scheduler (every 30s).
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

// NOTE (testing agent): The block below was orphaned dead JSX left over from a
// botched paste. It has been commented out to unblock compilation. The 2FA card
// UI (state already declared at top of file: twofa, setupData, otpCode, disablePw,
// disableOpen + start2FA / enable2FA / disable2FA handlers) is NOT rendered
// anywhere in the active return() above. Main agent must add the 2FA Card JSX
// (data-testid: enable-2fa-button, 2fa-qr-image, 2fa-code-input,
// disable-2fa-password) inside the active return().
/*
v className="relative mt-1">
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
            All provider integrations (Twilio, Gupshup, Exotel, Google RBM) run with <strong>mock adapters</strong>.
            Super Admin can plug in real API keys via <strong>Providers → Credentials</strong> and toggle Mock mode off when ready.
            Scheduled campaigns are auto-dispatched by the background scheduler (every 30s).
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
*/

