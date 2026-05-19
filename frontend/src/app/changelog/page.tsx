import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Changelog — Aervyx Pilot",
  description:
    "Release history and changelog for the Aervyx Pilot Android app — every version, every fix.",
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

async function fetchReleases(): Promise<AppVersionResponse[] | null> {
  try {
    const apiBase = process.env.BACKEND_INTERNAL_URL || "http://backend:8000";
    const res = await fetch(`${apiBase}/api/app/releases`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return (await res.json()) as AppVersionResponse[];
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

export default async function ChangelogPage() {
  const releases = await fetchReleases();
  const hasReleases = releases && releases.length > 0;
  const latest = hasReleases ? releases[0] : null;

  return (
    <>
      <style>{`
        /* Changelog page — dark brand theme matching aervyx-landing.css */
        *,*::before,*::after{box-sizing:border-box}
        .cl-page{
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
        .cl-nav{
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
        .cl-nav-brand{
          display:flex;
          align-items:center;
          gap:0.5rem;
          text-decoration:none;
        }
        .cl-nav-wordmark{
          font-family:'Exo 2',sans-serif;
          font-weight:900;
          font-size:1.1rem;
          color:#fff;
          letter-spacing:-0.01em;
        }
        .cl-nav-tld{color:#00e5ff}
        .cl-nav-back{
          font-size:0.875rem;
          color:rgba(255,255,255,0.42);
          text-decoration:none;
          transition:color .18s;
        }
        .cl-nav-back:hover{color:#fff}
        /* MAIN */
        .cl-main{
          flex:1;
          padding:3rem 1.5rem 5rem;
          position:relative;
        }
        .cl-bg{
          position:absolute;
          inset:0;
          background:
            radial-gradient(ellipse 80% 55% at 50% -10%,rgba(0,229,255,0.06) 0%,transparent 60%),
            radial-gradient(ellipse 50% 40% at 80% 90%,rgba(255,107,53,0.05) 0%,transparent 55%);
          pointer-events:none;
        }
        .cl-container{
          position:relative;
          max-width:720px;
          margin:0 auto;
        }
        /* Header */
        .cl-header{
          text-align:center;
          margin-bottom:3rem;
        }
        .cl-title{
          font-family:'Exo 2',sans-serif;
          font-weight:900;
          font-size:2.5rem;
          color:#fff;
          letter-spacing:-0.02em;
          line-height:1.1;
          margin:0 0 0.75rem;
        }
        .cl-subtitle{
          font-size:1rem;
          color:rgba(255,255,255,0.42);
          font-weight:300;
          margin:0 0 1.5rem;
        }
        .cl-header-btn{
          display:inline-flex;
          align-items:center;
          gap:0.45rem;
          padding:0.55rem 1.1rem;
          border-radius:999px;
          background:rgba(0,229,255,0.08);
          border:1px solid rgba(0,229,255,0.25);
          color:#00e5ff;
          font-family:'Barlow',sans-serif;
          font-size:0.85rem;
          font-weight:600;
          text-decoration:none;
          transition:background .18s,border-color .18s,transform .14s;
        }
        .cl-header-btn:hover{
          background:rgba(0,229,255,0.14);
          border-color:rgba(0,229,255,0.45);
          transform:translateY(-1px);
        }
        /* Timeline */
        .cl-timeline{
          position:relative;
          padding-left:2rem;
        }
        .cl-timeline::before{
          content:'';
          position:absolute;
          left:0.55rem;
          top:0.8rem;
          bottom:0.8rem;
          width:1px;
          background:linear-gradient(to bottom,rgba(0,229,255,0.35),rgba(0,229,255,0.05));
        }
        .cl-entry{
          position:relative;
          margin-bottom:2.5rem;
        }
        .cl-entry:last-child{margin-bottom:0}
        .cl-entry::before{
          content:'';
          position:absolute;
          left:-1.79rem;
          top:0.65rem;
          width:12px;
          height:12px;
          border-radius:50%;
          background:#06090f;
          border:2px solid rgba(0,229,255,0.5);
        }
        .cl-entry.latest::before{
          background:#00e5ff;
          border-color:#00e5ff;
          box-shadow:0 0 16px rgba(0,229,255,0.6);
        }
        .cl-entry-card{
          background:#111827;
          border:1px solid rgba(255,255,255,0.08);
          border-radius:14px;
          padding:1.5rem 1.75rem;
          box-shadow:0 20px 60px rgba(0,0,0,0.35);
        }
        .cl-entry.latest .cl-entry-card{
          border-color:rgba(0,229,255,0.22);
          box-shadow:0 20px 60px rgba(0,0,0,0.35),0 0 40px rgba(0,229,255,0.05);
        }
        .cl-entry-head{
          display:flex;
          align-items:center;
          justify-content:space-between;
          gap:1rem;
          flex-wrap:wrap;
          margin-bottom:0.8rem;
        }
        .cl-entry-version{
          display:flex;
          align-items:baseline;
          gap:0.5rem;
        }
        .cl-entry-vnum{
          font-family:'JetBrains Mono',monospace;
          font-weight:700;
          font-size:1.15rem;
          color:#00e5ff;
          letter-spacing:-0.01em;
        }
        .cl-entry-latest-tag{
          display:inline-block;
          padding:0.15rem 0.5rem;
          border-radius:999px;
          background:rgba(0,229,255,0.14);
          border:1px solid rgba(0,229,255,0.35);
          color:#00e5ff;
          font-family:'Exo 2',sans-serif;
          font-size:0.62rem;
          font-weight:700;
          letter-spacing:0.1em;
          text-transform:uppercase;
        }
        .cl-entry-meta{
          display:flex;
          align-items:center;
          gap:0.65rem;
          font-size:0.76rem;
          color:rgba(255,255,255,0.38);
        }
        .cl-entry-meta-dot{
          width:3px;
          height:3px;
          border-radius:50%;
          background:rgba(255,255,255,0.18);
        }
        .cl-entry-notes{
          font-size:0.88rem;
          color:rgba(255,255,255,0.68);
          white-space:pre-wrap;
          line-height:1.7;
        }
        .cl-entry-notes-empty{
          font-size:0.85rem;
          color:rgba(255,255,255,0.28);
          font-style:italic;
        }
        /* Empty state */
        .cl-empty{
          text-align:center;
          padding:4rem 2rem;
          background:#111827;
          border:1px dashed rgba(255,255,255,0.08);
          border-radius:16px;
        }
        .cl-empty-title{
          font-family:'Exo 2',sans-serif;
          font-weight:800;
          font-size:1.3rem;
          color:#fff;
          margin:0 0 0.6rem;
        }
        .cl-empty-sub{
          font-size:0.9rem;
          color:rgba(255,255,255,0.38);
          margin:0;
        }
        /* Footer */
        .cl-footer{
          text-align:center;
          padding:1.5rem;
          font-size:0.75rem;
          color:rgba(255,255,255,0.2);
          border-top:1px solid rgba(255,255,255,0.05);
        }
        .cl-footer a{
          color:rgba(0,229,255,0.5);
          text-decoration:none;
        }
        .cl-footer a:hover{color:#00e5ff}
        @media(max-width:640px){
          .cl-title{font-size:1.9rem}
          .cl-main{padding:2rem 1rem 4rem}
          .cl-timeline{padding-left:1.5rem}
          .cl-entry::before{left:-1.3rem}
          .cl-entry-card{padding:1.1rem 1.2rem}
          .cl-nav{padding:0 1rem}
        }
      `}</style>

      <div className="cl-page">
        {/* Navigation */}
        <nav className="cl-nav">
          <a href="/" className="cl-nav-brand" aria-label="Aervyx home">
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
            <span className="cl-nav-wordmark">
              Aervyx<span className="cl-nav-tld">.net</span>
            </span>
          </a>
          <a href="/app" className="cl-nav-back">
            &larr; Back to download
          </a>
        </nav>

        {/* Main */}
        <main className="cl-main">
          <div className="cl-bg" aria-hidden="true" />

          <div className="cl-container">
            {/* Header */}
            <header className="cl-header">
              <h1 className="cl-title">Changelog</h1>
              <p className="cl-subtitle">
                Every version of the Aervyx Pilot Android app
              </p>
              {latest && (
                <a href="/app" className="cl-header-btn">
                  <svg
                    width="14"
                    height="14"
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
                  Download latest (v{latest.version}+{latest.version_code})
                </a>
              )}
            </header>

            {/* Timeline */}
            {hasReleases ? (
              <div className="cl-timeline">
                {releases.map((release, index) => {
                  const isLatest = index === 0;
                  const hasNotes =
                    release.release_notes != null &&
                    release.release_notes.trim().length > 0;
                  return (
                    <article
                      key={`${release.version}-${release.version_code}`}
                      className={`cl-entry${isLatest ? " latest" : ""}`}
                    >
                      <div className="cl-entry-card">
                        <div className="cl-entry-head">
                          <div className="cl-entry-version">
                            <span className="cl-entry-vnum">
                              v{release.version}+{release.version_code}
                            </span>
                            {isLatest && (
                              <span className="cl-entry-latest-tag">Latest</span>
                            )}
                          </div>
                          <div className="cl-entry-meta">
                            {release.release_date && (
                              <span>{formatDate(release.release_date)}</span>
                            )}
                            {release.release_date &&
                              release.file_size_bytes != null &&
                              release.file_size_bytes > 0 && (
                                <span
                                  className="cl-entry-meta-dot"
                                  aria-hidden="true"
                                />
                              )}
                            {release.file_size_bytes != null &&
                              release.file_size_bytes > 0 && (
                                <span>{formatBytes(release.file_size_bytes)}</span>
                              )}
                          </div>
                        </div>
                        {hasNotes ? (
                          <div className="cl-entry-notes">
                            {release.release_notes}
                          </div>
                        ) : (
                          <div className="cl-entry-notes-empty">
                            No release notes for this version.
                          </div>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="cl-empty">
                <h2 className="cl-empty-title">No releases yet</h2>
                <p className="cl-empty-sub">
                  Check back soon — the first version is on its way.
                </p>
              </div>
            )}
          </div>
        </main>

        {/* Footer */}
        <footer className="cl-footer">
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
