import React, { useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";
import { Switch } from "@/components/ui/switch";
import { KeyRound } from "lucide-react";
import { toast } from "sonner";

export default function Settings() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();
  const [pwd, setPwd] = useState({ old_password: "", new_password: "", confirm: "" });
  const [saving, setSaving] = useState(false);

  const changePassword = async (e) => {
    e.preventDefault();
    if (pwd.new_password.length < 6) return toast.error("New password must be at least 6 characters");
    if (pwd.new_password !== pwd.confirm) return toast.error("Passwords do not match");
    setSaving(true);
    try {
      await api.post("/auth/change-password", { old_password: pwd.old_password, new_password: pwd.new_password });
      toast.success("Password updated");
      setPwd({ old_password: "", new_password: "", confirm: "" });
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    } finally { setSaving(false); }
  };

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
            All provider integrations (Twilio, Gupshup, Exotel, Google RBM) run with <strong>mock adapters</strong> in this environment.
            Super Admin can plug in real API keys via <strong>Providers → Credentials</strong> and toggle Mock mode off when ready.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
