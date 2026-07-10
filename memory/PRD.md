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
- **Rebrand → tezsandesh.digital** (July 2 2026): logo image + orange wordmark across sidebar/login/reset/forgot pages, PDF invoice header, TOTP issuer, backend API title; theme colors shifted from blue to orange (--primary: 24 95% 53%)
- JWT auth + role guard + 2FA TOTP + brute-force lockout (5/15min) + change-password + token versioning + password reset flow (60s rate-limit)
- All 17 MongoDB collections w/ indexes
- Full REST API under /api (split between server.py + features.py + adapters/airtel_iq.py)
- Mock provider adapters: SMS / WhatsApp / RCS / Voice / **Email** with simulated async delivery
- **Airtel IQ adapter** (July 2 2026, `/app/backend/adapters/airtel_iq.py`) — SMS + WhatsApp + Voice with OAuth2 client-credentials + token cache, DLT-compliant SMS payload (customerId + dltHeaderId + dltTemplateId + templateVariables), transparent mock fallback when AIRTEL_IQ_LIVE≠1 or any credential missing. HMAC-SHA256 signature verify helper. 3 webhook endpoints wired: `/api/webhooks/airtel/{sms/dlr, whatsapp/inbound, voice/status}` — inbound WhatsApp auto-creates contact with `wa-inbound` tag. Provider Vault seeded with 3 "Airtel IQ" cards.
- Background campaign scheduler (every 30s, try/except + audit on failure)
- Audit Logs + Provider Credentials Vault + Channel Markup + Monthly Invoices (JSON + CSV + **PDF**) + CSV exports
- **AI Bill Splitter** — upload multi-bill PDF, Claude Sonnet 4.5 extracts each bill (name/phone/email/property_id/address/amount/due_date), bulk-send via SMS/WhatsApp/Email with template variables
- **Notice Templates** — HTML template + variables → WeasyPrint PDF → bulk send via Email/WhatsApp with cover message; downloadable PDFs
- **AI Voice Campaigns** — script-based outbound calls with `{{name}}` `{{amount}}` `{{property_id}}` variables, voice selection, audience picker (bills or contacts), live progress
- **Smart Reminder Automation (Feb 21, 2026)** — auto-escalating multi-channel reminders for unpaid bills: T-7 days → SMS, T-3 days → WhatsApp, T-1 day → AI Voice. Background loop every 60s. Endpoints: `POST /api/bills/enable-reminders` (min 1 bill), `POST /api/bills/{id}/mark-paid` (404 on missing bill, auto-cancels pending schedules), `GET /api/bills/{id}/schedules`, `GET /api/reminders/upcoming`. New `/reminders` page (super_admin + admin) with cadence preview + per-bill schedule view + inline Mark Paid.
- **Invoice PDF Export (Feb 21, 2026)** — `GET /api/export/invoice/{YYYY-MM}.pdf` (WeasyPrint, super_admin/admin only). PDF button added to /invoices alongside CSV + JSON.
- Pages: Dashboard (role-aware), Contacts (+ profile timeline + edit + CSV import/export + bulk delete), Lists CRUD, Templates (+ edit), Campaigns (+ wizard + detail), **Bills (AI)** (+ Auto-Remind & Mark Paid actions + Status column), **Notices**, **Voice AI**, **Reminders**, Conversations, Message Logs (+ export), Calls, Reports, Providers (+ credentials manager + 3 Airtel IQ cards), Webhooks, Audit Logs, Invoices (+ PDF), Team, Settings (+ 2FA + Markup + change-password), ForgotPassword + ResetPassword
- Role-aware sidebar + RoleRoute guards; Agent dashboard
- **VPS Production Readiness (Jun 2026)** — `/app/DEPLOYMENT.md` (Ubuntu+Nginx+SSL+systemd guide for Hostinger VPS), `.env.production.example` for backend+frontend. Changes: api.js relative `/api` fallback when REACT_APP_BACKEND_URL empty; logo self-hosted at `/logo.png` (no emergent asset URLs); `DEMO_MODE=false` → no sample seed data + WhatsApp mock sends become hard errors (`_mock_or_fail`); fixed Gunicorn boot crash (features.py reminder_loop now scheduled via router startup event, not import-time create_task); gunicorn added to requirements.txt (pip freeze); CORS via CORS_ORIGINS env. Verified: gunicorn 2-workers boot + webhook verification on :8002, `yarn build` clean (no hardcoded URLs), preview still green.
- **Meta WhatsApp Cloud API (Jun 2026)** — production integration in `adapters/meta_whatsapp.py` (Graph v22.0). Endpoints: `GET/POST /api/webhook/whatsapp` (hub.challenge verification + inbound msgs/statuses with idempotency + STOP opt-out + read→delivered mapping), `POST /api/whatsapp/send-message` (auto-creates contact, live via Meta / mock fallback), `GET /api/whatsapp/setup` (callback URL + verify token info). Credentials: Vault (provider_key `meta_whatsapp`, mock OFF) → env (`WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN=tezsandesh_verify_7f3a9c1e`, optional `WHATSAPP_APP_SECRET` for X-Hub-Signature-256, `GRAPH_API_VERSION`). Providers page has Meta setup card (copy callback URL/verify token + quick test send). Live sends skip mock lifecycle simulation (real statuses via webhook); provider Test button does real Graph handshake when creds present. Self-tested via curl (verification 200/403, inbound save, status mapping, idempotency) + UI screenshot.

## Backlog / Next
- **P0 (user)**: DLT Entity + Header `TZSDSH` + starter Templates via SmartPing.live (`https://smartping.live/entity/login`)
- **P0 (user)**: Airtel IQ enterprise onboarding (contact sales at `airtel.in/business/airtel-iq/` → get Customer ID / Client ID / Client Secret / SMS+WhatsApp+Voice base URLs / OAuth token URL / DLT Header + Template IDs / Webhook secret). When keys arrive, set the AIRTEL_IQ_* env vars + `AIRTEL_IQ_LIVE=1` → adapter flips to live with zero code changes.
- **P1**: Increase EMERGENT_LLM_KEY budget for end-to-end Bill Splitter demo (key budget exhausted in preview env)
- **P1**: Provider Credentials UI enhancement — add Airtel IQ specific fields (Customer ID, OAuth URL, Base URLs, DLT Header/Template ID) with test-connection button
- **P0 (user)**: Configure Callback URL + Verify Token in Meta dashboard, paste Access Token + Phone Number ID in Vault (mock OFF) → live WhatsApp. Later: permanent System User token + business verification.
- **P2**: Move notice PDFs to GridFS/object storage (currently base64 in Mongo)
- **P2**: Split server.py (~1638 lines) into modular routers (auth/audit/exports/scheduler/messages/webhooks); features.py is approaching 700 lines — split Reminders + Invoice-PDF out
- **P2**: Lifespan-managed shutdown for reminder_loop (avoid duplicate schedulers under hot-reload)
- **P2**: Pagination + date-range filters on `GET /api/reminders/upcoming`
- **P2**: Fix Recharts `width/height=-1` warning on Dashboard (min-height on ResponsiveContainer parents)
- **P2**: WebSocket inbox push, OCR for scanned PDFs (Tesseract), Jinja2 templating
