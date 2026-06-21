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
- JWT auth + role guard + 2FA TOTP + brute-force lockout (5/15min) + change-password + token versioning + password reset flow (60s rate-limit)
- All 17 MongoDB collections w/ indexes
- Full REST API under /api (split between server.py + features.py)
- Mock provider adapters: SMS / WhatsApp / RCS / Voice / **Email** with simulated async delivery
- Background campaign scheduler (every 30s, try/except + audit on failure)
- Audit Logs + Provider Credentials Vault + Channel Markup + Monthly Invoices (JSON + CSV + **PDF**) + CSV exports
- **AI Bill Splitter** — upload multi-bill PDF, Claude Sonnet 4.5 extracts each bill (name/phone/email/property_id/address/amount/due_date), bulk-send via SMS/WhatsApp/Email with template variables
- **Notice Templates** — HTML template + variables → WeasyPrint PDF → bulk send via Email/WhatsApp with cover message; downloadable PDFs
- **AI Voice Campaigns** — script-based outbound calls with `{{name}}` `{{amount}}` `{{property_id}}` variables, voice selection, audience picker (bills or contacts), live progress
- **Smart Reminder Automation (Feb 21, 2026)** — auto-escalating multi-channel reminders for unpaid bills: T-7 days → SMS, T-3 days → WhatsApp, T-1 day → AI Voice. Background loop every 60s. Endpoints: `POST /api/bills/enable-reminders` (min 1 bill), `POST /api/bills/{id}/mark-paid` (404 on missing bill, auto-cancels pending schedules), `GET /api/bills/{id}/schedules`, `GET /api/reminders/upcoming`. New `/reminders` page (super_admin + admin) with cadence preview + per-bill schedule view + inline Mark Paid.
- **Invoice PDF Export (Feb 21, 2026)** — `GET /api/export/invoice/{YYYY-MM}.pdf` (WeasyPrint, super_admin/admin only). PDF button added to /invoices alongside CSV + JSON.
- Pages: Dashboard (role-aware), Contacts (+ profile timeline + edit + CSV import/export + bulk delete), Lists CRUD, Templates (+ edit), Campaigns (+ wizard + detail), **Bills (AI)** (+ Auto-Remind & Mark Paid actions + Status column), **Notices**, **Voice AI**, **Reminders**, Conversations, Message Logs (+ export), Calls, Reports, Providers (+ credentials manager), Webhooks, Audit Logs, Invoices (+ PDF), Team, Settings (+ 2FA + Markup + change-password), ForgotPassword + ResetPassword
- Role-aware sidebar + RoleRoute guards; Agent dashboard

## Backlog / Next
- **P1**: Increase EMERGENT_LLM_KEY budget for end-to-end Bill Splitter demo (key budget exhausted in preview env)
- **P1**: Replace mock provider adapters with real Twilio / Gupshup / Exotel / Google RBM / Resend / ElevenLabs when credentials are added
- **P2**: Move notice PDFs to GridFS/object storage (currently base64 in Mongo)
- **P2**: Split server.py into modular routers (auth/audit/exports/scheduler); features.py is approaching 700 lines — split Reminders + Invoice-PDF out
- **P2**: Lifespan-managed shutdown for reminder_loop (avoid duplicate schedulers under hot-reload)
- **P2**: Pagination + date-range filters on `GET /api/reminders/upcoming`
- **P2**: WebSocket inbox push, OCR for scanned PDFs (Tesseract), Jinja2 templating
