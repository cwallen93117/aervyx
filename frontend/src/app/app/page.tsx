"use client";

import { useEffect, useState } from "react";

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) return configured;
  if (typeof window !== "undefined") {
    if (configured) {
      try {
        const parsed = new URL(configured);
        if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1")
          return `${window.location.protocol}//${window.location.hostname}:${parsed.port || "8000"}`;
      } catch {
        return configured;
      }
      return configured;
    }
    return "/backend";
  }
  return configured ?? "/backend";
}

type VersionInfo = {
  version: string;
  version_code: number;
  download_url: string;
  release_notes: string;
  release_date: string;
  min_supported_version: string;
  file_size_bytes: number | null;
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  } catch {
    return iso;
  }
}

export default function AppDownloadPage() {
  const [info, setInfo] = useState<VersionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch(`${resolveApiBase()}/api/app/version`)
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((d) => setInfo(d))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  const downloadHref = info?.download_url || (info ? `${resolveApiBase()}/api/app/download` : "#");

  return (
    <main style={styles.shell}>
      {/* background glow */}
      <div style={styles.glowCyan} />
      <div style={styles.glowPurple} />

      <div style={styles.container}>
        {/* brand */}
        <a href="/" style={styles.brand}>
          <span style={styles.brandMark}>{"\u25B3"}</span>
          <span style={styles.brandWord}>Aervyx.net</span>
        </a>

        {/* hero */}
        <div style={styles.hero}>
          <div style={styles.iconWrap}>
            <svg width="60" height="60" viewBox="0 0 30 30" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M15 3L27 25L15 19L3 25Z" stroke="#00e5ff" strokeWidth="1.5" fill="none" strokeLinejoin="round"/>
              <path d="M15 3L15 19" stroke="#00e5ff" strokeWidth="1" opacity=".4"/>
              <circle cx="15" cy="15" r="2.2" fill="#00e5ff" opacity=".85"/>
              <circle cx="15" cy="15" r="5" stroke="#00e5ff" strokeWidth=".5" fill="none" opacity=".22"/>
            </svg>
          </div>
          <h1 style={styles.title}>Aervyx</h1>
          <p style={styles.tagline}>Competition companion for hang gliding & paragliding</p>
          {info && (
            <div style={styles.versionRow}>
              <span style={styles.versionBadge}>v{info.version}+{info.version_code}</span>
              <a href="/changelog" style={styles.changelogLink}>View changelog -&gt;</a>
            </div>
          )}
        </div>

        {/* download */}
        {loading ? (
          <div style={styles.statusCard}>
            <p style={styles.statusText}>Loading release info...</p>
          </div>
        ) : error || !info ? (
          <div style={styles.statusCard}>
            <p style={styles.statusText}>No releases available yet. Check back soon.</p>
            <a href="/" style={styles.backLink}>Back to Aervyx</a>
          </div>
        ) : (
          <>
            <a href={downloadHref} style={styles.downloadBtn}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 10, flexShrink: 0 }}>
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Download APK
              {info.file_size_bytes ? (
                <span style={styles.fileSize}>{formatBytes(info.file_size_bytes)}</span>
              ) : null}
            </a>

            {/* what's new */}
            <section style={styles.card}>
              <span style={styles.eyebrow}>WHAT&apos;S NEW</span>
              <p style={styles.releaseDate}>Released {formatDate(info.release_date)}</p>
              {info.release_notes ? (
                <p style={styles.notes}>{info.release_notes}</p>
              ) : (
                <p style={{ ...styles.notes, color: "rgba(255,255,255,0.35)", fontStyle: "italic" }}>
                  No release notes for this version.
                </p>
              )}
            </section>

            {/* requirements */}
            <section style={styles.card}>
              <span style={styles.eyebrow}>REQUIREMENTS</span>
              <ul style={styles.list}>
                <li>Android 6.0 or later (API 23+)</li>
                <li>Location permission (GPS tracking)</li>
                <li>Bluetooth (Meshtastic mesh networking)</li>
                <li>Internet connection</li>
              </ul>
            </section>

            {/* install instructions */}
            <section style={styles.card}>
              <span style={styles.eyebrow}>HOW TO INSTALL</span>
              <ol style={styles.list}>
                <li>Tap <strong>Download APK</strong> above</li>
                <li>When prompted, allow installing from this source</li>
                <li>Open the downloaded file to install</li>
                <li>Launch Aervyx and sign in with your account</li>
              </ol>
            </section>

            <a href="/" style={styles.backLink}>Back to Aervyx</a>
          </>
        )}
      </div>
    </main>
  );
}

