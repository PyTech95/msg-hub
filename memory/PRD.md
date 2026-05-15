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
- JWT auth + role guard + seeded super admin & agent
- All 14 collections w/ indexes
- Full REST API under /api
- Mock provider adapters with simulated async delivery & inbound replies
- Dashboard, Contacts (+ profile timeline), Templates, Campaigns (+ wizard), Conversations, Messages, Calls, Reports, Providers, Webhooks, Team, Settings pages
- Light/dark theme, sidebar layout, channel-colored badges
- Seed data: 15 contacts, 4 templates, 3 campaigns, 50 messages, 10 calls, 4 providers

## Backlog / Next
- **P1**: Real provider integrations (Twilio SMS, Gupshup WA, Exotel Voice, RBM RCS)
- **P1**: Rate-limit + queue (Redis/BullMQ equivalent via APScheduler)
- **P2**: Audit log viewer UI
- **P2**: Invoice PDF export
- **P2**: WebSocket for live inbox updates
- **P2**: 2FA, password reset email flow
