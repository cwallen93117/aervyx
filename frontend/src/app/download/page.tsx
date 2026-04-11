import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Download Aervyx Pilot — Android App",
  description:
    "Download the Aervyx Pilot Android app for live tracking, logbook, and competition support.",
};

interface AppVersionResponse {
  version: string;
  version_code: number;
  download_url: string;
  release_notes: string | null;
  release_date: string | null;
  min_supported_version: string;
  file_size_bytes: number | null;
}

async function fetchAppVersion(): Promise<AppVersionResponse | null> {
  try {
    const apiBase = process.env.BACKEND_INTERNAL_URL || "http://backend:8000";
    const res = await fetch(`${apiBase}/api/app/version`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return (await res.json()) as AppVersionResponse;
  } catch {
    return null;
  }
}

function formatBytes(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  if (bytes >= 1_000) return `${Math.round(bytes / 1_000)} KB`;
  return `${bytes} B`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default async function DownloadPage() {
  const app = await fetchAppVersion();

  return (
    <>
      <style>{`
        /* Download page — dark brand theme matching aervyx-landing.css */
        *,*::before,*::after{box-sizing:border-box}
        .dl-page{
          min-height:100vh;
          background:#06090f;
          color:rgba(255,255,255,0.88);
          font-family:'Barlow',sans-serif;
          font-weight:400;
          line-height:1.6;
          display:flex;
          flex-direction:column;
        }
        /* NAV */
        .dl-nav{
          display:flex;
          align-items:center;
          justify-content:space-between;
          padding:0 2rem;
          height:60px;
          background:rgba(6,9,15,0.9);
          backdrop-filter:blur(20px);
          border-bottom:1px solid rgba(255,255,255,0.07);
          position:sticky;
          top:0;
          z-index:100;
        }
        .dl-nav-brand{
          display:flex;
          align-items:center;
          gap:0.5rem;
          text-decoration:none;
        }
        .dl-nav-wordmark{
          font-family:'Exo 2',sans-serif;
          font-weight:900;
          font-size:1.1rem;
          color:#fff;
          letter-spacing:-0.01em;
        }
        .dl-nav-tld{color:#00e5ff}
        .dl-nav-back{
          font-size:0.875rem;
          color:rgba(255,255,255,0.42);
          text-decoration:none;
          transition:color .18s;
        }
        .dl-nav-back:hover{color:#fff}
        /* MAIN */
        .dl-main{
          flex:1;
          display:flex;
          align-items:center;
          justify-content:center;
          padding:3rem 1.5rem 5rem;
          position:relative;
        }
        .dl-bg{
          position:absolute;
          inset:0;
          background:
            radial-gradient(ellipse 80% 55% at 50% -10%,rgba(0,229,255,0.06) 0%,transparent 60%),
            radial-gradient(ellipse 50% 40% at 80% 90%,rgba(255,107,53,0.05) 0%,transparent 55%);
          pointer-events:none;
        }
        .dl-card{
          position:relative;
          width:100%;
          max-width:580px;
          background:#111827;
          border:1px solid rgba(255,255,255,0.1);
          border-radius:18px;
          overflow:hidden;
          box-shadow:0 40px 90px rgba(0,0,0,0.6),0 0 60px rgba(0,229,255,0.04);
        }
        /* Card header stripe */
        .dl-card-header{
          background:linear-gradient(135deg,rgba(0,229,255,0.08) 0%,rgba(0,229,255,0.02) 100%);
          border-bottom:1px solid rgba(255,255,255,0.07);
          padding:2rem 2rem 1.5rem;
          display:flex;
          align-items:center;
          gap:1.1rem;
        }
        .dl-app-icon{
          width:56px;
          height:56px;
          border-radius:14px;
          background:linear-gradient(135deg,#0b1120 0%,#16202f 100%);
          border:1px solid rgba(0,229,255,0.22);
          display:flex;
          align-items:center;
          justify-content:center;
          flex-shrink:0;
          box-shadow:0 0 20px rgba(0,229,255,0.12);
        }
        .dl-app-name{
          font-family:'Exo 2',sans-serif;
          font-weight:900;
          font-size:1.5rem;
          color:#fff;
          letter-spacing:-0.02em;
          line-height:1.1;
        }
        .dl-app-tagline{
          font-size:0.82rem;
          color:rgba(255,255,255,0.42);
          margin-top:0.22rem;
          font-weight:300;
        }
        /* Card body */
        .dl-card-body{
          padding:1.75rem 2rem 2rem;
        }
        /* Meta row */
        .dl-meta{
          display:flex;
          align-items:center;
          gap:0.6rem;
          flex-wrap:wrap;
          margin-bottom:1.5rem;
        }
        .dl-badge{
          display:inline-flex;
          align-items:center;
          gap:0.3rem;
          padding:0.25rem 0.65rem;
          border-radius:999px;
          font-family:'JetBrains Mono',monospace;
          font-size:0.7rem;
          font-weight:600;
          letter-spacing:0.04em;
          border:1px solid;
        }
        .dl-badge-version{
          background:rgba(0,229,255,0.07);
          border-color:rgba(0,229,255,0.22);
          color:#00e5ff;
        }
        .dl-badge-android{
          background:rgba(0,230,118,0.07);
          border-color:rgba(0,230,118,0.2);
          color:#00e676;
        }
        .dl-badge-date{
          background:rgba(255,255,255,0.04);
          border-color:rgba(255,255,255,0.1);
          color:rgba(255,255,255,0.45);
        }
        .dl-badge-changelog{
          background:transparent;
          border-color:rgba(0,229,255,0.22);
          color:rgba(0,229,255,0.8);
          text-decoration:none;
          transition:background .18s,color .18s,border-color .18s;
        }
        .dl-badge-changelog:hover{
          background:rgba(0,229,255,0.08);
          color:#00e5ff;
          border-color:rgba(0,229,255,0.45);
        }
        /* Size info */
        .dl-size{
          font-size:0.8rem;
          color:rgba(255,255,255,0.35);
          margin-bottom:1.5rem;
        }
        /* Download button */
        .dl-btn{
          display:inline-flex;
          align-items:center;
          justify-content:center;
          gap:0.55rem;
          width:100%;
          padding:0.95rem 1.5rem;
          border-radius:12px;
          background:#00e5ff;
          color:#06090f;
          font-family:'Barlow',sans-serif;
          font-size:1rem;
          font-weight:700;
          text-decoration:none;
          border:none;
          cursor:pointer;
          transition:background .18s,transform .14s,box-shadow .18s;
          box-shadow:0 0 36px rgba(0,229,255,0.28);
          margin-bottom:1rem;
        }
        .dl-btn:hover{
          background:#1aecff;
          transform:translateY(-2px);
          box-shadow:0 4px 52px rgba(0,229,255,0.44);
        }
        /* Android disclaimer */
        .dl-disclaimer{
          display:flex;
          align-items:flex-start;
          gap:0.5rem;
          background:rgba(255,107,53,0.05);
          border:1px solid rgba(255,107,53,0.15);
          border-radius:8px;
          padding:0.75rem 1rem;
          font-size:0.8rem;
          color:rgba(255,255,255,0.55);
          margin-bottom:1.5rem;
          line-height:1.5;
        }
        .dl-disclaimer-icon{
          color:#ff6b35;
          flex-shrink:0;
          margin-top:0.05rem;
        }
        /* Release notes */
        .dl-notes-label{
          font-family:'Exo 2',sans-serif;
          font-size:0.7rem;
          font-weight:700;
          letter-spacing:0.12em;
          text-transform:uppercase;
          color:#00e5ff;
          margin-bottom:0.6rem;
        }
        .dl-notes{
          background:#0b1120;
          border:1px solid rgba(255,255,255,0.06);
          border-radius:8px;
          padding:1rem 1.1rem;
          font-size:0.84rem;
          color:rgba(255,255,255,0.65);
          white-space:pre-wrap;
          line-height:1.65;
          margin-bottom:1.5rem;
          max-height:220px;
          overflow-y:auto;
        }
        /* Installation steps */
        .dl-steps-label{
          font-family:'Exo 2',sans-serif;
          font-size:0.7rem;
          font-weight:700;
          letter-spacing:0.12em;
          text-transform:uppercase;
          color:rgba(255,255,255,0.35);
          margin-bottom:0.7rem;
        }
        .dl-steps{
          display:flex;
          flex-direction:column;
          gap:0.55rem;
          list-style:none;
          margin:0;
          padding:0;
        }
        .dl-steps li{
          display:flex;
          align-items:flex-start;
          gap:0.65rem;
          font-size:0.83rem;
          color:rgba(255,255,255,0.5);
          line-height:1.5;
        }
        .dl-step-num{
          display:inline-flex;
          align-items:center;
          justify-content:center;
          width:20px;
          height:20px;
          border-radius:50%;
          background:rgba(0,229,255,0.1);
          border:1px solid rgba(0,229,255,0.2);
          color:#00e5ff;
          font-family:'JetBrains Mono',monospace;
          font-size:0.65rem;
          font-weight:600;
          flex-shrink:0;
          margin-top:0.08rem;
        }
        /* Divider */
        .dl-divider{
          border:none;
          border-top:1px solid rgba(255,255,255,0.06);
          margin:1.5rem 0;
        }
        /* Coming soon state */
        .dl-soon{
          text-align:center;
          padding:3rem 2rem;
        }
        .dl-soon-icon{
          margin:0 auto 1.25rem;
          width:64px;
          height:64px;
          border-radius:16px;
          background:rgba(255,255,255,0.04);
          border:1px solid rgba(255,255,255,0.09);
          display:flex;
          align-items:center;
          justify-content:center;
        }
        .dl-soon-title{
          font-family:'Exo 2',sans-serif;
          font-weight:800;
          font-size:1.35rem;
          color:#fff;
          margin-bottom:0.65rem;
          letter-spacing:-0.01em;
        }
        .dl-soon-sub{
          font-size:0.88rem;
          color:rgba(255,255,255,0.38);
          line-height:1.7;
          max-width:360px;
          margin:0 auto;
        }
        /* Footer */
        .dl-footer{
          text-align:center;
          padding:1.5rem;
          font-size:0.75rem;
          color:rgba(255,255,255,0.2);
          border-top:1px solid rgba(255,255,255,0.05);
        }
        .dl-footer a{
          color:rgba(0,229,255,0.5);
          text-decoration:none;
        }
        .dl-footer a:hover{color:#00e5ff}
        @media(max-width:480px){
          .dl-card-header{padding:1.5rem 1.25rem 1.2rem;gap:0.85rem}
          .dl-card-body{padding:1.25rem 1.25rem 1.5rem}
          .dl-app-name{font-size:1.25rem}
          .dl-nav{padding:0 1rem}
        }
      `}</style>

      <div className="dl-page">
        {/* Navigation */}
        <nav className="dl-nav">
          <a href="/" className="dl-nav-brand" aria-label="Aervyx home">
            <svg width="26" height="26" viewBox="0 0 30 30" fill="none" aria-hidden="true">
              <path
                d="M15 3L27 25L15 19L3 25Z"
                stroke="#00e5ff"
                strokeWidth="1.5"
                fill="none"
                strokeLinejoin="round"
              />
              <path d="M15 3L15 19" stroke="#00e5ff" strokeWidth="1" opacity="0.4" />
              <circle cx="15" cy="15" r="2.2" fill="#00e5ff" opacity="0.85" />
            </svg>
            <span className="dl-nav-wordmark">
              Aervyx<span className="dl-nav-tld">.net</span>
            </span>
          </a>
          <a href="/" className="dl-nav-back">
            &larr; Back to home
          </a>
        </nav>

        {/* Main */}
        <main className="dl-main">
          <div className="dl-bg" aria-hidden="true" />

          <div className="dl-card">
            {/* Card header */}
            <div className="dl-card-header">
              <div className="dl-app-icon" aria-hidden="true">
                <svg width="32" height="32" viewBox="0 0 30 30" fill="none">
                  <path
                    d="M15 3L27 25L15 19L3 25Z"
                    stroke="#00e5ff"
                    strokeWidth="1.5"
                    fill="none"
                    strokeLinejoin="round"
                  />
                  <path d="M15 3L15 19" stroke="#00e5ff" strokeWidth="1" opacity="0.4" />
                  <circle cx="15" cy="15" r="2.2" fill="#00e5ff" opacity="0.85" />
                  <circle cx="15" cy="15" r="5" stroke="#00e5ff" strokeWidth="0.5" fill="none" opacity="0.3" />
                </svg>
              </div>
              <div>
                <div className="dl-app-name">Aervyx Pilot</div>
                <div className="dl-app-tagline">
                  Live tracking, logbook &amp; competition support
                </div>
              </div>
            </div>

            {/* Card body */}
            <div className="dl-card-body">
              {app ? (
                <>
                  {/* Meta badges */}
                  <div className="dl-meta">
                    <span className="dl-badge dl-badge-version">
                      <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true">
                        <circle cx="4" cy="4" r="3.5" fill="#00e5ff" opacity="0.7" />
                      </svg>
                      v{app.version}+{app.version_code}
                    </span>
                    <span className="dl-badge dl-badge-android">Android</span>
                    {app.release_date && (
                      <span className="dl-badge dl-badge-date">
                        {formatDate(app.release_date)}
                      </span>
                    )}
                    <a href="/changelog" className="dl-badge dl-badge-changelog">
                      View changelog →
                    </a>
                  </div>

                  {/* File size */}
                  {app.file_size_bytes != null && app.file_size_bytes > 0 && (
                    <div className="dl-size">
                      APK size: {formatBytes(app.file_size_bytes)}
                    </div>
                  )}

                  {/* Download button */}
                  <a
                    href={app.download_url}
                    className="dl-btn"
                    aria-label={`Download Aervyx Pilot v${app.version}+${app.version_code} APK`}
                  >
                    <svg
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                    Download APK
                  </a>

                  {/* Android disclaimer */}
                  <div className="dl-disclaimer" role="note">
                    <span className="dl-disclaimer-icon" aria-hidden="true">
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <circle cx="12" cy="12" r="10" />
                        <line x1="12" y1="8" x2="12" y2="12" />
                        <line x1="12" y1="16" x2="12.01" y2="16" />
                      </svg>
                    </span>
                    <span>
                      <strong style={{ color: "rgba(255,255,255,0.7)" }}>Android only</strong>
                      {" — "}APK sideload required. iOS is not yet available.
                      Open the downloaded file with your file manager to install.
                    </span>
                  </div>

                  {/* Release notes */}
                  {app.release_notes && app.release_notes.trim().length > 0 && (
                    <>
                      <div className="dl-notes-label">Release notes</div>
                      <div className="dl-notes">{app.release_notes}</div>
                    </>
                  )}

                  <hr className="dl-divider" />

                  {/* Installation instructions */}
                  <div className="dl-steps-label">Installation steps</div>
                  <ol className="dl-steps">
                    <li>
                      <span className="dl-step-num">1</span>
                      <span>
                        On your Android device, open <strong style={{ color: "rgba(255,255,255,0.65)" }}>Settings</strong>{" "}
                        and search for <strong style={{ color: "rgba(255,255,255,0.65)" }}>Install unknown apps</strong>.
                        Grant permission to your browser or file manager.
                      </span>
                    </li>
                    <li>
                      <span className="dl-step-num">2</span>
                      <span>
                        Tap <strong style={{ color: "rgba(255,255,255,0.65)" }}>Download APK</strong> above and wait
                        for the file to finish downloading.
                      </span>
                    </li>
                    <li>
                      <span className="dl-step-num">3</span>
                      <span>
                        Open the downloaded{" "}
                        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "0.78rem", color: "#00e5ff" }}>
                          .apk
                        </span>{" "}
                        file from your notifications or file manager and tap{" "}
                        <strong style={{ color: "rgba(255,255,255,0.65)" }}>Install</strong>.
                      </span>
                    </li>
                    <li>
                      <span className="dl-step-num">4</span>
                      <span>
                        Launch <strong style={{ color: "rgba(255,255,255,0.65)" }}>Aervyx Pilot</strong>, log in with
                        your Aervyx account, and you&apos;re ready to fly.
                      </span>
                    </li>
                  </ol>
                </>
              ) : (
                /* Coming soon state */
                <div className="dl-soon">
                  <div className="dl-soon-icon" aria-hidden="true">
                    <svg
                      width="28"
                      height="28"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="rgba(255,255,255,0.3)"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <rect x="5" y="2" width="14" height="20" rx="2" ry="2" />
                      <line x1="12" y1="18" x2="12.01" y2="18" />
                    </svg>
                  </div>
                  <div className="dl-soon-title">App download coming soon</div>
                  <p className="dl-soon-sub">
                    The Aervyx Pilot Android app is almost ready. Check back shortly
                    or{" "}
                    <a
                      href="https://github.com/cwallen93117/aervyx"
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "#00e5ff", textDecoration: "none" }}
                    >
                      follow the project on GitHub
                    </a>{" "}
                    to be notified when it launches.
                  </p>
                </div>
              )}
            </div>
          </div>
        </main>

        {/* Footer */}
        <footer className="dl-footer">
          <span>
            &copy; {new Date().getFullYear()} Aervyx &mdash;{" "}
            <a href="/privacy">Privacy</a> &middot; <a href="/terms">Terms</a> &middot;{" "}
            <a
              href="https://github.com/cwallen93117/aervyx"
              target="_blank"
              rel="noopener noreferrer"
            >
              Open Source
            </a>
          </span>
        </footer>
      </div>
    </>
  );
}
