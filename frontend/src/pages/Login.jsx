import React, { useState } from "react";
import { useNavigate, Navigate, Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { toast } from "sonner";
import { ArrowRight } from "lucide-react";

export default function Login() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("admin@cpaas.io");
  const [password, setPassword] = useState("Admin@12345");
  const [otp, setOtp] = useState("");
  const [otpRequired, setOtpRequired] = useState(false);
  const [loading, setLoading] = useState(false);

  if (user) return <Navigate to="/dashboard" replace />;

  const onSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await login(email, password, otp || undefined);
      if (res.otp_required) {
        setOtpRequired(true);
        toast.message("Enter your 6-digit authenticator code");
      } else {
        toast.success("Welcome back");
        nav("/dashboard");
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-2 bg-background">
      {/* Left panel - art */}
      <div className="hidden lg:flex relative overflow-hidden bg-zinc-950 text-white">
        <div className="absolute inset-0 opacity-90"
          style={{
            backgroundImage:
              "radial-gradient(circle at 30% 20%, rgba(59,130,246,0.18), transparent 40%), radial-gradient(circle at 70% 70%, rgba(34,197,94,0.12), transparent 40%)",
          }}
        />
        <div className="absolute inset-0">
          <svg className="w-full h-full" viewBox="0 0 800 800" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
              </pattern>
            </defs>
            <rect width="800" height="800" fill="url(#grid)" />
          </svg>
        </div>
        <div className="relative z-10 p-12 flex flex-col justify-between">
          <div className="flex items-center gap-3">
            <img
              src="/logo.png"
              alt="tezsandesh.digital"
              className="h-12 w-12 object-contain"
            />
            <div>
              <div className="text-xl font-black tracking-tight">
                <span className="text-white">tez</span><span className="text-orange-500">sandesh</span>
                <span className="text-[11px] text-zinc-400">.digital</span>
              </div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-zinc-400">Unified Comms Console</div>
            </div>
          </div>
          <div className="space-y-6 max-w-md">
            <h1 className="text-5xl font-black tracking-tighter leading-[1.05]">
              One console.<br />Every channel.
            </h1>
            <p className="text-base text-zinc-300 leading-relaxed">
              SMS, WhatsApp, RCS and Voice — orchestrated through a single, provider-agnostic dashboard built for enterprise scale.
            </p>
            <div className="grid grid-cols-2 gap-3 pt-4">
              {[
                ["Multi-channel", "SMS · WA · RCS · Voice"],
                ["Provider agnostic", "Twilio · Gupshup · Exotel"],
                ["Campaign engine", "Segments + Templates"],
                ["Real-time events", "Webhook-driven"],
              ].map(([t, s]) => (
                <div key={t} className="p-3 rounded-sm border border-white/10 bg-white/5">
                  <div className="text-[10px] uppercase tracking-wider text-zinc-400">{t}</div>
                  <div className="text-sm font-semibold mt-1">{s}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-zinc-500">© 2026 tezsandesh.digital · Demo Build</div>
        </div>
      </div>

      {/* Right panel - form */}
      <div className="flex items-center justify-center p-6 md:p-12">
        <Card className="w-full max-w-md rounded-sm border-border shadow-none">
          <CardHeader className="space-y-1">
            <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Sign In</div>
            <CardTitle className="text-3xl font-black tracking-tight">Welcome back</CardTitle>
            <CardDescription>Use your admin credentials to access the console.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-4" data-testid="login-form">
              <div className="space-y-1.5">
                <Label htmlFor="email" className="text-xs uppercase tracking-wider">Email</Label>
                <Input id="email" type="email" value={email} onChange={(e)=>setEmail(e.target.value)}
                  required data-testid="login-email-input" className="rounded-sm" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password" className="text-xs uppercase tracking-wider">Password</Label>
                <Input id="password" type="password" value={password} onChange={(e)=>setPassword(e.target.value)}
                  required data-testid="login-password-input" className="rounded-sm" />
              </div>
              {otpRequired && (
                <div className="space-y-1.5">
                  <Label htmlFor="otp" className="text-xs uppercase tracking-wider">Authenticator code</Label>
                  <Input id="otp" type="text" inputMode="numeric" maxLength={6} value={otp}
                    onChange={e => setOtp(e.target.value.replace(/\D/g,"").slice(0,6))}
                    required data-testid="login-otp-input" className="rounded-sm font-mono text-center text-lg tracking-widest"
                    placeholder="000000" autoFocus />
                </div>
              )}
              <Button type="submit" disabled={loading} className="w-full rounded-sm gap-2" data-testid="login-submit-button">
                {loading ? "Signing in…" : "Sign in"}
                <ArrowRight className="h-4 w-4" />
              </Button>
              <div className="flex justify-end">
                <Link to="/forgot-password" className="text-xs text-muted-foreground hover:text-foreground" data-testid="forgot-password-link">Forgot password?</Link>
              </div>
              <div className="text-xs text-muted-foreground border border-dashed border-border rounded-sm p-3">
                <div className="font-semibold mb-1">Demo credentials</div>
                <div className="font-mono">admin@cpaas.io · Admin@12345</div>
                <div className="font-mono">agent@cpaas.io · Agent@12345</div>
              </div>
            </form>
          </CardContent>
        </Card>
        <nav className="mt-6 flex items-center justify-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground flex-wrap">
          <Link to="/privacy-policy" className="hover:text-foreground" data-testid="login-privacy-link">Privacy Policy</Link>
          <span className="opacity-40">·</span>
          <Link to="/terms" className="hover:text-foreground" data-testid="login-terms-link">Terms &amp; Conditions</Link>
          <span className="opacity-40">·</span>
          <Link to="/data-deletion" className="hover:text-foreground" data-testid="login-data-deletion-link">Data Deletion</Link>
        </nav>
      </div>
    </div>
  );
}
