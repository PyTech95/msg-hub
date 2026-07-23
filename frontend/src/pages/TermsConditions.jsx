import React from "react";
import { FileText } from "lucide-react";
import LegalLayout from "@/components/LegalLayout";

export default function TermsConditions() {
  return (
    <LegalLayout title="Terms &amp; Conditions" lastUpdated="23 July 2026" icon={FileText}>
      <p>
        These Terms &amp; Conditions (&quot;Terms&quot;) govern your access to and use of the
        <strong> tezsandesh.digital</strong> Platform (the &quot;Service&quot;). By creating an
        account, accessing or using the Service you agree to be bound by these Terms. If
        you do not agree, do not use the Service.
      </p>

      <h2>1. Acceptance of Terms</h2>
      <p>
        You confirm that (a) you are at least 18 years old, (b) you have the authority
        to bind your organization to these Terms, and (c) the information you provide is
        accurate and complete. Continued use of the Service constitutes ongoing acceptance
        of these Terms, including any updates published on this page.
      </p>

      <h2>2. Description of Service — SaaS usage</h2>
      <p>
        We provide a hosted, multi-tenant Software-as-a-Service platform that enables
        businesses to communicate with their customers over the official Meta WhatsApp
        Business Platform, SMS, email and voice. The Service includes a message inbox,
        template manager, broadcast/campaign engine, wallet, billing, analytics and
        related tooling.
      </p>
      <p>
        Each customer account is a <strong>Tenant</strong>. Data is strictly isolated
        between Tenants at the database query level.
      </p>

      <h2>3. WhatsApp Business Platform usage</h2>
      <p>
        The Service uses the official <strong>Meta WhatsApp Cloud API</strong>. By
        connecting your WhatsApp Business Account (WABA) via Meta&apos;s Embedded Signup
        flow, you authorize us to send and receive messages on your behalf using the
        access token that Meta issues. Your obligations under the
        <a href="https://www.whatsapp.com/legal/business-policy" target="_blank" rel="noopener noreferrer"> WhatsApp Business Messaging Policy</a>
        and
        <a href="https://www.whatsapp.com/legal/commerce-policy" target="_blank" rel="noopener noreferrer"> WhatsApp Commerce Policy</a>
        remain your own — we are a service provider, not a party to those policies.
      </p>

      <h2>4. Meta compliance</h2>
      <p>You agree to comply with:</p>
      <ul>
        <li>Meta&apos;s Platform Terms and Data Processing Terms</li>
        <li>WhatsApp Business Messaging Policy (opt-in, no spam, no restricted content)</li>
        <li>All template approval requirements — you may not send template messages that have not been approved by Meta</li>
        <li>The 24-hour customer service window rule — free-form outbound messages must occur within 24 hours of the customer&apos;s most recent inbound message; outside that window only approved template categories may be used</li>
      </ul>
      <p>
        Repeated policy violations may result in reduced quality rating, messaging limit
        downgrades, or WABA suspension by Meta. We are not responsible for Meta-imposed
        restrictions arising from your usage.
      </p>

      <h2>5. User responsibilities</h2>
      <ul>
        <li>You are responsible for the content of every message you send</li>
        <li>You must obtain valid opt-in from every recipient before contacting them</li>
        <li>You must honor opt-out requests promptly (STOP / UNSUBSCRIBE keywords are respected automatically by the Platform, but you must also cease business messaging where required)</li>
        <li>You may not use the Service to send spam, phishing, malware, unlawful content, hate speech, or any content prohibited by Meta or applicable law</li>
        <li>You must safeguard your account credentials, use 2FA where available, and immediately notify us of any suspected unauthorized access</li>
        <li>You must comply with all applicable Indian and foreign laws — DPDP Act 2023, TRAI DLT regulations for SMS, GST for tax invoicing, GDPR/CCPA where relevant</li>
      </ul>

      <h2>6. Billing, Wallet &amp; Subscriptions</h2>

      <h3>6.1 Wallet</h3>
      <p>
        The Service operates on a <strong>prepaid wallet</strong> model. You top up your
        wallet using Razorpay and every outbound message deducts a per-message price
        (published on your billing page) plus applicable taxes. You are responsible for
        ensuring sufficient wallet balance; sending fails with HTTP 402 when the balance
        is insufficient.
      </p>

      <h3>6.2 Subscription plans</h3>
      <p>
        You may optionally subscribe to a plan (Starter / Growth / Pro / Enterprise) which
        includes a monthly credit allocation and platform features. Plans renew
        automatically unless auto-renew is disabled. On cancellation the plan remains
        active until the end of the paid period.
      </p>

      <h3>6.3 GST invoicing</h3>
      <p>
        For Indian Tenants we issue GST tax invoices with a sequential invoice number
        (<code>TZS/YYYY/NNNNNN</code>) and CGST+SGST or IGST split based on your GSTIN
        state. You are responsible for providing a valid 15-character GSTIN.
      </p>

      <h3>6.4 Refund policy</h3>
      <p>
        Wallet balances are <strong>non-refundable</strong> once used. Unused wallet
        balance is refundable within <strong>30 days</strong> of top-up on written request
        to <a href="mailto:billing@tezsandesh.digital">billing@tezsandesh.digital</a>,
        subject to a 5% processing charge deducted by Razorpay. Subscription fees are
        non-refundable except in cases of documented Service-side outage exceeding 72
        hours in a calendar month, in which case we will credit a pro-rata refund to your
        wallet.
      </p>

      <h2>7. Account suspension &amp; termination</h2>
      <p>
        We may suspend or terminate your account, without prior notice, if:
      </p>
      <ul>
        <li>You breach these Terms, Meta&apos;s policies, or applicable law</li>
        <li>Your wallet remains at zero balance and account inactive for more than 180 days</li>
        <li>You engage in fraudulent payments, chargebacks or abuse</li>
        <li>We are ordered to suspend by a court, regulator or Meta</li>
      </ul>
      <p>
        You may terminate your account at any time from Settings → Account Deletion, or
        by writing to <a href="mailto:privacy@tezsandesh.digital">privacy@tezsandesh.digital</a>.
        See <a href="/data-deletion">Data Deletion</a> for what happens on account closure.
      </p>

      <h2>8. Intellectual property</h2>
      <p>
        The Service — including all code, UI, documentation, trademarks, and content
        created by us — is owned by tezsandesh.digital and its licensors and is protected
        by copyright and other intellectual-property laws. You retain all rights to your
        own data (contacts, message content, media). By using the Service you grant us a
        limited, worldwide, royalty-free license to store, transmit and process your data
        solely to operate the Service on your behalf.
      </p>

      <h2>9. Limitation of liability</h2>
      <p>
        To the maximum extent permitted by law, the Service is provided <strong>&quot;as
        is&quot;</strong> without warranties of any kind. We are not liable for indirect,
        incidental, special, consequential, or punitive damages, or any loss of profits
        or data, arising out of or related to your use of the Service. Our aggregate
        liability for any claim arising from these Terms shall not exceed the amount you
        paid us in the twelve months preceding the claim.
      </p>
      <p>
        We are not responsible for Meta-side outages, WhatsApp Cloud API rate limits,
        WABA suspension by Meta, or any third-party payment processor failure.
      </p>

      <h2>10. Indemnification</h2>
      <p>
        You agree to indemnify and hold harmless tezsandesh.digital, its officers,
        employees and affiliates from any claim, damage or expense arising out of (a)
        your breach of these Terms, (b) your violation of Meta&apos;s policies or any law,
        or (c) any content you sent through the Service.
      </p>

      <h2>11. Governing law &amp; dispute resolution</h2>
      <p>
        These Terms are governed by the laws of India, without regard to conflict-of-law
        principles. Any dispute shall be subject to the exclusive jurisdiction of the
        courts of <strong>Mumbai, Maharashtra</strong>. Before filing any suit the parties
        will attempt in good faith to resolve the dispute through 30 days of
        confidential written negotiation.
      </p>

      <h2>12. Changes to these Terms</h2>
      <p>
        We may revise these Terms at any time. Material changes will be notified by email
        or via an in-app banner at least 14 days before they take effect. Continued use of
        the Service after the effective date constitutes acceptance of the revised Terms.
      </p>

      <h2>13. Contact us</h2>
      <p>
        General support: <a href="mailto:support@tezsandesh.digital">support@tezsandesh.digital</a><br />
        Billing enquiries: <a href="mailto:billing@tezsandesh.digital">billing@tezsandesh.digital</a><br />
        Legal / privacy: <a href="mailto:privacy@tezsandesh.digital">privacy@tezsandesh.digital</a>
      </p>
    </LegalLayout>
  );
}
