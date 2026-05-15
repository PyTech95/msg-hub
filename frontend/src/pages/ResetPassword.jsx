import React, { useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Radio, ArrowLeft } from "lucide-react";
import { toast } from "sonner";

export default function ResetPassword() {
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const token = sp.get("token") || "";
  const [pw, setPw] = useState({ new_password: "", confirm: "" });
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (pw.new_password.length < 6) return toast.error("Password must be at least 6 characters");
    if (pw.new_password !== pw.confirm) return toast.error("Passwords do not match");
    setLoading(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: pw.new_password });
      toast.success("Password reset. Please log in.");
      nav("/login");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen grid place-items-center bg-background p-6">
      <Card className="w-full max-w-md rounded-sm border-border shadow-none">
        <CardHeader>
          <div className="flex items-center gap-2 mb-1">
            <div className="h-7 w-7 grid place-items-center rounded-sm bg-primary text-primary-foreground">
              <Radio className="h-4 w-4" />
            </div>
            <span className="text-sm font-bold">NSTU</span>
          </div>
          <CardTitle className="text-2xl font-black tracking-tighter">Set a new password</CardTitle>
          <CardDescription>Pick a strong password (min 6 chars).</CardDescription>
        </CardHeader>
        <CardContent>
          {!token ? (
            <div className="text-sm text-red-600">Missing or invalid reset token. Request a new link.</div>
          ) : (
            <form onSubmit={submit} className="space-y-3" data-testid="reset-password-form">
              <div><Label>New password</Label><Input type="password" required value={pw.new_password} onChange={e=>setPw({...pw,new_password:e.target.value})} className="rounded-sm" data-testid="reset-new-password" /></div>
              <div><Label>Confirm password</Label><Input type="password" required value={pw.confirm} onChange={e=>setPw({...pw,confirm:e.target.value})} className="rounded-sm" data-testid="reset-confirm-password" /></div>
              <Button type="submit" disabled={loading} className="w-full rounded-sm" data-testid="reset-submit-button">{loading ? "Saving…" : "Update password"}</Button>
              <Link to="/login" className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"><ArrowLeft className="h-3 w-3" /> Back to login</Link>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
