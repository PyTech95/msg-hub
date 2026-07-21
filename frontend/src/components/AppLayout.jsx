import React from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useRealtime } from "@/hooks/useRealtime";
import {
  LayoutDashboard, Users, FileText, Megaphone, MessageSquare, Phone,
  BarChart3, Plug, Webhook, UserCog, Settings, Inbox, Sun, Moon, LogOut,
  ListChecks, ReceiptText, ScrollText, Sparkles, BotMessageSquare, AlarmClock, Building2, MessageCircle, Smartphone,
  Wallet as WalletIcon
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Toaster } from "@/components/ui/sonner";

// roles allowed to see each nav item. super_admin always sees all.
const NAV = [
  { to: "/dashboard",     label: "Dashboard",     icon: LayoutDashboard, roles: ["super_admin","admin","agent"] },
  { to: "/contacts",      label: "Contacts",      icon: Users,           roles: ["super_admin","admin","agent"] },
  { to: "/lists",         label: "Lists",         icon: ListChecks,      roles: ["super_admin","admin"] },
  { to: "/templates",     label: "Templates",     icon: FileText,        roles: ["super_admin","admin","agent"] },
  { to: "/bills",         label: "Bills (AI)",    icon: Sparkles,        roles: ["super_admin","admin","agent"] },
  { to: "/notices",       label: "Notices",       icon: ScrollText,      roles: ["super_admin","admin"] },
  { to: "/campaigns",     label: "Campaigns",     icon: Megaphone,       roles: ["super_admin","admin"] },
  { to: "/voice-campaigns", label: "Voice AI",    icon: BotMessageSquare, roles: ["super_admin","admin","agent"] },
  { to: "/reminders",     label: "Reminders",     icon: AlarmClock,      roles: ["super_admin","admin"] },
  { to: "/conversations", label: "Conversations", icon: Inbox,           roles: ["super_admin","admin","agent"] },
  { to: "/messages",      label: "Message Logs",  icon: MessageSquare,   roles: ["super_admin","admin","agent"] },
  { to: "/calls",         label: "Voice Calls",   icon: Phone,           roles: ["super_admin","admin","agent"] },
  { to: "/reports",       label: "Reports",       icon: BarChart3,       roles: ["super_admin","admin"] },
  { to: "/invoices",      label: "Invoices",      icon: ReceiptText,     roles: ["super_admin","admin"] },
  { to: "/companies",     label: "Companies",     icon: Building2,       roles: ["super_admin"], platformOnly: true },
  { to: "/providers",     label: "Providers",     icon: Plug,            roles: ["super_admin","admin"], platformOnly: true },
  { to: "/webhooks",      label: "Webhooks",      icon: Webhook,         roles: ["super_admin","admin"], platformOnly: true },
  { to: "/whatsapp-settings", label: "WhatsApp Setup", icon: MessageCircle, roles: ["super_admin","admin"], tenantOnly: true },
  { to: "/whatsapp-numbers", label: "WA Numbers", icon: Smartphone, roles: ["super_admin","admin","manager","agent"] },
  { to: "/wallet",        label: "Wallet",        icon: WalletIcon,      roles: ["super_admin","admin"] },
  { to: "/audit-logs",    label: "Audit Logs",    icon: ScrollText,      roles: ["super_admin","admin"] },
  { to: "/team",          label: "Team",          icon: UserCog,         roles: ["super_admin","admin"] },
  { to: "/settings",      label: "Settings",      icon: Settings,        roles: ["super_admin","admin","manager","agent"] },
];

// Extend nav roles so Manager & Agent see relevant nav items (backend already gates permissions)
NAV.forEach(item => {
  if (["/inbox","/contacts","/campaigns","/messages","/analytics","/dashboard","/wallet","/templates"].includes(item.to)
      && !item.roles.includes("manager")) item.roles.push("manager");
  if (["/inbox","/contacts"].includes(item.to) && !item.roles.includes("agent")) item.roles.push("agent");
});

export const ROLE_NAV = NAV;

export default function AppLayout() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const nav = useNavigate();

  // Global realtime feed — surfaces inbound messages + low-balance alerts as toasts
  useRealtime((evt) => {
    if (!evt) return;
    if (evt.type === "inbound_message") {
      toast.info("New WhatsApp message", {
        description: (evt.body || "").slice(0, 120),
        action: { label: "Open", onClick: () => nav(`/contacts/${evt.contact_id}`) },
      });
    } else if (evt.type === "wallet_debit" && evt.low_balance) {
      toast.warning("Low wallet balance", {
        description: `Balance dropped to ₹${(evt.balance_paise/100).toFixed(2)} — recharge soon.`,
        action: { label: "Recharge", onClick: () => nav("/wallet") },
      });
    }
  });

  return (
    <div className="min-h-screen flex bg-background text-foreground">
      {/* Sidebar */}
      <aside className="hidden md:flex flex-col w-60 fixed inset-y-0 left-0 border-r border-border bg-card" data-testid="app-sidebar">
        <div className="h-14 flex items-center gap-2 px-4 border-b border-border">
          <img
            src="/logo.png"
            alt="tezsandesh.digital"
            className="h-9 w-9 object-contain shrink-0"
          />
          <div className="leading-tight">
            <div className="text-sm font-bold tracking-tight">
              <span className="text-foreground">tez</span><span className="text-orange-500">sandesh</span>
              <span className="text-[9px] text-muted-foreground">.digital</span>
            </div>
            <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Comms Console</div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
          {NAV.filter(item => item.roles.includes(user?.role) && (!item.platformOnly || !user?.company_id) && (!item.tenantOnly || !!user?.company_id)).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
            >
              <item.icon className="h-4 w-4" strokeWidth={2} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-border text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          v1.0 · Demo Mode
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 md:ml-60 flex flex-col min-h-screen">
        <header className="h-14 sticky top-0 z-20 flex items-center justify-between gap-3 px-4 md:px-6 border-b border-border bg-background/80 backdrop-blur">
          <div className="md:hidden flex items-center gap-2">
            <img
              src="/logo.png"
              alt="tezsandesh.digital"
              className="h-8 w-8 object-contain"
            />
            <span className="text-sm font-bold">
              <span>tez</span><span className="text-orange-500">sandesh</span>
            </span>
          </div>
          <div className="flex-1" />
          <Button variant="ghost" size="icon" onClick={toggle} data-testid="theme-toggle" aria-label="Toggle theme">
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="gap-2 h-9 px-2" data-testid="user-menu-trigger">
                <Avatar className="h-7 w-7"><AvatarFallback className="text-xs font-semibold">{(user?.name||"U").slice(0,2).toUpperCase()}</AvatarFallback></Avatar>
                <div className="text-left hidden sm:block">
                  <div className="text-xs font-semibold leading-tight">{user?.name}</div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{user?.company_name ? `${user.company_name}` : user?.role}</div>
                </div>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel>{user?.email}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => nav("/settings")} data-testid="menu-settings">Settings</DropdownMenuItem>
              <DropdownMenuItem onClick={async () => { await logout(); nav("/login"); }} data-testid="menu-logout">
                <LogOut className="h-4 w-4 mr-2" /> Logout
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>

        <div className="flex-1 p-4 md:p-6 lg:p-8">
          <Outlet />
        </div>
      </main>
      <Toaster richColors position="top-right" />
    </div>
  );
}
