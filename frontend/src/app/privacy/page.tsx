import type { Metadata } from "next";

export const metadata: Metadata = { title: "Privacy Policy — Aervyx" };

export default function PrivacyPage() {
  return (
    <main className="legal-page">
      <a href="/" className="legal-back">&larr; Back to Aervyx</a>
      <h1>Privacy Policy</h1>
      <p className="legal-effective">Effective date: April 2, 2026</p>

      <p>
        Aervyx (&quot;we&quot;, &quot;us&quot;, or &quot;the platform&quot;) is a competition management platform for hang
        gliding and paragliding. This policy explains what data we collect, why, and how we protect it.
      </p>

      <h2>1. Information We Collect</h2>
      <h3>Account information</h3>
      <p>
        When you create an account we collect your email address, display name, and an optional competition number,
        nation code, CIVL ID, and name. If you sign in with Google, we receive your email and name from Google&apos;s
        OAuth service.
      </p>
      <h3>Flight and tracking data</h3>
      <p>
        When you upload IGC files or use live tracking, we process GPS coordinates, altitude, timestamps, and derived
        flight statistics (duration, distance, climb rates). This data is stored to power your logbook, flight replay,
        and competition scoring.
      </p>
      <h3>Live tracking positions</h3>
      <p>
        During live tracking sessions (via the mobile app, Meshtastic devices, or buddy group tracking), your GPS
        position is transmitted in real time. Positions are retained for the duration of the tracking session and
        associated event or buddy group.
      </p>
      <h3>Device and usage data</h3>
      <p>
        We collect standard server logs (IP address, browser user-agent, request timestamps) for security and
        debugging purposes. We do not use third-party analytics or advertising trackers.
      </p>

      <h2>2. How We Use Your Data</h2>
      <ul>
        <li>Provide competition management, scoring, and live tracking services</li>
        <li>Store and display your flight logbook and statistics</li>
        <li>Enable buddy group tracking so pilots you choose can see your position</li>
        <li>Authenticate your account and protect against unauthorized access</li>
        <li>Debug technical issues and maintain platform reliability</li>
      </ul>

      <h2>3. Data Sharing</h2>
      <p>
        We do not sell your personal data. Your data may be visible to others in these contexts:
      </p>
      <ul>
        <li><strong>Competition results:</strong> Your name, nation, and scores are visible on public results pages for events you participate in.</li>
        <li><strong>Live tracking:</strong> Your position is visible to other participants in the same event or buddy group.</li>
        <li><strong>Event organizers:</strong> Organizers of events you join can see your registration details and flight data for that event.</li>
      </ul>
      <p>
        We may share data with law enforcement if required by law or to protect the safety of pilots.
      </p>

      <h2>4. Data Storage and Security</h2>
      <p>
        Data is stored on servers we operate. Passwords are hashed using bcrypt and are never stored in plain text.
        All connections use HTTPS/TLS encryption. We follow reasonable security practices but cannot guarantee
        absolute security — no internet service can.
      </p>

      <h2>5. Data Retention</h2>
      <p>
        Account data and flight logs are retained as long as your account is active. You may request deletion of your
        account and associated data by contacting us. Server logs are retained for up to 90 days.
      </p>

      <h2>6. Cookies</h2>
      <p>
        We use a session token stored in your browser&apos;s local storage to keep you logged in. We use a theme
        preference cookie to remember your light/dark mode choice. We do not use tracking cookies or third-party cookies.
      </p>

      <h2>7. Third-Party Services</h2>
      <ul>
        <li><strong>Google Sign-In:</strong> If you choose to sign in with Google, your authentication is handled by Google&apos;s OAuth service. See <a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer">Google&apos;s Privacy Policy</a>.</li>
        <li><strong>Cloudflare:</strong> We use Cloudflare for DNS and DDoS protection. See <a href="https://www.cloudflare.com/privacypolicy/" target="_blank" rel="noopener noreferrer">Cloudflare&apos;s Privacy Policy</a>.</li>
        <li><strong>MapTiler / OpenStreetMap:</strong> Map tiles are loaded from third-party providers when you view maps.</li>
      </ul>

      <h2>8. Children</h2>
      <p>
        Aervyx is not directed at children under 13. We do not knowingly collect data from children under 13.
      </p>

      <h2>9. Your Rights</h2>
      <p>
        You may request access to, correction of, or deletion of your personal data by contacting us. If you are in
        the EU/EEA, you have rights under the GDPR including the right to data portability and the right to lodge a
        complaint with a supervisory authority.
      </p>

      <h2>10. Changes</h2>
      <p>
        We may update this policy. Material changes will be noted on this page with an updated effective date.
      </p>

      <h2>11. Contact</h2>
      <p>
        For privacy questions, contact us at <a href="mailto:privacy@aervyx.net">privacy@aervyx.net</a>.
      </p>
    </main>
  );
}
