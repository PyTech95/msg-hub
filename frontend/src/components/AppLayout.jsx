import React from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Users, FileText, Megaphone, MessageSquare, Phone,
  BarChart3, Plug, Webhook, UserCog, Settings, Inbox, Sun, Moon, LogOut,
  Radio
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

const NAV = [
  { to: "/dashboard",   label: "Dashboard",     icon: LayoutDashboard },
  { to: "/contacts",    label: "Contacts",      icon: Users },
  { to: "/templates",   label: "Templates",     icon: FileText },
  { to: "/campaigns",   label: "Campaigns",     icon: Megaphone },
  { to: "/conversations", label: "Conversations", icon: Inbox },
  { to: "/messages",    label: "Message Logs",  icon: MessageSquare },
  { to: "/calls",       label: "Voice Calls",   icon: Phone },
  { to: "/reports",     label: "Reports",       icon: BarChart3 },
  { to: "/providers",   label: "Providers",     icon: Plug },
  { to: "/webhooks",    label: "Webhooks",      icon: Webhook },
  { to: "/team",        label: "Team",          icon: UserCog },
  { to: "/settings",    label: "Settings",      icon: Settings },
];

export default function AppLayout() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const nav = useNavigate();

  return (
    <div className="min-h-screen flex bg-background text-foreground">
      {/* Sidebar */}
      <aside className="hidden md:flex flex-col w-60 fixed inset-y-0 left-0 border-r border-border bg-card" data-testid="app-sidebar">
        <div className="h-14 flex items-center gap-2 px-4 border-b border-border">
          <div className="h-7 w-7 grid place-items-center rounded-sm bg-primary text-primary-foreground">
            <Radio className="h-4 w-4" strokeWidth={2.2} />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-bold tracking-tight">CPaaS Hub</div>
            <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Comms Console</div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
          {NAV.map((item) => (
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
            <div className="h-7 w-7 grid place-items-center rounded-sm bg-primary text-primary-foreground">
              <Radio className="h-4 w-4" />
            </div>
            <span className="text-sm font-bold">CPaaS Hub</span>
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
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{user?.role}</div>
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
