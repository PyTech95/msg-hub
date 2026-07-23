import React from "react";
import { ShieldCheck } from "lucide-react";
import LegalLayout from "@/components/LegalLayout";

export default function PrivacyPolicy() {
  return (
    <LegalLayout title="Privacy Policy" lastUpdated="23 July 2026" icon={ShieldCheck}>
      <p>
        <strong>tezsandesh.digital</strong> (&quot;we&quot;, &quot;us&quot;, &quot;our&quot;, or the &quot;Platform&quot;) is a
        multi-tenant Software-as-a-Service platform that helps businesses communicate with
        their customers over the official <strong>Meta WhatsApp Business Platform</strong>,
        SMS, email and voice channels. This Privacy Policy explains what information we
        collect, how we use it, how we share it, and the choices you have. Please read it
        carefully. By creating an account or using the Platform you agree to this Policy.
      </p>

      <h2>1. Who we are</h2>
      <p>
        The Platform is operated as a WhatsApp Business Solution Provider (BSP)
        integration. We use the official Meta WhatsApp Cloud API and Meta&apos;s Embedded
        Signup flow so that our customers (&quot;Tenants&quot;) can connect their own WhatsApp
        Business Account (WABA) to send and receive business messages.
      </p>

      <h2>2. Information we collect</h2>

      <h3>2.1 Account information</h3>
      <ul>
        <li>Full name, business name, business email, mobile number</li>
        <li>Password (stored using bcrypt one-way hashing — we cannot read your password)</li>
        <li>Role (Super Admin, Admin, Manager, Agent) and team membership</li>
        <li>Billing address, GSTIN (for Indian tenants), invoicing contact</li>
        <li>Optional 2FA (TOTP) secret</li>
      </ul>

      <h3>2.2 WhatsApp Business data (received via Meta APIs)</h3>
      <p>
        When you connect your WABA through Meta Embedded Signup we obtain and store:
      </p>
      <ul>
        <li>WhatsApp Business Account ID (WABA ID)</li>
        <li>Business Manager ID</li>
        <li>Phone Number ID(s)</li>
        <li>Display phone number, verified business name</li>
        <li>Quality rating, messaging limit tier, code verification status</li>
        <li>A short-lived / long-lived <strong>Access Token</strong> and, if provided, an <strong>App Secret</strong> — both are encrypted at rest with envelope encryption (Fernet AES-128-CBC + HMAC-SHA256, key held in <code>SECRETS_KEK</code>) and never displayed in the UI in plaintext</li>
        <li>A per-tenant Webhook Verify Token for validating inbound webhook events</li>
      </ul>

      <h3>2.3 Contact data</h3>
      <ul>
        <li>Contact name, phone number in E.164 form, email (optional), tags, list membership</li>
        <li>Custom fields you upload (for template variable substitution)</li>
        <li>Consent state (opted-out / do-not-disturb flags)</li>
        <li>Notes and internal annotations</li>
      </ul>

      <h3>2.4 Messages and media</h3>
      <ul>
        <li>The content of messages you send and receive (text, media, interactive buttons, template payloads)</li>
        <li>WhatsApp <em>wamid</em> identifiers, delivery / read / failed timestamps, quality feedback</li>
        <li>Media files uploaded or received — stored in our object store (MongoDB GridFS) with tenant-scoped access control; served with signed access checks only to authenticated users of the owning tenant</li>
        <li>Reactions and message-level metadata (edited, deleted, forwarded)</li>
      </ul>

      <h3>2.5 Payment information</h3>
      <p>
        We use <strong>Razorpay</strong> as our payment processor. Card numbers, UPI IDs
        or bank details are entered directly on Razorpay&apos;s PCI-DSS-compliant checkout
        and are <strong>never</strong> stored on our servers. We receive only:
      </p>
      <ul>
        <li>Razorpay <code>order_id</code>, <code>payment_id</code>, <code>refund_id</code></li>
        <li>Amount, currency, status (created / paid / failed / refunded)</li>
        <li>Timestamps and Razorpay signatures for auditing</li>
      </ul>

      <h3>2.6 Cookies and similar technologies</h3>
      <p>
        We use two strictly-necessary <strong>httpOnly, SameSite=Lax</strong> cookies —
        <code>access_token</code> and <code>refresh_token</code> — to authenticate your
        session. These are set only during login and cleared on logout. We do not use
        any third-party advertising cookies. A single non-sensitive
        <code>cpaas_user</code> profile cache lives in localStorage so the app can render
        immediately on page reload; it contains no credentials.
      </p>

      <h3>2.7 Usage and analytics data</h3>
      <ul>
        <li>Server logs: IP address, User-Agent, request path, response status, timing</li>
        <li>Audit logs: which authenticated user performed which action, when</li>
        <li>Prometheus metrics: aggregate counters, no per-user personal data</li>
      </ul>

      <h2>3. How we use your information</h2>
      <ul>
        <li>To provide, operate, and improve the Platform (send messages via your WABA on your instruction, deliver receipts, render your inbox)</li>
        <li>To authenticate you and protect your account (bcrypt hashing, JWT + refresh tokens, rate limiting, brute-force lockouts, 2FA)</li>
        <li>To process billing and payments (wallet top-ups, subscription plans, GST invoices)</li>
        <li>To send transactional email (payment receipts, low-balance alerts, campaign completion)</li>
        <li>To comply with Meta / WhatsApp Business Policy, applicable law and regulator requests</li>
        <li>To debug, troubleshoot, and prevent abuse or fraud</li>
      </ul>

      <h2>4. Meta / Facebook integration</h2>
      <p>
        The Platform integrates with Meta&apos;s official WhatsApp Cloud API. When you
        click <em>&quot;Connect WhatsApp with Facebook&quot;</em> we launch Meta&apos;s
        Embedded Signup dialog. Your Facebook / Meta credentials are entered directly on
        Meta&apos;s domain and are never seen by us. Meta returns an authorization code
        that we exchange server-side for an access token scoped to your WhatsApp
        Business Account. We use the access token only to:
      </p>
      <ul>
        <li>Send messages that you or your users originate</li>
        <li>Fetch phone number metadata (display name, quality rating, messaging limit)</li>
        <li>Subscribe our webhook to your WABA so you receive inbound messages</li>
        <li>List and submit message templates you create</li>
      </ul>
      <p>
        We <strong>do not</strong> use your Meta access token to access any Facebook page,
        Instagram account, or personal data outside the WABA you explicitly connect.
        Meta&apos;s handling of the underlying data is governed by
        <a href="https://www.facebook.com/policy.php" target="_blank" rel="noopener noreferrer">Meta&apos;s Data Policy</a>
        and the
        <a href="https://www.whatsapp.com/legal/business-policy" target="_blank" rel="noopener noreferrer">WhatsApp Business Messaging Policy</a>.
      </p>

      <h2>5. Third-party services</h2>
      <p>We share data with the following processors only to the extent necessary:</p>
      <ul>
        <li><strong>Meta Platforms Inc.</strong> — WhatsApp Cloud API (message delivery, media hosting, webhook events)</li>
        <li><strong>Razorpay Software Pvt. Ltd.</strong> — payment processing</li>
        <li><strong>Resend / SendGrid</strong> — transactional email delivery</li>
        <li><strong>Cloud infrastructure providers</strong> — MongoDB Atlas / self-hosted MongoDB, Redis, hosting VPS</li>
        <li><strong>Anthropic / OpenAI</strong> — used only when a Tenant explicitly triggers AI-assisted features (Bill Splitter, Smart Reminders). No message content is sent for training</li>
      </ul>

      <h2>6. Data security</h2>
      <ul>
        <li>All traffic served over HTTPS/TLS 1.2+</li>
        <li>Passwords hashed with bcrypt (cost factor 12+)</li>
        <li>WhatsApp access tokens and app secrets encrypted at rest using Fernet envelope encryption; keys are stored outside the database and rotated per <code>SECRETS_KEK</code>/<code>SECRETS_KEK_OLD</code> policy</li>
        <li>httpOnly cookies with <code>Secure</code> flag on HTTPS to mitigate XSS-based token theft</li>
        <li>Strict Content-Security-Policy, X-Frame-Options, HSTS, Referrer-Policy, Permissions-Policy headers on every API response</li>
        <li>Per-tenant isolation enforced at the database query level — every list / detail / update API filters by <code>company_id</code> derived from the caller&apos;s JWT</li>
        <li>Rate limiting on authentication endpoints; 5-strike lockout in 15-minute windows</li>
        <li>Complete audit trail (<code>audit_logs</code>) of every mutation: login, logout, message send, delete, recharge, role change</li>
      </ul>

      <h2>7. Data retention</h2>
      <ul>
        <li><strong>Message history</strong> — retained for the lifetime of your account plus 90 days for dispute resolution, unless you request earlier deletion</li>
        <li><strong>Media files (GridFS)</strong> — same retention as the parent message</li>
        <li><strong>Invoices &amp; billing records</strong> — retained for 8 years to comply with Indian GST record-keeping requirements</li>
        <li><strong>Webhook events</strong> — 30 days for debugging, then purged</li>
        <li><strong>Audit logs</strong> — 2 years</li>
        <li><strong>Deleted account data</strong> — see the <a href="/data-deletion">Data Deletion page</a>: full purge within 30 days of a verified deletion request, except records we are legally required to keep</li>
      </ul>

      <h2>8. Your rights</h2>
      <p>Regardless of jurisdiction, every user of the Platform has the right to:</p>
      <ul>
        <li><strong>Access</strong> — request a machine-readable export of all data associated with your account</li>
        <li><strong>Rectification</strong> — correct any inaccurate personal information</li>
        <li><strong>Erasure</strong> — request deletion of your account and all associated data (see <a href="/data-deletion">/data-deletion</a>)</li>
        <li><strong>Portability</strong> — receive contact and message data in CSV / Excel / JSON</li>
        <li><strong>Restriction / Objection</strong> — object to a particular processing activity</li>
        <li><strong>Withdraw consent</strong> — you may disconnect your WhatsApp Business Account at any time from the WhatsApp Numbers page; the associated access token is destroyed immediately</li>
      </ul>

      <h2>9. GDPR / DPDP considerations</h2>
      <p>
        Where GDPR (EEA/UK) or India&apos;s Digital Personal Data Protection Act 2023
        applies, we act as a <strong>Data Processor</strong> on your behalf when we send
        messages to your customer contacts — you (the Tenant) are the Data Controller.
        For your own account information (billing, login) we act as a Data Controller.
        Cross-border transfers rely on Standard Contractual Clauses (SCCs) and Meta&apos;s
        equivalent safeguards. To exercise any DPDP / GDPR right or to appoint a Grievance
        Officer contact, email <a href="mailto:privacy@tezsandesh.digital">privacy@tezsandesh.digital</a>.
      </p>

      <h2>10. Children</h2>
      <p>
        The Platform is a B2B service and is not directed to children under 18. We do not
        knowingly collect personal information from children. If you believe a child has
        provided us information, please email us and we will delete it.
      </p>

      <h2>11. Changes to this Policy</h2>
      <p>
        We may update this Policy from time to time. The &quot;Last updated&quot; date
        above reflects the most recent revision. Material changes will be notified by
        email or in-app banner at least 14 days before they take effect.
      </p>

      <h2>12. Contact us</h2>
      <p>
        Data Protection Officer / Grievance Officer:<br />
        Email: <a href="mailto:privacy@tezsandesh.digital">privacy@tezsandesh.digital</a><br />
        Support: <a href="mailto:support@tezsandesh.digital">support@tezsandesh.digital</a>
      </p>
    </LegalLayout>
  );
}
