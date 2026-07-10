import React, { useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post("/auth/forgot-password", { email });
      setSent(true);
      toast.success("Reset link generated. Check server logs (demo mode).");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen grid place-items-center bg-background p-6">
      <Card className="w-full max-w-md rounded-sm border-border shadow-none">
        <CardHeader>
          <div className="flex items-center gap-2 mb-1">
            <img
              src="/logo.png"
              alt="tezsandesh.digital"
              className="h-8 w-8 object-contain"
            />
            <span className="text-sm font-bold">
              <span>tez</span><span className="text-orange-500">sandesh</span>
              <span className="text-[9px] text-muted-foreground">.digital</span>
            </span>
          </div>
          <CardTitle className="text-2xl font-black tracking-tighter">Reset your password</CardTitle>
          <CardDescription>Enter your email — we'll generate a reset link.</CardDescription>
        </CardHeader>
        <CardContent>
          {sent ? (
            <div className="space-y-3">
              <div className="p-3 rounded-sm border border-dashed border-border text-xs">
                If <span className="font-mono">{email}</span> exists, a reset link has been logged to the server console.
                In demo mode you can find it by running: <code className="font-mono">tail /var/log/supervisor/backend.err.log</code>.
              </div>
              <Link to="/login" className="text-xs text-primary hover:underline flex items-center gap-1"><ArrowLeft className="h-3 w-3" /> Back to login</Link>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-3" data-testid="forgot-password-form">
              <div>
                <Label>Email</Label>
                <Input type="email" required value={email} onChange={e=>setEmail(e.target.value)} className="rounded-sm" data-testid="forgot-email-input" />
              </div>
              <Button type="submit" disabled={loading} className="w-full rounded-sm" data-testid="forgot-submit-button">{loading ? "Sending…" : "Send reset link"}</Button>
              <Link to="/login" className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"><ArrowLeft className="h-3 w-3" /> Back to login</Link>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
