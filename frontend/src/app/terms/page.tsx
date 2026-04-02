import type { Metadata } from "next";

export const metadata: Metadata = { title: "Terms of Service — Aervyx" };

export default function TermsPage() {
  return (
    <main className="legal-page">
      <a href="/" className="legal-back">&larr; Back to Aervyx</a>
      <h1>Terms of Service</h1>
      <p className="legal-effective">Effective date: April 2, 2026</p>

      <p>
        These terms govern your use of the Aervyx platform (&quot;the Service&quot;), operated as an open-source
        project. By creating an account or using the Service, you agree to these terms.
      </p>

      <h2>1. The Service</h2>
      <p>
        Aervyx is a competition management and flight tracking platform for hang gliding and paragliding. It provides
        event management, task design, live GPS tracking, flight scoring, a personal flight logbook, and related tools.
      </p>

      <h2>2. Accounts</h2>
      <ul>
        <li>You must provide accurate information when creating an account.</li>
        <li>You are responsible for keeping your login credentials secure.</li>
        <li>You must be at least 13 years old to use the Service.</li>
        <li>We may suspend or terminate accounts that violate these terms or are inactive for extended periods.</li>
      </ul>

      <h2>3. Acceptable Use</h2>
      <p>You agree not to:</p>
      <ul>
        <li>Use the Service for any unlawful purpose</li>
        <li>Attempt to gain unauthorized access to other accounts or platform infrastructure</li>
        <li>Upload malicious files, spam, or content that infringes others&apos; rights</li>
        <li>Interfere with the operation of the Service (e.g., denial-of-service attacks, automated scraping at abusive rates)</li>
        <li>Submit falsified flight data or competition results</li>
        <li>Impersonate another pilot or organizer</li>
      </ul>

      <h2>4. Your Content</h2>
      <p>
        You retain ownership of content you upload (IGC files, flight data, profile information). By uploading content,
        you grant Aervyx a license to store, process, and display it as necessary to provide the Service — for example,
        showing your track on a live tracking map or computing your competition score.
      </p>
      <p>
        For competition events, your results (name, nation, scores, rankings) will be publicly visible as part of the
        event results. This is inherent to competition scoring.
      </p>

      <h2>5. Live Tracking and Safety</h2>
      <p>
        Live tracking is provided as a convenience and should <strong>not</strong> be relied upon as a sole safety
        system. GPS positions may be delayed, inaccurate, or unavailable due to signal loss, device failure, or
        network issues. Pilots are responsible for their own safety and must follow all applicable aviation regulations
        and site rules.
      </p>
      <p>
        Aervyx is not a substitute for proper flight planning, safety equipment, or emergency services. The SOS alert
        feature is a best-effort notification and does not guarantee emergency response.
      </p>

      <h2>6. Meshtastic and Radio Devices</h2>
      <p>
        If you use Meshtastic or other radio devices with the platform, you are responsible for compliance with radio
        licensing and regulations in your jurisdiction. Aervyx does not manufacture, sell, or certify radio hardware.
      </p>

      <h2>7. Open Source</h2>
      <p>
        The Aervyx source code is available under an open-source license. These terms govern your use of the hosted
        Service at aervyx.net, not the source code itself. If you self-host Aervyx, these terms do not apply to your
        instance.
      </p>

      <h2>8. Availability and Changes</h2>
      <p>
        We aim to keep the Service available but do not guarantee uptime. We may modify, suspend, or discontinue
        features at any time. We will make reasonable efforts to notify users of significant changes.
      </p>

      <h2>9. Limitation of Liability</h2>
      <p>
        The Service is provided &quot;as is&quot; without warranties of any kind, express or implied. To the fullest
        extent permitted by law:
      </p>
      <ul>
        <li>Aervyx and its contributors are not liable for any indirect, incidental, special, or consequential damages arising from your use of the Service.</li>
        <li>Our total liability for any claim related to the Service is limited to the amount you paid us in the 12 months before the claim (which, for a free service, is zero).</li>
        <li>We are not liable for injuries, accidents, or losses that occur during flying activities, regardless of whether you were using the Service at the time.</li>
      </ul>

      <h2>10. Indemnification</h2>
      <p>
        You agree to indemnify and hold harmless Aervyx and its contributors from claims, damages, or expenses arising
        from your use of the Service or violation of these terms.
      </p>

      <h2>11. Governing Law</h2>
      <p>
        These terms are governed by the laws of the United States. Any disputes will be resolved in courts located in
        California.
      </p>

      <h2>12. Changes to These Terms</h2>
      <p>
        We may update these terms. Material changes will be noted on this page with an updated effective date.
        Continued use of the Service after changes constitutes acceptance.
      </p>

      <h2>13. Contact</h2>
      <p>
        For questions about these terms, contact us at <a href="mailto:legal@aervyx.net">legal@aervyx.net</a>.
      </p>
    </main>
  );
}