/* ── inline styles ─────────────────────────────────────────────── */

const styles: Record<string, React.CSSProperties> = {
  shell: {
    minHeight: "100vh",
    background: "linear-gradient(180deg, #06090f 0%, #0b1120 50%, #06090f 100%)",
    color: "rgba(255,255,255,0.88)",
    fontFamily: "'Barlow', sans-serif",
    position: "relative",
    overflow: "hidden",
  },
  glowCyan: {
    position: "absolute",
    top: "-20%",
    left: "30%",
    width: "40vw",
    height: "40vw",
    borderRadius: "50%",
    background: "radial-gradient(circle, rgba(0,229,255,0.08) 0%, transparent 70%)",
    pointerEvents: "none",
  },
  glowPurple: {
    position: "absolute",
    top: "30%",
    right: "10%",
    width: "30vw",
    height: "30vw",
    borderRadius: "50%",
    background: "radial-gradient(circle, rgba(167,139,250,0.06) 0%, transparent 70%)",
    pointerEvents: "none",
  },
  container: {
    position: "relative",
    maxWidth: 480,
    margin: "0 auto",
    padding: "40px 24px 60px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 24,
  },
  brand: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    textDecoration: "none",
    color: "rgba(255,255,255,0.88)",
    marginBottom: 8,
  },
  brandMark: {
    fontSize: 28,
    color: "#00e5ff",
    fontFamily: "'Exo 2', sans-serif",
    fontWeight: 900,
  },
  brandWord: {
    fontSize: 20,
    fontFamily: "'Exo 2', sans-serif",
    fontWeight: 700,
    letterSpacing: "0.02em",
  },
  hero: {
    textAlign: "center" as const,
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    gap: 12,
  },
  iconWrap: {
    width: 96,
    height: 96,
    borderRadius: 24,
    background: "rgba(0,229,255,0.06)",
    border: "1px solid rgba(0,229,255,0.15)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    fontSize: "clamp(2.2rem, 6vw, 3rem)",
    fontFamily: "'Exo 2', sans-serif",
    fontWeight: 900,
    margin: 0,
    letterSpacing: "-0.02em",
  },
  tagline: {
    fontSize: 16,
    color: "rgba(255,255,255,0.55)",
    margin: 0,
    maxWidth: 300,
  },
  versionRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    flexWrap: "wrap" as const,
    justifyContent: "center",
    marginTop: 4,
  },
  versionBadge: {
    display: "inline-block",
    padding: "4px 14px",
    borderRadius: 20,
    border: "1px solid rgba(0,229,255,0.25)",
    color: "#00e5ff",
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: "0.04em",
    fontFamily: "'JetBrains Mono', monospace",
  },
  changelogLink: {
    fontSize: 13,
    color: "rgba(0,229,255,0.7)",
    textDecoration: "none",
    fontWeight: 500,
    transition: "color 0.15s",
  },
  downloadBtn: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "100%",
    padding: "16px 32px",
    borderRadius: 12,
    background: "#00e5ff",
    color: "#06090f",
    fontFamily: "'Barlow', sans-serif",
    fontSize: 18,
    fontWeight: 700,
    textDecoration: "none",
    boxShadow: "0 0 34px rgba(0,229,255,0.3)",
    transition: "transform 0.15s, box-shadow 0.15s",
    cursor: "pointer",
  },
  fileSize: {
    marginLeft: 10,
    fontSize: 14,
    fontWeight: 500,
    opacity: 0.7,
  },
  card: {
    width: "100%",
    padding: "20px 24px",
    borderRadius: 12,
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.07)",
  },
  eyebrow: {
    display: "block",
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.12em",
    color: "#00e5ff",
    marginBottom: 10,
  },
  releaseDate: {
    fontSize: 13,
    color: "rgba(255,255,255,0.42)",
    margin: "0 0 8px 0",
  },
  notes: {
    fontSize: 15,
    lineHeight: 1.6,
    margin: 0,
    color: "rgba(255,255,255,0.75)",
    whiteSpace: "pre-line" as const,
  },
  list: {
    margin: 0,
    paddingLeft: 20,
    fontSize: 15,
    lineHeight: 1.8,
    color: "rgba(255,255,255,0.75)",
  },
  statusCard: {
    textAlign: "center" as const,
    padding: "40px 24px",
    borderRadius: 12,
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.07)",
    width: "100%",
  },
  statusText: {
    fontSize: 16,
    color: "rgba(255,255,255,0.55)",
    margin: 0,
  },
  backLink: {
    fontSize: 14,
    color: "rgba(255,255,255,0.42)",
    textDecoration: "none",
    marginTop: 8,
  },
};
