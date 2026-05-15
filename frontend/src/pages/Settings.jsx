import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";
import { Switch } from "@/components/ui/switch";

export default function Settings() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();

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
            Replace the adapters in <code className="px-1 rounded-sm bg-muted">backend/server.py → BaseAdapter</code> and add real credentials in the Providers screen to go live.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
