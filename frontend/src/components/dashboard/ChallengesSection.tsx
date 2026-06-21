"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { SectionCard } from "../SectionCard";
import type { BuddyGroup, EventRecord } from "./types";

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
      } catch {
        return configured;
      }
      return configured;
    }
    return "/backend";
  }
  return configured ?? "/backend";
}

async function apiFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${resolveApiBase()}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Request failed: ${response.status}`);
  }
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

type ChallengeForm = {
  name: string;
  challenge_type: "open_distance" | "race_to_goal_with_gates";
  starts_on: string;
  ends_on: string;
  location: string;
  source_buddy_group_id: string;
  is_public_tracking: boolean;
};

const today = new Date().toISOString().slice(0, 10);

function blankChallengeForm(): ChallengeForm {
  return {
    name: "New XC Challenge",
    challenge_type: "open_distance",
    starts_on: today,
    ends_on: today,
    location: "",
    source_buddy_group_id: "",
    is_public_tracking: false,
  };
}

export default function ChallengesSection({
  token,
  onOpenChallenge,
}: {
  token: string;
  onOpenChallenge: (challenge: EventRecord) => void;
}) {
  const [challenges, setChallenges] = useState<EventRecord[]>([]);
  const [groups, setGroups] = useState<BuddyGroup[]>([]);
  const [form, setForm] = useState<ChallengeForm>(blankChallengeForm);
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<{ type: "success" | "error" | "pending"; text: string } | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [loadedChallenges, loadedGroups] = await Promise.all([
        apiFetch<EventRecord[]>("/api/challenges", token),
        apiFetch<BuddyGroup[]>("/api/buddies/groups", token),
      ]);
      setChallenges(loadedChallenges);
      setGroups(loadedGroups);
    } catch (caught) {
      setFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not load challenges." });
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  async function createChallenge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedback({ type: "pending", text: "Creating challenge..." });
    try {
      const created = await apiFetch<EventRecord>("/api/challenges", token, {
        method: "POST",
        body: JSON.stringify({
          ...form,
          source_buddy_group_id: form.source_buddy_group_id ? Number(form.source_buddy_group_id) : null,
          visibility: "public",
          public_listed: false,
        }),
      });
      setForm(blankChallengeForm());
      setFeedback({ type: "success", text: `Created ${created.name}.` });
      await loadData();
      onOpenChallenge(created);
    } catch (caught) {
      setFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Challenge creation failed." });
    }
  }

  return (
    <div className="challenge-layout">
      <SectionCard title="Create Challenge" description="One-off XC and race-to-goal comps use your saved challenge scoring settings.">
        {feedback ? <div className={`status-chip ${feedback.type}`}>{feedback.text}</div> : null}
        <form className="challenge-form" onSubmit={createChallenge}>
          <label className="stack compact">
            <span>Name</span>
            <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} maxLength={160} />
          </label>
          <label className="stack compact">
            <span>Type</span>
            <select value={form.challenge_type} onChange={(event) => setForm({ ...form, challenge_type: event.target.value as ChallengeForm["challenge_type"] })}>
              <option value="open_distance">XC open distance</option>
              <option value="race_to_goal_with_gates">Race to goal</option>
            </select>
          </label>
          <label className="stack compact">
            <span>Starts</span>
            <input type="date" value={form.starts_on} onChange={(event) => setForm({ ...form, starts_on: event.target.value, ends_on: form.ends_on || event.target.value })} />
          </label>
          <label className="stack compact">
            <span>Ends</span>
            <input type="date" value={form.ends_on} onChange={(event) => setForm({ ...form, ends_on: event.target.value })} />
          </label>
          <label className="stack compact">
            <span>Buddy group</span>
            <select value={form.source_buddy_group_id} onChange={(event) => setForm({ ...form, source_buddy_group_id: event.target.value })}>
              <option value="">Just me</option>
              {groups.map((group) => (
                <option key={group.id} value={group.id}>{group.name} ({group.members.length})</option>
              ))}
            </select>
          </label>
          <label className="stack compact">
            <span>Location</span>
            <input value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} maxLength={160} />
          </label>
          <label className="inline-check">
            <input type="checkbox" checked={form.is_public_tracking} onChange={(event) => setForm({ ...form, is_public_tracking: event.target.checked })} />
            <span>Show live tracking publicly</span>
          </label>
          <button type="submit" className="primary-button" disabled={!form.name.trim() || !form.starts_on || !form.ends_on}>
            Create challenge
          </button>
        </form>
      </SectionCard>

      <SectionCard title="My Challenges" description="Open a challenge to build tasks, invite pilots, and view scores.">
        {loading ? <p className="muted">Loading challenges...</p> : null}
        {!loading && !challenges.length ? <p className="muted">No challenges yet.</p> : null}
        <div className="challenge-list">
          {challenges.map((challenge) => (
            <button key={challenge.id} type="button" className="challenge-row" onClick={() => onOpenChallenge(challenge)}>
              <span>
                <strong>{challenge.name}</strong>
                <small>{challenge.starts_on} - {challenge.ends_on}</small>
              </span>
              <span className="challenge-meta">
                {challenge.pilot_count} pilot{challenge.pilot_count === 1 ? "" : "s"}
              </span>
            </button>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
