import React from "react";
import { UserX } from "lucide-react";
import LegalLayout from "@/components/LegalLayout";

export default function DataDeletion() {
  return (
    <LegalLayout title="User Data Deletion" lastUpdated="23 July 2026" icon={UserX}>
      <p>
        <strong>tezsandesh.digital</strong> respects your right to be forgotten. This
        page explains exactly how you (or an end-customer of one of our Tenants) can
        request deletion of personal data we hold, what will be deleted, how long the
        process takes, and how we handle data received from Meta / WhatsApp.
      </p>

      <h2>1. Who can request deletion</h2>
      <ul>
        <li><strong>Account owner (Tenant Admin)</strong> — can request full account deletion including all associated contacts, messages, media and billing records</li>
        <li><strong>Team members</strong> — can request removal of their individual user profile from a Tenant. Contact your Tenant Admin or write to us if the admin is unresponsive</li>
        <li><strong>End-customers</strong> whose data is stored inside a Tenant&apos;s contact list — please first contact that business directly, since the Tenant is the Data Controller for their own customer records. If they are unresponsive within 30 days, forward the request to us and we will facilitate</li>
        <li><strong>Meta / Facebook users</strong> whose data flowed through the WhatsApp Cloud API integration — see Section 5 below</li>
      </ul>

      <h2>2. How to submit a deletion request</h2>
      <p>Choose whichever method is most convenient:</p>
      <ul>
        <li><strong>In-app</strong> — log in → Settings → &quot;Delete my account&quot; (Tenant Admins only). We will verify your identity via email before proceeding.</li>
        <li><strong>Email</strong> — send a request to
          <a href="mailto:privacy@tezsandesh.digital?subject=User%20Data%20Deletion%20Request">privacy@tezsandesh.digital</a>
          with the subject line <em>&quot;User Data Deletion Request&quot;</em> from the email address associated with the account.
        </li>
        <li><strong>Postal mail</strong> — write to our Grievance Officer at the address listed at the bottom of this page.</li>
      </ul>
      <p>
        Include: (a) your registered email or company name, (b) whether you want full
        account deletion or removal of specific data, and (c) any reference numbers.
      </p>

      <h2>3. What will be deleted</h2>
      <p>Upon verified deletion request we will erase the following:</p>
      <ul>
        <li>Your user account: name, email, hashed password, 2FA secret, session tokens</li>
        <li>All contacts, lists, tags, custom fields you uploaded</li>
        <li>All messages sent and received (text, media, reactions, notes, campaign records)</li>
        <li>All media files in GridFS (images, videos, documents, audio, voice notes)</li>
        <li>All WhatsApp Business Account credentials (WABA ID, phone number IDs, encrypted access tokens and app secrets)</li>
        <li>Wallet transaction history (aggregated to statutory ledger only — see retention below)</li>
        <li>Webhook events, delivery receipts, quality feedback linked to your tenancy</li>
        <li>Templates you created, campaign definitions, scheduled sends, drafts</li>
        <li>Audit logs older than the statutory minimum (Section 4)</li>
      </ul>

      <h2>4. What we must retain (and for how long)</h2>
      <p>
        Certain records are retained for a limited period after account deletion to
        comply with legal, tax, or fraud-prevention obligations:
      </p>
      <ul>
        <li><strong>GST tax invoices and payment records</strong> — retained for 8 years as required by the Indian GST Act</li>
        <li><strong>Anti-fraud / anti-abuse logs</strong> — retained for 2 years (only aggregate, non-personal signals)</li>
        <li><strong>Audit trail of the deletion itself</strong> — retained for 2 years so that we can prove compliance if audited</li>
      </ul>
      <p>
        These retained records are stripped of identifying content wherever legally
        permitted (pseudonymized email, redacted content).
      </p>

      <h2>5. WhatsApp / Meta data handling</h2>
      <p>
        When you connect your WhatsApp Business Account we hold:
      </p>
      <ul>
        <li>An encrypted long-lived access token issued by Meta</li>
        <li>Metadata about your WABA (Business ID, WABA ID, phone_number_id, display name, quality rating)</li>
        <li>Copies of inbound and outbound messages (in your Tenant scope only)</li>
      </ul>
      <p>
        On a verified deletion request:
      </p>
      <ol>
        <li>We call Meta&apos;s
          <code>POST /{'{waba_id}'}/subscribed_apps</code> (DELETE) endpoint to unsubscribe our
          app from your WABA — no further webhooks will flow to us.
        </li>
        <li>We delete the encrypted access token, app secret, and verify token from our
          database. The plaintext is unrecoverable because the Fernet-encrypted ciphertext
          is destroyed along with any decryption context.</li>
        <li>We delete all stored message content and media associated with your WABA within
          the timelines in Section 6.</li>
        <li>Data that Meta itself stores on their servers is governed by
          <a href="https://www.facebook.com/policy.php" target="_blank" rel="noopener noreferrer">Meta&apos;s Data Policy</a>.
          To request deletion of data that lives on Meta&apos;s infrastructure, use
          <a href="https://www.facebook.com/help/contact/507739850846588" target="_blank" rel="noopener noreferrer">Meta&apos;s User Data Deletion form</a>.
        </li>
      </ol>

      <h2>6. Expected deletion timeline</h2>
      <table style={{ width: "100%", borderCollapse: "collapse", margin: "1rem 0" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid hsl(var(--border))" }}>
            <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Step</th>
            <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Timeline</th>
          </tr>
        </thead>
        <tbody>
          <tr style={{ borderBottom: "1px solid hsl(var(--border))" }}>
            <td style={{ padding: "0.5rem 0.75rem" }}>Request acknowledgement by email</td>
            <td style={{ padding: "0.5rem 0.75rem" }}>Within 48 hours of receipt</td>
          </tr>
          <tr style={{ borderBottom: "1px solid hsl(var(--border))" }}>
            <td style={{ padding: "0.5rem 0.75rem" }}>Identity verification (email challenge)</td>
            <td style={{ padding: "0.5rem 0.75rem" }}>Within 5 business days</td>
          </tr>
          <tr style={{ borderBottom: "1px solid hsl(var(--border))" }}>
            <td style={{ padding: "0.5rem 0.75rem" }}>Account and messaging data purge</td>
            <td style={{ padding: "0.5rem 0.75rem" }}>Within 30 days of verified request</td>
          </tr>
          <tr style={{ borderBottom: "1px solid hsl(var(--border))" }}>
            <td style={{ padding: "0.5rem 0.75rem" }}>Backup rotation (final backup expiry)</td>
            <td style={{ padding: "0.5rem 0.75rem" }}>Additional 60 days maximum</td>
          </tr>
          <tr>
            <td style={{ padding: "0.5rem 0.75rem" }}>Written confirmation of completion</td>
            <td style={{ padding: "0.5rem 0.75rem" }}>Within 7 days after purge</td>
          </tr>
        </tbody>
      </table>

      <h2>7. If your request is refused</h2>
      <p>
        We may refuse or partially fulfil a deletion request only when:
      </p>
      <ul>
        <li>The identity of the requester cannot be verified</li>
        <li>Deletion would prevent us from complying with a legal obligation (e.g. an active tax-audit hold)</li>
        <li>The request is repetitive, excessive, or made in bad faith</li>
      </ul>
      <p>
        In such cases we will provide a written reason within 30 days and inform you of
        your right to complain to the appropriate data-protection authority (in India:
        the Data Protection Board under the DPDP Act 2023).
      </p>

      <h2>8. Contact for deletion requests</h2>
      <p>
        <strong>Data Protection Officer / Grievance Officer</strong><br />
        tezsandesh.digital<br />
        Email: <a href="mailto:privacy@tezsandesh.digital?subject=User%20Data%20Deletion%20Request">privacy@tezsandesh.digital</a><br />
        Response window: within 48 hours of receipt
      </p>

      <p style={{ marginTop: "2rem", padding: "1rem", background: "hsl(var(--muted))", borderRadius: "6px", fontSize: "0.9em" }}>
        <strong>Note for Meta App Reviewers:</strong> This URL
        (<code>/data-deletion</code>) is the official user-data-deletion-instructions
        endpoint for our Meta Developer App. Users can also submit deletion callbacks
        via the standard OAuth Deauthorize / Data Deletion callback which we handle at
        <code>/api/webhooks/meta-data-deletion</code>.
      </p>
    </LegalLayout>
  );
}
