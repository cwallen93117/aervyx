import type { Metadata } from "next";

export const metadata: Metadata = { title: "Terms of Service — Aervyx" };

export default function TermsPage() {
  return (
    <main className="legal-page">
      <a href="/" className="legal-back">&larr; Back to Aervyx</a>
      <h1>Terms of Service</h1>
      <p className="legal-effective">Effective date: July 23, 2026</p>

      <p>
        These terms govern your use of the Aervyx platform (&quot;the Service&quot;). By creating an account or using
        the Service, you agree to these terms.
      </p>

      <h2>1. The Service</h2>
      <p>
        Aervyx is a competition management and flight tracking platform for hang gliding and paragliding. It provides
        event management, task design, live GPS tracking, flight scoring, a personal flight logbook, and related tools.
      </p>

      <h2>2. Beta Status</h2>
      <p>
        Aervyx is currently in <strong>public beta</strong>. The platform is under active development with the help
        of its community. By using the Service during the beta period, you acknowledge and accept the following:
      </p>
      <ul>
        <li>All services, features, and data storage are provided on a <strong>best-effort, as-is basis</strong>.</li>
        <li>Beta services may contain bugs, errors, incomplete features, or design flaws.</li>
        <li>Features may be added, modified, or removed without advance notice.</li>
        <li>No service level agreement (SLA) applies. Uptime, availability, and data persistence are not guaranteed.</li>
        <li>Data created during the beta period may be affected by schema changes, migrations, or resets. You are responsible for maintaining your own backups of critical data (e.g., IGC files, flight logs).</li>
        <li>The beta may end or transition to a general release at any time. There is no guarantee that any specific feature will remain available.</li>
        <li>By continuing to use the Service, you assume all risk associated with using pre-release software and agree that Aervyx and its contributors bear no liability for issues arising from the beta nature of the platform.</li>
      </ul>

      <h2>3. Accounts</h2>
      <ul>
        <li>You must provide accurate information when creating an account.</li>
        <li>You are responsible for keeping your login credentials secure.</li>
        <li>You must be at least 13 years old to use the Service.</li>
        <li>We may suspend or terminate accounts that violate these terms or are inactive for extended periods.</li>
      </ul>

      <h2>4. Acceptable Use</h2>
      <p>You agree not to:</p>
      <ul>
        <li>Use the Service for any unlawful purpose</li>
        <li>Attempt to gain unauthorized access to other accounts or platform infrastructure</li>
        <li>Upload malicious files, spam, or content that infringes others&apos; rights</li>
        <li>Interfere with the operation of the Service (e.g., denial-of-service attacks, automated scraping at abusive rates)</li>
        <li>Submit falsified flight data or competition results</li>
        <li>Impersonate another pilot or organizer</li>
      </ul>

      <h2>5. Your Content</h2>
      <p>
        You retain ownership of content you upload (IGC files, flight data, profile information). By uploading content,
        you grant Aervyx a license to store, process, and display it as necessary to provide the Service — for example,
        showing your track on a live tracking map or computing your competition score.
      </p>
      <p>
        For competition events, your results (name, nation, scores, rankings) will be publicly visible as part of the
        event results. This is inherent to competition scoring.
      </p>

      <h2>6. Live Tracking and Safety</h2>
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

      <h2>7. Meshtastic and Radio Devices</h2>
      <p>
        If you use Meshtastic or other radio devices with the platform, you are responsible for compliance with radio
        licensing and regulations in your jurisdiction. Aervyx does not manufacture, sell, or certify radio hardware.
      </p>

      <h2>8. Source Code</h2>
      <p>
        These terms govern your use of the hosted Service at aervyx.net. Aervyx source code is licensed separately
        under the GNU Affero General Public License, Version 3, as stated in the repository&apos;s LICENSE file.
      </p>

      <h2>9. Availability and Changes</h2>
      <p>
        We aim to keep the Service available but do not guarantee uptime. We may modify, suspend, or discontinue
        features at any time. We will make reasonable efforts to notify users of significant changes.
      </p>

      <h2>10. Disclaimer of Warranties and Limitation of Liability</h2>
      <p>
        THE SERVICE IS PROVIDED &quot;AS IS&quot; AND &quot;AS AVAILABLE&quot; WITHOUT WARRANTIES OF ANY KIND, WHETHER
        EXPRESS, IMPLIED, OR STATUTORY, INCLUDING BUT NOT LIMITED TO WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
        PARTICULAR PURPOSE, TITLE, AND NON-INFRINGEMENT. AERVYX DOES NOT WARRANT THAT THE SERVICE WILL BE
        UNINTERRUPTED, ERROR-FREE, OR SECURE.
      </p>
      <p>To the fullest extent permitted by law:</p>
      <ul>
        <li>Aervyx and its contributors are not liable for any indirect, incidental, special, or consequential damages arising from your use of the Service.</li>
        <li>Our total liability for any claim related to the Service is limited to the amount you paid us in the 12 months before the claim (which, for a free service, is zero).</li>
        <li>We are not liable for injuries, accidents, or losses that occur during flying activities, regardless of whether you were using the Service at the time.</li>
        <li>Without limiting the foregoing, Aervyx is not liable for any data loss, corruption, or unavailability that occurs during the beta period, including but not limited to flight records, competition results, logbook entries, or tracking data.</li>
      </ul>

      <h2>11. Indemnification</h2>
      <p>
        You agree to indemnify and hold harmless Aervyx and its contributors from claims, damages, or expenses arising
        from your use of the Service or violation of these terms.
      </p>

      <h2>12. Governing Law</h2>
      <p>
        These terms are governed by the laws of the Commonwealth of Pennsylvania, without regard to conflict-of-law
        principles. Any dispute arising from these terms or the Service will be subject to the exclusive jurisdiction
        and venue of the state and federal courts located in Pennsylvania.
      </p>

      <h2>13. Changes to These Terms</h2>
      <p>
        We may update these terms. Material changes will be noted on this page with an updated effective date.
        Continued use of the Service after changes constitutes acceptance.
      </p>

      <h2>14. Contact</h2>
      <p>
        For questions about these terms, contact us at <a href="mailto:aervyxnet@gmail.com">aervyxnet@gmail.com</a>.
      </p>
    </main>
  );
}
