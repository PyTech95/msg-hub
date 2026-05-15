# CPaaS Hub — Product Requirements Document

## Original Problem Statement
Build a production-ready full-stack CPaaS-style web application that lets a business send SMS, WhatsApp, RCS messages and place voice calls from one unified dashboard. Multi-user with roles (Super Admin, Admin, Agent). Contacts, lists, templates, campaigns, conversation timeline, voice calls, analytics, providers, webhooks, billing/usage. Provider abstraction with mock implementations so app runs end-to-end without live keys.

## Architecture
- **Frontend:** React 19 + react-router 7 + Tailwind + shadcn/ui + Recharts (Vite-style CRA via craco)
- **Backend:** FastAPI + Motor (MongoDB async) + PyJWT + bcrypt
- **Database:** MongoDB (collections listed below)
- **Auth:** JWT email/password (Bearer header + httpOnly cookie)
- **Providers:** Async mock adapters (SMS/WhatsApp/RCS/Voice) with provider-interface; swap to live (Twilio/Gupshup/Exotel/RBM) later.

## User Personas
- **Super Admin** — full control, billing, providers, team.
- **Admin** — campaigns, templates, contacts.
- **Agent** — conversations, click-to-call, send messages.

## Core Requirements (static)
1. Contact CRUD + CSV import + lists/tags + DND flag
2. Templates per channel
3. Campaign builder + scheduler + recipient stats
4. Multi-channel send (SMS / WhatsApp / RCS / Voice)
5. Conversation timeline per contact (omnichannel)
6. Provider settings + webhook event monitor
7. Dashboard KPIs + analytics charts
8. Role-based access
9. Usage/billing records

## MongoDB Collections
users, contacts, contact_lists, templates, campaigns, campaign_recipients, messages, message_events, conversations, call_logs, provider_accounts, webhook_events, usage_records, audit_logs

## Implemented (Feb 2026)
- JWT auth + role guard + seeded super admin & agent + change-password + **token versioning (JWT revoked on pw change)** + **password reset flow** (console-logged token)
- All 14 collections w/ indexes + new `audit_logs`, `password_reset_tokens`, `system_settings`
- Full REST API under /api
- Mock provider adapters with simulated async delivery & inbound replies
- **Background campaign scheduler** (every 30s, dispatches scheduled campaigns automatically)
- **Audit Logs** — login/login_failed, user CRUD, campaign created/auto-started, provider credentials updated, markup updated, password changed/reset
- **Provider Credentials Vault** — masked storage (super_admin only), per-provider schemas (Twilio/Gupshup/Exotel/RBM), reveal toggle, rotate-on-edit, test connection
- **Channel Markup config** (super_admin only) + **Monthly Invoices** with base / markup / billable totals + per-month detail + JSON download
- **CSV exports**: contacts, messages (channel + status filters)
- Pages: Dashboard (role-aware), Contacts (+ profile timeline + edit + CSV import/export + bulk delete), Lists CRUD, Templates (+ edit), Campaigns (+ wizard + detail page), Conversations, Message Logs (+ export), Calls, Reports, Providers (+ credentials manager), Webhooks, Audit Logs, Invoices, Team, Settings (+ change-password + markup), ForgotPassword + ResetPassword
- Role-aware sidebar + RoleRoute guards; Agent gets a dedicated inbox-first dashboard
- Light/dark theme, channel-colored badges, NSTU branding
- Seed data: 15 contacts, 3 lists, 4 templates, 4 providers, 3 campaigns, ~80 historical messages, 10 calls, 8 webhook events, default markup (20/25/30/15 %)

## Backlog / Next
- **P1**: Replace mock adapters with real provider implementations once Super Admin saves API keys (Twilio SMS/Voice, Gupshup WhatsApp, Google RBM RCS, Exotel Voice)
- **P1**: Wrap scheduler's run_campaign with try/except + audit failures
- **P1**: Forgot-password rate limit; password-reset token API access in DEMO_MODE
- **P2**: WebSocket push for live inbox/campaign progress, 2FA TOTP, streaming CSV for >10k rows, invoice PDF
- **P2**: Split server.py into modular routers (auth, audit, invoices, campaigns, providers)
