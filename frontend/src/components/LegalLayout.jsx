import React from "react";
import { Link } from "react-router-dom";
import { useTheme } from "@/contexts/ThemeContext";
import { Moon, Sun, Mail, FileText, ShieldCheck, UserX } from "lucide-react";

// Public shell for legal pages (Privacy / Terms / Data Deletion). Works fully
// unauthenticated — Meta reviewers can open these URLs without logging in.
export default function LegalLayout({ title, lastUpdated, icon, children }) {
  const { theme, toggleTheme } = useTheme();
  const Icon = icon || FileText;
  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      <header className="border-b border-border bg-card">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3" data-testid="legal-home-link">
            <div className="h-9 w-9 rounded-md bg-primary text-primary-foreground grid place-items-center font-bold text-sm">
              TZ
            </div>
            <div>
              <div className="font-semibold tracking-tight">tezsandesh.digital</div>
              <div className="text-[11px] text-muted-foreground -mt-0.5">COMMS CONSOLE</div>
            </div>
          </Link>
          <button
            type="button"
            onClick={toggleTheme}
            className="h-9 w-9 grid place-items-center rounded-md hover:bg-accent"
            aria-label="Toggle theme"
            data-testid="legal-theme-toggle"
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </div>
      </header>

      <main className="flex-1">
        <article className="max-w-4xl mx-auto px-6 py-10 lg:py-14">
          <div className="flex items-center gap-3 mb-2">
            <Icon className="h-5 w-5 text-primary" />
            <span className="text-xs uppercase tracking-widest text-muted-foreground">Legal</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-2">{title}</h1>
          <p className="text-sm text-muted-foreground mb-8">Last updated: {lastUpdated}</p>
          <div className="prose prose-slate dark:prose-invert max-w-none legal-body">
            {children}
          </div>
        </article>
      </main>

      <footer className="border-t border-border mt-16">
        <div className="max-w-4xl mx-auto px-6 py-8 flex flex-wrap items-center justify-between gap-4">
          <div className="text-xs text-muted-foreground">
            © {new Date().getFullYear()} tezsandesh.digital · A multi-tenant WhatsApp Business SaaS platform
          </div>
          <nav className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
            <Link to="/privacy-policy" className="hover:text-primary flex items-center gap-1" data-testid="footer-privacy-link">
              <ShieldCheck className="h-3 w-3" /> Privacy Policy
            </Link>
            <Link to="/terms" className="hover:text-primary flex items-center gap-1" data-testid="footer-terms-link">
              <FileText className="h-3 w-3" /> Terms &amp; Conditions
            </Link>
            <Link to="/data-deletion" className="hover:text-primary flex items-center gap-1" data-testid="footer-data-deletion-link">
              <UserX className="h-3 w-3" /> Data Deletion
            </Link>
            <a href="mailto:privacy@tezsandesh.digital" className="hover:text-primary flex items-center gap-1">
              <Mail className="h-3 w-3" /> privacy@tezsandesh.digital
            </a>
          </nav>
        </div>
      </footer>

      {/* Inline typography — keeps legal pages readable without pulling in @tailwindcss/typography */}
      <style>{`
        .legal-body { line-height: 1.7; font-size: 15px; }
        .legal-body h2 { font-size: 1.35rem; font-weight: 700; margin-top: 2.25rem; margin-bottom: 0.75rem; letter-spacing: -0.01em; }
        .legal-body h3 { font-size: 1.05rem; font-weight: 600; margin-top: 1.5rem; margin-bottom: 0.5rem; }
        .legal-body p { margin-bottom: 0.85rem; }
        .legal-body ul { list-style: disc; padding-left: 1.4rem; margin-bottom: 1rem; }
        .legal-body ul ul { list-style: circle; margin-top: 0.35rem; margin-bottom: 0.35rem; }
        .legal-body li { margin-bottom: 0.3rem; }
        .legal-body a { color: hsl(var(--primary)); text-decoration: underline; text-underline-offset: 3px; }
        .legal-body strong { font-weight: 600; }
        .legal-body code { background: hsl(var(--muted)); padding: 0.1rem 0.35rem; border-radius: 3px; font-size: 0.85em; }
      `}</style>
    </div>
  );
}
