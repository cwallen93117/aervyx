"use client";

import { useCallback, useRef, useState } from "react";
import type { PilotClaimSearchResultRecord, PilotClaimResponseRecord } from "./types";

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) return configured;
  if (typeof window !== "undefined") {
    if (configured) {
      try {
        const parsed = new URL(configured);
        if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
          return `${window.location.protocol}//${window.location.hostname}:${parsed.port || "8000"}`;
        }
      } catch { return configured; }
      return configured;
    }
    return "/backend";
  }
  return configured ?? "/backend";
}

async function apiFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${resolveApiBase()}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Request failed: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export interface PilotClaimSectionProps {
  token: string;
  pilotId: number | null;
  onClaimed: () => void;
}

export default function PilotClaimSection({ token, pilotId, onClaimed }: PilotClaimSectionProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<PilotClaimSearchResultRecord[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [claimingId, setClaimingId] = useState<number | null>(null);
  const [claimCompNumber, setClaimCompNumber] = useState("");
  const [claimCivlId, setClaimCivlId] = useState("");
  const [expandedPilotId, setExpandedPilotId] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showFeedback = useCallback((type: "success" | "error", text: string) => {
    setFeedback({ type, text });
    setTimeout(() => setFeedback(null), 4000);
  }, []);

  function handleSearchInput(query: string) {
    setSearchQuery(query);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (query.trim().length < 2) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    searchTimer.current = setTimeout(async () => {
      try {
        const results = await apiFetch<PilotClaimSearchResultRecord[]>(
          `/api/auth/pilot-search?q=${encodeURIComponent(query.trim())}`,
          token,
        );
        setSearchResults(results);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 300);
  }

  async function claimPilot(pilotIdToClaim: number, compNum: string, civlId: string) {
    setClaimingId(pilotIdToClaim);
    try {
      const result = await apiFetch<PilotClaimResponseRecord>("/api/auth/claim-pilot", token, {
        method: "POST",
        body: JSON.stringify({
          pilot_id: pilotIdToClaim,
          competition_number: compNum.trim() || null,
          civl_id: civlId.trim() || null,
        }),
      });
      showFeedback("success", result.message);
      setSearchQuery("");
      setSearchResults([]);
      setExpandedPilotId(null);
      setClaimCompNumber("");
      setClaimCivlId("");
      onClaimed();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Claim failed";
      try {
        const parsed = JSON.parse(msg);
        showFeedback("error", parsed.detail || msg);
      } catch {
        showFeedback("error", msg);
      }
    } finally {
      setClaimingId(null);
    }
  }

  // If user already has a linked pilot, show a summary
  if (pilotId) {
    return (
      <div className="stack">
        <div className="status-chip success">
          Your account is linked to pilot record #{pilotId}. Your flights, scores, and event participation are synced.
        </div>
      </div>
    );
  }

  return (
    <div className="stack">
      <p className="settings-description">
        Search for your pilot record to link it with your account. This connects event results, uploaded flights, and scores to your logbook.
      </p>

      {feedback ? <div className={`status-chip ${feedback.type}`}>{feedback.text}</div> : null}

      <div className="buddy-create-row">
        <input
          className="buddy-create-input"
          value={searchQuery}
          onChange={(e) => handleSearchInput(e.target.value)}
          placeholder="Search by pilot name or comp number"
        />
      </div>

      {searchLoading ? <p className="muted">Searching...</p> : null}

      {searchResults.length > 0 ? (
        <div className="buddy-groups-list">
          {searchResults.map((pilot) => (
            <div key={pilot.pilot_id} className="buddy-group-card">
              <div className="buddy-group-header">
                <strong className="buddy-group-name">
                  {pilot.first_name} {pilot.last_name}
                </strong>
                {pilot.nation ? <span className="muted"> ({pilot.nation})</span> : null}
                {pilot.competition_number ? <span className="muted"> #{pilot.competition_number}</span> : null}
              </div>

              {pilot.can_instant_claim ? (
                <div className="buddy-search-area">
                  <p className="muted">Email match found &mdash; instant claim available.</p>
                  <button
                    type="button"
                    onClick={() => claimPilot(pilot.pilot_id, "", "")}
                    disabled={claimingId === pilot.pilot_id}
                  >
                    {claimingId === pilot.pilot_id ? "Claiming..." : "Claim this pilot record"}
                  </button>
                </div>
              ) : expandedPilotId === pilot.pilot_id ? (
                <div className="buddy-search-area">
                  <p className="muted">
                    Verify your identity by providing your competition number or CIVL ID.
                  </p>
                  <div className="inline-grid">
                    <label className="stack compact">
                      <span>Competition number</span>
                      <input
                        value={claimCompNumber}
                        onChange={(e) => setClaimCompNumber(e.target.value)}
                        placeholder="e.g. 42"
                      />
                    </label>
                    <label className="stack compact">
                      <span>CIVL ID</span>
                      <input
                        value={claimCivlId}
                        onChange={(e) => setClaimCivlId(e.target.value)}
                        placeholder="e.g. 12345"
                      />
                    </label>
                  </div>
                  <div className="button-row">
                    <button
                      type="button"
                      onClick={() => claimPilot(pilot.pilot_id, claimCompNumber, claimCivlId)}
                      disabled={claimingId === pilot.pilot_id || (!claimCompNumber.trim() && !claimCivlId.trim())}
                    >
                      {claimingId === pilot.pilot_id ? "Claiming..." : "Verify & claim"}
                    </button>
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={() => { setExpandedPilotId(null); setClaimCompNumber(""); setClaimCivlId(""); }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  className="ghost-button buddy-add-btn"
                  onClick={() => { setExpandedPilotId(pilot.pilot_id); setClaimCompNumber(""); setClaimCivlId(""); }}
                >
                  Claim this record
                </button>
              )}
            </div>
          ))}
        </div>
      ) : searchQuery.trim().length >= 2 && !searchLoading ? (
        <p className="muted">No unclaimed pilot records found.</p>
      ) : null}
    </div>
  );
}
